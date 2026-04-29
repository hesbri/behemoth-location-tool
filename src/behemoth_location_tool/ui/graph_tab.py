from __future__ import annotations

import contextlib

from PySide6.QtCore import Qt, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QUndoStack
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsLineItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import GraphNode, LocationsFile
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.undo.commands import MoveGraphNodeCommand
from behemoth_location_tool.validation.diagnostics import Diagnostic
from behemoth_location_tool.validation.semantic_validator import validate_locations

STATUS_START = "start_location"
STATUS_MISSING_RECIPROCAL = "missing_reciprocal_exit"
STATUS_UNREACHABLE = "unreachable_location"
STATUS_INVALID_TARGET = "invalid_exit_target"
STATUS_MISSING_DEFAULT_BACK = "missing_default_back_exit"


def classify_graph_location_statuses(
    locations_file: LocationsFile,
    diagnostics: list[Diagnostic],
) -> dict[str, set[str]]:
    """Map location IDs to graph statuses based on validation diagnostics."""
    status_index: dict[str, set[str]] = {loc.id: set() for loc in locations_file.locations}
    exit_to_location: dict[str, str] = {}
    for location in locations_file.locations:
        for exit_def in location.exits:
            exit_to_location[exit_def.id] = location.id

    if locations_file.start_location in status_index:
        status_index[locations_file.start_location].add(STATUS_START)

    for diag in diagnostics:
        object_id = diag.object_id or ""
        if diag.code == STATUS_MISSING_RECIPROCAL and object_id in status_index:
            status_index[object_id].add(STATUS_MISSING_RECIPROCAL)
        elif diag.code == STATUS_UNREACHABLE and object_id in status_index:
            status_index[object_id].add(STATUS_UNREACHABLE)
        elif diag.code == STATUS_MISSING_DEFAULT_BACK and object_id in status_index:
            status_index[object_id].add(STATUS_MISSING_DEFAULT_BACK)
        elif diag.code == "missing_target_location":
            source_location = exit_to_location.get(object_id)
            if source_location is not None and source_location in status_index:
                status_index[source_location].add(STATUS_INVALID_TARGET)

    return status_index


class GraphNodeItem(QGraphicsEllipseItem):
    """Draggable graph node representing a location."""

    def __init__(
        self,
        location_id: str,
        name: str,
        x: float,
        y: float,
        status_flags: set[str] | None = None,
    ) -> None:
        r = 30
        super().__init__(-r, -r, r * 2, r * 2)
        self.location_id = location_id
        self._name = name
        self._status_flags: set[str] = set(status_flags or set())
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(5)

        self._label = QGraphicsTextItem(self)
        self._label.setPlainText("")
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont()
        font.setPointSize(7)
        self._label.setFont(font)
        self._status_label = QGraphicsTextItem(self)
        self._status_label.setDefaultTextColor(QColor(240, 240, 240))
        status_font = QFont()
        status_font.setPointSize(6)
        self._status_label.setFont(status_font)
        self._update_style()

    def _update_style(self) -> None:
        if STATUS_MISSING_DEFAULT_BACK in self._status_flags:
            fill = QColor(231, 76, 60)   # red
        elif STATUS_INVALID_TARGET in self._status_flags:
            fill = QColor(142, 68, 173)  # purple
        elif STATUS_UNREACHABLE in self._status_flags:
            fill = QColor(230, 126, 34)  # orange
        elif STATUS_MISSING_RECIPROCAL in self._status_flags:
            fill = QColor(241, 196, 15)  # yellow
        elif STATUS_START in self._status_flags:
            fill = QColor(46, 204, 113)  # green
        else:
            fill = QColor(52, 152, 219)  # blue
        self.setBrush(QBrush(fill))

        if STATUS_START in self._status_flags:
            self.setPen(QPen(QColor(46, 204, 113), 3))
        else:
            self.setPen(QPen(QColor(255, 255, 255), 2))

        display_id = self.location_id
        if STATUS_START in self._status_flags:
            display_id = f"★ {display_id}"
        self._label.setPlainText(display_id)
        self._label.setPos(-self._label.boundingRect().width() / 2, -46)

        badge = _build_status_badge(self._status_flags)
        self._status_label.setPlainText(badge)
        self._status_label.setPos(-self._status_label.boundingRect().width() / 2, 28)
        self.setToolTip(_build_status_tooltip(self._status_flags))

    def set_status_flags(self, status_flags: set[str]) -> None:
        self._status_flags = set(status_flags)
        self._update_style()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value) -> object:  # type: ignore[no-untyped-def]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if scene and isinstance(scene, GraphScene):
                scene.update_edges()
                scene.node_moved.emit(self.location_id, self.pos().x(), self.pos().y())
        return super().itemChange(change, value)

    def mouseDoubleClickEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        scene = self.scene()
        if scene and isinstance(scene, GraphScene):
            scene.node_double_clicked.emit(self.location_id)
        super().mouseDoubleClickEvent(event)


class GraphEdgeItem(QGraphicsLineItem):
    """Directed edge between two graph nodes."""

    def __init__(
        self,
        source: GraphNodeItem,
        target: GraphNodeItem,
        *,
        style: str = "valid",
    ) -> None:
        super().__init__()
        self._source = source
        self._target = target
        self._style = style
        self.setZValue(1)
        self._update_line()
        self._update_pen()

    def _update_line(self) -> None:
        self.setLine(
            self._source.pos().x(), self._source.pos().y(),
            self._target.pos().x(), self._target.pos().y(),
        )

    def _update_pen(self) -> None:
        if self._style == "invalid_target":
            self.setPen(QPen(QColor(231, 76, 60), 2))
            return
        if self._style == "missing_reciprocal":
            pen = QPen(QColor(241, 196, 15), 2)
            pen.setStyle(Qt.PenStyle.DashLine)
            self.setPen(pen)
            return
        self.setPen(QPen(QColor(200, 200, 200), 2))

    def update_position(self) -> None:
        self._update_line()


class GraphScene(QGraphicsScene):
    """Scene that manages graph nodes and edges."""

    node_moved = Signal(str, float, float)
    node_double_clicked = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._nodes: dict[str, GraphNodeItem] = {}
        self._edges: list[GraphEdgeItem] = []

    @property
    def nodes(self) -> dict[str, GraphNodeItem]:
        return self._nodes

    def clear_graph(self) -> None:
        self.clear()
        self._nodes.clear()
        self._edges.clear()

    def add_node(
        self,
        location_id: str,
        name: str,
        x: float,
        y: float,
        status_flags: set[str] | None = None,
    ) -> GraphNodeItem:
        node = GraphNodeItem(location_id, name, x, y, status_flags=status_flags)
        self.addItem(node)
        self._nodes[location_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, *, style: str = "valid") -> GraphEdgeItem | None:
        source = self._nodes.get(source_id)
        target = self._nodes.get(target_id)
        if source is None:
            return None
        # Target may be missing → draw edge to a phantom position or skip
        if target is None:
            return None
        edge = GraphEdgeItem(source, target, style=style)
        self.addItem(edge)
        self._edges.append(edge)
        return edge

    def update_edges(self) -> None:
        for edge in self._edges:
            edge.update_position()

    def get_node_positions(self) -> dict[str, tuple[float, float]]:
        return {lid: (n.pos().x(), n.pos().y()) for lid, n in self._nodes.items()}


class GraphTab(QWidget):
    """Graph view showing locations as nodes and exits as directed edges."""

    location_double_clicked = Signal(str)  # location_id
    graph_positions_changed = Signal()

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locations_file: LocationsFile | None = None
        self._catalog: RoomCatalog | None = None
        self._entities: list[EntityDefinition] = []
        self._project_layers: list[str] | None = None
        self._diagnostics_override: list[Diagnostic] | None = None
        self._undo_stack: QUndoStack | None = None
        self._suppress_undo_index_refresh = False
        self._build_ui()
        self._scene.node_moved.connect(self._on_node_moved)
        self._scene.node_double_clicked.connect(self._on_scene_node_double_clicked)
        self.destroyed.connect(lambda *_args: self._disconnect_undo_stack())

    def set_locations_file(self, lf: LocationsFile) -> None:
        self._locations_file = lf
        self._refresh_graph()

    def set_validation_context(
        self,
        *,
        catalog: RoomCatalog | None,
        entities: list[EntityDefinition],
        project_layers: list[str] | None = None,
    ) -> None:
        self._catalog = catalog
        self._entities = list(entities)
        self._project_layers = project_layers
        self._refresh_graph()

    def set_validation_diagnostics(self, diagnostics: list[Diagnostic] | None) -> None:
        self._diagnostics_override = diagnostics
        self._refresh_graph()

    def set_undo_stack(self, undo_stack: QUndoStack | None) -> None:
        self._disconnect_undo_stack()
        self._undo_stack = undo_stack
        if undo_stack is not None:
            undo_stack.indexChanged.connect(self._on_undo_stack_index_changed)

    def _disconnect_undo_stack(self) -> None:
        if self._undo_stack is None:
            return
        with contextlib.suppress(Exception):
            self._undo_stack.indexChanged.disconnect(self._on_undo_stack_index_changed)

    def get_graph_positions(self) -> dict[str, tuple[float, float]]:
        return self._scene.get_node_positions()

    def _on_scene_node_double_clicked(self, location_id: str) -> None:
        self.location_double_clicked.emit(location_id)

    def _build_ui(self) -> None:
        layout = QVBoxLayout(self)

        toolbar = QHBoxLayout()
        self._refresh_btn = QPushButton("Refresh Graph")
        self._refresh_btn.clicked.connect(self._refresh_graph)
        self._info_label = QLabel("Nodes: 0 | Edges: 0")
        toolbar.addWidget(self._refresh_btn)
        toolbar.addWidget(self._info_label)
        toolbar.addStretch()
        layout.addLayout(toolbar)

        self._scene = GraphScene()
        self._view = QGraphicsView(self._scene)
        self._view.setRenderHint(QPainter.RenderHint.Antialiasing)
        self._view.setDragMode(QGraphicsView.DragMode.NoDrag)
        layout.addWidget(self._view)

    def _on_node_moved(self, location_id: str, x: float, y: float) -> None:
        if self._locations_file is None:
            return
        x_i = int(round(x))
        y_i = int(round(y))
        target: GraphNode | None = None
        for node in self._locations_file.graph.nodes:
            if node.location_id == location_id:
                target = node
                break
        if target is None:
            old_x = None
            old_y = None
        else:
            old_x = target.x
            old_y = target.y
        if old_x == x_i and old_y == y_i:
            return
        if self._undo_stack is None:
            if target is None:
                self._locations_file.graph.nodes.append(GraphNode(location_id=location_id, x=x_i, y=y_i))
            else:
                target.x = x_i
                target.y = y_i
            self.graph_positions_changed.emit()
            return
        self._suppress_undo_index_refresh = True
        try:
            self._undo_stack.push(
                MoveGraphNodeCommand(
                    locations_file=self._locations_file,
                    location_id=location_id,
                    old_x=old_x,
                    old_y=old_y,
                    new_x=x_i,
                    new_y=y_i,
                    on_changed=self.graph_positions_changed.emit,
                )
            )
        finally:
            self._suppress_undo_index_refresh = False

    def _on_undo_stack_index_changed(self, _index: int) -> None:
        if self._suppress_undo_index_refresh:
            return
        try:
            self._refresh_graph()
        except RuntimeError:
            self._disconnect_undo_stack()

    def _refresh_graph(self) -> None:
        self._scene.clear_graph()
        if self._locations_file is None:
            self._info_label.setText("Nodes: 0 | Edges: 0")
            return

        lf = self._locations_file
        location_ids = {loc.id for loc in lf.locations}

        # Build node position map from graph
        node_positions: dict[str, tuple[float, float]] = {
            n.location_id: (float(n.x), float(n.y)) for n in lf.graph.nodes
        }

        diagnostics = self._diagnostics_override
        if diagnostics is None:
            report = validate_locations(
                lf,
                catalog=self._catalog,
                entities=self._entities,
                project_layers=self._project_layers,
            )
            diagnostics = report.diagnostics
        status_index = classify_graph_location_statuses(lf, diagnostics)
        missing_recip_count = sum(
            STATUS_MISSING_RECIPROCAL in flags for flags in status_index.values()
        )
        unreachable_count = sum(STATUS_UNREACHABLE in flags for flags in status_index.values())
        missing_back_count = sum(
            STATUS_MISSING_DEFAULT_BACK in flags for flags in status_index.values()
        )

        # Create nodes for all locations
        for loc in lf.locations:
            pos = node_positions.get(loc.id, (100.0 + len(self._scene.nodes) * 250.0, 200.0))
            self._scene.add_node(
                loc.id,
                loc.name,
                pos[0],
                pos[1],
                status_flags=status_index.get(loc.id, set()),
            )

        # Create edges from exits
        edge_count = 0
        invalid_edge_count = 0
        for loc in lf.locations:
            for ex in loc.exits:
                if ex.target_location_id:
                    target_exists = ex.target_location_id in location_ids
                    style = "valid"
                    if not target_exists:
                        style = "invalid_target"
                    elif ex.target_location_id != loc.id:
                        target_loc = next(
                            (
                                candidate
                                for candidate in lf.locations
                                if candidate.id == ex.target_location_id
                            ),
                            None,
                        )
                        has_reciprocal = False
                        if target_loc is not None:
                            has_reciprocal = any(
                                back.target_location_id == loc.id
                                for back in target_loc.exits
                            )
                        if not has_reciprocal:
                            style = "missing_reciprocal"

                    edge = self._scene.add_edge(loc.id, ex.target_location_id, style=style)
                    if edge:
                        edge_count += 1
                    if not target_exists:
                        invalid_edge_count += 1

        # Mark graph nodes without matching locations
        for gn in lf.graph.nodes:
            if gn.location_id not in location_ids:
                # Orphan graph node → create a warning node
                pos = node_positions.get(gn.location_id, (100.0, 400.0))
                node = self._scene.add_node(gn.location_id, "?", pos[0], pos[1])
                node.setBrush(QBrush(QColor(231, 76, 60)))

        n_nodes = len(self._scene.nodes)
        self._info_label.setText(
            f"Nodes: {n_nodes} | Edges: {edge_count} | Invalid Targets: {invalid_edge_count} | "
            f"No Reciprocal: {missing_recip_count} | Unreachable: {unreachable_count} | "
            f"No Back Exit: {missing_back_count}"
        )

        # Fit view
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)


def _build_status_badge(status_flags: set[str]) -> str:
    tokens: list[str] = []
    if STATUS_START in status_flags:
        tokens.append("START")
    if STATUS_MISSING_DEFAULT_BACK in status_flags:
        tokens.append("NO_BACK")
    if STATUS_INVALID_TARGET in status_flags:
        tokens.append("BAD_TARGET")
    if STATUS_UNREACHABLE in status_flags:
        tokens.append("UNREACHABLE")
    if STATUS_MISSING_RECIPROCAL in status_flags:
        tokens.append("NO_RECIP")
    return " | ".join(tokens)


def _build_status_tooltip(status_flags: set[str]) -> str:
    if not status_flags:
        return "Status: OK"
    labels: list[str] = []
    if STATUS_START in status_flags:
        labels.append("Start location")
    if STATUS_MISSING_DEFAULT_BACK in status_flags:
        labels.append("Missing default/back exit")
    if STATUS_INVALID_TARGET in status_flags:
        labels.append("Has exit with invalid target")
    if STATUS_UNREACHABLE in status_flags:
        labels.append("Unreachable from start")
    if STATUS_MISSING_RECIPROCAL in status_flags:
        labels.append("Missing reciprocal exit")
    return "Status: " + ", ".join(labels)
