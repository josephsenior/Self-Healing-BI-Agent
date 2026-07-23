from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .pbir import _report_root, validate_pbir_project


@dataclass(frozen=True)
class DesktopHandoffResult:
    report_path: str
    pbir_path: str
    semantic_model_path: str
    relative_model_path: str
    validation: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def ensure_staging_semantic_model(dashboard_root: str | Path) -> Path:
    """Create a default staging .SemanticModel directory with definition.pbism if not present."""
    root = Path(dashboard_root).resolve()
    model_dir = root / "Staging.SemanticModel"
    model_dir.mkdir(parents=True, exist_ok=True)
    pbism_file = model_dir / "definition.pbism"
    if not pbism_file.exists():
        pbism_file.write_text(
            json.dumps({"$schema": "https://developer.microsoft.com/json-schemas/fabric/item/semanticModel/definition/1.0.0/schema.json"}, indent=2) + "\n",
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
    os.startfile(str(pbir_path))
    return str(pbir_path)
