import uuid
import logging
import asyncio
from typing import Dict, Any, List, Literal, Union, AsyncGenerator
from contextlib import asynccontextmanager, AsyncExitStack


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
    llm_model: str = Field(default="gemini-3.6-flash", alias="LLM_MODEL")
    openai_api_key: str = Field(default="", alias="OPENAI_API_KEY")
    anthropic_api_key: str = Field(default="", alias="ANTHROPIC_API_KEY")
    gemini_api_key: str = Field(default="", alias="GEMINI_API_KEY")
    redis_url: str = Field(default="redis://127.0.0.1:6379/0", alias="REDIS_URL")
    redis_required: bool = Field(default=False, alias="REDIS_REQUIRED")
    redis_checkpoint_ttl_minutes: int = Field(default=1440, alias="REDIS_CHECKPOINT_TTL_MINUTES", ge=1)
    agent_max_context_messages: int = Field(default=80, alias="AGENT_MAX_CONTEXT_MESSAGES", ge=4, le=1000)
    agent_max_tool_result_chars: int = Field(default=50000, alias="AGENT_MAX_TOOL_RESULT_CHARS", ge=1000, le=1000000)
    agent_tool_timeout_seconds: float = Field(default=120, alias="AGENT_TOOL_TIMEOUT_SECONDS", ge=5, le=1800)

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

**Report Authoring Rule**: When asked to create a dashboard, first clarify internally whether the user means a PBIR report page or a Power BI Service dashboard. For report authoring, inspect the semantic model and construct a SemanticModelCatalog from the live metadata. Submit the strict DashboardSpec through create_dashboard_workspace; creation, revision, and rollback automatically run the runtime QA admission controller. If a workspace tool returns `accepted: false` with `NEEDS_REVISION`, correct the blocking findings and retry with the complete spec. If it returns `NEEDS_REVIEW`, stop automatic retries and explain the remaining evidence. Only describe a version as verified when the tool returns `accepted: true` with `VERIFIED` or `VERIFIED_WITH_WARNINGS`. If and only if the user explicitly requests to open or preview the report locally in Power BI Desktop, call open_active_dashboard_in_powerbi_desktop. Before cloud publication, call check_powerbi_cloud_qa_readiness. When publishing_ready is true and the user authorizes publication, call publish_pbir_to_fabric. Continue with render_powerbi_report, review_powerbi_render, and decide_powerbi_visual_qa_iteration only when visual_qa_ready is true. In Power BI Pro/PPU mode, stop after successful publication and clearly state that the report was not visually inspected because ExportToFile requires a capacity-backed workspace. Never generate PBIR with run_python_sandbox and never claim a report was deployed or visually approved unless the corresponding tool result confirms it.

**Visual Selection Rule**: Before constructing or revising a DashboardSpec, call list_powerbi_visual_capabilities and use a listed visual type with its documented field roles and configuration. Prefer the generic `fields` map for new visuals; `category`, `values`, and `series` exist for compatibility with older specs. An unlisted custom visual is allowed only when the spec includes an inline `custom_visual` adapter that declares its exact data roles and confirms the visual is trusted and already installed. Never download or install a custom visual while authoring a report.

**BigQuery Source Rule**: Treat BigQuery as read-only and fail closed. Use bigquery_list_tables, bigquery_get_table_schema, bigquery_query, and bigquery_semantic_catalog only for configured allowlisted datasets. For a dashboard, call bigquery_create_powerbi_semantic_model with storage_mode exactly `import` or `directQuery`. In DashboardSpec use the returned `dataset_reference_path` as `dataset.path`; never put the absolute semantic_model_path inside DashboardSpec. Pass the returned absolute `semantic_model_path` only through the separate create_dashboard_workspace argument, and pass the exact returned catalog. The current BigQuery catalog is authoritative: preserve its exact table/column casing, never reuse fields from an earlier dashboard or Power BI connection, and never invent columns or measures absent from it. Run semantic validation with that same catalog before creating the workspace. Use open_active_dashboard_in_powerbi_desktop only when the user asks to open or preview it. Never embed or repeat Google credential material in a model, report, tool argument, or response.

**Stateful Dashboard Revision Rule**: When the user refers to the current, existing, generated, or active dashboard, do not ask them to restate its specification or the mechanical workflow. Call get_active_dashboard and audit_active_dashboard, inspect the current semantic model when useful, decide the changes needed from the user's outcome and the audit, and call revise_active_dashboard with the full revised DashboardSpec and the current version as expected_version. Preserve unrelated content, explain the revision reason, never edit generated PBIR directly, and never overwrite history. Do NOT call open_active_dashboard_in_powerbi_desktop automatically after revising or modifying a report; only call open_active_dashboard_in_powerbi_desktop if the user explicitly asks to open or view the report in Power BI Desktop. Use list_dashboard_versions or rollback_dashboard when the user asks to compare or undo changes.

**Power BI Pro Cloud Rule**: In Pro cloud mode, use list_powerbi_cloud_semantic_models, get_powerbi_cloud_semantic_catalog, and execute_powerbi_cloud_dax for capacity-independent discovery and analysis. These direct REST tools are preferred over the preview remote MCP server. Use the returned semantic catalog to ground DAX and report authoring. Service-principal queries do not support semantic models with RLS or SSO; report that limitation instead of bypassing it.

**Autonomous & Zero UX Friction Rule**: NEVER ask the user to manually save a project file or provide a semantic model path before viewing or opening a report. You operate fully autonomously. All report authoring and desktop preview tools automatically manage staging semantic models. When the user asks to open, preview, or view the report, call `open_active_dashboard_in_powerbi_desktop` directly without asking the user for any file path or file saving.

Guidelines:
- **Connection Rule**: Before executing any model operations (like listing tables, getting measures, executing DAX queries), you MUST verify that you are connected. If you get a "No connectionName provided" or "no last used connection available" error, you must first call `connection_operations` with `ListLocalInstances` to list all running local instances, and then call `connection_operations` with `Connect` specifying the connectionName or port of the active instance.
- Always validate DAX syntax before executing queries.
- For complex operations, provide a concise execution plan and observable evidence. Never expose private chain-of-thought.
- When modifying a model, explain what you are about to change and why.
- Present query results in clear, formatted tables when possible.
- If asked to visualize the schema, describe relationships, or show the model diagram, you can output a flowchart/diagram using Mermaid.js syntax inside a ```mermaid ... ``` code block. Represent tables as nodes and draw relationships between them showing keys/cardinality.
- If a tool call fails, diagnose the error and suggest a fix.
- Before calling a tool, reuse exact enum values and identifiers from its schema or prior tool result. Do not guess casing, paths, slugs, table names, or field names.
- A failed validation is not progress: correct its reported inputs before moving to creation. Do not validate against one catalog and create against another.
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

class InProcessMCPServerAdapter:
    """Call monolith-owned FastMCP tools directly without a client lifecycle.

    Creating one in-memory FastMCP Client per WebSocket caused overlapping
    clients to contend on the same server object before the Python tool body
    was entered. Direct server dispatch preserves FastMCP validation and thread
    execution while removing that shared transport lifecycle.
    """

    def __init__(self, server: Any):
        self.server = server

    async def list_tools(self) -> types.ListToolsResult:
        registered = await self.server.list_tools()
        return types.ListToolsResult(tools=[tool.to_mcp_tool() for tool in registered])

    async def call_tool(self, name: str, arguments: dict):
        return await self.server.call_tool(name, arguments)

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

        # 2. Mount local helper tools in-process. They are part of this modular
        # monolith and do not need a fragile subprocess/STDIO boundary.
        from backend.custom_mcp_server import mcp as custom_mcp

        logger.info("Mounting custom MCP helper tools through direct in-process dispatch.")
        sessions.append(InProcessMCPServerAdapter(custom_mcp))

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
# LANGGRAPH EXECUTION FACADE
# ==============================================================================
async def run_agent_loop(
    query: str,
    session: ClientSession,
    history: list | None = None,
    llm_provider: str | None = None,
    llm_model: str | None = None,
    reasoning_effort: str | None = None,
    thread_id: str | None = None,
    run_id: str | None = None,
    checkpointer: Any = None,
) -> AsyncGenerator[Dict[str, Any], None]:
    """Compatibility facade; LangGraph now owns the bounded tool workflow."""
    from langgraph.checkpoint.memory import InMemorySaver

    from backend.application.graph_agent import stream_agent_graph
    from backend.infrastructure.models import create_chat_model

    del history  # Conversation state is now checkpointed by thread_id.
    selected_provider = llm_provider or config.llm_provider
    selected_model = llm_model or config.llm_model
    model = create_chat_model(
        provider=selected_provider,
        model=selected_model,
        openai_api_key=config.openai_api_key,
        anthropic_api_key=config.anthropic_api_key,
        gemini_api_key=config.gemini_api_key,
        reasoning_effort=reasoning_effort,
    )

    async for event in stream_agent_graph(
        query=query,
        thread_id=thread_id or str(uuid.uuid4()),
        run_id=run_id or str(uuid.uuid4()),
        model=model,
        session=session,
        system_prompt=SYSTEM_PROMPT,
        checkpointer=checkpointer or InMemorySaver(),
        max_context_messages=config.agent_max_context_messages,
        max_tool_result_chars=config.agent_max_tool_result_chars,
        tool_timeout_seconds=config.agent_tool_timeout_seconds,
    ):
        yield event
