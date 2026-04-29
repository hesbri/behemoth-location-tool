from __future__ import annotations

from PySide6.QtGui import QUndoCommand

from behemoth_location_tool.generation.placement_pass import PlacementResultRow, apply_placement_rows
from behemoth_location_tool.model.location import (
    ExitDefinition,
    GraphNode,
    LocationInstance,
    LocationsFile,
    PlacedEntity,
)
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.undo.command_helpers import call_if_set, clone_value, models_equal

GRAPH_MOVE_COMMAND_ID = 31001
SOCKET_MOVE_COMMAND_ID = 31002
SOCKET_EDIT_COMMAND_ID = 31003


def _find_graph_node_index(locations_file: LocationsFile, location_id: str) -> int:
    for idx, node in enumerate(locations_file.graph.nodes):
        if node.location_id == location_id:
            return idx
    return -1


def _set_graph_node_position(
    locations_file: LocationsFile,
    *,
    location_id: str,
    x: int,
    y: int,
) -> None:
    idx = _find_graph_node_index(locations_file, location_id)
    if idx < 0:
        locations_file.graph.nodes.append(GraphNode(location_id=location_id, x=x, y=y))
        return
    locations_file.graph.nodes[idx].x = x
    locations_file.graph.nodes[idx].y = y


class MoveGraphNodeCommand(QUndoCommand):
    def __init__(
        self,
        *,
        locations_file: LocationsFile,
        location_id: str,
        old_x: int | None,
        old_y: int | None,
        new_x: int,
        new_y: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Move Graph Node: {location_id}")
        self._locations_file = locations_file
        self._location_id = location_id
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y
        self._on_changed = on_changed

    def id(self) -> int:
        return GRAPH_MOVE_COMMAND_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, MoveGraphNodeCommand):
            return False
        if self._location_id != other._location_id:
            return False
        self._new_x = other._new_x
        self._new_y = other._new_y
        return True

    def redo(self) -> None:
        _set_graph_node_position(
            self._locations_file,
            location_id=self._location_id,
            x=self._new_x,
            y=self._new_y,
        )
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if self._old_x is None or self._old_y is None:
            idx = _find_graph_node_index(self._locations_file, self._location_id)
            if idx >= 0:
                del self._locations_file.graph.nodes[idx]
        else:
            _set_graph_node_position(
                self._locations_file,
                location_id=self._location_id,
                x=self._old_x,
                y=self._old_y,
            )
        call_if_set(self._on_changed)


class AddLocationCommand(QUndoCommand):
    def __init__(
        self,
        *,
        locations_file: LocationsFile,
        location: LocationInstance,
        graph_node: GraphNode | None,
        index: int,
        set_start_on_add: bool,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Add Location: {location.id}")
        self._locations_file = locations_file
        self._location = clone_value(location)
        self._graph_node = clone_value(graph_node) if graph_node is not None else None
        self._index = index
        self._start_before = locations_file.start_location
        self._start_after = location.id if set_start_on_add else locations_file.start_location
        self._on_changed = on_changed

    def redo(self) -> None:
        if not any(item.id == self._location.id for item in self._locations_file.locations):
            index = min(self._index, len(self._locations_file.locations))
            self._locations_file.locations.insert(index, clone_value(self._location))
        if self._graph_node is not None and _find_graph_node_index(
            self._locations_file, self._graph_node.location_id
        ) < 0:
            self._locations_file.graph.nodes.append(clone_value(self._graph_node))
        self._locations_file.start_location = self._start_after
        call_if_set(self._on_changed)

    def undo(self) -> None:
        self._locations_file.locations = [
            item for item in self._locations_file.locations if item.id != self._location.id
        ]
        self._locations_file.graph.nodes = [
            node for node in self._locations_file.graph.nodes if node.location_id != self._location.id
        ]
        self._locations_file.start_location = self._start_before
        call_if_set(self._on_changed)


class DeleteLocationCommand(QUndoCommand):
    def __init__(
        self,
        *,
        locations_file: LocationsFile,
        location: LocationInstance,
        graph_node: GraphNode | None,
        index: int,
        start_after: str,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Delete Location: {location.id}")
        self._locations_file = locations_file
        self._location = clone_value(location)
        self._graph_node = clone_value(graph_node) if graph_node is not None else None
        self._index = index
        self._start_before = locations_file.start_location
        self._start_after = start_after
        self._on_changed = on_changed

    def redo(self) -> None:
        self._locations_file.locations = [
            item for item in self._locations_file.locations if item.id != self._location.id
        ]
        self._locations_file.graph.nodes = [
            node for node in self._locations_file.graph.nodes if node.location_id != self._location.id
        ]
        self._locations_file.start_location = self._start_after
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if not any(item.id == self._location.id for item in self._locations_file.locations):
            index = min(self._index, len(self._locations_file.locations))
            self._locations_file.locations.insert(index, clone_value(self._location))
        if self._graph_node is not None and _find_graph_node_index(
            self._locations_file, self._graph_node.location_id
        ) < 0:
            self._locations_file.graph.nodes.insert(
                min(self._index, len(self._locations_file.graph.nodes)),
                clone_value(self._graph_node),
            )
        self._locations_file.start_location = self._start_before
        call_if_set(self._on_changed)


class AddExitCommand(QUndoCommand):
    def __init__(
        self,
        *,
        location: LocationInstance,
        exit_def: ExitDefinition,
        index: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Add Exit: {exit_def.id}")
        self._location = location
        self._exit = clone_value(exit_def)
        self._index = index
        self._on_changed = on_changed

    def redo(self) -> None:
        if not any(item.id == self._exit.id for item in self._location.exits):
            index = min(self._index, len(self._location.exits))
            self._location.exits.insert(index, clone_value(self._exit))
        call_if_set(self._on_changed)

    def undo(self) -> None:
        for idx, item in enumerate(self._location.exits):
            if item.id == self._exit.id:
                del self._location.exits[idx]
                break
        call_if_set(self._on_changed)


class DeleteExitCommand(QUndoCommand):
    def __init__(
        self,
        *,
        location: LocationInstance,
        exit_def: ExitDefinition,
        index: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Delete Exit: {exit_def.id}")
        self._location = location
        self._exit = clone_value(exit_def)
        self._index = index
        self._on_changed = on_changed

    def redo(self) -> None:
        self._location.exits = [item for item in self._location.exits if item.id != self._exit.id]
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if not any(item.id == self._exit.id for item in self._location.exits):
            index = min(self._index, len(self._location.exits))
            self._location.exits.insert(index, clone_value(self._exit))
        call_if_set(self._on_changed)


class EditExitCommand(QUndoCommand):
    def __init__(
        self,
        *,
        location: LocationInstance,
        index: int,
        before: ExitDefinition,
        after: ExitDefinition,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Edit Exit: {before.id}")
        self._location = location
        self._index = index
        self._before = clone_value(before)
        self._after = clone_value(after)
        self._on_changed = on_changed

    def redo(self) -> None:
        if 0 <= self._index < len(self._location.exits):
            self._location.exits[self._index] = clone_value(self._after)
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if 0 <= self._index < len(self._location.exits):
            self._location.exits[self._index] = clone_value(self._before)
        call_if_set(self._on_changed)


class ApplyGenerationResultCommand(QUndoCommand):
    def __init__(
        self,
        *,
        location: LocationInstance,
        preview_rows: list[PlacementResultRow],
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Apply Generation: {location.id}")
        self._location = location
        self._on_changed = on_changed
        self._before: list[PlacedEntity] = [clone_value(item) for item in location.placed_entities]
        temp_location = clone_value(location)
        apply_placement_rows(temp_location, preview_rows)
        self._after: list[PlacedEntity] = [clone_value(item) for item in temp_location.placed_entities]

    def redo(self) -> None:
        self._location.placed_entities = [clone_value(item) for item in self._after]
        call_if_set(self._on_changed)

    def undo(self) -> None:
        self._location.placed_entities = [clone_value(item) for item in self._before]
        call_if_set(self._on_changed)


class AddSocketCommand(QUndoCommand):
    def __init__(
        self,
        *,
        room: RoomCatalogEntry,
        socket: SocketDefinition,
        index: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Add Socket: {socket.id}")
        self._room = room
        self._socket = clone_value(socket)
        self._index = index
        self._on_changed = on_changed

    def redo(self) -> None:
        if not any(item.id == self._socket.id for item in self._room.sockets):
            index = min(self._index, len(self._room.sockets))
            self._room.sockets.insert(index, clone_value(self._socket))
        call_if_set(self._on_changed)

    def undo(self) -> None:
        self._room.sockets = [item for item in self._room.sockets if item.id != self._socket.id]
        call_if_set(self._on_changed)


class DeleteSocketCommand(QUndoCommand):
    def __init__(
        self,
        *,
        room: RoomCatalogEntry,
        socket: SocketDefinition,
        index: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Delete Socket: {socket.id}")
        self._room = room
        self._socket = clone_value(socket)
        self._index = index
        self._on_changed = on_changed

    def redo(self) -> None:
        self._room.sockets = [item for item in self._room.sockets if item.id != self._socket.id]
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if not any(item.id == self._socket.id for item in self._room.sockets):
            index = min(self._index, len(self._room.sockets))
            self._room.sockets.insert(index, clone_value(self._socket))
        call_if_set(self._on_changed)


class MoveSocketCommand(QUndoCommand):
    def __init__(
        self,
        *,
        room: RoomCatalogEntry,
        socket_id: str,
        old_x: int,
        old_y: int,
        new_x: int,
        new_y: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Move Socket: {socket_id}")
        self._room = room
        self._socket_id = socket_id
        self._old_x = old_x
        self._old_y = old_y
        self._new_x = new_x
        self._new_y = new_y
        self._on_changed = on_changed

    def id(self) -> int:
        return SOCKET_MOVE_COMMAND_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, MoveSocketCommand):
            return False
        if self._socket_id != other._socket_id:
            return False
        if self._room is not other._room:
            return False
        self._new_x = other._new_x
        self._new_y = other._new_y
        return True

    def _set(self, x: int, y: int) -> None:
        for sock in self._room.sockets:
            if sock.id == self._socket_id:
                sock.x = x
                sock.y = y
                break
        call_if_set(self._on_changed)

    def redo(self) -> None:
        self._set(self._new_x, self._new_y)

    def undo(self) -> None:
        self._set(self._old_x, self._old_y)


def exit_changed(before: ExitDefinition, after: ExitDefinition) -> bool:
    return not models_equal(before, after)


class AddRoomCommand(QUndoCommand):
    def __init__(
        self,
        *,
        catalog: RoomCatalog,
        room: RoomCatalogEntry,
        index: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Add Room: {room.id}")
        self._catalog = catalog
        self._room = clone_value(room)
        self._index = index
        self._on_changed = on_changed

    def redo(self) -> None:
        if not any(item.id == self._room.id for item in self._catalog.rooms):
            index = min(self._index, len(self._catalog.rooms))
            self._catalog.rooms.insert(index, clone_value(self._room))
        call_if_set(self._on_changed)

    def undo(self) -> None:
        self._catalog.rooms = [item for item in self._catalog.rooms if item.id != self._room.id]
        call_if_set(self._on_changed)


class DeleteRoomCommand(QUndoCommand):
    def __init__(
        self,
        *,
        catalog: RoomCatalog,
        room: RoomCatalogEntry,
        index: int,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Delete Room: {room.id}")
        self._catalog = catalog
        self._room = clone_value(room)
        self._index = index
        self._on_changed = on_changed

    def redo(self) -> None:
        self._catalog.rooms = [item for item in self._catalog.rooms if item.id != self._room.id]
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if not any(item.id == self._room.id for item in self._catalog.rooms):
            index = min(self._index, len(self._catalog.rooms))
            self._catalog.rooms.insert(index, clone_value(self._room))
        call_if_set(self._on_changed)


class EditRoomCommand(QUndoCommand):
    def __init__(
        self,
        *,
        catalog: RoomCatalog,
        index: int,
        before: RoomCatalogEntry,
        after: RoomCatalogEntry,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Edit Room: {before.id}")
        self._catalog = catalog
        self._index = index
        self._before = clone_value(before)
        self._after = clone_value(after)
        self._on_changed = on_changed

    def redo(self) -> None:
        if 0 <= self._index < len(self._catalog.rooms):
            self._catalog.rooms[self._index] = clone_value(self._after)
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if 0 <= self._index < len(self._catalog.rooms):
            self._catalog.rooms[self._index] = clone_value(self._before)
        call_if_set(self._on_changed)


class EditSocketCommand(QUndoCommand):
    def __init__(
        self,
        *,
        room: RoomCatalogEntry,
        index: int,
        before: SocketDefinition,
        after: SocketDefinition,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Edit Socket: {before.id}")
        self._room = room
        self._index = index
        self._before = clone_value(before)
        self._after = clone_value(after)
        self._on_changed = on_changed

    def id(self) -> int:
        return SOCKET_EDIT_COMMAND_ID

    def mergeWith(self, other: QUndoCommand) -> bool:
        if not isinstance(other, EditSocketCommand):
            return False
        if self._room is not other._room:
            return False
        if self._index != other._index:
            return False
        self._after = clone_value(other._after)
        return True

    def redo(self) -> None:
        if 0 <= self._index < len(self._room.sockets):
            self._room.sockets[self._index] = clone_value(self._after)
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if 0 <= self._index < len(self._room.sockets):
            self._room.sockets[self._index] = clone_value(self._before)
        call_if_set(self._on_changed)


def socket_changed(before: SocketDefinition, after: SocketDefinition) -> bool:
    return not models_equal(before, after)


class EditLocationCommand(QUndoCommand):
    def __init__(
        self,
        *,
        locations_file: LocationsFile,
        index: int,
        before: LocationInstance,
        after: LocationInstance,
        on_changed=None,  # type: ignore[no-untyped-def]
    ) -> None:
        super().__init__(f"Edit Location: {before.id}")
        self._locations_file = locations_file
        self._index = index
        self._before = clone_value(before)
        self._after = clone_value(after)
        self._on_changed = on_changed

    def redo(self) -> None:
        if 0 <= self._index < len(self._locations_file.locations):
            self._locations_file.locations[self._index] = clone_value(self._after)
        call_if_set(self._on_changed)

    def undo(self) -> None:
        if 0 <= self._index < len(self._locations_file.locations):
            self._locations_file.locations[self._index] = clone_value(self._before)
        call_if_set(self._on_changed)


def room_changed(before: RoomCatalogEntry, after: RoomCatalogEntry) -> bool:
    return not models_equal(before, after)


def location_changed(before: LocationInstance, after: LocationInstance) -> bool:
    return not models_equal(before, after)
