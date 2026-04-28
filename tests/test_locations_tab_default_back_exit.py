from __future__ import annotations

import sys

from PySide6.QtWidgets import QApplication

from conftest import requires_gui

from behemoth_location_tool.io.location_factory import DEFAULT_BACK_EXIT_ENTITY_ID
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import ExitDefinition
from behemoth_location_tool.model.room import SocketDefinition
from behemoth_location_tool.ui.locations_tab import LocationsTab
from behemoth_location_tool.validation.validator import validate_locations


@requires_gui
def test_locations_tab_new_non_start_has_real_default_back_exit() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = LocationsTab()
    tab._on_add_empty()  # start
    tab._on_add_empty()  # non-start

    locations = tab.locations_file.locations
    assert len(locations) == 2

    start = locations[0]
    non_start = locations[1]
    assert len(non_start.exits) == 1
    default_back = non_start.exits[0]
    assert default_back.entity_id == DEFAULT_BACK_EXIT_ENTITY_ID
    assert default_back.socket_id
    assert any(socket.id == default_back.socket_id for socket in non_start.sockets)

    # Add reciprocal start->non_start exit with real socket so validation stays clean.
    start.socket_overridden = True
    start.sockets.append(SocketDefinition(id="start_exit_socket", name="Start Exit", x=100, y=900))
    start.exits.append(
        ExitDefinition(
            id="start_to_non_start",
            entity_id=DEFAULT_BACK_EXIT_ENTITY_ID,
            target_location_id=non_start.id,
            socket_id="start_exit_socket",
            tags=["exit.door"],
        )
    )

    entities = [
        EntityDefinition(
            id=DEFAULT_BACK_EXIT_ENTITY_ID,
            kind="exit",
            name="Default Back Exit",
            description="Default back exit entity.",
            tags=["exit.door"],
        )
    ]
    report = validate_locations(tab.locations_file, entities=entities)
    errors = [diag for diag in report.diagnostics if diag.severity.value == "error"]
    assert errors == [], [diag.message for diag in errors]
