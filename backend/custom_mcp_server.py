import sys
import json
import os
import subprocess
import uuid
import re
import time
from typing import Dict, Any, List

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
    temp_filename = os.path.join(root_dir, f"temp_sandbox_{uuid.uuid4().hex}.py")
    
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
    validate_pbir_project,
)
from report_authoring.layout import validate_page_layout

AUTHORING_ROOT = Path(
    os.getenv("POWERBI_AUTHORING_ROOT", Path(__file__).resolve().parent.parent)
).resolve()


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
def validate_dashboard_spec(spec: Dict[str, Any]) -> str:
    """Validate a dashboard specification without writing files."""
    dashboard = DashboardSpec.model_validate(spec)
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
def stage_pbir_report(spec: Dict[str, Any]) -> str:
    """Compile a dashboard specification into an isolated PBIR change set."""
    dashboard = DashboardSpec.model_validate(spec)
    result = compile_report(dashboard, AUTHORING_ROOT / ".pbir-staging")
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
def validate_dashboard_semantics(spec: Dict[str, Any], catalog: Dict[str, Any]) -> str:
    """Validate every visual field against a semantic-model catalog."""
    from report_authoring.semantic import SemanticModelCatalog, validate_dashboard_semantics as run
    dashboard = DashboardSpec.model_validate(spec)
    issues = run(dashboard, SemanticModelCatalog.model_validate(catalog))
    return json.dumps({
        "valid": not any(item.severity == "error" for item in issues),
        "issues": [item.to_dict() for item in issues],
    }, indent=2)


@mcp.tool()
def evaluate_dashboard_quality(spec: Dict[str, Any]) -> str:
    """Run report density, sizing, and readability diagnostics."""
    from report_authoring.quality import evaluate_report_quality
    issues = evaluate_report_quality(DashboardSpec.model_validate(spec))
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
def check_powerbi_cloud_qa_readiness() -> str:
    """Check cloud publishing, PNG rendering, and visual-review configuration."""
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
    required = ["workspace_id", "fabric_auth", "powerbi_auth", "vision_model", "vision_api_key"]
    return json.dumps({
        "ready": all(bool(checks[item]) for item in required),
        "checks": checks,
    }, indent=2)


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
    """Render a staged Fabric report to real Power BI PNG screenshots."""
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
