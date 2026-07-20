from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from .layout import grid_to_pixels
from .models import DashboardSpec


@dataclass(frozen=True)
class QualityIssue:
    severity: str
    code: str
    message: str
    page: str = ""
    visual: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def evaluate_report_quality(spec: DashboardSpec) -> list[QualityIssue]:
    issues: list[QualityIssue] = []
    for page in spec.pages:
        if len(page.visuals) > 12:
            issues.append(QualityIssue(
                "warning", "visual_density",
                f"page contains {len(page.visuals)} visuals; target 12 or fewer",
                page.name,
            ))
        slicers = sum(item.visual_type == "slicer" for item in page.visuals)
        if slicers > 4:
            issues.append(QualityIssue(
                "warning", "slicer_density",
                f"page contains {slicers} slicers; target 4 or fewer",
                page.name,
            ))
        if not any(item.visual_type == "card" for item in page.visuals):
            issues.append(QualityIssue(
                "info", "no_kpi_card",
                "page has no KPI card; confirm this is intentional",
                page.name,
            ))
        for index, visual in enumerate(page.visuals):
            pixel = grid_to_pixels(visual.position, page_width=page.width, index=index)
            if len(visual.title) > 60:
                issues.append(QualityIssue(
                    "warning", "long_title",
                    "visual title is longer than 60 characters",
                    page.name, visual.title,
                ))
            if pixel.width < 180 or pixel.height < 96:
                issues.append(QualityIssue(
                    "warning", "small_visual",
                    f"visual is only {pixel.width}x{pixel.height} pixels",
                    page.name, visual.title,
                ))
            if visual.visual_type in {"barChart", "clusteredColumnChart", "lineChart"}:
                if len(visual.values) > 4:
                    issues.append(QualityIssue(
                        "warning", "too_many_series",
                        "chart has more than four value series",
                        page.name, visual.title,
                    ))
    return issues
