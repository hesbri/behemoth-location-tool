from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QCheckBox, QComboBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel,
    QLineEdit, QListWidget, QPushButton, QSpinBox, QSplitter, QVBoxLayout,
    QWidget, QFormLayout, QScrollArea, QTextEdit, QTableWidget,
    QTableWidgetItem, QHeaderView,
)

from behemoth_location_tool.io.location_factory import (
    add_graph_node_for_location,
    add_default_back_exit_with_socket,
    create_location_from_room,
)
from behemoth_location_tool.io.locations_loader import load_locations, save_locations
from behemoth_location_tool.model.common import Conditions, Rect
from behemoth_location_tool.model.id_utils import generate_id, generate_padded_id
from behemoth_location_tool.model.location import (
    ExitDefinition, LocationInstance, LocationsFile, PlacedEntity,
    change_location_catalog_room, find_catalog_room, get_effective_background,
    get_effective_sockets, migrate_location_background, migrate_location_sockets,
)
from behemoth_location_tool.model.room import RoomCatalog, SocketDefinition


class LocationsTab(QWidget):
    """Location instances editor: list, create-from-catalog, edit exits/sockets/entities."""

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._locations_file: LocationsFile = LocationsFile(start_location="")
        self._catalog: RoomCatalog | None = None
        self._file_path: Path | None = None
        self._dirty = False
        self._preview_callback: object | None = None
        self._prev_row = -1
        self._loading = False
        self._build_ui()

    # ---- public API ----

    def load_file(self, path: Path) -> None:
        self._locations_file = load_locations(path)
        self._file_path = path
        self._dirty = False
        self._refresh_list()

    def save_file(self, path: Path | None = None) -> None:
        target = path or self._file_path
        if target is None:
            return
        self._sync_form_to_data()
        save_locations(target, self._locations_file)
        self._file_path = target
        self._dirty = False

    @property
    def locations_file(self) -> LocationsFile:
        return self._locations_file

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    @property
    def current_location_id(self) -> str:
        loc = self._current_location()
        return loc.id if loc else ""

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

        self._f_width = QSpinBox(); self._f_width.setRange(1, 9999); self._f_width.setValue(1920)
        self._f_height = QSpinBox(); self._f_height.setRange(1, 9999); self._f_height.setValue(1080)
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
        self._ef_cr_x = QSpinBox(); self._ef_cr_x.setRange(-9999, 9999)
        self._ef_cr_y = QSpinBox(); self._ef_cr_y.setRange(-9999, 9999)
        self._ef_cr_w = QSpinBox(); self._ef_cr_w.setRange(0, 9999)
        self._ef_cr_h = QSpinBox(); self._ef_cr_h.setRange(0, 9999)
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

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for loc in self._locations_file.locations:
            prefix = "★ " if loc.id == self._locations_file.start_location else "  "
            self._list.addItem(f"{prefix}{loc.id} — {loc.name}")
        self._list.blockSignals(False)
        self._f_start_label.setText(self._locations_file.start_location or "(not set)")
        if self._locations_file.locations:
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
        # Re-run migration with the new catalog
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
        loc.id = self._f_id.text().strip()
        loc.catalog_room_id = self._f_catalog_room_id.currentText().strip()
        loc.name = self._f_name.text().strip()
        loc.description = self._f_desc.toPlainText().strip()
        # background_image is managed via override/clear/sync buttons
        # but also sync from the hidden field
        bg_text = self._f_bg.text().strip()
        loc.background_image = bg_text or None
        loc.design_size.w = self._f_width.value()
        loc.design_size.h = self._f_height.value()
        loc.tags = self._parse_csv(self._f_tags.text())
        loc.layers = self._parse_csv(self._f_layers.text())
        self._sync_exit_form()
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
        ex = loc.exits[row]
        ex.id = self._ef_id.text().strip()
        ex.entity_id = self._ef_entity_id.text().strip()
        ex.target_location_id = self._ef_target.currentText().strip()
        ex.socket_id = self._ef_socket_id.text().strip()
        ex.layer = self._ef_layer.text().strip()
        ex.tags = self._parse_csv(self._ef_tags.text())
        ex.locked = self._ef_locked.isChecked()
        if self._ef_cr_check.isChecked():
            ex.clickable_rect = Rect(
                x=self._ef_cr_x.value(), y=self._ef_cr_y.value(),
                w=self._ef_cr_w.value(), h=self._ef_cr_h.value(),
            )
        else:
            ex.clickable_rect = None
        ex.conditions = Conditions(
            requires_tags=self._parse_csv(self._ef_req_tags.text()),
            forbidden_tags=self._parse_csv(self._ef_forb_tags.text()),
        )
        self._exit_list.item(row).setText(f"{ex.id} → {ex.target_location_id or '?'}")

    def _load_location_to_form(self, loc: LocationInstance) -> None:
        self._loading = True
        try:
            # Migrate legacy background data
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

            # Sockets — migrate legacy data first, then show effective sockets
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
                label = f"Sockets: Inherited from catalog ({loc.catalog_room_id}) — {count} socket{'s' if count != 1 else ''}"
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
        self._sync_form_to_data()
        self._prev_row = row
        if 0 <= row < len(self._locations_file.locations):
            self._load_location_to_form(self._locations_file.locations[row])
            self._set_form_enabled(True)
            self._notify_preview()
        else:
            self._set_form_enabled(False)

    def _on_exit_selection_changed(self, row: int) -> None:
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
        self._locations_file.locations.append(loc)
        add_graph_node_for_location(self._locations_file, loc.id)
        if is_start:
            self._locations_file.start_location = loc.id
        self._refresh_list()
        self._list.setCurrentRow(len(self._locations_file.locations) - 1)
        self._dirty = True

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
        self._locations_file.locations.append(loc)
        add_graph_node_for_location(self._locations_file, loc.id)
        if is_start:
            self._locations_file.start_location = loc.id
        self._refresh_list()
        self._list.setCurrentRow(len(self._locations_file.locations) - 1)
        self._dirty = True

    def _on_delete(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        loc = self._locations_file.locations[row]
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
