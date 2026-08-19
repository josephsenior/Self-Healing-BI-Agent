from __future__ import annotations

from dataclasses import asdict, dataclass, replace
from typing import Literal

FieldKind = Literal["column", "measure", "any"]


@dataclass(frozen=True)
class RoleCapability:
    query_role: str
    min_fields: int = 0
    max_fields: int = 20
    field_kind: FieldKind = "any"


@dataclass(frozen=True)
class VisualCapability:
    visual_type: str
    family: str
    roles: dict[str, RoleCapability]
    min_total_fields: int = 1
    legacy_category_role: str | None = None
    legacy_values_role: str | None = None
    legacy_series_role: str | None = None
    configuration: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "visual_type": self.visual_type,
            "family": self.family,
            "min_total_fields": self.min_total_fields,
            "roles": {name: asdict(role) for name, role in self.roles.items()},
            "configuration": list(self.configuration),
        }


def role(query: str, minimum: int = 0, maximum: int = 20,
         kind: FieldKind = "any") -> RoleCapability:
    return RoleCapability(query, minimum, maximum, kind)


def capability(visual_type: str, family: str,
               roles: dict[str, RoleCapability],
               legacy: tuple[str | None, str | None, str | None] = (None, None, None),
               minimum: int = 1,
               configuration: tuple[str, ...] = ()) -> VisualCapability:
    return VisualCapability(visual_type, family, roles, minimum, *legacy, configuration)


CARTESIAN_ROLES = {
    "axis": role("Category", 1, kind="column"),
    "values": role("Y", 1),
    "legend": role("Series", maximum=1, kind="column"),
    "small_multiples": role("SmallMultiples", maximum=1, kind="column"),
    "tooltips": role("Tooltips"),
}
PART_TO_WHOLE_ROLES = {
    "category": role("Category", 1, kind="column"),
    "values": role("Y", 1),
    "tooltips": role("Tooltips"),
}

VISUAL_CAPABILITIES: dict[str, VisualCapability] = {}
for name in (
    "barChart", "clusteredBarChart", "stackedBarChart",
    "hundredPercentStackedBarChart", "clusteredColumnChart",
    "stackedColumnChart", "hundredPercentStackedColumnChart",
    "lineChart", "areaChart", "stackedAreaChart", "ribbonChart",
):
    VISUAL_CAPABILITIES[name] = capability(
        name, "cartesian", CARTESIAN_ROLES, ("axis", "values", "legend")
    )
for name in ("pieChart", "donutChart", "funnel"):
    VISUAL_CAPABILITIES[name] = capability(
        name, "part-to-whole", PART_TO_WHOLE_ROLES, ("category", "values", None)
    )

COMBO_ROLES = {
    "axis": role("Category", 1, kind="column"),
    "column_values": role("Y", 1), "line_values": role("Y2", 1),
    "column_legend": role("Series", maximum=1, kind="column"),
    "tooltips": role("Tooltips"),
}
for name in ("lineStackedColumnComboChart", "lineClusteredColumnComboChart"):
    VISUAL_CAPABILITIES[name] = capability(
        name, "combo", COMBO_ROLES, ("axis", "column_values", "column_legend")
    )

SPECIAL_VISUALS = {
    "waterfallChart": ("waterfall", {
        "category": role("Category", 1, kind="column"),
        "values": role("Y", 1, 1),
        "breakdown": role("Breakdown", maximum=1, kind="column"),
        "tooltips": role("Tooltips"),
    }, ("category", "values", "breakdown")),
    "treemap": ("part-to-whole", {
        "group": role("Group", 1, 1, "column"),
        "details": role("Details", maximum=1, kind="column"),
        "values": role("Values", 1), "tooltips": role("Tooltips"),
    }, ("group", "values", "details")),
    "scatterChart": ("distribution", {
        "x": role("X", 1, 1), "y": role("Y", 1, 1),
        "size": role("Size", maximum=1),
        "legend": role("Series", maximum=1, kind="column"),
        "details": role("Category", maximum=1, kind="column"),
        "play_axis": role("Play", maximum=1, kind="column"),
        "tooltips": role("Tooltips"),
    }, (None, None, None)),
    "tableEx": ("table", {
        "values": role("Values", 1), "tooltips": role("Tooltips"),
    }, (None, "values", None)),
    "pivotTable": ("matrix", {
        "rows": role("Rows", kind="column"),
        "columns": role("Columns", kind="column"), "values": role("Values"),
    }, ("rows", "values", None)),
    "card": ("card", {"value": role("Data", 1, 1)}, (None, "value", None)),
    "multiRowCard": ("card", {"values": role("Values", 1)}, (None, "values", None)),
    "kpi": ("indicator", {
        "indicator": role("Indicator", 1, 1),
        "trend_axis": role("TrendAxis", maximum=1, kind="column"),
        "target": role("Goal", maximum=1),
    }, (None, None, None)),
    "gauge": ("indicator", {
        "value": role("Y", 1, 1), "minimum": role("MinValue", maximum=1),
        "maximum": role("MaxValue", maximum=1),
        "target": role("TargetValue", maximum=1), "tooltips": role("Tooltips"),
    }, (None, "value", None)),
    "slicer": ("filter", {"field": role("Values", 1, 1, "column")},
               ("field", None, None)),
}
for name, (family, roles, legacy) in SPECIAL_VISUALS.items():
    VISUAL_CAPABILITIES[name] = capability(name, family, roles, legacy)

VISUAL_CAPABILITIES.update({
    "azureMap": capability("azureMap", "map", {
        "location": role("Location", maximum=1, kind="column"),
        "latitude": role("Latitude", maximum=1, kind="column"),
        "longitude": role("Longitude", maximum=1, kind="column"),
        "size": role("Size", maximum=1),
        "gradient": role("Gradient", maximum=1),
        "legend": role("Legend", maximum=1, kind="column"),
        "tooltips": role("Tooltips"),
    }),
    "shapeMap": capability("shapeMap", "map", {
        "location": role("Category", 1, 1, "column"),
        "value": role("Value", maximum=1),
        "legend": role("Series", maximum=1, kind="column"),
        "tooltips": role("Tooltips"),
    }),
    "decompositionTreeVisual": capability("decompositionTreeVisual", "ai", {
        "analyze": role("Analyze", 1, 1),
        "explain_by": role("ExplainBy", 1, kind="column"),
    }),
    "keyDriversVisual": capability("keyDriversVisual", "ai", {
        "target": role("Target", 1, 1),
        "explain_by": role("ExplainBy", 1),
        "expand_by": role("ExpandBy", maximum=1, kind="column"),
    }),
    "textbox": capability(
        "textbox", "canvas", {}, minimum=0,
        configuration=("content", "font_size", "font_color", "text_alignment"),
    ),
    "basicShape": capability(
        "basicShape", "canvas", {}, minimum=0,
        configuration=("shape_type", "content"),
    ),
    "actionButton": capability(
        "actionButton", "canvas", {}, minimum=0,
        configuration=("action", "content", "font_size", "text_alignment"),
    ),
    "image": capability("image", "canvas", {
        "image": role("Image", maximum=1, kind="column"),
    }, minimum=0, configuration=("image_url",)),
})

VISUAL_TYPES = tuple(VISUAL_CAPABILITIES)

# The compiler emits a native color override for every visual whose family
# supports a series or callout color.  Advertise font_color on those visuals so
# the agent knows a custom color can be requested for them.
_COLORABLE_FAMILIES = {
    "cartesian", "part-to-whole", "combo", "waterfall", "distribution",
    "card", "indicator",
}
for _name, _capability in list(VISUAL_CAPABILITIES.items()):
    if _capability.family in _COLORABLE_FAMILIES and "font_color" not in _capability.configuration:
        VISUAL_CAPABILITIES[_name] = replace(
            _capability,
            configuration=(*_capability.configuration, "font_color"),
        )


def get_visual_capability(visual_type: str) -> VisualCapability:
    try:
        return VISUAL_CAPABILITIES[visual_type]
    except KeyError as exc:
        raise ValueError(f"unsupported visual type: {visual_type}") from exc


def list_visual_capabilities() -> list[dict[str, object]]:
    return [VISUAL_CAPABILITIES[name].to_dict() for name in sorted(VISUAL_CAPABILITIES)]
