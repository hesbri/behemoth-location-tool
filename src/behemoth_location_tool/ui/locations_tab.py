from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt, Slot
from PySide6.QtGui import QUndoStack
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QListWidget,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.io.location_factory import (
    add_default_back_exit_with_socket,
    add_graph_node_for_location,
    create_location_from_room,
)
from behemoth_location_tool.io.locations_loader import load_locations, save_locations
from behemoth_location_tool.model.common import Conditions, Rect
from behemoth_location_tool.model.id_utils import generate_id, generate_padded_id
from behemoth_location_tool.model.location import (
    ExitDefinition,
    GraphNode,
    LocationInstance,
    LocationsFile,
    change_location_catalog_room,
    find_catalog_room,
    get_effective_background,
    get_effective_sockets,
    migrate_location_background,
    migrate_location_sockets,
)
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.undo.commands import (
    AddExitCommand,
    AddLocationCommand,
    DeleteExitCommand,
    DeleteLocationCommand,
    EditExitCommand,
    EditLocationCommand,
    exit_changed,
    location_changed,
)


class LocationsTab(QWidget):
    """Location instances editor: list, create-from-catalog, edit exits/sockets/entities."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locations_file: LocationsFile = LocationsFile(start_location="")
        self._catalog: RoomCatalog | None = None
        self._file_path: Path | None = None
        self._dirty = False
        self._undo_dirty = False
        self._preview_callback: object | None = None
        self._undo_stack: QUndoStack | None = None
        self._prev_row = -1
        self._loading = False
        self._suppress_selection_sync = False
        self._build_ui()

    # ---- public API ----

    def load_file(self, path: Path) -> None:
        self._locations_file = load_locations(path)
        self._file_path = path
        self._dirty = False
        self._undo_dirty = False
        self._refresh_list()

    def save_file(self, path: Path | None = None) -> None:
        target = path or self._file_path
        if target is None:
            return
        self._sync_form_to_data()
        save_locations(target, self._locations_file)
        self._file_path = target
        self._dirty = False
        self._undo_dirty = False

    @property
    def locations_file(self) -> LocationsFile:
        return self._locations_file

    @property
    def is_dirty(self) -> bool:
        return self._dirty or self._undo_dirty

    @property
    def current_location_id(self) -> str:
        loc = self._current_location()
        return loc.id if loc else ""

    def select_location(self, location_id: str) -> bool:
        for idx, loc in enumerate(self._locations_file.locations):
            if loc.id == location_id:
                self._list.setCurrentRow(idx)
                return True
        return False

    def mark_dirty(self) -> None:
        self._dirty = True

    def mark_undo_dirty(self) -> None:
        self._undo_dirty = True

    def clear_undo_dirty(self) -> None:
        self._undo_dirty = False

    def set_catalog(self, catalog: RoomCatalog) -> None:
        self._catalog = catalog
        # Save current selection state
        loc = self._current_location()
        current_catalog_room_id = loc.catalog_room_id if loc else ""

        # Populate catalog room dropdown
        self._f_catalog_room_id.blockSignals(True)
        self._f_catalog_room_id.clear()
        self._f_catalog_room_id.addItem("")  # empty option
        for room in catalog.rooms:
            self._f_catalog_room_id.addItem(room.id)
        # Restore selection
        if current_catalog_room_id:
            idx = self._f_catalog_room_id.findText(current_catalog_room_id)
            if idx >= 0:
                self._f_catalog_room_id.setCurrentIndex(idx)
            else:
                self._f_catalog_room_id.setEditText(current_catalog_room_id)
        self._f_catalog_room_id.blockSignals(False)

        # Refresh the current location's display with updated catalog
        self._refresh_current_location_bg()
        if loc is not None:
            self._refresh_socket_list(loc)

    def set_preview_callback(self, callback) -> None:  # type: ignore[no-untyped-def]
        self._preview_callback = callback

    def set_undo_stack(self, undo_stack: QUndoStack | None) -> None:
        self._undo_stack = undo_stack
        if undo_stack is not None:
            undo_stack.indexChanged.connect(self._on_undo_stack_index_changed)

    # ---- UI construction ----

    def _build_ui(self) -> None:
        main_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: location list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Locations"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add Empty")
        self._add_btn.clicked.connect(self._on_add_empty)
        self._add_from_cat_btn = QPushButton("+ From Catalog")
        self._add_from_cat_btn.clicked.connect(self._on_add_from_catalog)
        self._del_btn = QPushButton("− Delete")
        self._del_btn.clicked.connect(self._on_delete)
        self._set_start_btn = QPushButton("★ Set Start")
        self._set_start_btn.clicked.connect(self._on_set_start)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._add_from_cat_btn)
        btn_row.addWidget(self._del_btn)
        btn_row.addWidget(self._set_start_btn)
        left_layout.addLayout(btn_row)
        main_splitter.addWidget(left)

        # Right: scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)

        # -- Core --
        core_group = QGroupBox("Location")
        core_form = QFormLayout(core_group)
        self._f_start_label = QLabel("(not set)")
        core_form.addRow("Start Location:", self._f_start_label)
        self._f_id = QLineEdit()
        self._f_catalog_room_id = QComboBox()
        self._f_catalog_room_id.setEditable(True)
        self._f_catalog_room_id.currentIndexChanged.connect(self._on_catalog_room_changed)
        self._f_name = QLineEdit()
        self._f_name.textChanged.connect(self._update_list_item_text)
        self._f_id.textChanged.connect(self._update_list_item_text)
        self._f_desc = QTextEdit()
        self._f_desc.setMaximumHeight(50)

        # Background inheritance controls
        self._f_bg = QLineEdit()  # hidden storage for the actual path
        self._f_bg.setVisible(False)
        self._f_bg_label = QLabel("(none)")
        self._f_bg_label.setWordWrap(True)
        self._f_bg_label.setStyleSheet("QLabel { padding: 2px; }")
        self._bg_override_btn = QPushButton("Override Background")
        self._bg_override_btn.clicked.connect(self._on_override_bg)
        self._bg_clear_btn = QPushButton("Clear Override")
        self._bg_clear_btn.clicked.connect(self._on_clear_override)
        self._bg_sync_btn = QPushButton("Sync From Catalog")
        self._bg_sync_btn.clicked.connect(self._on_sync_from_catalog)
        bg_btn_row = QHBoxLayout()
        bg_btn_row.addWidget(self._bg_override_btn)
        bg_btn_row.addWidget(self._bg_clear_btn)
        bg_btn_row.addWidget(self._bg_sync_btn)
        bg_btn_row.addStretch()
        bg_widget = QWidget()
        bg_layout = QVBoxLayout(bg_widget)
        bg_layout.setContentsMargins(0, 0, 0, 0)
        bg_layout.addWidget(self._f_bg_label)
        bg_layout.addWidget(self._f_bg)
        bg_layout.addLayout(bg_btn_row)

        self._f_width = QSpinBox()
        self._f_width.setRange(1, 9999)
        self._f_width.setValue(1920)
        self._f_height = QSpinBox()
        self._f_height.setRange(1, 9999)
        self._f_height.setValue(1080)
        self._f_tags = QLineEdit()
        self._f_tags.setPlaceholderText("tag1, tag2")
        self._f_layers = QLineEdit()
        self._f_layers.setPlaceholderText("bg, characters, fg")
        core_form.addRow("ID:", self._f_id)
        core_form.addRow("Catalog Room:", self._f_catalog_room_id)
        core_form.addRow("Name:", self._f_name)
        core_form.addRow("Description:", self._f_desc)
        core_form.addRow("Background:", bg_widget)
        core_form.addRow("Width:", self._f_width)
        core_form.addRow("Height:", self._f_height)
        core_form.addRow("Tags:", self._f_tags)
        core_form.addRow("Layers:", self._f_layers)
        form_layout.addWidget(core_group)

        # -- Sockets --
        sockets_group = QGroupBox("Sockets")
        sockets_lay = QVBoxLayout(sockets_group)

        self._socket_status_label = QLabel("Sockets: —")
        self._socket_status_label.setWordWrap(True)
        self._socket_status_label.setStyleSheet("QLabel { padding: 2px; }")
        sockets_lay.addWidget(self._socket_status_label)

        sock_btn_row = QHBoxLayout()
        self._sock_override_btn = QPushButton("Override Sockets")
        self._sock_override_btn.clicked.connect(self._on_override_sockets)
        self._sock_clear_btn = QPushButton("Clear Override")
        self._sock_clear_btn.clicked.connect(self._on_clear_socket_override)
        self._sock_sync_btn = QPushButton("Sync From Catalog")
        self._sock_sync_btn.clicked.connect(self._on_sync_sockets_from_catalog)
        sock_btn_row.addWidget(self._sock_override_btn)
        sock_btn_row.addWidget(self._sock_clear_btn)
        sock_btn_row.addWidget(self._sock_sync_btn)
        sock_btn_row.addStretch()
        sockets_lay.addLayout(sock_btn_row)

        self._socket_list = QListWidget()
        self._socket_list.setMaximumHeight(80)
        sockets_lay.addWidget(self._socket_list)
        form_layout.addWidget(sockets_group)

        # -- Exits --
        exits_group = QGroupBox("Exits")
        exits_lay = QVBoxLayout(exits_group)
        exit_btn_row = QHBoxLayout()
        self._exit_add_btn = QPushButton("+ Add Exit")
        self._exit_add_btn.clicked.connect(self._on_add_exit)
        self._exit_del_btn = QPushButton("− Delete Exit")
        self._exit_del_btn.clicked.connect(self._on_delete_exit)
        exit_btn_row.addWidget(self._exit_add_btn)
        exit_btn_row.addWidget(self._exit_del_btn)
        exits_lay.addLayout(exit_btn_row)

        self._exit_list = QListWidget()
        self._exit_list.setMaximumHeight(80)
        self._exit_list.currentRowChanged.connect(self._on_exit_selection_changed)
        exits_lay.addWidget(self._exit_list)

        exit_form = QFormLayout()
        self._ef_id = QLineEdit()
        self._ef_entity_id = QLineEdit()
        self._ef_target = QComboBox()
        self._ef_target.setEditable(True)
        self._ef_socket_id = QLineEdit()
        self._ef_layer = QLineEdit()
        self._ef_tags = QLineEdit()
        self._ef_tags.setPlaceholderText("exit.default_back, ...")
        self._ef_locked = QCheckBox("Locked")
        # Clickable rect
        self._ef_cr_check = QCheckBox("Has Clickable Rect")
        self._ef_cr_x = QSpinBox()
        self._ef_cr_x.setRange(-9999, 9999)
        self._ef_cr_y = QSpinBox()
        self._ef_cr_y.setRange(-9999, 9999)
        self._ef_cr_w = QSpinBox()
        self._ef_cr_w.setRange(0, 9999)
        self._ef_cr_h = QSpinBox()
        self._ef_cr_h.setRange(0, 9999)
        # Conditions
        self._ef_req_tags = QLineEdit()
        self._ef_req_tags.setPlaceholderText("requiresTags")
        self._ef_forb_tags = QLineEdit()
        self._ef_forb_tags.setPlaceholderText("forbiddenTags")

        exit_form.addRow("Exit ID:", self._ef_id)
        exit_form.addRow("Entity ID:", self._ef_entity_id)
        exit_form.addRow("Target Location:", self._ef_target)
        exit_form.addRow("Socket ID:", self._ef_socket_id)
        exit_form.addRow("Layer:", self._ef_layer)
        exit_form.addRow("Tags:", self._ef_tags)
        exit_form.addRow("", self._ef_locked)
        exit_form.addRow("", self._ef_cr_check)
        exit_form.addRow("Rect X:", self._ef_cr_x)
        exit_form.addRow("Rect Y:", self._ef_cr_y)
        exit_form.addRow("Rect W:", self._ef_cr_w)
        exit_form.addRow("Rect H:", self._ef_cr_h)
        exit_form.addRow("Requires Tags:", self._ef_req_tags)
        exit_form.addRow("Forbidden Tags:", self._ef_forb_tags)
        exits_lay.addLayout(exit_form)
        form_layout.addWidget(exits_group)

        # -- Placed Entities (read-only table) --
        pe_group = QGroupBox("Placed Entities")
        pe_lay = QVBoxLayout(pe_group)
        self._pe_table = QTableWidget(0, 5)
        self._pe_table.setHorizontalHeaderLabels(["Instance ID", "Entity ID", "Socket ID", "Layer", "Sort"])
        self._pe_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._pe_table.setMaximumHeight(120)
        self._pe_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        pe_lay.addWidget(self._pe_table)
        form_layout.addWidget(pe_group)

        form_layout.addStretch(1)
        scroll.setWidget(form_container)
        main_splitter.addWidget(scroll)
        main_splitter.setSizes([200, 550])

        layout = QVBoxLayout(self)
        layout.addWidget(main_splitter)
        self._set_form_enabled(False)

    # ---- helpers ----

    def _set_form_enabled(self, enabled: bool) -> None:
        for w in [self._f_id, self._f_catalog_room_id, self._f_name, self._f_desc,
                   self._f_width, self._f_height, self._f_tags, self._f_layers]:
            w.setEnabled(enabled)
        for w in [self._bg_override_btn, self._bg_clear_btn, self._bg_sync_btn,
                   self._sock_override_btn, self._sock_clear_btn, self._sock_sync_btn]:
            w.setEnabled(enabled)

    def _refresh_list(self, *, select_first: bool = True) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for loc in self._locations_file.locations:
            prefix = "★ " if loc.id == self._locations_file.start_location else "  "
            self._list.addItem(f"{prefix}{loc.id} — {loc.name}")
        self._list.blockSignals(False)
        self._f_start_label.setText(self._locations_file.start_location or "(not set)")
        if select_first and self._locations_file.locations:
            self._list.setCurrentRow(0)

    def _current_location(self) -> LocationInstance | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._locations_file.locations):
            return self._locations_file.locations[row]
        return None

    @staticmethod
    def _parse_csv(text: str) -> list[str]:
        return [t.strip() for t in text.split(",") if t.strip()]

    def _update_list_item_text(self) -> None:
        """Live-update the selected list item text when ID or name fields change."""
        if self._loading:
            return
        row = self._list.currentRow()
        if row < 0:
            return
        loc_id = self._f_id.text().strip()
        loc_name = self._f_name.text().strip()
        prefix = "★ " if loc_id == self._locations_file.start_location else "  "
        self._list.item(row).setText(f"{prefix}{loc_id} — {loc_name}")
        self._dirty = True

    def _update_bg_label(self, loc: LocationInstance) -> None:
        """Update the background label and hidden field to show inheritance status."""
        effective_bg = get_effective_background(loc, self._catalog)
        if loc.background_overridden:
            label = "Custom override"
            if loc.background_image:
                label += f": {loc.background_image}"
            else:
                label += ": (empty)"
            self._f_bg_label.setStyleSheet(
                "QLabel { padding: 2px; color: #cc6600; font-weight: bold; }"
            )
            self._f_bg_label.setText(label)
        else:
            if loc.catalog_room_id and effective_bg:
                label = f"Inherited from catalog ({loc.catalog_room_id}): {effective_bg}"
            elif loc.catalog_room_id:
                label = f"Inherited from catalog ({loc.catalog_room_id}): (none)"
            else:
                label = "No catalog room assigned"
                if effective_bg:
                    label = f"Standalone: {effective_bg}"
            self._f_bg_label.setStyleSheet(
                "QLabel { padding: 2px; color: #0066cc; }"
            )
            self._f_bg_label.setText(label)
            # Keep hidden field and model in sync with effective (inherited) bg
            # so _sync_form_to_data doesn't accidentally clear it.
            if effective_bg:
                self._f_bg.setText(effective_bg)
                if not loc.background_image:
                    loc.background_image = effective_bg

    def _refresh_current_location_bg(self) -> None:
        """Re-evaluate and refresh background for the currently selected location."""
        loc = self._current_location()
        if loc is None:
            return
        # Reconcile inheritance metadata with the current catalog.
        migrate_location_background(loc, self._catalog)
        # For non-overridden locations, update background_image from catalog
        if not loc.background_overridden:
            room = find_catalog_room(self._catalog, loc.catalog_room_id)
            if room is not None:
                loc.background_image = room.background_image
        self._f_bg.setText(loc.background_image or "")
        self._update_bg_label(loc)

    def _sync_form_to_data(self) -> None:
        if self._prev_row < 0 or self._prev_row >= len(self._locations_file.locations):
            return
        loc = self._locations_file.locations[self._prev_row]
        before = loc.model_copy(deep=True)
        after = before.model_copy(deep=True)
        after.id = self._f_id.text().strip()
        after.catalog_room_id = self._f_catalog_room_id.currentText().strip()
        after.name = self._f_name.text().strip()
        after.description = self._f_desc.toPlainText().strip()
        # background_image is managed via override/clear/sync buttons
        # but also sync from the hidden field
        bg_text = self._f_bg.text().strip()
        after.background_image = bg_text or None
        after.design_size.w = self._f_width.value()
        after.design_size.h = self._f_height.value()
        after.tags = self._parse_csv(self._f_tags.text())
        after.layers = self._parse_csv(self._f_layers.text())
        self._sync_exit_form()
        if not location_changed(before, after):
            return

        def _on_location_changed() -> None:
            self.mark_undo_dirty()
            self._refresh_from_model_preserve_selection(
                preferred_location_id=after.id,
                preferred_exit_row=self._exit_list.currentRow(),
            )

        if self._undo_stack is not None:
            self._undo_stack.push(
                EditLocationCommand(
                    locations_file=self._locations_file,
                    index=self._prev_row,
                    before=before,
                    after=after,
                    on_changed=_on_location_changed,
                )
            )
            return

        self._locations_file.locations[self._prev_row] = after
        loc = after
        prefix = "★ " if loc.id == self._locations_file.start_location else "  "
        self._list.item(self._prev_row).setText(f"{prefix}{loc.id} — {loc.name}")
        self._dirty = True

    def _sync_exit_form(self) -> None:
        if self._loading:
            return
        loc = self._current_location()
        if loc is None:
            return
        row = self._exit_list.currentRow()
        if row < 0 or row >= len(loc.exits):
            return
        before = loc.exits[row].model_copy(deep=True)
        after = before.model_copy(deep=True)
        after.id = self._ef_id.text().strip()
        after.entity_id = self._ef_entity_id.text().strip()
        after.target_location_id = self._ef_target.currentText().strip()
        after.socket_id = self._ef_socket_id.text().strip()
        after.layer = self._ef_layer.text().strip()
        after.tags = self._parse_csv(self._ef_tags.text())
        after.locked = self._ef_locked.isChecked()
        if self._ef_cr_check.isChecked():
            after.clickable_rect = Rect(
                x=self._ef_cr_x.value(), y=self._ef_cr_y.value(),
                w=self._ef_cr_w.value(), h=self._ef_cr_h.value(),
            )
        else:
            after.clickable_rect = None
        after.conditions = Conditions(
            requires_tags=self._parse_csv(self._ef_req_tags.text()),
            forbidden_tags=self._parse_csv(self._ef_forb_tags.text()),
        )
        if self._ensure_default_back_for_candidate(loc, row, after):
            self._ef_tags.setText(", ".join(after.tags))
        if not exit_changed(before, after):
            return
        if self._undo_stack is not None:
            self._undo_stack.push(
                EditExitCommand(
                    location=loc,
                    index=row,
                    before=before,
                    after=after,
                    on_changed=self.mark_undo_dirty,
                )
            )
            return
        loc.exits[row] = after
        self._dirty = True
        ex = after
        self._exit_list.item(row).setText(f"{ex.id} → {ex.target_location_id or '?'}")

    def _load_location_to_form(self, loc: LocationInstance) -> None:
        self._loading = True
        try:
            # Reconcile background inheritance metadata before displaying.
            migrate_location_background(loc, self._catalog)

            self._f_id.setText(loc.id)
            self._f_catalog_room_id.blockSignals(True)
            idx = self._f_catalog_room_id.findText(loc.catalog_room_id)
            if idx >= 0:
                self._f_catalog_room_id.setCurrentIndex(idx)
            else:
                self._f_catalog_room_id.setEditText(loc.catalog_room_id)
            self._f_catalog_room_id.blockSignals(False)
            self._f_name.setText(loc.name)
            self._f_desc.setPlainText(loc.description)
            self._f_bg.setText(loc.background_image or "")
            self._update_bg_label(loc)
            self._f_width.setValue(loc.design_size.w)
            self._f_height.setValue(loc.design_size.h)
            self._f_tags.setText(", ".join(loc.tags))
            self._f_layers.setText(", ".join(loc.layers))

            # Sockets: reconcile inheritance metadata, then show effective sockets.
            migrate_location_sockets(loc, self._catalog)
            effective_sockets = get_effective_sockets(loc, self._catalog)
            self._socket_list.blockSignals(True)
            self._socket_list.clear()
            if effective_sockets:
                for sock in effective_sockets:
                    parts = [f"{sock.id}", f"\"{sock.name}\"", f"({sock.x}, {sock.y})"]
                    if sock.layer:
                        parts.append(f"[{sock.layer}]")
                    self._socket_list.addItem("  ".join(parts))
            else:
                self._socket_list.addItem("  (no sockets)")
            self._socket_list.blockSignals(False)
            self._update_socket_status(loc)

            # Exits
            self._exit_list.blockSignals(True)
            self._exit_list.clear()
            for ex in loc.exits:
                self._exit_list.addItem(f"{ex.id} → {ex.target_location_id or '?'}")
            self._exit_list.blockSignals(False)
            if loc.exits:
                self._exit_list.setCurrentRow(0)
            else:
                self._clear_exit_form()

            # Placed entities
            self._pe_table.setRowCount(len(loc.placed_entities))
            for i, pe in enumerate(loc.placed_entities):
                self._pe_table.setItem(i, 0, QTableWidgetItem(pe.instance_id))
                self._pe_table.setItem(i, 1, QTableWidgetItem(pe.entity_id))
                self._pe_table.setItem(i, 2, QTableWidgetItem(pe.socket_id))
                self._pe_table.setItem(i, 3, QTableWidgetItem(pe.layer or ""))
                self._pe_table.setItem(i, 4, QTableWidgetItem(str(pe.sort_order)))

            self._f_start_label.setText(self._locations_file.start_location or "(not set)")
            self._refresh_target_location_combo()
        finally:
            self._loading = False

    def _load_exit_to_form(self, ex: ExitDefinition) -> None:
        self._ef_id.setText(ex.id)
        self._ef_entity_id.setText(ex.entity_id)
        idx = self._ef_target.findText(ex.target_location_id)
        if idx >= 0:
            self._ef_target.setCurrentIndex(idx)
        else:
            self._ef_target.setEditText(ex.target_location_id)
        self._ef_socket_id.setText(ex.socket_id)
        self._ef_layer.setText(ex.layer)
        self._ef_tags.setText(", ".join(ex.tags))
        self._ef_locked.setChecked(ex.locked)
        if ex.clickable_rect:
            self._ef_cr_check.setChecked(True)
            self._ef_cr_x.setValue(ex.clickable_rect.x)
            self._ef_cr_y.setValue(ex.clickable_rect.y)
            self._ef_cr_w.setValue(ex.clickable_rect.w)
            self._ef_cr_h.setValue(ex.clickable_rect.h)
        else:
            self._ef_cr_check.setChecked(False)
            self._ef_cr_x.setValue(0)
            self._ef_cr_y.setValue(0)
            self._ef_cr_w.setValue(0)
            self._ef_cr_h.setValue(0)
        self._ef_req_tags.setText(", ".join(ex.conditions.requires_tags))
        self._ef_forb_tags.setText(", ".join(ex.conditions.forbidden_tags))

    def _update_socket_status(self, loc: LocationInstance) -> None:
        """Update the socket status label showing inheritance/override state."""
        if loc.socket_overridden:
            count = len(loc.sockets)
            label = f"Sockets: Custom override ({count} socket{'s' if count != 1 else ''})"
            self._socket_status_label.setStyleSheet(
                "QLabel { padding: 2px; color: #cc6600; font-weight: bold; }"
            )
        else:
            room = find_catalog_room(self._catalog, loc.catalog_room_id)
            if room:
                count = len(room.sockets)
                socket_word = "socket" if count == 1 else "sockets"
                label = (
                    f"Sockets: Inherited from catalog ({loc.catalog_room_id}) — "
                    f"{count} {socket_word}"
                )
            else:
                count = len(loc.sockets)
                label = f"Sockets: No catalog room assigned — {count} socket{'s' if count != 1 else ''}"
            self._socket_status_label.setStyleSheet(
                "QLabel { padding: 2px; color: #0066cc; }"
            )
        self._socket_status_label.setText(label)

    def _refresh_socket_list(self, loc: LocationInstance) -> None:
        """Refresh the socket list from effective sockets."""
        effective = get_effective_sockets(loc, self._catalog)
        self._socket_list.blockSignals(True)
        self._socket_list.clear()
        if effective:
            for sock in effective:
                parts = [f"{sock.id}", f"\"{sock.name}\"", f"({sock.x}, {sock.y})"]
                if sock.layer:
                    parts.append(f"[{sock.layer}]")
                self._socket_list.addItem("  ".join(parts))
        else:
            self._socket_list.addItem("  (no sockets)")
        self._socket_list.blockSignals(False)
        self._update_socket_status(loc)

    def _clear_location_form(self) -> None:
        """Clear all location form fields and reset to defaults."""
        self._loading = True
        try:
            self._f_id.setText("")
            self._f_catalog_room_id.setCurrentIndex(0)
            self._f_name.setText("")
            self._f_desc.setPlainText("")
            self._f_bg.setText("")
            self._f_bg_label.setText("(none)")
            self._f_bg_label.setStyleSheet("QLabel { padding: 2px; }")
            self._f_width.setValue(1920)
            self._f_height.setValue(1080)
            self._f_tags.setText("")
            self._f_layers.setText("")
            self._socket_status_label.setText("Sockets: —")
            self._socket_status_label.setStyleSheet("QLabel { padding: 2px; }")
            self._socket_list.clear()
            self._exit_list.clear()
            self._clear_exit_form()
            self._pe_table.setRowCount(0)
        finally:
            self._loading = False

    def _clear_exit_form(self) -> None:
        for w in [self._ef_id, self._ef_entity_id,
                   self._ef_socket_id, self._ef_layer, self._ef_tags,
                   self._ef_req_tags, self._ef_forb_tags]:
            w.setText("")
        self._ef_target.setCurrentIndex(0)
        self._ef_locked.setChecked(False)
        self._ef_cr_check.setChecked(False)

    def _refresh_target_location_combo(self) -> None:
        """Repopulate the Target Location dropdown with all current location IDs."""
        current_text = self._ef_target.currentText()
        self._ef_target.blockSignals(True)
        self._ef_target.clear()
        self._ef_target.addItem("")  # empty option
        for loc in self._locations_file.locations:
            self._ef_target.addItem(loc.id)
        idx = self._ef_target.findText(current_text)
        if idx >= 0:
            self._ef_target.setCurrentIndex(idx)
        else:
            self._ef_target.setEditText(current_text)
        self._ef_target.blockSignals(False)

    @staticmethod
    def _is_default_back_exit(exit_def: ExitDefinition) -> bool:
        return "exit.default_back" in exit_def.tags

    def _ensure_default_back_for_candidate(
        self,
        loc: LocationInstance,
        candidate_index: int,
        candidate_exit: ExitDefinition,
    ) -> bool:
        """Ensure non-start locations always retain one default/back exit."""
        if loc.id == self._locations_file.start_location:
            return False
        exits = [ex.model_copy(deep=True) for ex in loc.exits]
        if 0 <= candidate_index < len(exits):
            exits[candidate_index] = candidate_exit.model_copy(deep=True)
        if any(self._is_default_back_exit(ex) for ex in exits):
            return False
        if "exit.default_back" in candidate_exit.tags:
            return False
        candidate_exit.tags = [*candidate_exit.tags, "exit.default_back"]
        return True

    @Slot(int)
    def _on_undo_stack_index_changed(self, _index: int) -> None:
        if not hasattr(self, "_undo_stack"):
            return
        if self._undo_stack is None:
            return
        try:
            is_clean = self._undo_stack.isClean()
        except RuntimeError:
            self._undo_stack = None
            return
        if is_clean:
            self._undo_dirty = False
        self._refresh_from_model_preserve_selection()

    def _refresh_from_model_preserve_selection(
        self,
        *,
        preferred_location_id: str = "",
        preferred_exit_row: int | None = None,
    ) -> None:
        current_location_id = preferred_location_id or self.current_location_id
        current_exit_row = (
            preferred_exit_row
            if preferred_exit_row is not None
            else self._exit_list.currentRow()
        )
        self._suppress_selection_sync = True
        try:
            self._prev_row = -1
            self._refresh_list(select_first=False)
            if not self._locations_file.locations:
                self._clear_location_form()
                self._set_form_enabled(False)
                return
            if not current_location_id or not self.select_location(current_location_id):
                self._list.setCurrentRow(0)
            loc = self._current_location()
            if loc is None:
                return
            if loc.exits:
                row = max(0, min(int(current_exit_row), len(loc.exits) - 1))
                self._exit_list.setCurrentRow(row)
            else:
                self._clear_exit_form()
        finally:
            self._suppress_selection_sync = False

    def _notify_preview(self) -> None:
        if self._preview_callback is not None:
            self._preview_callback()

    # ---- socket inheritance slots ----

    def _on_override_sockets(self) -> None:
        """Copy current effective sockets into the location override list."""
        loc = self._current_location()
        if loc is None:
            return
        effective = get_effective_sockets(loc, self._catalog)
        loc.sockets = [s.model_copy(deep=True) for s in effective]
        loc.socket_overridden = True
        self._refresh_socket_list(loc)
        self._dirty = True

    def _on_clear_socket_override(self) -> None:
        """Clear socket override, returning to catalog inheritance."""
        loc = self._current_location()
        if loc is None:
            return
        loc.socket_overridden = False
        loc.sockets = []
        self._refresh_socket_list(loc)
        self._dirty = True

    def _on_sync_sockets_from_catalog(self) -> None:
        """Sync sockets from catalog, clearing any override."""
        self._on_clear_socket_override()
        self._notify_preview()

    # ---- background inheritance slots ----

    def _on_override_bg(self) -> None:
        """Open file dialog to set a custom background override."""
        loc = self._current_location()
        if loc is None:
            return
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", "",
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        bg_path = Path(path).as_posix()
        loc.background_image = bg_path
        loc.background_overridden = True
        self._f_bg.setText(bg_path)
        self._update_bg_label(loc)
        self._dirty = True

    def _on_clear_override(self) -> None:
        """Clear the background override, returning to catalog inheritance."""
        loc = self._current_location()
        if loc is None:
            return
        loc.background_overridden = False
        # Set background_image to catalog's value
        room = find_catalog_room(self._catalog, loc.catalog_room_id)
        loc.background_image = room.background_image if room else None
        self._f_bg.setText(loc.background_image or "")
        self._update_bg_label(loc)
        self._dirty = True

    def _on_sync_from_catalog(self) -> None:
        """Sync background from catalog, clearing any override."""
        self._on_clear_override()
        self._notify_preview()

    def _on_catalog_room_changed(self, _index: int) -> None:
        """Handle catalog room dropdown change with inheritance logic."""
        if self._loading:
            return
        loc = self._current_location()
        if loc is None:
            return
        new_room_id = self._f_catalog_room_id.currentText().strip()
        if new_room_id == loc.catalog_room_id:
            return
        change_location_catalog_room(loc, new_room_id, self._catalog)
        self._f_bg.setText(loc.background_image or "")
        self._update_bg_label(loc)
        self._refresh_socket_list(loc)
        self._dirty = True

    # ---- slots ----

    def _on_selection_changed(self, row: int) -> None:
        if self._suppress_selection_sync:
            self._prev_row = row
            if 0 <= row < len(self._locations_file.locations):
                self._load_location_to_form(self._locations_file.locations[row])
                self._set_form_enabled(True)
            else:
                self._set_form_enabled(False)
            return
        self._sync_form_to_data()
        self._prev_row = row
        if 0 <= row < len(self._locations_file.locations):
            self._load_location_to_form(self._locations_file.locations[row])
            self._set_form_enabled(True)
            self._notify_preview()
        else:
            self._set_form_enabled(False)

    def _on_exit_selection_changed(self, row: int) -> None:
        if self._suppress_selection_sync:
            loc = self._current_location()
            if loc and 0 <= row < len(loc.exits):
                self._load_exit_to_form(loc.exits[row])
            return
        self._sync_exit_form()
        loc = self._current_location()
        if loc and 0 <= row < len(loc.exits):
            self._load_exit_to_form(loc.exits[row])

    def _on_add_empty(self) -> None:
        existing = {loc.id for loc in self._locations_file.locations}
        new_id = generate_padded_id("new_location", existing, fallback="location")
        new_name = f"Location {len(self._locations_file.locations) + 1}"
        is_start = not self._locations_file.locations
        loc = LocationInstance(
            id=new_id,
            catalog_room_id="",
            name=new_name,
        )
        if not is_start:
            add_default_back_exit_with_socket(
                loc,
                target_location_id=self._locations_file.start_location,
            )
        if self._undo_stack is None:
            self._locations_file.locations.append(loc)
            add_graph_node_for_location(self._locations_file, loc.id)
            if is_start:
                self._locations_file.start_location = loc.id
            self._refresh_list()
            self._list.setCurrentRow(len(self._locations_file.locations) - 1)
            self._dirty = True
            return

        node_x, node_y = 100, 100
        if self._locations_file.graph.nodes:
            last = self._locations_file.graph.nodes[-1]
            node_x = last.x + 250
            node_y = last.y
        self._undo_stack.push(
            AddLocationCommand(
                locations_file=self._locations_file,
                location=loc,
                graph_node=GraphNode(location_id=loc.id, x=node_x, y=node_y),
                index=len(self._locations_file.locations),
                set_start_on_add=is_start,
                on_changed=self.mark_undo_dirty,
            )
        )
        self._refresh_from_model_preserve_selection(preferred_location_id=loc.id)

    def _on_add_from_catalog(self) -> None:
        if self._catalog is None:
            return
        rooms = self._catalog.rooms
        if not rooms:
            return
        # Use first room that hasn't been used yet
        existing_ids = {loc.catalog_room_id for loc in self._locations_file.locations}
        room = None
        for r in rooms:
            if r.id not in existing_ids:
                room = r
                break
        if room is None:
            room = rooms[0]

        is_start = not self._locations_file.locations
        loc = create_location_from_room(
            room, is_start=is_start,
            start_location_id=self._locations_file.start_location or "",
        )
        if self._undo_stack is None:
            self._locations_file.locations.append(loc)
            add_graph_node_for_location(self._locations_file, loc.id)
            if is_start:
                self._locations_file.start_location = loc.id
            self._refresh_list()
            self._list.setCurrentRow(len(self._locations_file.locations) - 1)
            self._dirty = True
            return

        node_x, node_y = 100, 100
        if self._locations_file.graph.nodes:
            last = self._locations_file.graph.nodes[-1]
            node_x = last.x + 250
            node_y = last.y
        self._undo_stack.push(
            AddLocationCommand(
                locations_file=self._locations_file,
                location=loc,
                graph_node=GraphNode(location_id=loc.id, x=node_x, y=node_y),
                index=len(self._locations_file.locations),
                set_start_on_add=is_start,
                on_changed=self.mark_undo_dirty,
            )
        )
        self._refresh_from_model_preserve_selection(preferred_location_id=loc.id)

    def _on_delete(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        loc = self._locations_file.locations[row]
        if self._undo_stack is None:
            del self._locations_file.locations[row]
            # Remove graph node
            self._locations_file.graph.nodes = [
                n for n in self._locations_file.graph.nodes if n.location_id != loc.id
            ]
            if self._locations_file.start_location == loc.id:
                self._locations_file.start_location = (
                    self._locations_file.locations[0].id if self._locations_file.locations else ""
                )
            self._prev_row = -1
            self._refresh_list()
            if not self._locations_file.locations:
                self._clear_location_form()
                self._set_form_enabled(False)
            self._dirty = True
            return

        remaining = [item for item in self._locations_file.locations if item.id != loc.id]
        start_after = self._locations_file.start_location
        if self._locations_file.start_location == loc.id:
            start_after = remaining[0].id if remaining else ""
        graph_node = next(
            (
                node.model_copy(deep=True)
                for node in self._locations_file.graph.nodes
                if node.location_id == loc.id
            ),
            None,
        )
        self._undo_stack.push(
            DeleteLocationCommand(
                locations_file=self._locations_file,
                location=loc,
                graph_node=graph_node,
                index=row,
                start_after=start_after,
                on_changed=self.mark_undo_dirty,
            )
        )
        self._refresh_from_model_preserve_selection()

    def _on_set_start(self) -> None:
        loc = self._current_location()
        if loc is None:
            return
        self._locations_file.start_location = loc.id
        self._refresh_list()
        self._dirty = True

    def _on_add_exit(self) -> None:
        loc = self._current_location()
        if loc is None:
            return
        existing = {ex.id for ex in loc.exits}
        new_id = generate_id("new_exit", existing, fallback="exit")
        ex = ExitDefinition(
            id=new_id,
            entity_id=new_id,
            target_location_id="", socket_id="",
        )
        if self._undo_stack is not None:
            self._undo_stack.push(
                AddExitCommand(
                    location=loc,
                    exit_def=ex,
                    index=len(loc.exits),
                    on_changed=self.mark_undo_dirty,
                )
            )
            self._refresh_from_model_preserve_selection(
                preferred_location_id=loc.id,
                preferred_exit_row=len(loc.exits) - 1,
            )
            return
        loc.exits.append(ex)
        self._exit_list.addItem(f"{ex.id} → ?")
        self._loading = True
        self._exit_list.setCurrentRow(len(loc.exits) - 1)
        self._loading = False
        self._load_exit_to_form(ex)
        self._dirty = True

    def _on_delete_exit(self) -> None:
        loc = self._current_location()
        if loc is None:
            return
        row = self._exit_list.currentRow()
        if row < 0 or row >= len(loc.exits):
            return
        start_id = self._locations_file.start_location
        if loc.id != start_id:
            default_back_indices = [
                idx for idx, ex in enumerate(loc.exits)
                if self._is_default_back_exit(ex)
            ]
            if row in default_back_indices and len(default_back_indices) == 1:
                QMessageBox.warning(
                    self,
                    "Default Back Exit Required",
                    "Non-start locations must keep at least one exit tagged exit.default_back.",
                )
                return
        if self._undo_stack is not None:
            deleted = loc.exits[row].model_copy(deep=True)
            self._undo_stack.push(
                DeleteExitCommand(
                    location=loc,
                    exit_def=deleted,
                    index=row,
                    on_changed=self.mark_undo_dirty,
                )
            )
            self._refresh_from_model_preserve_selection(
                preferred_location_id=loc.id,
                preferred_exit_row=min(row, len(loc.exits) - 1),
            )
            return
        del loc.exits[row]
        self._exit_list.blockSignals(True)
        self._exit_list.clear()
        for ex in loc.exits:
            self._exit_list.addItem(f"{ex.id} → {ex.target_location_id or '?'}")
        self._exit_list.blockSignals(False)
        if loc.exits:
            self._exit_list.setCurrentRow(0)
        else:
            self._clear_exit_form()
        self._dirty = True
