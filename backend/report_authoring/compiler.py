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
PBIP_SCHEMA = "https://developer.microsoft.com/json-schemas/fabric/pbip/pbipProperties/1.0.0/schema.json"


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


def _projection(
    field: FieldRef,
    *,
    aggregate_column: bool = False,
    agg_function: int = 0,
    active: bool | None = None,
) -> dict[str, Any]:
    _AGG_NAMES = {0: "Sum", 1: "Count", 2: "Min", 3: "Max", 4: "Average", 5: "DistinctCount"}
    if field.kind == "column" and aggregate_column:
        agg_name = _AGG_NAMES.get(agg_function, "Sum")
        expression = {
            "Aggregation": {
                "Expression": _field_expression(field),
                "Function": agg_function,
            }
        }
        query_ref = f"{agg_name}({field.query_ref})"
        native_query_ref = f"{agg_name} of {field.name}"
    else:
        expression = _field_expression(field)
        query_ref = field.query_ref
        native_query_ref = field.name
    value: dict[str, Any] = {
        "field": expression,
        "queryRef": query_ref,
        "nativeQueryRef": native_query_ref,
    }
    if active is not None:
        value["active"] = active
    return value


def _detect_agg_function(field: FieldRef) -> int:
    """Detect aggregation function from field name: DistinctCount for IDs, Sum otherwise."""
    name_lower = field.name.lower()
    if name_lower.endswith("_id") or name_lower == "id":
        return 5  # DistinctCount
    if field.kind == "measure":
        return -1  # No aggregation for measures
    return 0  # Sum


def _query_state(spec: VisualSpec) -> dict[str, Any]:
    capability = spec.capability()
    aggregate_roles = {
        role.query_role
        for role in capability.roles.values()
        if role.field_kind != "column"
    }
    if capability.family in {"table", "filter", "custom", "canvas"}:
        aggregate_roles.clear()
    return {
        role: {
            "projections": [
                _projection(
                    item,
                    aggregate_column=role in aggregate_roles,
                    agg_function=_detect_agg_function(item),
                    active=True
                    if role == "Values" and spec.visual_type == "slicer"
                    else None,
                )
                for item in items
            ]
        }
        for role, items in spec.resolved_fields().items()
    }


def _literal_expression(value: str) -> dict[str, Any]:
    escaped = "'" + value.replace("'", "''") + "'"
    return {"expr": {"Literal": {"Value": escaped}}}


def _color_expression(value: str) -> dict[str, Any]:
    """Return the PBIR expression shape used by color properties."""
    return {"solid": {"color": _literal_expression(value)}}


def _boolean_expression(value: bool) -> dict[str, Any]:
    return {"expr": {"Literal": {"Value": str(value).lower()}}}


def _title_objects(title: str, font_color: str) -> dict[str, Any]:
    return {
        "title": [{
            "properties": {
                "show": _boolean_expression(True),
                "text": _literal_expression(title),
                "fontColor": _color_expression(font_color),
            }
        }]
    }


SERIES_COLOR_TYPES = {
    "barChart", "clusteredBarChart", "stackedBarChart",
    "hundredPercentStackedBarChart", "clusteredColumnChart",
    "stackedColumnChart", "hundredPercentStackedColumnChart",
    "lineChart", "areaChart", "stackedAreaChart", "ribbonChart",
    "pieChart", "donutChart", "funnel",
    "lineStackedColumnComboChart", "lineClusteredColumnComboChart",
    "scatterChart", "treemap", "waterfallChart", "gauge",
}
CALLOUT_COLOR_TYPES = {"card", "multiRowCard", "kpi"}


def _visual_objects(spec: VisualSpec) -> dict[str, Any] | None:
    if spec.visual_type == "textbox":
        return {"general": [{"properties": {"paragraphs": [{
            "textRuns": [{"value": spec.content, "textStyle": {
                "fontSize": f"{spec.font_size}pt", "color": spec.font_color,
            }}],
            "horizontalTextAlignment": spec.text_alignment,
        }]}}]}
    if spec.visual_type == "basicShape":
        objects: dict[str, Any] = {"shape": [{"properties": {
            "tileShape": _literal_expression(spec.shape_type),
        }}], "fill": [{"properties": {
            "fillColor": _color_expression(spec.font_color),
        }, "selector": {"id": "default"}}], "outline": [{"properties": {
            "show": _boolean_expression(False),
        }, "selector": {"id": "default"}}]}
        if spec.content:
            objects["text"] = [
                {"properties": {"show": _boolean_expression(True)}},
                {"properties": {
                    "text": _literal_expression(spec.content),
                    "fontColor": _color_expression(spec.font_color),
                }, "selector": {"id": "default"}},
            ]
        return objects
    if spec.visual_type == "actionButton":
        return {"fill": [
            {"properties": {}},
            {"properties": {
                "fillColor": _color_expression(spec.font_color),
            }, "selector": {"id": "default"}},
        ], "text": [
            {"properties": {"show": _boolean_expression(True)}},
            {"properties": {
                "text": _literal_expression(spec.content or spec.title),
                "fontColor": _color_expression(spec.font_color),
                "fontSize": {"expr": {"Literal": {"Value": f"{spec.font_size}D"}}},
                "horizontalAlignment": _literal_expression(spec.text_alignment),
            }, "selector": {"id": "default"}},
        ]}
    if spec.visual_type == "image" and spec.image_url:
        return {"general": [{"properties": {
            "imageUrl": _literal_expression(spec.image_url),
        }}]}
    if spec.visual_type in CALLOUT_COLOR_TYPES:
        # Card callout values do not inherit the textbox text style.  They
        # require the native cardVisual formatting object explicitly.
        return {"calloutValue": [{"properties": {
            "color": _color_expression(spec.font_color),
        }}]}
    if spec.visual_type in SERIES_COLOR_TYPES:
        # dataPoint.fill is the native PBIR series color override.  Setting
        # dataLabels as well keeps labels legible when a custom palette is
        # requested by the dashboard specification.
        return {"dataPoint": [{"properties": {
            "fill": _color_expression(spec.font_color),
        }}], "dataLabels": [{"properties": {
            "color": _color_expression(spec.font_color),
        }}]}
    return None


def _container_objects(
    spec: VisualSpec,
    page_targets: dict[str, str],
) -> dict[str, Any] | None:
    if spec.visual_type != "actionButton":
        return None if spec.visual_type in {"textbox", "basicShape", "image"} else _title_objects(spec.title, spec.font_color)
    action = spec.action
    properties = {
        "show": _boolean_expression(True),
        "type": _literal_expression(
            "WebUrl" if action.action_type == "webUrl" else "PageNavigation"
        ),
    }
    if action.action_type == "webUrl":
        properties["webUrl"] = _literal_expression(action.target)
    else:
        properties["navigationSection"] = _literal_expression(
            page_targets[action.target.casefold()]
        )
    if action.tooltip:
        properties["tooltip"] = _literal_expression(action.tooltip)
    return {"visualLink": [{"properties": properties}]}


def _compile_visual(
    spec: VisualSpec,
    visual_id: str,
    pixel: Any,
    page_targets: dict[str, str],
) -> dict[str, Any]:
    visual: dict[str, Any] = {
        "visualType": {
            "card": "cardVisual",
            "basicShape": "shape",
        }.get(spec.visual_type, spec.visual_type),
        "drillFilterOtherVisuals": True,
    }
    query_state = _query_state(spec)
    if query_state:
        visual["query"] = {"queryState": query_state}
    objects = _visual_objects(spec)
    if objects:
        visual["objects"] = objects
    container_objects = _container_objects(spec, page_targets)
    if container_objects:
        visual["visualContainerObjects"] = container_objects
    return {
        "$schema": VISUAL_SCHEMA,
        "name": visual_id,
        "position": {
            "x": pixel.x, "y": pixel.y, "z": pixel.z,
            "height": pixel.height, "width": pixel.width,
            "tabOrder": pixel.tab_order,
        },
        "visual": visual,
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

    _write_json(change_root / f"{report_name}.pbip", {
        "$schema": PBIP_SCHEMA,
        "version": "1.0",
        "artifacts": [{"report": {"path": f"{report_name}.Report"}}],
        "settings": {"enableAutoRecovery": True},
    })
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
    page_targets = {
        page.name.casefold(): page_id
        for page, page_id in zip(spec.pages, page_ids)
    }
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
                _compile_visual(visual, visual_id, pixel, page_targets),
            )

    files = sorted(
        str(path.relative_to(change_root)).replace("\\", "/")
        for path in change_root.rglob("*")
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
