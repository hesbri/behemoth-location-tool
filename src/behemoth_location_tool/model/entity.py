from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from behemoth_location_tool.model.common import Pivot, Rect, SavePolicy


class InteractionEffectDefinition(BaseModel):
    effect: str = ""
    params: dict[str, str] = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class InteractionDefinition(BaseModel):
    type: str = ""
    needs_tags: list[str] = Field(default_factory=list, alias="needs_tags")
    effects: list[InteractionEffectDefinition] = Field(default_factory=list)

    model_config = {"populate_by_name": True}


class EntityRenderData(BaseModel):
    sprite: str | None = None
    default_layer: str | None = Field(default=None, alias="defaultLayer")
    pivot: Pivot = Field(default_factory=Pivot)
    clickable_rect: Rect | None = Field(default=None, alias="clickableRect")

    model_config = {"populate_by_name": True}


class EntitySpawnRules(BaseModel):
    required_context_tags: list[str] = Field(default_factory=list, alias="requiredContextTags")
    forbidden_context_tags: list[str] = Field(default_factory=list, alias="forbiddenContextTags")
    exclusive_groups: list[str] = Field(default_factory=list, alias="exclusiveGroups")
    save_policy: SavePolicy = Field(default=SavePolicy.PERSISTENT, alias="savePolicy")

    model_config = {"populate_by_name": True}


class EntityDefinition(BaseModel):
    id: str
    kind: str
    name: str
    description: str = ""
    tags: list[str] = Field(default_factory=list)
    render: EntityRenderData | None = None
    spawn_rules: EntitySpawnRules = Field(default_factory=EntitySpawnRules, alias="spawnRules")
    interactions: list[InteractionDefinition] = Field(default_factory=list)
    character: dict | None = None
    inventory: list[dict] = Field(default_factory=list)
    editor: dict = Field(default_factory=dict)

    model_config = {"populate_by_name": True}


class EntityModule(BaseModel):
    version: int = Field(default=2, alias="version")
    entities: list[EntityDefinition] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _require_v2(self) -> EntityModule:
        if self.version != 2:
            raise ValueError(f"Unsupported entity module version {self.version}; expected version 2")
        return self


class EntityManifest(BaseModel):
    version: int = Field(default=2, alias="version")
    includes: list[str] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _require_v2(self) -> EntityManifest:
        if self.version != 2:
            raise ValueError(f"Unsupported entity manifest version {self.version}; expected version 2")
        return self
