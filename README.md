# 🛡️ Self-Healing BI Agent

[![CI](https://github.com/josephsenior/Self-Healing-BI-Agent/actions/workflows/ci.yml/badge.svg)](https://github.com/josephsenior/Self-Healing-BI-Agent/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-orange.svg)](https://www.python.org/downloads/)
[![Next.js 14](https://img.shields.io/badge/Next.js-14-black.svg)](https://nextjs.org/)
[![LangGraph](https://img.shields.io/badge/LangGraph-1.0+-orange.svg)](https://langchain-ai.github.io/langgraph/)
[![License: MIT](https://img.shields.io/badge/License-MIT-orange.svg)](LICENSE)

> **A reliability-first, self-healing BI agent by Youssef Mejdi.** It turns natural-language questions into live, governed Power BI dashboards from BigQuery, then validates, diagnoses, and corrects report defects through bounded recovery loops. Durable checkpoints, transient-service retries, and versioned rollback help keep the workflow resilient—from question to Fabric publication.

---

## ▶️ Product Demo

<video controls width="100%" src="https://github.com/user-attachments/assets/7fe8a7a0-afd3-44b0-8c28-e55e3e4dbe98"></video>

---

## ✨ What It Does

You type: *"Create a sales performance dashboard by region and product category for 2024"*

The agent autonomously:

1. 🔍 **Queries BigQuery** — runs SQL, profiles columns, builds a semantic catalog
2. 🧠 **Creates a Power BI Semantic Model** — live BigQuery DirectQuery only; no imports or embedded snapshots
3. 📊 **Authors PBIR Report** — multi-page layouts, KPIs, charts, slicers in structured JSON
4. ✅ **Runs Visual QA** — validates layout, semantics, quality, and official PBIR schemas
5. 🖥️ **Opens in Power BI Desktop** — one-click local preview with live data
6. ☁️ **Publishes to Microsoft Fabric** — deploys directly to your staging workspace

### 🛡️ Reliability, Recovery & Self-Healing

The agent treats report generation as a recoverable workflow, not a one-shot prompt:

- **Quality gates before promotion** reject invalid PBIR, semantic, or visual candidates instead of presenting them as verified.
- **Finding-driven repair** feeds structured QA diagnostics back into bounded revision attempts; unresolved or review-only findings stop safely for human attention.
- **Versioned recovery** preserves dashboard history and supports rollback to a known-good version.
- **Resilient execution** uses durable Redis checkpoints, per-thread worker coordination, and bounded retries for transient cloud API failures.
- **Honest status reporting** distinguishes verified reports, warnings, blocked reviews, and unavailable checks.


---

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│  Frontend  ·  Next.js 14  ·  localhost:3000                 │
│                                                             │
│  ┌─────────────┐  ┌──────────────┐  ┌───────────────────┐  │
│  │   Sidebar   │  │  Chat + AI   │  │  Dashboard Panel  │  │
│  │  • History  │  │  Messages    │  │  • Overview       │  │
│  │  • Tools    │  │  Tool Cards  │  │  • Visual QA      │  │
│  │  • Config   │  │  Streaming   │  │  • Color Themes   │  │
│  └─────────────┘  └──────┬───────┘  │  • Publish        │  │
│                          │ WS       │  • Desktop        │  │
└──────────────────────────┼──────────┴───────────────────────┘
                           │ WebSocket /ws/chat
┌──────────────────────────┼──────────────────────────────────┐
│  Backend  ·  FastAPI  ·  127.0.0.1:8000                     │
│                          │                                  │
│  ┌───────────────────────▼──────────────────────────────┐   │
│  │  LangGraph Agent  (graph_agent.py)                   │   │
│  │  • Gemini / OpenAI / Anthropic via LangChain         │   │
│  │  • Redis checkpointed conversation threads           │   │
│  │  • Human-in-the-loop elicitation safety gates        │   │
│  └──────────────┬────────────────────────────────────────┘  │
│                 │                                            │
│  ┌──────────────▼────────────────────────────────────────┐  │
│  │  Tool Registry  (custom_mcp_server.py)                │  │
│  │                                                       │  │
│  │  BigQuery        PBIR Authoring     Cloud / QA        │  │
│  │  ────────────    ───────────────    ─────────────     │  │
│  │  list_tables     create_workspace   publish_fabric    │  │
│  │  get_schema      stage_report       render_report     │  │
│  │  run_query       validate_spec      visual_qa_review  │  │
│  │  build_catalog   open_desktop       cloud_readiness   │  │
│  └───────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                           │
          ┌────────────────┼────────────────┐
          │                │                │
    ┌─────▼─────┐   ┌──────▼──────┐  ┌─────▼──────┐
    │ BigQuery  │   │ Power BI    │  │ Microsoft  │
    │  (GCP)    │   │ Desktop     │  │   Fabric   │
    └───────────┘   └─────────────┘  └────────────┘
```

---

## 🚀 Quick Start

### Prerequisites

| Requirement | Version | Notes |
|-------------|---------|-------|
| Python | 3.11+ | |
| Node.js | 18+ | `winget install OpenJS.NodeJS` on Windows |
| Redis / Memurai | Any | Optional for local use; enables durable conversation state. `winget install Memurai.Memurai` on Windows. |
| Power BI Desktop | Latest | For local report preview (optional) |
| GCP Service Account | — | For BigQuery integration (optional) |

### 1. Clone & Configure

```bash
git clone https://github.com/josephsenior/Data-Analysis-Agent.git
cd Data-Analysis-Agent
cp .env.example .env
```

Edit `.env` — at minimum set your LLM provider key:

```env
LLM_PROVIDER=gemini          # or openai / anthropic
LLM_MODEL=gemini-3.7-flash
GEMINI_API_KEY=your-key-here
```

### 2. Install Dependencies

```bash
# Python backend
pip install -r requirements.txt

# Node frontend
cd frontend && npm install && cd ..
```

### 3. Start Everything

```bash
python start.py
```

This single command:
- Uses Redis on port 6379 when available; otherwise starts with non-durable in-memory conversation state (`REDIS_REQUIRED=false`)
- Starts FastAPI backend on `http://127.0.0.1:8000`
- Starts Next.js frontend on `http://localhost:3000`

> **Press `Ctrl+C` once** to cleanly stop both processes.

---

## ⚙️ Configuration Reference

All settings live in `.env`. Copy from `.env.example`:

### LLM Settings

```env
LLM_PROVIDER=gemini          # gemini | openai | anthropic
LLM_MODEL=gemini-3.7-flash
GEMINI_API_KEY=...
OPENAI_API_KEY=...
ANTHROPIC_API_KEY=...
```

### BigQuery Integration

```env
GOOGLE_APPLICATION_CREDENTIALS=C:\path\to\service-account.json
BIGQUERY_PROJECT_ID=your-gcp-project
BIGQUERY_LOCATION=EU
BIGQUERY_ALLOWED_DATASETS=project.dataset1,project.dataset2
BIGQUERY_MAX_BYTES_BILLED=1000000000
BIGQUERY_MAX_ROWS=1000
```

> The service account needs `BigQuery Job User` on the billing project and `BigQuery Data Viewer` on each allowed dataset.

### Microsoft Fabric / Power BI Cloud

```env
POWERBI_STAGING_WORKSPACE_ID=00000000-0000-0000-0000-000000000000
POWERBI_CLOUD_LICENSE_MODE=capacity   # capacity | pro | fabric | premium

# Option A: Entra ID app registration (recommended)
AZURE_TENANT_ID=...
AZURE_CLIENT_ID=...
AZURE_CLIENT_SECRET=...

# Option B: Short-lived bearer tokens (quick interactive testing)
FABRIC_API_ACCESS_TOKEN=eyJ...
POWERBI_API_ACCESS_TOKEN=eyJ...
```

### Redis State

```env
REDIS_URL=redis://127.0.0.1:6379/0
REDIS_REQUIRED=false   # Set true to fail fast if Redis is down
```

---

## 🎛️ Key Features

### 🔶 White/Orange Design System
Clean, professional UI built with a white background and orange brand color. Every element follows a unified design language optimised for data engineering and BI workflows.

### 🃏 Rich Tool Call Cards
Each AI tool execution is shown as an interactive card with:
- Status indicator dot (pulsing orange = running, green check = done, red = failed)
- Animated progress bar while executing
- Sortable data grid for BigQuery results with CSV/JSON export
- Dashboard preview with page thumbnails for PBIR operations
- Expandable raw arguments drawer

### 📊 Dashboard Manager Panel
When a dashboard is generated, the right panel exposes:

| Tab | Contents |
|-----|----------|
| **Overview** | Pages, visuals, dataset path |
| **Visual QA** | AI-reviewed issues, render thumbnails |
| **Colors** | Live color theme editor |
| **Publish** | Microsoft Fabric deployment with readiness checks |
| **Desktop** | One-click open in Power BI Desktop |
| **Qualification** | Full end-to-end Fabric qualification suite |

### ☁️ Microsoft Fabric Publishing
The Publish tab shows:
- Live readiness checks (workspace ID, auth tokens, license mode)
- Report display name editor
- Semantic Model ID field for Direct Lake / re-binding
- One-click **Publish to Microsoft Fabric** button
- Direct **Open in Power BI Service** link after publishing

### 🧪 Visual QA Pipeline
After publishing, the agent can:
1. Call ExportToFile API to render report pages as PNG
2. Feed screenshots to the vision LLM for review
3. Identify layout, contrast, truncation, and semantic issues
4. Iterate revisions automatically until QA passes

---

## 📁 Project Structure

```
Data-Analysis-Agent/
├── backend/
│   ├── main.py                        # FastAPI app, REST + WebSocket routes
│   ├── custom_mcp_server.py           # 30+ tool definitions (FastMCP)
│   ├── application/
│   │   └── graph_agent.py             # LangGraph agent graph
│   ├── infrastructure/
│   │   └── redis_state.py             # Redis/in-memory checkpointer
│   └── report_authoring/
│       ├── compiler.py                # PBIR JSON compiler
│       ├── cloud.py                   # Fabric publish + PNG render
│       ├── qualification.py           # End-to-end Fabric qualification
│       └── semantic.py                # Semantic catalog builder
│
├── frontend/
│   └── src/
│       ├── app/page.tsx               # Root workspace layout
│       ├── components/
│       │   ├── sidebar.tsx            # Collapsible sidebar with search & config modal
│       │   ├── tool-call-card.tsx     # Rich tool execution cards
│       │   ├── dashboard-manager.tsx  # 6-tab right panel
│       │   ├── publish-panel.tsx      # Fabric publish UI
│       │   └── visual-qa-panel.tsx    # QA image review panel
│       └── styles/
│           ├── design-system.css      # CSS variables (orange/white theme)
│           └── globals.css            # Layout + component styles
│
├── tests/                             # 82 pytest tests
├── docs/                              # Extended documentation
│   ├── architecture.md
│   ├── bigquery.md
│   ├── qualification.md
│   └── report-authoring.md
├── .env.example                       # All variables with comments
├── .github/workflows/ci.yml           # GitHub Actions CI
├── compose.yaml                       # Docker Compose (Redis + app)
├── start.py                           # One-command local launcher
└── requirements.txt
```

---

## 🧪 Running Tests

```bash
python -m pytest
```

82 tests covering LangGraph agent architecture, BigQuery security boundary, PBIR compiler correctness, visual QA pipeline, and cloud qualification workflow.

---

## 🐳 Docker Compose

```bash
docker compose up
```

Starts Redis + backend + frontend. Edit `compose.yaml` to adjust ports or environment variables.

---

## 📚 Further Reading

| Document | Contents |
|----------|----------|
| [docs/architecture.md](docs/architecture.md) | LangGraph graph, Redis checkpointing, WebSocket protocol |
| [docs/bigquery.md](docs/bigquery.md) | BigQuery security boundary, allowed datasets, Power BI bridge |
| [docs/report-authoring.md](docs/report-authoring.md) | PBIR compiler, visual types, layout grid |
| [docs/qualification.md](docs/qualification.md) | End-to-end Fabric qualification state machine |

---

## 🤝 Contributing

1. Fork the repo
2. Create a feature branch: `git checkout -b feat/your-feature`
3. Commit your changes: `git commit -m "feat: description"`
4. Push and open a Pull Request

---

## 📄 License

MIT License — see [LICENSE](LICENSE) for details.



