# Power BI MCP Autonomous Agent

An enterprise-ready, dual-service autonomous AI agent dashboard designed to interface with Microsoft's Power BI Model Context Protocol (MCP) servers (both remote SSE querying and local STDIO modeling).

This project features a **FastAPI Python Backend** serving as the core agent/MCP client, and a **Next.js React Frontend** styled with premium dark mode and glassmorphism. It incorporates the MCP elicitation protocol to intercept sensitive write requests and prompt for human approval (y/n) via interactive modals before changes are applied to your semantic models.

---

## Features
- **Dual-Transport Routing**: Configurable to connect to either the local modeling MCP server (`@microsoft/powerbi-modeling-mcp` via STDIO) or the remote querying server (`api.fabric.microsoft.com` via SSE).
- **Human-in-the-Loop Guardrails**: Bidirectional WebSocket connection intercepts `elicitation/create` prompts (for confirmations or authentication URLs) and displays them as interactive modal forms, pausing agent execution until accepted/declined.
- **Dynamic Tool Mapping**: Dynamically queries and maps schemas from `list_tools()` into the native structure expected by OpenAI (`gpt-4o`) and Anthropic (`claude-3-5-sonnet-latest`).
- **Real-Time Streaming**: Streams LLM token generation, active tool execution states, and raw tool output logs directly to the user dashboard.

---

## Directory Structure
```
Data-Analysis-Agent/
│
├── backend/
│   ├── agent.py       # Core MCP client connection and LLM orchestration loop
│   └── main.py        # FastAPI server & bidirectional WebSocket endpoint
│
├── frontend/
│   ├── src/app/
│   │   ├── page.tsx   # React SPA console: chat, tool logs, approval modals
│   │   └── globals.css# Glassmorphism & premium dark styling parameters
│   └── package.json   # Frontend Next.js / TypeScript / Tailwind config
│
├── docs/
│   └── architecture.md# Deep dive into the agent execution and safety callbacks
│
└── README.md
```

---

## Quick Start

### 1. Prerequisites
Install Node.js (version 18+) on your system. If on Windows, you can run:
```powershell
winget install OpenJS.NodeJS
# Restart your terminal/IDE after installation.
```

### 2. Configure Environment
Set up your environment variables:
```bash
# LLM Provider Configuration (OpenAI or Anthropic)
export OPENAI_API_KEY="sk-proj-yourOpenAiKey"

# Connection Transport Configuration
export POWERBI_TRANSPORT_MODE="STDIO" # "STDIO" (Local Desktop) or "SSE" (Fabric Remote)
```

### 3. Launch Backend (Python)
1. Install backend requirements:
   ```bash
   pip install fastapi uvicorn websockets openai anthropic mcp
   ```
2. Start the FastAPI server (runs on `localhost:8000`):
   ```bash
   python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
   ```

### 4. Launch Frontend (Next.js)
1. Navigate to the `frontend/` directory and install dependencies:
   ```bash
   cd frontend
   npm install
   ```
2. Run the development server (runs on `localhost:3000`):
   ```bash
   npm run dev
   ```
3. Open [http://localhost:3000](http://localhost:3000) in your browser.

---

## Further Reading
For a detailed breakdown of the internal messaging pipeline, dynamic tool mapping, and WebSocket safety coordination, see the [Architecture Guide](docs/architecture.md).
