from __future__ import annotations

from behemoth_location_tool.model.id_utils import generate_id
from behemoth_location_tool.model.location import (
    ExitDefinition,
    GraphNode,
    LocationInstance,
    LocationsFile,
)
from behemoth_location_tool.model.room import RoomCatalogEntry, SocketDefinition


def create_location_from_room(
    room: RoomCatalogEntry,
    *,
    location_id: str | None = None,
    is_start: bool = False,
    start_location_id: str | None = None,
) -> LocationInstance:
    """Create a LocationInstance from a RoomCatalogEntry.

    Copies sockets from the catalog at creation time (snapshot, not reference).
    Adds a default back exit if this is not the start location.
    """
    loc_id = location_id or room.id
    loc_name = room.name
    loc_desc = room.description

    # Sockets are inherited from catalog by default (not copied).
    # Only populated when user explicitly overrides.
    sockets: list[SocketDefinition] = []

    # Resolve layers
    if room.layers.mode == "custom" and room.layers.order:
        layers = list(room.layers.order)
    else:
        layers = []

    # Create exits
    exits: list[ExitDefinition] = []

    if not is_start:
        # Auto-create default back exit
        exit_id = generate_id("default_exit", {e.id for e in exits}, fallback="exit")
        exits.append(ExitDefinition(
            id=exit_id,
            entity_id=exit_id,
            target_location_id=start_location_id or "",
            socket_id="",
            layer="exit_behind",
            tags=["exit.default_back"],
        ))

    return LocationInstance(
        id=loc_id,
        catalog_room_id=room.id,
        name=loc_name,
        description=loc_desc,
        background_image=room.background_image,
        background_overridden=False,  # inherit from catalog by default
        socket_overridden=False,  # inherit sockets from catalog by default
        design_size=room.design_size.model_copy(deep=True),
        tags=list(room.tags),
        layers=layers,
        sockets=sockets,
        exits=exits,
        placed_entities=[],
    )


def add_graph_node_for_location(locations_file: LocationsFile, location_id: str) -> None:
    """Ensure a graph node exists for the given location ID.

    If one already exists, do nothing. Otherwise, create a default position
    offset from the last existing node.
    """
    existing = {n.location_id for n in locations_file.graph.nodes}
    if location_id in existing:
        return

    # Default position: offset from last node or origin
    x, y = 100, 100
    if locations_file.graph.nodes:
        last = locations_file.graph.nodes[-1]
        x = last.x + 250
        y = last.y

    locations_file.graph.nodes.append(GraphNode(location_id=location_id, x=x, y=y))
