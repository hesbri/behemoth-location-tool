"""Project configuration tab — displays and edits project settings."""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFileDialog,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.io.project import save_project
from behemoth_location_tool.model.project import ProjectConfig


class ProjectTab(QWidget):
    """Tab for editing project configuration and viewing resolved paths."""

    def __init__(self, project: ProjectConfig, *, project_path: Path | None = None) -> None:
        super().__init__()
        self.project = project
        self._project_path = project_path
        self._dirty = False
        self._build_ui()
        self._refresh_resolved()

    # ------------------------------------------------------------------ UI

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ---- Editable fields ----
        fields_group = QGroupBox("Project Settings")
        form = QFormLayout(fields_group)

        self._name_edit = QLineEdit(self.project.project_name)
        self._name_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Project Name:", self._name_edit)

        self._game_root_edit = QLineEdit(str(self.project.game_root))
        self._game_root_edit.textChanged.connect(self._on_game_root_changed)
        row = QHBoxLayout()
        row.addWidget(self._game_root_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_game_root)
        row.addWidget(browse)
        form.addRow("Game Root:", row)

        self._game_exe_edit = QLineEdit(str(self.project.game_executable))
        self._game_exe_edit.textChanged.connect(self._mark_dirty)
        row = QHBoxLayout()
        row.addWidget(self._game_exe_edit)
        browse = QPushButton("Browse…")
        browse.clicked.connect(self._browse_game_exe)
        row.addWidget(browse)
        form.addRow("Game Executable:", row)

        self._content_root_edit = QLineEdit(str(self.project.content_root))
        self._content_root_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Content Root:", self._content_root_edit)

        self._image_root_edit = QLineEdit(str(self.project.image_root))
        self._image_root_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Image Root:", self._image_root_edit)

        self._game_data_root_edit = QLineEdit(str(self.project.game_data_root))
        self._game_data_root_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Game Data Root:", self._game_data_root_edit)

        self._tool_data_root_edit = QLineEdit(str(self.project.tool_data_root))
        self._tool_data_root_edit.textChanged.connect(self._mark_dirty)
        form.addRow("Tool Data Root:", self._tool_data_root_edit)

        self._width_spin = QSpinBox()
        self._width_spin.setRange(640, 7680)
        self._width_spin.setValue(self.project.design_width)
        self._width_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Design Width:", self._width_spin)

        self._height_spin = QSpinBox()
        self._height_spin.setRange(480, 4320)
        self._height_spin.setValue(self.project.design_height)
        self._height_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Design Height:", self._height_spin)

        self._port_spin = QSpinBox()
        self._port_spin.setRange(1024, 65535)
        self._port_spin.setValue(self.project.preview_port)
        self._port_spin.valueChanged.connect(self._mark_dirty)
        form.addRow("Preview Port:", self._port_spin)

        root.addWidget(fields_group)

        # ---- Resolved paths (read-only) ----
        resolved_group = QGroupBox("Resolved Paths")
        rform = QFormLayout(resolved_group)

        self._resolved_game_root = QLabel()
        self._resolved_game_root.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rform.addRow("Game Root:", self._resolved_game_root)

        self._resolved_game_exe = QLabel()
        self._resolved_game_exe.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rform.addRow("Game Executable:", self._resolved_game_exe)

        self._resolved_content_root = QLabel()
        self._resolved_content_root.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rform.addRow("Content Root:", self._resolved_content_root)

        self._resolved_image_root = QLabel()
        self._resolved_image_root.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rform.addRow("Image Root:", self._resolved_image_root)

        self._resolved_game_data_root = QLabel()
        self._resolved_game_data_root.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rform.addRow("Game Data Root:", self._resolved_game_data_root)

        self._resolved_preview_snapshot = QLabel()
        self._resolved_preview_snapshot.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        rform.addRow("Preview Snapshot:", self._resolved_preview_snapshot)

        root.addWidget(resolved_group)

        # ---- Validation status ----
        self._validation_label = QLabel()
        root.addWidget(self._validation_label)

        # ---- Action buttons ----
        btn_row = QHBoxLayout()
        self._save_btn = QPushButton("Save Project Config")
        self._save_btn.clicked.connect(self._save)
        self._save_btn.setEnabled(False)
        btn_row.addWidget(self._save_btn)

        open_game_data = QPushButton("Open Game Data Folder")
        open_game_data.clicked.connect(self._open_game_data_folder)
        btn_row.addWidget(open_game_data)

        open_tool_data = QPushButton("Open Tool Data Folder")
        open_tool_data.clicked.connect(self._open_tool_data_folder)
        btn_row.addWidget(open_tool_data)

        btn_row.addStretch(1)
        root.addLayout(btn_row)

        root.addStretch(1)

    # ------------------------------------------------------------------ helpers

    def _mark_dirty(self, *_args: object) -> None:
        self._dirty = True
        self._save_btn.setEnabled(True)
        self._refresh_resolved()
        self._validate_live()

    def _on_game_root_changed(self, text: str) -> None:
        self._mark_dirty()

    def _apply_fields_to_project(self) -> None:
        """Push UI field values back into the ProjectConfig model."""
        self.project.project_name = self._name_edit.text()
        self.project.game_root = Path(self._game_root_edit.text())
        self.project.game_executable = Path(self._game_exe_edit.text())
        self.project.content_root = Path(self._content_root_edit.text())
        self.project.image_root = Path(self._image_root_edit.text())
        self.project.game_data_root = Path(self._game_data_root_edit.text())
        self.project.tool_data_root = Path(self._tool_data_root_edit.text())
        self.project.design_width = self._width_spin.value()
        self.project.design_height = self._height_spin.value()
        self.project.preview_port = self._port_spin.value()

    def _refresh_resolved(self) -> None:
        """Recompute resolved absolute paths from current field values."""
        # Temporarily apply to compute resolved paths
        old = (
            self.project.game_root, self.project.game_executable,
            self.project.content_root, self.project.image_root,
            self.project.game_data_root, self.project.tool_data_root,
        )
        self._apply_fields_to_project()

        # Re-resolve
        resolved_game_root = self.project.game_root
        if not resolved_game_root.is_absolute() and self._project_path is not None:
            resolved_game_root = (self._project_path.parent / resolved_game_root).resolve()
        else:
            resolved_game_root = resolved_game_root.resolve()

        def _resolve(child: Path) -> Path:
            if child.is_absolute():
                return child.resolve()
            return (resolved_game_root / child).resolve()

        self._resolved_game_root.setText(str(resolved_game_root))
        self._resolved_game_exe.setText(str(_resolve(self.project.game_executable)))
        self._resolved_content_root.setText(str(_resolve(self.project.content_root)))
        self._resolved_image_root.setText(str(_resolve(self.project.image_root)))
        self._resolved_game_data_root.setText(str(_resolve(self.project.game_data_root)))
        self._resolved_preview_snapshot.setText(str(self.project.absolute_preview_snapshot_path))

        # Restore original project values so we don't mutate prematurely
        (
            self.project.game_root, self.project.game_executable,
            self.project.content_root, self.project.image_root,
            self.project.game_data_root, self.project.tool_data_root,
        ) = old

    def _validate_live(self) -> None:
        """Quick validation of critical paths and show status."""
        self._apply_fields_to_project()
        errors: list[str] = []
        warnings: list[str] = []

        resolved = self.project.game_root.resolve()
        if not self.project.game_root.is_absolute() and self._project_path:
            resolved = (self._project_path.parent / self.project.game_root).resolve()

        if not self.project.game_root or str(self.project.game_root) == ".":
            errors.append("Game Root is not set")

        exe = self.project.game_executable
        if not exe or str(exe) == ".":
            errors.append("Game Executable is not set")

        content_root = resolved / self.project.content_root if not self.project.content_root.is_absolute() else self.project.content_root.resolve()
        settings = content_root / "config" / "settings.json"
        if not settings.parent.exists():
            errors.append(f"contentRoot/config/settings.json not found ({settings})")

        game_data = resolved / self.project.game_data_root if not self.project.game_data_root.is_absolute() else self.project.game_data_root.resolve()
        if not game_data.exists():
            warnings.append(f"gameDataRoot does not exist ({game_data})")

        parts: list[str] = []
        for e in errors:
            parts.append(f"❌ {e}")
        for w in warnings:
            parts.append(f"⚠ {w}")
        if not parts:
            parts.append("✓ All checks passed")

        self._validation_label.setText("\n".join(parts))

    # ------------------------------------------------------------------ actions

    def _browse_game_root(self) -> None:
        path = QFileDialog.getExistingDirectory(self, "Select Game Root Directory")
        if path:
            self._game_root_edit.setText(path)

    def _browse_game_exe(self) -> None:
        path, _ = QFileDialog.getOpenFileName(
            self, "Select Game Executable", "",
            "Executables (*.exe);;All Files (*)",
        )
        if path:
            self._game_exe_edit.setText(path)

    def _open_game_data_folder(self) -> None:
        self._apply_fields_to_project()
        path = self.project.game_root / self.project.game_data_root if not self.project.game_data_root.is_absolute() else self.project.game_data_root
        path = path.resolve()
        if path.exists():
            self._open_folder(path)
        else:
            QMessageBox.warning(self, "Not Found", f"Game data folder does not exist:\n{path}")

    def _open_tool_data_folder(self) -> None:
        self._apply_fields_to_project()
        path = self.project.absolute_tool_root
        if path.exists():
            self._open_folder(path)
        else:
            QMessageBox.information(self, "Create Folder", f"Tool data folder does not exist yet:\n{path}\n\nIt will be created when needed.")

    @staticmethod
    def _open_folder(path: Path) -> None:
        if sys.platform == "win32":
            subprocess.Popen(["explorer", str(path)])
        elif sys.platform == "darwin":
            subprocess.Popen(["open", str(path)])
        else:
            subprocess.Popen(["xdg-open", str(path)])

    def _save(self) -> None:
        if self._project_path is None:
            path, _ = QFileDialog.getSaveFileName(
                self, "Save Project Config", "project.json",
                "JSON Files (*.json);;All Files (*)",
            )
            if not path:
                return
            self._project_path = Path(path)

        self._apply_fields_to_project()
        self._project_path.parent.mkdir(parents=True, exist_ok=True)
        save_project(self._project_path, self.project)
        self._dirty = False
        self._save_btn.setEnabled(False)

    # ------------------------------------------------------------------ public

    @property
    def is_dirty(self) -> bool:
        return self._dirty

    def refresh_from_project(self) -> None:
        """Reload all fields from the project config model."""
        self._name_edit.setText(self.project.project_name)
        self._game_root_edit.setText(str(self.project.game_root))
        self._game_exe_edit.setText(str(self.project.game_executable))
        self._content_root_edit.setText(str(self.project.content_root))
        self._image_root_edit.setText(str(self.project.image_root))
        self._game_data_root_edit.setText(str(self.project.game_data_root))
        self._tool_data_root_edit.setText(str(self.project.tool_data_root))
        self._width_spin.setValue(self.project.design_width)
        self._height_spin.setValue(self.project.design_height)
        self._port_spin.setValue(self.project.preview_port)
        self._dirty = False
        self._save_btn.setEnabled(False)
        self._refresh_resolved()