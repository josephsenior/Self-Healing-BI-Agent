from __future__ import annotations

import json
from typing import Annotated, Literal

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    StringConstraints,
    field_validator,
    model_validator,
)

from .visual_capabilities import (
    VISUAL_CAPABILITIES,
    RoleCapability,
    VisualCapability,
)

Name = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=160)]
Content = Annotated[str, StringConstraints(strip_whitespace=True, min_length=1, max_length=10000)]
VisualType = Name


class FieldRef(BaseModel):
    model_config = ConfigDict(extra="forbid")
    table: Name
    name: Name
    kind: Literal["column", "measure"] = "column"

    @property
    def query_ref(self) -> str:
        return f"{self.table}.{self.name}"


class ButtonAction(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)
    action_type: Literal["webUrl", "pageNavigation"] = Field(alias="type")
    target: Content
    tooltip: Name | None = None

    @model_validator(mode="after")
    def validate_target(self) -> "ButtonAction":
        if self.action_type == "webUrl" and not self.target.startswith("https://"):
            raise ValueError("button webUrl targets must use https")
        return self


class CustomRoleDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    query_role: Name
    min_fields: int = Field(default=0, ge=0, le=20)
    max_fields: int = Field(default=20, ge=1, le=20)
    field_kind: Literal["column", "measure", "any"] = "any"

    @model_validator(mode="after")
    def valid_range(self) -> "CustomRoleDefinition":
        if self.min_fields > self.max_fields:
            raise ValueError("min_fields cannot exceed max_fields")
        return self


class CustomVisualDefinition(BaseModel):
    model_config = ConfigDict(extra="forbid")
    source: Literal["appsource", "organizational", "private"]
    trusted: Literal[True]
    installed: Literal[True]
    roles: dict[Name, CustomRoleDefinition]
    min_total_fields: int = Field(default=1, ge=0, le=20)


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
    fields: dict[Name, list[FieldRef]] = Field(default_factory=dict)
    content: Content | None = None
    font_size: int = Field(default=12, ge=6, le=72)
    font_color: str = "#000000"
    text_alignment: Literal["left", "center", "right"] = "left"
    shape_type: Literal["rectangle", "roundedRectangle", "oval", "line", "arrow"] | None = None
    image_url: str | None = None
    action: ButtonAction | None = None
    custom_visual: CustomVisualDefinition | None = None

    @field_validator("fields", mode="before")
    @classmethod
    def normalize_json_fields(cls, value: object) -> object:
        """Accept JSON-object strings emitted by tool-calling models."""
        if not isinstance(value, str):
            return value
        try:
            parsed = json.loads(value)
        except json.JSONDecodeError as exc:
            raise ValueError("fields must be a JSON object") from exc
        if not isinstance(parsed, dict):
            raise ValueError("fields must decode to a JSON object")
        return parsed

    def capability(self) -> VisualCapability:
        builtin = VISUAL_CAPABILITIES.get(self.visual_type)
        if builtin is not None:
            if self.custom_visual is not None:
                raise ValueError("custom_visual cannot override a built-in visual type")
            return builtin
        if self.custom_visual is None:
            raise ValueError(
                f"unsupported visual type {self.visual_type!r}; provide a trusted custom_visual adapter"
            )
        roles = {
            name: RoleCapability(
                item.query_role,
                item.min_fields,
                item.max_fields,
                item.field_kind,
            )
            for name, item in self.custom_visual.roles.items()
        }
        return VisualCapability(
            self.visual_type,
            "custom",
            roles,
            self.custom_visual.min_total_fields,
        )

    def resolved_fields(self) -> dict[str, list[FieldRef]]:
        """Return PBIR query-role names mapped to their field projections."""
        capability = self.capability()
        logical = {role: list(items) for role, items in self.fields.items()}
        legacy = (
            (capability.legacy_category_role, [self.category] if self.category else []),
            (capability.legacy_values_role, self.values),
            (capability.legacy_series_role, [self.series] if self.series else []),
        )
        for role_name, items in legacy:
            if not role_name or not items:
                continue
            if role_name in logical:
                raise ValueError(
                    f"role {role_name!r} is provided by both fields and a legacy field"
                )
            logical[role_name] = list(items)
        return {
            capability.roles[role_name].query_role: items
            for role_name, items in logical.items()
            if items
        }

    def fields_for_role(self, role_name: str) -> list[FieldRef]:
        capability = self.capability()
        return self.resolved_fields().get(capability.roles[role_name].query_role, [])

    @model_validator(mode="after")
    def validate_roles(self) -> "VisualSpec":
        capability = self.capability()
        unknown = set(self.fields) - set(capability.roles)
        if unknown:
            raise ValueError(
                f"{self.visual_type} does not support field roles: "
                + ", ".join(sorted(unknown))
            )
        resolved = self.resolved_fields()
        if sum(len(items) for items in resolved.values()) < capability.min_total_fields:
            raise ValueError(f"{self.visual_type} requires at least one field")
        for role_name, role in capability.roles.items():
            items = resolved.get(role.query_role, [])
            if len(items) < role.min_fields:
                raise ValueError(
                    f"{self.visual_type} role {role_name!r} requires at least "
                    f"{role.min_fields} field(s)"
                )
            if len(items) > role.max_fields:
                raise ValueError(
                    f"{self.visual_type} role {role_name!r} accepts at most "
                    f"{role.max_fields} field(s)"
                )
            if role.field_kind != "any" and any(
                item.kind != role.field_kind for item in items
            ):
                raise ValueError(
                    f"{self.visual_type} role {role_name!r} requires {role.field_kind}s"
                )
        if self.visual_type == "azureMap":
            has_latitude = bool(self.fields_for_role("latitude"))
            has_longitude = bool(self.fields_for_role("longitude"))
            if has_latitude != has_longitude:
                raise ValueError("azureMap latitude and longitude must be provided together")
        if self.visual_type == "textbox" and self.content is None:
            raise ValueError("textbox requires content")
        if self.visual_type == "basicShape" and self.shape_type is None:
            raise ValueError("basicShape requires shape_type")
        if self.visual_type == "actionButton" and self.action is None:
            raise ValueError("actionButton requires an action")
        if self.visual_type == "image":
            if not self.image_url and not self.fields_for_role("image"):
                raise ValueError("image requires image_url or an image field")
            if self.image_url and not self.image_url.startswith("https://"):
                raise ValueError("image_url must use https")
        canvas_types = {"textbox", "basicShape", "actionButton", "image"}
        if self.visual_type not in canvas_types and any(
            item is not None
            for item in (self.content, self.shape_type, self.image_url, self.action)
        ):
            raise ValueError("canvas content properties require a canvas visual type")
        if len(self.font_color) != 7 or not self.font_color.startswith("#"):
            raise ValueError("font_color must be a #RRGGBB color")
        try:
            int(self.font_color[1:], 16)
        except ValueError as exc:
            raise ValueError("font_color must be a #RRGGBB color") from exc
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
        page_names = {page.name.casefold() for page in self.pages}
        for page in self.pages:
            for visual in page.visuals:
                if (
                    visual.action
                    and visual.action.action_type == "pageNavigation"
                    and visual.action.target.casefold() not in page_names
                ):
                    raise ValueError(
                        f"button target page {visual.action.target!r} does not exist"
                    )
        return self
