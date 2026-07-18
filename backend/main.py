import json
import logging
import asyncio
import os
from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel


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
    logger.info("=== Power BI MCP Agent — Starting Up ===")
    logger.info(f"  LLM Provider   : {config.llm_provider}")
    logger.info(f"  LLM Model      : {config.llm_model}")
    logger.info(f"  Transport Mode : {config.transport_mode}")
    if config.transport_mode.upper() == "SSE":
        logger.info(f"  SSE URL        : {config.sse_url}")
    else:
        logger.info(f"  STDIO Command  : {config.stdio_command}")
    logger.info("========================================")

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
    }

@app.get("/api/config")
async def get_config():
    """Return safe (non-secret) configuration details."""
    return {
        "llm_provider": config.llm_provider,
        "llm_model": config.llm_model,
        "transport_mode": config.transport_mode,
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
        "sse_url": config.sse_url if config.transport_mode.upper() == "SSE" else None,
    }


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

    try:
        await websocket.send_json({"type": "status", "status": "starting_agent"})

        # Establish and maintain the warm MCP connection scope for the entire socket lifecycle
        async with mcp_session_scope(coordinator) as session:
            # Discover tools and notify the client immediately on load
            mcp_tools = await session.list_tools()
            tool_names = [t.name for t in mcp_tools.tools]
            await websocket.send_json({"type": "tools_discovered", "tools": tool_names, "count": len(tool_names)})
            await websocket.send_json({"type": "status", "status": "mcp_connected"})

            # Maintain conversation history for the entire WebSocket lifecycle
            conversation_history = []

            async def execute_agent(query_text: str, reasoning_effort: str = None):
                try:
                    await websocket.send_json({"type": "status", "status": "running"})
                    # Run the LLM/Agent tool loop
                    async for event in run_agent_loop(
                        query_text,
                        session,
                        history=conversation_history,
                        reasoning_effort=reasoning_effort
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
                    # Cancel existing run if it's currently active
                    if agent_task and not agent_task.done():
                        logger.info("Aborting active agent run to start new query.")
                        agent_task.cancel()
                        # Short wait to let task clean up
                        await asyncio.sleep(0.1)

                    # Spawn new asynchronous agent run task
                    agent_task = asyncio.create_task(execute_agent(query_text, reasoning_effort=reasoning_effort))

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
