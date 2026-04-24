from __future__ import annotations
from pydantic import BaseModel, Field
from behemoth_location_tool.model.common import Rect, SavePolicy, TagQuery
from behemoth_location_tool.model.room import SocketDefinition

class ExitDefinition(TagQuery):
    id: str
    entity_id: str = Field(alias="entityId")
    target_location_id: str = Field(alias="targetLocationId")
    socket_id: str = Field(alias="socketId")
    layer: str = "exit_front"
    tags: list[str] = Field(default_factory=list)
    locked: bool = False
    clickable_rect: Rect | None = Field(default=None, alias="clickableRect")
    conditions: dict = Field(default_factory=dict)
    model_config = {"populate_by_name": True}

class PlacedEntity(BaseModel):
    instance_id: str = Field(alias="instanceId")
    entity_id: str = Field(alias="entityId")
    socket_id: str = Field(alias="socketId")
    layer: str | None = None
    sort_order: int = Field(default=0, alias="sortOrder")
    save_policy: SavePolicy = Field(default=SavePolicy.PERSISTENT, alias="savePolicy")
    placement_source: str = Field(default="manual", alias="placementSource")
    model_config = {"populate_by_name": True}

class GraphNode(BaseModel):
    location_id: str = Field(alias="locationId")
    x: int = 0
    y: int = 0
    model_config = {"populate_by_name": True}

class LocationGraph(BaseModel):
    nodes: list[GraphNode] = Field(default_factory=list)

class LocationInstance(TagQuery):
    id: str
    catalog_room_id: str = Field(alias="catalogRoomId")
    name: str
    description: str = ""
    background_image: str | None = Field(default=None, alias="backgroundImage")
    design_size: dict[str, int] = Field(default_factory=lambda: {"w": 1920, "h": 1080}, alias="designSize")
    tags: list[str] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    sockets: list[SocketDefinition] = Field(default_factory=list)
    exits: list[ExitDefinition] = Field(default_factory=list)
    placed_entities: list[PlacedEntity] = Field(default_factory=list, alias="placedEntities")
    model_config = {"populate_by_name": True}

class LocationsFile(BaseModel):
    version: int = 2
    start_location: str = Field(alias="startLocation")
    mansion_seed: int = Field(default=0, alias="mansionSeed")
    graph: LocationGraph = Field(default_factory=LocationGraph)
    locations: list[LocationInstance] = Field(default_factory=list)
    model_config = {"populate_by_name": True}
