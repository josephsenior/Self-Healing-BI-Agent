"""Read-only BigQuery discovery and query helpers for dashboard authoring."""
from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Literal, Protocol

from pydantic import Field
from pydantic_settings import BaseSettings

from .report_authoring.desktop_version import detect_compatibility_level
from .report_authoring.semantic import CatalogField, CatalogTable, SemanticModelCatalog

_IDENTIFIER = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,1023}$")
_PROJECT_IDENTIFIER = re.compile(r"^[A-Za-z0-9][A-Za-z0-9-]{4,61}[A-Za-z0-9]$")
_READ_ONLY_SQL = re.compile(r"^(?:SELECT|WITH)\b", re.IGNORECASE)
_FORBIDDEN_SQL = re.compile(
    r"\b(?:INSERT|UPDATE|DELETE|MERGE|CREATE|ALTER|DROP|TRUNCATE|CALL|"
    r"EXPORT|LOAD|GRANT|REVOKE|EXTERNAL_QUERY)\b",
    re.IGNORECASE,
)
_QUOTED_RESOURCE = re.compile(
    r"`(?P<resource>[A-Za-z0-9_-]+(?:\.[A-Za-z0-9_-]+){2,})`"
)


def _validate_m_expression(expression: list[str]) -> None:
    """Fail closed on malformed generated Power Query M structure.

    This is intentionally a structural check rather than a full M parser: it
    catches the class of generator errors that Power BI reports only when a PBIP
    is opened (unbalanced delimiters, especially navigation records).
    """
    text = "\n".join(expression)
    pairs = {")": "(", "]": "[", "}": "{",
    }
    opening = set(pairs.values())
    stack: list[tuple[str, int]] = []
    in_string = False
    index = 0
    while index < len(text):
        char = text[index]
        if char == '"':
            if in_string and index + 1 < len(text) and text[index + 1] == '"':
                index += 2
                continue
            in_string = not in_string
        elif not in_string:
            if char in opening:
                stack.append((char, index))
            elif char in pairs:
                if not stack or stack[-1][0] != pairs[char]:
                    raise ValueError(
                        f"generated BigQuery M expression has an unexpected "
                        f"'{char}' at character {index}"
                    )
                stack.pop()
        index += 1
    if in_string:
        raise ValueError("generated BigQuery M expression has an unterminated string")
    if stack:
        delimiter, position = stack[-1]
        raise ValueError(
            f"generated BigQuery M expression has an unclosed '{delimiter}' "
            f"at character {position}"
        )
    if not expression or expression[0].strip().lower() != "let" or not any(
        line.strip().lower() == "in" for line in expression
    ):
        raise ValueError("generated BigQuery M expression must contain let/in")


def _validate_model_definition(model: dict[str, Any]) -> None:
    """Validate every M partition before a semantic model reaches PBIP."""
    if not isinstance(model, dict) or not isinstance(model.get("model"), dict):
        raise ValueError("generated semantic model has no model definition")
    tables = model["model"].get("tables", [])
    if not isinstance(tables, list) or not tables:
        raise ValueError("generated semantic model has no tables")
    for table in tables:
        for partition in table.get("partitions", []):
            source = partition.get("source", {})
            if source.get("type") != "m":
                continue
            expression = source.get("expression")
            if not isinstance(expression, list) or not all(
                isinstance(line, str) for line in expression
            ):
                raise ValueError(
                    f"semantic model partition {partition.get('name', '')!r} "
                    "has an invalid M expression"
                )
            _validate_m_expression(expression)


def _infer_measure_format(measure: dict[str, str]) -> str | None:
    """Infer formatString for a measure based on name and expression patterns.

    Returns a Power BI format string (e.g. "0.0%") for common ratio/percentage
    patterns, or None if no inference is possible. This prevents measures like
    "Margin %" from rendering as 0.72 instead of 72.0%.
    """
    name = measure.get("name", "").casefold()
    expression = measure.get("expression", "").casefold()
    # Percentage patterns: name contains %, rate, ratio, margin %, etc.
    pct_name_tokens = ("%", "rate", "ratio", "margin percent", "growth")
    if any(token in name for token in pct_name_tokens):
        return "0.0%"
    # DIVIDE() in expression strongly implies a ratio/percentage
    if "divide(" in expression:
        return "0.0%"
    return None


class BigQuerySettings(BaseSettings):
    project_id: str = Field(default="", alias="BIGQUERY_PROJECT_ID")
    location: str = Field(default="", alias="BIGQUERY_LOCATION")
    allowed_datasets: str = Field(default="", alias="BIGQUERY_ALLOWED_DATASETS")
    max_bytes_billed: int = Field(default=1_000_000_000, alias="BIGQUERY_MAX_BYTES_BILLED", ge=1)
    max_rows: int = Field(default=1_000, alias="BIGQUERY_MAX_ROWS", ge=1, le=10_000)
    powerbi_implementation: Literal["1.0", "2.0"] = Field(
        default="2.0", alias="BIGQUERY_POWERBI_IMPLEMENTATION"
    )
    powerbi_use_storage_api: bool = Field(
        default=False, alias="BIGQUERY_POWERBI_USE_STORAGE_API"
    )

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


@dataclass(frozen=True)
class PowerBIModelBinding:
    semantic_model_path: str
    table: str
    storage_mode: str
    connector_implementation: str
    uses_storage_api: bool
    catalog: dict[str, Any]
    requires_powerbi_credentials: bool = True

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


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
        if not allowed:
            raise PermissionError("BIGQUERY_ALLOWED_DATASETS must be configured")
        if dataset_key not in allowed:
            raise PermissionError(f"dataset {dataset_key!r} is not in BIGQUERY_ALLOWED_DATASETS")

    def _ensure_quoted_resources_allowed(self, sql: str) -> None:
        """Fail closed on explicit fully qualified resources before BigQuery sees SQL."""
        for match in _QUOTED_RESOURCE.finditer(sql):
            parts = match.group("resource").split(".")
            if len(parts) == 3:
                project, dataset, resource = parts
            elif len(parts) == 4 and parts[-2].upper() == "INFORMATION_SCHEMA":
                project, dataset, resource = parts[0], parts[1], parts[-1]
            else:
                raise ValueError(
                    "quoted BigQuery resources must be project.dataset.resource"
                )
            ref = TableReference(
                _identifier(project, "project", _PROJECT_IDENTIFIER),
                _identifier(dataset, "dataset"),
                _identifier(resource, "resource"),
            )
            self._ensure_allowed(ref)

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
        return self._catalog_from_schema(ref, resource.schema)

    def create_powerbi_model(
        self,
        table: str,
        output_root: str | Path,
        storage_mode: Literal["import", "directQuery", "embedded"] = "directQuery",
        measures: list[dict[str, str]] | None = None,
    ) -> PowerBIModelBinding:
        """Create a PBIP semantic model bound to one BigQuery table.

        storage_mode:
        - "import" / "directQuery": live Power Query connector to BigQuery.
          Cloud (Fabric) renders require data-source credentials/gateway.
        - "embedded": rows are snapshotted into the model as a calculated
          table with no external data source, so Fabric renders work without
          any cloud credentials. Bounded by BIGQUERY_MAX_ROWS.
        """
        normalized_mode = str(storage_mode).strip().replace("-", "").replace("_", "").casefold()
        storage_modes = {
            "import": "import",
            "directquery": "directQuery",
            "embedded": "embedded",
        }
        if normalized_mode not in storage_modes:
            raise ValueError("storage_mode must be 'import', 'directQuery', or 'embedded'")
        storage_mode = storage_modes[normalized_mode]
        ref = self.table(table)
        resource = self.client.get_table(ref.full_name)
        fields = list(resource.schema)
        if not fields:
            raise ValueError(f"BigQuery table {ref.full_name!r} has no columns")
        catalog = self._catalog_from_schema(ref, fields, measures=measures)
        model_dir = (
            Path(output_root).resolve()
            / f"{ref.project}__{ref.dataset}__{ref.table}.SemanticModel"
        )
        model_dir.mkdir(parents=True, exist_ok=True)

        # Auto-detect formatString for measures that lack one (e.g. percentage ratios)
        normalized_measures = None
        if measures:
            normalized_measures = []
            for m in measures:
                entry = dict(m)
                if "formatString" not in entry:
                    inferred = _infer_measure_format(entry)
                    if inferred:
                        entry["formatString"] = inferred
                normalized_measures.append(entry)

        if storage_mode == "embedded":
            model = self._embedded_model(ref, fields, catalog, measures=normalized_measures)
        else:
            model = self._connector_model(ref, fields, storage_mode, measures=normalized_measures)

        _validate_model_definition(model)
        self._write_json(
            model_dir / "definition.pbism",
            {
                "$schema": (
                    "https://developer.microsoft.com/json-schemas/fabric/item/"
                    "semanticModel/definitionProperties/1.0.0/schema.json"
                ),
                "version": "4.2",
                "settings": {"qnaEnabled": True},
            },
        )
        self._write_json(model_dir / "model.bim", model)
        self._write_json(
            model_dir / "bigquery-binding.json",
            {
                "billing_project": self.settings.project_id,
                "source": ref.full_name,
                "storage_mode": storage_mode,
                "connector_implementation": (
                    "none" if storage_mode == "embedded"
                    else self.settings.powerbi_implementation
                ),
                "uses_storage_api": (
                    False if storage_mode == "embedded"
                    else self.settings.powerbi_use_storage_api
                ),
                "credential_material_embedded": storage_mode == "embedded",
            },
        )
        return PowerBIModelBinding(
            semantic_model_path=str(model_dir),
            table=ref.full_name,
            storage_mode=storage_mode,
            connector_implementation=(
                "none" if storage_mode == "embedded"
                else self.settings.powerbi_implementation
            ),
            uses_storage_api=(
                False if storage_mode == "embedded"
                else self.settings.powerbi_use_storage_api
            ),
            requires_powerbi_credentials=storage_mode != "embedded",
            catalog=catalog.model_dump(),
        )

    def _connector_model(
        self, ref: TableReference, fields: Any, storage_mode: str,
        measures: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Build a live Power Query model bound to the BigQuery connector."""
        options = [
            f'BillingProject="{self.settings.project_id}"',
            f'Implementation="{self.settings.powerbi_implementation}"',
            "UseStorageApi="
            + ("true" if self.settings.powerbi_use_storage_api else "false"),
        ]
        m_expression = [
            "let",
            f"    Source = GoogleBigQuery.Database([{', '.join(options)}]),",
            f'    Project = Source{{[Name="{ref.project}"]}}[Data],',
            (
                f'    Dataset = Project{{[Name="{ref.dataset}", '
                'Kind="Schema"]}[Data],'
            ),
            (
                f'    SelectedTable = Dataset{{[Name="{ref.table}", '
                'Kind="Table"]}[Data]'
            ),
            "in",
            "    SelectedTable",
        ]
        _validate_m_expression(m_expression)
        columns = []
        for field in fields:
            column = {
                "name": field.name,
                "dataType": self._tabular_type(field.field_type),
                "sourceColumn": field.name,
                "summarizeBy": "none",
            }
            if field.field_type.upper() == "DATE":
                column["formatString"] = "yyyy-MM-dd"
            columns.append(column)

        return {
            "name": f"{ref.table} BigQuery Model",
            "compatibilityLevel": detect_compatibility_level(),
            "model": {
                "culture": "en-US",
                "defaultPowerBIDataSourceVersion": "powerBI_V3",
                "discourageImplicitMeasures": True,
                "tables": [
                    {
                        "name": ref.table,
                        "description": f"BigQuery source {ref.full_name}",
                        "columns": columns,
                        "partitions": [
                            {
                                "name": ref.table,
                                "mode": storage_mode,
                                "source": {
                                    "type": "m",
                                    "expression": m_expression,
                                },
                            }
                        ],
                        "measures": measures or [],
                    }
                ],
            },
        }

    def _embedded_model(
        self,
        ref: TableReference,
        fields: Any,
        catalog: SemanticModelCatalog,
        measures: list[dict[str, str]] | None = None,
    ) -> dict[str, Any]:
        """Build a data-source-free model with rows embedded as a calculated table.

        The calculated table uses ROW()/UNION() expressions, the same technique
        the cloud qualification runner uses: Fabric accepts it consistently when
        a TMSL definition is created through the public API, and the model needs
        no gateway, credentials, or refresh. Bounded by BIGQUERY_MAX_ROWS.
        """
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise RuntimeError(
                "BigQuery support requires google-cloud-bigquery; run pip install -r requirements.txt"
            ) from exc
        job = self.client.query(
            f"SELECT * FROM `{ref.full_name}`",
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=self.settings.max_bytes_billed,
                use_legacy_sql=False,
            ),
            location=self.settings.location or None,
        )
        rows = list(job.result(max_results=self.settings.max_rows))
        if not rows:
            raise ValueError(f"BigQuery table {ref.full_name!r} returned no rows to embed")

        def m_literal(value: Any, field_type: str) -> str:
            if value is None:
                return "null"
            normalized = field_type.upper()
            if normalized == "DATE":
                if hasattr(value, "strftime"):
                    return f'"{value.strftime("%Y-%m-%d")}"'
                return f'"{str(value)}"'
            if normalized in {"DATETIME", "TIMESTAMP"}:
                if hasattr(value, "strftime"):
                    return f'"{value.strftime("%Y-%m-%d %H:%M:%S")}"'
                return f'"{str(value)}"'
            if isinstance(value, bool):
                return "true" if value else "false"
            if isinstance(value, (int, float)):
                return repr(value)
            return f'"{str(value).replace(chr(34), chr(34) * 2)}"'

        row_expressions = [
            "ROW("
            + ", ".join(
                f'"{field.name}", {m_literal(row[field.name], field.field_type)}'
                for field in fields
            )
            + ")"
            for row in rows
        ]
        if len(row_expressions) == 1:
            expression = row_expressions[0]
        else:
            expression = "UNION(" + ", ".join(row_expressions) + ")"

        columns = []
        for field in fields:
            column = {
                "type": "calculatedTableColumn",
                "name": field.name,
                "dataType": self._tabular_type(field.field_type),
                "sourceColumn": f"[{field.name}]",
                "summarizeBy": "none",
            }
            if field.field_type.upper() == "DATE":
                column["formatString"] = "yyyy-MM-dd"
            columns.append(column)

        return {
            "name": f"{ref.table} BigQuery Model",
            "compatibilityLevel": detect_compatibility_level(),
            "model": {
                "culture": "en-US",
                "defaultPowerBIDataSourceVersion": "powerBI_V3",
                "discourageImplicitMeasures": True,
                "tables": [
                    {
                        "name": ref.table,
                        "description": (
                            f"Embedded snapshot of {ref.full_name} "
                            f"({len(rows)} rows, no external data source)"
                        ),
                        "columns": columns,
                        "partitions": [
                            {
                                "name": ref.table,
                                "mode": "import",
                                "source": {
                                    "type": "calculated",
                                    "expression": expression,
                                },
                            }
                        ],
                        "measures": measures or [],
                    }
                ],
            },
        }

    def query(self, sql: str, max_rows: int | None = None) -> dict[str, Any]:
        normalized = sql.strip()
        if ";" in normalized or not _READ_ONLY_SQL.match(normalized) or _FORBIDDEN_SQL.search(normalized):
            raise ValueError("only a single read-only SELECT or WITH query is allowed")
        self._ensure_quoted_resources_allowed(normalized)
        row_limit = min(max_rows or self.settings.max_rows, self.settings.max_rows)
        try:
            from google.cloud import bigquery
        except ImportError as exc:
            raise RuntimeError("BigQuery support requires google-cloud-bigquery; run pip install -r requirements.txt") from exc
        dry_run = self.client.query(
            normalized,
            job_config=bigquery.QueryJobConfig(
                dry_run=True,
                use_query_cache=False,
                maximum_bytes_billed=self.settings.max_bytes_billed,
                use_legacy_sql=False,
            ),
            location=self.settings.location or None,
        )
        referenced_tables = []
        for table_ref in getattr(dry_run, "referenced_tables", None) or []:
            ref = TableReference(
                str(table_ref.project),
                str(table_ref.dataset_id),
                str(table_ref.table_id),
            )
            self._ensure_allowed(ref)
            referenced_tables.append(ref.full_name)

        job = self.client.query(
            normalized,
            job_config=bigquery.QueryJobConfig(
                maximum_bytes_billed=self.settings.max_bytes_billed,
                use_legacy_sql=False,
            ),
            location=self.settings.location or None,
        )
        iterator = job.result(max_results=row_limit)
        fields = [field.name for field in iterator.schema]
        rows = [
            {name: _json_value(row[name]) for name in fields}
            for row in iterator
        ]
        return {
            "columns": fields,
            "rows": rows,
            "row_count": len(rows),
            "referenced_tables": referenced_tables,
            "total_bytes_processed": getattr(job, "total_bytes_processed", None),
            "total_bytes_billed": getattr(job, "total_bytes_billed", None),
            "limited_to": row_limit,
        }

    def _catalog_from_schema(
        self, ref: TableReference, fields: Any,
        measures: list[dict[str, str]] | None = None,
    ) -> SemanticModelCatalog:
        columns = [CatalogField(name=field.name, data_type=self._powerbi_type(field.field_type)) for field in fields]
        measure_fields = [CatalogField(name=m["name"], data_type="measure") for m in (measures or [])]
        return SemanticModelCatalog(tables=[CatalogTable(name=ref.table, columns=columns, measures=measure_fields)])

    @staticmethod
    def _schema_field(field: Any) -> dict[str, Any]:
        return {"name": field.name, "type": field.field_type, "mode": getattr(field, "mode", "NULLABLE"), "description": getattr(field, "description", None), "fields": [BigQueryService._schema_field(child) for child in getattr(field, "fields", ())]}

    @staticmethod
    def _powerbi_type(bigquery_type: str) -> str:
        return {"INTEGER": "int64", "INT64": "int64", "FLOAT": "double", "FLOAT64": "double", "NUMERIC": "decimal", "BIGNUMERIC": "decimal", "BOOL": "boolean", "DATE": "date", "DATETIME": "datetime", "TIMESTAMP": "datetime", "TIME": "time", "STRING": "string", "BYTES": "binary"}.get(bigquery_type.upper(), bigquery_type.lower())

    @staticmethod
    def _tabular_type(bigquery_type: str) -> str:
        return {
            "INTEGER": "int64", "INT64": "int64",
            "FLOAT": "double", "FLOAT64": "double",
            "NUMERIC": "decimal", "BIGNUMERIC": "decimal",
            "BOOL": "boolean", "BOOLEAN": "boolean",
            "DATE": "dateTime", "DATETIME": "dateTime", "TIMESTAMP": "dateTime",
            "BYTES": "binary",
        }.get(bigquery_type.upper(), "string")

    @staticmethod
    def _write_json(path: Path, value: dict[str, Any]) -> None:
        path.write_text(
            json.dumps(value, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
