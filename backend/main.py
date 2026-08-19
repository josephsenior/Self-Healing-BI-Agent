import json
import logging
import asyncio
import os
import uuid
from pathlib import Path
from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from backend.infrastructure.redis_state import AgentStateRuntime


from backend.agent import (
    ElicitationCoordinator,
    mcp_session_scope,
    run_agent_loop,
    config,
)

logger = logging.getLogger("mcp_server")
logging.basicConfig(level=logging.INFO)

app = FastAPI(title="Power BI MCP Agent Backend")

# Ensure the static files directory exists and mount it
ROOT_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
static_dir = os.path.join(ROOT_DIR, "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")

# Enable CORS for the frontend dev server
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, restrict this to the frontend URL
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ==============================================================================
# STARTUP EVENT
# ==============================================================================
@app.on_event("startup")
async def log_startup_config():
    """Log the active configuration at startup (secrets are masked)."""
    logger.info("=== Power BI MCP Agent â€” Starting Up ===")
    logger.info(f"  LLM Provider   : {config.llm_provider}")
    logger.info(f"  LLM Model      : {config.llm_model}")
    logger.info(f"  Transport Mode : {config.transport_mode}")
    if config.transport_mode.upper() == "SSE":
        logger.info(f"  SSE URL        : {config.sse_url}")
    else:
        logger.info(f"  STDIO Command  : {config.stdio_command}")
    logger.info("========================================")
    state_runtime = AgentStateRuntime(
        config.redis_url,
        required=config.redis_required,
        checkpoint_ttl_minutes=config.redis_checkpoint_ttl_minutes,
    )
    await state_runtime.start()
    app.state.agent_state_runtime = state_runtime
    logger.info("  State Backend  : %s", state_runtime.backend)

# ==============================================================================
# REST ENDPOINTS
# ==============================================================================
@app.get("/api/health")
async def health_check():
    """Simple API check for frontend routing tests."""
    return {
        "status": "healthy",
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "transport_mode": config.transport_mode,
        "state": app.state.agent_state_runtime.health(),
    }

# Rendered report artifacts are written below these git-ignored roots. Serving
# them keeps dashboard previews visible in the browser without exposing the
# rest of the repository.
_ARTIFACT_ROOTS = (".pbir-previews", ".dashboard-workspaces")


@app.get("/api/preview")
async def preview_image(path: str):
    """Serve a rendered dashboard/report image from the artifact roots."""
    root = Path(ROOT_DIR).resolve()
    target = (root / path).resolve()
    try:
        target.relative_to(root)
    except ValueError:
        return JSONResponse({"error": "path must be inside the repository"}, status_code=400)
    if not any(
        (root / artifact_root) in target.parents for artifact_root in _ARTIFACT_ROOTS
    ):
        return JSONResponse(
            {"error": "path is not an allowed artifact location"}, status_code=400
        )
    if not target.is_file():
        return JSONResponse({"error": "artifact not found"}, status_code=404)
    return FileResponse(target)

@app.on_event("shutdown")
async def close_application_resources():
    """Close application-scoped pools explicitly."""
    runtime = getattr(app.state, "agent_state_runtime", None)
    if runtime is not None:
        await runtime.close()

@app.get("/api/config")
async def get_config():
    """Return safe (non-secret) configuration details."""
    return {
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "transport_mode": config.transport_mode,
        "state": app.state.agent_state_runtime.health(),
        "sse_url": config.sse_url if config.transport_mode.upper() == "SSE" else None,
    }

class ConfigUpdateRequest(BaseModel):
    llm_provider: str
    llm_model: str
    transport_mode: str
    sse_url: str | None = None

@app.post("/api/config")
async def update_config(req: ConfigUpdateRequest):
    """Update active configuration details in-memory."""
    config.llm_provider = req.llm_provider.lower()
    config.llm_model = req.llm_model
    config.transport_mode = req.transport_mode.upper()
    if req.sse_url is not None:
        config.sse_url = req.sse_url
    
    logger.info("=== Config Updated dynamically ===")
    logger.info(f"  LLM Provider   : {config.llm_provider}")
    logger.info(f"  LLM Model      : {config.llm_model}")
    logger.info(f"  Transport Mode : {config.transport_mode}")
    logger.info("==================================")
    
    return {
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "transport_mode": config.transport_mode,
        "state": app.state.agent_state_runtime.health(),
        "sse_url": config.sse_url if config.transport_mode.upper() == "SSE" else None,
    }


# ==============================================================================
# DASHBOARD MANAGEMENT REST ENDPOINTS
# ==============================================================================

@app.get("/api/dashboard/active")
async def get_active_dashboard(dashboard_id: str = ""):
    """Get the active dashboard spec and version metadata."""
    from backend.custom_mcp_server import _dashboard_manager
    return json.loads(_dashboard_manager().get(dashboard_id or None, indent=2))

@app.get("/api/dashboard/versions")
async def list_dashboard_versions(dashboard_id: str = ""):
    """List all versions for a dashboard."""
    from backend.custom_mcp_server import _dashboard_manager
    return json.loads(_dashboard_manager().list_versions(dashboard_id or None))

@app.post("/api/dashboard/rollback")
async def rollback_dashboard(dashboard_id: str = "", target_version: int = 0, catalog: dict | None = None):
    """Rollback dashboard to a previous version."""
    from backend.custom_mcp_server import _dashboard_manager, _qa_workspace_response
    from backend.report_authoring.semantic import SemanticModelCatalog
    
    def op():
        return _dashboard_manager().rollback(
            target_version,
            dashboard_id or None,
            SemanticModelCatalog.model_validate(catalog) if catalog else None,
        )
    return json.loads(_qa_workspace_response(op))

@app.post("/api/dashboard/audit")
async def audit_dashboard(dashboard_id: str = "", catalog: dict | None = None):
    """Audit the active dashboard."""
    from backend.custom_mcp_server import _dashboard_manager
    from backend.report_authoring.semantic import SemanticModelCatalog
    
    result = _dashboard_manager().audit(
        dashboard_id or None,
        SemanticModelCatalog.model_validate(catalog) if catalog else None,
    )
    return result

@app.get("/api/dashboard/cloud-readiness")
async def check_cloud_readiness():
    """Check cloud publishing and visual QA readiness."""
    import os
    from backend.report_authoring.cloud import CloudConfig
    
    vision_provider = os.getenv("POWERBI_VISION_PROVIDER", os.getenv("LLM_PROVIDER", "gemini")).lower()
    vision_key_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }.get(vision_provider, "")
    has_client_credentials = all(os.getenv(name) for name in (
        "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"
    ))
    checks = {
        "workspace_id": bool(os.getenv("POWERBI_STAGING_WORKSPACE_ID")),
        "fabric_auth": bool(os.getenv("FABRIC_API_ACCESS_TOKEN")) or has_client_credentials,
        "powerbi_auth": bool(os.getenv("POWERBI_API_ACCESS_TOKEN")) or has_client_credentials,
        "vision_provider": vision_provider,
        "vision_model": bool(os.getenv("POWERBI_VISION_MODEL") or os.getenv("LLM_MODEL")),
        "vision_api_key": bool(vision_key_name and os.getenv(vision_key_name)),
    }
    license_mode = os.getenv("POWERBI_CLOUD_LICENSE_MODE", "capacity").strip().lower()
    rendering_supported = CloudConfig(
        workspace_id=os.getenv("POWERBI_STAGING_WORKSPACE_ID", "") or "not-configured",
        license_mode=license_mode,
    ).supports_export_to_file
    publishing_required = ["workspace_id", "fabric_auth"]
    rendering_required = ["workspace_id", "powerbi_auth", "vision_model", "vision_api_key"]
    publishing_ready = all(bool(checks[item]) for item in publishing_required)
    visual_qa_ready = rendering_supported and all(
        bool(checks[item]) for item in rendering_required
    )
    return {
        "ready": publishing_ready,
        "publishing_ready": publishing_ready,
        "visual_qa_ready": visual_qa_ready,
        "license_mode": license_mode,
        "rendering_supported": rendering_supported,
        "limitations": ([] if rendering_supported else [
            "Power BI Pro/PPU supports cloud report publication, but not the "
            "ExportToFile API used for PNG rendering and automated visual QA."
        ]),
        "checks": checks,
    }

@app.post("/api/dashboard/publish")
async def publish_dashboard(project_path: str, display_name: str, semantic_model_id: str = "", report_id: str = ""):
    """Publish PBIR to Fabric workspace."""
    from backend.custom_mcp_server import _allowed_authoring_path
    from backend.report_authoring.cloud import CloudConfig, FabricReportPublisher
    
    result = FabricReportPublisher(CloudConfig.from_env()).publish(
        _allowed_authoring_path(project_path),
        display_name=display_name,
        semantic_model_id=semantic_model_id or None,
        report_id=report_id or None,
    )
    return result.to_dict()

@app.post("/api/dashboard/render")
async def render_dashboard(report_id: str, page_names: list[str] | None = None, locale: str = "en-US"):
    """Render report pages as PNG."""
    from backend.custom_mcp_server import _allowed_authoring_path
    from backend.report_authoring.cloud import CloudConfig, PowerBIExportRenderer
    import uuid
    
    output = Path(ROOT_DIR) / ".pbir-previews" / report_id / uuid.uuid4().hex
    result = PowerBIExportRenderer(CloudConfig.from_env()).render_report(
        report_id,
        output,
        page_names=page_names or None,
        locale=locale,
    )
    return result.to_dict()

@app.post("/api/dashboard/review")
async def review_render(artifact_paths: list[str], project_path: str, provider: str = "", model: str = ""):
    """Review rendered Power BI screenshots."""
    from backend.custom_mcp_server import _allowed_authoring_path
    from backend.report_authoring.preview import build_preview_manifest
    from backend.report_authoring.visual_review import review_rendered_report
    
    images = [_allowed_authoring_path(value) for value in artifact_paths]
    manifest = build_preview_manifest(_allowed_authoring_path(project_path))
    review = review_rendered_report(
        images,
        manifest,
        provider=provider or None,
        model=model or None,
    )
    return review.to_dict()

@app.post("/api/dashboard/decide-qa")
async def decide_qa(review: dict, attempt: int, max_attempts: int = 3):
    """Decide visual QA iteration."""
    from backend.report_authoring.visual_review import VisualReview, decide_visual_qa_iteration
    
    decision = decide_visual_qa_iteration(
        VisualReview.model_validate(review), attempt, max_attempts
    )
    return decision.model_dump()

@app.post("/api/dashboard/open-desktop")
async def open_desktop(dashboard_id: str = "", semantic_model_path: str = ""):
    """Open dashboard in Power BI Desktop."""
    from backend.custom_mcp_server import _dashboard_manager
    
    result = _dashboard_manager().open_active_in_desktop(
        dashboard_id or None, semantic_model_path or None
    )
    return result

@app.get("/api/semantic-models")
async def list_semantic_models():
    """List semantic models in cloud workspace."""
    from backend.report_authoring.cloud import CloudConfig, PowerBICloudClient
    
    models = PowerBICloudClient(CloudConfig.from_env()).list_semantic_models()
    return {"semantic_models": models}

@app.get("/api/semantic-models/{semantic_model_id}/catalog")
async def get_semantic_catalog(semantic_model_id: str):
    """Get semantic catalog for a model."""
    from backend.report_authoring.cloud import CloudConfig, PowerBICloudClient
    
    catalog = PowerBICloudClient(CloudConfig.from_env()).semantic_catalog(semantic_model_id)
    return catalog.model_dump()

@app.post("/api/semantic-models/{semantic_model_id}/dax")
async def execute_dax(semantic_model_id: str, query: str, include_nulls: bool = True):
    """Execute DAX query against cloud model."""
    from backend.report_authoring.cloud import CloudConfig, PowerBICloudClient
    
    result = PowerBICloudClient(CloudConfig.from_env()).execute_dax(
        semantic_model_id, query, include_nulls=include_nulls
    )
    return result

@app.post("/api/qualification/run")
async def run_qualification(max_visual_attempts: int = 3):
    """Run full autonomous agent qualification."""
    from backend.report_authoring.qualification import run_full_agent_qualification
    
    return run_full_agent_qualification(max_visual_attempts)

@app.get("/api/visual-capabilities")
async def get_visual_capabilities():
    """Get supported Power BI visual capabilities."""
    from backend.report_authoring.visual_capabilities import list_visual_capabilities
    return {"visuals": list_visual_capabilities()}

# ==============================================================================
# WEBSOCKET CHAT ENDPOINT
# ==============================================================================
@app.websocket("/ws/chat")
async def websocket_chat(websocket: WebSocket):
    """
    Bidirectional WebSocket chat endpoint supporting streamed LLM outputs,
    persistent warm MCP session runtime, and human-in-the-loop safety approvals.
    """
    await websocket.accept()
    logger.info("WebSocket connection established.")

    coordinator = ElicitationCoordinator()

    async def send_payload(payload: dict):
        try:
            await websocket.send_json(payload)
        except Exception as e:
            logger.error(f"Failed to send JSON over websocket: {e}")

    # Connect coordinator to this websocket connection
    coordinator.set_send_callback(send_payload)

    agent_task = None
    default_thread_id = str(uuid.uuid4())
    state_runtime: AgentStateRuntime = websocket.app.state.agent_state_runtime

    try:
        await websocket.send_json({"type": "status", "status": "starting_agent"})

        # Establish and maintain the warm MCP connection scope for the entire socket lifecycle
        async with mcp_session_scope(coordinator) as session:
            # Discover tools and notify the client immediately on load
            mcp_tools = await session.list_tools()
            tool_names = [t.name for t in mcp_tools.tools]
            await websocket.send_json({"type": "tools_discovered", "tools": tool_names, "count": len(tool_names)})
            await websocket.send_json({"type": "status", "status": "mcp_connected"})

            await websocket.send_json({"type": "thread_ready", "threadId": default_thread_id})

            async def execute_agent(query_text: str, thread_id: str, reasoning_effort: str = None):
                try:
                    await websocket.send_json({"type": "status", "status": "running"})
                    run_id = str(uuid.uuid4())
                    async with state_runtime.run_lock(thread_id):
                        async for event in run_agent_loop(
                            query_text,
                            session,
                            reasoning_effort=reasoning_effort,
                            thread_id=thread_id,
                            run_id=run_id,
                            checkpointer=state_runtime.checkpointer,
                        ):
                            await websocket.send_json(event)
                    await websocket.send_json({"type": "complete"})
                except asyncio.CancelledError:
                    logger.info("Agent task was cancelled by client.")
                    await websocket.send_json({"type": "status", "status": "cancelled"})
                except Exception as e:
                    logger.error(f"Error in agent tool loop: {e}")
                    await websocket.send_json({"type": "error", "message": str(e)})

            while True:
                # Await raw text message from WebSocket client
                data = await websocket.receive_text()
                try:
                    message = json.loads(data)
                except json.JSONDecodeError:
                    await websocket.send_json({"type": "error", "message": "Invalid JSON payload"})
                    continue

                msg_type = message.get("type")
                logger.info(f"Received message of type: {msg_type}")

                if msg_type == "query":
                    query_text = message.get("text")
                    reasoning_effort = message.get("reasoningEffort")
                    thread_id = str(message.get("threadId") or default_thread_id)
                    if not query_text or len(thread_id) > 128:
                        await websocket.send_json({"type": "error", "message": "Invalid query or threadId"})
                        continue
                    # Cancel existing run if it's currently active
                    if agent_task and not agent_task.done():
                        logger.info("Aborting active agent run to start new query.")
                        agent_task.cancel()
                        # Short wait to let task clean up
                        await asyncio.sleep(0.1)

                    # Spawn new asynchronous agent run task
                    agent_task = asyncio.create_task(execute_agent(query_text, thread_id, reasoning_effort=reasoning_effort))

                elif msg_type == "elicitation_response":
                    elicit_id = message.get("id")
                    action = message.get("action")   # 'accept', 'decline', 'cancel'
                    content = message.get("content")  # form payload dictionary or empty dict

                    logger.info(f"Submitting elicitation response. ID: {elicit_id}, Action: {action}")
                    coordinator.submit_response(elicit_id, action, content)

                elif msg_type == "abort":
                    if agent_task and not agent_task.done():
                        logger.info("Client requested execution abort.")
                        agent_task.cancel()
                    else:
                        await websocket.send_json({"type": "status", "status": "idle"})

    except WebSocketDisconnect:
        logger.info("WebSocket client disconnected.")
    except Exception as e:
        logger.error(f"Error in WebSocket lifecycle: {e}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except Exception:
            pass
    finally:
        # Guarantee cleanup of running subprocesses or sessions upon socket close
        if agent_task and not agent_task.done():
            agent_task.cancel()
            logger.info("WebSocket closed. Cleaned up active agent task.")
