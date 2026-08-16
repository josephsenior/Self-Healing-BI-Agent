# Runtime architecture

The application is a **local-first modular monolith**. FastAPI remains the single backend deployment, while internal boundaries separate orchestration, infrastructure adapters, and deterministic data/report services.

## Package map

```text
backend/
|-- main.py                         WebSocket/HTTP presentation layer
|-- agent.py                        MCP lifecycle + compatibility facade
|-- application/
|   |-- state.py                    Serializable, thread-scoped AgentState
|   `-- graph_agent.py              Bounded LangGraph model/tool workflow
|-- infrastructure/
|   |-- models.py                   LangChain provider adapters
|   |-- redis_state.py              Redis pool, checkpointer selection and run locks
|   `-- basic_redis_checkpointer.py Core-command saver for Memurai/plain Redis
|-- bigquery.py                     Deterministic read-only BigQuery service
|-- custom_mcp_server.py            Existing MCP tool boundary
`-- report_authoring/               Existing deterministic Power BI services
```

No BigQuery, report-authoring, QA, Fabric, Desktop, or MCP functionality was removed by the migration.

## Runtime flow

```text
Browser query + stable threadId
        |
        v
FastAPI WebSocket creates runId
        |
        v
Redis lock for this threadId
        |
        v
LangGraph model node (LangChain adapter)
        |
        +-- no tool call --> final streamed answer
        |
        `-- tool call --> existing MCP dispatcher
                              |
                              v
                 deterministic BigQuery/Power BI service
                              |
                              v
                        ToolMessage evidence
                              |
                              `----> model node
```

The graph has no application-level tool-iteration budget, so a valid long-running qualification pipeline is not stopped after an arbitrary number of model/tool rounds. LangGraph retains a high recursion safety guard solely to terminate a genuinely non-converging graph. The browser protocol remains `token`, `tool_start`, `tool_result`, `complete`, and `error`, so the current UI does not depend on model-provider event formats.

## State ownership

Redis is not a global Agent Singleton. FastAPI creates one application-scoped Redis connection pool and injects its checkpointer into each graph invocation.

State is isolated by keys:

```text
thread_id -> conversation/checkpoint history
run_id    -> one execution attempt
```

Conversation messages, tool evidence, run metadata, and errors are serializable LangGraph state. MCP sessions, credentials, WebSockets, cancellation tasks, and Python futures never enter checkpoints.

The frontend stores its `threadId` in browser local storage, so reconnecting uses the same Redis checkpoint. A different browser profile receives a different thread.

## Redis lifecycle

The runtime auto-selects the strongest compatible checkpointer:

- `redis-search`: official LangGraph saver when Redis Search/JSON are available.
- `redis-basic`: included core-command saver for Memurai and plain Redis.
- `memory`: non-durable fallback when optional Redis is unreachable.

Memurai is already installed locally, so no Docker command is needed. Verify it with:

```powershell
& "C:\Program Files\Memurai\memurai-cli.exe" -h 127.0.0.1 -p 6379 PING
```

Alternatively, `docker compose up -d redis` starts the supplied `redis:8-alpine` service bound to `127.0.0.1:6379` with AOF persistence.

Configuration:

```env
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_REQUIRED=false
REDIS_CHECKPOINT_TTL_MINUTES=1440
AGENT_MAX_CONTEXT_MESSAGES=80
AGENT_MAX_TOOL_RESULT_CHARS=50000
```

`/api/health` exposes `checkpointer` as `redis-search`, `redis-basic`, or `memory`. When `REDIS_REQUIRED=false`, unreachable Redis falls back to memory and reports `durable: false`. Set `REDIS_REQUIRED=true` for qualification or enterprise execution so startup fails closed if Redis is unavailable.

## Context policy

The durable checkpoint retains thread history. Before each model invocation, context compaction removes orphaned or incomplete historical tool cycles and truncates only at a user-message boundary. This preserves the provider-required `user -> function call -> function response` ordering even after cancellation, reconnect, or long pipelines. The configured `AGENT_MAX_CONTEXT_MESSAGES` is a target window; an active user/tool turn is kept intact when it exceeds that target. Individual MCP results are bounded by `AGENT_MAX_TOOL_RESULT_CHARS`. Large report/render artifacts remain referenced by path or ID rather than embedded as credentials or binary state.

This is bounded context selection, not semantic summarization. A later hardening phase can add structured summaries when real conversation traces show that the fixed window is insufficient.

## Concurrency and recovery

A Redis lock prevents two backend workers from executing the same `threadId` concurrently. Different threads can run independently. LangGraph checkpoints after graph steps, allowing the next invocation to resume conversation state after reconnect or restart.

Exactly-once execution of arbitrary external writes is not guaranteed by a checkpointer alone. Existing idempotent/versioned report and Fabric services remain responsible for safe retries, while approval-requiring MCP writes still use the existing elicitation boundary.

## Provider abstraction

`infrastructure/models.py` is the only layer that chooses:

- `ChatOpenAI`
- `ChatAnthropic`
- `ChatGoogleGenerativeAI`

The LangGraph application layer sees a common LangChain `BaseChatModel`, so provider-specific loops are gone.

## Verification

```powershell
python -m unittest discover -s tests -p "test_*.py"
cd frontend
npx tsc --noEmit
```

`tests/test_agent_architecture.py` proves that the graph discovers and calls existing MCP tools, emits the stable frontend protocol, and isolates locks by thread.
