# Power BI MCP Agent

An autonomous AI agent that interfaces with Microsoft's Power BI [Model Context Protocol](https://modelcontextprotocol.io/) servers — both the **remote Fabric SSE** endpoint for querying and the **local STDIO** server for semantic model editing.

Built as a dual-service stack: a **Python/FastAPI backend** handles MCP client sessions and LLM orchestration, while a **Next.js/React frontend** provides a real-time streaming console with human-in-the-loop safety approvals.

---

## Key Capabilities

| Capability | Description |
|---|---|
| **Dual-Transport Routing** | Connects to either the remote Fabric querying server (`api.fabric.microsoft.com/v1/mcp/powerbi` via SSE) or the local modeling server (`@microsoft/powerbi-modeling-mcp` via STDIO) based on a single environment variable. |
| **Human-in-the-Loop Safety** | Intercepts MCP `elicitation/create` requests (destructive writes, auth prompts) and surfaces them as interactive approval modals. Agent execution suspends until the operator accepts or declines. |
| **Dynamic Tool Discovery** | Queries `list_tools()` at session init and dynamically maps MCP schemas into OpenAI or Anthropic function-calling format — no hardcoded tool definitions. |
| **Real-Time Streaming** | Streams LLM tokens, tool execution states, and raw results to the frontend over a persistent WebSocket. |
| **Pydantic Config Management** | All environment configuration is validated through `pydantic-settings` with `.env` file support. |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────────┐
│  Frontend (Next.js)            :3000                                │
│  ┌──────────┐  ┌────────────┐  ┌──────────────────┐                │
│  │ Sidebar   │  │ ChatInput  │  │ ElicitationModal │                │
│  │ • Config  │  │ • Query    │  │ • Form/URL       │                │
│  │ • Tools   │  │ • Abort    │  │ • Approve/Decline│                │
│  └──────────┘  └─────┬──────┘  └──────────────────┘                │
│                      │ WebSocket                                    │
└──────────────────────┼──────────────────────────────────────────────┘
                       │
┌──────────────────────┼──────────────────────────────────────────────┐
│  Backend (FastAPI)   :8000                                         │
│                      │                                              │
│  ┌───────────────────▼──────────────────────┐                      │
│  │  WebSocket /ws/chat                      │                      │
│  │  • Routes queries to agent loop          │                      │
│  │  • Bridges elicitation ↔ frontend        │                      │
│  └───────────────────┬──────────────────────┘                      │
│                      │                                              │
│  ┌───────────────────▼──────────────────────┐                      │
│  │  Agent Loop (agent.py)                   │                      │
│  │  • System prompt (Power BI specialist)   │                      │
│  │  • LLM streaming (OpenAI / Anthropic)    │                      │
│  │  • Tool call execution via MCP session   │                      │
│  │  • ElicitationCoordinator (async suspend)│                      │
│  └───────────────────┬──────────────────────┘                      │
│                      │ MCP Protocol                                 │
│              ┌───────┴────────┐                                     │
│              │   SSE or STDIO │                                     │
│              └───────┬────────┘                                     │
└──────────────────────┼──────────────────────────────────────────────┘
                       │
        ┌──────────────▼──────────────┐
        │  Power BI MCP Server        │
        │  • Remote (Fabric SSE)      │
        │  • Local  (Desktop STDIO)   │
        └─────────────────────────────┘
```

---

## Project Structure

```
Data-Analysis-Agent/
├── backend/
│   ├── __init__.py              # Package marker
│   ├── agent.py                 # MCP client, LLM orchestration, elicitation coordinator
│   └── main.py                  # FastAPI server, WebSocket endpoint, REST endpoints
│
├── frontend/
│   ├── src/
│   │   ├── app/
│   │   │   ├── page.tsx         # Page orchestrator — composes all components
│   │   │   ├── layout.tsx       # Root layout with Inter font & metadata
│   │   │   └── globals.css      # Dark theme, animations, scrollbar styles
│   │   ├── components/
│   │   │   ├── sidebar.tsx      # Connection status, config display, tool list
│   │   │   ├── chat-message.tsx # Role-based message bubbles with timestamps
│   │   │   ├── chat-input.tsx   # Query input with send/abort toggle
│   │   │   ├── tool-call-card.tsx  # Collapsible tool execution cards
│   │   │   └── elicitation-modal.tsx  # Safety approval overlay (form/URL modes)
│   │   ├── hooks/
│   │   │   └── use-agent.ts     # Custom hook: WebSocket lifecycle & state management
│   │   ├── types/
│   │   │   └── index.ts         # All TypeScript interfaces & discriminated union types
│   │   └── lib/
│   │       └── utils.ts         # cn() utility (clsx + tailwind-merge)
│   ├── package.json
│   ├── tsconfig.json
│   ├── tailwind.config.ts
│   ├── postcss.config.js
│   └── next.config.js
│
├── docs/
│   └── architecture.md          # Detailed design document
│
├── requirements.txt             # Python backend dependencies
├── .env.example                 # Environment variable template
└── .gitignore
```

---

## Quick Start

### Prerequisites

- **Python 3.11+**
- **Node.js 18+** — `winget install OpenJS.NodeJS` on Windows
- **Power BI Desktop** (for STDIO mode) or a **Fabric workspace** (for SSE mode)

### 1. Configure Environment

```bash
cp .env.example .env
```

Edit `.env` with your API keys and transport preferences. See [`.env.example`](.env.example) for all available options.

### 2. Launch Backend

```bash
pip install -r requirements.txt
python -m uvicorn backend.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Launch Frontend

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:3000](http://localhost:3000).

---

## REST Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/health` | Server health check (status, provider, transport, model) |
| `GET` | `/api/config` | Returns active config (no secrets) |
| `WS` | `/ws/chat` | Bidirectional WebSocket for agent queries and elicitation |

---

## WebSocket Protocol

Messages are JSON objects with a `type` discriminator:

**Client → Server:**
- `{ type: "query", text: "..." }` — Submit a natural language query
- `{ type: "elicitation_response", id, action, content }` — Respond to safety prompt
- `{ type: "abort" }` — Cancel active agent execution

**Server → Client:**
- `{ type: "status", status }` — Agent lifecycle updates
- `{ type: "tools_discovered", tools, count }` — Available MCP tools
- `{ type: "token", text }` — Streamed LLM token
- `{ type: "tool_start", calls }` — Tool execution started
- `{ type: "tool_result", id, name, result?, error? }` — Tool completed
- `{ type: "elicitation_request", id, mode, message, schema?, url? }` — Safety approval needed
- `{ type: "complete" }` — Agent run finished
- `{ type: "error", message }` — Error occurred

---

## Further Reading

See [docs/architecture.md](docs/architecture.md) for a detailed breakdown of the elicitation suspension/resume flow, dual-transport connection management, and dynamic tool schema mapping.

See [docs/qualification.md](docs/qualification.md) for the idempotent single-user Fabric semantic-model, report, PNG rendering, and visual-QA qualification workflow.
