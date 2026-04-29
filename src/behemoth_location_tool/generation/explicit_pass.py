from __future__ import annotations

from dataclasses import dataclass, field

from behemoth_location_tool.generation.candidate_filter import is_candidate_allowed
from behemoth_location_tool.generation.exclusive_groups import register_entity_groups
from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance
from behemoth_location_tool.model.room import SocketDefinition


@dataclass
class ExplicitPlacementRequest:
    socket_id: str
    entity_id: str
    required_tags: list[str] = field(default_factory=list)
    forbidden_tags: list[str] = field(default_factory=list)


def run_explicit_placement_pass(
    location: LocationInstance,
    sockets: list[SocketDefinition],
    entities: list[EntityDefinition],
    requests: list[ExplicitPlacementRequest],
    *,
    used_groups: set[str] | None = None,
) -> list[PlacementResultRow]:
    """Resolve direct explicit placements.

    Explicit placement intentionally ignores ambientSpawnChance and ambient rules.
    """
    socket_map = {socket.id: socket for socket in sockets}
    entity_map = {entity.id: entity for entity in entities}
    active_groups = used_groups if used_groups is not None else set()
    filled_socket_ids = {placement.socket_id for placement in location.placed_entities}
    rows: list[PlacementResultRow] = []

    for request in requests:
        row = PlacementResultRow(socket_id=request.socket_id)
        socket = socket_map.get(request.socket_id)
        if socket is None:
            row.reject_reason = "socket not found"
            rows.append(row)
            continue
        if request.socket_id in filled_socket_ids:
            row.reject_reason = "socket already occupied"
            rows.append(row)
            continue
        entity = entity_map.get(request.entity_id)
        if entity is None:
            row.reject_reason = "entity not found"
            rows.append(row)
            continue

        if not is_candidate_allowed(
            entity,
            location_tags=location.tags,
            socket=socket,
            used_groups=active_groups,
            required_tags=request.required_tags,
            forbidden_tags=request.forbidden_tags,
        ):
            row.reject_reason = "entity failed placement filters"
            rows.append(row)
            continue

        row.entity_id = entity.id
        row.placement_source = "explicit"
        rows.append(row)
        filled_socket_ids.add(request.socket_id)
        register_entity_groups(active_groups, entity)

    return rows
