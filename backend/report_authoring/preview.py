from __future__ import annotations

import json
from dataclasses import asdict, dataclass, field
from pathlib import Path
from typing import Any, Protocol

from .pbir import _report_root


@dataclass(frozen=True)
class RenderResult:
    provider: str
    artifacts: list[str]
    warnings: list[str]
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class ReportRenderer(Protocol):
    def render(self, report_path: Path, output_path: Path) -> RenderResult: ...


def build_preview_manifest(path: str | Path) -> dict[str, Any]:
    root = _report_root(path)
    pages: list[dict[str, Any]] = []
    for page_file in sorted((root / "definition" / "pages").glob("*/page.json")):
        page = json.loads(page_file.read_text(encoding="utf-8"))
        visuals: list[dict[str, Any]] = []
        for visual_file in sorted((page_file.parent / "visuals").glob("*/visual.json")):
            visual = json.loads(visual_file.read_text(encoding="utf-8"))
            config = visual.get("visual", {})
            title_value = (
                config.get("visualContainerObjects", {})
                .get("title", [{}])[0]
                .get("properties", {})
                .get("text", {})
                .get("expr", {})
                .get("Literal", {})
                .get("Value", "")
            )
            visuals.append({
                "id": visual.get("name"),
                "type": config.get("visualType"),
                "title": title_value.strip("'"),
                "position": visual.get("position", {}),
                "roles": sorted(config.get("query", {}).get("queryState", {}).keys()),
            })
        pages.append({
            "id": page.get("name"),
            "display_name": page.get("displayName"),
            "width": page.get("width"),
            "height": page.get("height"),
            "visuals": visuals,
        })
    return {"report_root": str(root), "pages": pages}
