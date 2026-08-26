from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from contextlib import contextmanager
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Iterator

import httpx

from .desktop_version import detect_compatibility_level

from .cloud import (
    FABRIC_API,
    FABRIC_SCOPE,
    POWERBI_API,
    POWERBI_SCOPE,
    CloudAPIError,
    CloudConfig,
    EntraTokenProvider,
    FabricReportPublisher,
    PowerBIExportRenderer,
    PublishResult,
    _ensure_success,
    _response_json,
    _safe_retry_after,
)
from .compiler import compile_report
from .models import DashboardSpec
from .pbir import validate_pbir_project
from .preview import build_preview_manifest
from .semantic import SemanticModelCatalog, validate_dashboard_semantics
from .visual_review import (
    VisualReview,
    decide_visual_qa_iteration,
    review_rendered_report,
)


MODEL_DISPLAY_NAME = "Agent Qualification Semantic Model"
REPORT_DISPLAY_NAME = "Agent Qualification Report"
RETRYABLE_STATUS_CODES = {429, 502, 503, 504}


@dataclass(frozen=True)
class SemanticModelResult:
    action: str
    workspace_id: str
    semantic_model_id: str
    display_name: str
    operation_id: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _request_with_retry(
    client: httpx.Client,
    method: str,
    url: str,
    *,
    sleep: Callable[[float], None],
    default_delay: float,
    max_attempts: int = 4,
    **kwargs: Any,
) -> httpx.Response:
    response: httpx.Response | None = None
    for attempt in range(1, max_attempts + 1):
        try:
            response = client.request(method, url, **kwargs)
        except httpx.TransportError:
            if attempt == max_attempts:
                raise
            sleep(default_delay)
            continue
        if response.status_code not in RETRYABLE_STATUS_CODES or attempt == max_attempts:
            return response
        sleep(_safe_retry_after(response, default_delay))
    if response is None:  # pragma: no cover
        raise RuntimeError("cloud request did not execute")
    return response


class RetryingCloudHttpClient:
    """Duck-typed httpx client that adds bounded retry behavior."""

    def __init__(self, config: CloudConfig, sleep: Callable[[float], None] = time.sleep):
        self.config = config
        self.sleep = sleep
        self.client = httpx.Client(timeout=config.timeout_seconds)

    def request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return _request_with_retry(
            self.client,
            method,
            url,
            sleep=self.sleep,
            default_delay=self.config.poll_interval_seconds,
            **kwargs,
        )

    def get(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("GET", url, **kwargs)

    def post(self, url: str, **kwargs: Any) -> httpx.Response:
        return self.request("POST", url, **kwargs)

    def close(self) -> None:
        self.client.close()


def synthetic_model_definition() -> dict[str, Any]:
    """A deterministic, data-source-free TMSL model for cloud qualification."""
    rows = [
        '("2026-01-01", "Mobile", "North", 12, 2400.0, 1500.0)',
        '("2026-01-15", "Fiber", "Tunis", 8, 3600.0, 2100.0)',
        '("2026-02-01", "Cloud", "South", 5, 4200.0, 2600.0)',
        '("2026-02-15", "Mobile", "Tunis", 15, 3100.0, 1800.0)',
        '("2026-03-01", "Fiber", "North", 10, 3900.0, 2200.0)',
        '("2026-03-15", "Cloud", "Tunis", 7, 5100.0, 3000.0)',
        '("2026-04-01", "Mobile", "South", 18, 3700.0, 2050.0)',
        '("2026-04-15", "Fiber", "Tunis", 11, 4400.0, 2450.0)',
        '("2026-05-01", "Cloud", "North", 9, 5700.0, 3200.0)',
        '("2026-05-15", "Mobile", "Tunis", 20, 4100.0, 2250.0)',
        '("2026-06-01", "Fiber", "South", 13, 4900.0, 2700.0)',
        '("2026-06-15", "Cloud", "Tunis", 10, 6300.0, 3500.0)',
    ]
    # ROW is intentionally used instead of DATATABLE here. Fabric accepts this
    # calculated-table expression consistently when a TMSL definition is
    # created through the public API, including in Pro workspaces.
    expression = (
        'ROW("Order Date", "2026-01-01", "Product", "Mobile", '
        '"Region", "North", "Quantity", 12, "Revenue", 2400.0, '
        '"Cost", 1500.0)'
    )
    return {
        "name": MODEL_DISPLAY_NAME,
        "compatibilityLevel": detect_compatibility_level(),
        "model": {
            "culture": "en-US",
            "defaultPowerBIDataSourceVersion": "powerBI_V3",
            "discourageImplicitMeasures": True,
            "tables": [
                {
                    "name": "Sales",
                    "description": "Deterministic synthetic sales data for agent qualification.",
                    "columns": [
                        {
                            "type": "calculatedTableColumn",
                            "name": "Order Date",
                            "dataType": "string",
                            "sourceColumn": "[Order Date]",
                            "summarizeBy": "none",
                        },
                        {
                            "type": "calculatedTableColumn",
                            "name": "Product",
                            "dataType": "string",
                            "sourceColumn": "[Product]",
                            "summarizeBy": "none",
                        },
                        {
                            "type": "calculatedTableColumn",
                            "name": "Region",
                            "dataType": "string",
                            "sourceColumn": "[Region]",
                            "summarizeBy": "none",
                        },
                        {
                            "type": "calculatedTableColumn",
                            "name": "Quantity",
                            "dataType": "int64",
                            "formatString": "0",
                            "sourceColumn": "[Quantity]",
                            "summarizeBy": "sum",
                        },
                        {
                            "type": "calculatedTableColumn",
                            "name": "Revenue",
                            "dataType": "double",
                            "formatString": "$#,0.00",
                            "sourceColumn": "[Revenue]",
                            "summarizeBy": "sum",
                        },
                        {
                            "type": "calculatedTableColumn",
                            "name": "Cost",
                            "dataType": "double",
                            "formatString": "$#,0.00",
                            "sourceColumn": "[Cost]",
                            "summarizeBy": "sum",
                        },
                    ],
                    "partitions": [
                        {
                            "name": "Sales",
                            "mode": "import",
                            "source": {"type": "calculated", "expression": expression},
                        }
                    ],
                    "measures": [
                        {
                            "name": "Total Revenue",
                            "expression": "SUM('Sales'[Revenue])",
                            "formatString": "$#,0.00",
                        },
                        {
                            "name": "Total Cost",
                            "expression": "SUM('Sales'[Cost])",
                            "formatString": "$#,0.00",
                        },
                        {
                            "name": "Total Margin",
                            "expression": "[Total Revenue] - [Total Cost]",
                            "formatString": "$#,0.00",
                        },
                        {
                            "name": "Margin %",
                            "expression": "DIVIDE([Total Margin], [Total Revenue])",
                            "formatString": "0.0%",
                        },
                        {
                            "name": "Total Quantity",
                            "expression": "SUM('Sales'[Quantity])",
                            "formatString": "#,0",
                        },
                    ],
                }
            ],
        },
    }


def synthetic_catalog() -> SemanticModelCatalog:
    return SemanticModelCatalog.model_validate(
        {
            "tables": [
                {
                    "name": "Sales",
                    "columns": [
                        {"name": "Order Date", "data_type": "string", "distinct_count": 12},
                        {"name": "Product", "data_type": "string", "distinct_count": 3},
                        {"name": "Region", "data_type": "string", "distinct_count": 3},
                        {"name": "Quantity", "data_type": "int64"},
                        {"name": "Revenue", "data_type": "double"},
                        {"name": "Cost", "data_type": "double"},
                    ],
                    "measures": [
                        {"name": "Total Revenue", "data_type": "currency"},
                        {"name": "Total Cost", "data_type": "currency"},
                        {"name": "Total Margin", "data_type": "currency"},
                        {"name": "Margin %", "data_type": "double"},
                        {"name": "Total Quantity", "data_type": "int64"},
                    ],
                }
            ]
        }
    )


def synthetic_dashboard_spec(semantic_model_id: str) -> DashboardSpec:
    return DashboardSpec.model_validate(
        {
            "title": REPORT_DISPLAY_NAME,
            "dataset": {"semantic_model_id": semantic_model_id},
            "pages": [
                {
                    "name": "QualificationOverview",
                    "display_name": "Qualification Overview",
                    # Keep the qualification canvas compact so the exported
                    # image uses the available space instead of leaving a
                    # large empty lower region.
                    "height": 560,
                    "visuals": [
                        {
                            "type": "card",
                            "title": "Revenue",
                            "position": {"column": 0, "row": 0, "width": 3, "height": 3},
                            "values": [
                                {"table": "Sales", "name": "Total Revenue", "kind": "measure"}
                            ],
                        },
                        {
                            "type": "card",
                            "title": "Margin",
                            "position": {"column": 3, "row": 0, "width": 3, "height": 3},
                            "values": [
                                {"table": "Sales", "name": "Margin %", "kind": "measure"}
                            ],
                        },
                        {
                            "type": "card",
                            "title": "Units",
                            "position": {"column": 6, "row": 0, "width": 3, "height": 3},
                            "values": [
                                {"table": "Sales", "name": "Total Quantity", "kind": "measure"}
                            ],
                        },
                        {
                            "type": "clusteredBarChart",
                            "title": "Revenue by Region",
                            "position": {"column": 0, "row": 3, "width": 6, "height": 5},
                            "category": {"table": "Sales", "name": "Region"},
                            "values": [
                                {"table": "Sales", "name": "Total Revenue", "kind": "measure"}
                            ],
                        },
                        {
                            "type": "lineChart",
                            "title": "Revenue Trend",
                            "position": {"column": 6, "row": 3, "width": 6, "height": 5},
                            "category": {"table": "Sales", "name": "Order Date"},
                            "values": [
                                {"table": "Sales", "name": "Total Revenue", "kind": "measure"}
                            ],
                        },
                        {
                            "type": "slicer",
                            "title": "Product Filter",
                            "position": {"column": 9, "row": 0, "width": 3, "height": 3},
                            "category": {"table": "Sales", "name": "Product"},
                        },
                    ],
                }
            ],
        }
    )


def _semantic_definition_parts(model: dict[str, Any]) -> list[dict[str, str]]:
    import base64

    payloads = {
        "definition.pbism": json.dumps(
            {"version": "4.2", "settings": {"qnaEnabled": True}},
            separators=(",", ":"),
        ).encode("utf-8"),
        "model.bim": json.dumps(model, separators=(",", ":")).encode("utf-8"),
    }
    return [
        {
            "path": path,
            "payload": base64.b64encode(payload).decode("ascii"),
            "payloadType": "InlineBase64",
        }
        for path, payload in payloads.items()
    ]


class QualificationStore:
    """Small durable ledger for single-user qualification runs and cloud IDs."""

    def __init__(self, path: str | Path):
        self.path = Path(path).resolve()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._connection() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS runs (
                    run_id TEXT PRIMARY KEY,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    error TEXT
                );
                CREATE TABLE IF NOT EXISTS steps (
                    run_id TEXT NOT NULL,
                    step TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    finished_at TEXT,
                    detail_json TEXT,
                    PRIMARY KEY (run_id, step)
                );
                CREATE TABLE IF NOT EXISTS resources (
                    workspace_id TEXT NOT NULL,
                    resource_type TEXT NOT NULL,
                    display_name TEXT NOT NULL,
                    resource_id TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (workspace_id, resource_type, display_name)
                );
                """
            )

    def _connect(self) -> sqlite3.Connection:
        connection = sqlite3.connect(self.path)
        connection.row_factory = sqlite3.Row
        return connection

    @contextmanager
    def _connection(self) -> Iterator[sqlite3.Connection]:
        connection = self._connect()
        try:
            with connection:
                yield connection
        finally:
            connection.close()

    def begin_run(self) -> str:
        run_id = uuid.uuid4().hex
        with self._connection() as connection:
            connection.execute(
                "INSERT INTO runs(run_id, status, started_at) VALUES (?, ?, ?)",
                (run_id, "RUNNING", _utc_now()),
            )
        return run_id

    @contextmanager
    def step(self, run_id: str, name: str) -> Iterator[dict[str, Any]]:
        detail: dict[str, Any] = {}
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO steps(
                    run_id, step, status, started_at, finished_at, detail_json
                ) VALUES (?, ?, ?, ?, NULL, NULL)
                """,
                (run_id, name, "RUNNING", _utc_now()),
            )
        try:
            yield detail
        except Exception as exc:
            detail["error"] = str(exc)
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE steps SET status = ?, finished_at = ?, detail_json = ?
                    WHERE run_id = ? AND step = ?
                    """,
                    ("FAILED", _utc_now(), json.dumps(detail), run_id, name),
                )
            raise
        else:
            with self._connection() as connection:
                connection.execute(
                    """
                    UPDATE steps SET status = ?, finished_at = ?, detail_json = ?
                    WHERE run_id = ? AND step = ?
                    """,
                    ("PASSED", _utc_now(), json.dumps(detail), run_id, name),
                )

    def finish(self, run_id: str, status: str, error: str | None = None) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                UPDATE runs SET status = ?, finished_at = ?, error = ?
                WHERE run_id = ?
                """,
                (status, _utc_now(), error, run_id),
            )

    def resource(
        self, workspace_id: str, resource_type: str, display_name: str
    ) -> str | None:
        with self._connection() as connection:
            row = connection.execute(
                """
                SELECT resource_id FROM resources
                WHERE workspace_id = ? AND resource_type = ? AND display_name = ?
                """,
                (workspace_id, resource_type, display_name),
            ).fetchone()
        return str(row["resource_id"]) if row else None

    def save_resource(
        self,
        workspace_id: str,
        resource_type: str,
        display_name: str,
        resource_id: str,
    ) -> None:
        with self._connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO resources(
                    workspace_id, resource_type, display_name, resource_id, updated_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (workspace_id, resource_type, display_name, resource_id, _utc_now()),
            )

    def steps(self, run_id: str) -> list[dict[str, Any]]:
        with self._connection() as connection:
            rows = connection.execute(
                """
                SELECT step, status, started_at, finished_at, detail_json
                FROM steps WHERE run_id = ? ORDER BY rowid
                """,
                (run_id,),
            ).fetchall()
        return [
            {
                "step": row["step"],
                "status": row["status"],
                "started_at": row["started_at"],
                "finished_at": row["finished_at"],
                "detail": json.loads(row["detail_json"] or "{}"),
            }
            for row in rows
        ]


class FabricQualificationClient:
    def __init__(
        self,
        config: CloudConfig,
        tokens: EntraTokenProvider | None = None,
        client: httpx.Client | None = None,
        sleep: Callable[[float], None] = time.sleep,
    ):
        self.config = config
        self.tokens = tokens or EntraTokenProvider(config)
        self.client = client or httpx.Client(timeout=config.timeout_seconds)
        self.sleep = sleep

    def _headers(self, scope: str) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self.tokens.token_for(scope)}",
            "Content-Type": "application/json",
        }

    def _request(self, method: str, url: str, **kwargs: Any) -> httpx.Response:
        return _request_with_retry(
            self.client,
            method,
            url,
            sleep=self.sleep,
            default_delay=self.config.poll_interval_seconds,
            **kwargs,
        )

    def _complete_lro(
        self,
        response: httpx.Response,
        operation: str,
        *,
        expect_result: bool = True,
    ) -> tuple[dict[str, Any], str | None]:
        if response.status_code != 202:
            return _response_json(response), None
        location = response.headers.get("Location", "").rstrip("/")
        operation_id = response.headers.get("x-ms-operation-id")
        if not operation_id:
            operation_id = location.rsplit("/", 1)[-1] if location else ""
        if not operation_id:
            raise CloudAPIError(f"{operation} returned 202 without an operation id")
        state_url = location or f"{FABRIC_API}/operations/{operation_id}"
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            state_response = self._request(
                "GET", state_url, headers=self._headers(FABRIC_SCOPE)
            )
            _ensure_success(state_response, f"poll {operation}")
            state = _response_json(state_response)
            status = state.get("status")
            if status == "Succeeded":
                if not expect_result:
                    return {}, operation_id
                result_response = self._request(
                    "GET",
                    f"{state_url}/result",
                    headers=self._headers(FABRIC_SCOPE),
                )
                _ensure_success(result_response, f"get {operation} result")
                return _response_json(result_response), operation_id
            if status in {"Failed", "Cancelled"}:
                raise CloudAPIError(
                    f"{operation} {operation_id} ended with "
                    f"{state.get('error') or state.get('message') or status}"
                )
            self.sleep(_safe_retry_after(state_response, self.config.poll_interval_seconds))
        raise TimeoutError(f"{operation} {operation_id} exceeded the configured timeout")

    def check_workspace(self) -> dict[str, Any]:
        # Acquire both audiences now so readiness reports real authentication failures.
        self.tokens.token_for(FABRIC_SCOPE)
        self.tokens.token_for(POWERBI_SCOPE)
        response = self._request(
            "GET",
            f"{FABRIC_API}/workspaces/{self.config.workspace_id}",
            headers=self._headers(FABRIC_SCOPE),
        )
        _ensure_success(response, "read Fabric qualification workspace")
        payload = _response_json(response)
        return {
            "workspace_id": self.config.workspace_id,
            "display_name": payload.get("displayName"),
            "fabric_token": True,
            "powerbi_token": True,
        }

    def _find_unique(self, endpoint: str, display_name: str) -> str | None:
        response = self._request(
            "GET",
            f"{FABRIC_API}/workspaces/{self.config.workspace_id}/{endpoint}",
            headers=self._headers(FABRIC_SCOPE),
        )
        _ensure_success(response, f"list Fabric {endpoint}")
        items = _response_json(response).get("value", [])
        matches = [
            str(item.get("id", ""))
            for item in items
            if str(item.get("displayName", "")).casefold() == display_name.casefold()
            and item.get("id")
        ]
        if len(matches) > 1:
            raise CloudAPIError(
                f"multiple {endpoint} are named {display_name!r}; "
                "qualification requires deterministic unique names"
            )
        return matches[0] if matches else None

    def ensure_model(
        self,
        display_name: str,
        model: dict[str, Any],
        known_id: str | None = None,
    ) -> SemanticModelResult:
        selected_id = known_id or self._find_unique("semanticModels", display_name)
        definition = {"format": "TMSL", "parts": _semantic_definition_parts(model)}
        if selected_id:
            response = self._request(
                "POST",
                (
                    f"{FABRIC_API}/workspaces/{self.config.workspace_id}/semanticModels/"
                    f"{selected_id}/updateDefinition"
                ),
                headers=self._headers(FABRIC_SCOPE),
                json={"definition": definition},
            )
            _ensure_success(response, "update qualification semantic model")
            _, operation_id = self._complete_lro(
                response,
                "semantic-model update",
                expect_result=False,
            )
            return SemanticModelResult(
                "updated",
                self.config.workspace_id,
                selected_id,
                display_name,
                operation_id,
            )
        response = self._request(
            "POST",
            f"{FABRIC_API}/workspaces/{self.config.workspace_id}/semanticModels",
            headers=self._headers(FABRIC_SCOPE),
            json={
                "displayName": display_name,
                "description": "Disposable model for autonomous agent qualification.",
                "definition": definition,
            },
        )
        _ensure_success(response, "create qualification semantic model")
        result, operation_id = self._complete_lro(response, "semantic-model create")
        model_id = str(result.get("id", ""))
        if not model_id:
            raise CloudAPIError("semantic-model create response did not include an id")
        return SemanticModelResult(
            "created",
            self.config.workspace_id,
            model_id,
            str(result.get("displayName") or display_name),
            operation_id,
        )

    def find_report(self, display_name: str) -> str | None:
        return self._find_unique("reports", display_name)

    def refresh_model(self, semantic_model_id: str) -> dict[str, Any]:
        url = (
            f"{POWERBI_API}/groups/{self.config.workspace_id}/datasets/"
            f"{semantic_model_id}/refreshes"
        )
        response = self._request(
            "POST",
            url,
            headers=self._headers(POWERBI_SCOPE),
            json={"notifyOption": "NoNotification"},
        )
        _ensure_success(response, "start qualification semantic-model refresh")
        deadline = time.monotonic() + self.config.timeout_seconds
        while time.monotonic() < deadline:
            status_response = self._request(
                "GET",
                f"{url}?$top=1",
                headers=self._headers(POWERBI_SCOPE),
            )
            _ensure_success(status_response, "poll qualification semantic-model refresh")
            refreshes = _response_json(status_response).get("value", [])
            status = str(refreshes[0].get("status", "")) if refreshes else ""
            if status == "Completed":
                return {"status": status}
            if status in {"Failed", "Disabled", "Cancelled"}:
                detail = refreshes[0].get("serviceExceptionJson") if refreshes else status
                raise CloudAPIError(f"qualification semantic-model refresh failed: {detail}")
            self.sleep(self.config.poll_interval_seconds)
        raise TimeoutError("qualification semantic-model refresh exceeded the configured timeout")

    def execute_dax(self, semantic_model_id: str) -> dict[str, Any]:
        response = self._request(
            "POST",
            (
                f"{POWERBI_API}/groups/{self.config.workspace_id}/datasets/"
                f"{semantic_model_id}/executeQueries"
            ),
            headers=self._headers(POWERBI_SCOPE),
            json={
                "queries": [
                    {
                        "query": (
                            'EVALUATE ROW("Revenue", [Total Revenue], '
                            '"Margin", [Total Margin], "Rows", COUNTROWS(\'Sales\'))'
                        )
                    }
                ],
                "serializerSettings": {"includeNulls": True},
            },
        )
        _ensure_success(response, "execute qualification DAX")
        payload = _response_json(response)
        results = payload.get("results", [])
        if not results or results[0].get("error"):
            raise CloudAPIError(
                f"qualification DAX returned no valid result: {payload}"
            )
        tables = results[0].get("tables", [])
        rows = tables[0].get("rows", []) if tables else []
        if not rows:
            raise CloudAPIError("qualification DAX returned no rows")
        return {"row": rows[0], "result_count": len(results)}


@dataclass
class QualificationResult:
    run_id: str
    status: str
    workspace_id: str
    semantic_model_id: str = ""
    report_id: str = ""
    pages_rendered: int = 0
    qa_attempts: int = 0
    tests_passed: int = 0
    tests_failed: int = 0
    artifacts: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    error: str | None = None
    steps: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class FullAgentQualificationRunner:
    """Run the complete single-user local-to-Fabric qualification workflow."""

    def __init__(
        self,
        config: CloudConfig | None = None,
        *,
        state_path: str | Path | None = None,
        output_root: str | Path | None = None,
        cloud: FabricQualificationClient | None = None,
        publisher: FabricReportPublisher | None = None,
        renderer: PowerBIExportRenderer | None = None,
        reviewer: Callable[..., VisualReview] = review_rendered_report,
    ):
        self.config = config or CloudConfig.from_env()
        root = Path(output_root or os.getenv(
            "POWERBI_QUALIFICATION_ROOT", ".dashboard-workspaces/qualification"
        )).resolve()
        root.mkdir(parents=True, exist_ok=True)
        self.root = root
        self.store = QualificationStore(
            state_path
            or os.getenv(
                "POWERBI_QUALIFICATION_STATE_PATH",
                str(root / "qualification.sqlite3"),
            )
        )
        shared_tokens = EntraTokenProvider(self.config)
        self.cloud = cloud or FabricQualificationClient(self.config, shared_tokens)
        reliable_http = (
            RetryingCloudHttpClient(self.config)
            if publisher is None or renderer is None
            else None
        )
        self.publisher = publisher or FabricReportPublisher(
            self.config, shared_tokens, client=reliable_http
        )
        self.renderer = renderer or PowerBIExportRenderer(
            self.config, shared_tokens, client=reliable_http
        )
        self.reviewer = reviewer

    def run(self, max_visual_attempts: int = 3) -> QualificationResult:
        run_id = self.store.begin_run()
        # PBIR definition files contain deeply nested page/visual paths. Keep the
        # per-run artifact directory short so Windows does not hit MAX_PATH while
        # compiling a qualification report, while retaining the full UUID in the
        # durable qualification ledger.
        run_slug = run_id[:8]
        result = QualificationResult(
            run_id=run_id,
            status="RUNNING",
            workspace_id=self.config.workspace_id,
        )
        try:
            with self.store.step(run_id, "cloud_readiness") as detail:
                detail.update(self.cloud.check_workspace())

            with self.store.step(run_id, "semantic_model") as detail:
                known_model_id = self.store.resource(
                    self.config.workspace_id, "semantic_model", MODEL_DISPLAY_NAME
                )
                model = self.cloud.ensure_model(
                    MODEL_DISPLAY_NAME,
                    synthetic_model_definition(),
                    known_model_id,
                )
                result.semantic_model_id = model.semantic_model_id
                self.store.save_resource(
                    self.config.workspace_id,
                    "semantic_model",
                    MODEL_DISPLAY_NAME,
                    model.semantic_model_id,
                )
                detail.update(model.to_dict())

            with self.store.step(run_id, "semantic_model_refresh") as detail:
                detail.update(self.cloud.refresh_model(result.semantic_model_id))

            with self.store.step(run_id, "dax_validation") as detail:
                detail.update(self.cloud.execute_dax(result.semantic_model_id))

            with self.store.step(run_id, "local_report_qa") as detail:
                spec = synthetic_dashboard_spec(result.semantic_model_id)
                catalog = synthetic_catalog()
                semantic_issues = validate_dashboard_semantics(spec, catalog)
                blocking = [
                    item.to_dict()
                    for item in semantic_issues
                    if item.severity == "error"
                ]
                if blocking:
                    raise ValueError(f"synthetic report has semantic errors: {blocking}")
                compiled = compile_report(spec, self.root / "runs" / run_slug)
                validation = validate_pbir_project(compiled.report_path)
                if not validation.valid:
                    raise ValueError(
                        f"compiled qualification report is invalid: {validation.to_dict()}"
                    )
                manifest = build_preview_manifest(compiled.report_path)
                detail.update(
                    {
                        "report_path": compiled.report_path,
                        "pages": len(manifest.get("pages", [])),
                        "semantic_findings": len(semantic_issues),
                    }
                )

            with self.store.step(run_id, "report_publish") as detail:
                known_report_id = self.store.resource(
                    self.config.workspace_id, "report", REPORT_DISPLAY_NAME
                )
                report_id = known_report_id or self.cloud.find_report(
                    REPORT_DISPLAY_NAME
                )
                published: PublishResult = self.publisher.publish(
                    compiled.report_path,
                    REPORT_DISPLAY_NAME,
                    semantic_model_id=result.semantic_model_id,
                    report_id=report_id,
                )
                result.report_id = published.report_id
                self.store.save_resource(
                    self.config.workspace_id,
                    "report",
                    REPORT_DISPLAY_NAME,
                    published.report_id,
                )
                detail.update(published.to_dict())

            with self.store.step(run_id, "powerbi_render") as detail:
                rendered = self.renderer.render_report(
                    result.report_id, self.root / "renders" / run_slug
                )
                result.artifacts = list(rendered.artifacts)
                result.pages_rendered = len(rendered.artifacts)
                detail.update(
                    {
                        "provider": rendered.provider,
                        "artifacts": rendered.artifacts,
                        "warnings": rendered.warnings,
                        "metadata": rendered.metadata,
                    }
                )
                result.warnings.extend(rendered.warnings)

            with self.store.step(run_id, "visual_review") as detail:
                review = self.reviewer(
                    result.artifacts,
                    build_preview_manifest(compiled.report_path),
                )
                decision = decide_visual_qa_iteration(
                    review, attempt=1, max_attempts=max_visual_attempts
                )
                result.qa_attempts = 1
                detail.update(
                    {
                        "review": review.to_dict(),
                        "decision": decision.model_dump(),
                    }
                )
                if not review.approved:
                    result.warnings.append(review.summary)
                    result.status = (
                        "NEEDS_REVISION" if decision.should_revise else "NEEDS_REVIEW"
                    )
                else:
                    result.status = "VERIFIED"

            self.store.finish(run_id, result.status)
        except Exception as exc:
            result.status = "FAILED"
            result.error = str(exc)
            self.store.finish(run_id, result.status, result.error)
        finally:
            result.steps = self.store.steps(run_id)
            result.tests_passed = sum(
                item["status"] == "PASSED" for item in result.steps
            )
            result.tests_failed = sum(
                item["status"] == "FAILED" for item in result.steps
            )
        return result


def run_full_agent_qualification(max_visual_attempts: int = 3) -> dict[str, Any]:
    return FullAgentQualificationRunner().run(max_visual_attempts).to_dict()
