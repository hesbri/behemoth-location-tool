from __future__ import annotations

from behemoth_location_tool.generation.explicit_pass import ExplicitPlacementRequest
from behemoth_location_tool.generation.generation_service import (
    apply_preview_to_location,
    generate_ambient_preview,
    generate_explicit_preview,
)
from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance, PlacedEntity
from behemoth_location_tool.model.room import AmbientRule, SocketDefinition


def test_generate_ambient_preview_is_deterministic() -> None:
    location = LocationInstance(id="hall_01", catalog_room_id="", name="Hall")
    sockets = [
        SocketDefinition(
            id="sock_1",
            ambient_spawn_chance=100,
            ambient_rule=AmbientRule(mode="tag_query", required_tags=["entity.spawnable"]),
        )
    ]
    entities = [
        EntityDefinition(
            id="chair_01",
            kind="furniture",
            name="Chair",
            description="A chair.",
            tags=["entity.spawnable", "furniture.chair"],
        )
    ]

    first = generate_ambient_preview(location, sockets, entities, mansion_seed=12345)
    second = generate_ambient_preview(location, sockets, entities, mansion_seed=12345)

    assert [row.entity_id for row in first] == [row.entity_id for row in second]
    assert [row.reject_reason for row in first] == [row.reject_reason for row in second]


def test_apply_preview_to_location_adds_collision_suffix() -> None:
    location = LocationInstance(
        id="hall_01",
        catalog_room_id="",
        name="Hall",
        placed_entities=[
            PlacedEntity(
                instance_id="hall_01__sock_1__chair_01",
                entity_id="chair_01",
                socket_id="sock_1",
            )
        ],
    )
    preview = [
        PlacementResultRow(
            socket_id="sock_1",
            entity_id="chair_01",
            placement_source="ambient_fill",
        )
    ]

    apply_preview_to_location(location, preview)

    assert len(location.placed_entities) == 2
    assert location.placed_entities[1].instance_id == "hall_01__sock_1__chair_01__02"


def test_generate_explicit_preview_ignores_ambient_spawn_chance() -> None:
    location = LocationInstance(id="hall_01", catalog_room_id="", name="Hall")
    sockets = [
        SocketDefinition(
            id="sock_1",
            ambient_spawn_chance=0,
            ambient_rule=AmbientRule(mode="none"),
        )
    ]
    entities = [
        EntityDefinition(
            id="fireplace_a",
            kind="prop",
            name="Fireplace",
            tags=["decor.fireplace"],
        )
    ]
    rows = generate_explicit_preview(
        location,
        sockets,
        entities,
        requests=[ExplicitPlacementRequest(socket_id="sock_1", entity_id="fireplace_a")],
    )

    assert len(rows) == 1
    assert rows[0].placed
    assert rows[0].entity_id == "fireplace_a"
    assert rows[0].placement_source == "explicit"


def test_generate_explicit_preview_respects_candidate_filter_rules() -> None:
    location = LocationInstance(id="hall_01", catalog_room_id="", name="Hall")
    sockets = [
        SocketDefinition(
            id="sock_1",
            allowed_entity_ids=["allowed_entity"],
        )
    ]
    entities = [
        EntityDefinition(
            id="disallowed_entity",
            kind="prop",
            name="Disallowed",
            tags=["decor.prop"],
        )
    ]
    rows = generate_explicit_preview(
        location,
        sockets,
        entities,
        requests=[ExplicitPlacementRequest(socket_id="sock_1", entity_id="disallowed_entity")],
    )

    assert len(rows) == 1
    assert not rows[0].placed
    assert rows[0].reject_reason == "entity failed placement filters"


def test_generate_ambient_preview_seeds_exclusive_groups_from_existing_placed_entities() -> None:
    location = LocationInstance(
        id="hall_01",
        catalog_room_id="",
        name="Hall",
        placed_entities=[
            PlacedEntity(
                instance_id="hall_01__sock_existing__fireplace_a",
                entity_id="fireplace_a",
                socket_id="sock_existing",
            )
        ],
    )
    sockets = [
        SocketDefinition(
            id="sock_new",
            ambient_spawn_chance=100,
            ambient_rule=AmbientRule(mode="tag_query", required_tags=["decor.hearth"]),
        )
    ]
    entities = [
        EntityDefinition(
            id="fireplace_a",
            kind="prop",
            name="Fireplace A",
            tags=["decor.hearth"],
            spawn_rules={"exclusiveGroups": ["unique.hearth"]},
        ),
        EntityDefinition(
            id="fireplace_b",
            kind="prop",
            name="Fireplace B",
            tags=["decor.hearth"],
            spawn_rules={"exclusiveGroups": ["unique.hearth"]},
        ),
    ]

    rows = generate_ambient_preview(location, sockets, entities, mansion_seed=7)

    assert len(rows) == 1
    assert not rows[0].placed
    assert rows[0].reject_reason == "no matching candidates"
