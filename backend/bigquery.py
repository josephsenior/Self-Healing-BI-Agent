"""Read-only BigQuery discovery and query helpers for dashboard authoring."""
from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any, Protocol

from pydantic import Field
from pydantic_settings import BaseSettings

from .report_authoring.semantic import CatalogField, CatalogTable, SemanticModelCatalog

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
_PROJECT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{4,61}[A-Za-z0-9]$")
_READ_ONLY_SQL = re.compile(r"^(?:SELECT|WITH)\b", re.IGNORECASE)
_FORBIDDEN_SQL = re.compile(r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|CALL|EXPORT|LOAD|GRANT|REVOKE)\b", re.IGNORECASE)


class BigQuerySettings(BaseSettings):
    project_id: str = Field(default="", alias="BIGQUERY_PROJECT_ID")
    location: str = Field(default="", alias="BIGQUERY_LOCATION")
    allowed_datasets: str = Field(default="", alias="BIGQUERY_ALLOWED_DATASETS")
    max_bytes_billed: int = Field(default=1_000_000_000, alias="BIGQUERY_MAX_BYTES_BILLED", ge=1)
    max_rows: int = Field(default=1_000, alias="BIGQUERY_MAX_ROWS", ge=1, le=10_000)

    model_config = {"env_file": ".env", "extra": "ignore", "populate_by_name": True}

    @property
    def allowlist(self) -> set[str]:
        return {item.strip().lower() for item in self.allowed_datasets.split(",") if item.strip()}


class BigQueryClient(Protocol):
    def get_table(self, table: str) -> Any: ...
    def list_tables(self, dataset: str) -> Any: ...
    def query(self, sql: str, **kwargs: Any) -> Any: ...


@dataclass(frozen=True)
class TableReference:
    project: str
    dataset: str
    table: str

    @property
    def full_name(self) -> str:
        return f"{self.project}.{self.dataset}.{self.table}"


def _identifier(value: str, kind: str, pattern: re.Pattern[str] = _IDENTIFIER) -> str:
    if not pattern.fullmatch(value):
        raise ValueError(f"invalid BigQuery {kind}: {value!r}")
    return value


def parse_table_reference(value: str, default_project: str) -> TableReference:
    parts = value.strip().strip("`").split(".")
    if len(parts) == 2:
        project, dataset, table = default_project, *parts
    elif len(parts) == 3:
        project, dataset, table = parts
    else:
        raise ValueError("table must be dataset.table or project.dataset.table")
    return TableReference(_identifier(project, "project", _PROJECT_IDENTIFIER), _identifier(dataset, "dataset"), _identifier(table, "table"))


def _json_value(value: Any) -> Any:
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(key): _json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_value(item) for item in value]
    return str(value)


class BigQueryService:
    """Bounded, read-only facade over the official BigQuery Python client."""

    def __init__(self, settings: BigQuerySettings | None = None, client: BigQueryClient | None = None):
        self.settings = settings or BigQuerySettings()
        if not self.settings.project_id:
            raise ValueError("BIGQUERY_PROJECT_ID must be configured")
        self._client = client

    @property
    def client(self) -> BigQueryClient:
        if self._client is None:
            try:
                from google.cloud import bigquery
            except ImportError as exc:
                raise RuntimeError("BigQuery support requires google-cloud-bigquery; run pip install -r requirements.txt") from exc
            self._client = bigquery.Client(project=self.settings.project_id)
        return self._client

    def _ensure_allowed(self, ref: TableReference) -> None:
        allowed = self.settings.allowlist
        dataset_key = f"{ref.project}.{ref.dataset}".lower()
        if allowed and dataset_key not in allowed:
            raise PermissionError(f"dataset {dataset_key!r} is not in BIGQUERY_ALLOWED_DATASETS")

    def table(self, value: str) -> TableReference:
        ref = parse_table_reference(value, self.settings.project_id)
        self._ensure_allowed(ref)
        return ref

    def list_tables(self, dataset: str) -> list[dict[str, str]]:
        ref = self.table(f"{dataset}.__placeholder__")
        return [{"project": ref.project, "dataset": ref.dataset, "table": item.table_id, "type": item.table_type} for item in self.client.list_tables(f"{ref.project}.{ref.dataset}")]

    def schema(self, table: str) -> list[dict[str, Any]]:
        resource = self.client.get_table(self.table(table).full_name)
        return [self._schema_field(field) for field in resource.schema]

    def catalog(self, table: str) -> SemanticModelCatalog:
        ref = self.table(table)
        resource = self.client.get_table(ref.full_name)
        return SemanticModelCatalog(tables=[CatalogTable(name=ref.table, columns=[CatalogField(name=field.name, data_type=self._powerbi_type(field.field_type)) for field in resource.schema])])

    def query(self, sql: str, max_rows: int | None = None) -> dict[str, Any]:
        normalized = sql.strip()
        if ";" in normalized or not _READ_ONLY_SQL.match(normalized) or _FORBIDDEN_SQL.search(normalized):
            raise ValueError("only a single read-only SELECT or WITH query is allowed")
        row_limit = min(max_rows or self.settings.max_rows, self.settings.max_rows)
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise RuntimeError("BigQuery support requires google-cloud-bigquery; run pip install -r requirements.txt") from exc
        job = self.client.query(normalized, job_config=bigquery.QueryJobConfig(maximum_bytes_billed=self.settings.max_bytes_billed, use_legacy_sql=False), location=self.settings.location or None)
        iterator = job.result(max_results=row_limit)
        fields = [field.name for field in iterator.schema]
        return {"columns": fields, "rows": [{name: _json_value(row[name]) for name in fields} for row in iterator], "row_count": 0, "total_bytes_processed": getattr(job, "total_bytes_processed", None), "total_bytes_billed": getattr(job, "total_bytes_billed", None), "limited_to": row_limit}

    @staticmethod
    def _schema_field(field: Any) -> dict[str, Any]:
        return {"name": field.name, "type": field.field_type, "mode": getattr(field, "mode", "NULLABLE"), "description": getattr(field, "description", None), "fields": [BigQueryService._schema_field(child) for child in getattr(field, "fields", ())]}

    @staticmethod
    def _powerbi_type(bigquery_type: str) -> str:
        return {"INTEGER": "int64", "INT64": "int64", "FLOAT": "double", "FLOAT64": "double", "NUMERIC": "decimal", "BIGNUMERIC": "decimal", "BOOL": "boolean", "DATE": "date", "DATETIME": "datetime", "TIMESTAMP": "datetime", "TIME": "time", "STRING": "string", "BYTES": "binary"}.get(bigquery_type.upper(), bigquery_type.lower())
