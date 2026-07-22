from __future__ import annotations

import hashlib
import json
import os
from dataclasses import asdict, dataclass, field, replace
from enum import StrEnum
from typing import Any, Iterable


class FindingClass(StrEnum):
    BLOCKING = "blocking"
    IMPROVEMENT = "improvement"
    INFORMATIONAL = "informational"


class GateStatus(StrEnum):
    PASSED = "passed"
    PASSED_WITH_FINDINGS = "passed_with_findings"
    FAILED = "failed"
    UNAVAILABLE = "unavailable"
    BLOCKED = "blocked"
    SKIPPED = "skipped"


@dataclass(frozen=True)
class QAFinding:
    classification: FindingClass
    gate: str
    code: str
    message: str
    page: str = ""
    visual: str = ""
    field: str = ""
    path: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["classification"] = self.classification.value
        return value


@dataclass(frozen=True)
class QAGateResult:
    name: str
    status: GateStatus
    finding_count: int = 0
    detail: str = ""

    def to_dict(self) -> dict[str, Any]:
        value = asdict(self)
        value["status"] = self.status.value
        return value


@dataclass(frozen=True)
class QAReport:
    status: str
    attempt: int
    max_attempts: int
    score: int
    fingerprint: str
    gates: list[QAGateResult] = field(default_factory=list)
    findings: list[QAFinding] = field(default_factory=list)
    best_candidate_report_path: str | None = None

    @property
    def promotable(self) -> bool:
        return not any(
            item.classification == FindingClass.BLOCKING for item in self.findings
        )

    def with_attempt(
        self,
        *,
        attempt: int,
        status: str,
        best_candidate_report_path: str | None,
    ) -> "QAReport":
        return replace(
            self,
            attempt=attempt,
            status=status,
            best_candidate_report_path=best_candidate_report_path,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status,
            "promotable": self.promotable,
            "attempt": self.attempt,
            "max_attempts": self.max_attempts,
            "score": self.score,
            "fingerprint": self.fingerprint,
            "best_candidate_report_path": self.best_candidate_report_path,
            "gates": [item.to_dict() for item in self.gates],
            "findings": [item.to_dict() for item in self.findings],
        }


@dataclass(frozen=True)
class QAPolicy:
    max_attempts: int = 3
    require_semantic_catalog: bool = False
    validate_official_schemas: bool = True
    allow_schema_download: bool = False
    blocking_quality_codes: frozenset[str] = frozenset()

    @classmethod
    def from_env(cls) -> "QAPolicy":
        def enabled(name: str, default: bool) -> bool:
            raw = os.getenv(name)
            if raw is None:
                return default
            return raw.strip().casefold() in {"1", "true", "yes", "on"}

        raw_codes = os.getenv("POWERBI_QA_BLOCKING_QUALITY_CODES", "")
        return cls(
            max_attempts=max(1, int(os.getenv("POWERBI_QA_MAX_ATTEMPTS", "3"))),
            require_semantic_catalog=enabled(
                "POWERBI_QA_REQUIRE_SEMANTIC_CATALOG", False
            ),
            validate_official_schemas=enabled(
                "POWERBI_QA_VALIDATE_OFFICIAL_SCHEMAS", True
            ),
            allow_schema_download=enabled(
                "POWERBI_QA_ALLOW_SCHEMA_DOWNLOAD", False
            ),
            blocking_quality_codes=frozenset(
                item.strip() for item in raw_codes.split(",") if item.strip()
            ),
        )


class DashboardQARejected(ValueError):
    def __init__(self, report: QAReport, candidate_manifest_path: str):
        self.report = report
        self.candidate_manifest_path = candidate_manifest_path
        payload = {
            "message": "Candidate was not promoted; revise from QA findings and retry.",
            "candidate_manifest_path": candidate_manifest_path,
            "qa": report.to_dict(),
        }
        super().__init__(json.dumps(payload, indent=2))


def build_report(
    gates: Iterable[QAGateResult],
    findings: Iterable[QAFinding],
    *,
    max_attempts: int,
) -> QAReport:
    gate_items = list(gates)
    finding_items = list(findings)
    weights = {
        FindingClass.BLOCKING: 100,
        FindingClass.IMPROVEMENT: 10,
        FindingClass.INFORMATIONAL: 1,
    }
    score = sum(weights[item.classification] for item in finding_items)
    canonical = [
        [
            item.classification.value,
            item.gate,
            item.code,
            item.page,
            item.visual,
            item.field,
            item.path,
            item.message,
        ]
        for item in sorted(
            finding_items,
            key=lambda value: (
                value.classification.value,
                value.gate,
                value.code,
                value.page,
                value.visual,
                value.field,
                value.path,
                value.message,
            ),
        )
    ]
    fingerprint = hashlib.sha256(
        json.dumps(canonical, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    has_blocking = any(
        item.classification == FindingClass.BLOCKING for item in finding_items
    )
    has_improvements = any(
        item.classification == FindingClass.IMPROVEMENT for item in finding_items
    )
    status = (
        "NEEDS_REVISION"
        if has_blocking
        else "VERIFIED_WITH_WARNINGS"
        if has_improvements
        else "VERIFIED"
    )
    return QAReport(
        status=status,
        attempt=1,
        max_attempts=max_attempts,
        score=score,
        fingerprint=fingerprint,
        gates=gate_items,
        findings=finding_items,
    )
