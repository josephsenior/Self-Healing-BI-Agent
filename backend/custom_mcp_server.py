import sys
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

if __name__ == "__main__":
    mcp.run()
