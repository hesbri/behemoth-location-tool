from __future__ import annotations
from PySide6.QtCore import Qt
from PySide6.QtWidgets import QLabel, QMainWindow, QMessageBox, QPushButton, QTabWidget, QToolBar, QVBoxLayout, QWidget
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.preview.snapshot import build_empty_preview_snapshot, write_preview_snapshot
from behemoth_location_tool.preview.server import PreviewServerController

class MainWindow(QMainWindow):
    def __init__(self, project: ProjectConfig) -> None:
        super().__init__()
        self.project = project
        self.preview_server = PreviewServerController("127.0.0.1", project.preview_port, self._handle_preview_message)
        self.setWindowTitle(f"Behemoth Location Tool - {project.project_name}")
        self._build_toolbar()
        self._build_tabs()

    def closeEvent(self, event) -> None:  # type: ignore[no-untyped-def]
        self.preview_server.stop()
        super().closeEvent(event)

    def _build_toolbar(self) -> None:
        toolbar = QToolBar("Main")
        toolbar.setMovable(False)
        self.addToolBar(Qt.ToolBarArea.TopToolBarArea, toolbar)
        start_preview = QPushButton("Start Preview Server")
        start_preview.clicked.connect(self._start_preview_server)
        toolbar.addWidget(start_preview)
        write_snapshot = QPushButton("Write Empty Snapshot")
        write_snapshot.clicked.connect(self._write_empty_snapshot)
        toolbar.addWidget(write_snapshot)

    def _build_tabs(self) -> None:
        tabs = QTabWidget()
        tabs.addTab(self._placeholder("Project settings and game-root selection."), "Project")
        tabs.addTab(self._placeholder("Reusable room templates, layers, sockets, backgrounds."), "Room Catalog")
        tabs.addTab(self._placeholder("Actual mansion location instances and placed entities."), "Locations")
        tabs.addTab(self._placeholder("Graph view from locations.json."), "Graph")
        tabs.addTab(self._placeholder("Shared entity catalog loaded from entities.json includes."), "Entities")
        tabs.addTab(self._placeholder("Preview-first deterministic generation, then Apply."), "Generate")
        tabs.addTab(self._placeholder("Schema, semantic, asset, and runtime diagnostics."), "Validate")
        tabs.addTab(self._placeholder("Preview protocol log and debug overlay controls."), "Preview")
        self.setCentralWidget(tabs)

    def _placeholder(self, text: str) -> QWidget:
        widget = QWidget()
        layout = QVBoxLayout(widget)
        label = QLabel(text)
        label.setWordWrap(True)
        layout.addWidget(label)
        layout.addStretch(1)
        return widget

    def _start_preview_server(self) -> None:
        self.preview_server.start()
        QMessageBox.information(self, "Preview Server", f"Listening on 127.0.0.1:{self.project.preview_port}")

    def _write_empty_snapshot(self) -> None:
        snapshot = build_empty_preview_snapshot(self.project)
        path = self.project.absolute_preview_snapshot_path
        write_preview_snapshot(path, snapshot)
        QMessageBox.information(self, "Preview Snapshot", f"Wrote {path}")

    def _handle_preview_message(self, message: dict) -> None:
        # UI-thread marshaling will be needed once this updates widgets.
        print("Preview message:", message)
