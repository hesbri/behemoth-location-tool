from __future__ import annotations

from behemoth_location_tool.model.id_utils import generate_id
from behemoth_location_tool.model.location import (
    ExitDefinition,
    GraphNode,
    LocationInstance,
    LocationsFile,
)
from behemoth_location_tool.model.room import RoomCatalogEntry, SocketDefinition

DEFAULT_BACK_EXIT_ENTITY_ID = "exit.default_back"
DEFAULT_BACK_EXIT_LAYER = "exit_behind"


def add_default_back_exit_with_socket(
    location: LocationInstance,
    *,
    target_location_id: str,
    entity_id: str = DEFAULT_BACK_EXIT_ENTITY_ID,
) -> None:
    """Ensure location has a concrete default-back socket and matching exit."""
    existing_socket_ids = {socket.id for socket in location.sockets}
    socket_id = generate_id("socket_exit_back", existing_socket_ids, fallback="socket")
    socket_x = location.design_size.w // 2
    socket_y = max(0, location.design_size.h - 80)
    location.sockets.append(
        SocketDefinition(
            id=socket_id,
            name="Default Back Exit",
            x=socket_x,
            y=socket_y,
            layer=DEFAULT_BACK_EXIT_LAYER,
        )
    )
    location.socket_overridden = True

    existing_exit_ids = {exit_def.id for exit_def in location.exits}
    exit_id = generate_id("exit_default_back", existing_exit_ids, fallback="exit")
    location.exits.append(
        ExitDefinition(
            id=exit_id,
            entity_id=entity_id,
            target_location_id=target_location_id,
            socket_id=socket_id,
            layer=DEFAULT_BACK_EXIT_LAYER,
            tags=["exit.default_back"],
        )
    )


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

    # Sockets are inherited from catalog by default.
    sockets: list[SocketDefinition] = []
    socket_overridden = False

    # Resolve layers
    if room.layers.mode == "custom" and room.layers.order:
        layers = list(room.layers.order)
    else:
        layers = []

    exits: list[ExitDefinition] = []

    if not is_start:
        # Non-start locations get a concrete default-back socket+exit.
        sockets = [socket.model_copy(deep=True) for socket in room.sockets]
        socket_overridden = True
        provisional = LocationInstance(
            id=loc_id,
            catalog_room_id=room.id,
            name=loc_name,
            description=loc_desc,
            background_image=room.background_image,
            background_overridden=False,
            socket_overridden=True,
            design_size=room.design_size.model_copy(deep=True),
            tags=list(room.tags),
            layers=layers,
            sockets=sockets,
            exits=exits,
            placed_entities=[],
        )
        add_default_back_exit_with_socket(provisional, target_location_id=start_location_id or "")
        sockets = provisional.sockets
        exits = provisional.exits

    return LocationInstance(
        id=loc_id,
        catalog_room_id=room.id,
        name=loc_name,
        description=loc_desc,
        background_image=room.background_image,
        background_overridden=False,  # inherit from catalog by default
        socket_overridden=socket_overridden,
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
