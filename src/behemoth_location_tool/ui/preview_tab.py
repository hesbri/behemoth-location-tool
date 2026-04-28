from __future__ import annotations

from PySide6.QtCore import Qt, QObject, Signal, Slot
from PySide6.QtGui import QTextCursor
from PySide6.QtWidgets import (
    QCheckBox, QFormLayout, QGroupBox, QHBoxLayout, QLabel, QTextEdit, QPushButton, QVBoxLayout, QWidget,
)

from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.preview.controller import ConnectionState, PreviewController


class _SignalBridge(QObject):
    """Bridges plain Python callbacks to Qt signals for thread-safe UI updates."""
    connection_changed = Signal(str)
    log_message = Signal(str, str)
    diagnostic_message = Signal(str, str)


class PreviewTab(QWidget):
    """Preview tab: start/stop server, display protocol log, debug overlay controls."""

    def __init__(self, project: ProjectConfig, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._controller = PreviewController(project)
        self._bridge = _SignalBridge(self)

        # Wire controller callbacks → bridge signals
        self._controller.on_connection_changed = self._bridge.connection_changed.emit
        self._controller.on_log_message = self._bridge.log_message.emit
        self._controller.on_diagnostic = self._bridge.diagnostic_message.emit

        # Wire bridge signals → UI slots (queued for thread safety)
        self._bridge.connection_changed.connect(self._on_connection_changed, Qt.ConnectionType.QueuedConnection)
        self._bridge.log_message.connect(self._on_log_message, Qt.ConnectionType.QueuedConnection)
        self._bridge.diagnostic_message.connect(self._on_diagnostic_message, Qt.ConnectionType.QueuedConnection)

        self._build_ui()

    @property
    def controller(self) -> PreviewController:
        return self._controller

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # --- Connection controls ---
        conn_group = QGroupBox("Preview Server")
        conn_layout = QHBoxLayout(conn_group)

        self._start_btn = QPushButton("▶ Start Preview")
        self._start_btn.clicked.connect(self._on_start_clicked)
        conn_layout.addWidget(self._start_btn)

        self._stop_btn = QPushButton("■ Stop")
        self._stop_btn.setEnabled(False)
        self._stop_btn.clicked.connect(self._on_stop_clicked)
        conn_layout.addWidget(self._stop_btn)

        self._launch_btn = QPushButton("🚀 Launch Game")
        self._launch_btn.setEnabled(False)
        self._launch_btn.clicked.connect(self._on_launch_clicked)
        conn_layout.addWidget(self._launch_btn)

        self._refresh_btn = QPushButton("⟳ Refresh Snapshot")
        self._refresh_btn.setEnabled(False)
        self._refresh_btn.clicked.connect(self._on_refresh_clicked)
        conn_layout.addWidget(self._refresh_btn)

        self._status_label = QLabel("● Disconnected")
        self._status_label.setStyleSheet("font-weight: bold; padding: 4px;")
        conn_layout.addWidget(self._status_label)
        conn_layout.addStretch(1)

        root.addWidget(conn_group)

        # --- Debug overlay ---
        debug_group = QGroupBox("Debug Overlay")
        debug_layout = QHBoxLayout(debug_group)
        self._cb_sockets = QCheckBox("Sockets")
        self._cb_sockets.setChecked(True)
        self._cb_socket_names = QCheckBox("Socket Names")
        self._cb_socket_names.setChecked(True)
        self._cb_clickable = QCheckBox("Clickable Rects")
        self._cb_clickable.setChecked(True)
        self._cb_safe_area = QCheckBox("Safe Area")
        self._cb_layer_names = QCheckBox("Layer Names")
        self._cb_instance_ids = QCheckBox("Placed Instance IDs")
        self._apply_overlay_btn = QPushButton("Apply Overlay")
        self._apply_overlay_btn.setEnabled(False)
        self._apply_overlay_btn.clicked.connect(self._on_apply_overlay)
        debug_layout.addWidget(self._cb_sockets)
        debug_layout.addWidget(self._cb_socket_names)
        debug_layout.addWidget(self._cb_clickable)
        debug_layout.addWidget(self._cb_safe_area)
        debug_layout.addWidget(self._cb_layer_names)
        debug_layout.addWidget(self._cb_instance_ids)
        debug_layout.addWidget(self._apply_overlay_btn)
        debug_layout.addStretch(1)
        root.addWidget(debug_group)

        # --- Info panel ---
        info_group = QGroupBox("Preview Info")
        info_form = QFormLayout(info_group)

        self._info_snapshot = QLabel(str(self._controller.project.absolute_preview_snapshot_path))
        self._info_snapshot.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._info_snapshot.setWordWrap(True)
        info_form.addRow("Snapshot:", self._info_snapshot)

        exe = self._controller.project.game_executable
        port = self._controller.project.preview_port
        cmd = (
            f"{exe} --editor-preview "
            f"--editor-host 127.0.0.1 --editor-port {port} "
            f"--project-root {self._controller.project.game_root}"
        )
        self._info_command = QLabel(cmd)
        self._info_command.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        self._info_command.setWordWrap(True)
        info_form.addRow("Command:", self._info_command)

        self._info_active_location = QLabel("(none)")
        info_form.addRow("Active Location:", self._info_active_location)

        root.addWidget(info_group)

        # --- Diagnostics log ---
        diag_group = QGroupBox("Diagnostics")
        diag_layout = QVBoxLayout(diag_group)
        self._diagnostics_log = QTextEdit()
        self._diagnostics_log.setReadOnly(True)
        self._diagnostics_log.setMaximumHeight(120)
        diag_layout.addWidget(self._diagnostics_log)
        root.addWidget(diag_group)

        # --- Protocol log ---
        log_group = QGroupBox("Protocol Log")
        log_layout = QVBoxLayout(log_group)
        self._protocol_log = QTextEdit()
        self._protocol_log.setReadOnly(True)
        log_layout.addWidget(self._protocol_log)
        root.addWidget(log_group)

        root.addStretch(1)

    # ---- public API ----

    def set_active_location(self, location_id: str) -> None:
        self._info_active_location.setText(location_id or "(none)")

    # ---- Button handlers ----

    def _on_start_clicked(self) -> None:
        self._controller.start()
        self._start_btn.setEnabled(False)
        self._stop_btn.setEnabled(True)
        self._launch_btn.setEnabled(True)
        self._refresh_btn.setEnabled(True)
        self._apply_overlay_btn.setEnabled(True)

    def _on_stop_clicked(self) -> None:
        self._controller.stop()
        self._start_btn.setEnabled(True)
        self._stop_btn.setEnabled(False)
        self._launch_btn.setEnabled(False)
        self._refresh_btn.setEnabled(False)
        self._apply_overlay_btn.setEnabled(False)

    def _on_launch_clicked(self) -> None:
        self._controller.launch_game()

    def _on_refresh_clicked(self) -> None:
        self._controller.refresh_snapshot()

    def _on_apply_overlay(self) -> None:
        self._controller.send_debug_overlay(
            show_sockets=self._cb_sockets.isChecked(),
            show_socket_names=self._cb_socket_names.isChecked(),
            show_clickable_rects=self._cb_clickable.isChecked(),
            show_safe_area=self._cb_safe_area.isChecked(),
            show_layer_names=self._cb_layer_names.isChecked(),
            show_placed_instance_ids=self._cb_instance_ids.isChecked(),
        )

    # ---- Signal handlers (queued from background threads) ----

    @Slot(str)
    def _on_connection_changed(self, state: str) -> None:
        if state == ConnectionState.CONNECTED:
            self._status_label.setText("● Connected")
            self._status_label.setStyleSheet("font-weight: bold; color: green; padding: 4px;")
        elif state == ConnectionState.WAITING:
            self._status_label.setText("● Waiting for connection...")
            self._status_label.setStyleSheet("font-weight: bold; color: orange; padding: 4px;")
        else:
            self._status_label.setText("● Disconnected")
            self._status_label.setStyleSheet("font-weight: bold; color: red; padding: 4px;")

    @Slot(str, str)
    def _on_log_message(self, direction: str, json_line: str) -> None:
        color = "#2196F3" if direction == "TX" else "#4CAF50"
        self._protocol_log.append(f'<span style="color:{color}">[{direction}]</span> {json_line}')
        self._protocol_log.moveCursor(QTextCursor.MoveOperation.End)

    @Slot(str, str)
    def _on_diagnostic_message(self, level: str, message: str) -> None:
        color = {"info": "#333", "warn": "#FF9800", "error": "#F44336"}.get(level, "#333")
        self._diagnostics_log.append(f'<span style="color:{color}">[{level.upper()}]</span> {message}')
        self._diagnostics_log.moveCursor(QTextCursor.MoveOperation.End)
