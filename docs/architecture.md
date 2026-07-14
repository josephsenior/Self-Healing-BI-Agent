# System Architecture

This document details the architectural design of the Power BI MCP Agent — a dual-service system where a Python backend orchestrates MCP client sessions and LLM reasoning, while a Next.js frontend provides a real-time streaming console with human-in-the-loop safety controls.

---

## High-Level Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│  Next.js Frontend (:3000)                                       │
│                                                                 │
│  page.tsx                                                       │
│  ├── useAgent() hook ──── WebSocket lifecycle & state mgmt      │
│  ├── <Sidebar />     ──── Connection status, config, tool list  │
│  ├── <ChatMessage /> ──── Role-based message bubbles            │
│  ├── <ToolCallCard />──── Collapsible tool execution cards      │
│  ├── <ChatInput />   ──── Query input with send/abort           │
│  └── <ElicitationModal /> Safety approval overlay               │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ WebSocket (ws://localhost:8000/ws/chat)
                           │
┌──────────────────────────▼──────────────────────────────────────┐
│  FastAPI Backend (:8000)                                        │
│                                                                 │
│  main.py                                                        │
│  ├── GET /api/health     Health check                           │
│  ├── GET /api/config     Active config (no secrets)             │
│  └── WS  /ws/chat        Bidirectional agent communication      │
│      └── execute_agent()                                        │
│          └── mcp_session_scope()                                │
│              └── run_agent_loop()                                │
│                                                                 │
│  agent.py                                                       │
│  ├── AgentConfig(BaseSettings) ── Pydantic .env config          │
│  ├── SYSTEM_PROMPT             ── Power BI specialist persona   │
│  ├── ElicitationCoordinator    ── Async suspend/resume bridge   │
│  ├── mcp_session_scope()       ── Dual-transport session mgr    │
│  ├── map_mcp_tools_to_*()      ── Dynamic schema mapping       │
│  └── run_agent_loop()          ── Streaming LLM + tool loop     │
│                                                                 │
└──────────────────────────┬──────────────────────────────────────┘
                           │ MCP Protocol
                   ┌───────┴───────┐
                   │               │
          ┌────────▼───────┐ ┌─────▼──────────────┐
          │ STDIO Transport│ │   SSE Transport    │
          │ (npx process)  │ │ (Fabric REST API)  │
          └────────┬───────┘ └─────┬──────────────┘
                   │               │
          ┌────────▼───────┐ ┌─────▼──────────────┐
          │ Power BI       │ │ Power BI           │
          │ Modeling MCP   │ │ Querying MCP       │
          │ (Local Desktop)│ │ (Fabric Remote)    │
          └────────────────┘ └────────────────────┘
```

---

## 1. Configuration Management

All runtime configuration is managed through `AgentConfig`, a Pydantic `BaseSettings` class that reads from both `.env` files and environment variables:

```python
class AgentConfig(BaseSettings):
    transport_mode: str    # "STDIO" or "SSE"
    llm_provider: str      # "openai" or "anthropic"
    llm_model: str         # e.g. "gpt-4o", "claude-sonnet-4-20250514"
    openai_api_key: str
    anthropic_api_key: str
    sse_url: str
    fabric_access_token: str
    stdio_command: str
    stdio_args: list[str]
```

This eliminates scattered `os.environ.get()` calls and provides validation at startup. See `.env.example` for the full list of configurable variables.

---

## 2. Dual-Transport MCP Session

The `mcp_session_scope()` async context manager abstracts transport selection:

- **STDIO mode**: Spawns `npx -y @microsoft/powerbi-modeling-mcp --start` as a child process. Communication happens over stdin/stdout using the MCP STDIO protocol. Used for local model editing with Power BI Desktop.

- **SSE mode**: Connects to `https://api.fabric.microsoft.com/v1/mcp/powerbi` using Server-Sent Events with a Bearer token. Used for querying remote Fabric workspaces.

Both paths yield an initialized `ClientSession` with the elicitation callback registered.

---

## 3. Agent Execution Loop

The `run_agent_loop()` generator drives the LLM reasoning cycle:

1. **Tool Discovery** → `session.list_tools()` → emit `tools_discovered` event
2. **LLM Call** → Stream tokens via OpenAI or Anthropic, yield `token` events
3. **Tool Calls** → If the LLM requests tool calls:
   - Yield `tool_start` event
   - Execute each tool via `session.call_tool(name, args)`
   - Yield `tool_result` events
   - Append results to conversation and loop back to step 2
4. **Completion** → No more tool calls → generator exits

The system prompt injects Power BI specialist context, including DAX validation guidelines and result formatting instructions.

---

## 4. Elicitation Safety Flow

Microsoft's local modeling MCP server requests human approval before executing write operations. The `ElicitationCoordinator` bridges this protocol across the async boundary:

### Suspension & Resumption Sequence

```
 Frontend                    Backend                    MCP Server
    │                          │                           │
    │──── query ──────────────►│                           │
    │                          │──── call_tool() ─────────►│
    │                          │                           │
    │                          │◄── elicitation/create ────│
    │                          │    (mode, message, schema) │
    │                          │                           │
    │                     ┌────┤ coordinator creates Future │
    │                     │    │ and awaits it (SUSPENDED)  │
    │                     │    │                           │
    │◄── elicitation_request ──┤                           │
    │    (id, mode, schema)    │                           │
    │                          │                           │
    │  [User reviews modal]    │                           │
    │  [Clicks Approve]        │                           │
    │                          │                           │
    │──── elicitation_response►│                           │
    │    (id, action, content) │                           │
    │                     │    │                           │
    │                     └───►│ Future resolved (RESUMED) │
    │                          │──── ElicitResult ────────►│
    │                          │                           │
    │                          │◄── tool result ──────────│
    │◄──── tool_result ────────│                           │
    │◄──── token stream ───────│                           │
    │◄──── complete ───────────│                           │
```

### Key Implementation Details

- **`ElicitationCoordinator.request_elicitation()`** creates a unique ID, registers an `asyncio.Future` in a pending dictionary, sends the request to the frontend over WebSocket, and awaits the future — suspending the tool execution task.

- **`ElicitationCoordinator.submit_response()`** resolves the matching future when the frontend sends back the user's decision, resuming the suspended tool call.

- The MCP SDK `ClientSession` accepts an `elicitation_callback` parameter. When provided, it automatically declares `form` and `url` elicitation capabilities during the `session.initialize()` handshake.

- Supported actions: `accept` (proceed with form data), `decline` (reject the operation), `cancel` (abort entirely).

---

## 5. Dynamic Tool Discovery & Mapping

The agent avoids hardcoded tool definitions. At session init:

1. `await session.list_tools()` returns all available MCP tools with JSON Schema input definitions.
2. `map_mcp_tools_to_openai()` translates each tool into the `{ type: "function", function: { name, description, parameters } }` format.
3. `map_mcp_tools_to_anthropic()` translates each tool into the `{ name, description, input_schema }` format.
4. The `tools_discovered` WebSocket event notifies the frontend of available tools for display in the sidebar.

This ensures that if Microsoft updates their MCP servers with new tools, the agent gains access immediately without code changes.

---

## 6. Frontend Component Architecture

The frontend follows a clean separation of concerns:

| Layer | File | Responsibility |
|-------|------|----------------|
| **Hook** | `use-agent.ts` | WebSocket lifecycle, auto-reconnect, message protocol parsing, all state management |
| **Types** | `types/index.ts` | All TypeScript interfaces and discriminated union types for the WebSocket protocol |
| **Orchestrator** | `page.tsx` | Composes all components, fetches config, manages scroll |
| **Components** | `sidebar.tsx` | Connection status indicator, config display, discovered tool chips |
| | `chat-message.tsx` | Role-based message bubbles with embedded tool cards |
| | `tool-call-card.tsx` | Collapsible cards showing tool arguments, results, errors |
| | `elicitation-modal.tsx` | Full-screen safety overlay with dynamic form generation |
| | `chat-input.tsx` | Input bar with send/abort toggle |
