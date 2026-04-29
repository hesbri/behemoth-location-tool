from __future__ import annotations

from behemoth_location_tool.generation.ambient_fill_pass import run_ambient_fill_pass
from behemoth_location_tool.generation.exclusive_groups import collect_used_groups_from_location
from behemoth_location_tool.generation.explicit_pass import (
    ExplicitPlacementRequest,
    run_explicit_placement_pass,
)
from behemoth_location_tool.generation.placement_pass import PlacementResultRow, apply_placement_rows
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance
from behemoth_location_tool.model.room import SocketDefinition


def generate_ambient_preview(
    location: LocationInstance,
    sockets: list[SocketDefinition],
    entities: list[EntityDefinition],
    mansion_seed: int,
) -> list[PlacementResultRow]:
    entity_map = {entity.id: entity for entity in entities}
    used_groups = collect_used_groups_from_location(location, entity_map)
    return run_ambient_fill_pass(
        location,
        sockets,
        entities,
        mansion_seed,
        used_groups=used_groups,
    )


def generate_explicit_preview(
    location: LocationInstance,
    sockets: list[SocketDefinition],
    entities: list[EntityDefinition],
    requests: list[ExplicitPlacementRequest],
) -> list[PlacementResultRow]:
    entity_map = {entity.id: entity for entity in entities}
    used_groups = collect_used_groups_from_location(location, entity_map)
    return run_explicit_placement_pass(
        location,
        sockets,
        entities,
        requests,
        used_groups=used_groups,
    )


def apply_preview_to_location(
    location: LocationInstance,
    preview_rows: list[PlacementResultRow],
) -> None:
    apply_placement_rows(location, preview_rows)
