from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, Field


class PivotMode(StrEnum):
    BOTTOM = "bottom"
    CENTER = "center"
    SPAWNABLE_DEFAULT = "spawnable_default"


class SavePolicy(StrEnum):
    PERSISTENT = "persistent"
    TRANSIENT = "transient"
    REGENERATE_ON_NEW_GAME = "regenerate_on_new_game"


class Rect(BaseModel):
    x: int = 0
    y: int = 0
    w: int = 0
    h: int = 0


class Transform2D(BaseModel):
    x: int = 0
    y: int = 0
    rotation: float = 0.0
    scale: float = 1.0


class DesignSize(BaseModel):
    w: int = 1920
    h: int = 1080


class Pivot(BaseModel):
    mode: PivotMode = PivotMode.BOTTOM
    x: int = 0
    y: int = 0


class TagQuery(BaseModel):
    required_tags: list[str] = Field(default_factory=list, alias="requiredTags")
    forbidden_tags: list[str] = Field(default_factory=list, alias="forbiddenTags")

    model_config = {"populate_by_name": True}


# Default render layer order from the spec (section 7.2).
# Used when a room uses "project_default" layer mode.
DEFAULT_LAYERS: list[str] = [
    "background",
    "exterior_view",
    "back_wall",
    "exit_behind",
    "back_props",
    "characters",
    "front_props",
    "exit_front",
    "foreground",
]


class Conditions(BaseModel):
    requires_tags: list[str] = Field(default_factory=list, alias="requiresTags")
    forbidden_tags: list[str] = Field(default_factory=list, alias="forbiddenTags")
    requires_flags: list[str] = Field(default_factory=list, alias="requiresFlags")
    forbidden_flags: list[str] = Field(default_factory=list, alias="forbiddenFlags")

    model_config = {"populate_by_name": True}