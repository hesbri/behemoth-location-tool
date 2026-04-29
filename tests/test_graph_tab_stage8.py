from __future__ import annotations

import sys

from conftest import requires_gui
from PySide6.QtCore import Qt
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import QApplication

from behemoth_location_tool.model.location import (
    ExitDefinition,
    GraphNode,
    LocationGraph,
    LocationInstance,
    LocationsFile,
)
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.ui.graph_tab import GraphTab
from behemoth_location_tool.ui.main_window import MainWindow


@requires_gui
def test_graph_tab_drag_persists_node_position_and_emits_change() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="loc_1",
        graph=LocationGraph(nodes=[GraphNode(location_id="loc_1", x=100, y=200)]),
        locations=[LocationInstance(id="loc_1", catalog_room_id="", name="Hall")],
    )
    tab = GraphTab()
    changed: list[bool] = []
    tab.graph_positions_changed.connect(lambda: changed.append(True))
    tab.set_locations_file(lf)

    node = tab._scene.nodes["loc_1"]
    node.setPos(444, 333)
    app.processEvents()

    assert lf.graph.nodes[0].x == 444
    assert lf.graph.nodes[0].y == 333
    assert changed


@requires_gui
def test_graph_tab_drag_creates_graph_node_when_missing() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="loc_1",
        graph=LocationGraph(nodes=[]),
        locations=[LocationInstance(id="loc_1", catalog_room_id="", name="Hall")],
    )
    tab = GraphTab()
    tab.set_locations_file(lf)

    node = tab._scene.nodes["loc_1"]
    node.setPos(260, 180)
    app.processEvents()

    assert len(lf.graph.nodes) == 1
    assert lf.graph.nodes[0].location_id == "loc_1"
    assert lf.graph.nodes[0].x == 260
    assert lf.graph.nodes[0].y == 180


@requires_gui
def test_main_window_graph_double_click_selects_location_tab() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    win = MainWindow(ProjectConfig())
    win._locations_tab._on_add_empty()
    win._locations_tab._on_add_empty()
    second_id = win._locations_tab.locations_file.locations[1].id
    win._sync_locations_to_graph()

    tabs = win.centralWidget()
    tabs.setCurrentWidget(win._graph_tab)
    win._graph_tab.location_double_clicked.emit(second_id)
    app.processEvents()

    assert tabs.currentWidget() is win._locations_tab
    assert win._locations_tab.current_location_id == second_id


@requires_gui
def test_main_window_graph_move_marks_locations_dirty() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    win = MainWindow(ProjectConfig())
    win._locations_tab._on_add_empty()
    location_id = win._locations_tab.locations_file.locations[0].id
    win._sync_locations_to_graph()
    win._locations_tab._dirty = False

    node = win._graph_tab._scene.nodes[location_id]
    node.setPos(512, 256)
    app.processEvents()

    assert win._locations_tab.is_dirty
    graph_node = win._locations_tab.locations_file.graph.nodes[0]
    assert graph_node.x == 512
    assert graph_node.y == 256


@requires_gui
def test_graph_tab_move_undo_redo_with_undo_stack() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="loc_1",
        graph=LocationGraph(nodes=[GraphNode(location_id="loc_1", x=100, y=200)]),
        locations=[LocationInstance(id="loc_1", catalog_room_id="", name="Hall")],
    )
    tab = GraphTab()
    stack = QUndoStack()
    tab.set_undo_stack(stack)
    tab.set_locations_file(lf)

    node = tab._scene.nodes["loc_1"]
    node.setPos(700, 440)
    app.processEvents()
    assert lf.graph.nodes[0].x == 700
    assert lf.graph.nodes[0].y == 440

    stack.undo()
    app.processEvents()
    assert lf.graph.nodes[0].x == 100
    assert lf.graph.nodes[0].y == 200

    stack.redo()
    app.processEvents()
    assert lf.graph.nodes[0].x == 700
    assert lf.graph.nodes[0].y == 440


@requires_gui
def test_graph_tab_info_label_includes_status_counts() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="start",
        graph=LocationGraph(nodes=[]),
        locations=[
            LocationInstance(
                id="start",
                catalog_room_id="",
                name="Start",
            ),
            LocationInstance(
                id="kitchen",
                catalog_room_id="",
                name="Kitchen",
            ),
        ],
    )
    tab = GraphTab()
    tab.set_locations_file(lf)
    text = tab._info_label.text()

    assert "No Reciprocal:" in text
    assert "Unreachable:" in text
    assert "No Back Exit:" in text
    tab.deleteLater()
    app.processEvents()


@requires_gui
def test_graph_tab_missing_reciprocal_edge_uses_dashed_style() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    lf = LocationsFile(
        start_location="a",
        graph=LocationGraph(
            nodes=[
                GraphNode(location_id="a", x=100, y=200),
                GraphNode(location_id="b", x=300, y=200),
            ]
        ),
        locations=[
            LocationInstance(
                id="a",
                catalog_room_id="",
                name="A",
                exits=[],
            ),
            LocationInstance(
                id="b",
                catalog_room_id="",
                name="B",
                exits=[],
            ),
        ],
    )
    lf.locations[0].exits.append(
        ExitDefinition(
            id="exit_a_b",
            entity_id="door",
            target_location_id="b",
            socket_id="socket_1",
            tags=["exit.default_back"],
        )
    )

    tab = GraphTab()
    tab.set_locations_file(lf)
    assert tab._scene._edges
    edge = tab._scene._edges[0]
    assert edge.pen().style() == Qt.PenStyle.DashLine
    tab.deleteLater()
    app.processEvents()
