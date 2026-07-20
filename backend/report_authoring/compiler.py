from __future__ import annotations

import hashlib
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .layout import grid_to_pixels, validate_page_layout
from .models import DashboardSpec, FieldRef, VisualSpec
from .pbir import ValidationReport, validate_pbir_project

PBIR_PROPERTIES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definitionProperties/2.0.0/schema.json"
REPORT_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/report/3.1.0/schema.json"
VERSION_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/versionMetadata/1.0.0/schema.json"
PAGES_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/pagesMetadata/1.0.0/schema.json"
PAGE_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/page/2.0.0/schema.json"
VISUAL_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/item/report/definition/visualContainer/2.0.0/schema.json"


@dataclass(frozen=True)
class CompilationResult:
    change_set_id: str
    staging_path: str
    report_path: str
    files: list[str]
    validation: ValidationReport

    def to_dict(self) -> dict[str, Any]:
        return {
            "change_set_id": self.change_set_id,
            "staging_path": self.staging_path,
            "report_path": self.report_path,
            "files": self.files,
            "validation": self.validation.to_dict(),
        }


def _write_json(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def _identifier(seed: str) -> str:
    return hashlib.sha1(seed.encode("utf-8")).hexdigest()[:20]


def _safe_name(name: str) -> str:
    value = re.sub(r"[^A-Za-z0-9._-]+", "-", name).strip(".-")
    return value or "GeneratedReport"


def _field_expression(field: FieldRef) -> dict[str, Any]:
    key = "Measure" if field.kind == "measure" else "Column"
    return {
        key: {
            "Expression": {"SourceRef": {"Entity": field.table}},
            "Property": field.name,
        }
    }


def _projection(field: FieldRef, *, active: bool | None = None) -> dict[str, Any]:
    value: dict[str, Any] = {
        "field": _field_expression(field),
        "queryRef": field.query_ref,
    }
    if active is not None:
        value["active"] = active
    return value


def _query_state(spec: VisualSpec) -> dict[str, Any]:
    if spec.visual_type == "slicer":
        return {"Values": {"projections": [_projection(spec.category, active=True)]}}
    if spec.visual_type == "card":
        return {"Data": {"projections": [_projection(spec.values[0])]}}
    if spec.visual_type == "tableEx":
        return {"Values": {"projections": [_projection(item) for item in spec.values]}}

    state: dict[str, Any] = {
        "Category": {"projections": [_projection(spec.category, active=True)]},
        "Y": {"projections": [_projection(item) for item in spec.values]},
    }
    if spec.series:
        state["Series"] = {"projections": [_projection(spec.series)]}
    return state


def _title_objects(title: str) -> dict[str, Any]:
    literal = "'" + title.replace("'", "''") + "'"
    return {
        "title": [{
            "properties": {
                "show": {"expr": {"Literal": {"Value": "true"}}},
                "text": {"expr": {"Literal": {"Value": literal}}},
            }
        }]
    }


def _compile_visual(spec: VisualSpec, visual_id: str, pixel: Any) -> dict[str, Any]:
    return {
        "$schema": VISUAL_SCHEMA,
        "name": visual_id,
        "position": {
            "x": pixel.x, "y": pixel.y, "z": pixel.z,
            "height": pixel.height, "width": pixel.width,
            "tabOrder": pixel.tab_order,
        },
        "visual": {
            "visualType": spec.visual_type,
            "query": {"queryState": _query_state(spec)},
            "visualContainerObjects": _title_objects(spec.title),
            "drillFilterOtherVisuals": True,
        },
    }


def compile_report(
    spec: DashboardSpec,
    staging_root: str | Path | None = None,
) -> CompilationResult:
    layout_errors = [
        f"{page.name}: {error}"
        for page in spec.pages
        for error in validate_page_layout(page)
    ]
    if layout_errors:
        raise ValueError("invalid report layout: " + "; ".join(layout_errors))

    change_set_id = uuid.uuid4().hex
    default_root = Path(__file__).resolve().parents[2] / ".pbir-staging"
    staging = (Path(staging_root) if staging_root else default_root).resolve()
    change_root = staging / change_set_id
    change_root.mkdir(parents=True, exist_ok=False)

    report_name = _safe_name(spec.title)
    report_root = change_root / f"{report_name}.Report"
    definition = report_root / "definition"
    pages_root = definition / "pages"

    if spec.dataset.path:
        dataset_reference = {"byPath": {"path": spec.dataset.path}}
    else:
        dataset_reference = {
            "byConnection": {
                "connectionString": f"semanticmodelid={spec.dataset.semantic_model_id}"
            }
        }

    _write_json(report_root / "definition.pbir", {
        "$schema": PBIR_PROPERTIES_SCHEMA, "version": "4.0",
        "datasetReference": dataset_reference,
    })
    _write_json(definition / "report.json", {
        "$schema": REPORT_SCHEMA,
        "themeCollection": {
            "baseTheme": {
                "name": "CY25SU12",
                "reportVersionAtImport": {
                    "visual": "2.5.0", "report": "3.1.0", "page": "2.3.0"
                },
                "type": "SharedResources",
            }
        },
        "settings": {
            "useStylableVisualContainerHeader": True,
            "defaultFilterActionIsDataFilter": True,
            "defaultDrillFilterOtherVisuals": True,
            "allowChangeFilterTypes": True,
            "allowInlineExploration": True,
            "useEnhancedTooltips": True,
        },
        "slowDataSourceSettings": {
            "isCrossHighlightingDisabled": False,
            "isSlicerSelectionsButtonEnabled": False,
            "isFilterSelectionsButtonEnabled": False,
            "isFieldWellButtonEnabled": False,
            "isApplyAllButtonEnabled": False,
        },
    })
    _write_json(definition / "version.json", {
        "$schema": VERSION_SCHEMA, "version": "2.0.0",
    })

    page_ids = [_identifier(f"{spec.title}:page:{page.name}") for page in spec.pages]
    _write_json(pages_root / "pages.json", {
        "$schema": PAGES_SCHEMA,
        "pageOrder": page_ids,
        "activePageName": page_ids[0],
    })

    for page, page_id in zip(spec.pages, page_ids):
        page_root = pages_root / page_id
        _write_json(page_root / "page.json", {
            "$schema": PAGE_SCHEMA,
            "name": page_id,
            "displayName": page.display_name or page.name,
            "displayOption": page.display_option,
            "height": page.height,
            "width": page.width,
        })
        for index, visual in enumerate(page.visuals):
            visual_id = _identifier(
                f"{spec.title}:{page.name}:{visual.title}:{index}"
            )
            pixel = grid_to_pixels(
                visual.position, page_width=page.width, index=index
            )
            _write_json(
                page_root / "visuals" / visual_id / "visual.json",
                _compile_visual(visual, visual_id, pixel),
            )

    files = sorted(
        str(path.relative_to(change_root)).replace("\\", "/")
        for path in report_root.rglob("*")
        if path.is_file()
    )
    validation = validate_pbir_project(report_root)
    return CompilationResult(
        change_set_id=change_set_id,
        staging_path=str(change_root),
        report_path=str(report_root),
        files=files,
        validation=validation,
    )
