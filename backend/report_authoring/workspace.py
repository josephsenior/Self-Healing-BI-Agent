from __future__ import annotations

import json
import os
import re
import threading
import uuid
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from .compiler import CompilationResult, compile_report
from .desktop import open_report_in_powerbi_desktop, prepare_report_for_desktop
from .layout import validate_page_layout
from .models import DashboardSpec
from .preview import build_preview_manifest
from .qa import (
    DashboardQARejected,
    FindingClass,
    GateStatus,
    QAFinding,
    QAGateResult,
    QAPolicy,
    QAReport,
    build_report,
)
from .quality import evaluate_report_quality
from .pbir import validate_pbir_project
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
    qa: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class DashboardWorkspaceManager:
    """Persistent, versioned source-of-truth for autonomous dashboards."""

    def __init__(self, root: str | Path, qa_policy: QAPolicy | None = None):
        self.root = Path(root).resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self.qa_policy = qa_policy or QAPolicy.from_env()

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

    def _qa_attempt_path(self, dashboard_id: str) -> Path:
        return self._dashboard_root(dashboard_id) / "qa-attempts.json"

    def _register_qa_attempt(
        self,
        dashboard_id: str,
        base_version: int,
        report: QAReport,
        candidate_report_path: str | None,
    ) -> QAReport:
        path = self._qa_attempt_path(dashboard_id)
        state = json.loads(path.read_text(encoding="utf-8")) if path.is_file() else {}
        key = str(base_version)
        previous = state.get(key, {})
        previous_attempt = int(previous.get("attempt", 0))
        previous_fingerprint = previous.get("fingerprint")

        # A materially different candidate starts a fresh cycle after a bounded
        # run has already reached NEEDS_REVIEW.
        if previous_attempt >= self.qa_policy.max_attempts and (
            previous_fingerprint != report.fingerprint
        ):
            previous = {}
            previous_attempt = 0
            previous_fingerprint = None

        attempt = previous_attempt + 1
        stalled = (
            int(previous.get("stalled_iterations", 0)) + 1
            if previous_fingerprint == report.fingerprint
            else 0
        )
        previous_best = int(previous.get("best_score", 10**9))
        is_best = report.score < previous_best
        best_score = min(previous_best, report.score)
        best_path = (
            candidate_report_path
            if is_best
            else previous.get("best_candidate_report_path")
        )

        if report.promotable:
            status = report.status
        elif attempt >= self.qa_policy.max_attempts or stalled >= 2:
            status = "NEEDS_REVIEW"
        else:
            status = "NEEDS_REVISION"

        updated = report.with_attempt(
            attempt=attempt,
            status=status,
            best_candidate_report_path=best_path,
        )
        state[key] = {
            "attempt": attempt,
            "fingerprint": report.fingerprint,
            "stalled_iterations": stalled,
            "best_score": best_score,
            "best_candidate_report_path": best_path,
            "status": status,
            "updated_at": _utc_now(),
        }
        _write_json_atomic(path, state)
        return updated

    def _clear_qa_attempt(self, dashboard_id: str, base_version: int) -> None:
        path = self._qa_attempt_path(dashboard_id)
        if not path.is_file():
            return
        state = json.loads(path.read_text(encoding="utf-8"))
        state.pop(str(base_version), None)
        _write_json_atomic(path, state)

    def _write_candidate_manifest(
        self,
        dashboard_id: str,
        base_version: int,
        reason: str,
        spec: DashboardSpec,
        report_path: str | None,
        qa: QAReport,
    ) -> Path:
        path = (
            self._dashboard_root(dashboard_id)
            / "qa-candidates"
            / f"{uuid.uuid4().hex}.json"
        )
        _write_json_atomic(path, {
            "dashboard_id": dashboard_id,
            "base_version": base_version,
            "reason": reason,
            "created_at": _utc_now(),
            "spec": spec.model_dump(by_alias=True),
            "report_path": report_path,
            "qa": qa.to_dict(),
        })
        return path

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
        findings: list[QAFinding] = []
        gates: list[QAGateResult] = []

        layout_errors = [
            (page.name, issue)
            for page in spec.pages
            for issue in validate_page_layout(page)
        ]
        layout_findings = [
            QAFinding(
                FindingClass.BLOCKING,
                "layout",
                "invalid_layout",
                message,
                page=page,
            )
            for page, message in layout_errors
        ]
        findings.extend(layout_findings)
        gates.append(QAGateResult(
            "layout",
            GateStatus.FAILED if layout_findings else GateStatus.PASSED,
            len(layout_findings),
        ))

        quality_items = evaluate_report_quality(spec)
        quality = [item.to_dict() for item in quality_items]
        quality_findings: list[QAFinding] = []
        for item in quality_items:
            if item.code in self.qa_policy.blocking_quality_codes:
                classification = FindingClass.BLOCKING
            elif item.severity == "warning":
                classification = FindingClass.IMPROVEMENT
            else:
                classification = FindingClass.INFORMATIONAL
            quality_findings.append(QAFinding(
                classification,
                "quality",
                item.code,
                item.message,
                page=item.page,
                visual=item.visual,
            ))
        findings.extend(quality_findings)
        gates.append(QAGateResult(
            "quality",
            GateStatus.FAILED
            if any(
                item.classification == FindingClass.BLOCKING
                for item in quality_findings
            )
            else GateStatus.PASSED_WITH_FINDINGS
            if quality_findings
            else GateStatus.PASSED,
            len(quality_findings),
        ))

        semantic: list[dict[str, Any]] = []
        semantic_findings: list[QAFinding] = []
        if catalog is not None:
            semantic_items = validate_dashboard_semantics(spec, catalog)
            semantic = [item.to_dict() for item in semantic_items]
            for item in semantic_items:
                semantic_findings.append(QAFinding(
                    FindingClass.BLOCKING
                    if item.severity == "error"
                    else FindingClass.IMPROVEMENT,
                    "semantic",
                    item.code,
                    item.message,
                    page=item.page,
                    visual=item.visual,
                    field=item.field,
                ))
            findings.extend(semantic_findings)
            gates.append(QAGateResult(
                "semantic",
                GateStatus.FAILED
                if any(
                    item.classification == FindingClass.BLOCKING
                    for item in semantic_findings
                )
                else GateStatus.PASSED_WITH_FINDINGS
                if semantic_findings
                else GateStatus.PASSED,
                len(semantic_findings),
            ))
        elif self.qa_policy.require_semantic_catalog:
            missing_catalog = QAFinding(
                FindingClass.BLOCKING,
                "semantic",
                "semantic_catalog_required",
                "strict QA requires a live SemanticModelCatalog",
            )
            findings.append(missing_catalog)
            gates.append(QAGateResult(
                "semantic", GateStatus.UNAVAILABLE, 1, missing_catalog.message
            ))
        else:
            gates.append(QAGateResult(
                "semantic",
                GateStatus.SKIPPED,
                detail="not configured: no catalog supplied",
            ))

        dashboard_root = self._dashboard_root(dashboard_id)
        build: CompilationResult | None = None
        report_path: str | None = None
        pbir_path: str | None = None
        try:
            build = compile_report(spec, dashboard_root / "candidate-builds")
            report_path = build.report_path
            pbir_path = str(Path(report_path) / "definition.pbir")
            gates.append(QAGateResult("compile", GateStatus.PASSED))
        except Exception as exc:
            findings.append(QAFinding(
                FindingClass.BLOCKING,
                "compile",
                "compilation_failed",
                str(exc),
            ))
            gates.append(QAGateResult("compile", GateStatus.FAILED, 1, str(exc)))

        if build is not None and semantic_model_path:
            try:
                handoff = prepare_report_for_desktop(report_path, semantic_model_path)
                pbir_path = handoff.pbir_path
                semantic_model_path = handoff.semantic_model_path
                gates.append(QAGateResult("desktop_binding", GateStatus.PASSED))
            except Exception as exc:
                findings.append(QAFinding(
                    FindingClass.BLOCKING,
                    "desktop_binding",
                    "desktop_binding_failed",
                    str(exc),
                ))
                gates.append(QAGateResult(
                    "desktop_binding", GateStatus.FAILED, 1, str(exc)
                ))
        elif build is not None:
            gates.append(QAGateResult(
                "desktop_binding",
                GateStatus.SKIPPED,
                detail="not configured: no local semantic-model path",
            ))
        else:
            gates.append(QAGateResult(
                "desktop_binding", GateStatus.BLOCKED, detail="compile failed"
            ))

        structural_validation = None
        final_validation = build.validation if build is not None else None
        if report_path is not None:
            structural_validation = validate_pbir_project(report_path)
            final_validation = structural_validation
            structural_findings = [
                QAFinding(
                    FindingClass.BLOCKING
                    if item.severity == "error"
                    else FindingClass.IMPROVEMENT,
                    "pbir_structure",
                    item.code,
                    item.message,
                    path=item.path,
                )
                for item in structural_validation.issues
            ]
            findings.extend(structural_findings)
            gates.append(QAGateResult(
                "pbir_structure",
                GateStatus.FAILED
                if not structural_validation.valid
                else GateStatus.PASSED_WITH_FINDINGS
                if structural_findings
                else GateStatus.PASSED,
                len(structural_findings),
            ))
        else:
            gates.append(QAGateResult(
                "pbir_structure", GateStatus.BLOCKED, detail="compile failed"
            ))

        if not self.qa_policy.validate_official_schemas:
            gates.append(QAGateResult(
                "official_schema",
                GateStatus.SKIPPED,
                detail="disabled by QA policy",
            ))
        elif report_path is None or structural_validation is None:
            gates.append(QAGateResult(
                "official_schema", GateStatus.BLOCKED, detail="compile failed"
            ))
        elif not structural_validation.valid:
            gates.append(QAGateResult(
                "official_schema",
                GateStatus.BLOCKED,
                detail="structural validation failed",
            ))
        else:
            try:
                official = validate_pbir_project(
                    report_path,
                    official_schemas=True,
                    allow_schema_download=self.qa_policy.allow_schema_download,
                    schema_cache=Path(__file__).resolve().parents[2]
                    / ".pbir-schema-cache",
                )
                final_validation = official
                structural_keys = {
                    (item.code, item.message, item.path)
                    for item in structural_validation.issues
                }
                official_items = [
                    item
                    for item in official.issues
                    if (item.code, item.message, item.path) not in structural_keys
                ]
                official_findings = [
                    QAFinding(
                        FindingClass.BLOCKING
                        if item.severity == "error"
                        else FindingClass.IMPROVEMENT,
                        "official_schema",
                        item.code,
                        item.message,
                        path=item.path,
                    )
                    for item in official_items
                ]
                findings.extend(official_findings)
                gates.append(QAGateResult(
                    "official_schema",
                    GateStatus.FAILED
                    if not official.valid
                    else GateStatus.PASSED_WITH_FINDINGS
                    if official_findings
                    else GateStatus.PASSED,
                    len(official_findings),
                ))
            except Exception as exc:
                findings.append(QAFinding(
                    FindingClass.BLOCKING,
                    "official_schema",
                    "official_schema_unavailable",
                    str(exc),
                ))
                gates.append(QAGateResult(
                    "official_schema", GateStatus.UNAVAILABLE, 1, str(exc)
                ))

        preview: dict[str, Any] = {}
        if report_path is not None:
            try:
                preview = build_preview_manifest(report_path)
                gates.append(QAGateResult("preview_manifest", GateStatus.PASSED))
            except Exception as exc:
                findings.append(QAFinding(
                    FindingClass.BLOCKING,
                    "preview_manifest",
                    "preview_manifest_failed",
                    str(exc),
                ))
                gates.append(QAGateResult(
                    "preview_manifest", GateStatus.FAILED, 1, str(exc)
                ))
        else:
            gates.append(QAGateResult(
                "preview_manifest", GateStatus.BLOCKED, detail="compile failed"
            ))

        qa = build_report(
            gates,
            findings,
            max_attempts=self.qa_policy.max_attempts,
        )
        base_version = previous_version or 0
        qa = self._register_qa_attempt(
            dashboard_id, base_version, qa, report_path
        )
        candidate_manifest = self._write_candidate_manifest(
            dashboard_id,
            base_version,
            reason,
            spec,
            report_path,
            qa,
        )
        if not qa.promotable:
            raise DashboardQARejected(qa, str(candidate_manifest))
        if build is None or report_path is None or pbir_path is None:
            raise RuntimeError("promotable QA result has no compiled report")

        version_path = self._version_path(dashboard_id, version)
        validation = (
            final_validation.to_dict()
            if final_validation is not None
            else build.validation.to_dict()
        )
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
            "validation": validation,
            "preview": preview,
            "qa": qa.to_dict(),
            "qa_candidate_manifest_path": str(candidate_manifest),
        }
        _write_json_atomic(version_path, payload)
        self._clear_qa_attempt(dashboard_id, base_version)
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
            validation=validation,
            preview=preview,
            qa=qa.to_dict(),
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
        catalog: SemanticModelCatalog | None = None,
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
            catalog=catalog,
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
