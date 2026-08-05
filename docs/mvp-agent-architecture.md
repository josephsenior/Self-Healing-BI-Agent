# MVP local-first data-analysis agent

This is the simplified architecture for the first reliable implementation. Read from top to bottom.

```mermaid
%%{init: {"flowchart": {"curve": "linear", "nodeSpacing": 45, "rankSpacing": 65}, "themeVariables": {"fontSize": "18px"}}}%%
flowchart TB

classDef user fill:#e8f1ff,stroke:#2563eb,color:#102a56,stroke-width:2px;
classDef app fill:#ede9fe,stroke:#6d28d9,color:#2e1065,stroke-width:2px;
classDef agent fill:#dbeafe,stroke:#1d4ed8,color:#172554,stroke-width:2px;
classDef service fill:#dcfce7,stroke:#15803d,color:#052e16,stroke-width:2px;
classDef state fill:#f3e8ff,stroke:#7e22ce,color:#3b0764,stroke-width:2px;
classDef external fill:#fff7ed,stroke:#c2410c,color:#431407,stroke-width:2px;
classDef output fill:#cffafe,stroke:#0e7490,color:#083344,stroke-width:2px;
classDef security fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:2px;

TITLE["MVP LOCAL-FIRST DATA ANALYSIS AGENT<br/>Single user · one orchestrator · reliable deterministic services"]:::app

USER["Analyst<br/>Business question or dashboard request"]:::user
UI["React / Next.js UI<br/>Chat · progress · approval · artifacts"]:::user
API["FastAPI backend<br/>WebSocket · validation · cancellation"]:::app
ORCH["One agent orchestrator<br/>LangGraph workflow<br/>bounded reasoning and tool selection"]:::agent
STATE["AgentState in Redis<br/>checkpoint · compact context · run status<br/>one application-scoped connection pool"]:::state

ANALYZE["Analysis stage<br/>understand question · select fields<br/>produce structured QueryPlan"]:::agent
TOOLS["MCP tool boundary<br/>dynamic tool discovery and dispatch"]:::app
BQ["BigQuery service<br/>read-only SQL · allowlist · dry run<br/>byte/row limits · QueryEvidence"]:::service
PBI["Power BI services<br/>semantic catalog · PBIP/PBIR compiler<br/>Desktop open when explicitly requested"]:::service
QA["Deterministic validation<br/>schema · fields · layout · evidence<br/>final admission decision"]:::service
RESULT["Verified result<br/>answer · data evidence · local report artifact<br/>warnings and next safe action"]:::output
CREDS["Local secret boundary<br/>Google ADC · Power BI credentials<br/>never placed in prompts or artifacts"]:::security
BQAPI[("Google BigQuery API")]:::external
DESKTOP[("Power BI Desktop")]:::external

TITLE --> USER --> UI --> API --> ORCH
ORCH <--> STATE
ORCH --> ANALYZE --> TOOLS
TOOLS --> BQ --> BQAPI
BQ --> PBI
PBI --> DESKTOP
TOOLS --> QA
ANALYZE --> QA
QA -->|approved| RESULT
QA -->|needs correction| ANALYZE
API --> RESULT --> UI --> USER
CREDS -. credentials only .-> BQ
CREDS -. credentials only .-> PBI

MVP_RULE["MVP boundaries<br/>One user · one orchestrator · no peer agents<br/>Redis manages state, not reasoning<br/>BigQuery/Power BI actions stay deterministic<br/>Cloud publishing is outside this MVP"]:::security
MVP_RULE -.-> ORCH
MVP_RULE -.-> STATE
```

The MVP deliberately uses one orchestrating agent. BigQuery access, Power BI artifact generation, and validation remain deterministic services. Redis stores checkpoints and compact structured context; it is created through an application-scoped connection pool and dependency injection, not a global Singleton.

The cloud publishing and multi-user identity branches can be added after this local workflow is stable.
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