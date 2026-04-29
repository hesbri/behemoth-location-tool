from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtGui import QPixmap
from PySide6.QtWidgets import (
    QCheckBox,
    QComboBox,
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.io.entity_loader import load_entity_module, save_entity_module
from behemoth_location_tool.model.common import PivotMode, Rect, SavePolicy
from behemoth_location_tool.model.entity import (
    EntityDefinition,
    EntityModule,
    EntityRenderData,
    EntitySpawnRules,
)
from behemoth_location_tool.model.id_utils import generate_id
from behemoth_location_tool.model.project import ProjectConfig


class EntitiesTab(QWidget):
    """Entity catalog editor: list, create, edit core fields, tags, render, spawn rules."""

    def __init__(self, project: ProjectConfig | None = None, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._project = project
        self._module: EntityModule = EntityModule()
        self._file_path: Path | None = None
        self._dirty = False
        self._prev_row = -1
        self._loading = False
        self._build_ui()

    # ---- public API ----

    def load_file(self, path: Path) -> None:
        self._module = load_entity_module(path)
        self._file_path = path
        self._dirty = False
        self._refresh_list()

    def set_module(self, module: EntityModule, *, file_path: Path | None = None) -> None:
        """Set the active module directly (used by MainWindow multi-module load)."""
        self._module = module
        self._file_path = file_path
        self._dirty = False
        self._refresh_list()

    def save_file(self, path: Path | None = None) -> None:
        target = path or self._file_path
        if target is None:
            return
        self._sync_form_to_module()
        save_entity_module(target, self._module)
        self._file_path = target
        self._dirty = False

    @property
    def module(self) -> EntityModule:
        return self._module

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    # ---- UI construction ----

    def _build_ui(self) -> None:
        splitter = QSplitter(Qt.Orientation.Horizontal)
        # Left: entity list
        left = QWidget()
        left_layout = QVBoxLayout(left)
        self._list = QListWidget()
        self._list.currentRowChanged.connect(self._on_selection_changed)
        left_layout.addWidget(QLabel("Entities"))
        left_layout.addWidget(self._list)

        btn_row = QHBoxLayout()
        self._add_btn = QPushButton("+ Add")
        self._add_btn.clicked.connect(self._on_add)
        self._del_btn = QPushButton("− Delete")
        self._del_btn.clicked.connect(self._on_delete)
        btn_row.addWidget(self._add_btn)
        btn_row.addWidget(self._del_btn)
        left_layout.addLayout(btn_row)
        splitter.addWidget(left)

        # Right: scrollable form
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        form_container = QWidget()
        self._form_layout = QVBoxLayout(form_container)

        # -- Core fields --
        core_group = QGroupBox("Core")
        core_form = QFormLayout(core_group)
        self._f_id = QLineEdit()
        self._f_id.textChanged.connect(self._update_list_item_text)
        self._f_kind = QLineEdit()
        self._f_name = QLineEdit()
        self._f_name.textChanged.connect(self._update_list_item_text)
        self._f_desc = QTextEdit()
        self._f_desc.setMaximumHeight(60)
        core_form.addRow("ID:", self._f_id)
        core_form.addRow("Kind:", self._f_kind)
        core_form.addRow("Name:", self._f_name)
        core_form.addRow("Description:", self._f_desc)
        self._form_layout.addWidget(core_group)

        # -- Tags --
        tags_group = QGroupBox("Tags")
        tags_layout = QVBoxLayout(tags_group)
        self._f_tags = QLineEdit()
        self._f_tags.setPlaceholderText("tag1, tag2, ...")
        tags_layout.addWidget(self._f_tags)
        self._form_layout.addWidget(tags_group)

        # -- Render --
        render_group = QGroupBox("Render")
        render_form = QFormLayout(render_group)
        self._f_sprite = QLineEdit()
        self._f_sprite.setPlaceholderText("path/to/sprite.png (relative to Image Root)")
        self._f_sprite.textChanged.connect(self._on_sprite_text_changed)
        self._f_sprite_browse = QPushButton("…")
        self._f_sprite_browse.setFixedWidth(30)
        self._f_sprite_browse.clicked.connect(self._on_browse_sprite)
        sprite_row = QHBoxLayout()
        sprite_row.addWidget(self._f_sprite)
        sprite_row.addWidget(self._f_sprite_browse)
        self._f_sprite_thumb = QLabel("No image")
        self._f_sprite_thumb.setFixedSize(128, 128)
        self._f_sprite_thumb.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._f_sprite_thumb.setStyleSheet(
            "QLabel { border: 1px solid #888; background: #1a1a1a; color: #999; font-size: 11px; }"
        )
        self._f_sprite_warn = QLabel("")
        self._f_sprite_warn.setStyleSheet("QLabel { color: #cc6600; font-size: 11px; }")
        self._f_default_layer = QLineEdit()
        self._f_pivot_mode = QComboBox()
        self._f_pivot_mode.addItems([m.value for m in PivotMode])
        self._f_pivot_x = QSpinBox()
        self._f_pivot_x.setRange(-9999, 9999)
        self._f_pivot_y = QSpinBox()
        self._f_pivot_y.setRange(-9999, 9999)
        self._f_has_rect = QCheckBox("Has Clickable Rect")
        self._f_rect_x = QSpinBox()
        self._f_rect_x.setRange(-9999, 9999)
        self._f_rect_y = QSpinBox()
        self._f_rect_y.setRange(-9999, 9999)
        self._f_rect_w = QSpinBox()
        self._f_rect_w.setRange(0, 9999)
        self._f_rect_h = QSpinBox()
        self._f_rect_h.setRange(0, 9999)
        render_form.addRow("Sprite:", sprite_row)
        render_form.addRow("", self._f_sprite_thumb)
        render_form.addRow("", self._f_sprite_warn)
        render_form.addRow("Default Layer:", self._f_default_layer)
        render_form.addRow("Pivot Mode:", self._f_pivot_mode)
        render_form.addRow("Pivot X:", self._f_pivot_x)
        render_form.addRow("Pivot Y:", self._f_pivot_y)
        render_form.addRow(self._f_has_rect)
        render_form.addRow("Rect X:", self._f_rect_x)
        render_form.addRow("Rect Y:", self._f_rect_y)
        render_form.addRow("Rect W:", self._f_rect_w)
        render_form.addRow("Rect H:", self._f_rect_h)
        self._form_layout.addWidget(render_group)

        # -- Spawn Rules --
        spawn_group = QGroupBox("Spawn Rules")
        spawn_form = QFormLayout(spawn_group)
        self._f_required_tags = QLineEdit()
        self._f_required_tags.setPlaceholderText("tag1, tag2, ...")
        self._f_forbidden_tags = QLineEdit()
        self._f_forbidden_tags.setPlaceholderText("tag1, tag2, ...")
        self._f_exclusive_groups = QLineEdit()
        self._f_exclusive_groups.setPlaceholderText("group1, group2, ...")
        self._f_save_policy = QComboBox()
        self._f_save_policy.addItems([p.value for p in SavePolicy])
        spawn_form.addRow("Required Context Tags:", self._f_required_tags)
        spawn_form.addRow("Forbidden Context Tags:", self._f_forbidden_tags)
        spawn_form.addRow("Exclusive Groups:", self._f_exclusive_groups)
        spawn_form.addRow("Save Policy:", self._f_save_policy)
        self._form_layout.addWidget(spawn_group)

        self._form_layout.addStretch(1)
        scroll.setWidget(form_container)
        splitter.addWidget(scroll)
        splitter.setSizes([200, 500])

        layout = QVBoxLayout(self)
        layout.addWidget(splitter)
        self._set_form_enabled(False)

    # ---- helpers ----

    def _set_form_enabled(self, enabled: bool) -> None:
        for w in [self._f_id, self._f_kind, self._f_name, self._f_desc, self._f_tags,
                   self._f_sprite, self._f_sprite_browse, self._f_default_layer, self._f_pivot_mode,
                   self._f_pivot_x, self._f_pivot_y, self._f_has_rect,
                   self._f_rect_x, self._f_rect_y, self._f_rect_w, self._f_rect_h,
                   self._f_required_tags, self._f_forbidden_tags, self._f_exclusive_groups,
                   self._f_save_policy]:
            w.setEnabled(enabled)

    def _refresh_list(self) -> None:
        self._list.blockSignals(True)
        self._list.clear()
        for ent in self._module.entities:
            self._list.addItem(f"{ent.id} — {ent.name}")
        self._list.blockSignals(False)
        if self._module.entities:
            self._list.setCurrentRow(0)

    def _current_entity(self) -> EntityDefinition | None:
        row = self._list.currentRow()
        if 0 <= row < len(self._module.entities):
            return self._module.entities[row]
        return None

    def _update_list_item_text(self) -> None:
        """Live-update the selected list item text when ID or name fields change."""
        if self._loading:
            return
        row = self._list.currentRow()
        if row < 0:
            return
        text = f"{self._f_id.text().strip()} — {self._f_name.text().strip()}"
        self._list.item(row).setText(text)
        self._dirty = True

    def _sync_form_to_module(self) -> None:
        if self._prev_row < 0 or self._prev_row >= len(self._module.entities):
            return
        ent = self._module.entities[self._prev_row]
        ent.id = self._f_id.text().strip()
        ent.kind = self._f_kind.text().strip()
        ent.name = self._f_name.text().strip()
        ent.description = self._f_desc.toPlainText().strip()
        ent.tags = [t.strip() for t in self._f_tags.text().split(",") if t.strip()]

        # Render
        sprite = self._f_sprite.text().strip() or None
        default_layer = self._f_default_layer.text().strip() or None
        pivot_mode = PivotMode(self._f_pivot_mode.currentText())
        pivot_x = self._f_pivot_x.value()
        pivot_y = self._f_pivot_y.value()
        rect = None
        if self._f_has_rect.isChecked():
            rect = Rect(x=self._f_rect_x.value(), y=self._f_rect_y.value(),
                        w=self._f_rect_w.value(), h=self._f_rect_h.value())
        ent.render = EntityRenderData(
            sprite=sprite, default_layer=default_layer,
            pivot={"mode": pivot_mode, "x": pivot_x, "y": pivot_y},
            clickable_rect=rect,
        )

        # Spawn rules
        ent.spawn_rules = EntitySpawnRules(
            required_context_tags=[t.strip() for t in self._f_required_tags.text().split(",") if t.strip()],
            forbidden_context_tags=[t.strip() for t in self._f_forbidden_tags.text().split(",") if t.strip()],
            exclusive_groups=[g.strip() for g in self._f_exclusive_groups.text().split(",") if g.strip()],
            save_policy=SavePolicy(self._f_save_policy.currentText()),
        )

        # Update list text for the previous row
        self._list.item(self._prev_row).setText(f"{ent.id} — {ent.name}")
        self._dirty = True

    def _clear_form(self) -> None:
        """Clear all form fields and reset to defaults."""
        self._loading = True
        try:
            self._f_id.setText("")
            self._f_kind.setText("")
            self._f_name.setText("")
            self._f_desc.setPlainText("")
            self._f_tags.setText("")
            self._f_sprite.setText("")
            self._f_sprite_thumb.setText("No image")
            self._f_sprite_thumb.setPixmap(QPixmap())
            self._f_sprite_warn.setText("")
            self._f_default_layer.setText("")
            self._f_pivot_mode.setCurrentIndex(0)
            self._f_pivot_x.setValue(0)
            self._f_pivot_y.setValue(0)
            self._f_has_rect.setChecked(False)
            self._f_rect_x.setValue(0)
            self._f_rect_y.setValue(0)
            self._f_rect_w.setValue(0)
            self._f_rect_h.setValue(0)
            self._f_required_tags.setText("")
            self._f_forbidden_tags.setText("")
            self._f_exclusive_groups.setText("")
            self._f_save_policy.setCurrentIndex(0)
        finally:
            self._loading = False

    def _load_entity_to_form(self, ent: EntityDefinition) -> None:
        self._loading = True
        try:
            self._f_id.setText(ent.id)
            self._f_kind.setText(ent.kind)
            self._f_name.setText(ent.name)
            self._f_desc.setPlainText(ent.description)
            self._f_tags.setText(", ".join(ent.tags))

            if ent.render:
                self._f_sprite.setText(ent.render.sprite or "")
                self._refresh_sprite_thumbnail()
                self._f_default_layer.setText(ent.render.default_layer or "")
                idx = self._f_pivot_mode.findText(ent.render.pivot.mode.value)
                if idx >= 0:
                    self._f_pivot_mode.setCurrentIndex(idx)
                self._f_pivot_x.setValue(ent.render.pivot.x)
                self._f_pivot_y.setValue(ent.render.pivot.y)
                if ent.render.clickable_rect:
                    self._f_has_rect.setChecked(True)
                    self._f_rect_x.setValue(ent.render.clickable_rect.x)
                    self._f_rect_y.setValue(ent.render.clickable_rect.y)
                    self._f_rect_w.setValue(ent.render.clickable_rect.w)
                    self._f_rect_h.setValue(ent.render.clickable_rect.h)
                else:
                    self._f_has_rect.setChecked(False)
            else:
                self._f_sprite.clear()
                self._f_sprite_thumb.setText("No image")
                self._f_sprite_thumb.setPixmap(QPixmap())
                self._f_sprite_warn.setText("")
                self._f_default_layer.clear()
                self._f_has_rect.setChecked(False)

            sr = ent.spawn_rules
            self._f_required_tags.setText(", ".join(sr.required_context_tags))
            self._f_forbidden_tags.setText(", ".join(sr.forbidden_context_tags))
            self._f_exclusive_groups.setText(", ".join(sr.exclusive_groups))
            idx = self._f_save_policy.findText(sr.save_policy.value)
            if idx >= 0:
                self._f_save_policy.setCurrentIndex(idx)
        finally:
            self._loading = False

    def _refresh_sprite_thumbnail(self) -> None:
        """Update the sprite thumbnail and warning label from the current sprite field."""
        sprite_text = self._f_sprite.text().strip()
        if not sprite_text:
            self._f_sprite_thumb.setText("No image")
            self._f_sprite_thumb.setPixmap(QPixmap())
            self._f_sprite_warn.setText("")
            return
        if self._project is None:
            self._f_sprite_thumb.setText("No project")
            self._f_sprite_warn.setText("")
            return
        full_path = self._project.image_root / sprite_text
        pix = QPixmap(str(full_path))
        if pix.isNull():
            self._f_sprite_thumb.setText("Missing")
            self._f_sprite_thumb.setPixmap(QPixmap())
            self._f_sprite_warn.setText(f"Image not found: {sprite_text}")
        else:
            scaled = pix.scaled(128, 128, Qt.AspectRatioMode.KeepAspectRatio,
                                 Qt.TransformationMode.SmoothTransformation)
            self._f_sprite_thumb.setPixmap(scaled)
            self._f_sprite_thumb.setText("")
            self._f_sprite_warn.setText("")

    def _on_sprite_text_changed(self) -> None:
        if self._loading:
            return
        self._refresh_sprite_thumbnail()
        self._dirty = True

    def _on_browse_sprite(self) -> None:
        """Open file dialog to pick a sprite image, store as relative path."""
        if self._project is None:
            return
        start_dir = str(self._project.image_root) if self._project.image_root.exists() else ""
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Sprite Image", start_dir,
            "Images (*.png *.jpg *.jpeg *.bmp *.webp);;All Files (*)",
        )
        if not path:
            return
        try:
            rel = Path(path).relative_to(self._project.image_root)
            self._f_sprite.setText(str(rel).replace("\\", "/"))
        except ValueError:
            self._f_sprite.setText(path.replace("\\", "/"))
        self._refresh_sprite_thumbnail()
        self._dirty = True

    # ---- slots ----

    def _on_selection_changed(self, row: int) -> None:
        self._sync_form_to_module()
        self._prev_row = row
        if 0 <= row < len(self._module.entities):
            self._load_entity_to_form(self._module.entities[row])
            self._set_form_enabled(True)
        else:
            self._set_form_enabled(False)

    def _on_add(self) -> None:
        existing = {e.id for e in self._module.entities}
        new_id = generate_id("new_entity", existing, fallback="entity")
        new_name = f"New Entity {len(self._module.entities) + 1}"
        ent = EntityDefinition(id=new_id, kind="prop", name=new_name)
        self._module.entities.append(ent)
        self._list.addItem(f"{ent.id} — {ent.name}")
        self._list.setCurrentRow(len(self._module.entities) - 1)
        self._dirty = True

    def _on_delete(self) -> None:
        row = self._list.currentRow()
        if row < 0:
            return
        del self._module.entities[row]
        self._prev_row = -1
        self._refresh_list()
        if not self._module.entities:
            self._clear_form()
            self._set_form_enabled(False)
        self._dirty = True
