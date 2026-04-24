from __future__ import annotations
from typing import Literal
from pydantic import BaseModel, Field, model_validator
from behemoth_location_tool.model.common import PivotMode, TagQuery, Transform2D

class WeightedEntityEntry(BaseModel):
    entity_id: str = Field(alias="entityId")
    weight: int
    model_config = {"populate_by_name": True}

class AmbientRule(BaseModel):
    mode: Literal["tag_query", "weighted_entity_list"] = "tag_query"
    required_tags: list[str] = Field(default_factory=list, alias="requiredTags")
    forbidden_tags: list[str] = Field(default_factory=list, alias="forbiddenTags")
    entries: list[WeightedEntityEntry] = Field(default_factory=list)
    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def validate_weighted_list(self) -> "AmbientRule":
        if self.mode == "weighted_entity_list" and self.entries:
            total = sum(entry.weight for entry in self.entries)
            if total != 100:
                raise ValueError(f"weighted_entity_list weights must sum to 100, got {total}")
        return self

class SocketDefinition(Transform2D, TagQuery):
    id: str
    name: str = ""
    description: str = ""
    pivot_mode: PivotMode = Field(default=PivotMode.BOTTOM, alias="pivotMode")
    layer: str = "characters"
    sort_order: int = Field(default=0, alias="sortOrder")
    ambient_spawn_chance: int = Field(default=0, alias="ambientSpawnChance", ge=0, le=100)
    ambient_rule: AmbientRule = Field(default_factory=AmbientRule, alias="ambientRule")
    allowed_entity_ids: list[str] = Field(default_factory=list, alias="allowedEntityIds")
    editor: dict = Field(default_factory=dict)
    model_config = {"populate_by_name": True}

class RoomCatalogEntry(TagQuery):
    id: str
    name: str
    description: str = ""
    background_image: str | None = Field(default=None, alias="backgroundImage")
    design_size: dict[str, int] = Field(default_factory=lambda: {"w": 1920, "h": 1080}, alias="designSize")
    tags: list[str] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    sockets: list[SocketDefinition] = Field(default_factory=list)
    model_config = {"populate_by_name": True}

class RoomCatalog(BaseModel):
    version: int = 2
    rooms: list[RoomCatalogEntry] = Field(default_factory=list)
