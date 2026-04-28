from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from behemoth_location_tool.io.entity_loader import (
    load_all_entities,
    save_entity_manifest,
    save_entity_module,
)
from behemoth_location_tool.io.json_io import read_json
from behemoth_location_tool.model.entity import EntityManifest, EntityModule
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.preview.snapshot import build_location_snapshot, write_preview_snapshot
from behemoth_location_tool.ui.entities_tab import EntitiesTab
from behemoth_location_tool.ui.generate_tab import GenerateTab
from behemoth_location_tool.ui.graph_tab import GraphTab
from behemoth_location_tool.ui.locations_tab import LocationsTab
from behemoth_location_tool.ui.preview_tab import PreviewTab
from behemoth_location_tool.ui.project_tab import ProjectTab
from behemoth_location_tool.ui.room_catalog_tab import RoomCatalogTab
from behemoth_location_tool.ui.validate_tab import ValidateTab
from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectConfig, *, project_path: Path | None = None) -> None:
        super().__init__()
        self.project = project
        self._project_path = project_path
        self._entity_manifest: EntityManifest | None = None
        self._entity_manifest_path: Path | None = None
        self._entity_modules: list[EntityModule] = []
        self._entity_module_paths: list[Path] = []
        self._tags_data: dict | list | None = None
        self._base_title = f"Behemoth Location Tool - {project.project_name}"
        self.setWindowTitle(self._base_title)
        self._build_menu()
        self._build_tabs()
        self._load_project_data()

        self._dirty_timer = QTimer(self)
        self._dirty_timer.setInterval(500)
        self._dirty_timer.timeout.connect(self._update_title)
        self._dirty_timer.start()

    # ------------------------------------------------------------------ menu

    def _build_menu(self) -> None:
        menu_bar = self.menuBar()
        file_menu = menu_bar.addMenu("&File")

        save_action = QAction("&Save Project", self)
        save_action.setShortcut(QKeySequence.StandardKey.Save)
        save_action.setStatusTip("Save all modified files to the game project")
        save_action.triggered.connect(self._on_save)
        file_menu.addAction(save_action)

    # ------------------------------------------------------------------ save / dirty

    def _is_any_dirty(self) -> bool:
        return any(
            [
                self._project_tab.is_dirty,
                self._room_catalog_tab.is_dirty,
                self._locations_tab.is_dirty,
                self._entities_tab.is_dirty,
            ]
        )

    def _update_title(self) -> None:
        dirty = self._is_any_dirty()
        expected = (self._base_title + " *") if dirty else self._base_title
        if self.windowTitle() != expected:
            self.setWindowTitle(expected)

    def _on_save(self) -> None:
        """Save all dirty tabs to their resolved game project paths."""
        errors: list[str] = []
        data_root = self.project.absolute_game_data_root

        if self._project_tab.is_dirty:
            try:
                self._project_tab._save()
            except Exception as exc:
                errors.append(f"Project config: {exc}")

        if self._room_catalog_tab.is_dirty:
            try:
                path = self._room_catalog_tab._file_path or (data_root / "room_catalog.json")
                data_root.mkdir(parents=True, exist_ok=True)
                self._room_catalog_tab.save_file(path)
            except Exception as exc:
                errors.append(f"Room catalog: {exc}")

        if self._locations_tab.is_dirty:
            try:
                path = self._locations_tab._file_path or (data_root / "locations.json")
                data_root.mkdir(parents=True, exist_ok=True)
                self._locations_tab.save_file(path)
            except Exception as exc:
                errors.append(f"Locations: {exc}")

        if self._entities_tab.is_dirty:
            try:
                if (
                    self._entity_manifest is not None
                    and self._entity_manifest_path is not None
                    and self._entity_module_paths
                ):
                    if not self._entity_modules:
                        self._entity_modules = [self._entities_tab.module]
                    self._entity_modules[0] = self._entities_tab.module
                    for module, path in zip(self._entity_modules, self._entity_module_paths, strict=False):
                        path.parent.mkdir(parents=True, exist_ok=True)
                        save_entity_module(path, module)
                    save_entity_manifest(self._entity_manifest_path, self._entity_manifest)
                    self._entities_tab._dirty = False
                else:
                    path = self._entities_tab._file_path or (data_root / "entity_modules" / "main.json")
                    path.parent.mkdir(parents=True, exist_ok=True)
                    self._entities_tab.save_file(path)
            except Exception as exc:
                errors.append(f"Entities: {exc}")

        if errors:
            QMessageBox.critical(self, "Save Failed", "\n".join(errors))
        else:
            self._update_title()

    # ------------------------------------------------------------------ close

    def closeEvent(self, event: QCloseEvent) -> None:
        if self._is_any_dirty():
            reply = QMessageBox.question(
                self,
                "Unsaved Changes",
                "There are unsaved changes. Save before closing?",
                QMessageBox.StandardButton.Save
                | QMessageBox.StandardButton.Discard
                | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Save,
            )
            if reply == QMessageBox.StandardButton.Save:
                self._on_save()
                if self._is_any_dirty():
                    event.ignore()
                    return
            elif reply == QMessageBox.StandardButton.Cancel:
                event.ignore()
                return

        if hasattr(self, "_preview_tab") and self._preview_tab is not None:
            self._preview_tab.controller.stop()
        super().closeEvent(event)

    # ------------------------------------------------------------------ tabs

    def _build_tabs(self) -> None:
        tabs = QTabWidget()

        self._project_tab = ProjectTab(self.project, project_path=self._project_path)
        tabs.addTab(self._project_tab, "Project")

        self._room_catalog_tab = RoomCatalogTab(self.project)
        tabs.addTab(self._room_catalog_tab, "Room Catalog")

        self._locations_tab = LocationsTab()
        self._locations_tab.set_preview_callback(self._on_location_preview)
        tabs.addTab(self._locations_tab, "Locations")

        self._graph_tab = GraphTab()
        tabs.addTab(self._graph_tab, "Graph")

        self._entities_tab = EntitiesTab(project=self.project)
        tabs.addTab(self._entities_tab, "Entities")

        self._generate_tab = GenerateTab()
        tabs.addTab(self._generate_tab, "Generate")

        self._validate_tab = ValidateTab(self.project)
        tabs.addTab(self._validate_tab, "Validate")

        self._preview_tab = PreviewTab(self.project)
        tabs.addTab(self._preview_tab, "Preview")
        self._preview_tab.controller.on_runtime_validation_result = self._on_runtime_validation_result
        self._validate_tab.set_runtime_validation_callback(self._request_runtime_validation)

        self._room_catalog_tab.set_preview_callback(self._on_room_preview)
        self._room_catalog_tab.set_catalog_changed_callback(self._sync_catalog_to_locations)
        self._sync_catalog_to_locations()
        self._sync_generate_tab()
        self._sync_locations_to_graph()

        self.setCentralWidget(tabs)

    # ------------------------------------------------------------------ loading / callbacks

    def _load_project_data(self) -> None:
        """Load canonical project data files in implementation-plan order."""
        data_root = self.project.absolute_game_data_root

        tags_path = data_root / "tags.json"
        if tags_path.exists():
            try:
                self._tags_data = read_json(tags_path)
            except Exception:
                self._tags_data = None

        manifest_path = data_root / "entities.json"
        if manifest_path.exists():
            try:
                manifest, modules, _all_entities = load_all_entities(manifest_path)
                self._entity_manifest = manifest
                self._entity_manifest_path = manifest_path
                self._entity_modules = modules
                self._entity_module_paths = [
                    (manifest_path.parent / include_path).resolve()
                    for include_path in manifest.includes
                ]
                if modules:
                    first_path = self._entity_module_paths[0] if self._entity_module_paths else None
                    self._entities_tab.set_module(modules[0], file_path=first_path)
            except Exception:
                self._entity_manifest = None
                self._entity_manifest_path = None
                self._entity_modules = []
                self._entity_module_paths = []

        room_catalog_path = data_root / "room_catalog.json"
        if room_catalog_path.exists():
            try:
                self._room_catalog_tab.load_file(room_catalog_path)
            except Exception:
                pass

        locations_path = data_root / "locations.json"
        if locations_path.exists():
            try:
                self._locations_tab.load_file(locations_path)
            except Exception:
                pass

        self._sync_catalog_to_locations()
        self._sync_generate_tab()
        self._sync_locations_to_graph()

    def _on_room_preview(self, room) -> None:  # type: ignore[no-untyped-def]
        ctrl = self._preview_tab.controller
        if ctrl.is_running:
            ctrl.send_load_preview()

    def _on_location_preview(self) -> None:
        locations_file = self._locations_tab.locations_file
        locations = locations_file.locations
        if not locations:
            return

        active_id = self._locations_tab.current_location_id or locations_file.start_location
        target = next((location for location in locations if location.id == active_id), None)
        if target is None:
            target = locations[0]

        snapshot = build_location_snapshot(
            self.project,
            target,
            catalog=self._room_catalog_tab.catalog,
            entities=self._entities_tab.module.entities,
        )
        snapshot_path = self.project.absolute_preview_snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_preview_snapshot(snapshot_path, snapshot)

        self._preview_tab.set_active_location(target.id)

        ctrl = self._preview_tab.controller
        if ctrl.is_running:
            ctrl.send_load_preview()

    def _request_runtime_validation(self) -> None:
        controller = self._preview_tab.controller
        if not controller.is_running:
            self._validate_tab.add_runtime_diagnostics(
                [
                    Diagnostic(
                        severity=Severity.WARNING,
                        code="runtime_disconnected",
                        message="Runtime validation requested, but preview runtime is not running.",
                        source="runtime",
                    )
                ]
            )
            return
        controller.request_runtime_validation()

    def _on_runtime_validation_result(self, diagnostics: list[dict[str, str]]) -> None:
        mapped: list[Diagnostic] = []
        for item in diagnostics:
            severity_str = item.get("severity", "info")
            if severity_str == "error":
                severity = Severity.ERROR
            elif severity_str == "warning":
                severity = Severity.WARNING
            else:
                severity = Severity.INFO
            mapped.append(
                Diagnostic(
                    severity=severity,
                    code=item.get("code", "runtime_validation"),
                    message=item.get("message", ""),
                    source="runtime",
                )
            )
        self._validate_tab.add_runtime_diagnostics(mapped)

    def _sync_catalog_to_locations(self) -> None:
        self._locations_tab.set_catalog(self._room_catalog_tab.catalog)
        self._sync_generate_tab()

    def _sync_generate_tab(self) -> None:
        self._generate_tab.set_locations_file(self._locations_tab.locations_file)
        self._generate_tab.set_catalog(self._room_catalog_tab.catalog)
        self._generate_tab.set_entities(self._entities_tab.module.entities)
        self._room_catalog_tab.set_entities(self._entities_tab.module.entities)

    def _sync_locations_to_graph(self) -> None:
        self._graph_tab.set_locations_file(self._locations_tab.locations_file)
