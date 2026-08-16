import sys
import json
import os
import subprocess
import uuid
import re
import time
from typing import Dict, Any, List, Literal
from pathlib import Path

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
load_dotenv(PROJECT_ROOT / ".env")

# Local development may deliberately bypass a machine-level proxy for Google
# APIs. This is opt-in so corporate proxy deployments keep their normal route.
if os.getenv("BIGQUERY_BYPASS_PROXY", "false").strip().lower() in {"1", "true", "yes", "on"}:
    google_hosts = {
        "oauth2.googleapis.com",
        "bigquery.googleapis.com",
        "storage.googleapis.com",
    }
    for name in ("NO_PROXY", "no_proxy"):
        current = {item.strip() for item in os.getenv(name, "").split(",") if item.strip()}
        os.environ[name] = ",".join(sorted(current | google_hosts))

# Add current directory to path to allow importing fastmcp if it is in backend directory or local env
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from fastmcp import FastMCP

# Create FastMCP server
mcp = FastMCP("Power BI Analytics and Helper Server")

# ==============================================================================
# DAX FORMATTER TOOL
# ==============================================================================
@mcp.tool()
def format_dax(dax_code: str) -> str:
    """
    Formats and beautifies a DAX expression.
    Capitalizes standard keywords and applies consistent line indentations.
    """
    keywords = {
        "calculate", "filter", "all", "sum", "average", "count", "divide", "var", "return", 
        "if", "and", "or", "not", "selectedvalue", "calculatetable", "values", "distinct", 
        "userelationship", "treatas", "keepfilters", "evaluate", "define", "measure"
    }
    
    # Capitalize keywords (simple word-based replacements)
    words = re.split(r'(\W+)', dax_code)
    formatted_words = []
    for w in words:
        if w.lower() in keywords:
            formatted_words.append(w.upper())
        else:
            formatted_words.append(w)
    dax_formatted = "".join(formatted_words)
    
    # Indentation layout based on bracket matching
    lines = dax_formatted.split("\n")
    indent_level = 0
    formatted_lines = []
    
    for line in lines:
        line_str = line.strip()
        if not line_str:
            formatted_lines.append("")
            continue
            
        # Count opening and closing brackets to estimate change in indentation for next line
        open_brackets = line_str.count("(") + line_str.count("[") + line_str.count("{")
        close_brackets = line_str.count(")") + line_str.count("]") + line_str.count("}")
        
        # If line starts with a closing bracket, decrease indent for this line itself
        if line_str.startswith(")") or line_str.startswith("]") or line_str.startswith("}"):
            current_indent = max(0, indent_level - 1)
        else:
            current_indent = indent_level
            
        formatted_lines.append("    " * current_indent + line_str)
        
        indent_level += (open_brackets - close_brackets)
        indent_level = max(0, indent_level)
        
    return "\n".join(formatted_lines)

# ==============================================================================
# PYTHON SANDBOX TOOL
# ==============================================================================
@mcp.tool()
def run_python_sandbox(code: str) -> str:
    """
    Executes Python data analysis code in a secure subprocess.
    If the script generates data visualizations/charts, it should save them to the 'static/' directory
    (e.g., 'static/chart.png'), and they will automatically be rendered in the chat.
    
    Standard packages like matplotlib, seaborn, pandas, and numpy are supported.
    """
    # Ensure static directory exists (at the parent of backend directory, so it's in the project root)
    root_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    static_dir = os.path.join(root_dir, "static")
    os.makedirs(static_dir, exist_ok=True)
    
    # Generate unique python script file
    # Uvicorn's development reloader watches ``*.py`` files recursively. A
    # temporary Python-suffixed script inside the repository therefore
    # restarted the backend mid-tool-call and severed the WebSocket before a
    # result could be emitted. Python executes source files regardless of the
    # extension, so use a non-watched suffix.
    temp_filename = os.path.join(root_dir, f"temp_sandbox_{uuid.uuid4().hex}.sandbox")
    
    # Inject helper configuration so user script knows where static dir is
    # Prepend helper imports and static directory variable
    injected_code = (
        f"import os\n"
        f"STATIC_DIR = r'{static_dir}'\n"
        f"os.makedirs(STATIC_DIR, exist_ok=True)\n\n"
        f"{code}"
    )
    
    with open(temp_filename, "w", encoding="utf-8") as f:
        f.write(injected_code)
        
    try:
        # Record start time to detect new charts
        start_time = time.time()
        

        result = subprocess.run(
            [sys.executable, temp_filename],
            stdin=subprocess.DEVNULL,
            capture_output=True,
            text=True,
            timeout=30,
            cwd=root_dir
        )
        stdout = result.stdout
        stderr = result.stderr
        
        output = []
        if stdout:
            output.append(f"### Standard Output:\n```\n{stdout}\n```")
        if stderr:
            output.append(f"### Standard Error:\n```\n{stderr}\n```")
            
        # Detect new chart image files in static directory
        created_charts = []
        if os.path.exists(static_dir):
            for f in os.listdir(static_dir):
                fpath = os.path.join(static_dir, f)
                if os.path.isfile(fpath) and f.lower().endswith((".png", ".jpg", ".jpeg", ".svg")):
                    # Check if modified since we started execution
                    if os.path.getmtime(fpath) >= start_time - 1:
                        # Construct image URL referencing backend server (port 8000)
                        # We use the relative url /static/<name> or full localhost URL
                        url = f"http://localhost:8000/static/{f}"
                        created_charts.append(url)
                        
        if created_charts:
            output.append("### Generated Visualizations:")
            for chart in created_charts:
                output.append(f"![Visualization]({chart})\n*Source: {chart}*")
                
        if not stdout and not stderr and not created_charts:
            return "Script executed successfully with no stdout/stderr or images."
            
        return "\n\n".join(output)
        
    except subprocess.TimeoutExpired:
        return "Error: Script execution timed out (limit: 30 seconds)."
    except Exception as e:
        return f"Error executing script: {str(e)}"
    finally:
        # Cleanup temp file
        if os.path.exists(temp_filename):
            try:
                os.remove(temp_filename)
            except Exception:
                pass



# ==============================================================================
# PBIR REPORT AUTHORING (STAGING ONLY)
# ==============================================================================
from pathlib import Path
from report_authoring import (
    DashboardSpec,
    compile_report,
    inspect_pbir_project,
    list_visual_capabilities,
    validate_pbir_project,
)
from report_authoring.layout import validate_page_layout
from report_authoring.semantic import SemanticModelCatalog

AUTHORING_ROOT = Path(
    os.getenv("POWERBI_AUTHORING_ROOT", Path(__file__).resolve().parent.parent)
).resolve()


def _bigquery_service():
    """Create the read-only BigQuery facade only when a tool is called."""
    try:
        from backend.bigquery import BigQueryService
    except ModuleNotFoundError:
        from bigquery import BigQueryService
    return BigQueryService()


@mcp.tool()
def bigquery_list_tables(dataset: str) -> str:
    """List tables/views in an allowlisted BigQuery dataset for dashboard planning."""
    return json.dumps({"tables": _bigquery_service().list_tables(dataset)}, indent=2)


@mcp.tool()
def bigquery_get_table_schema(table: str) -> str:
    """Inspect BigQuery table columns before defining a Power BI semantic model."""
    return json.dumps({"table": table, "fields": _bigquery_service().schema(table)}, indent=2)


@mcp.tool()
def bigquery_query(sql: str, max_rows: int = 1000) -> str:
    """Run one bounded, read-only Standard SQL SELECT/WITH query against BigQuery."""
    return json.dumps(_bigquery_service().query(sql, max_rows=max_rows), indent=2, default=str)


@mcp.tool()
def bigquery_semantic_catalog(table: str) -> str:
    """Convert a BigQuery table schema into a DashboardSpec semantic catalog."""
    return json.dumps(_bigquery_service().catalog(table).model_dump(), indent=2)


@mcp.tool()
def bigquery_create_powerbi_semantic_model(
    table: str,
    storage_mode: Literal["import", "directQuery"] = "directQuery",
) -> str:
    """Create a local PBIP semantic model. storage_mode is exactly import or directQuery."""
    result = _bigquery_service().create_powerbi_model(
        table,
        AUTHORING_ROOT / ".bigquery-models",
        storage_mode=storage_mode,
    )
    return json.dumps({
        **result.to_dict(),
        "dataset_reference_path": f"../{Path(result.semantic_model_path).name}",
        "next_action": (
            "In DashboardSpec set dataset.path to dataset_reference_path (relative). "
            "Pass semantic_model_path separately to create_dashboard_workspace and pass "
            "the exact catalog returned by this tool. "
            "Power BI Desktop may require one-time Google data-source sign-in."
        ),
    }, indent=2)


def _allowed_authoring_path(value: str) -> Path:
    candidate = Path(value)
    if not candidate.is_absolute():
        candidate = AUTHORING_ROOT / candidate
    candidate = candidate.resolve()
    try:
        candidate.relative_to(AUTHORING_ROOT)
    except ValueError as exc:
        raise ValueError(
            f"path must remain under POWERBI_AUTHORING_ROOT: {AUTHORING_ROOT}"
        ) from exc
    return candidate


@mcp.tool()
def validate_dashboard_spec(spec: DashboardSpec) -> str:
    """Validate a dashboard specification without writing files."""
    dashboard = spec
    layout_errors = [
        f"{page.name}: {error}"
        for page in dashboard.pages
        for error in validate_page_layout(page)
    ]
    return json.dumps({
        "valid": not layout_errors,
        "layout_errors": layout_errors,
        "normalized_spec": dashboard.model_dump(by_alias=True),
    }, indent=2)


@mcp.tool()
def stage_pbir_report(spec: DashboardSpec) -> str:
    """Compile a dashboard specification into an isolated PBIR change set."""
    result = compile_report(spec, AUTHORING_ROOT / ".pbir-staging")
    return json.dumps(result.to_dict(), indent=2)


@mcp.tool()
def validate_pbir_report(project_path: str) -> str:
    """Structurally validate an enhanced PBIR report project."""
    report = validate_pbir_project(_allowed_authoring_path(project_path))
    return json.dumps(report.to_dict(), indent=2)


@mcp.tool()
def inspect_pbir_report(project_path: str) -> str:
    """List pages and visuals in an enhanced PBIR report project."""
    result = inspect_pbir_project(_allowed_authoring_path(project_path))
    return json.dumps(result, indent=2)



@mcp.tool()
def validate_dashboard_semantics(spec: DashboardSpec, catalog: SemanticModelCatalog) -> str:
    """Validate every visual field against a semantic-model catalog."""
    from report_authoring.semantic import validate_dashboard_semantics as run
    issues = run(spec, catalog)
    return json.dumps({
        "valid": not any(item.severity == "error" for item in issues),
        "issues": [item.to_dict() for item in issues],
    }, indent=2)


@mcp.tool()
def evaluate_dashboard_quality(spec: DashboardSpec) -> str:
    """Run report density, sizing, and readability diagnostics."""
    from report_authoring.quality import evaluate_report_quality
    issues = evaluate_report_quality(spec)
    return json.dumps({
        "valid": not any(item.severity == "error" for item in issues),
        "issues": [item.to_dict() for item in issues],
    }, indent=2)


@mcp.tool()
def validate_pbir_official_schemas(
    project_path: str,
    allow_schema_download: bool = False,
) -> str:
    """Validate report documents against allowlisted Microsoft PBIR schemas."""
    report = validate_pbir_project(
        _allowed_authoring_path(project_path),
        official_schemas=True,
        allow_schema_download=allow_schema_download,
        schema_cache=AUTHORING_ROOT / ".pbir-schema-cache",
    )
    return json.dumps(report.to_dict(), indent=2)


@mcp.tool()
def preview_pbir_report(project_path: str) -> str:
    """Return a deterministic page and visual preview manifest."""
    from report_authoring.preview import build_preview_manifest
    return json.dumps(
        build_preview_manifest(_allowed_authoring_path(project_path)),
        indent=2,
    )


@mcp.tool()
def prepare_pbir_for_powerbi_desktop(
    project_path: str,
    semantic_model_path: str,
) -> str:
    """Bind a staged PBIR report to a local PBIP semantic model folder."""
    from report_authoring.desktop import prepare_report_for_desktop

    result = prepare_report_for_desktop(
        _allowed_authoring_path(project_path), semantic_model_path
    )
    return json.dumps(result.to_dict(), indent=2)


@mcp.tool()
def open_pbir_in_powerbi_desktop(project_path: str) -> str:
    """Open a validated staged PBIR report in the installed Power BI Desktop app."""
    from report_authoring.desktop import open_report_in_powerbi_desktop

    opened = open_report_in_powerbi_desktop(_allowed_authoring_path(project_path))
    return json.dumps({"opened": True, "pbir_path": opened}, indent=2)


def _dashboard_manager():
    from report_authoring.workspace import DashboardWorkspaceManager

    return DashboardWorkspaceManager(AUTHORING_ROOT / ".dashboard-workspaces")


def _qa_workspace_response(operation) -> str:
    from report_authoring.qa import DashboardQARejected

    try:
        result = operation()
    except DashboardQARejected as exc:
        return json.dumps({
            "accepted": False,
            "candidate_manifest_path": exc.candidate_manifest_path,
            "qa": exc.report.to_dict(),
            "next_action": (
                "revise the DashboardSpec from blocking findings and retry"
                if exc.report.status == "NEEDS_REVISION"
                else "stop automatic retries and request human review"
            ),
        }, indent=2)
    return json.dumps({"accepted": True, **result.to_dict()}, indent=2)


@mcp.tool()
def create_dashboard_workspace(
    spec: DashboardSpec,
    semantic_model_path: str = "",
    dashboard_id: str = "",
    catalog: SemanticModelCatalog | None = None,
    reason: str = "Initial dashboard",
) -> str:
    """Create a persistent dashboard. IDs are normalized and collisions get a new ID."""
    manager = _dashboard_manager()
    normalized_id = ""
    if dashboard_id:
        normalized_id = re.sub(
            r"[^a-z0-9]+", "-", dashboard_id.casefold()
        ).strip("-")[:80] or "dashboard"
        if (manager.root / normalized_id / "dashboard.json").is_file():
            normalized_id = ""
    return _qa_workspace_response(lambda: manager.create(
        spec,
        semantic_model_path=semantic_model_path or None,
        dashboard_id=normalized_id or None,
        catalog=catalog,
        reason=reason,
    ))


@mcp.tool()
def get_active_dashboard(dashboard_id: str = "") -> str:
    """Load the active dashboard's canonical spec, build, and version metadata."""
    return json.dumps(_dashboard_manager().get(dashboard_id or None), indent=2)


@mcp.tool()
def set_active_dashboard(dashboard_id: str) -> str:
    """Select which persistent dashboard subsequent revision requests target."""
    return json.dumps(_dashboard_manager().set_active(dashboard_id), indent=2)


@mcp.tool()
def audit_active_dashboard(
    dashboard_id: str = "",
    catalog: SemanticModelCatalog | None = None,
) -> str:
    """Audit the active dashboard before an autonomous revision."""
    result = _dashboard_manager().audit(
        dashboard_id or None,
        catalog,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def revise_active_dashboard(
    spec: DashboardSpec,
    reason: str,
    expected_version: int,
    dashboard_id: str = "",
    catalog: SemanticModelCatalog | None = None,
) -> str:
    """Validate and compile a new immutable version of the active dashboard."""
    return _qa_workspace_response(lambda: _dashboard_manager().revise(
        spec,
        reason=reason,
        expected_version=expected_version,
        dashboard_id=dashboard_id or None,
        catalog=catalog,
    ))


@mcp.tool()
def list_dashboard_versions(dashboard_id: str = "") -> str:
    """List immutable versions for the active or selected dashboard."""
    return json.dumps(
        _dashboard_manager().list_versions(dashboard_id or None), indent=2
    )


@mcp.tool()
def rollback_dashboard(
    target_version: int,
    dashboard_id: str = "",
    catalog: Dict[str, Any] | None = None,
) -> str:
    """Restore an earlier spec through the same runtime QA admission loop."""
    from report_authoring.semantic import SemanticModelCatalog

    return _qa_workspace_response(lambda: _dashboard_manager().rollback(
        target_version,
        dashboard_id or None,
        SemanticModelCatalog.model_validate(catalog) if catalog else None,
    ))


@mcp.tool()
def open_active_dashboard_in_powerbi_desktop(
    dashboard_id: str = "",
    semantic_model_path: str = "",
) -> str:
    """Open the active dashboard version in Desktop using its saved model link."""
    result = _dashboard_manager().open_active_in_desktop(
        dashboard_id or None, semantic_model_path or None
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def check_powerbi_cloud_qa_readiness() -> str:
    """Check cloud publishing separately from capacity-dependent visual QA."""
    from report_authoring.cloud import CloudConfig

    vision_provider = os.getenv("POWERBI_VISION_PROVIDER", os.getenv("LLM_PROVIDER", "gemini")).lower()
    vision_key_name = {
        "openai": "OPENAI_API_KEY",
        "anthropic": "ANTHROPIC_API_KEY",
        "gemini": "GEMINI_API_KEY",
    }.get(vision_provider, "")
    has_client_credentials = all(os.getenv(name) for name in (
        "AZURE_TENANT_ID", "AZURE_CLIENT_ID", "AZURE_CLIENT_SECRET"
    ))
    checks = {
        "workspace_id": bool(os.getenv("POWERBI_STAGING_WORKSPACE_ID")),
        "fabric_auth": bool(os.getenv("FABRIC_API_ACCESS_TOKEN")) or has_client_credentials,
        "powerbi_auth": bool(os.getenv("POWERBI_API_ACCESS_TOKEN")) or has_client_credentials,
        "vision_provider": vision_provider,
        "vision_model": bool(os.getenv("POWERBI_VISION_MODEL") or os.getenv("LLM_MODEL")),
        "vision_api_key": bool(vision_key_name and os.getenv(vision_key_name)),
    }
    license_mode = os.getenv("POWERBI_CLOUD_LICENSE_MODE", "capacity").strip().lower()
    rendering_supported = CloudConfig(
        workspace_id=os.getenv("POWERBI_STAGING_WORKSPACE_ID", "") or "not-configured",
        license_mode=license_mode,
    ).supports_export_to_file
    publishing_required = ["workspace_id", "fabric_auth"]
    rendering_required = ["workspace_id", "powerbi_auth", "vision_model", "vision_api_key"]
    publishing_ready = all(bool(checks[item]) for item in publishing_required)
    visual_qa_ready = rendering_supported and all(
        bool(checks[item]) for item in rendering_required
    )
    return json.dumps({
        "ready": publishing_ready,
        "publishing_ready": publishing_ready,
        "visual_qa_ready": visual_qa_ready,
        "license_mode": license_mode,
        "rendering_supported": rendering_supported,
        "limitations": ([] if rendering_supported else [
            "Power BI Pro/PPU supports cloud report publication, but not the "
            "ExportToFile API used for PNG rendering and automated visual QA."
        ]),
        "checks": checks,
    }, indent=2)


@mcp.tool()
def run_full_autonomous_agent_qualification(
    max_visual_attempts: int = 3,
) -> str:
    """Provision synthetic Fabric assets and qualify the complete cloud QA path."""
    from report_authoring.qualification import run_full_agent_qualification

    return json.dumps(run_full_agent_qualification(max_visual_attempts), indent=2)

@mcp.tool()
def list_powerbi_visual_capabilities() -> str:
    """List supported native Power BI visuals and their accepted field roles."""
    return json.dumps({"visuals": list_visual_capabilities()}, indent=2)


@mcp.tool()
def list_powerbi_cloud_semantic_models() -> str:
    """List semantic models in the configured Power BI cloud workspace."""
    from report_authoring.cloud import CloudConfig, PowerBICloudClient

    models = PowerBICloudClient(CloudConfig.from_env()).list_semantic_models()
    return json.dumps({"semantic_models": models}, indent=2)


@mcp.tool()
def get_powerbi_cloud_semantic_catalog(semantic_model_id: str) -> str:
    """Read tables, columns, and measures from a cloud semantic model."""
    from report_authoring.cloud import CloudConfig, PowerBICloudClient

    catalog = PowerBICloudClient(CloudConfig.from_env()).semantic_catalog(
        semantic_model_id
    )
    return catalog.model_dump_json(indent=2)


@mcp.tool()
def execute_powerbi_cloud_dax(
    semantic_model_id: str,
    query: str,
    include_nulls: bool = True,
) -> str:
    """Execute one read-only DAX query against a Power BI cloud model."""
    from report_authoring.cloud import CloudConfig, PowerBICloudClient

    result = PowerBICloudClient(CloudConfig.from_env()).execute_dax(
        semantic_model_id,
        query,
        include_nulls=include_nulls,
    )
    return json.dumps(result, indent=2)


@mcp.tool()
def publish_pbir_to_fabric(
    project_path: str,
    display_name: str,
    semantic_model_id: str = "",
    report_id: str = "",
) -> str:
    """Create or update a report in the configured Fabric staging workspace."""
    from report_authoring.cloud import CloudConfig, FabricReportPublisher

    result = FabricReportPublisher(CloudConfig.from_env()).publish(
        _allowed_authoring_path(project_path),
        display_name=display_name,
        semantic_model_id=semantic_model_id or None,
        report_id=report_id or None,
    )
    return json.dumps(result.to_dict(), indent=2)


@mcp.tool()
def render_powerbi_report(
    report_id: str,
    page_names: List[str] | None = None,
    locale: str = "en-US",
) -> str:
    """Render report pages as PNG; requires a capacity-backed workspace."""
    from report_authoring.cloud import CloudConfig, PowerBIExportRenderer

    output = AUTHORING_ROOT / ".pbir-previews" / report_id / uuid.uuid4().hex
    result = PowerBIExportRenderer(CloudConfig.from_env()).render_report(
        report_id,
        output,
        page_names=page_names or None,
        locale=locale,
    )
    return json.dumps(result.to_dict(), indent=2)


@mcp.tool()
def review_powerbi_render(
    artifact_paths: List[str],
    project_path: str,
    provider: str = "",
    model: str = "",
) -> str:
    """Let the configured multimodal model inspect rendered Power BI screenshots."""
    from report_authoring.preview import build_preview_manifest
    from report_authoring.visual_review import review_rendered_report

    images = [_allowed_authoring_path(value) for value in artifact_paths]
    manifest = build_preview_manifest(_allowed_authoring_path(project_path))
    review = review_rendered_report(
        images,
        manifest,
        provider=provider or None,
        model=model or None,
    )
    return json.dumps(review.to_dict(), indent=2)


@mcp.tool()
def decide_powerbi_visual_qa_iteration(
    review: Dict[str, Any],
    attempt: int,
    max_attempts: int = 3,
) -> str:
    """Apply the bounded retry policy to structured visual-review findings."""
    from report_authoring.visual_review import VisualReview, decide_visual_qa_iteration

    decision = decide_visual_qa_iteration(
        VisualReview.model_validate(review), attempt, max_attempts
    )
    return json.dumps(decision.model_dump(), indent=2)

if __name__ == "__main__":
    mcp.run()
