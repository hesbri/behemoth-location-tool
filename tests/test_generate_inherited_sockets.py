from __future__ import annotations

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance, get_effective_sockets
from behemoth_location_tool.model.room import AmbientRule, RoomCatalog, RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.ui.generate_tab import _run_ambient_fill


def test_ambient_fill_uses_effective_catalog_sockets() -> None:
    catalog = RoomCatalog(
        rooms=[
            RoomCatalogEntry(
                id="catalog.hall",
                name="Hall",
                sockets=[
                    SocketDefinition(
                        id="sock_a",
                        name="Socket A",
                        ambient_spawn_chance=100,
                        ambient_rule=AmbientRule(mode="tag_query", required_tags=["entity.spawnable"]),
                    )
                ],
            )
        ]
    )
    location = LocationInstance(
        id="hall_01",
        catalog_room_id="catalog.hall",
        name="Hall",
        socket_overridden=False,
        sockets=[],
    )
    entities = [
        EntityDefinition(
            id="chair_01",
            kind="furniture",
            name="Chair",
            description="A chair.",
            tags=["entity.spawnable", "furniture.chair"],
        )
    ]

    effective = get_effective_sockets(location, catalog)
    rows = _run_ambient_fill(location, effective, entities, mansion_seed=123)

    assert len(rows) == 1
    assert rows[0].socket_id == "sock_a"
    assert rows[0].placed
    assert rows[0].entity_id == "chair_01"
