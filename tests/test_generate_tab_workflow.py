from __future__ import annotations

import sys

from conftest import requires_gui
from PySide6.QtWidgets import QApplication

from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance, LocationsFile
from behemoth_location_tool.model.room import AmbientRule, SocketDefinition
from behemoth_location_tool.ui.generate_tab import GenerateTab


def _build_tab_with_single_location() -> tuple[QApplication, GenerateTab, LocationInstance]:
    app = QApplication.instance() or QApplication(sys.argv)
    location = LocationInstance(
        id="hall_01",
        catalog_room_id="",
        name="Hall",
        socket_overridden=True,
        sockets=[
            SocketDefinition(
                id="sock_1",
                ambient_spawn_chance=100,
                ambient_rule=AmbientRule(mode="tag_query", required_tags=["entity.spawnable"]),
            )
        ],
    )
    lf = LocationsFile(start_location=location.id, locations=[location])
    tab = GenerateTab()
    tab.set_locations_file(lf)
    tab.set_entities(
        [
            EntityDefinition(
                id="chair_01",
                kind="furniture",
                name="Chair",
                tags=["entity.spawnable", "furniture.chair"],
            )
        ]
    )
    return app, tab, location


@requires_gui
def test_generate_tab_preview_discard_apply_workflow() -> None:
    app, tab, location = _build_tab_with_single_location()
    assert app is not None
    applied: list[str] = []
    tab.set_apply_callback(lambda loc: applied.append(loc.id))

    tab._on_generate()
    assert location.placed_entities == []
    assert tab._discard_btn.isEnabled()

    tab._on_discard()
    assert location.placed_entities == []
    assert not tab._apply_btn.isEnabled()
    assert not tab._send_preview_btn.isEnabled()

    tab._on_generate()
    tab._on_apply()
    assert len(location.placed_entities) == 1
    assert location.placed_entities[0].instance_id == "hall_01__sock_1__chair_01"
    assert location.placed_entities[0].placement_source == "ambient_fill"
    assert applied == ["hall_01"]


@requires_gui
def test_generate_tab_send_preview_uses_callback_without_mutating_location() -> None:
    app, tab, location = _build_tab_with_single_location()
    assert app is not None

    calls: list[tuple[str, int]] = []

    def _callback(loc: LocationInstance, rows: list[PlacementResultRow]) -> bool:
        calls.append((loc.id, len(rows)))
        return True

    tab.set_send_preview_callback(_callback)
    tab._on_generate()
    tab._on_send_preview()

    assert calls == [("hall_01", 1)]
    assert location.placed_entities == []
