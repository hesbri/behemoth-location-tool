from __future__ import annotations

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.room import SocketDefinition
from behemoth_location_tool.model.tags import matches_all, matches_none


def is_candidate_allowed(
    entity: EntityDefinition,
    *,
    location_tags: list[str],
    socket: SocketDefinition,
    used_groups: set[str],
    required_tags: list[str] | None = None,
    forbidden_tags: list[str] | None = None,
) -> bool:
    entity_tags = set(entity.tags)
    spawn_rules = entity.spawn_rules

    if socket.required_tags and not matches_all(entity_tags, socket.required_tags):
        return False
    if socket.forbidden_tags and not matches_none(entity_tags, socket.forbidden_tags):
        return False

    if required_tags and not matches_all(entity_tags, required_tags):
        return False
    if forbidden_tags and not matches_none(entity_tags, forbidden_tags):
        return False

    context_tags = set(location_tags) | set(socket.required_tags)
    if spawn_rules.required_context_tags and not matches_all(
        context_tags,
        spawn_rules.required_context_tags,
    ):
        return False
    if spawn_rules.forbidden_context_tags and not matches_none(
        context_tags,
        spawn_rules.forbidden_context_tags,
    ):
        return False

    if any(group in used_groups for group in spawn_rules.exclusive_groups):
        return False

    return not socket.allowed_entity_ids or entity.id in socket.allowed_entity_ids
