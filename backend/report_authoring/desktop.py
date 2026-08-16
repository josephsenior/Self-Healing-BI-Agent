from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .pbir import _report_root, validate_pbir_project
from .models import DashboardSpec, FieldRef


SEMANTIC_MODEL_DEFINITION_SCHEMA = (
    "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/"
    "definitionProperties/1.0.0/schema.json"
)


@dataclass(frozen=True)
class DesktopHandoffResult:
    report_path: str
    pbir_path: str
    semantic_model_path: str
    relative_model_path: str
    validation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _synthetic_data_type(field: FieldRef) -> tuple[str, str]:
    name = field.name.casefold()
    if "date" in name or "time" in name:
        return "dateTime", "date"
    if any(token in name for token in ("quantity", "count", "number", "units")):
        return "int64", "Int64.Type"
    if any(token in name for token in ("revenue", "amount", "price", "cost", "sales", "profit")):
        return "double", "number"
    return "string", "text"


def _m_identifier(value: str) -> str:
    return '#"' + value.replace('"', '""') + '"'


def _synthetic_value(field: FieldRef, row: int) -> str:
    data_type, _ = _synthetic_data_type(field)
    if data_type == "dateTime":
        return f"#date(2026, {(row % 6) + 1}, {(row * 3 % 27) + 1})"
    if data_type == "int64":
        return str((row + 1) * 7)
    if data_type == "double":
        return f"{(row + 1) * 425.5:.2f}"
    samples = {
        "region": ["North", "South", "East", "West", "North", "South"],
        "product": ["Alpha", "Beta", "Gamma", "Delta", "Beta", "Alpha"],
    }
    values = samples.get(field.name.casefold())
    value = values[row % len(values)] if values else f"{field.name} {row + 1}"
    return '"' + value.replace('"', '""') + '"'


def _synthetic_model(spec: DashboardSpec | None) -> dict[str, Any]:
    grouped: dict[str, dict[tuple[str, str], FieldRef]] = {}
    if spec is not None:
        for page in spec.pages:
            for visual in page.visuals:
                for fields in visual.resolved_fields().values():
                    for field in fields:
                        grouped.setdefault(field.table, {})[(field.name, field.kind)] = field

    tables = []
    for table_name, field_map in sorted(grouped.items()):
        fields = list(field_map.values())
        source_fields = [
            (field, f"__{field.name}_Value" if field.kind == "measure" else field.name)
            for field in fields
        ]
        type_fields = ", ".join(
            f"{_m_identifier(source_name)} = {_synthetic_data_type(field)[1]}"
            for field, source_name in source_fields
        )
        rows = [
            "        {" + ", ".join(
                _synthetic_value(field, row) for field, _ in source_fields
            ) + "}"
            for row in range(6)
        ]
        expression = [
            "let",
            f"    Source = #table(type table [{type_fields}],",
            "    {",
            ",\n".join(rows),
            "    })",
            "in",
            "    Source",
        ]
        columns = []
        measures = []
        for field, source_name in source_fields:
            data_type, _ = _synthetic_data_type(field)
            column = {
                "name": source_name,
                "dataType": data_type,
                "sourceColumn": source_name,
                "summarizeBy": (
                    "sum"
                    if field.kind == "column" and data_type in {"int64", "double"}
                    else "none"
                ),
            }
            if field.kind == "measure":
                column["isHidden"] = True
            if data_type == "dateTime":
                column["formatString"] = "yyyy-MM-dd"
            columns.append(column)
            if field.kind == "measure":
                dax_table = table_name.replace("'", "''")
                dax_column = source_name.replace("]", "]]")
                measures.append({
                    "name": field.name,
                    "expression": f"SUM('{dax_table}'[{dax_column}])",
                })
        table = {
            "name": table_name,
            "description": "Deterministic synthetic qualification data",
            "columns": columns,
            "partitions": [{
                "name": table_name,
                "mode": "import",
                "source": {"type": "m", "expression": expression},
            }],
        }
        if measures:
            table["measures"] = measures
        tables.append(table)

    return {
        "name": "Synthetic Qualification Model",
        "compatibilityLevel": 1600,
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "discourageImplicitMeasures": False,
            "tables": tables,
        },
    }


def ensure_staging_semantic_model(
    dashboard_root: str | Path,
    spec: DashboardSpec | None = None,
) -> Path:
    """Create a valid, populated synthetic TMSL model for Desktop qualification."""
    root = Path(dashboard_root).resolve()
    model_dir = root / "Staging.SemanticModel"
    model_dir.mkdir(parents=True, exist_ok=True)
    pbism_file = model_dir / "definition.pbism"
    pbism_file.write_text(
        json.dumps({
            "$schema": SEMANTIC_MODEL_DEFINITION_SCHEMA,
            "version": "4.2",
            "settings": {"qnaEnabled": True},
        }, indent=2) + "\n",
        encoding="utf-8",
    )
    (model_dir / "model.bim").write_text(
        json.dumps(_synthetic_model(spec), indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    return model_dir


def _semantic_model_root(value: str | Path) -> Path:
    path = Path(value).resolve()
    if path.is_file() and path.name == "definition.pbism":
        path = path.parent
    definition = path / "definition.pbism"
    if not definition.is_file():
        raise ValueError(
            "semantic_model_path must identify a Power BI Project "
            ".SemanticModel folder containing definition.pbism"
        )
    return path


def prepare_report_for_desktop(
    report_path: str | Path,
    semantic_model_path: str | Path,
) -> DesktopHandoffResult:
    """Rebind a staged report to a local PBIP semantic model for Desktop."""
    report_root = _report_root(report_path)
    model_root = _semantic_model_root(semantic_model_path)
    try:
        relative = os.path.relpath(model_root, report_root).replace("\\", "/")
    except ValueError as exc:
        raise ValueError(
            "the report and semantic model must be on the same Windows drive"
        ) from exc

    pbir_path = report_root / "definition.pbir"
    definition = json.loads(pbir_path.read_text(encoding="utf-8"))
    definition["datasetReference"] = {"byPath": {"path": relative}}
    pbir_path.write_text(
        json.dumps(definition, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    validation = validate_pbir_project(report_root)
    if not validation.valid:
        raise ValueError(f"Desktop report preparation failed validation: {validation.to_dict()}")
    return DesktopHandoffResult(
        report_path=str(report_root),
        pbir_path=str(pbir_path),
        semantic_model_path=str(model_root),
        relative_model_path=relative,
        validation=validation.to_dict(),
    )


def open_report_in_powerbi_desktop(report_path: str | Path) -> str:
    """Open a validated PBIR report through the Windows file association."""
    report_root = _report_root(report_path)
    pbir_path = report_root / "definition.pbir"
    validation = validate_pbir_project(report_root)
    if not validation.valid:
        raise ValueError(f"refusing to open invalid PBIR report: {validation.to_dict()}")
    if not hasattr(os, "startfile"):
        raise RuntimeError("Power BI Desktop launch is supported only on Windows")
    project_path = report_root.parent / f"{report_root.name.removesuffix('.Report')}.pbip"
    launch_path = project_path if project_path.is_file() else pbir_path
    os.startfile(str(launch_path))
    return str(launch_path)


def refresh_open_powerbi_model(
    opened_after_unix_ms: int,
    verification_table: str,
    timeout_seconds: int = 90,
) -> dict[str, Any]:
    """Process and verify the model opened by Power BI Desktop on Windows."""
    if os.name != "nt":
        raise RuntimeError("local Power BI model refresh is supported only on Windows")
    script = Path(__file__).with_name("refresh_powerbi_model.ps1")
    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-NonInteractive",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(script),
            "-OpenedAfterUnixMs",
            str(opened_after_unix_ms),
            "-VerificationTable",
            verification_table,
            "-TimeoutSeconds",
            str(timeout_seconds),
        ],
        capture_output=True,
        text=True,
        timeout=timeout_seconds + 15,
        check=False,
    )
    if completed.returncode != 0:
        detail = completed.stderr.strip() or completed.stdout.strip()
        raise RuntimeError(f"Power BI model refresh failed: {detail}")
    lines = [line for line in completed.stdout.splitlines() if line.strip()]
    if not lines:
        raise RuntimeError("Power BI model refresh returned no verification result")
    result = json.loads(lines[-1])
    if not result.get("processed"):
        raise RuntimeError(f"Power BI model was not processed: {result}")
    return result


def open_and_refresh_report_in_powerbi_desktop(
    report_path: str | Path,
    verification_table: str,
    timeout_seconds: int = 90,
) -> tuple[str, dict[str, Any]]:
    opened_after = time.time_ns() // 1_000_000
    opened = open_report_in_powerbi_desktop(report_path)
    refreshed = refresh_open_powerbi_model(
        opened_after,
        verification_table,
        timeout_seconds,
    )
    return opened, refreshed
