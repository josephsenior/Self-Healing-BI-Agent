# System Architecture & Communication Flow

This document details the architectural design of the Power BI Model Context Protocol (MCP) Autonomous Agent. The application uses a split-service design: a Python backend orchestrating model queries and LLM logic, and a Next.js frontend rendering real-time streaming tokens and approval overlays.

---

## High-Level Architecture

```
                  ┌───────────────────────┐
                  │   Next.js React UI    │
                  │   (Port 3000)         │
                  └───────────┬───────────┘
                              │
                    WebSocket │ (Bidirectional Chat & Elicitation)
                              │
                  ┌───────────▼───────────┐
                  │    FastAPI Server     │
                  │    (Port 8000)        │
                  └───────────┬───────────┘
                              │
            ┌─────────────────┴─────────────────┐
            │                                   │
 (Local STDIO Transport)             (Remote SSE Transport)
            │                                   │
┌───────────▼───────────┐           ┌───────────▼───────────┐
│ Power BI Modeling MCP │           │  Power BI Remote MCP  │
│  (Node Subprocess)    │           │ (Fabric API Endpoint) │
└───────────────────────┘           └───────────────────────┘
```

---

## 1. Bidirectional Safety Coordination Flow

Microsoft's local modeling MCP server requests human validation before executing write operations on a semantic model. When this occurs, the server sends an `elicitation/create` request. In our headless backend environment, we suspend the current agent task and route the prompt to the UI using a custom `ElicitationCoordinator`.

### Messaging & Suspension Lifecycle

1. **Agent Start**: The user enters a prompt in the React interface. It is sent via WebSocket:
   ```json
   { "type": "query", "text": "Create a new column called 'Region' in table 'Sales'." }
   ```
2. **LLM Decision**: The LLM analyzes the query, maps it to the `dax_query_operations` tool, and returns a tool call to the client.
3. **MCP Tool Call**: The agent invokes `session.call_tool("dax_query_operations", {...})`.
4. **Safety Trigger**: The local MCP server intercepts the write operation and issues an `elicitation/create` JSON-RPC request to the Python client session.
5. **Callback Invocation**: The client session calls our registered `elicitation_callback`.
6. **Task Suspension**:
   - The callback invokes `coordinator.request_elicitation(message, mode, schema)`.
   - The coordinator generates a unique `elicitation_id`, creates an `asyncio.Future`, and registers it in a pending dictionary.
   - It transmits a message over the WebSocket to the frontend:
     ```json
     {
       "type": "elicitation_request",
       "id": "e7b8...",
       "mode": "form",
       "message": "Do you approve adding column 'Region' to table 'Sales'?",
       "schema": { "properties": { "confirm": { "type": "boolean" } } }
     }
     ```
   - The coordinator awaits the `Future`, suspending the background tool execution task.
7. **User Approval**:
   - The Next.js client renders a modal overlay based on the message and schema.
   - The user clicks **"Approve & Continue"**.
   - The client transmits the decision back over the WebSocket:
     ```json
     {
       "type": "elicitation_response",
       "id": "e7b8...",
       "action": "accept",
       "content": { "confirm": true }
     }
     ```
8. **Task Resumption**:
   - The FastAPI WebSocket receiver loop catches `elicitation_response`.
   - It resolves the future via `coordinator.submit_response(elicit_id, action, content)`.
   - The `elicitation_callback` wakes up and returns the `types.ElicitResult` payload to the MCP server.
9. **Execution Completion**: The MCP server performs the write operation, returns the success response to the client, and the agent streams the final text explanation back to the user.

---

## 2. Dynamic Tool Discovery & Mapping

To avoid tight-coupling and hardcoding tool definitions, the script reads available tools dynamically during the initial handshake:

1. During session startup, the client runs `await session.initialize()`.
2. It then queries the server using `await session.list_tools()`.
3. The returned tool definitions (containing JSON Schema definitions of input arguments) are translated at runtime:
   - **OpenAI**: Maps schemas into the `function` and `parameters` configuration expected by chat completions.
   - **Anthropic**: Maps schemas into standard `input_schema` block objects.
4. This ensures that if Microsoft updates `@microsoft/powerbi-modeling-mcp` or the remote Fabric endpoint to include new actions, the AI agent gains access to them immediately without requiring code changes.
