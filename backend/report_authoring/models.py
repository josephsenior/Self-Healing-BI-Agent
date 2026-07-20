from __future__ import annotations

from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
VisualType = Literal[
    "barChart", "clusteredColumnChart", "lineChart", "donutChart",
    "card", "tableEx", "slicer",
]


class FieldRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: Name
    name: Name
    kind: Literal["column", "measure"] = "column"

    @property
    def query_ref(self) -> str:
        return f"{self.table}.{self.name}"


class GridPosition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    column: int = Field(ge=0, le=11)
    row: int = Field(ge=0, le=11)
    width: int = Field(ge=1, le=12)
    height: int = Field(ge=1, le=12)

    @model_validator(mode="after")
    def fits_grid(self) -> "GridPosition":
        if self.column + self.width > 12:
            raise ValueError("visual extends beyond the 12-column grid")
        return self


class VisualSpec(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    visual_type: VisualType = Field(alias="type")
    title: Name
    position: GridPosition
    category: FieldRef | None = None
    values: list[FieldRef] = Field(default_factory=list, max_length=20)
    series: FieldRef | None = None

    @model_validator(mode="after")
    def validate_roles(self) -> "VisualSpec":
        category_types = {
            "barChart", "clusteredColumnChart", "lineChart", "donutChart"
        }
        if self.visual_type in category_types and self.category is None:
            raise ValueError(f"{self.visual_type} requires a category field")
        if self.visual_type in category_types | {"card", "tableEx"} and not self.values:
            raise ValueError(f"{self.visual_type} requires at least one value")
        if self.visual_type == "card" and len(self.values) != 1:
            raise ValueError("card requires exactly one value")
        if self.visual_type == "slicer":
            if self.category is None:
                raise ValueError("slicer requires a category field")
            if self.values or self.series:
                raise ValueError("slicer only accepts a category field")
        if self.series and self.visual_type not in {
            "barChart", "clusteredColumnChart", "lineChart"
        }:
            raise ValueError(f"{self.visual_type} does not support a series field")
        return self


class PageSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: Name
    display_name: Name | None = None
    visuals: list[VisualSpec] = Field(min_length=1, max_length=30)
    width: int = Field(default=1280, ge=320, le=3840)
    height: int = Field(default=720, ge=240, le=2160)
    display_option: Literal["FitToPage", "FitToWidth", "ActualSize"] = "FitToPage"

    @model_validator(mode="after")
    def unique_visual_titles(self) -> "PageSpec":
        titles = [visual.title.casefold() for visual in self.visuals]
        if len(titles) != len(set(titles)):
            raise ValueError("visual titles must be unique within a page")
        return self


class DatasetReference(BaseModel):
    model_config = ConfigDict(extra="forbid")
    path: str | None = None
    semantic_model_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_target(self) -> "DatasetReference":
        if bool(self.path) == bool(self.semantic_model_id):
            raise ValueError("provide exactly one of path or semantic_model_id")
        if self.path:
            normalized = self.path.replace("\\", "/")
            if normalized.startswith("/") or ":" in normalized:
                raise ValueError("semantic model path must be relative")
        return self


class DashboardSpec(BaseModel):
    """Strict intermediate representation produced by the planning agent."""

    model_config = ConfigDict(extra="forbid")
    title: Name
    dataset: DatasetReference
    pages: list[PageSpec] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def unique_pages(self) -> "DashboardSpec":
        names = [page.name.casefold() for page in self.pages]
        if len(names) != len(set(names)):
            raise ValueError("page names must be unique")
        return self
