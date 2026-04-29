from __future__ import annotations

from behemoth_location_tool.generation.candidate_filter import is_candidate_allowed
from behemoth_location_tool.generation.deterministic_rng import (
    choose_uniform,
    choose_weighted,
    roll_spawn_chance,
    stable_seed_int,
)
from behemoth_location_tool.generation.exclusive_groups import register_entity_groups
from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance
from behemoth_location_tool.model.room import SocketDefinition, WeightedFillEntry


def run_ambient_fill_pass(
    location: LocationInstance,
    sockets: list[SocketDefinition],
    entities: list[EntityDefinition],
    mansion_seed: int,
    *,
    used_groups: set[str] | None = None,
) -> list[PlacementResultRow]:
    entity_map = {entity.id: entity for entity in entities}
    active_groups = used_groups if used_groups is not None else set()
    filled_socket_ids = {placement.socket_id for placement in location.placed_entities}
    rows: list[PlacementResultRow] = []

    for socket in sockets:
        if socket.id in filled_socket_ids:
            continue

        row = PlacementResultRow(socket_id=socket.id)
        seed = stable_seed_int(mansion_seed, location.id, socket.id, "ambient_fill")
        if not roll_spawn_chance(seed, socket.ambient_spawn_chance):
            row.reject_reason = f"spawn roll failed (chance={socket.ambient_spawn_chance}%)"
            rows.append(row)
            continue

        rule = socket.ambient_rule
        if rule.mode == "none":
            row.reject_reason = "ambient rule mode=none"
            rows.append(row)
            continue

        chosen: EntityDefinition | None = None
        if rule.mode == "tag_query":
            candidates = [
                entity
                for entity in entities
                if is_candidate_allowed(
                    entity,
                    location_tags=location.tags,
                    socket=socket,
                    used_groups=active_groups,
                    required_tags=rule.required_tags,
                    forbidden_tags=rule.forbidden_tags,
                )
            ]
            chosen = choose_uniform(seed, candidates)

        elif rule.mode in ("weighted_entity_list", "weighted_entries"):
            weighted_candidates: list[tuple[EntityDefinition, int]] = []
            if rule.mode == "weighted_entity_list":
                for entry in rule.entries:
                    entity = entity_map.get(entry.entity_id)
                    if entity is None:
                        continue
                    if is_candidate_allowed(
                        entity,
                        location_tags=location.tags,
                        socket=socket,
                        used_groups=active_groups,
                    ):
                        weighted_candidates.append((entity, entry.weight))
            else:
                for entry in rule.fill_entries:
                    weighted_candidates.extend(
                        _weighted_candidates_from_fill_entry(
                            entry=entry,
                            entities=entities,
                            entity_map=entity_map,
                            location=location,
                            socket=socket,
                            used_groups=active_groups,
                        )
                    )
            chosen = choose_weighted(seed, weighted_candidates)

        if chosen is None:
            row.reject_reason = "no matching candidates"
        else:
            row.entity_id = chosen.id
            row.placement_source = "ambient_fill"
            register_entity_groups(active_groups, chosen)

        rows.append(row)

    return rows


def _weighted_candidates_from_fill_entry(
    *,
    entry: WeightedFillEntry,
    entities: list[EntityDefinition],
    entity_map: dict[str, EntityDefinition],
    location: LocationInstance,
    socket: SocketDefinition,
    used_groups: set[str],
) -> list[tuple[EntityDefinition, int]]:
    if entry.type == "entity" and entry.entity_id:
        entity = entity_map.get(entry.entity_id)
        if entity is None:
            return []
        if is_candidate_allowed(
            entity,
            location_tags=location.tags,
            socket=socket,
            used_groups=used_groups,
            required_tags=entry.required_tags,
            forbidden_tags=entry.forbidden_tags,
        ):
            return [(entity, entry.weight)]
        return []

    # Extension mode: a weighted tag query can nominate multiple candidates.
    if entry.type == "tag_query":
        return [
            (entity, entry.weight)
            for entity in entities
            if is_candidate_allowed(
                entity,
                location_tags=location.tags,
                socket=socket,
                used_groups=used_groups,
                required_tags=entry.required_tags,
                forbidden_tags=entry.forbidden_tags,
            )
        ]
    return []
