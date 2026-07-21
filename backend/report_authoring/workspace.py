from __future__ import annotations

import json
import os
import re
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compiler import CompilationResult, compile_report
from .desktop import open_report_in_powerbi_desktop, prepare_report_for_desktop
from .layout import validate_page_layout
from .models import DashboardSpec
from .preview import build_preview_manifest
from .quality import evaluate_report_quality
from .semantic import SemanticModelCatalog, validate_dashboard_semantics


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _slug(value: str) -> str:
    result = re.sub(r"[^a-z0-9]+", "-", value.casefold()).strip("-")
    return result[:80] or "dashboard"


def _write_json_atomic(path: Path, value: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{os.getpid()}.tmp")
    temporary.write_text(
        json.dumps(value, indent=2, ensure_ascii=False) + "\n", encoding="utf-8"
    )
    os.replace(temporary, path)


@dataclass(frozen=True)
class WorkspaceRevisionResult:
    dashboard_id: str
    version: int
    previous_version: int | None
    reason: str
    spec_path: str
    report_path: str
    pbir_path: str
    semantic_model_path: str | None
    quality_issues: list[dict[str, Any]]
    semantic_issues: list[dict[str, Any]]
    validation: dict[str, Any]
    preview: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DashboardWorkspaceManager:
    """Persistent, versioned source-of-truth for autonomous dashboards."""

    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    @property
    def index_path(self) -> Path:
        return self.root / "index.json"

    def _read_index(self) -> dict[str, Any]:
        if not self.index_path.is_file():
            return {"active_dashboard_id": None, "dashboards": []}
        return json.loads(self.index_path.read_text(encoding="utf-8"))

    def _dashboard_root(self, dashboard_id: str) -> Path:
        if not re.fullmatch(r"[a-z0-9][a-z0-9-]{0,79}", dashboard_id):
            raise ValueError("dashboard_id must be a lowercase URL-style slug")
        return self.root / dashboard_id

    def _record_path(self, dashboard_id: str) -> Path:
        return self._dashboard_root(dashboard_id) / "dashboard.json"

    def _read_record(self, dashboard_id: str) -> dict[str, Any]:
        path = self._record_path(dashboard_id)
        if not path.is_file():
            raise FileNotFoundError(f"dashboard workspace not found: {dashboard_id}")
        return json.loads(path.read_text(encoding="utf-8"))

    def _version_path(self, dashboard_id: str, version: int) -> Path:
        if version < 1:
            raise ValueError("version must be at least 1")
        return self._dashboard_root(dashboard_id) / "versions" / f"{version:04d}.json"

    def _read_version(self, dashboard_id: str, version: int) -> dict[str, Any]:
        path = self._version_path(dashboard_id, version)
        if not path.is_file():
            raise FileNotFoundError(
                f"dashboard {dashboard_id!r} has no version {version}"
            )
        return json.loads(path.read_text(encoding="utf-8"))

    def _next_available_id(self, title: str) -> str:
        base = _slug(title)
        candidate = base
        suffix = 2
        while self._record_path(candidate).exists():
            candidate = f"{base[:74]}-{suffix}"
            suffix += 1
        return candidate

    def active_dashboard_id(self) -> str:
        dashboard_id = self._read_index().get("active_dashboard_id")
        if not dashboard_id:
            raise FileNotFoundError("no active dashboard workspace is configured")
        return str(dashboard_id)

    def set_active(self, dashboard_id: str) -> dict[str, Any]:
        with self._lock:
            self._read_record(dashboard_id)
            index = self._read_index()
            dashboards = list(dict.fromkeys([*index.get("dashboards", []), dashboard_id]))
            index = {"active_dashboard_id": dashboard_id, "dashboards": dashboards}
            _write_json_atomic(self.index_path, index)
            return index

    def _build_revision(
        self,
        dashboard_id: str,
        version: int,
        previous_version: int | None,
        reason: str,
        spec: DashboardSpec,
        semantic_model_path: str | None,
        catalog: SemanticModelCatalog | None,
    ) -> WorkspaceRevisionResult:
        layout_errors = [
            f"{page.name}: {issue}"
            for page in spec.pages
            for issue in validate_page_layout(page)
        ]
        if layout_errors:
            raise ValueError("invalid report layout: " + "; ".join(layout_errors))
        quality = [item.to_dict() for item in evaluate_report_quality(spec)]
        semantic = (
            [item.to_dict() for item in validate_dashboard_semantics(spec, catalog)]
            if catalog
            else []
        )
        semantic_errors = [item for item in semantic if item["severity"] == "error"]
        if semantic_errors:
            raise ValueError(f"semantic validation failed: {semantic_errors}")

        dashboard_root = self._dashboard_root(dashboard_id)
        build: CompilationResult = compile_report(spec, dashboard_root / "builds")
        report_path = build.report_path
        pbir_path = str(Path(report_path) / "definition.pbir")
        if semantic_model_path:
            handoff = prepare_report_for_desktop(report_path, semantic_model_path)
            pbir_path = handoff.pbir_path
            semantic_model_path = handoff.semantic_model_path

        version_path = self._version_path(dashboard_id, version)
        preview = build_preview_manifest(report_path)
        payload = {
            "dashboard_id": dashboard_id,
            "version": version,
            "previous_version": previous_version,
            "reason": reason,
            "created_at": _utc_now(),
            "spec": spec.model_dump(by_alias=True),
            "spec_path": str(version_path),
            "report_path": report_path,
            "pbir_path": pbir_path,
            "semantic_model_path": semantic_model_path,
            "quality_issues": quality,
            "semantic_issues": semantic,
            "validation": build.validation.to_dict(),
            "preview": preview,
        }
        _write_json_atomic(version_path, payload)
        return WorkspaceRevisionResult(
            dashboard_id=dashboard_id,
            version=version,
            previous_version=previous_version,
            reason=reason,
            spec_path=str(version_path),
            report_path=report_path,
            pbir_path=pbir_path,
            semantic_model_path=semantic_model_path,
            quality_issues=quality,
            semantic_issues=semantic,
            validation=build.validation.to_dict(),
            preview=preview,
        )

    def create(
        self,
        spec: DashboardSpec,
        semantic_model_path: str | None = None,
        dashboard_id: str | None = None,
        catalog: SemanticModelCatalog | None = None,
        reason: str = "Initial dashboard",
    ) -> WorkspaceRevisionResult:
        with self._lock:
            selected_id = dashboard_id or self._next_available_id(spec.title)
            root = self._dashboard_root(selected_id)
            if self._record_path(selected_id).exists():
                raise FileExistsError(f"dashboard workspace already exists: {selected_id}")
            root.mkdir(parents=True, exist_ok=True)
            result = self._build_revision(
                selected_id, 1, None, reason, spec, semantic_model_path, catalog
            )
            now = _utc_now()
            _write_json_atomic(self._record_path(selected_id), {
                "dashboard_id": selected_id,
                "title": spec.title,
                "active_version": 1,
                "semantic_model_path": result.semantic_model_path,
                "created_at": now,
                "updated_at": now,
            })
            self.set_active(selected_id)
            return result

    def get(self, dashboard_id: str | None = None) -> dict[str, Any]:
        selected_id = dashboard_id or self.active_dashboard_id()
        record = self._read_record(selected_id)
        version = self._read_version(selected_id, int(record["active_version"]))
        return {"dashboard": record, "current": version}

    def revise(
        self,
        spec: DashboardSpec,
        reason: str,
        expected_version: int,
        dashboard_id: str | None = None,
        catalog: SemanticModelCatalog | None = None,
    ) -> WorkspaceRevisionResult:
        with self._lock:
            selected_id = dashboard_id or self.active_dashboard_id()
            record = self._read_record(selected_id)
            current = int(record["active_version"])
            if current != expected_version:
                raise RuntimeError(
                    f"dashboard version conflict: expected {expected_version}, active is {current}"
                )
            next_version = current + 1
            result = self._build_revision(
                selected_id,
                next_version,
                current,
                reason,
                spec,
                record.get("semantic_model_path"),
                catalog,
            )
            record.update({
                "title": spec.title,
                "active_version": next_version,
                "semantic_model_path": result.semantic_model_path,
                "updated_at": _utc_now(),
            })
            _write_json_atomic(self._record_path(selected_id), record)
            self.set_active(selected_id)
            return result

    def audit(
        self,
        dashboard_id: str | None = None,
        catalog: SemanticModelCatalog | None = None,
    ) -> dict[str, Any]:
        state = self.get(dashboard_id)
        spec = DashboardSpec.model_validate(state["current"]["spec"])
        layout = [
            {"page": page.name, "message": issue}
            for page in spec.pages
            for issue in validate_page_layout(page)
        ]
        quality = [item.to_dict() for item in evaluate_report_quality(spec)]
        semantic = (
            [item.to_dict() for item in validate_dashboard_semantics(spec, catalog)]
            if catalog
            else []
        )
        return {
            "dashboard_id": state["dashboard"]["dashboard_id"],
            "version": state["dashboard"]["active_version"],
            "valid": not layout and not any(
                item["severity"] == "error" for item in semantic
            ),
            "layout_issues": layout,
            "quality_issues": quality,
            "semantic_issues": semantic,
            "spec": spec.model_dump(by_alias=True),
            "preview": state["current"]["preview"],
        }

    def list_versions(self, dashboard_id: str | None = None) -> list[dict[str, Any]]:
        selected_id = dashboard_id or self.active_dashboard_id()
        record = self._read_record(selected_id)
        items: list[dict[str, Any]] = []
        for path in sorted((self._dashboard_root(selected_id) / "versions").glob("*.json")):
            value = json.loads(path.read_text(encoding="utf-8"))
            items.append({
                "version": value["version"],
                "reason": value["reason"],
                "created_at": value["created_at"],
                "report_path": value["report_path"],
                "active": value["version"] == record["active_version"],
            })
        return items

    def rollback(
        self,
        target_version: int,
        dashboard_id: str | None = None,
    ) -> WorkspaceRevisionResult:
        selected_id = dashboard_id or self.active_dashboard_id()
        state = self.get(selected_id)
        target = self._read_version(selected_id, target_version)
        spec = DashboardSpec.model_validate(target["spec"])
        return self.revise(
            spec,
            reason=f"Rollback to version {target_version}",
            expected_version=int(state["dashboard"]["active_version"]),
            dashboard_id=selected_id,
        )

    def open_active_in_desktop(
        self,
        dashboard_id: str | None = None,
        semantic_model_path: str | None = None,
    ) -> dict[str, Any]:
        selected_id = dashboard_id or self.active_dashboard_id()
        state = self.get(selected_id)
        record = state["dashboard"]
        current = state["current"]
        model_path = semantic_model_path or record.get("semantic_model_path")
        if not model_path:
            raise ValueError("semantic_model_path is required for Desktop rendering")
        handoff = prepare_report_for_desktop(current["report_path"], model_path)
        opened = open_report_in_powerbi_desktop(handoff.report_path)
        if semantic_model_path and semantic_model_path != record.get("semantic_model_path"):
            record["semantic_model_path"] = handoff.semantic_model_path
            record["updated_at"] = _utc_now()
            _write_json_atomic(self._record_path(selected_id), record)
        return {
            "dashboard_id": selected_id,
            "version": record["active_version"],
            "opened": True,
            "pbir_path": opened,
            "semantic_model_path": handoff.semantic_model_path,
        }
