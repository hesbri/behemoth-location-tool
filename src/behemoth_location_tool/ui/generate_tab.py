"""Generate tab - preview-first deterministic ambient fill, then Apply."""
from __future__ import annotations

from collections.abc import Callable

from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QComboBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.generation.generation_service import (
    apply_preview_to_location,
    generate_ambient_preview,
)
from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationInstance, LocationsFile, get_effective_sockets
from behemoth_location_tool.model.room import RoomCatalog, SocketDefinition
from behemoth_location_tool.undo.commands import ApplyGenerationResultCommand


def _run_ambient_fill(
    location: LocationInstance,
    sockets: list[SocketDefinition],
    entities: list[EntityDefinition],
    mansion_seed: int,
) -> list[PlacementResultRow]:
    """Backward-compatible test hook while generation logic lives in services."""
    return generate_ambient_preview(location, sockets, entities, mansion_seed)


class GenerateTab(QWidget):
    """Preview-first deterministic ambient fill, then Apply."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locations_file: LocationsFile | None = None
        self._catalog: RoomCatalog | None = None
        self._entities: list[EntityDefinition] = []
        self._preview_rows: list[PlacementResultRow] = []
        self._send_preview_callback: (
            Callable[[LocationInstance, list[PlacementResultRow]], bool] | None
        ) = None
        self._apply_callback: Callable[[LocationInstance], None] | None = None
        self._undo_stack: QUndoStack | None = None
        self._build_ui()

    def set_locations_file(self, lf: LocationsFile) -> None:
        self._locations_file = lf
        self._refresh_combo()
        self._seed_spin.setValue(lf.mansion_seed)

    def set_catalog(self, catalog: RoomCatalog | None) -> None:
        self._catalog = catalog

    def set_entities(self, entities: list[EntityDefinition]) -> None:
        self._entities = list(entities)

    def set_send_preview_callback(
        self,
        callback: Callable[[LocationInstance, list[PlacementResultRow]], bool] | None,
    ) -> None:
        self._send_preview_callback = callback

    def set_apply_callback(self, callback: Callable[[LocationInstance], None] | None) -> None:
        self._apply_callback = callback

    def set_undo_stack(self, undo_stack: QUndoStack | None) -> None:
        self._undo_stack = undo_stack

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        settings = QGroupBox("Generation Settings")
        slay = QVBoxLayout(settings)

        row = QHBoxLayout()
        row.addWidget(QLabel("Location:"))
        self._combo = QComboBox()
        row.addWidget(self._combo, 1)
        slay.addLayout(row)

        row2 = QHBoxLayout()
        row2.addWidget(QLabel("Mansion Seed:"))
        self._seed_spin = QSpinBox()
        self._seed_spin.setRange(0, 2_147_483_647)
        row2.addWidget(self._seed_spin, 1)
        slay.addLayout(row2)

        root.addWidget(settings)

        self._table = QTableWidget(0, 4)
        self._table.setHorizontalHeaderLabels(["Socket", "Entity", "Source", "Status"])
        self._table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        root.addWidget(self._table, 1)

        btn_row = QHBoxLayout()
        self._gen_btn = QPushButton("Generate Preview")
        self._gen_btn.clicked.connect(self._on_generate)
        self._apply_btn = QPushButton("Apply to Location")
        self._apply_btn.setEnabled(False)
        self._apply_btn.clicked.connect(self._on_apply)
        self._discard_btn = QPushButton("Discard Preview")
        self._discard_btn.setEnabled(False)
        self._discard_btn.clicked.connect(self._on_discard)
        self._send_preview_btn = QPushButton("Send Preview To Runtime")
        self._send_preview_btn.setEnabled(False)
        self._send_preview_btn.clicked.connect(self._on_send_preview)
        btn_row.addWidget(self._gen_btn)
        btn_row.addWidget(self._send_preview_btn)
        btn_row.addWidget(self._apply_btn)
        btn_row.addWidget(self._discard_btn)
        btn_row.addStretch(1)
        root.addLayout(btn_row)

    def _refresh_combo(self) -> None:
        self._combo.clear()
        if self._locations_file is None:
            return
        for loc in self._locations_file.locations:
            self._combo.addItem(f"{loc.name} ({loc.id})", loc.id)

    def _current_location(self) -> LocationInstance | None:
        if self._locations_file is None:
            return None
        loc_id = self._combo.currentData()
        for loc in self._locations_file.locations:
            if loc.id == loc_id:
                return loc
        return None

    def _on_generate(self) -> None:
        location = self._current_location()
        if location is None:
            QMessageBox.warning(self, "No Location", "Select a location first.")
            return
        seed = self._seed_spin.value()
        effective_sockets = get_effective_sockets(location, self._catalog)
        self._preview_rows = _run_ambient_fill(location, effective_sockets, self._entities, seed)
        self._table.setRowCount(0)
        for row in self._preview_rows:
            table_row = self._table.rowCount()
            self._table.insertRow(table_row)
            self._table.setItem(table_row, 0, QTableWidgetItem(row.socket_id))
            self._table.setItem(table_row, 1, QTableWidgetItem(row.entity_id or "-"))
            self._table.setItem(table_row, 2, QTableWidgetItem(row.placement_source or "-"))
            status = "placed" if row.placed else f"skipped: {row.reject_reason}"
            self._table.setItem(table_row, 3, QTableWidgetItem(status))
        has_placed = any(row.placed for row in self._preview_rows)
        self._apply_btn.setEnabled(has_placed)
        self._send_preview_btn.setEnabled(has_placed)
        self._discard_btn.setEnabled(True)

    def _on_apply(self) -> None:
        location = self._current_location()
        if location is None or not self._preview_rows:
            return
        if self._undo_stack is None:
            apply_preview_to_location(location, self._preview_rows)
            if self._apply_callback is not None:
                self._apply_callback(location)
        else:
            self._undo_stack.push(
                ApplyGenerationResultCommand(
                    location=location,
                    preview_rows=list(self._preview_rows),
                    on_changed=(lambda: self._apply_callback(location)) if self._apply_callback else None,
                )
            )
        self._preview_rows = []
        self._table.setRowCount(0)
        self._apply_btn.setEnabled(False)
        self._send_preview_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)

    def _on_discard(self) -> None:
        self._preview_rows = []
        self._table.setRowCount(0)
        self._apply_btn.setEnabled(False)
        self._send_preview_btn.setEnabled(False)
        self._discard_btn.setEnabled(False)

    def _on_send_preview(self) -> None:
        location = self._current_location()
        if location is None:
            return
        placed_rows = [row for row in self._preview_rows if row.placed]
        if not placed_rows:
            return
        if self._send_preview_callback is None:
            QMessageBox.warning(self, "Preview Unavailable", "Runtime preview callback is not configured.")
            return
        ok = self._send_preview_callback(location, placed_rows)
        if not ok:
            QMessageBox.warning(self, "Preview Unavailable", "Preview runtime is not running.")
