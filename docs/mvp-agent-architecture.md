# MVP local-first data-analysis agent

This is the simplified execution view for the first reliable implementation. Follow the numbered stages from top to bottom. The orange handoffs are the only workflow path; side notes describe boundaries without adding execution branches.

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 30, "rankSpacing": 45}, "themeVariables": {"fontSize": "17px"}}}%%
flowchart TB

classDef input fill:#e8f1ff,stroke:#2563eb,color:#102a56,stroke-width:2px;
classDef control fill:#ede9fe,stroke:#6d28d9,color:#2e1065,stroke-width:2px;
classDef reasoning fill:#dbeafe,stroke:#1d4ed8,color:#172554,stroke-width:2px;
classDef service fill:#dcfce7,stroke:#15803d,color:#052e16,stroke-width:2px;
classDef state fill:#f3e8ff,stroke:#7e22ce,color:#3b0764,stroke-width:2px;
classDef handoff fill:#fff7ed,stroke:#c2410c,color:#431407,stroke-width:2px;
classDef output fill:#cffafe,stroke:#0e7490,color:#083344,stroke-width:2px;
classDef boundary fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:2px;
classDef note fill:#f8fafc,stroke:#64748b,color:#0f172a,stroke-dasharray:5 3;

TITLE["MVP LOCAL-FIRST DATA-ANALYSIS AGENT<br/>One user - one orchestrator - deterministic execution"]:::control

subgraph S1["1. INPUT"]
  direction TB
  USER["Analyst submits a question or dashboard request"]:::input
  UI["React / Next.js console<br/>chat, progress, approval, artifacts"]:::input
  USER --> UI
end
H1["HANDOFF 1<br/>Request text + run metadata"]:::handoff
UI --> H1

subgraph S2["2. BACKEND RUN SETUP"]
  direction TB
  API["FastAPI WebSocket endpoint<br/>validate input, create run_id, handle cancellation"]:::control
  CTX["RunContext<br/>thread_id, provider, permissions, cancellation"]:::state
  API --> CTX
end
H2["HANDOFF 2<br/>Validated request + isolated run context"]:::handoff
H1 --> API
CTX --> H2

subgraph S3["3. DURABLE STATE"]
  direction TB
  REDIS["Redis adapter<br/>application-scoped connection pool<br/>checkpoint, compact context, run status, locks"]:::state
  PORTS["Injected ports<br/>ContextStore, LockService, EventPublisher"]:::control
  REDIS --> PORTS
end
H3["HANDOFF 3<br/>Recoverable state services available to the workflow"]:::handoff
H2 --> REDIS
PORTS --> H3

subgraph S4["4. AGENT ORCHESTRATION"]
  direction TB
  ORCH["Single agent orchestrator<br/>bounded workflow and tool selection"]:::reasoning
  ANALYZE["Analysis stage<br/>understand intent, select fields, create structured QueryPlan"]:::reasoning
  ORCH --> ANALYZE
end
H4["HANDOFF 4<br/>Structured QueryPlan"]:::handoff
H3 --> ORCH
ANALYZE --> H4

subgraph S5["5. DATA ACQUISITION"]
  direction TB
  MCP["MCP tool boundary<br/>discover tools and dispatch approved calls"]:::control
  BQ["BigQuery read-only service<br/>allowlist, SQL preflight, dry run, byte/row limits"]:::service
  EVIDENCE["QueryEvidence<br/>rows, columns, row_count, referenced tables, bytes"]:::state
  MCP --> BQ --> EVIDENCE
end
H5["HANDOFF 5<br/>Evidence-backed data result"]:::handoff
H4 --> MCP
EVIDENCE --> H5

subgraph S6["6. OPTIONAL POWER BI ARTIFACT"]
  direction TB
  CHOICE["Does the user request a local dashboard artifact?"]:::control
  CATALOG["Semantic catalog and BigQuery model binding"]:::service
  REPORT["PBIP/PBIR compiler<br/>DashboardSpec to versioned local report"]:::service
  ANSWER["Answer/data-only result"]:::output
  CHOICE -->|yes| CATALOG --> REPORT
  CHOICE -->|no| ANSWER
end
H6["HANDOFF 6<br/>Data answer or candidate report"]:::handoff
H5 --> CHOICE
REPORT --> H6
ANSWER --> H6

subgraph S7["7. DETERMINISTIC QUALITY GATE"]
  direction TB
  QA["Validation service<br/>schema, fields, layout, evidence, security"]:::service
  ADMIT["Admission decision<br/>verified, verified with warnings, or needs review"]:::boundary
  QA --> ADMIT
end
H7["HANDOFF 7<br/>Verified result and audit evidence"]:::handoff
H6 --> QA
ADMIT --> H7

subgraph S8["8. DELIVERY"]
  direction TB
  LOCAL["If approved and requested:<br/>open the generated report in Power BI Desktop"]:::service
  FINAL["Final response assembler<br/>answer, evidence, artifact path, warnings, next action"]:::output
  UI2["React console displays the result"]:::input
  LOCAL --> FINAL
  FINAL --> UI2
end
H7 --> LOCAL
H7 --> FINAL
UI2 --> USER


subgraph S9["9. ARCHITECTURE DECISIONS"]
  direction TB
  DECISIONS["Why this approach?<br/><br/>1. Modular monolith instead of microservices: one local user and lower operational cost.<br/>2. Clean/Hexagonal ports instead of direct SDK calls: replaceable adapters and testability.<br/>3. One orchestrator instead of peer agents: fewer handoffs, lower cost, clearer debugging.<br/>4. Redis pool + dependency injection instead of Singleton: durable shared state without hidden global state.<br/>5. Deterministic services instead of LLM execution: security, limits, validation, and audit are reproducible.<br/>6. Local-first instead of cloud-first: harden BigQuery-to-Desktop workflow before Fabric administration."]:::note
end
UI2 --> S9
BOUNDARY["Security boundary<br/>Credentials stay in local environment / OS store<br/>never in prompts, AgentState, PBIP files, or logs"]:::boundary
MVP["MVP scope<br/>single user, local execution, one orchestrator<br/>Fabric publishing and multi-user identity are deferred"]:::note
BOUNDARY -. applies to .-> BQ
BOUNDARY -. applies to .-> REPORT
MVP -. scope .-> TITLE
```

The MVP is a **local-first modular monolith using Clean/Hexagonal Architecture with one bounded agent orchestrator**. Redis is an application-scoped infrastructure adapter, not a global Singleton. BigQuery access, Power BI artifact generation, and quality validation remain deterministic services.
## Architecture decisions

### D1 — Local-first modular monolith

**Chosen:** one FastAPI backend containing the orchestration, data, Power BI, and validation modules.

**Why:** the MVP is for one user and local Power BI Desktop. This minimizes deployment and debugging overhead while keeping module boundaries clear.

**Deferred alternative:** microservices. They would add network contracts, deployment, observability, and failure modes before the workflow is stable.

### D2 — Clean/hexagonal boundaries

**Chosen:** the application depends on ports such as `ContextStore`, `LockService`, `EventPublisher`, and `BigQueryGateway`; Redis and cloud services are adapters.

**Why:** infrastructure can change without rewriting the agent core, and each service can be tested with fakes.

**Deferred alternative:** direct SDK calls throughout the agent. That would couple reasoning, credentials, vendor APIs, and persistence.

### D3 — One orchestrating agent

**Chosen:** one bounded agent with an analysis stage, followed by deterministic tool execution and validation.

**Why:** the MVP does not need peer-agent handoffs. One orchestrator is easier to trace, cheaper to run, and less likely to lose context.

**Deferred alternative:** separate extractor, executor, validator, and report-builder agents. Those may be introduced only when complexity or team ownership justifies them.

### D4 — Deterministic services have execution authority

**Chosen:** BigQuery security, Power BI compilation, and QA are implemented as code, not delegated to the LLM.

**Why:** allowlists, byte limits, schema checks, versioning, and approval rules must be reproducible and fail closed.

**Rejected alternative:** allowing the LLM to call provider SDKs directly. Prompts cannot be treated as a security boundary.

### D5 — Redis with an application-scoped pool

**Chosen:** Redis stores checkpoints, compact structured context, run status, locks, and typed events. The backend creates one pool during application startup and injects interfaces into services.

**Why:** state survives reconnects and restarts, and the same design can coordinate multiple workers later.

**Rejected alternative:** a global Singleton client. It hides lifecycle and configuration, complicates testing, and creates unsafe process-global state.

### D6 — Structured context compaction

**Chosen:** retain query plans, evidence summaries, dashboard specifications, validation findings, and artifact references; bound or discard verbose raw tool payloads.

**Why:** each workflow stage receives the smallest relevant context while durable evidence remains available for replay and audit.

**Deferred alternative:** unlimited transcript replay, which increases token cost and eventually exceeds model context windows.

### D7 — Local delivery first

**Chosen:** generate a credential-free semantic model/report artifact and open it in Power BI Desktop only when explicitly requested.

**Why:** this validates the core BigQuery-to-Power BI workflow without requiring Fabric administration or Entra application registration.

**Deferred alternative:** cloud-first publishing. It adds tenant permissions, capacity, identity, and long-running API operations before the local core is hardened.

## MVP success criterion

A single analyst can ask a question, receive evidence-backed results, optionally generate a validated local Power BI artifact, and resume the run after a reconnect—without peer-agent complexity or cloud administration.