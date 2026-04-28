from __future__ import annotations

from PySide6.QtCore import Qt, QRectF, Signal
from PySide6.QtGui import QBrush, QColor, QPen, QFont, QPainter
from PySide6.QtWidgets import (
    QGraphicsEllipseItem, QGraphicsItem, QGraphicsLineItem, QGraphicsScene,
    QGraphicsTextItem, QGraphicsView, QVBoxLayout, QWidget, QHBoxLayout,
    QPushButton, QLabel, QListWidget, QSplitter,
)
from behemoth_location_tool.model.location import LocationsFile


class GraphNodeItem(QGraphicsEllipseItem):
    """Draggable graph node representing a location."""

    def __init__(self, location_id: str, name: str, x: float, y: float,
                 is_start: bool = False, has_default_back: bool = True) -> None:
        r = 30
        super().__init__(-r, -r, r * 2, r * 2)
        self.location_id = location_id
        self._name = name
        self._is_start = is_start
        self._has_default_back = has_default_back
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(5)
        self._update_style()

        self._label = QGraphicsTextItem(self)
        self._label.setPlainText(location_id)
        self._label.setDefaultTextColor(QColor(255, 255, 255))
        font = QFont()
        font.setPointSize(7)
        self._label.setFont(font)
        self._label.setPos(-self._label.boundingRect().width() / 2, -r - 16)

    def _update_style(self) -> None:
        if self._is_start:
            self.setBrush(QBrush(QColor(46, 204, 113)))
            self.setPen(QPen(QColor(255, 255, 255), 3))
        elif not self._has_default_back:
            self.setBrush(QBrush(QColor(231, 76, 60)))
            self.setPen(QPen(QColor(255, 255, 255), 2))
        else:
            self.setBrush(QBrush(QColor(52, 152, 219)))
            self.setPen(QPen(QColor(255, 255, 255), 2))

    def set_start(self, is_start: bool) -> None:
        self._is_start = is_start
        self._update_style()

    def set_has_default_back(self, has: bool) -> None:
        self._has_default_back = has
        self._update_style()

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value) -> object:  # type: ignore[no-untyped-def]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            scene = self.scene()
            if scene and isinstance(scene, GraphScene):
                scene.update_edges()
        return super().itemChange(change, value)


class GraphEdgeItem(QGraphicsLineItem):
    """Directed edge between two graph nodes."""

    def __init__(self, source: GraphNodeItem, target: GraphNodeItem, is_valid: bool = True) -> None:
        super().__init__()
        self._source = source
        self._target = target
        self._is_valid = is_valid
        self.setZValue(1)
        self._update_line()
        self._update_pen()

    def _update_line(self) -> None:
        self.setLine(
            self._source.pos().x(), self._source.pos().y(),
            self._target.pos().x(), self._target.pos().y(),
        )

    def _update_pen(self) -> None:
        color = QColor(200, 200, 200) if self._is_valid else QColor(231, 76, 60)
        self.setPen(QPen(color, 2))

    def set_valid(self, valid: bool) -> None:
        self._is_valid = valid
        self._update_pen()

    def update_position(self) -> None:
        self._update_line()


class GraphScene(QGraphicsScene):
    """Scene that manages graph nodes and edges."""

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

    def add_node(self, location_id: str, name: str, x: float, y: float,
                 is_start: bool = False, has_default_back: bool = True) -> GraphNodeItem:
        node = GraphNodeItem(location_id, name, x, y, is_start, has_default_back)
        self.addItem(node)
        self._nodes[location_id] = node
        return node

    def add_edge(self, source_id: str, target_id: str, is_valid: bool = True) -> GraphEdgeItem | None:
        source = self._nodes.get(source_id)
        target = self._nodes.get(target_id)
        if source is None:
            return None
        # Target may be missing → draw edge to a phantom position or skip
        if target is None:
            return None
        edge = GraphEdgeItem(source, target, is_valid)
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

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locations_file: LocationsFile | None = None
        self._build_ui()

    def set_locations_file(self, lf: LocationsFile) -> None:
        self._locations_file = lf
        self._refresh_graph()

    def get_graph_positions(self) -> dict[str, tuple[float, float]]:
        return self._scene.get_node_positions()

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

    def _refresh_graph(self) -> None:
        self._scene.clear_graph()
        if self._locations_file is None:
            self._info_label.setText("Nodes: 0 | Edges: 0")
            return

        lf = self._locations_file
        location_ids = {loc.id for loc in lf.locations}
        start = lf.start_location

        # Build node position map from graph
        node_positions: dict[str, tuple[float, float]] = {
            n.location_id: (float(n.x), float(n.y)) for n in lf.graph.nodes
        }

        # Create nodes for all locations
        for loc in lf.locations:
            pos = node_positions.get(loc.id, (100.0 + len(self._scene.nodes) * 250.0, 200.0))
            has_back = any("exit.default_back" in ex.tags for ex in loc.exits)
            self._scene.add_node(
                loc.id, loc.name, pos[0], pos[1],
                is_start=(loc.id == start),
                has_default_back=has_back,
            )

        # Create edges from exits
        edge_count = 0
        for loc in lf.locations:
            for ex in loc.exits:
                if ex.target_location_id:
                    is_valid = ex.target_location_id in location_ids
                    edge = self._scene.add_edge(loc.id, ex.target_location_id, is_valid)
                    if edge:
                        edge_count += 1

        # Mark graph nodes without matching locations
        for gn in lf.graph.nodes:
            if gn.location_id not in location_ids:
                # Orphan graph node → create a warning node
                pos = node_positions.get(gn.location_id, (100.0, 400.0))
                node = self._scene.add_node(gn.location_id, "?", pos[0], pos[1])
                node.setBrush(QBrush(QColor(231, 76, 60)))

        n_nodes = len(self._scene.nodes)
        self._info_label.setText(f"Nodes: {n_nodes} | Edges: {edge_count}")

        # Fit view
        self._view.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)