from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, QPointF, Signal
from PySide6.QtGui import QBrush, QColor, QFont, QPainter, QPen, QPixmap
from PySide6.QtWidgets import (
    QGraphicsEllipseItem,
    QGraphicsItem,
    QGraphicsRectItem,
    QGraphicsScene,
    QGraphicsTextItem,
    QGraphicsView,
)


class SocketHandle(QGraphicsEllipseItem):
    """Draggable socket handle on room canvas."""

    def __init__(self, socket_id: str, x: float, y: float, radius: float = 10) -> None:
        super().__init__(-radius, -radius, radius * 2, radius * 2)
        self.socket_id = socket_id
        self._radius = radius
        self.setPos(x, y)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsMovable, False)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemIsSelectable, True)
        self.setFlag(QGraphicsItem.GraphicsItemFlag.ItemSendsGeometryChanges, True)
        self.setZValue(10)
        self.setBrush(QBrush(QColor(255, 165, 0, 200)))
        self.setPen(QPen(QColor(255, 255, 255), 2))
        self._label: QGraphicsTextItem | None = None
        self._dragging = False
        self._drag_start_scene_pos: QPointF | None = None
        self._drag_start_item_pos: QPointF | None = None

    def set_label_visible(self, visible: bool) -> None:
        if visible and self._label is None:
            self._label = QGraphicsTextItem(self)
            self._label.setPlainText(self.socket_id)
            self._label.setDefaultTextColor(QColor(255, 255, 255))
            self._label.setZValue(11)
            # Position label above the handle
            self._update_label_pos()
        if self._label is not None:
            self._label.setVisible(visible)

    def _update_label_pos(self) -> None:
        if self._label:
            self._label.setPos(-self._label.boundingRect().width() / 2, -self._radius - 18)

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Start dragging the socket handle."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = True
            self._drag_start_scene_pos = event.scenePos()
            self._drag_start_item_pos = self.pos()
            event.accept()
        else:
            super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Handle socket dragging manually."""
        if (
            self._dragging
            and self._drag_start_scene_pos is not None
            and self._drag_start_item_pos is not None
        ):
            delta = event.scenePos() - self._drag_start_scene_pos
            self.setPos(self._drag_start_item_pos + delta)
            event.accept()
        else:
            super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        """Stop dragging."""
        if event.button() == Qt.MouseButton.LeftButton:
            self._dragging = False
            self._drag_start_scene_pos = None
            self._drag_start_item_pos = None
            event.accept()
        else:
            super().mouseReleaseEvent(event)

    def itemChange(self, change: QGraphicsItem.GraphicsItemChange, value) -> object:  # type: ignore[no-untyped-def]
        if change == QGraphicsItem.GraphicsItemChange.ItemPositionHasChanged:
            self._update_label_pos()
        return super().itemChange(change, value)


class RoomScene(QGraphicsScene):
    """Graphics scene for a room background + socket handles."""

    def __init__(self) -> None:
        super().__init__()
        self._bg_item = None
        self._socket_handles: list[SocketHandle] = []
        self._design_width = 1920
        self._design_height = 1080

    @property
    def socket_handles(self) -> list[SocketHandle]:
        return list(self._socket_handles)

    def set_background(self, image_path: Path | None, design_w: int, design_h: int) -> None:
        """Set the room background image and design size."""
        self._design_width = design_w
        self._design_height = design_h
        self.setSceneRect(0, 0, design_w, design_h)

        # Remove old background
        if self._bg_item is not None:
            self.removeItem(self._bg_item)
            self._bg_item = None

        if image_path:
            if image_path.exists():
                pixmap = QPixmap(str(image_path))
                if not pixmap.isNull():
                    pixmap = pixmap.scaled(design_w, design_h, Qt.AspectRatioMode.IgnoreAspectRatio,
                                           Qt.TransformationMode.SmoothTransformation)
                    self._bg_item = self.addPixmap(pixmap)
                    self._bg_item.setZValue(0)
                else:
                    self._draw_grid_bg(design_w, design_h,
                                       warning=f"⚠ Failed to load image:\n{image_path.name}")
            else:
                self._draw_grid_bg(design_w, design_h,
                                   warning=f"⚠ Image not found:\n{image_path}")
        else:
            self._draw_grid_bg(design_w, design_h)

    def _draw_grid_bg(self, w: int, h: int, warning: str = "") -> None:
        """Draw a placeholder grid background with optional warning text."""
        rect_item = QGraphicsRectItem(0, 0, w, h)
        rect_item.setPen(QPen(QColor(60, 60, 60)))
        rect_item.setBrush(QBrush(QColor(40, 40, 40)))
        rect_item.setZValue(0)
        self.addItem(rect_item)

        # Draw warning text if provided
        if warning:
            text_item = QGraphicsTextItem(warning, rect_item)
            text_item.setDefaultTextColor(QColor(200, 80, 80))
            font = QFont("Arial", 16)
            font.setBold(True)
            text_item.setFont(font)
            text_item.setPos(w / 2 - text_item.boundingRect().width() / 2,
                             h / 2 - text_item.boundingRect().height() / 2)

        # Draw dimension label
        dim_text = f"{w} × {h}"
        dim_item = QGraphicsTextItem(dim_text, rect_item)
        dim_item.setDefaultTextColor(QColor(100, 100, 100))
        dim_item.setFont(QFont("Arial", 12))
        dim_item.setPos(w / 2 - dim_item.boundingRect().width() / 2,
                        h / 2 + 20)

        self._bg_item = rect_item

    def clear_sockets(self) -> None:
        for handle in self._socket_handles:
            self.removeItem(handle)
        self._socket_handles.clear()

    def add_socket(self, socket_id: str, x: float, y: float) -> SocketHandle:
        handle = SocketHandle(socket_id, x, y)
        self.addItem(handle)
        self._socket_handles.append(handle)
        return handle

    def get_socket_positions(self) -> dict[str, tuple[float, float]]:
        """Return {socket_id: (x, y)} for all handles."""
        return {h.socket_id: (h.pos().x(), h.pos().y()) for h in self._socket_handles}

    def find_handle(self, socket_id: str) -> SocketHandle | None:
        for h in self._socket_handles:
            if h.socket_id == socket_id:
                return h
        return None


class RoomCanvas(QGraphicsView):
    """Graphics view for the room editor with zoom and pan."""

    socket_moved = Signal(str, float, float)  # socket_id, new_x, new_y

    def __init__(self, parent=None) -> None:  # type: ignore[no-untyped-def]
        super().__init__(parent)
        self._scene = RoomScene()
        self.setScene(self._scene)
        self.setRenderHint(QPainter.RenderHint.Antialiasing)
        self.setDragMode(QGraphicsView.DragMode.NoDrag)
        self.setTransformationAnchor(QGraphicsView.ViewportAnchor.AnchorUnderMouse)
        self.setViewportUpdateMode(QGraphicsView.ViewportUpdateMode.FullViewportUpdate)
        self._zoom = 1.0
        self._panning = False
        self._pan_start = None
        self._socket_dragging = False

        # Track socket moves
        self._scene.selectionChanged.connect(self._on_selection_changed)

    @property
    def room_scene(self) -> RoomScene:
        return self._scene

    def fit_to_view(self) -> None:
        """Fit the scene in the view."""
        self.fitInView(self._scene.sceneRect(), Qt.AspectRatioMode.KeepAspectRatio)
        self._zoom = self.transform().m11()

    def wheelEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        factor = 1.15 if event.angleDelta().y() > 0 else 1 / 1.15
        self.scale(factor, factor)
        self._zoom = self.transform().m11()

    def mousePressEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = True
            self._pan_start = event.position().toPoint()
            self.setCursor(Qt.CursorShape.ClosedHandCursor)
            event.accept()
            return
        super().mousePressEvent(event)

    def mouseMoveEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if self._panning and self._pan_start is not None:
            delta = event.position().toPoint() - self._pan_start
            self._pan_start = event.position().toPoint()
            self.horizontalScrollBar().setValue(self.horizontalScrollBar().value() - delta.x())
            self.verticalScrollBar().setValue(self.verticalScrollBar().value() - delta.y())
            event.accept()
            return
        super().mouseMoveEvent(event)

    def mouseReleaseEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        if event.button() == Qt.MouseButton.MiddleButton:
            self._panning = False
            self.setCursor(Qt.CursorShape.ArrowCursor)
            event.accept()
            return

        # Check if a socket handle was being dragged
        if event.button() == Qt.MouseButton.LeftButton:
            self._emit_socket_positions()

        super().mouseReleaseEvent(event)

    def _on_selection_changed(self) -> None:
        pass

    def _emit_socket_positions(self) -> None:
        for handle in self._scene.socket_handles:
            pos = handle.pos()
            self.socket_moved.emit(handle.socket_id, pos.x(), pos.y())

    def get_socket_positions(self) -> dict[str, tuple[float, float]]:
        return self._scene.get_socket_positions()
