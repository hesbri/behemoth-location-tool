from __future__ import annotations

import sys

from conftest import requires_gui
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.ui.room_catalog_tab import RoomCatalogTab


@requires_gui
def test_room_add_delete_undo_redo_and_catalog_callback() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = RoomCatalogTab(ProjectConfig())
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    callback_calls: list[int] = []
    tab.set_catalog_changed_callback(lambda: callback_calls.append(1))

    tab._on_add()
    assert len(tab.catalog.rooms) == 1
    assert tab.catalog.rooms[0].id == "new_room"

    stack.undo()
    assert len(tab.catalog.rooms) == 0

    stack.redo()
    assert len(tab.catalog.rooms) == 1
    assert len(callback_calls) >= 3

    tab._on_add()
    assert len(tab.catalog.rooms) == 2
    tab._list.setCurrentRow(0)
    tab._on_delete()
    assert len(tab.catalog.rooms) == 1

    stack.undo()
    assert len(tab.catalog.rooms) == 2
    stack.redo()
    assert len(tab.catalog.rooms) == 1


@requires_gui
def test_socket_property_edit_undo_redo() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = RoomCatalogTab(ProjectConfig())
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    tab.catalog.rooms.append(
        RoomCatalogEntry(
            id="room_1",
            name="Room 1",
            sockets=[SocketDefinition(id="socket_1", x=100, y=150)],
        )
    )
    tab._refresh_list()
    tab._list.setCurrentRow(0)
    tab._socket_list.setCurrentRow(0)

    tab._sf_x.setValue(450)
    tab._sf_y.setValue(222)
    tab._sf_rotation.setValue(15.0)
    tab._sf_scale.setValue(1.25)
    tab._sf_layer.setCurrentText("front_props")
    tab._sf_sort.setValue(7)
    tab._sf_req_tags.setText("furniture.chair")
    tab._sf_forb_tags.setText("furniture.broken")
    tab._sync_socket_form()

    sock = tab.catalog.rooms[0].sockets[0]
    assert sock.x == 450
    assert sock.y == 222
    assert sock.rotation == 15.0
    assert sock.scale == 1.25
    assert sock.layer == "front_props"
    assert sock.sort_order == 7
    assert sock.required_tags == ["furniture.chair"]
    assert sock.forbidden_tags == ["furniture.broken"]

    stack.undo()
    sock = tab.catalog.rooms[0].sockets[0]
    assert sock.x == 100
    assert sock.y == 150
    assert sock.rotation == 0.0
    assert sock.scale == 1.0

    stack.redo()
    sock = tab.catalog.rooms[0].sockets[0]
    assert sock.x == 450
    assert sock.y == 222


@requires_gui
def test_room_catalog_dirty_resets_when_undo_back_to_clean() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = RoomCatalogTab(ProjectConfig())
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    stack.setClean()
    assert not tab.is_dirty

    tab._on_add()
    assert tab.is_dirty
    assert not stack.isClean()

    stack.undo()
    assert stack.isClean()
    assert not tab.is_dirty


@requires_gui
def test_room_core_field_edit_undo_redo() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = RoomCatalogTab(ProjectConfig())
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    tab.catalog.rooms.append(RoomCatalogEntry(id="room_1", name="Room One"))
    tab._refresh_list()
    tab._list.setCurrentRow(0)
    stack.setClean()

    tab._f_name.setText("Room Renamed")
    tab._f_bg.setText("world/backgrounds/room_renamed.png")
    tab._f_layer_mode.setCurrentText("custom")
    tab._f_layer_order.setText("background, characters, foreground")
    tab._sync_form_to_catalog()

    room = tab.catalog.rooms[0]
    assert room.name == "Room Renamed"
    assert room.background_image == "world/backgrounds/room_renamed.png"
    assert room.layers.mode == "custom"
    assert room.layers.order == ["background", "characters", "foreground"]
    assert not stack.isClean()

    stack.undo()
    room = tab.catalog.rooms[0]
    assert room.name == "Room One"
    assert room.background_image is None
    assert room.layers.mode == "project_default"

    stack.redo()
    room = tab.catalog.rooms[0]
    assert room.name == "Room Renamed"
    tab.deleteLater()
    app.processEvents()
