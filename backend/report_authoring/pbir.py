from __future__ import annotations

import json
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any

from .schema_validation import validate_json_document


@dataclass(frozen=True)
class ValidationIssue:
    severity: str
    code: str
    message: str
    path: str = ""


@dataclass(frozen=True)
class ValidationReport:
    valid: bool
    issues: list[ValidationIssue]
    page_count: int = 0
    visual_count: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "valid": self.valid,
            "issues": [asdict(issue) for issue in self.issues],
            "page_count": self.page_count,
            "visual_count": self.visual_count,
        }


def _report_root(path: str | Path) -> Path:
    root = Path(path).expanduser().resolve()
    if root.name.endswith(".Report"):
        return root
    reports = sorted(item for item in root.glob("*.Report") if item.is_dir())
    if len(reports) != 1:
        raise ValueError("path must be a .Report folder or contain exactly one .Report folder")
    return reports[0]


def _load_json(path: Path, issues: list[ValidationIssue]) -> dict[str, Any] | None:
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
        if not isinstance(value, dict):
            raise ValueError("JSON root must be an object")
        return value
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        issues.append(ValidationIssue("error", "invalid_json", str(exc), str(path)))
        return None


def inspect_pbir_project(path: str | Path) -> dict[str, Any]:
    root = _report_root(path)
    report = validate_pbir_project(root)
    pages: list[dict[str, Any]] = []
    pages_root = root / "definition" / "pages"
    for page_file in sorted(pages_root.glob("*/page.json")):
        page = json.loads(page_file.read_text(encoding="utf-8"))
        visual_files = sorted((page_file.parent / "visuals").glob("*/visual.json"))
        pages.append({
            "id": page.get("name"),
            "display_name": page.get("displayName"),
            "visual_count": len(visual_files),
            "visual_types": [
                json.loads(item.read_text(encoding="utf-8"))
                .get("visual", {}).get("visualType")
                for item in visual_files
            ],
        })
    return {"report_root": str(root), "validation": report.to_dict(), "pages": pages}


def _validate_pbir_structure(path: str | Path) -> ValidationReport:
    try:
        root = _report_root(path)
    except ValueError as exc:
        issue = ValidationIssue("error", "report_root", str(exc), str(path))
        return ValidationReport(False, [issue])

    issues: list[ValidationIssue] = []
    required = [
        root / "definition.pbir",
        root / "definition" / "report.json",
        root / "definition" / "version.json",
        root / "definition" / "pages" / "pages.json",
    ]
    for item in required:
        if not item.is_file():
            issues.append(ValidationIssue("error", "missing_file", "required PBIR file is missing", str(item)))

    if issues:
        return ValidationReport(False, issues)

    properties = _load_json(required[0], issues)
    pages_metadata = _load_json(required[3], issues)
    if properties:
        reference = properties.get("datasetReference", {})
        if bool(reference.get("byPath")) == bool(reference.get("byConnection")):
            issues.append(ValidationIssue(
                "error", "dataset_reference",
                "definition.pbir must contain exactly one dataset reference", str(required[0])
            ))

    page_order = pages_metadata.get("pageOrder", []) if pages_metadata else []
    active_page = pages_metadata.get("activePageName") if pages_metadata else None
    if not page_order:
        issues.append(ValidationIssue("error", "page_order", "pageOrder must not be empty", str(required[3])))
    if active_page not in page_order:
        issues.append(ValidationIssue("error", "active_page", "activePageName is not in pageOrder", str(required[3])))

    visual_count = 0
    pages_root = root / "definition" / "pages"
    for page_id in page_order:
        page_path = pages_root / page_id / "page.json"
        if not page_path.is_file():
            issues.append(ValidationIssue("error", "missing_page", "page folder is missing", str(page_path)))
            continue
        page = _load_json(page_path, issues)
        if page and page.get("name") != page_id:
            issues.append(ValidationIssue("error", "page_id", "page name does not match folder", str(page_path)))
        for visual_path in sorted((page_path.parent / "visuals").glob("*/visual.json")):
            visual_count += 1
            visual = _load_json(visual_path, issues)
            if not visual:
                continue
            if visual.get("name") != visual_path.parent.name:
                issues.append(ValidationIssue("error", "visual_id", "visual name does not match folder", str(visual_path)))
            position = visual.get("position", {})
            if not all(isinstance(position.get(key), (int, float)) for key in ("x", "y", "width", "height")):
                issues.append(ValidationIssue("error", "visual_position", "visual position is incomplete", str(visual_path)))
            if not visual.get("visual", {}).get("visualType"):
                issues.append(ValidationIssue("error", "visual_type", "visualType is missing", str(visual_path)))

    return ValidationReport(
        not any(issue.severity == "error" for issue in issues),
        issues,
        len(page_order),
        visual_count,
    )


def validate_pbir_project(
    path: str | Path,
    *,
    official_schemas: bool = False,
    allow_schema_download: bool = False,
    schema_cache: str | Path | None = None,
) -> ValidationReport:
    """Run structural validation and optionally the official Microsoft schemas."""
    report = _validate_pbir_structure(path)
    if not official_schemas or not report.valid:
        return report

    root = _report_root(path)
    cache = (
        Path(schema_cache)
        if schema_cache
        else Path(__file__).resolve().parents[2] / ".pbir-schema-cache"
    )
    document_paths = [root / "definition.pbir"]
    document_paths.extend(sorted((root / "definition").rglob("*.json")))
    issues = list(report.issues)

    for document_path in document_paths:
        document = _load_json(document_path, issues)
        if document is None:
            continue
        for item in validate_json_document(
            document,
            path=str(document_path),
            cache_root=cache,
            allow_network=allow_schema_download,
        ):
            location = f" at {item.json_path}" if item.json_path else ""
            issues.append(ValidationIssue(
                item.severity,
                item.code,
                item.message + location,
                item.path,
            ))

    return ValidationReport(
        not any(issue.severity == "error" for issue in issues),
        issues,
        report.page_count,
        report.visual_count,
    )
