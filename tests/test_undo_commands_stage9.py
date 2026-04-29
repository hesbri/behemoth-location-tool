from __future__ import annotations

import sys

from conftest import requires_gui
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.model.location import (
    ExitDefinition,
    GraphNode,
    LocationGraph,
    LocationInstance,
    LocationsFile,
    PlacedEntity,
)
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.ui.locations_tab import LocationsTab
from behemoth_location_tool.undo.commands import (
    AddLocationCommand,
    ApplyGenerationResultCommand,
    EditExitCommand,
    EditLocationCommand,
    EditRoomCommand,
    MoveGraphNodeCommand,
    MoveSocketCommand,
)


@requires_gui
def test_move_graph_node_command_redo_undo_and_callback() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="loc_1",
        graph=LocationGraph(nodes=[GraphNode(location_id="loc_1", x=100, y=200)]),
        locations=[LocationInstance(id="loc_1", catalog_room_id="", name="Hall")],
    )
    calls: list[str] = []
    stack = QUndoStack()
    stack.push(
        MoveGraphNodeCommand(
            locations_file=lf,
            location_id="loc_1",
            old_x=100,
            old_y=200,
            new_x=450,
            new_y=320,
            on_changed=lambda: calls.append("changed"),
        )
    )

    assert lf.graph.nodes[0].x == 450
    assert lf.graph.nodes[0].y == 320

    stack.undo()
    assert lf.graph.nodes[0].x == 100
    assert lf.graph.nodes[0].y == 200

    stack.redo()
    assert lf.graph.nodes[0].x == 450
    assert lf.graph.nodes[0].y == 320
    assert calls == ["changed", "changed", "changed"]


@requires_gui
def test_add_location_command_mutates_and_restores() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="loc_1",
        graph=LocationGraph(nodes=[GraphNode(location_id="loc_1", x=100, y=200)]),
        locations=[LocationInstance(id="loc_1", catalog_room_id="", name="Hall")],
    )
    new_loc = LocationInstance(id="loc_2", catalog_room_id="", name="Library")
    calls: list[str] = []
    stack = QUndoStack()
    stack.push(
        AddLocationCommand(
            locations_file=lf,
            location=new_loc,
            graph_node=GraphNode(location_id="loc_2", x=360, y=220),
            index=1,
            set_start_on_add=False,
            on_changed=lambda: calls.append("changed"),
        )
    )

    assert [loc.id for loc in lf.locations] == ["loc_1", "loc_2"]
    assert any(node.location_id == "loc_2" for node in lf.graph.nodes)

    stack.undo()
    assert [loc.id for loc in lf.locations] == ["loc_1"]
    assert all(node.location_id != "loc_2" for node in lf.graph.nodes)
    assert calls == ["changed", "changed"]


@requires_gui
def test_edit_exit_command_and_apply_generation_undo() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    location = LocationInstance(
        id="loc_1",
        catalog_room_id="",
        name="Hall",
        exits=[
            ExitDefinition(
                id="exit_1",
                entity_id="exit.default_back",
                target_location_id="loc_2",
                socket_id="socket_1",
            )
        ],
        placed_entities=[
            PlacedEntity(
                instance_id="loc_1__socket_0__chair_01",
                entity_id="chair_01",
                socket_id="socket_0",
                placement_source="manual",
            )
        ],
    )
    before = location.exits[0].model_copy(deep=True)
    after = before.model_copy(deep=True)
    after.target_location_id = "loc_3"
    callbacks: list[str] = []
    stack = QUndoStack()
    stack.push(
        EditExitCommand(
            location=location,
            index=0,
            before=before,
            after=after,
            on_changed=lambda: callbacks.append("exit"),
        )
    )
    assert location.exits[0].target_location_id == "loc_3"
    stack.undo()
    assert location.exits[0].target_location_id == "loc_2"

    rows = [
        PlacementResultRow(
            socket_id="socket_2",
            entity_id="table_01",
            placement_source="ambient_fill",
        )
    ]
    stack.push(
        ApplyGenerationResultCommand(
            location=location,
            preview_rows=rows,
            on_changed=lambda: callbacks.append("apply"),
        )
    )
    assert len(location.placed_entities) == 2
    assert location.placed_entities[1].entity_id == "table_01"
    stack.undo()
    assert len(location.placed_entities) == 1
    assert callbacks.count("apply") == 2


@requires_gui
def test_move_socket_command_redo_undo() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    room = RoomCatalogEntry(
        id="room_1",
        name="Room 1",
        sockets=[SocketDefinition(id="socket_1", x=100, y=150)],
    )
    stack = QUndoStack()
    stack.push(
        MoveSocketCommand(
            room=room,
            socket_id="socket_1",
            old_x=100,
            old_y=150,
            new_x=310,
            new_y=420,
        )
    )
    assert room.sockets[0].x == 310
    assert room.sockets[0].y == 420
    stack.undo()
    assert room.sockets[0].x == 100
    assert room.sockets[0].y == 150


@requires_gui
def test_locations_tab_dirty_resets_when_undo_returns_to_clean() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = LocationsTab()
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    stack.setClean()

    tab._on_add_empty()
    assert tab.is_dirty
    assert not stack.isClean()

    stack.undo()
    assert stack.isClean()
    assert not tab.is_dirty


@requires_gui
def test_edit_room_command_redo_undo_and_callback() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    catalog = RoomCatalog(
        rooms=[
            RoomCatalogEntry(
                id="room_1",
                name="Room One",
            )
        ]
    )
    before = catalog.rooms[0].model_copy(deep=True)
    after = before.model_copy(deep=True)
    after.name = "Renamed Room"
    after.background_image = "world/backgrounds/room.png"
    after.layers.mode = "custom"
    after.layers.order = ["background", "characters", "foreground"]

    callbacks: list[str] = []
    stack = QUndoStack()
    stack.push(
        EditRoomCommand(
            catalog=catalog,
            index=0,
            before=before,
            after=after,
            on_changed=lambda: callbacks.append("changed"),
        )
    )
    assert catalog.rooms[0].name == "Renamed Room"
    assert catalog.rooms[0].background_image == "world/backgrounds/room.png"
    assert catalog.rooms[0].layers.mode == "custom"
    assert catalog.rooms[0].layers.order == ["background", "characters", "foreground"]

    stack.undo()
    assert catalog.rooms[0].name == "Room One"
    assert catalog.rooms[0].background_image is None
    assert catalog.rooms[0].layers.mode == "project_default"

    stack.redo()
    assert catalog.rooms[0].name == "Renamed Room"
    assert callbacks == ["changed", "changed", "changed"]


@requires_gui
def test_edit_location_command_redo_undo_and_callback() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    locations = LocationsFile(
        start_location="loc_1",
        locations=[LocationInstance(id="loc_1", catalog_room_id="", name="Hall")],
    )
    before = locations.locations[0].model_copy(deep=True)
    after = before.model_copy(deep=True)
    after.id = "loc_renamed"
    after.name = "Great Hall"
    after.background_image = "world/backgrounds/hall.png"
    after.layers = ["background", "characters", "foreground"]

    callbacks: list[str] = []
    stack = QUndoStack()
    stack.push(
        EditLocationCommand(
            locations_file=locations,
            index=0,
            before=before,
            after=after,
            on_changed=lambda: callbacks.append("changed"),
        )
    )
    assert locations.locations[0].id == "loc_renamed"
    assert locations.locations[0].name == "Great Hall"
    assert locations.locations[0].background_image == "world/backgrounds/hall.png"

    stack.undo()
    assert locations.locations[0].id == "loc_1"
    assert locations.locations[0].name == "Hall"
    assert locations.locations[0].background_image is None

    stack.redo()
    assert locations.locations[0].id == "loc_renamed"
    assert callbacks == ["changed", "changed", "changed"]


@requires_gui
def test_locations_tab_core_field_edit_undo_redo() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = LocationsTab()
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    tab._on_add_empty()
    tab._list.setCurrentRow(0)
    tab._prev_row = 0
    stack.setClean()

    tab._f_name.setText("Renamed Location")
    tab._f_bg.setText("world/backgrounds/renamed.png")
    tab._f_layers.setText("background, characters, foreground")
    tab._sync_form_to_data()

    loc = tab.locations_file.locations[0]
    assert loc.name == "Renamed Location"
    assert loc.background_image == "world/backgrounds/renamed.png"
    assert loc.layers == ["background", "characters", "foreground"]
    assert not stack.isClean()

    stack.undo()
    loc = tab.locations_file.locations[0]
    assert loc.name != "Renamed Location"
    assert loc.background_image is None
    assert loc.layers == []
    tab.deleteLater()
    app.processEvents()
