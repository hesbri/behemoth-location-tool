from __future__ import annotations

from pydantic import BaseModel, Field, model_validator

from behemoth_location_tool.model.common import Conditions, DesignSize, Rect, SavePolicy
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition


class ExitDefinition(BaseModel):
    id: str
    entity_id: str = Field(alias="entityId")
    target_location_id: str = Field(alias="targetLocationId")
    socket_id: str = Field(alias="socketId")
    layer: str = "exit_front"
    tags: list[str] = Field(default_factory=list)
    locked: bool = False
    clickable_rect: Rect | None = Field(default=None, alias="clickableRect")
    conditions: Conditions = Field(default_factory=Conditions)

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

    model_config = {"populate_by_name": True}


class LocationInstance(BaseModel):
    id: str
    catalog_room_id: str = Field(alias="catalogRoomId")
    name: str
    description: str = ""
    background_image: str | None = Field(default=None, alias="backgroundImage")
    background_overridden: bool = Field(default=False, alias="backgroundOverridden")
    design_size: DesignSize = Field(default_factory=DesignSize, alias="designSize")
    tags: list[str] = Field(default_factory=list)
    layers: list[str] = Field(default_factory=list)
    socket_overridden: bool = Field(default=False, alias="socketOverridden")
    sockets: list[SocketDefinition] = Field(default_factory=list)
    exits: list[ExitDefinition] = Field(default_factory=list)
    placed_entities: list[PlacedEntity] = Field(default_factory=list, alias="placedEntities")

    model_config = {"populate_by_name": True}


class LocationsFile(BaseModel):
    version: int = Field(default=2, alias="version")
    start_location: str = Field(alias="startLocation")
    mansion_seed: int = Field(default=0, alias="mansionSeed")
    graph: LocationGraph = Field(default_factory=LocationGraph)
    locations: list[LocationInstance] = Field(default_factory=list)

    model_config = {"populate_by_name": True}

    @model_validator(mode="after")
    def _require_v2(self) -> LocationsFile:
        if self.version != 2:
            raise ValueError(f"Unsupported locations file version {self.version}; expected version 2")
        return self


# ---- Background inheritance helpers ----

def find_catalog_room(catalog: RoomCatalog | None, catalog_room_id: str) -> RoomCatalogEntry | None:
    """Find a room in the catalog by ID."""
    if catalog is None:
        return None
    for room in catalog.rooms:
        if room.id == catalog_room_id:
            return room
    return None


def get_effective_background(
    location: LocationInstance,
    catalog: RoomCatalog | None,
) -> str | None:
    """Return the effective background image for a location.

    If background is explicitly overridden, use the location's own value.
    Otherwise, inherit from the catalog room entry.
    Falls back to location.background_image if catalog is unavailable.
    """
    if location.background_overridden:
        return location.background_image
    room = find_catalog_room(catalog, location.catalog_room_id)
    if room is not None:
        return room.background_image
    return location.background_image


def migrate_location_background(
    location: LocationInstance,
    catalog: RoomCatalog | None,
) -> None:
    """Backfill override metadata for locations that lack it.

    Rules:
    - If background_overridden is already True, do nothing.
    - If background_image is None or empty, do nothing (inherited/none).
    - If a matching catalog room exists and backgrounds differ → mark overridden.
    - If no catalog room found → assume overridden.
    """
    if location.background_overridden:
        return
    bg = location.background_image
    if bg is None or bg == "":
        return
    room = find_catalog_room(catalog, location.catalog_room_id)
    if room is None:
        # No catalog to compare, assume user set it intentionally
        location.background_overridden = True
        return
    if bg != (room.background_image or ""):
        location.background_overridden = True
    # else: matches catalog → inherited (background_overridden stays False)


def get_effective_sockets(
    location: LocationInstance,
    catalog: RoomCatalog | None,
) -> list[SocketDefinition]:
    """Return the effective sockets for a location.

    If sockets are explicitly overridden, return the location's own socket list.
    Otherwise, inherit sockets from the catalog room entry.
    Falls back to location.sockets if catalog is unavailable.
    """
    if location.socket_overridden:
        return location.sockets
    room = find_catalog_room(catalog, location.catalog_room_id)
    if room is not None:
        return room.sockets
    return location.sockets


def migrate_location_sockets(
    location: LocationInstance,
    catalog: RoomCatalog | None,
) -> None:
    """Backfill socket override metadata for locations that lack it.

    Rules:
    - If socket_overridden is already True, do nothing.
    - If sockets is empty and catalog exists: treat as inherited (no override).
    - If sockets differ from catalog sockets: treat as overridden.
    - If sockets equal catalog sockets: treat as inherited.
    - If no catalog room found and sockets exist: assume overridden.
    """
    if location.socket_overridden:
        return
    if not location.sockets:
        # Empty sockets → inherited (or no sockets at all)
        return
    room = find_catalog_room(catalog, location.catalog_room_id)
    if room is None:
        # No catalog to compare, assume user set them intentionally
        location.socket_overridden = True
        return
    # Compare with catalog sockets
    if _sockets_equal(location.sockets, room.sockets):
        # Matches catalog → inherited
        pass
    else:
        location.socket_overridden = True


def _sockets_equal(a: list[SocketDefinition], b: list[SocketDefinition]) -> bool:
    """Check if two socket lists are semantically equal."""
    if len(a) != len(b):
        return False
    for sa, sb in zip(a, b, strict=False):
        if sa.id != sb.id or sa.name != sb.name:
            return False
        if sa.x != sb.x or sa.y != sb.y:
            return False
        if sa.layer != sb.layer:
            return False
    return True


DEFAULT_PROJECT_LAYERS = [
    "background", "exterior_view", "back_wall", "exit_behind",
    "back_props", "characters", "front_props", "exit_front", "foreground",
]


def get_effective_layers(
    location: LocationInstance,
    project_layers: list[str] | None = None,
) -> list[str]:
    """Return the effective render layers for a location.

    If the location defines custom layers, use those.
    Otherwise, fall back to project default layers.
    """
    if location.layers:
        return list(location.layers)
    return list(project_layers or DEFAULT_PROJECT_LAYERS)


def change_location_catalog_room(
    location: LocationInstance,
    new_catalog_room_id: str,
    catalog: RoomCatalog | None,
) -> None:
    """Change the catalog room for a location, handling background and socket inheritance.

    If background was inherited from the old catalog, switch to new catalog background.
    If background was custom/overridden, preserve it.

    If sockets were inherited, automatically switch to new catalog sockets.
    If sockets were overridden, preserve them.
    """
    if not location.background_overridden:
        # Inherited → update to new catalog's background
        location.catalog_room_id = new_catalog_room_id
        room = find_catalog_room(catalog, new_catalog_room_id)
        location.background_image = room.background_image if room else None
    else:
        # Overridden → just change the catalog room ID, keep the background
        location.catalog_room_id = new_catalog_room_id

    # Sockets: if inherited, just point to new catalog; if overridden, keep custom
    if not location.socket_overridden:
        # Inherited → sockets will come from new catalog automatically
        location.sockets = []
