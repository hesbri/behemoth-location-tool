from __future__ import annotations
from pydantic import BaseModel, Field
from behemoth_location_tool.model.common import PivotMode, Rect, SavePolicy, TagQuery

class EntityManifest(BaseModel):
    version: int = 2
    includes: list[str] = Field(default_factory=list)

class EntityRenderData(BaseModel):
    sprite: str | None = None
    default_layer: str | None = Field(default=None, alias="defaultLayer")
    pivot_mode: PivotMode = Field(default=PivotMode.BOTTOM, alias="pivotMode")
    clickable_rect: Rect | None = Field(default=None, alias="clickableRect")
    model_config = {"populate_by_name": True}

class EntitySpawnRules(TagQuery):
    required_context_tags: list[str] = Field(default_factory=list, alias="requiredContextTags")
    forbidden_context_tags: list[str] = Field(default_factory=list, alias="forbiddenContextTags")
    exclusive_groups: list[str] = Field(default_factory=list, alias="exclusiveGroups")
    save_policy: SavePolicy = Field(default=SavePolicy.PERSISTENT, alias="savePolicy")

class EntityDefinition(BaseModel):
    id: str
    kind: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    render: EntityRenderData | None = None
    spawn_rules: EntitySpawnRules = Field(default_factory=EntitySpawnRules, alias="spawnRules")
    interactions: list[dict] = Field(default_factory=list)
    character: dict | None = None
    inventory: list[dict] = Field(default_factory=list)
    editor: dict = Field(default_factory=dict)
    model_config = {"populate_by_name": True}

class EntityModule(BaseModel):
    version: int = 2
    entities: list[EntityDefinition] = Field(default_factory=list)
