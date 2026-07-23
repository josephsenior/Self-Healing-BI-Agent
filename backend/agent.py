import json
import uuid
import logging
import asyncio
from typing import Dict, Any, List, Literal, Union, AsyncGenerator
from contextlib import asynccontextmanager, AsyncExitStack

import openai
import anthropic

from pathlib import Path
from pydantic_settings import BaseSettings
from pydantic import Field

from google import genai
from google.genai import types as genai_types

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client
from mcp.client.sse import sse_client
import mcp.types as types

import httpx
logger = logging.getLogger("mcp_agent")
logging.basicConfig(level=logging.INFO)

# Global HTTP client with disabled SSL verification to bypass local/corporate proxy cert issues
http_client = httpx.AsyncClient(verify=False)

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
    llm_model: str = Field(default="gemini-3.6-flash", alias="LLM_MODEL")
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

**Report Authoring Rule**: When asked to create a dashboard, first clarify internally whether the user means a PBIR report page or a Power BI Service dashboard. For report authoring, inspect the semantic model and construct a SemanticModelCatalog from the live metadata. Submit the strict DashboardSpec through create_dashboard_workspace; creation, revision, and rollback automatically run the runtime QA admission controller. If a workspace tool returns `accepted: false` with `NEEDS_REVISION`, correct the blocking findings and retry with the complete spec. If it returns `NEEDS_REVIEW`, stop automatic retries and explain the remaining evidence. Only describe a version as verified when the tool returns `accepted: true` with `VERIFIED` or `VERIFIED_WITH_WARNINGS`. If and only if the user explicitly requests to open or preview the report locally in Power BI Desktop, call open_active_dashboard_in_powerbi_desktop. When cloud QA is configured and the user authorizes publication, continue with publish_pbir_to_fabric, render_powerbi_report, review_powerbi_render, and decide_powerbi_visual_qa_iteration. Never generate PBIR with run_python_sandbox and never claim a report was deployed or visually approved unless the corresponding tool result confirms it.

**Visual Selection Rule**: Before constructing or revising a DashboardSpec, call list_powerbi_visual_capabilities and use a listed visual type with its documented field roles and configuration. Prefer the generic `fields` map for new visuals; `category`, `values`, and `series` exist for compatibility with older specs. An unlisted custom visual is allowed only when the spec includes an inline `custom_visual` adapter that declares its exact data roles and confirms the visual is trusted and already installed. Never download or install a custom visual while authoring a report.

**Stateful Dashboard Revision Rule**: When the user refers to the current, existing, generated, or active dashboard, do not ask them to restate its specification or the mechanical workflow. Call get_active_dashboard and audit_active_dashboard, inspect the current semantic model when useful, decide the changes needed from the user's outcome and the audit, and call revise_active_dashboard with the full revised DashboardSpec and the current version as expected_version. Preserve unrelated content, explain the revision reason, never edit generated PBIR directly, and never overwrite history. Do NOT call open_active_dashboard_in_powerbi_desktop automatically after revising or modifying a report; only call open_active_dashboard_in_powerbi_desktop if the user explicitly asks to open or view the report in Power BI Desktop. Use list_dashboard_versions or rollback_dashboard when the user asks to compare or undo changes.

**Autonomous & Zero UX Friction Rule**: NEVER ask the user to manually save a project file or provide a semantic model path before viewing or opening a report. You operate fully autonomously. All report authoring and desktop preview tools automatically manage staging semantic models. When the user asks to open, preview, or view the report, call `open_active_dashboard_in_powerbi_desktop` directly without asking the user for any file path or file saving.

Guidelines:
- **Connection Rule**: Before executing any model operations (like listing tables, getting measures, executing DAX queries), you MUST verify that you are connected. If you get a "No connectionName provided" or "no last used connection available" error, you must first call `connection_operations` with `ListLocalInstances` to list all running local instances, and then call `connection_operations` with `Connect` specifying the connectionName or port of the active instance.
- Always validate DAX syntax before executing queries.
- **Reasoning Rule**: For all complex questions or operations, you MUST outline your internal thought process and steps inside <thinking>...</thinking> tags *before* presenting your final answer or executing tool calls. Keep the text inside the tags focused on your engineering plans and analysis.
- When modifying a model, explain what you are about to change and why.
- Present query results in clear, formatted tables when possible.
- If asked to visualize the schema, describe relationships, or show the model diagram, you can output a flowchart/diagram using Mermaid.js syntax inside a ```mermaid ... ``` code block. Represent tables as nodes and draw relationships between them showing keys/cardinality.
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
# MULTI-SESSION ORCHESTRATOR
# ==============================================================================
class MultiClientSession:
    """
    Orchestrates communication with multiple MCP servers concurrently.
    Exposes a unified interface that routes list_tools and call_tool actions.
    """
    def __init__(self, sessions: List[ClientSession]):
        self.sessions = sessions
        self.tool_to_session = {}

    async def list_tools(self) -> types.ListToolsResult:
        all_tools = []
        for session in self.sessions:
            try:
                res = await session.list_tools()
                for tool in res.tools:
                    all_tools.append(tool)
                    self.tool_to_session[tool.name] = session
            except Exception as e:
                logger.error(f"Error listing tools from session: {e}")
        return types.ListToolsResult(tools=all_tools)

    async def call_tool(self, name: str, arguments: dict):
        session = self.tool_to_session.get(name)
        if not session:
            # Refresh mappings in case tools were registered dynamically
            await self.list_tools()
            session = self.tool_to_session.get(name)
            if not session:
                raise ValueError(f"Tool '{name}' not found in any active MCP session.")
        return await session.call_tool(name, arguments)

# ==============================================================================
# DUAL-TRANSPORT MCP CLIENT SESSION
# ==============================================================================
@asynccontextmanager
async def mcp_session_scope(coordinator: ElicitationCoordinator) -> AsyncGenerator[MultiClientSession, None]:
    """
    Context manager to yield a MultiClientSession containing connections to both
    the active Power BI server (SSE or STDIO) and the custom helper tools server.
    """
    import os
    import shutil
    import sys
    elicitation_cb = create_elicitation_callback(coordinator)

    async with AsyncExitStack() as stack:
        sessions = []

        # 1. Initialize Power BI Client Session
        if config.transport_mode.upper() == "SSE":
            logger.info(f"Connecting to remote Power BI server via SSE: {config.sse_url}")
            headers = {}
            if config.fabric_access_token:
                headers["Authorization"] = f"Bearer {config.fabric_access_token}"

            read_stream, write_stream = await stack.enter_async_context(
                sse_client(url=config.sse_url, headers=headers)
            )
            pbi_session = await stack.enter_async_context(
                ClientSession(read_stream, write_stream, elicitation_callback=elicitation_cb)
            )
            await pbi_session.initialize()
            sessions.append(pbi_session)
        else:
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
            
            node_dir = r"C:\Program Files\nodejs"
            custom_env = os.environ.copy()
            custom_env["PATH"] = node_dir + os.pathsep + custom_env.get("PATH", "")

            logger.info(f"Connecting to local Power BI modeling server via STDIO. Executable: {stdio_cmd}")
            is_npx = "npx" in stdio_cmd.lower()
            use_fast_startup = is_npx and config.stdio_args and "@microsoft/powerbi-modeling-mcp" in config.stdio_args

            pbi_session = None
            if use_fast_startup:
                try:
                    logger.info("Attempting fast startup with --no-install...")
                    fast_args = ["--no-install"] + [arg for arg in config.stdio_args if arg != "-y"]
                    server_params = StdioServerParameters(
                        command=stdio_cmd,
                        args=fast_args,
                        env=custom_env
                    )
                    read_stream, write_stream = await stack.enter_async_context(
                        stdio_client(server_params)
                    )
                    pbi_session = await stack.enter_async_context(
                        ClientSession(read_stream, write_stream, elicitation_callback=elicitation_cb)
                    )
                    await pbi_session.initialize()
                    logger.info("Fast startup succeeded.")
                except Exception as e:
                    logger.warning(f"Fast startup failed: {e}. Falling back to standard startup...")

            if pbi_session is None:
                server_params = StdioServerParameters(
                    command=stdio_cmd,
                    args=config.stdio_args,
                    env=custom_env
                )
                read_stream, write_stream = await stack.enter_async_context(
                    stdio_client(server_params)
                )
                pbi_session = await stack.enter_async_context(
                    ClientSession(read_stream, write_stream, elicitation_callback=elicitation_cb)
                )
                await pbi_session.initialize()
            
            sessions.append(pbi_session)

        # 2. Initialize Custom Helper MCP Server Session
        custom_server_script = str(ROOT_DIR / "backend" / "custom_mcp_server.py")
        logger.info(f"Connecting to Custom MCP helper server via STDIO: {custom_server_script}")
        custom_env = os.environ.copy()
        
        custom_params = StdioServerParameters(
            command=sys.executable,
            args=[custom_server_script],
            env=custom_env
        )
        
        c_read, c_write = await stack.enter_async_context(
            stdio_client(custom_params)
        )
        custom_session = await stack.enter_async_context(
            ClientSession(c_read, c_write)
        )
        await custom_session.initialize()
        sessions.append(custom_session)

        # Yield the unified Multi-Session orchestrator wrapper
        multi_session = MultiClientSession(sessions)
        await multi_session.list_tools()  # Warm up the tool mapping cache
        
        try:
            yield multi_session
        except (GeneratorExit, asyncio.CancelledError):
            logger.info("Multi-Session context generator exited or cancelled.")
        except BaseExceptionGroup:
            logger.info("Handled exception group during Multi-Session cleanup.")
        except Exception as e:
            logger.error(f"Error inside multi-session execution: {e}")

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

def map_mcp_tools_to_gemini(mcp_tools: types.ListToolsResult) -> List[genai_types.Tool]:
    """Convert MCP schemas to native Google GenAI Tool structures."""
    function_declarations = []
    for tool in mcp_tools.tools:
        # Convert schema property types if needed or map them
        props = {}
        input_schema = tool.inputSchema or {}
        raw_properties = input_schema.get("properties", {})
        
        for k, v in raw_properties.items():
            t_type = v.get("type", "STRING").upper()
            if t_type not in ["STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT", "NULL"]:
                t_type = "STRING"
            
            # Map items if type is ARRAY
            items_schema = None
            if t_type == "ARRAY" and "items" in v:
                items_type = v["items"].get("type", "STRING").upper()
                if items_type not in ["STRING", "NUMBER", "INTEGER", "BOOLEAN", "ARRAY", "OBJECT", "NULL"]:
                    items_type = "STRING"
                items_schema = genai_types.Schema(type=items_type)
            
            props[k] = genai_types.Schema(
                type=t_type,
                description=v.get("description", ""),
                items=items_schema
            )
            
        fd = genai_types.FunctionDeclaration(
            name=tool.name,
            description=tool.description or "",
            parameters=genai_types.Schema(
                type="OBJECT",
                properties=props,
                required=input_schema.get("required", [])
            )
        )
        function_declarations.append(fd)
        
    return [genai_types.Tool(function_declarations=function_declarations)]

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
    history: list = None,
    llm_provider: str = None,
    llm_model: str = None,
    reasoning_effort: str = None
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

    # Initialize LLM Clients (using global http_client/http_options to bypass SSL verification issues)
    openai_client = openai.AsyncOpenAI(api_key=config.openai_api_key, http_client=http_client)
    anthropic_client = anthropic.AsyncAnthropic(api_key=config.anthropic_api_key, http_client=http_client)
    gemini_client = genai.Client(
        api_key=config.gemini_api_key,
        http_options=genai_types.HttpOptions(
            httpx_async_client=http_client
        )
    )

    # Dynamic Environment Discovery & Auto-Connection at Startup
    connection_context = ""
    if "connection_operations" in tool_names:
        try:
            logger.info("Checking active Power BI connections...")
            import json
            
            # 1. Check if there are active connections
            conn_res = await session.call_tool("connection_operations", {"request": {"operation": "ListConnections"}})
            conn_data = json.loads(conn_res.content[0].text)
            connections = conn_data.get("data") if isinstance(conn_data, dict) else conn_data
            
            active_conn = None
            if isinstance(connections, list) and len(connections) > 0:
                active_conn = connections[0]
                logger.info(f"Active connection already exists: {active_conn.get('connectionName')}")
            else:
                # 2. No active connection, discover local instances and auto-connect
                logger.info("No active connections. Discovering local instances...")
                list_res = await session.call_tool("connection_operations", {"request": {"operation": "ListLocalInstances"}})
                list_data = json.loads(list_res.content[0].text)
                inst_list = list_data.get("data") if isinstance(list_data, dict) else list_data
                
                if isinstance(inst_list, list) and len(inst_list) > 0:
                    first_inst = inst_list[0]
                    conn_str = first_inst.get("connectionString")
                    title = first_inst.get("parentWindowTitle") or "Power BI Desktop"
                    logger.info(f"Auto-connecting to '{title}'...")
                    
                    connect_res = await session.call_tool("connection_operations", {
                        "request": {
                            "operation": "Connect",
                            "connectionString": conn_str
                        }
                    })
                    logger.info(f"Auto-connect response: {connect_res.content[0].text}")
                    
                    # Verify active connection again
                    verify_res = await session.call_tool("connection_operations", {"request": {"operation": "ListConnections"}})
                    verify_data = json.loads(verify_res.content[0].text)
                    verify_connections = verify_data.get("data") if isinstance(verify_data, dict) else verify_data
                    if isinstance(verify_connections, list) and len(verify_connections) > 0:
                        active_conn = verify_connections[0]
            
            if active_conn:
                conn_name = active_conn.get("connectionName") or "Power BI Model"
                # 3. Discover tables in the model to inject into System Prompt
                tables_res = await session.call_tool("table_operations", {"request": {"operation": "LIST"}})
                tables_data = json.loads(tables_res.content[0].text)
                tables_list = tables_data.get("data") if isinstance(tables_data, dict) else tables_data
                
                table_names = []
                if isinstance(tables_list, list):
                    table_names = [t.get("name") for t in tables_list]
                
                # Discover measures
                measures_list = []
                if "measure_operations" in tool_names:
                    try:
                        measures_res = await session.call_tool("measure_operations", {"request": {"operation": "LIST"}})
                        measures_data = json.loads(measures_res.content[0].text)
                        m_list = measures_data.get("data") if isinstance(measures_data, dict) else measures_data
                        if isinstance(m_list, list):
                            measures_list = [f"{m.get('tableName')}[{m.get('name')}]" for m in m_list if m.get('tableName') and m.get('name')]
                    except Exception as me:
                        logger.warning(f"Failed to fetch measures: {me}")
                
                connection_context = (
                    f"\n\n[Active Connection Status: CONNECTED]\n"
                    f"- Connected Instance: '{conn_name}'\n"
                    f"- Tables in Semantic Model: {', '.join(table_names) if table_names else 'None (Empty Model)'}\n"
                )
                if measures_list:
                    connection_context += f"- Discovered Measures: {', '.join(measures_list[:35])}{' ... (and more)' if len(measures_list) > 35 else ''}\n"
                
                connection_context += (
                    f"Guidance: You are already connected to this semantic model. You do not need to ask the user to connect, "
                    f"nor do you need to call Connect or ListLocalInstances unless you encounter a disconnection. "
                    f"Start directly by acknowledging the connection to '{conn_name}' and discussing the model schema or answering the query."
                )
            else:
                connection_context = (
                    f"\n\n[Active Connection Status: DISCONNECTED]\n"
                    f"- No local Power BI Desktop instances were detected running.\n"
                    f"Guidance: Greet the user, explain that you are currently not connected to any model, and guide them to open "
                    f"Power BI Desktop locally or connect to a Fabric semantic model so we can begin."
                )
        except Exception as e:
            logger.error(f"Error during startup environmental discovery: {e}")
            connection_context = f"\n\n[Active Connection Status: ERROR]\n- Details: {e}"

    dynamic_system_prompt = SYSTEM_PROMPT + connection_context

    # 1. Initialize or retrieve conversation history
    if history is None:
        messages = []
    else:
        messages = history

    # 2. Append new user query to the history matching the provider format
    if llm_provider == "openai":
        # Find and update or insert system message at the beginning
        system_msg_idx = next((i for i, m in enumerate(messages) if m.get("role") == "system"), -1)
        if system_msg_idx != -1:
            messages[system_msg_idx] = {"role": "system", "content": dynamic_system_prompt}
        else:
            messages.insert(0, {"role": "system", "content": dynamic_system_prompt})
        
        messages.append({"role": "user", "content": query})
    elif llm_provider == "anthropic":
        messages.append({"role": "user", "content": query})
    else: # gemini
        messages.append(
            genai_types.Content(
                role="user",
                parts=[genai_types.Part.from_text(text=query)]
            )
        )

    # Loop to support multi-turn reasoning and tool calling
    while True:
        if llm_provider == "gemini":
            # Map tools to Gemini structure
            gemini_tools = map_mcp_tools_to_gemini(mcp_tools)

            logger.info("Calling Gemini models.generate_content_stream...")
            text_accumulator = []
            reasoning_accumulator = []
            
            # Reset tool call holders
            gemini_tool_calls = []

            # Gemini 3.6+ uses qualitative thinking levels; token budgets are deprecated.
            thinking_config = None
            if reasoning_effort != "off":
                thinking_levels = {
                    "low": genai_types.ThinkingLevel.LOW,
                    "medium": genai_types.ThinkingLevel.MEDIUM,
                    "high": genai_types.ThinkingLevel.HIGH,
                }
                thinking_config = genai_types.ThinkingConfig(
                    include_thoughts=True,
                    thinking_level=thinking_levels.get(
                        reasoning_effort, genai_types.ThinkingLevel.MEDIUM
                    ),
                )

            # We pass dynamic_system_prompt in GenerateContentConfig system_instruction
            response_stream = await gemini_client.aio.models.generate_content_stream(
                model=llm_model,
                contents=messages,
                config=genai_types.GenerateContentConfig(
                    system_instruction=dynamic_system_prompt,
                    tools=gemini_tools if gemini_tools else None,
                    thinking_config=thinking_config
                )
            )

            async for chunk in response_stream:
                if chunk.candidates and chunk.candidates[0].content:
                    for part in chunk.candidates[0].content.parts:
                        if getattr(part, "thought", False):
                            reasoning_accumulator.append(part.text)
                            yield {"type": "reasoning_token", "text": part.text}
                        elif part.text:
                            text_accumulator.append(part.text)
                            yield {"type": "token", "text": part.text}
                            
                        if part.function_call:
                            gemini_tool_calls.append(part)

            # Process any tool calls accumulated
            if gemini_tool_calls:
                formatted_tool_calls_payload = []
                for pt in gemini_tool_calls:
                    fc = pt.function_call
                    fc_id = getattr(fc, "id", str(uuid.uuid4()))
                    formatted_tool_calls_payload.append({
                        "id": fc_id,
                        "name": fc.name,
                        "arguments": fc.args
                    })

                # Append assistant content containing tool call parts (including thought_signature!)
                # The GenAI SDK Content object contains the exact parts list returned by the model
                messages.append(
                    genai_types.Content(
                        role="model",
                        parts=gemini_tool_calls
                    )
                )

                # Alert client of tool starts
                yield {"type": "tool_start", "calls": formatted_tool_calls_payload}

                # Execute tool calls
                tool_response_parts = []
                for pt, payload in zip(gemini_tool_calls, formatted_tool_calls_payload):
                    fc = pt.function_call
                    tool_name = fc.name
                    tool_args = fc.args
                    tc_id = payload["id"]

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
                        tool_response_parts.append(
                            genai_types.Part.from_function_response(
                                name=tool_name,
                                response={"result": content_str}
                            )
                        )
                    except Exception as e:
                        logger.error(f"Error executing tool {tool_name}: {e}")
                        yield {"type": "tool_result", "id": tc_id, "name": tool_name, "error": str(e)}
                        tool_response_parts.append(
                            genai_types.Part.from_function_response(
                                name=tool_name,
                                response={"error": str(e)}
                            )
                        )
                
                # Append tool responses to context
                messages.append(
                    genai_types.Content(
                        role="user",
                        parts=tool_response_parts
                    )
                )
                # Re-loop to feed tool results back to Gemini
                continue
            else:
                # Append assistant final message
                final_parts = []
                if text_accumulator:
                    final_parts.append(genai_types.Part.from_text(text="".join(text_accumulator)))
                
                messages.append(
                    genai_types.Content(
                        role="model",
                        parts=final_parts
                    )
                )
                # Execution complete
                break

        elif llm_provider == "openai":
            # Map tools
            openai_tools = map_mcp_tools_to_openai(mcp_tools)

            # Call OpenAI (Streaming)
            logger.info("Calling OpenAI Chat Completion...")
            tool_calls_accumulator = {}
            text_accumulator = []

            reasoning_accumulator = []

            stream = await openai_client.chat.completions.create(
                model=llm_model,
                messages=messages,
                tools=openai_tools if openai_tools else None,
                stream=True
            )

            async for chunk in stream:
                delta = chunk.choices[0].delta
                if hasattr(delta, "reasoning_content") and delta.reasoning_content:
                    reasoning_accumulator.append(delta.reasoning_content)
                    yield {"type": "reasoning_token", "text": delta.reasoning_content}
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
                    "reasoning_content": "".join(reasoning_accumulator) or None,
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
                # Append assistant message with text to context
                messages.append({
                    "role": "assistant",
                    "content": "".join(text_accumulator) or None,
                    "reasoning_content": "".join(reasoning_accumulator) or None
                })
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
                system=dynamic_system_prompt,
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
