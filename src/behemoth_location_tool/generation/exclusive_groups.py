from __future__ import annotations

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance


def collect_used_groups_from_location(
    location: LocationInstance,
    entities_by_id: dict[str, EntityDefinition],
) -> set[str]:
    used_groups: set[str] = set()
    for placement in location.placed_entities:
        entity = entities_by_id.get(placement.entity_id)
        if entity is None:
            continue
        used_groups.update(entity.spawn_rules.exclusive_groups)
    return used_groups


def register_entity_groups(used_groups: set[str], entity: EntityDefinition) -> None:
    used_groups.update(entity.spawn_rules.exclusive_groups)
