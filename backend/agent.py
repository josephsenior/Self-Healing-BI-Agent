import json
import uuid
import logging
import asyncio
from typing import Dict, Any, List, Literal, Union, AsyncGenerator
from contextlib import asynccontextmanager

import openai
import anthropic

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
import mcp.types as types

logger = logging.getLogger("mcp_agent")
logging.basicConfig(level=logging.INFO)

# Resolve the absolute path to the root .env file (one level above backend/agent.py)
ROOT_DIR = Path(__file__).resolve().parent.parent
ENV_FILE = ROOT_DIR / ".env"

class AgentConfig(BaseSettings):
    transport_mode: str = Field(default="STDIO", alias="POWERBI_TRANSPORT_MODE")
    sse_url: str = Field(default="https://api.fabric.microsoft.com/v1/mcp/powerbi", alias="POWERBI_SSE_URL")
    fabric_access_token: str = Field(default="", alias="FABRIC_ACCESS_TOKEN")
    stdio_command: str = Field(default="npx", alias="POWERBI_STDIO_COMMAND")
    stdio_args: list[str] = ["-y", "@microsoft/powerbi-modeling-mcp", "--start"]
    llm_provider: str = Field(default="gemini", alias="LLM_PROVIDER")
    llm_model: str = Field(default="gemini-2.5-flash", alias="LLM_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")

    model_config = {"env_file": str(ENV_FILE), "extra": "ignore", "populate_by_name": True}

config = AgentConfig()

# ==============================================================================
# SYSTEM PROMPT
# ==============================================================================
SYSTEM_PROMPT = """You are an expert Power BI data analyst and semantic model engineer.
You have access to Microsoft Power BI tools via the Model Context Protocol (MCP).

Your capabilities include:
- Executing DAX queries against semantic models
- Inspecting model metadata (tables, columns, measures, relationships)
- Creating and modifying measures, calculated columns, and tables
- Evaluating and applying modeling best practices

Guidelines:
- **Connection Rule**: Before executing any model operations (like listing tables, getting measures, executing DAX queries), you MUST verify that you are connected. If you get a "No connectionName provided" or "no last used connection available" error, you must first call `connection_operations` with `ListLocalInstances` to list all running local instances, and then call `connection_operations` with `Connect` specifying the connectionName or port of the active instance.
- Always validate DAX syntax before executing queries.
- When modifying a model, explain what you are about to change and why.
- Present query results in clear, formatted tables when possible.
- If a tool call fails, diagnose the error and suggest a fix.
- Be concise but thorough in your explanations."""

# ==============================================================================
# ELICITATION COORDINATOR (SAFETY APPROVALS)
# ==============================================================================
class ElicitationCoordinator:
    """
    Coordinates human-in-the-loop approvals between the background MCP ClientSession
    and the active WebSocket frontend client.
    """
    def __init__(self):
        self._pending_responses: Dict[str, asyncio.Future] = {}
        self._send_to_client_callback = None

    def set_send_callback(self, callback):
        """Register the WebSocket send callback."""
        self._send_to_client_callback = callback

    async def request_elicitation(
        self,
        message: str,
        mode: Literal["form", "url"],
        schema: Dict[str, Any] = None,
        url: str = None
    ) -> Dict[str, Any]:
        """
        Called inside the elicitation_callback of the MCP ClientSession.
        Suspends execution and alerts the WebSocket frontend.
        """
        elicitation_id = str(uuid.uuid4())
        future = asyncio.get_running_loop().create_future()
        self._pending_responses[elicitation_id] = future

        payload = {
            "type": "elicitation_request",
            "id": elicitation_id,
            "mode": mode,
            "message": message,
            "schema": schema,
            "url": url
        }

        logger.info(f"Suspending tool execution for safety approval. ID: {elicitation_id}")

        if self._send_to_client_callback:
            # Send elicitation request to the WebSocket frontend
            await self._send_to_client_callback(payload)
        else:
            logger.warning("No active WebSocket client. Automatically declining safety prompt.")
            return {"action": "decline", "content": None}

        try:
            # Wait for response from frontend
            result = await future
            logger.info(f"Safety approval response received for ID: {elicitation_id} -> {result['action']}")
            return result
        except Exception as e:
            logger.error(f"Error waiting for elicitation response: {e}")
            return {"action": "decline", "content": None}
        finally:
            self._pending_responses.pop(elicitation_id, None)

    def submit_response(self, elicitation_id: str, action: str, content: Any):
        """
        Called when the WebSocket endpoint receives the user's action.
        """
        future = self._pending_responses.get(elicitation_id)
        if future and not future.done():
            future.set_result({
                "action": action,
                "content": content
            })

def create_elicitation_callback(coordinator: ElicitationCoordinator):
    """Factory to create a callback matching ElicitationFnT."""
    async def callback(context, params: Union[types.ElicitRequestFormParams, types.ElicitRequestURLParams]) -> types.ElicitResult:
        mode = params.mode
        message = params.message
        schema = getattr(params, "requestedSchema", None)
        url = getattr(params, "url", None)

        result = await coordinator.request_elicitation(
            message=message,
            mode=mode,
            schema=schema,
            url=url
        )

        return types.ElicitResult(
            action=result["action"],
            content=result["content"]
        )
    return callback

# ==============================================================================
# DUAL-TRANSPORT MCP CLIENT SESSION
# ==============================================================================
@asynccontextmanager
async def mcp_session_scope(coordinator: ElicitationCoordinator) -> AsyncGenerator[ClientSession, None]:
    """
    Context manager to yield an initialized ClientSession based on the
    transport_mode configuration (SSE or STDIO).
    """
    elicitation_cb = create_elicitation_callback(coordinator)

    if config.transport_mode.upper() == "SSE":
        logger.info(f"Connecting to remote Power BI server via SSE: {config.sse_url}")
        headers = {}
        if config.fabric_access_token:
            headers["Authorization"] = f"Bearer {config.fabric_access_token}"

        async with sse_client(url=config.sse_url, headers=headers) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, elicitation_callback=elicitation_cb) as session:
                await session.initialize()
                yield session
    else:
        import os
        import shutil
        stdio_cmd = config.stdio_command
        if os.name == "nt" and not stdio_cmd.endswith((".exe", ".cmd", ".bat")):
            for ext in (".cmd", ".bat", ".exe"):
                if shutil.which(stdio_cmd + ext):
                    stdio_cmd = stdio_cmd + ext
                    break
            if not stdio_cmd.endswith((".cmd", ".bat", ".exe")):
                default_node_npx = os.path.join("C:\\Program Files\\nodejs", stdio_cmd + ".cmd")
                if os.path.exists(default_node_npx):
                    stdio_cmd = default_node_npx
        
        # Prepend Node.js directory to PATH to avoid 'node' command not found errors
        node_dir = r"C:\Program Files\nodejs"
        custom_env = os.environ.copy()
        custom_env["PATH"] = node_dir + os.pathsep + custom_env.get("PATH", "")

        logger.info(f"Connecting to local Power BI modeling server via STDIO. Executable: {stdio_cmd}")
        server_params = StdioServerParameters(
            command=stdio_cmd,
            args=config.stdio_args,
            env=custom_env
        )
        async with stdio_client(server_params) as (read_stream, write_stream):
            async with ClientSession(read_stream, write_stream, elicitation_callback=elicitation_cb) as session:
                await session.initialize()
                yield session

# ==============================================================================
# TOOL SCHEMAS MAPPING
# ==============================================================================
def map_mcp_tools_to_openai(mcp_tools: types.ListToolsResult) -> List[Dict[str, Any]]:
    """Convert MCP schemas to OpenAI tool schemas."""
    openai_tools = []
    for tool in mcp_tools.tools:
        openai_tools.append({
            "type": "function",
            "function": {
                "name": tool.name,
                "description": tool.description or "",
                "parameters": tool.inputSchema
            }
        })
    return openai_tools

def map_mcp_tools_to_anthropic(mcp_tools: types.ListToolsResult) -> List[Dict[str, Any]]:
    """Convert MCP schemas to Anthropic tool schemas."""
    anthropic_tools = []
    for tool in mcp_tools.tools:
        anthropic_tools.append({
            "name": tool.name,
            "description": tool.description or "",
            "input_schema": tool.inputSchema
        })
    return anthropic_tools

# ==============================================================================
# AGENT EXECUTION LOOP
# ==============================================================================
async def run_agent_loop(
    query: str,
    session: ClientSession,
    llm_provider: str = None,
    llm_model: str = None
) -> AsyncGenerator[Dict[str, Any], None]:
    """
    Main asynchronous agent execution generator. Streams responses and tool states
    back to the caller.
    """
    # Fall back to config values when not explicitly provided
    llm_provider = llm_provider or config.llm_provider
    llm_model = llm_model or config.llm_model

    mcp_tools = await session.list_tools()

    # Emit tools_discovered event for the frontend
    tool_names = [t.name for t in mcp_tools.tools]
    yield {"type": "tools_discovered", "tools": tool_names, "count": len(tool_names)}

    # Initialize LLM Clients
    openai_client = openai.AsyncOpenAI(api_key=config.openai_api_key)
    anthropic_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key)
    gemini_client = openai.AsyncOpenAI(
        api_key=config.gemini_api_key,
        base_url="https://generativelanguage.googleapis.com/v1beta/openai/"
    )

    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": query}
    ]

    # Loop to support multi-turn reasoning and tool calling
    while True:
        if llm_provider == "gemini":
            # Map tools
            openai_tools = map_mcp_tools_to_openai(mcp_tools)

            # Call Gemini (Streaming)
            logger.info("Calling Gemini Chat Completion...")
            tool_calls_accumulator = {}
            text_accumulator = []

            stream = await gemini_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                tools=openai_tools if openai_tools else None,
                stream=True
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    text_accumulator.append(delta.content)
                    yield {"type": "token", "text": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        index = tc.index
                        if index not in tool_calls_accumulator:
                            tool_calls_accumulator[index] = {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {"name": "", "arguments": ""},
                                "extra_content": None
                            }
                        if tc.id:
                            tool_calls_accumulator[index]["id"] = tc.id
                        if hasattr(tc, "extra_content") and tc.extra_content:
                            tool_calls_accumulator[index]["extra_content"] = tc.extra_content
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accumulator[index]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accumulator[index]["function"]["arguments"] += tc.function.arguments

            # Process any tool calls accumulated
            if tool_calls_accumulator:
                tool_calls_list = []
                formatted_tool_calls_payload = []

                for idx, tc in sorted(tool_calls_accumulator.items()):
                    tool_call_dict = {
                        "id": tc["id"],
                        "type": "function",
                        "function": {
                            "name": tc["function"]["name"],
                            "arguments": tc["function"]["arguments"]
                        }
                    }
                    if tc.get("extra_content"):
                        tool_call_dict["extra_content"] = tc["extra_content"]
                    
                    tool_calls_list.append(tool_call_dict)
                    formatted_tool_calls_payload.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"])
                    })

                # Append assistant message with tool calls to context
                messages.append({
                    "role": "assistant",
                    "content": "".join(text_accumulator) or None,
                    "tool_calls": tool_calls_list
                })

                # Alert client of tool starts
                yield {"type": "tool_start", "calls": formatted_tool_calls_payload}

                # Execute tool calls
                for tc in tool_calls_list:
                    tool_name = tc["function"]["name"]
                    tool_args = json.loads(tc["function"]["arguments"])
                    tc_id = tc["id"]

                    try:
                        logger.info(f"Executing tool {tool_name} with args {tool_args}")
                        tool_result = await session.call_tool(tool_name, tool_args)

                        # Serialize result content
                        content_str = ""
                        for item in tool_result.content:
                            if item.type == "text":
                                content_str += item.text
                            else:
                                content_str += f"[{item.type} content]"

                        yield {"type": "tool_result", "id": tc_id, "name": tool_name, "result": content_str}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_name,
                            "content": content_str
                        })
                    except Exception as e:
                        logger.error(f"Error executing tool {tool_name}: {e}")
                        yield {"type": "tool_result", "id": tc_id, "name": tool_name, "error": str(e)}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_name,
                            "content": f"Error executing tool: {str(e)}"
                        })
                # Re-loop to feed tool results back to Gemini
                continue
            else:
                # Execution complete
                break

        elif llm_provider == "openai":
            # Map tools
            openai_tools = map_mcp_tools_to_openai(mcp_tools)

            # Call OpenAI (Streaming)
            logger.info("Calling OpenAI Chat Completion...")
            tool_calls_accumulator = {}
            text_accumulator = []

            stream = await openai_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                tools=openai_tools if openai_tools else None,
                stream=True
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if delta.content:
                    text_accumulator.append(delta.content)
                    yield {"type": "token", "text": delta.content}

                if delta.tool_calls:
                    for tc in delta.tool_calls:
                        index = tc.index
                        if index not in tool_calls_accumulator:
                            tool_calls_accumulator[index] = {
                                "id": tc.id,
                                "type": tc.type,
                                "function": {"name": "", "arguments": ""}
                            }
                        if tc.id:
                            tool_calls_accumulator[index]["id"] = tc.id
                        if tc.function:
                            if tc.function.name:
                                tool_calls_accumulator[index]["function"]["name"] = tc.function.name
                            if tc.function.arguments:
                                tool_calls_accumulator[index]["function"]["arguments"] += tc.function.arguments

            # Process any tool calls accumulated
            if tool_calls_accumulator:
                tool_calls_list = []
                formatted_tool_calls_payload = []

                for idx, tc in sorted(tool_calls_accumulator.items()):
                    openai_tc = openai.types.chat.chat_completion_message_tool_call.ChatCompletionMessageToolCall(
                        id=tc["id"],
                        type="function",
                        function=openai.types.chat.chat_completion_message_tool_call.Function(
                            name=tc["function"]["name"],
                            arguments=tc["function"]["arguments"]
                        )
                    )
                    tool_calls_list.append(openai_tc)
                    formatted_tool_calls_payload.append({
                        "id": tc["id"],
                        "name": tc["function"]["name"],
                        "arguments": json.loads(tc["function"]["arguments"])
                    })

                # Append assistant message with tool calls to context
                messages.append({
                    "role": "assistant",
                    "content": "".join(text_accumulator) or None,
                    "tool_calls": tool_calls_list
                })

                # Alert client of tool starts
                yield {"type": "tool_start", "calls": formatted_tool_calls_payload}

                # Execute tool calls
                for tc in tool_calls_list:
                    tool_name = tc.function.name
                    tool_args = json.loads(tc.function.arguments)

                    try:
                        logger.info(f"Executing tool {tool_name} with args {tool_args}")
                        tool_result = await session.call_tool(tool_name, tool_args)

                        # Serialize result content
                        content_str = ""
                        for item in tool_result.content:
                            if item.type == "text":
                                content_str += item.text
                            else:
                                content_str += f"[{item.type} content]"

                        yield {"type": "tool_result", "id": tc.id, "name": tool_name, "result": content_str}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "content": content_str
                        })
                    except Exception as e:
                        logger.error(f"Error executing tool {tool_name}: {e}")
                        yield {"type": "tool_result", "id": tc.id, "name": tool_name, "error": str(e)}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "name": tool_name,
                            "content": f"Error executing tool: {str(e)}"
                        })
                # Re-loop to feed tool results back to OpenAI
                continue
            else:
                # Execution complete
                break

        elif llm_provider == "anthropic":
            # Map tools
            anthropic_tools = map_mcp_tools_to_anthropic(mcp_tools)

            # Convert messages structure for Anthropic
            # Anthropic expects 'user' and 'assistant' roles, with tool blocks
            # Filter out system messages — Anthropic uses the `system` parameter instead
            anthropic_messages = []
            for msg in messages:
                role = msg["role"]
                # Skip system messages — passed via the `system` parameter
                if role == "system":
                    continue
                # Convert 'tool' role messages to tool_result content in Anthropic
                if role == "tool":
                    anthropic_messages.append({
                        "role": "user",
                        "content": [{
                            "type": "tool_result",
                            "tool_use_id": msg["tool_call_id"],
                            "content": msg["content"]
                        }]
                    })
                elif role == "assistant" and "tool_calls" in msg and msg["tool_calls"]:
                    # Convert tool calls to Anthropic tool_use blocks
                    content = []
                    if msg.get("content"):
                        content.append({"type": "text", "text": msg["content"]})
                    for tc in msg["tool_calls"]:
                        content.append({
                            "type": "tool_use",
                            "id": tc.id,
                            "name": tc.function.name,
                            "input": json.loads(tc.function.arguments)
                        })
                    anthropic_messages.append({"role": "assistant", "content": content})
                else:
                    anthropic_messages.append({"role": role, "content": msg["content"]})

            # Call Anthropic (Streaming)
            logger.info("Calling Anthropic messages stream...")
            content_accumulator = []
            tool_calls_accumulator = {}

            # Wrap async context manager
            async with anthropic_client.messages.stream(
                model=llm_model,
                max_tokens=4096,
                system=SYSTEM_PROMPT,
                messages=anthropic_messages,
                tools=anthropic_tools if anthropic_tools else None
            ) as stream:
                async for event in stream:
                    if event.type == "text":
                        yield {"type": "token", "text": event.text}
                        content_accumulator.append({"type": "text", "text": event.text})
                    elif event.type == "tool_use":
                        tool_calls_accumulator[event.id] = {
                            "id": event.id,
                            "name": event.name,
                            "input": event.input
                        }

            if tool_calls_accumulator:
                # Map to standard OpenAI-style messages for internal state tracking
                standard_tc_list = []
                formatted_tool_calls_payload = []

                for tc_id, tc in tool_calls_accumulator.items():
                    standard_tc_list.append(
                        openai.types.chat.chat_completion_message_tool_call.ChatCompletionMessageToolCall(
                            id=tc_id,
                            type="function",
                            function=openai.types.chat.chat_completion_message_tool_call.Function(
                                name=tc["name"],
                                arguments=json.dumps(tc["input"])
                            )
                        )
                    )
                    formatted_tool_calls_payload.append({
                        "id": tc_id,
                        "name": tc["name"],
                        "arguments": tc["input"]
                    })

                messages.append({
                    "role": "assistant",
                    "content": "".join([c["text"] for c in content_accumulator if c["type"] == "text"]) or None,
                    "tool_calls": standard_tc_list
                })

                yield {"type": "tool_start", "calls": formatted_tool_calls_payload}

                # Run tools
                for tc_id, tc in tool_calls_accumulator.items():
                    tool_name = tc["name"]
                    tool_args = tc["input"]
                    try:
                        logger.info(f"Executing tool {tool_name} with args {tool_args}")
                        tool_result = await session.call_tool(tool_name, tool_args)

                        content_str = ""
                        for item in tool_result.content:
                            if item.type == "text":
                                content_str += item.text
                            else:
                                content_str += f"[{item.type} content]"

                        yield {"type": "tool_result", "id": tc_id, "name": tool_name, "result": content_str}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_name,
                            "content": content_str
                        })
                    except Exception as e:
                        logger.error(f"Error executing tool {tool_name}: {e}")
                        yield {"type": "tool_result", "id": tc_id, "name": tool_name, "error": str(e)}
                        messages.append({
                            "role": "tool",
                            "tool_call_id": tc_id,
                            "name": tool_name,
                            "content": f"Error executing tool: {str(e)}"
                        })
                # Re-loop to feed tool results to Anthropic
                continue
            else:
                break
        else:
            raise ValueError(f"Unknown LLM provider: {llm_provider}")
