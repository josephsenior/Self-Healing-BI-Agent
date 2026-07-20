from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from .models import DashboardSpec, FieldRef


class CatalogField(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    data_type: str = "unknown"
    hidden: bool = False
    distinct_count: int | None = Field(default=None, ge=0)


class CatalogTable(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str
    columns: list[CatalogField] = Field(default_factory=list)
    measures: list[CatalogField] = Field(default_factory=list)


class SemanticModelCatalog(BaseModel):
    model_config = ConfigDict(extra="forbid")
    tables: list[CatalogTable]

    def resolve(self, field: FieldRef) -> CatalogField | None:
        for table in self.tables:
            if table.name.casefold() != field.table.casefold():
                continue
            candidates = table.measures if field.kind == "measure" else table.columns
            return next(
                (item for item in candidates if item.name.casefold() == field.name.casefold()),
                None,
            )
        return None

    def has_table(self, name: str) -> bool:
        return any(table.name.casefold() == name.casefold() for table in self.tables)


@dataclass(frozen=True)
class SemanticIssue:
    severity: str
    code: str
    message: str
    page: str = ""
    visual: str = ""
    field: str = ""

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def validate_dashboard_semantics(
    spec: DashboardSpec,
    catalog: SemanticModelCatalog,
) -> list[SemanticIssue]:
    issues: list[SemanticIssue] = []
    for page in spec.pages:
        for visual in page.visuals:
            roles: list[tuple[str, FieldRef]] = []
            if visual.category:
                roles.append(("category", visual.category))
            if visual.series:
                roles.append(("series", visual.series))
            roles.extend(("value", field) for field in visual.values)

            for role, field in roles:
                address = field.query_ref
                if not catalog.has_table(field.table):
                    issues.append(SemanticIssue(
                        "error", "unknown_table", f"table {field.table!r} does not exist",
                        page.name, visual.title, address,
                    ))
                    continue
                metadata = catalog.resolve(field)
                if metadata is None:
                    issues.append(SemanticIssue(
                        "error", "unknown_field",
                        f"{field.kind} {address!r} does not exist",
                        page.name, visual.title, address,
                    ))
                    continue
                if metadata.hidden:
                    issues.append(SemanticIssue(
                        "warning", "hidden_field", f"{address!r} is hidden",
                        page.name, visual.title, address,
                    ))
                if role in {"category", "series"} and field.kind != "column":
                    issues.append(SemanticIssue(
                        "error", "invalid_role",
                        f"{role} requires a column, not a measure",
                        page.name, visual.title, address,
                    ))
                if role == "category" and metadata.distinct_count is not None:
                    limit = 30 if visual.visual_type != "slicer" else 200
                    if metadata.distinct_count > limit:
                        issues.append(SemanticIssue(
                            "warning", "high_cardinality",
                            f"{address!r} has {metadata.distinct_count} distinct values",
                            page.name, visual.title, address,
                        ))
                if role == "value" and field.kind == "column":
                    numeric = {"int64", "integer", "double", "decimal", "currency", "number"}
                    if metadata.data_type.casefold() not in numeric:
                        issues.append(SemanticIssue(
                            "warning", "non_numeric_value",
                            f"{address!r} is {metadata.data_type}, not numeric",
                            page.name, visual.title, address,
                        ))
    return issues
