# Target architecture — local-first Power BI data-analysis agent

The diagram is intentionally detailed enough to present from the first user
input through local or Fabric output. Yellow nodes are architectural decisions;
red nodes are non-negotiable security or approval boundaries.

Presentation files:

- [Standalone Mermaid source](target-langgraph-agent-architecture.mmd)
- [Zoomable SVG rendering](target-langgraph-agent-architecture.svg)
- [High-resolution PNG rendering](target-langgraph-agent-architecture.png)

For a presentation, open the SVG in a browser and follow sections 1 through 10,
zooming into the corresponding yellow decision nodes when explaining tradeoffs.
```mermaid
%%{init: {"flowchart": {"defaultRenderer": "elk", "curve": "linear", "nodeSpacing": 30, "rankSpacing": 50}, "themeVariables": {"fontSize": "15px"}}}%%
flowchart TB

%% ============================================================================
%% STYLES AND LEGEND
%% ============================================================================
classDef channel fill:#e8f1ff,stroke:#2563eb,color:#102a56,stroke-width:1px;
classDef graphNode fill:#ede9fe,stroke:#6d28d9,color:#2e1065,stroke-width:1px;
classDef agent fill:#dbeafe,stroke:#1d4ed8,color:#172554,stroke-width:2px;
classDef deterministic fill:#dcfce7,stroke:#15803d,color:#052e16,stroke-width:1px;
classDef security fill:#fee2e2,stroke:#b91c1c,color:#450a0a,stroke-width:2px;
classDef state fill:#f3e8ff,stroke:#7e22ce,color:#3b0764,stroke-width:1px;
classDef output fill:#cffafe,stroke:#0e7490,color:#083344,stroke-width:1px;
classDef decision fill:#fef3c7,stroke:#b45309,color:#451a03,stroke-width:2px;
classDef failure fill:#ffe4e6,stroke:#be123c,color:#4c0519,stroke-width:1px;
classDef optional fill:#f1f5f9,stroke:#64748b,color:#0f172a,stroke-dasharray:5 3;

LEGEND["LEGEND<br/>Blue = bounded LLM reasoning<br/>Purple = LangGraph runtime/state<br/>Green = deterministic code<br/>Red = security or human authority<br/>Cyan = verified output<br/>Yellow = decision plus rejected alternative"]:::decision

%% ============================================================================
%% 1. USER, CLIENT, AND TRANSPORT
%% ============================================================================
subgraph CHANNEL["1 · USER AND CLIENT CHANNEL"]
  direction TB
  USER["Single authenticated analyst<br/>Natural-language question, dashboard request,<br/>revision, local-open, or authorized publish request"]:::channel
  UI["React/Next.js console<br/>Conversation, tool activity, evidence,<br/>approval modal, cancellation, final artifacts"]:::channel
  WS["Persistent WebSocket<br/>run_id + thread_id + ordered events<br/>status / token / tool_start / tool_result / approval / complete"]:::channel
  USER --> UI --> WS
end

D_UI["DECISION D1 · Keep React only as the presentation layer<br/>Reason: rich streaming and approval UX are useful.<br/>Rejected: putting orchestration in React because browser refreshes,<br/>multiple tabs, and client cancellation cannot own durable execution."]:::decision
D_UI ~~~ UI

%% ============================================================================
%% 2. API BOUNDARY AND RUN CONTEXT
%% ============================================================================
subgraph API["2 · FASTAPI RUNTIME BOUNDARY"]
  direction TB
  API_WS["FastAPI WebSocket endpoint<br/>Validate message envelope and size<br/>Create or resume run<br/>Propagate cancellation"]:::deterministic
  RUNCTX["RunContext<br/>run_id · thread_id · user_id<br/>timezone · correlation_id · cancellation token<br/>configured provider · transport mode"]:::state
  EVENTBUS["Typed event emitter<br/>Transforms graph events into stable UI protocol<br/>Redacts secrets and large raw payloads"]:::deterministic
  WS --> API_WS --> RUNCTX
  EVENTBUS --> WS
end

D_SINGLE["DECISION D2 · Single-user identity now, identity-ready state schema<br/>Reason: harden the core before introducing tenant and row-level policy.<br/>Rejected now: multi-user RBAC because it multiplies test combinations<br/>without improving the current agent workflow."]:::decision
D_SINGLE ~~~ RUNCTX

%% ============================================================================
%% 3. LANGGRAPH CONTROL PLANE AND AUTHORITATIVE STATE
%% ============================================================================
subgraph CONTROL["3 · LANGGRAPH CONTROL PLANE — THE MAIN AGENT RUNTIME"]
  direction TB

  GRAPH_START(("START / RESUME")):::graphNode
  LOAD["Load checkpoint and active dashboard metadata"]:::graphNode
  NORMALIZE["Normalize request<br/>Preserve original text<br/>Attach current dashboard context when referenced"]:::deterministic
  CLASSIFY{"Classify intent and required authority"}:::graphNode

  STATE[["Authoritative AgentState<br/>identity: run_id, thread_id, user_id<br/>request: text, intent, constraints<br/>source: project, allowed dataset, selected tables<br/>analysis: query plan, SQL, result summary, evidence<br/>model: semantic catalog, semantic_model_path<br/>report: DashboardSpec, dashboard_id, base_version<br/>quality: validation findings, render evidence<br/>control: attempt counters, approvals, errors<br/>output: artifacts, final response, audit references"]]:::state

  CHECKPOINT[("Checkpointer<br/>Local qualification: SQLite<br/>Enterprise target: PostgreSQL<br/>Checkpoint after every external side effect")]:::state

  ROUTE_CHAT["Route: explanation or metadata-only answer"]:::graphNode
  ROUTE_ANALYSIS["Route: BigQuery analysis"]:::graphNode
  ROUTE_CREATE["Route: create dashboard"]:::graphNode
  ROUTE_REVISE["Route: inspect/audit/revise existing dashboard"]:::graphNode
  ROUTE_OPEN["Route: explicitly open local Power BI report"]:::graphNode
  ROUTE_PUBLISH["Route: explicitly publish/render in Fabric"]:::graphNode
  ROUTE_QUALIFY["Route: explicit end-to-end qualification"]:::graphNode

  GRAPH_START --> LOAD --> NORMALIZE --> CLASSIFY
  CLASSIFY -->|answer only| ROUTE_CHAT
  CLASSIFY -->|analyze data| ROUTE_ANALYSIS
  CLASSIFY -->|new report| ROUTE_CREATE
  CLASSIFY -->|existing report| ROUTE_REVISE
  CLASSIFY -->|explicit local open| ROUTE_OPEN
  CLASSIFY -->|explicit cloud mutation| ROUTE_PUBLISH
  CLASSIFY -->|qualification request| ROUTE_QUALIFY

  LOAD -. read .-> STATE
  NORMALIZE -. update .-> STATE
  CLASSIFY -. update .-> STATE
  STATE <--> CHECKPOINT
end

D_GRAPH["DECISION D3 · LangGraph owns orchestration; LangChain supplies model/tool adapters<br/>Reason: durable state, explicit transitions, interrupts, bounded loops, and replay.<br/>Rejected: the current global while-true ReAct loop because stopping,<br/>recovery, and provider behavior are model-dependent."]:::decision
D_GRAPH ~~~ CONTROL

D_CHECK["DECISION D4 · Checkpoint after side effects, not after every token<br/>Reason: resume safely without duplicating queries, reports, or publications.<br/>Rejected: memory-only state because a process crash loses approvals and progress.<br/>Rejected now: Temporal because its operational cost is excessive for one user."]:::decision
D_CHECK ~~~ CHECKPOINT

%% ============================================================================
%% 4. MODEL PROVIDERS AND BOUNDED REASONING ROLES
%% ============================================================================
subgraph REASONING["4 · BOUNDED REASONING — JUDGMENT ONLY"]
  direction TB

  MODEL_GATE["LangChain ChatModel adapter<br/>OpenAI / Anthropic / Google<br/>Common messages, structured output, timeout, token budget"]:::deterministic

  ANALYST["Analyst agent — bounded ReAct, maximum 2 corrections<br/>Understands the business question<br/>Selects relevant metadata<br/>Proposes read-only SQL<br/>Interprets returned evidence<br/>Cannot execute outside approved BigQuery tools"]:::agent

  BUILDER["Report Builder agent — bounded revision, maximum 2 corrections<br/>Selects registered Power BI visuals<br/>Produces complete DashboardSpec<br/>Revises only from structured validator feedback<br/>Cannot directly edit generated PBIR"]:::agent

  REVIEWER["Optional Reviewer agent — read-only advisory critic<br/>Checks whether conclusions answer the question<br/>Checks visual narrative and evidence alignment<br/>May recommend rejection; may never override code validation"]:::agent

  BUDGET{"Reasoning attempt budget remaining?"}:::graphNode
  HUMAN_REVIEW["Interrupt: NEEDS_REVIEW<br/>Present evidence and unresolved findings<br/>Wait for explicit human direction"]:::security

  MODEL_GATE --> ANALYST
  MODEL_GATE --> BUILDER
  MODEL_GATE --> REVIEWER
  BUDGET -->|yes| ANALYST
  BUDGET -->|no or identical failure repeated| HUMAN_REVIEW
end

D_AGENTS["DECISION D5 · One graph with two specialists, not three peer agents<br/>Reason: extraction and execution are security-sensitive deterministic services.<br/>Analyst reasons; Builder authors; Reviewer is optional and read-only.<br/>Rejected: Extractor/Executor/Validator peer agents because handoffs duplicate state,<br/>increase cost, blur authority, and allow one LLM to approve another LLM."]:::decision
D_AGENTS ~~~ REASONING

D_REACT["DECISION D6 · ReAct exists only inside bounded Analyst/Builder nodes<br/>Reason: ambiguity, SQL repair, and visual selection need judgment.<br/>Rejected: ReAct for credentials, querying, validation, versioning, or publication<br/>because those operations have known deterministic transitions."]:::decision
D_REACT ~~~ ANALYST

D_PROVIDER["DECISION D7 · Provider-neutral interface, provider-specific packages<br/>Reason: consistent graph state while preserving native model capabilities.<br/>Rejected: three copied provider loops because fixes and policies drift over time."]:::decision
D_PROVIDER ~~~ MODEL_GATE

%% ============================================================================
%% 5. MCP ADAPTER AND HUMAN-IN-THE-LOOP BRIDGE
%% ============================================================================
subgraph MCP["5 · MCP INTEGRATION BOUNDARY"]
  direction TB
  DISCOVER["Dynamic MCP tool discovery at session initialization<br/>Read JSON schemas and register typed LangChain tools"]:::deterministic
  REGISTRY["Tool Registry and Policy Metadata<br/>tool name · source session · read/write class<br/>timeout · retry class · approval requirement"]:::deterministic
  DISPATCH["Multi-session dispatcher<br/>Route tool call to the owning warm MCP session"]:::deterministic
  MS_MCP["Microsoft Power BI Modeling MCP<br/>STDIO for local Desktop model operations"]:::deterministic
  CUSTOM_MCP["Custom FastMCP helper server<br/>BigQuery · PBIR authoring · workspace<br/>Fabric qualification · rendering · QA"]:::deterministic
  ELICIT["MCP elicitation callback<br/>Convert destructive/auth request into LangGraph interrupt"]:::security
  APPROVAL{"User approves exact operation?"}:::security
  DENY["Record denial<br/>Do not retry or rephrase to bypass policy"]:::failure

  DISCOVER --> REGISTRY --> DISPATCH
  DISPATCH --> MS_MCP
  DISPATCH --> CUSTOM_MCP
  MS_MCP -->|elicitation/create| ELICIT
  CUSTOM_MCP -->|approval-required operation| ELICIT
  ELICIT --> APPROVAL
  APPROVAL -->|no| DENY
  APPROVAL -->|yes; checkpoint decision| DISPATCH
end

D_MCP["DECISION D8 · Keep MCP as the tool protocol<br/>Reason: dynamic discovery isolates the agent from Microsoft and custom tool changes.<br/>Rejected: direct SDK calls inside reasoning nodes because they couple orchestration,<br/>credentials, schemas, and vendor-specific transport."]:::decision
D_MCP ~~~ MCP

D_APPROVAL["DECISION D9 · Approval belongs to a durable interrupt<br/>Reason: a suspended run must survive disconnect or backend restart.<br/>Rejected: a blocking browser callback because it loses state and cannot be audited."]:::decision
D_APPROVAL ~~~ ELICIT

%% ============================================================================
%% 6. BIGQUERY READ-ONLY DATA PLANE
%% ============================================================================
subgraph BQ["6 · BIGQUERY READ-ONLY DATA PLANE"]
  direction TB
  BQ_CONFIG["BigQuerySettings<br/>GOOGLE_APPLICATION_CREDENTIALS path<br/>billing project · location · mandatory dataset allowlist<br/>maximum bytes billed · maximum returned rows"]:::security
  BQ_META["Metadata operations<br/>list allowlisted tables<br/>read table schema<br/>build SemanticModelCatalog"]:::deterministic
  SQL_PLAN["Structured QueryPlan<br/>business goal · selected fields<br/>aggregations · filters · expected grain<br/>proposed Standard SQL"]:::state
  SQL_STATIC{"Static preflight"}:::security
  SQL_STATIC_RULES["Require one SELECT/WITH statement<br/>Reject write/admin keywords and EXTERNAL_QUERY<br/>Reject semicolons/scripts<br/>Check explicit qualified resources against allowlist"]:::security
  BQ_DRY["BigQuery dry run<br/>Standard SQL only · cache disabled<br/>maximum_bytes_billed enforced"]:::security
  REF_CHECK{"Every resolved project.dataset<br/>is allowlisted?"}:::security
  BQ_EXEC["Execute bounded query<br/>maximum bytes billed again<br/>materialize at most configured max_rows"]:::deterministic
  BQ_RESULT["QueryEvidence<br/>columns · rows · accurate row_count<br/>resolved table references<br/>bytes processed/billed · row limit"]:::state
  BQ_DENY["PermissionError / policy finding<br/>No executable query submitted"]:::failure
  CATALOG["SemanticModelCatalog<br/>tables · columns · data types<br/>Used for field-level report validation"]:::deterministic

  BQ_CONFIG --> BQ_META --> CATALOG
  SQL_PLAN --> SQL_STATIC --> SQL_STATIC_RULES --> BQ_DRY --> REF_CHECK
  REF_CHECK -->|yes| BQ_EXEC --> BQ_RESULT
  REF_CHECK -->|no| BQ_DENY
end

D_BQ["DECISION D10 · BigQuery access is a service, never an extraction agent<br/>Reason: least privilege and reproducible enforcement must not depend on prompts.<br/>Rejected: giving an LLM the Google client because it could bypass allowlists,<br/>cost ceilings, audit fields, and stable error handling."]:::decision
D_BQ ~~~ SQL_STATIC

D_DRY["DECISION D11 · Validate both explicit SQL resources and dry-run resolved tables<br/>Reason: text checks catch obvious escapes; BigQuery resolves aliases, views, and syntax.<br/>Rejected: regex-only validation because SQL resolution is not reliably lexical.<br/>Rejected: IAM-only protection because application policy may be narrower than IAM."]:::decision
D_DRY ~~~ BQ_DRY

%% ============================================================================
%% 7. POWER BI MODEL AND REPORT AUTHORING PLANE
%% ============================================================================
subgraph PBI["7 · LOCAL POWER BI MODEL AND REPORT AUTHORING"]
  direction TB

  MODEL_BRIDGE["BigQuery → PBIP semantic-model bridge<br/>Create deterministic .SemanticModel directory<br/>definition.pbism + model.bim + audit manifest"]:::deterministic
  M_PARTITION["Native Power Query partition<br/>GoogleBigQuery.Database<br/>BillingProject configured<br/>ADBC Implementation 2.0<br/>UseStorageApi false by default"]:::deterministic
  STORAGE{"Requested storage mode"}:::graphNode
  DIRECT["DirectQuery default<br/>Fresh data, smaller local artifact"]:::deterministic
  IMPORT["Import optional<br/>Faster visuals/offline copy<br/>Requires explicit refresh lifecycle"]:::deterministic
  PBI_CRED["Power BI Desktop credential store<br/>First use may require one service-account sign-in<br/>No key, token, or email embedded in PBIP"]:::security

  CAPABILITIES["Registered visual capability catalog<br/>visual type → accepted field roles/configuration<br/>Reject unknown untrusted custom visual"]:::deterministic
  SPEC["Strict DashboardSpec<br/>title · relative dataset reference<br/>pages · visuals · positions · typed field refs"]:::state
  SEM_VALIDATE["Semantic validation<br/>table/column/measure exists<br/>hidden-field and cardinality findings<br/>numeric role compatibility"]:::deterministic
  LAYOUT_VALIDATE["Layout validation<br/>bounds · overlap · minimum usable size"]:::deterministic
  COMPILE["Deterministic PBIR compiler<br/>DashboardSpec → definition.pbir<br/>pages, visuals, queries, resources"]:::deterministic
  SCHEMA_VALIDATE["Official PBIR JSON Schema validation<br/>Trusted schema host/cache only"]:::security

  WORKSPACE["DashboardWorkspaceManager<br/>Immutable versions · active version pointer<br/>expected_version conflict check<br/>audit trail · rollback · atomic writes"]:::deterministic
  ADMISSION{"Runtime QA admission controller"}:::security
  VERIFIED["VERIFIED<br/>Promote candidate to active version"]:::output
  WARNINGS["VERIFIED_WITH_WARNINGS<br/>Promote and preserve non-blocking findings"]:::output
  REVISION["NEEDS_REVISION<br/>Return structured, actionable findings"]:::failure
  REVIEW["NEEDS_REVIEW<br/>Stop automatic retries"]:::failure
  DESKTOP_BIND["Desktop handoff<br/>Rebind definition.pbir by relative path<br/>to generated .SemanticModel<br/>Validate again before opening"]:::deterministic
  DESKTOP_OPEN["Explicit os.startfile(definition.pbir)<br/>Power BI Desktop loads model and report"]:::output

  CATALOG --> MODEL_BRIDGE --> M_PARTITION --> STORAGE
  STORAGE -->|default| DIRECT
  STORAGE -->|explicit| IMPORT
  DIRECT --> PBI_CRED
  IMPORT --> PBI_CRED

  CAPABILITIES --> SPEC
  CATALOG --> SEM_VALIDATE
  SPEC --> SEM_VALIDATE --> LAYOUT_VALIDATE --> COMPILE --> SCHEMA_VALIDATE --> WORKSPACE --> ADMISSION
  ADMISSION -->|no blocking finding| VERIFIED
  ADMISSION -->|warnings only| WARNINGS
  ADMISSION -->|correctable and attempts remain| REVISION
  ADMISSION -->|repeated/uncertain failure| REVIEW
  VERIFIED --> DESKTOP_BIND
  WARNINGS --> DESKTOP_BIND
  DESKTOP_BIND --> DESKTOP_OPEN
end

D_MODEL["DECISION D12 · Generate a real semantic-model connection definition<br/>Reason: a catalog alone cannot make Desktop query BigQuery.<br/>Rejected: embedding Google credentials because PBIP is source-controlled,<br/>portable, and not an acceptable secret store."]:::decision
D_MODEL ~~~ MODEL_BRIDGE

D_DIRECT["DECISION D13 · DirectQuery is default; Import is an explicit option<br/>Reason: local-first analysis should see current data without copying datasets.<br/>Tradeoff: DirectQuery depends on connectivity and source performance;<br/>use Import when interactivity/offline operation outweighs freshness."]:::decision
D_DIRECT ~~~ STORAGE

D_SPEC["DECISION D14 · LLM produces DashboardSpec, never PBIR JSON directly<br/>Reason: a narrow typed contract enables deterministic compilation and validation.<br/>Rejected: free-form PBIR generation because schema drift and hallucinated fields<br/>would enter source artifacts before validation."]:::decision
D_SPEC ~~~ SPEC

D_VERSION["DECISION D15 · Immutable revisions plus optimistic concurrency<br/>Reason: every mutation is auditable and rollback is reliable.<br/>Rejected: editing the active report in place because partial failure destroys<br/>the last known-good version."]:::decision
D_VERSION ~~~ WORKSPACE

D_QA["DECISION D16 · Deterministic QA has final authority<br/>Reason: security, schema, and semantic correctness require reproducible rules.<br/>Rejected: an LLM validator as final approver because confident agreement<br/>between agents is not evidence of correctness."]:::decision
D_QA ~~~ ADMISSION

%% ============================================================================
%% 8. FABRIC CLOUD PLANE — EXPLICIT AND OPTIONAL
%% ============================================================================
subgraph FABRIC["8 · OPTIONAL FABRIC CLOUD PLANE"]
  direction TB
  CLOUD_GATE{"Explicit publish or qualification request<br/>and recorded user approval?"}:::security
  MSAL["MSAL token provider<br/>Acquire separate Power BI and Fabric scopes<br/>Never expose access tokens to the LLM"]:::security
  READINESS["Readiness checks<br/>workspace configured · capacity/trial available<br/>required APIs reachable · bounded throttling retry"]:::deterministic
  IDEMPOTENCY["Qualification state store<br/>Persist workspace/model/report IDs and completed steps<br/>Reuse resources safely after restart"]:::state
  PUBLISH_MODEL["Create/update semantic model<br/>Credential-free definition parts<br/>Poll long-running operation to terminal state"]:::deterministic
  REFRESH["Request semantic-model refresh<br/>Poll success/failure with deadline"]:::deterministic
  PUBLISH_REPORT["Create/update report bound to remote model<br/>Poll long-running operation"]:::deterministic
  RENDER["Render report pages to PNG<br/>Persist page evidence and operation IDs"]:::deterministic
  VISUAL_REVIEW["Visual evidence review<br/>layout, clipping, readability, narrative<br/>Optional reviewer suggestion + deterministic attempt gate"]:::deterministic
  CLOUD_DONE["Verified Fabric resource IDs<br/>semantic model · report · rendered pages<br/>qualification evidence"]:::output
  CLOUD_STOP["Stop safely<br/>No success claim without terminal API evidence"]:::failure

  CLOUD_GATE -->|yes| MSAL --> READINESS --> IDEMPOTENCY
  IDEMPOTENCY --> PUBLISH_MODEL --> REFRESH --> PUBLISH_REPORT --> RENDER --> VISUAL_REVIEW
  VISUAL_REVIEW -->|accepted| CLOUD_DONE
  VISUAL_REVIEW -->|correctable and bounded attempt remains| REVISION
  VISUAL_REVIEW -->|failed/timeout/no evidence| CLOUD_STOP
  CLOUD_GATE -->|no| CLOUD_STOP
end

D_LOCAL["DECISION D17 · Local-first core; Fabric is an optional output plane<br/>Reason: analysis and authoring remain usable without tenant admin privileges.<br/>Rejected: Fabric-first execution because Entra/Fabric access would block<br/>local development, qualification, and single-user iteration."]:::decision
D_LOCAL ~~~ CLOUD_GATE

D_CLOUD["DECISION D18 · Idempotent cloud workflow, not a cloud execution agent<br/>Reason: API mutations and long-running operations need exact IDs and terminal states.<br/>Rejected: letting an agent improvise retries because it can duplicate resources<br/>or report success before Fabric completes the operation."]:::decision
D_CLOUD ~~~ IDEMPOTENCY

%% ============================================================================
%% 9. VALIDATION, ERROR POLICY, AND OBSERVABILITY
%% ============================================================================
subgraph GOVERNANCE["9 · CROSS-CUTTING RELIABILITY AND GOVERNANCE"]
  direction TB
  ERROR_CLASS{"Classify failure"}:::graphNode
  SECURITY_FAIL["Security/policy failure<br/>Fail closed · never auto-retry"]:::failure
  AUTH_FAIL["Missing/expired external authorization<br/>Interrupt for exact credential or approval action"]:::failure
  TRANSIENT_FAIL["Transient network/throttling failure<br/>Bounded exponential retry with deadline"]:::failure
  SEMANTIC_FAIL["Semantic/layout/schema finding<br/>Structured feedback to Builder"]:::failure
  REPEAT_FAIL["Same blocking fingerprint repeated<br/>Stop at NEEDS_REVIEW"]:::failure

  AUDIT["Structured audit record<br/>run and thread IDs · tool name · sanitized arguments<br/>policy decision · resource IDs · version · outcome · timings"]:::deterministic
  METRICS["Operational metrics<br/>latency · token/tool cost · query bytes<br/>retry counts · validation pass rate · approval rate"]:::deterministic
  TRACE["Optional LangSmith or OpenTelemetry tracing<br/>Opt-in and redacted<br/>Not required for runtime correctness"]:::optional
  SECRETS["Secret boundary<br/>.env / OS credential stores during local qualification<br/>enterprise target: managed secret vault<br/>Never graph state, prompt, PBIR, logs, or frontend events"]:::security

  ERROR_CLASS -->|policy| SECURITY_FAIL
  ERROR_CLASS -->|authorization| AUTH_FAIL
  ERROR_CLASS -->|transient| TRANSIENT_FAIL
  ERROR_CLASS -->|correctable artifact| SEMANTIC_FAIL
  SEMANTIC_FAIL --> REPEAT_FAIL
  AUDIT --> METRICS --> TRACE
end

D_RETRY["DECISION D19 · Retry by typed failure class<br/>Reason: throttling may recover; security and deterministic validation will not.<br/>Rejected: generic automatic retry because it wastes cost and can repeat mutations."]:::decision
D_RETRY ~~~ ERROR_CLASS

D_OBS["DECISION D20 · Observability is replaceable; audit evidence is mandatory<br/>Reason: enterprise review needs stable local records independent of a SaaS vendor.<br/>Rejected: making LangSmith mandatory because privacy, cost, or connectivity<br/>must not prevent local execution."]:::decision
D_OBS ~~~ AUDIT

%% ============================================================================
%% 10. END-TO-END ROUTING — FIRST INPUT TO FINAL OUTPUT
%% ============================================================================
ROUTE_CHAT --> ANALYST
ROUTE_ANALYSIS --> ANALYST
ROUTE_CREATE --> ANALYST
ROUTE_REVISE --> WORKSPACE
ROUTE_OPEN --> WORKSPACE
ROUTE_PUBLISH --> CLOUD_GATE
ROUTE_QUALIFY --> CLOUD_GATE

ANALYST -->|metadata request| DISCOVER
ANALYST -->|proposed QueryPlan| SQL_PLAN
BQ_META -->|metadata and catalog| ANALYST
BQ_RESULT -->|evidence, never credentials| ANALYST
ANALYST -->|answer supported by evidence| ANSWER_BUILD
ANALYST -->|dashboard required| BUILDER
WORKSPACE -->|active spec, version, audit| BUILDER
BUILDER -->|request registered visual capabilities| CAPABILITIES
BUILDER -->|complete candidate spec| SPEC
REVISION -->|structured correction only| BUDGET
BUDGET -->|builder correction| BUILDER
REVIEW --> HUMAN_REVIEW

ROUTE_OPEN -->|must be explicit| DESKTOP_BIND
ROUTE_PUBLISH -->|must be explicit| APPROVAL
ROUTE_QUALIFY -->|must be explicit| APPROVAL

MS_MCP --> ERROR_CLASS
CUSTOM_MCP --> ERROR_CLASS
BQ_DENY --> ERROR_CLASS
SCHEMA_VALIDATE --> ERROR_CLASS
CLOUD_STOP --> ERROR_CLASS
TRANSIENT_FAIL -->|retry same deterministic node only| DISPATCH
SEMANTIC_FAIL --> BUDGET
AUTH_FAIL --> ELICIT
SECURITY_FAIL --> ANSWER_BUILD
REPEAT_FAIL --> HUMAN_REVIEW

VERIFIED --> ANSWER_BUILD
WARNINGS --> ANSWER_BUILD
DESKTOP_OPEN --> ANSWER_BUILD
CLOUD_DONE --> ANSWER_BUILD
HUMAN_REVIEW --> EVENTBUS
DENY --> ANSWER_BUILD

subgraph OUTPUTS["10 · VERIFIED OUTPUT AND USER FEEDBACK"]
  direction TB
  ANSWER_BUILD["Final response assembler<br/>State what was completed<br/>Attach data/report/model paths or cloud IDs<br/>Include validation status and evidence<br/>Disclose remaining credential or approval boundary<br/>Never claim unverified success"]:::deterministic
  LOCAL_ARTIFACTS["Local artifacts<br/>query evidence · semantic catalog<br/>.SemanticModel · versioned PBIR workspace<br/>audit and QA reports"]:::output
  CLOUD_ARTIFACTS["Optional cloud artifacts<br/>Fabric semantic model/report IDs<br/>rendered PNG evidence<br/>terminal operation outcomes"]:::output
  UI_FINAL["UI presentation<br/>Answer + artifact links + warnings<br/>reproducible run status and next safe action"]:::output

  ANSWER_BUILD --> LOCAL_ARTIFACTS
  ANSWER_BUILD --> CLOUD_ARTIFACTS
  ANSWER_BUILD --> EVENTBUS --> UI_FINAL --> USER
end

%% Every meaningful operation emits evidence and updates durable state.
ANALYST -. state/evidence .-> STATE
BUILDER -. state/candidate .-> STATE
BQ_RESULT -. checkpoint .-> STATE
WORKSPACE -. version metadata .-> STATE
ADMISSION -. QA status .-> STATE
CLOUD_DONE -. cloud evidence .-> STATE
ERROR_CLASS -. typed error .-> STATE

ANALYST -. audit .-> AUDIT
BUILDER -. audit .-> AUDIT
DISPATCH -. audit .-> AUDIT
BQ_EXEC -. audit .-> AUDIT
WORKSPACE -. audit .-> AUDIT
PUBLISH_MODEL -. audit .-> AUDIT

SECRETS -. supplies credentials only to .-> BQ_CONFIG
SECRETS -. supplies credentials only to .-> MSAL
SECRETS -. supplies credentials only to .-> PBI_CRED

LEGEND ~~~ USER
```

