from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QComboBox, QDoubleSpinBox, QFileDialog, QGroupBox, QHBoxLayout, QLabel, QLineEdit, QListWidget,
    QPushButton, QSpinBox, QSplitter, QVBoxLayout, QWidget, QFormLayout,
    QScrollArea, QTextEdit, QCheckBox, QTableWidget, QTableWidgetItem,
    QHeaderView, QStackedWidget,
)

from behemoth_location_tool.io.room_catalog_loader import load_room_catalog, save_room_catalog
from behemoth_location_tool.model.common import DEFAULT_LAYERS, PivotMode
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.id_utils import generate_id, generate_padded_id
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.tags import matches_all, matches_none
from behemoth_location_tool.model.room import (
    AmbientRule, LayerConfig, RoomCatalog, RoomCatalogEntry, SocketDefinition,
    WeightedEntityEntry, WeightedFillEntry,
)
from behemoth_location_tool.preview.snapshot import build_room_catalog_snapshot, write_preview_snapshot
from behemoth_location_tool.ui.room_scene import RoomCanvas


class RoomCatalogTab(QWidget):
    """Room catalog editor: list, create, edit background, tags, layers, sockets + visual canvas."""

    def __init__(self, project: ProjectConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._catalog: RoomCatalog = RoomCatalog()
        self._file_path: Path | None = None
        self._dirty = False
        self._project = project
        self._entities: list[EntityDefinition] = []
        self._preview_callback: object | None = None  # set by MainWindow
        self._catalog_changed_callback: object | None = None  # set by MainWindow
        self._updating_canvas = False  # guard for programmatic updates
        self._prev_row = -1
        self._loading = False
        self._build_ui()

    # ---- public API ----

    def load_file(self, path: Path) -> None:
        self._catalog = load_room_catalog(path)
        self._file_path = path
        self._dirty = False
        self._refresh_list()
        if self._catalog_changed_callback is not None:
            self._catalog_changed_callback()

    def save_file(self, path: Path | None = None) -> None:
        target = path or self._file_path
        if target is None:
            return
        self._sync_form_to_catalog()
        save_room_catalog(target, self._catalog)
        self._file_path = target
        self._dirty = False

    @property
    def catalog(self) -> RoomCatalog:
        return self._catalog

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def set_preview_callback(self, callback) -> None:  # type: ignore[no-untyped-def]
        """Set callback(room: RoomCatalogEntry) to trigger snapshot write + send."""
        self._preview_callback = callback

    def set_catalog_changed_callback(self, callback) -> None:  # type: ignore[no-untyped-def]
        """Set callback() triggered when rooms are added/deleted/catalog loaded."""
        self._catalog_changed_callback = callback

    def set_entities(self, entities: list[EntityDefinition]) -> None:
        """Update the entity list used for ambient tag-query match counts."""
        self._entities = entities

    # ---- UI construction ----

    def _build_ui(self) -> None:
        main_splitter = QSplitter(Qt.Orientation.Vertical)

        # === TOP: Canvas ===
        canvas_group = QGroupBox("Room Preview")
        canvas_layout = QVBoxLayout(canvas_group)
        self._canvas = RoomCanvas()
        self._canvas.setMinimumHeight(300)
        self._canvas.socket_moved.connect(self._on_socket_moved)
        canvas_layout.addWidget(self._canvas)

        canvas_btn_row = QHBoxLayout()
        self._fit_btn = QPushButton("Fit to View")
        self._fit_btn.clicked.connect(self._canvas.fit_to_view)
        self._show_labels_cb = QCheckBox("Show Socket Names")
        self._show_labels_cb.setChecked(True)
        self._show_labels_cb.toggled.connect(self._on_toggle_labels)
        canvas_btn_row.addWidget(self._fit_btn)
        canvas_btn_row.addWidget(self._show_labels_cb)
        canvas_btn_row.addStretch()
        canvas_layout.addLayout(canvas_btn_row)
        main_splitter.addWidget(canvas_group)

        # === BOTTOM: List + Form ===
        bottom_splitter = QSplitter(Qt.Orientation.Horizontal)

        # Left: room list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.addWidget(QLabel("Rooms"))
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(self._list)
        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._add_btn.clicked.connect(self._on_add)
        self._del_btn = QPushButton("− Delete")
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._del_btn)
        left_layout.addLayout(btn_row)
        bottom_splitter.addWidget(left)

        # Right: scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        form_layout = QVBoxLayout(form_container)

        # -- Core --
        core_group = QGroupBox("Core")
        core_form = QFormLayout(core_group)
        self._f_id = QLineEdit()
        self._f_name = QLineEdit()
        self._f_desc = QTextEdit()
        self._f_desc.setMaximumHeight(50)
        self._f_bg = QLineEdit()
        self._f_bg.setPlaceholderText("path/to/background.png (relative to Image Root)")
        self._f_bg_browse = QPushButton("…")
        self._f_bg_browse.setFixedWidth(30)
        self._f_bg_browse.clicked.connect(self._on_browse_bg)
        bg_row = QHBoxLayout()
        bg_row.addWidget(self._f_bg)
        bg_row.addWidget(self._f_bg_browse)

        self._f_bg_thumb = QLabel("No image")
        self._f_bg_thumb.setFixedSize(160, 90)
        self._f_bg_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._f_bg_thumb.setStyleSheet(
            "QLabel { border: 1px solid #888; background: #1a1a1a; color: #999; font-size: 11px; }"
        )
        self._f_bg_warn = QLabel("")
        self._f_bg_warn.setStyleSheet("QLabel { color: #cc6600; font-size: 11px; }")

        self._f_width = QSpinBox(); self._f_width.setRange(1, 9999); self._f_width.setValue(1920)
        self._f_height = QSpinBox(); self._f_height.setRange(1, 9999); self._f_height.setValue(1080)
        self._f_id.textChanged.connect(self._update_list_item_text)
        self._f_name.textChanged.connect(self._update_list_item_text)
        self._f_bg.textChanged.connect(self._on_bg_text_changed)
        core_form.addRow("ID:", self._f_id)
        core_form.addRow("Name:", self._f_name)
        core_form.addRow("Description:", self._f_desc)
        core_form.addRow("Background:", bg_row)
        core_form.addRow("", self._f_bg_thumb)
        core_form.addRow("", self._f_bg_warn)
        core_form.addRow("Width:", self._f_width)
        core_form.addRow("Height:", self._f_height)
        form_layout.addWidget(core_group)

        # -- Tags --
        tags_group = QGroupBox("Tags")
        tags_lay = QVBoxLayout(tags_group)
        self._f_tags = QLineEdit()
        self._f_tags.setPlaceholderText("tag1, tag2, ...")
        tags_lay.addWidget(self._f_tags)
        form_layout.addWidget(tags_group)

        # -- Layers --
        layers_group = QGroupBox("Layers")
        layers_form = QFormLayout(layers_group)
        self._f_layer_mode = QComboBox()
        self._f_layer_mode.addItems(["project_default", "custom"])
        self._f_layer_order = QLineEdit()
        self._f_layer_order.setPlaceholderText("bg, characters, fg (comma-separated)")
        self._f_layer_overrides = QLineEdit()
        self._f_layer_overrides.setPlaceholderText("override1, override2")
        layers_form.addRow("Mode:", self._f_layer_mode)
        layers_form.addRow("Order:", self._f_layer_order)
        layers_form.addRow("Overrides:", self._f_layer_overrides)
        form_layout.addWidget(layers_group)

        # -- Sockets --
        sockets_group = QGroupBox("Sockets")
        sockets_lay = QVBoxLayout(sockets_group)

        sock_btn_row = QHBoxLayout()
        self._sock_add_btn = QPushButton("+ Add Socket")
        self._sock_add_btn.clicked.connect(self._on_add_socket)
        self._sock_del_btn = QPushButton("− Delete Socket")
        self._sock_del_btn.clicked.connect(self._on_delete_socket)
        sock_btn_row.addWidget(self._sock_add_btn)
        sock_btn_row.addWidget(self._sock_del_btn)
        sockets_lay.addLayout(sock_btn_row)

        self._socket_list = QListWidget()
        self._socket_list.setMaximumHeight(80)
        self._socket_list.currentRowChanged.connect(self._on_socket_selection_changed)
        sockets_lay.addWidget(self._socket_list)

        # ---- Socket Identity ----
        identity_group = QGroupBox("Socket Identity")
        identity_form = QFormLayout(identity_group)
        self._sf_id = QLineEdit()
        self._sf_name = QLineEdit()
        self._sf_desc = QLineEdit()
        identity_form.addRow("Socket ID:", self._sf_id)
        identity_form.addRow("Name:", self._sf_name)
        identity_form.addRow("Description:", self._sf_desc)
        sockets_lay.addWidget(identity_group)

        # ---- Transform ----
        transform_group = QGroupBox("Transform")
        transform_form = QFormLayout(transform_group)
        self._sf_x = QSpinBox(); self._sf_x.setRange(-9999, 9999)
        self._sf_y = QSpinBox(); self._sf_y.setRange(-9999, 9999)
        self._sf_rotation = QDoubleSpinBox(); self._sf_rotation.setRange(-360, 360); self._sf_rotation.setDecimals(1)
        self._sf_scale = QDoubleSpinBox(); self._sf_scale.setRange(0.01, 100); self._sf_scale.setDecimals(2); self._sf_scale.setValue(1.0)
        self._sf_pivot_mode = QComboBox()
        self._sf_pivot_mode.addItems([m.value for m in PivotMode])
        self._sf_layer = QComboBox()
        self._sf_layer.setEditable(True)
        self._sf_layer.addItems(DEFAULT_LAYERS)
        self._sf_sort = QSpinBox(); self._sf_sort.setRange(-9999, 9999)
        transform_form.addRow("X:", self._sf_x)
        transform_form.addRow("Y:", self._sf_y)
        transform_form.addRow("Rotation:", self._sf_rotation)
        transform_form.addRow("Scale:", self._sf_scale)
        transform_form.addRow("Pivot Mode:", self._sf_pivot_mode)
        transform_form.addRow("Layer:", self._sf_layer)
        transform_form.addRow("Sort Order:", self._sf_sort)
        sockets_lay.addWidget(transform_group)

        # ---- Placement Eligibility ----
        eligibility_group = QGroupBox("Placement Eligibility")
        eligibility_form = QFormLayout(eligibility_group)
        eligibility_info = QLabel("Socket-level filters used by explicit placement and ambient generation.")
        eligibility_info.setWordWrap(True)
        eligibility_info.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        eligibility_form.addRow(eligibility_info)
        self._sf_req_tags = QLineEdit()
        self._sf_req_tags.setPlaceholderText("tag1, tag2")
        self._sf_forb_tags = QLineEdit()
        self._sf_forb_tags.setPlaceholderText("tag1, tag2")
        eligibility_form.addRow("Required Tags:", self._sf_req_tags)
        eligibility_form.addRow("Forbidden Tags:", self._sf_forb_tags)
        sockets_lay.addWidget(eligibility_group)

        # ---- Ambient Fill ----
        ambient_group = QGroupBox("Ambient Fill")
        ambient_lay = QVBoxLayout(ambient_group)

        ambient_info = QLabel(
            "Ambient Spawn Chance controls random filler. "
            "Explicit placement can still use this socket when Ambient Spawn Chance is 0%."
        )
        ambient_info.setWordWrap(True)
        ambient_info.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        ambient_lay.addWidget(ambient_info)

        ambient_chance_row = QFormLayout()
        self._sf_ambient_chance = QSpinBox(); self._sf_ambient_chance.setRange(0, 100)
        self._sf_ambient_chance.setSuffix("%")
        ambient_chance_row.addRow("Ambient Spawn Chance:", self._sf_ambient_chance)
        ambient_lay.addLayout(ambient_chance_row)

        ambient_mode_row = QFormLayout()
        self._sf_ambient_mode = QComboBox()
        self._sf_ambient_mode.addItems(["none", "tag_query", "weighted_entity_list", "weighted_entries"])
        self._sf_ambient_mode.currentIndexChanged.connect(self._on_ambient_mode_changed)
        ambient_mode_row.addRow("Ambient Rule Mode:", self._sf_ambient_mode)
        ambient_lay.addLayout(ambient_mode_row)

        # Stacked widget for mode-specific content
        self._ambient_stack = QStackedWidget()

        # Page 0: none
        none_page = QWidget()
        none_lay = QVBoxLayout(none_page)
        none_label = QLabel("No ambient rules configured.")
        none_label.setStyleSheet("QLabel { color: #999; font-style: italic; }")
        none_lay.addWidget(none_label)
        self._ambient_stack.addWidget(none_page)

        # Page 1: tag_query
        tq_page = QWidget()
        tq_form = QFormLayout(tq_page)
        tq_info = QLabel("If spawn chance succeeds, select uniformly from entities matching this tag query.")
        tq_info.setWordWrap(True)
        tq_info.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        tq_form.addRow(tq_info)
        self._sf_ar_req_tags = QLineEdit()
        self._sf_ar_req_tags.setPlaceholderText("tag1, tag2")
        self._sf_ar_forb_tags = QLineEdit()
        self._sf_ar_forb_tags.setPlaceholderText("tag1, tag2")
        tq_form.addRow("Required Tags:", self._sf_ar_req_tags)
        tq_form.addRow("Forbidden Tags:", self._sf_ar_forb_tags)
        self._sf_ar_match_label = QLabel("")
        self._sf_ar_match_label.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        tq_form.addRow("", self._sf_ar_match_label)
        self._ambient_stack.addWidget(tq_page)

        # Page 2: weighted_entity_list
        wel_page = QWidget()
        wel_lay = QVBoxLayout(wel_page)
        wel_info = QLabel("Weights must sum to 100.")
        wel_info.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        wel_lay.addWidget(wel_info)
        self._wel_table = QTableWidget(0, 2)
        self._wel_table.setHorizontalHeaderLabels(["Entity ID", "Weight"])
        self._wel_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._wel_table.setMaximumHeight(150)
        wel_lay.addWidget(self._wel_table)
        wel_btn_row = QHBoxLayout()
        self._wel_add_btn = QPushButton("+ Add Entity")
        self._wel_add_btn.clicked.connect(self._on_add_weighted_entity)
        self._wel_del_btn = QPushButton("− Remove")
        self._wel_del_btn.clicked.connect(self._on_remove_weighted_entity)
        self._wel_norm_btn = QPushButton("Normalize")
        self._wel_norm_btn.clicked.connect(self._on_normalize_weights)
        self._wel_validate_label = QLabel("")
        self._wel_validate_label.setStyleSheet("QLabel { font-weight: bold; }")
        wel_btn_row.addWidget(self._wel_add_btn)
        wel_btn_row.addWidget(self._wel_del_btn)
        wel_btn_row.addWidget(self._wel_norm_btn)
        wel_btn_row.addStretch()
        wel_lay.addLayout(wel_btn_row)
        wel_lay.addWidget(self._wel_validate_label)
        self._ambient_stack.addWidget(wel_page)

        # Page 3: weighted_entries
        we_page = QWidget()
        we_lay = QVBoxLayout(we_page)
        we_info = QLabel("Each entry is an entity or tag query. Weights must sum to 100.")
        we_info.setStyleSheet("QLabel { color: #666; font-size: 11px; }")
        we_lay.addWidget(we_info)
        self._we_table = QTableWidget(0, 5)
        self._we_table.setHorizontalHeaderLabels(["Type", "Entity ID", "Required Tags", "Forbidden Tags", "Weight"])
        self._we_table.horizontalHeader().setSectionResizeMode(QHeaderView.ResizeMode.Stretch)
        self._we_table.setMaximumHeight(150)
        we_lay.addWidget(self._we_table)
        we_btn_row = QHBoxLayout()
        self._we_add_btn = QPushButton("+ Add Entry")
        self._we_add_btn.clicked.connect(self._on_add_fill_entry)
        self._we_del_btn = QPushButton("− Remove")
        self._we_del_btn.clicked.connect(self._on_remove_fill_entry)
        self._we_validate_label = QLabel("")
        self._we_validate_label.setStyleSheet("QLabel { font-weight: bold; }")
        we_btn_row.addWidget(self._we_add_btn)
        we_btn_row.addWidget(self._we_del_btn)
        we_btn_row.addStretch()
        we_lay.addLayout(we_btn_row)
        we_lay.addWidget(self._we_validate_label)
        self._ambient_stack.addWidget(we_page)

        ambient_lay.addWidget(self._ambient_stack)

        # Ambient validation warnings
        self._ambient_warn_label = QLabel("")
        self._ambient_warn_label.setWordWrap(True)
        self._ambient_warn_label.setStyleSheet("QLabel { color: #cc6600; font-size: 11px; }")
        ambient_lay.addWidget(self._ambient_warn_label)

        sockets_lay.addWidget(ambient_group)

        form_layout.addWidget(sockets_group)
        form_layout.addStretch(1)
        scroll.setWidget(form_container)
        bottom_splitter.addWidget(scroll)
        bottom_splitter.setSizes([200, 500])

        main_splitter.addWidget(bottom_splitter)
        main_splitter.setSizes([400, 300])

        layout = QVBoxLayout(self)
        layout.addWidget(main_splitter)
        self._set_form_enabled(False)

    # ---- helpers ----

    def _set_form_enabled(self, enabled: bool) -> None:
        self._f_bg_browse.setEnabled(enabled)
        for w in [self._f_id, self._f_name, self._f_desc, self._f_bg,
                   self._f_width, self._f_height, self._f_tags,
                   self._f_layer_mode, self._f_layer_order, self._f_layer_overrides]:
            w.setEnabled(enabled)

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for room in self._catalog.rooms:
            self._list.addItem(f"{room.id} — {room.name}")
        self._list.blockSignals(False)
        if self._catalog.rooms:
            self._list.setCurrentRow(0)

    def _current_room(self) -> RoomCatalogEntry | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._catalog.rooms):
            return self._catalog.rooms[row]
        return None

    def _refresh_socket_list(self, room: RoomCatalogEntry) -> None:
        self._socket_list.blockSignals(True)
        self._socket_list.clear()
        for sock in room.sockets:
            self._socket_list.addItem(f"{sock.id} ({sock.name})")
        self._socket_list.blockSignals(False)
        if room.sockets:
            self._socket_list.setCurrentRow(0)

    def _current_socket(self) -> tuple[RoomCatalogEntry, int] | None:
        room = self._current_room()
        if room is None:
            return None
        row = self._socket_list.currentRow()
        if 0 <= row < len(room.sockets):
            return room, row
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
        new_id = self._f_id.text().strip()
        new_name = self._f_name.text().strip()
        text = f"{new_id} — {new_name}"
        self._list.item(row).setText(text)
        self._dirty = True
        # Notify listeners (e.g. locations tab) so catalog room dropdown stays in sync
        if self._catalog_changed_callback is not None:
            self._catalog_changed_callback()

    def _sync_form_to_catalog(self) -> None:
        if self._prev_row < 0 or self._prev_row >= len(self._catalog.rooms):
            return
        room = self._catalog.rooms[self._prev_row]
        room.id = self._f_id.text().strip()
        room.name = self._f_name.text().strip()
        room.description = self._f_desc.toPlainText().strip()
        room.background_image = self._f_bg.text().strip() or None
        room.design_size.w = self._f_width.value()
        room.design_size.h = self._f_height.value()
        room.tags = self._parse_csv(self._f_tags.text())
        room.layers = LayerConfig(
            mode=self._f_layer_mode.currentText(),
            overrides=self._parse_csv(self._f_layer_overrides.text()),
            order=self._parse_csv(self._f_layer_order.text()),
        )
        # Sync current socket
        self._sync_socket_form()

        self._list.item(self._prev_row).setText(f"{room.id} — {room.name}")
        self._dirty = True

    def _sync_socket_form(self) -> None:
        result = self._current_socket()
        if result is None:
            return
        room, idx = result
        sock = room.sockets[idx]
        sock.id = self._sf_id.text().strip()
        sock.name = self._sf_name.text().strip()
        sock.description = self._sf_desc.text().strip()
        sock.x = self._sf_x.value()
        sock.y = self._sf_y.value()
        sock.rotation = self._sf_rotation.value()
        sock.scale = self._sf_scale.value()
        sock.pivot_mode = PivotMode(self._sf_pivot_mode.currentText())
        sock.layer = self._sf_layer.currentText().strip()
        sock.sort_order = self._sf_sort.value()
        # Placement eligibility
        sock.required_tags = self._parse_csv(self._sf_req_tags.text())
        sock.forbidden_tags = self._parse_csv(self._sf_forb_tags.text())
        # Ambient fill
        sock.ambient_spawn_chance = self._sf_ambient_chance.value()
        mode = self._sf_ambient_mode.currentText()
        sock.ambient_rule.mode = mode
        # Mode-specific fields
        if mode == "tag_query":
            sock.ambient_rule.required_tags = self._parse_csv(self._sf_ar_req_tags.text())
            sock.ambient_rule.forbidden_tags = self._parse_csv(self._sf_ar_forb_tags.text())
        elif mode == "weighted_entity_list":
            self._sync_weighted_entity_table_to_model(sock)
        elif mode == "weighted_entries":
            self._sync_fill_entry_table_to_model(sock)
        self._socket_list.item(idx).setText(f"{sock.id} ({sock.name})")

    def _sync_weighted_entity_table_to_model(self, sock: SocketDefinition) -> None:
        """Read the weighted_entity_list table into the socket model."""
        entries: list[WeightedEntityEntry] = []
        for row in range(self._wel_table.rowCount()):
            eid_item = self._wel_table.item(row, 0)
            w_item = self._wel_table.item(row, 1)
            if eid_item and w_item:
                eid = eid_item.text().strip()
                try:
                    w = int(w_item.text().strip())
                except ValueError:
                    w = 0
                if eid:
                    entries.append(WeightedEntityEntry(entity_id=eid, weight=w))
        sock.ambient_rule.entries = entries

    def _sync_fill_entry_table_to_model(self, sock: SocketDefinition) -> None:
        """Read the weighted_entries table into the socket model."""
        entries: list[WeightedFillEntry] = []
        for row in range(self._we_table.rowCount()):
            type_item = self._we_table.item(row, 0)
            eid_item = self._we_table.item(row, 1)
            req_item = self._we_table.item(row, 2)
            forb_item = self._we_table.item(row, 3)
            w_item = self._we_table.item(row, 4)
            if type_item and w_item:
                entry_type = type_item.text().strip()
                eid = eid_item.text().strip() if eid_item else ""
                req = self._parse_csv(req_item.text()) if req_item else []
                forb = self._parse_csv(forb_item.text()) if forb_item else []
                try:
                    w = int(w_item.text().strip())
                except ValueError:
                    w = 0
                entries.append(WeightedFillEntry(
                    type=entry_type,  # type: ignore
                    entity_id=eid,
                    required_tags=req,
                    forbidden_tags=forb,
                    weight=w,
                ))
        sock.ambient_rule.fill_entries = entries

    def _clear_room_form(self) -> None:
        """Clear room form fields and reset to defaults."""
        self._loading = True
        try:
            self._f_id.setText("")
            self._f_name.setText("")
            self._f_desc.setPlainText("")
            self._f_bg.setText("")
            self._f_bg_thumb.setText("No image")
            self._f_bg_thumb.setPixmap(QPixmap())
            self._f_bg_warn.setText("")
            self._f_width.setValue(1920)
            self._f_height.setValue(1080)
            self._f_tags.setText("")
            self._f_layer_mode.setCurrentIndex(0)
            self._f_layer_order.setText("")
            self._f_layer_overrides.setText("")
            self._socket_list.clear()
            self._clear_socket_form()
        finally:
            self._loading = False

    def _clear_socket_form(self) -> None:
        """Clear socket form fields and reset to defaults."""
        self._loading = True
        try:
            self._sf_id.setText("")
            self._sf_name.setText("")
            self._sf_desc.setText("")
            self._sf_x.setValue(0)
            self._sf_y.setValue(0)
            self._sf_rotation.setValue(0.0)
            self._sf_scale.setValue(1.0)
            self._sf_pivot_mode.setCurrentIndex(0)
            self._sf_layer.setCurrentIndex(0)
            self._sf_sort.setValue(0)
            self._sf_req_tags.setText("")
            self._sf_forb_tags.setText("")
            self._sf_ambient_chance.setValue(0)
            self._sf_ambient_mode.setCurrentIndex(0)
            self._sf_ar_req_tags.setText("")
            self._sf_ar_forb_tags.setText("")
            self._wel_table.setRowCount(0)
            self._we_table.setRowCount(0)
            self._wel_validate_label.setText("")
            self._we_validate_label.setText("")
            self._ambient_warn_label.setText("")
        finally:
            self._loading = False

    def _load_room_to_form(self, room: RoomCatalogEntry) -> None:
        self._loading = True
        try:
            self._f_id.setText(room.id)
            self._f_name.setText(room.name)
            self._f_desc.setPlainText(room.description)
            self._f_bg.setText(room.background_image or "")
            self._f_width.setValue(room.design_size.w)
            self._f_height.setValue(room.design_size.h)
            self._f_tags.setText(", ".join(room.tags))

            idx = self._f_layer_mode.findText(room.layers.mode)
            if idx >= 0:
                self._f_layer_mode.setCurrentIndex(idx)
            self._f_layer_order.setText(", ".join(room.layers.order))
            self._f_layer_overrides.setText(", ".join(room.layers.overrides))

            self._refresh_socket_list(room)
            self._refresh_canvas(room)
            self._refresh_bg_thumbnail()
        finally:
            self._loading = False

    def _refresh_canvas(self, room: RoomCatalogEntry) -> None:
        """Update the canvas background and socket handles for a room."""
        self._updating_canvas = True
        try:
            scene = self._canvas.room_scene
            scene.clear_sockets()

            # Resolve background image path relative to imageRoot
            bg_path = None
            if room.background_image:
                bg_path = self._project.image_root / room.background_image

            scene.set_background(bg_path, room.design_size.w, room.design_size.h)

            # Add socket handles
            for sock in room.sockets:
                handle = scene.add_socket(sock.id, float(sock.x), float(sock.y))
                handle.set_label_visible(self._show_labels_cb.isChecked())

            self._canvas.fit_to_view()
        finally:
            self._updating_canvas = False

    def _load_socket_to_form(self, sock: SocketDefinition) -> None:
        """Load socket data into the form fields."""
        self._loading = True
        try:
            # Identity
            self._sf_id.setText(sock.id)
            self._sf_name.setText(sock.name)
            self._sf_desc.setText(sock.description)
            # Transform
            self._sf_x.setValue(sock.x)
            self._sf_y.setValue(sock.y)
            self._sf_rotation.setValue(sock.rotation)
            self._sf_scale.setValue(sock.scale)
            idx = self._sf_pivot_mode.findText(sock.pivot_mode.value)
            if idx >= 0:
                self._sf_pivot_mode.setCurrentIndex(idx)
            layer_idx = self._sf_layer.findText(sock.layer)
            if layer_idx >= 0:
                self._sf_layer.setCurrentIndex(layer_idx)
            else:
                self._sf_layer.setCurrentText(sock.layer)
            self._sf_sort.setValue(sock.sort_order)
            # Placement eligibility
            self._sf_req_tags.setText(", ".join(sock.required_tags))
            self._sf_forb_tags.setText(", ".join(sock.forbidden_tags))
            # Ambient fill
            self._sf_ambient_chance.setValue(sock.ambient_spawn_chance)
            mode = sock.ambient_rule.mode
            mode_idx = self._sf_ambient_mode.findText(mode)
            if mode_idx >= 0:
                self._sf_ambient_mode.setCurrentIndex(mode_idx)
            # Mode-specific
            self._sf_ar_req_tags.setText(", ".join(sock.ambient_rule.required_tags))
            self._sf_ar_forb_tags.setText(", ".join(sock.ambient_rule.forbidden_tags))
            # Weighted entity list
            self._wel_table.setRowCount(len(sock.ambient_rule.entries))
            for i, entry in enumerate(sock.ambient_rule.entries):
                self._wel_table.setItem(i, 0, QTableWidgetItem(entry.entity_id))
                self._wel_table.setItem(i, 1, QTableWidgetItem(str(entry.weight)))
            # Weighted entries
            self._we_table.setRowCount(len(sock.ambient_rule.fill_entries))
            for i, fe in enumerate(sock.ambient_rule.fill_entries):
                self._we_table.setItem(i, 0, QTableWidgetItem(fe.type))
                self._we_table.setItem(i, 1, QTableWidgetItem(fe.entity_id))
                self._we_table.setItem(i, 2, QTableWidgetItem(", ".join(fe.required_tags)))
                self._we_table.setItem(i, 3, QTableWidgetItem(", ".join(fe.forbidden_tags)))
                self._we_table.setItem(i, 4, QTableWidgetItem(str(fe.weight)))
            # Update validation labels
            self._update_ambient_validation(sock)
        finally:
            self._loading = False

    def _update_ambient_validation(self, sock: SocketDefinition) -> None:
        """Update validation labels for the ambient fill section."""
        warnings: list[str] = []
        chance = sock.ambient_spawn_chance
        rule = sock.ambient_rule
        mode = rule.mode

        # Weighted entity list total
        if mode == "weighted_entity_list" and rule.entries:
            total = sum(e.weight for e in rule.entries)
            if total == 100:
                self._wel_validate_label.setText(f"✓ Total: {total}/100")
                self._wel_validate_label.setStyleSheet("QLabel { color: #009900; font-weight: bold; }")
            else:
                self._wel_validate_label.setText(f"✗ Total: {total}/100 (must be 100)")
                self._wel_validate_label.setStyleSheet("QLabel { color: #cc0000; font-weight: bold; }")
        else:
            self._wel_validate_label.setText("")

        # Weighted entries total
        if mode == "weighted_entries" and rule.fill_entries:
            total = sum(e.weight for e in rule.fill_entries)
            if total == 100:
                self._we_validate_label.setText(f"✓ Total: {total}/100")
                self._we_validate_label.setStyleSheet("QLabel { color: #009900; font-weight: bold; }")
            else:
                self._we_validate_label.setText(f"✗ Total: {total}/100 (must be 100)")
                self._we_validate_label.setStyleSheet("QLabel { color: #cc0000; font-weight: bold; }")
        else:
            self._we_validate_label.setText("")

        # Tag query match count
        if mode == "tag_query":
            req = self._parse_csv(self._sf_ar_req_tags.text())
            forb = self._parse_csv(self._sf_ar_forb_tags.text())
            n = self._count_matching_entities(req, forb)
            self._sf_ar_match_label.setText(f"Matching entities: {n}")
        else:
            self._sf_ar_match_label.setText("")

        # Warnings
        if chance > 0 and mode == "none":
            warnings.append("Ambient Spawn Chance > 0 but mode is 'none'. No ambient entities will spawn.")
        if chance == 0 and (mode != "none" or rule.entries or rule.fill_entries):
            warnings.append(
                "Ambient rule is configured but random ambient fill is disabled (0%). "
                "Explicit placement may still use this socket."
            )
        if mode == "tag_query" and not rule.required_tags and not rule.forbidden_tags:
            warnings.append("Tag query mode with no tags specified will match all entities.")
        if mode == "weighted_entity_list" and not rule.entries:
            warnings.append("Weighted entity list is empty.")
        if mode == "weighted_entries" and not rule.fill_entries:
            warnings.append("Weighted entries list is empty.")

        if warnings:
            self._ambient_warn_label.setText("\n".join(f"⚠ {w}" for w in warnings))
        else:
            self._ambient_warn_label.setText("")

    def _write_preview_snapshot(self) -> None:
        """Write the current room as a preview snapshot and notify callback."""
        room = self._current_room()
        if room is None:
            return
        snapshot = build_room_catalog_snapshot(self._project, room)
        snapshot_path = self._project.absolute_preview_snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_preview_snapshot(snapshot_path, snapshot)
        if self._preview_callback is not None:
            self._preview_callback(room)

    def _refresh_bg_thumbnail(self) -> None:
        """Update the background thumbnail and warning label from the current bg field."""
        bg_text = self._f_bg.text().strip()
        if not bg_text:
            self._f_bg_thumb.setText("No image")
            self._f_bg_thumb.setPixmap(QPixmap())
            self._f_bg_warn.setText("")
            return
        full_path = self._project.image_root / bg_text
        pix = QPixmap(str(full_path))
        if pix.isNull():
            self._f_bg_thumb.setText("Missing")
            self._f_bg_thumb.setPixmap(QPixmap())
            self._f_bg_warn.setText(f"Image not found: {bg_text}")
        else:
            scaled = pix.scaled(160, 90, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            self._f_bg_thumb.setPixmap(scaled)
            self._f_bg_thumb.setText("")
            self._f_bg_warn.setText("")

    def _count_matching_entities(self, required: list[str], forbidden: list[str]) -> int:
        return _count_matching_entities(self._entities, required, forbidden)

    # ---- slots ----

    def _on_selection_changed(self, row: int) -> None:
        self._sync_form_to_catalog()
        self._prev_row = row
        if 0 <= row < len(self._catalog.rooms):
            self._load_room_to_form(self._catalog.rooms[row])
            self._set_form_enabled(True)
        else:
            self._set_form_enabled(False)

    def _on_socket_selection_changed(self, row: int) -> None:
        self._sync_socket_form()
        room = self._current_room()
        if room and 0 <= row < len(room.sockets):
            self._load_socket_to_form(room.sockets[row])

    def _on_add(self) -> None:
        existing = {r.id for r in self._catalog.rooms}
        new_id = generate_padded_id("new_room", existing, fallback="room")
        new_name = f"New Room {len(self._catalog.rooms) + 1}"
        room = RoomCatalogEntry(id=new_id, name=new_name)
        self._catalog.rooms.append(room)
        self._list.addItem(f"{room.id} — {room.name}")
        self._list.setCurrentRow(len(self._catalog.rooms) - 1)
        self._dirty = True
        if self._catalog_changed_callback is not None:
            self._catalog_changed_callback()

    def _on_delete(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        del self._catalog.rooms[row]
        self._prev_row = -1
        self._refresh_list()
        if not self._catalog.rooms:
            self._clear_room_form()
            self._set_form_enabled(False)
            self._canvas.room_scene.clear_sockets()
            self._canvas.room_scene.set_background(None, 1920, 1080)
        self._dirty = True
        if self._catalog_changed_callback is not None:
            self._catalog_changed_callback()

    def _on_add_socket(self) -> None:
        room = self._current_room()
        if room is None:
            return
        # Sync current socket before adding a new one
        self._sync_socket_form()

        existing = {s.id for s in room.sockets}
        new_id = generate_padded_id("new_socket", existing, fallback="socket")
        new_name = f"Socket {len(room.sockets) + 1}"
        sock = SocketDefinition(id=new_id, name=new_name)
        room.sockets.append(sock)

        # Block signals so _on_socket_selection_changed doesn't overwrite
        # the new socket's ID/name with stale form data
        self._socket_list.blockSignals(True)
        self._socket_list.addItem(f"{sock.id} ({sock.name})")
        self._socket_list.setCurrentRow(len(room.sockets) - 1)
        self._socket_list.blockSignals(False)

        # Manually load the new socket into the form
        self._load_socket_to_form(sock)

        # Add handle to canvas
        scene = self._canvas.room_scene
        handle = scene.add_socket(sock.id, float(sock.x), float(sock.y))
        handle.set_label_visible(self._show_labels_cb.isChecked())
        self._dirty = True

    def _on_delete_socket(self) -> None:
        result = self._current_socket()
        if result is None:
            return
        room, idx = result
        sock_id = room.sockets[idx].id
        del room.sockets[idx]
        # Remove handle from canvas
        scene = self._canvas.room_scene
        handle = scene.find_handle(sock_id)
        if handle:
            scene.removeItem(handle)
            scene.socket_handles  # access to refresh
        self._refresh_socket_list(room)
        if not room.sockets:
            self._clear_socket_form()
        self._dirty = True

    def _on_socket_moved(self, socket_id: str, new_x: float, new_y: float) -> None:
        """Handle socket drag on canvas → update model + form."""
        if self._updating_canvas:
            return
        room = self._current_room()
        if room is None:
            return
        for sock in room.sockets:
            if sock.id == socket_id:
                sock.x = int(round(new_x))
                sock.y = int(round(new_y))
                # Update form if this socket is selected
                result = self._current_socket()
                if result and result[1] < len(room.sockets) and room.sockets[result[1]].id == socket_id:
                    self._sf_x.blockSignals(True)
                    self._sf_y.blockSignals(True)
                    self._sf_x.setValue(sock.x)
                    self._sf_y.setValue(sock.y)
                    self._sf_x.blockSignals(False)
                    self._sf_y.blockSignals(False)
                break
        self._dirty = True
        # Write preview snapshot
        self._write_preview_snapshot()

    def _on_toggle_labels(self, checked: bool) -> None:
        scene = self._canvas.room_scene
        for handle in scene.socket_handles:
            handle.set_label_visible(checked)

    def _on_bg_text_changed(self) -> None:
        """Live-reload the canvas background when the background path field changes."""
        if self._loading:
            return
        room = self._current_room()
        if room is None:
            return
        scene = self._canvas.room_scene
        bg_path = None
        bg_text = self._f_bg.text().strip()
        if bg_text:
            bg_path = self._project.image_root / bg_text
        scene.set_background(bg_path, self._f_width.value(), self._f_height.value())
        self._canvas.fit_to_view()
        self._refresh_bg_thumbnail()
        self._dirty = True

    def _on_browse_bg(self) -> None:
        """Open file dialog to pick a background image, store as relative path."""
        start_dir = str(self._project.image_root) if self._project.image_root.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Background Image", start_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        # Try to store as relative to image_root
        try:
            rel = Path(path).relative_to(self._project.image_root)
            self._f_bg.setText(str(rel).replace("\\", "/"))
        except ValueError:
            self._f_bg.setText(path.replace("\\", "/"))
        self._refresh_bg_thumbnail()
        self._dirty = True

    # ---- ambient fill slots ----

    def _on_ambient_mode_changed(self, _index: int) -> None:
        """Switch the ambient rule stacked widget to the selected mode page."""
        if self._loading:
            return
        mode = self._sf_ambient_mode.currentText()
        page_map = {"none": 0, "tag_query": 1, "weighted_entity_list": 2, "weighted_entries": 3}
        self._ambient_stack.setCurrentIndex(page_map.get(mode, 0))
        self._dirty = True

    def _on_add_weighted_entity(self) -> None:
        """Add a blank row to the weighted entity list table."""
        row = self._wel_table.rowCount()
        self._wel_table.insertRow(row)
        self._wel_table.setItem(row, 0, QTableWidgetItem(""))
        self._wel_table.setItem(row, 1, QTableWidgetItem("1"))
        self._dirty = True

    def _on_remove_weighted_entity(self) -> None:
        """Remove the selected row from the weighted entity list table."""
        row = self._wel_table.currentRow()
        if row >= 0:
            self._wel_table.removeRow(row)
            self._dirty = True

    def _on_normalize_weights(self) -> None:
        """Normalize weights in the weighted entity list table to sum to 100."""
        rows = self._wel_table.rowCount()
        if rows == 0:
            return
        weights: list[int] = []
        for r in range(rows):
            w_item = self._wel_table.item(r, 1)
            try:
                w = int(w_item.text().strip()) if w_item else 1
            except ValueError:
                w = 1
            weights.append(max(w, 1))
        total = sum(weights)
        if total == 0:
            return
        for r, w in enumerate(weights):
            normalized = max(1, round(w * 100 / total))
            self._wel_table.item(r, 1).setText(str(normalized))
        self._dirty = True

    def _on_add_fill_entry(self) -> None:
        """Add a blank row to the weighted entries table."""
        row = self._we_table.rowCount()
        self._we_table.insertRow(row)
        self._we_table.setItem(row, 0, QTableWidgetItem("entity"))
        self._we_table.setItem(row, 1, QTableWidgetItem(""))
        self._we_table.setItem(row, 2, QTableWidgetItem(""))
        self._we_table.setItem(row, 3, QTableWidgetItem(""))
        self._we_table.setItem(row, 4, QTableWidgetItem("1"))
        self._dirty = True

    def _on_remove_fill_entry(self) -> None:
        """Remove the selected row from the weighted entries table."""
        row = self._we_table.currentRow()
        if row >= 0:
            self._we_table.removeRow(row)
            self._dirty = True


def _count_matching_entities(entities: list[EntityDefinition], required: list[str], forbidden: list[str]) -> int:
    """Count spawnable entities matching the tag query (hierarchical prefix matching)."""
    count = 0
    for ent in entities:
        tags = set(ent.tags)
        if "entity.spawnable" not in tags:
            continue
        if required and not matches_all(tags, required):
            continue
        if forbidden and not matches_none(tags, forbidden):
            continue
        count += 1
    return count
