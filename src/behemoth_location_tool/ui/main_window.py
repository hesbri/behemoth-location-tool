from __future__ import annotations

from pathlib import Path

from PySide6.QtCore import QTimer, Slot
from PySide6.QtGui import QAction, QCloseEvent, QKeySequence, QUndoStack
from PySide6.QtWidgets import QMainWindow, QMessageBox, QTabWidget

from behemoth_location_tool.generation.generation_service import apply_preview_to_location
from behemoth_location_tool.generation.placement_pass import PlacementResultRow
from behemoth_location_tool.io.entity_loader import (
    load_all_entities,
    save_entity_manifest,
    save_entity_module,
)
from behemoth_location_tool.io.json_io import read_json
from behemoth_location_tool.io.location_factory import DEFAULT_BACK_EXIT_ENTITY_ID
from behemoth_location_tool.io.locations_loader import save_locations
from behemoth_location_tool.io.room_catalog_loader import save_room_catalog
from behemoth_location_tool.model.entity import EntityDefinition, EntityManifest, EntityModule
from behemoth_location_tool.model.location import (
    GraphNode,
    LocationGraph,
    LocationInstance,
    LocationsFile,
)
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.preview.snapshot import build_location_snapshot, write_preview_snapshot
from behemoth_location_tool.ui.entities_tab import EntitiesTab
from behemoth_location_tool.ui.generate_tab import GenerateTab
from behemoth_location_tool.ui.graph_tab import GraphTab
from behemoth_location_tool.ui.locations_tab import LocationsTab
from behemoth_location_tool.ui.preview_tab import PreviewTab
from behemoth_location_tool.ui.project_tab import ProjectTab
from behemoth_location_tool.ui.room_catalog_tab import RoomCatalogTab
from behemoth_location_tool.ui.validate_tab import ValidateTab
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity
from behemoth_location_tool.validation.runtime_validator import request_runtime_validation
from behemoth_location_tool.validation.validation_service import (
    validate_project_data,
)


class MainWindow(QMainWindow):
    def __init__(self, project: ProjectConfig, *, project_path: Path | None = None) -> None:
        super().__init__()
        self.project = project
        self._project_path = project_path
        self._undo_stack = QUndoStack(self)
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
        self._file_menu = menu_bar.addMenu("&File")

        save_project_action = QAction("Save Project Config", self)
        save_project_action.setStatusTip("Save only the .json project config")
        save_project_action.triggered.connect(self._on_save_project_config)
        self._file_menu.addAction(save_project_action)

        save_game_data_action = QAction("Save Game Data", self)
        save_game_data_action.setShortcut(QKeySequence.StandardKey.Save)
        save_game_data_action.setStatusTip(
            "Save modified game data files (entities, room catalog, locations)"
        )
        save_game_data_action.triggered.connect(self._on_save_game_data)
        self._file_menu.addAction(save_game_data_action)

        export_game_data_action = QAction("Export Game Data...", self)
        export_game_data_action.setStatusTip("Validate and export canonical game data")
        export_game_data_action.triggered.connect(self._on_export_game_data)
        self._file_menu.addAction(export_game_data_action)

        create_fresh_data_action = QAction("Create Fresh Game Data", self)
        create_fresh_data_action.setStatusTip("Create starter canonical data files in game_data_root")
        create_fresh_data_action.triggered.connect(self._on_create_fresh_v2_game_data)
        self._file_menu.addAction(create_fresh_data_action)

        self._edit_menu = menu_bar.addMenu("&Edit")
        undo_action = self._undo_stack.createUndoAction(self, "Undo")
        undo_action.setShortcut(QKeySequence.StandardKey.Undo)
        self._edit_menu.addAction(undo_action)
        redo_action = self._undo_stack.createRedoAction(self, "Redo")
        redo_action.setShortcut(QKeySequence.StandardKey.Redo)
        self._edit_menu.addAction(redo_action)

    # ------------------------------------------------------------------ save / dirty

    def _is_any_dirty(self) -> bool:
        return any(
            [
                self._project_tab.is_dirty,
                self._room_catalog_tab.is_dirty,
                self._locations_tab.is_dirty,
                self._entities_tab.is_dirty,
                not self._undo_stack.isClean(),
            ]
        )

    def _update_title(self) -> None:
        dirty = self._is_any_dirty()
        expected = (self._base_title + " *") if dirty else self._base_title
        if self.windowTitle() != expected:
            self.setWindowTitle(expected)

    def _save_project_config_only(self) -> list[str]:
        errors: list[str] = []

        if self._project_tab.is_dirty:
            try:
                self._project_tab._save()
            except Exception as exc:
                errors.append(f"Project config: {exc}")
        return errors

    def _sync_live_form_state(self) -> list[str]:
        sync_errors: list[str] = []
        sync_steps = [
            ("Room catalog form sync", self._room_catalog_tab._sync_form_to_catalog),
            ("Locations form sync", self._locations_tab._sync_form_to_data),
            ("Entities form sync", self._entities_tab._sync_form_to_module),
        ]
        for label, sync_fn in sync_steps:
            try:
                sync_fn()
            except Exception as exc:
                sync_errors.append(f"{label}: {exc}")
        return sync_errors

    def _save_game_data(self, *, force_all: bool = False, sync_forms: bool = True) -> list[str]:
        errors: list[str] = []
        data_root = self.project.absolute_game_data_root
        tool_root = self.project.absolute_tool_root

        if sync_forms:
            sync_errors = self._sync_live_form_state()
            if sync_errors:
                return sync_errors

        tool_root.mkdir(parents=True, exist_ok=True)

        if force_all or self._room_catalog_tab.is_dirty:
            try:
                path = self._room_catalog_tab._file_path or (data_root / "room_catalog.json")
                data_root.mkdir(parents=True, exist_ok=True)
                if force_all:
                    save_room_catalog(path, self._room_catalog_tab.catalog)
                    self._room_catalog_tab._file_path = path
                    self._room_catalog_tab._dirty = False
                    self._room_catalog_tab.clear_undo_dirty()
                else:
                    self._room_catalog_tab.save_file(path)
            except Exception as exc:
                errors.append(f"Room catalog: {exc}")

        if force_all or self._locations_tab.is_dirty:
            try:
                path = self._locations_tab._file_path or (data_root / "locations.json")
                data_root.mkdir(parents=True, exist_ok=True)
                if force_all:
                    save_locations(path, self._locations_tab.locations_file)
                    self._locations_tab._file_path = path
                    self._locations_tab._dirty = False
                    self._locations_tab.clear_undo_dirty()
                else:
                    self._locations_tab.save_file(path)
            except Exception as exc:
                errors.append(f"Locations: {exc}")

        if force_all or self._entities_tab.is_dirty:
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
                    if force_all:
                        save_entity_module(path, self._entities_tab.module)
                        self._entities_tab._file_path = path
                        self._entities_tab._dirty = False
                    else:
                        self._entities_tab.save_file(path)
            except Exception as exc:
                errors.append(f"Entities: {exc}")

        return errors

    def _on_save_project_config(self) -> None:
        errors = self._save_project_config_only()
        if errors:
            QMessageBox.critical(self, "Save Failed", "\n".join(errors))
        else:
            self._update_title()

    def _on_save_game_data(self) -> None:
        errors = self._save_game_data(force_all=False)
        if errors:
            QMessageBox.critical(self, "Save Failed", "\n".join(errors))
        else:
            self._mark_undo_clean()
            self._update_title()

    def _on_save(self) -> None:
        """Back-compat save handler: project config + dirty game data."""
        errors = self._save_project_config_only() + self._save_game_data(force_all=False)
        if errors:
            QMessageBox.critical(self, "Save Failed", "\n".join(errors))
        else:
            self._mark_undo_clean()
            self._update_title()

    def _build_export_validation_report(self) -> DiagnosticReport:
        modules = list(self._entity_modules)
        if modules:
            modules[0] = self._entities_tab.module
        else:
            modules = [self._entities_tab.module]
        return validate_project_data(
            project=self.project,
            manifest=self._entity_manifest,
            modules=modules,
            room_catalog=self._room_catalog_tab.catalog,
            locations_file=self._locations_tab.locations_file,
            tags_raw=self._tags_data,
        )

    def _on_export_game_data(self) -> None:
        sync_errors = self._sync_live_form_state()
        if sync_errors:
            QMessageBox.critical(self, "Export Failed", "\n".join(sync_errors))
            return

        report = self._build_export_validation_report()
        self._validate_tab.set_diagnostics(report.diagnostics)
        errors = [d for d in report.diagnostics if d.severity == Severity.ERROR]
        if errors:
            reply = QMessageBox.question(
                self,
                "Validation Errors",
                f"Validation found {len(errors)} error(s). Export anyway?",
                QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.Cancel,
                QMessageBox.StandardButton.Cancel,
            )
            if reply != QMessageBox.StandardButton.Yes:
                return

        save_errors = self._save_game_data(force_all=True, sync_forms=False)
        if save_errors:
            QMessageBox.critical(self, "Export Failed", "\n".join(save_errors))
            return
        self._mark_undo_clean()
        QMessageBox.information(self, "Export Complete", "Game data exported as canonical JSON.")

    def _on_create_fresh_v2_game_data(self) -> None:
        data_root = self.project.absolute_game_data_root
        tool_root = self.project.absolute_tool_root
        data_root.mkdir(parents=True, exist_ok=True)
        tool_root.mkdir(parents=True, exist_ok=True)
        (tool_root / "preview").mkdir(parents=True, exist_ok=True)
        (tool_root / "cache").mkdir(parents=True, exist_ok=True)
        (tool_root / "schemas").mkdir(parents=True, exist_ok=True)

        manifest_path = data_root / "entities.json"
        module_path = data_root / "entity_modules" / "main.json"
        room_catalog_path = data_root / "room_catalog.json"
        locations_path = data_root / "locations.json"
        tags_path = data_root / "tags.json"

        if not manifest_path.exists():
            manifest = EntityManifest(version=2, includes=["entity_modules/main.json"])
            save_entity_manifest(manifest_path, manifest)
        if not module_path.exists():
            module_path.parent.mkdir(parents=True, exist_ok=True)
            save_entity_module(
                module_path,
                EntityModule(
                    version=2,
                    entities=[
                        EntityDefinition(
                            id=DEFAULT_BACK_EXIT_ENTITY_ID,
                            kind="exit",
                            name="Default Back Exit",
                            description="Default return exit for non-start locations.",
                            tags=["exit.default_back", "exit.door"],
                        )
                    ],
                ),
            )
        if not room_catalog_path.exists():
            save_room_catalog(room_catalog_path, RoomCatalog(version=2, rooms=[]))
        if not locations_path.exists():
            starter = LocationInstance(id="location_01", catalog_room_id="", name="Location 01")
            locations = LocationsFile(
                version=2,
                start_location="location_01",
                graph=LocationGraph(nodes=[GraphNode(location_id="location_01", x=100, y=200)]),
                locations=[starter],
            )
            save_locations(locations_path, locations)
        if not tags_path.exists():
            tags_path.write_text('{\n  "version": 2,\n  "tags": []\n}\n', encoding="utf-8")

        self._load_project_data()
        self._mark_undo_clean()
        self._update_title()
        QMessageBox.information(self, "Fresh Data Ready", "Created missing canonical data files.")

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
        self._tabs = tabs

        self._project_tab = ProjectTab(self.project, project_path=self._project_path)
        tabs.addTab(self._project_tab, "Project")

        self._room_catalog_tab = RoomCatalogTab(self.project)
        self._room_catalog_tab.set_undo_stack(self._undo_stack)
        tabs.addTab(self._room_catalog_tab, "Room Catalog")

        self._locations_tab = LocationsTab()
        self._locations_tab.set_undo_stack(self._undo_stack)
        self._locations_tab.set_preview_callback(self._on_location_preview)
        tabs.addTab(self._locations_tab, "Locations")

        self._graph_tab = GraphTab()
        self._graph_tab.set_undo_stack(self._undo_stack)
        tabs.addTab(self._graph_tab, "Graph")
        self._graph_tab.graph_positions_changed.connect(self._on_graph_positions_changed)
        self._graph_tab.location_double_clicked.connect(self._on_graph_location_double_clicked)

        self._entities_tab = EntitiesTab(project=self.project)
        tabs.addTab(self._entities_tab, "Entities")

        self._generate_tab = GenerateTab()
        self._generate_tab.set_send_preview_callback(self._send_generation_preview)
        self._generate_tab.set_apply_callback(self._on_generation_applied)
        self._generate_tab.set_undo_stack(self._undo_stack)
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
        self._undo_stack.indexChanged.connect(self._on_undo_stack_index_changed)

        self.setCentralWidget(tabs)

    # ------------------------------------------------------------------ loading / callbacks

    def _load_project_data(self) -> None:
        """Load canonical project data files in implementation-plan order."""
        data_root = self.project.absolute_game_data_root
        load_diagnostics: list[Diagnostic] = []

        tags_path = data_root / "tags.json"
        if tags_path.exists():
            try:
                self._tags_data = read_json(tags_path)
            except Exception as exc:
                self._tags_data = None
                load_diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="tags_load_failed",
                        message=f"Failed to load tags.json: {exc}",
                        file=str(tags_path),
                        source="python",
                    )
                )

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
            except Exception as exc:
                self._entity_manifest = None
                self._entity_manifest_path = None
                self._entity_modules = []
                self._entity_module_paths = []
                load_diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="entities_load_failed",
                        message=f"Failed to load entities manifest/modules: {exc}",
                        file=str(manifest_path),
                        source="python",
                    )
                )

        room_catalog_path = data_root / "room_catalog.json"
        if room_catalog_path.exists():
            try:
                self._room_catalog_tab.load_file(room_catalog_path)
            except Exception as exc:
                load_diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="room_catalog_load_failed",
                        message=f"Failed to load room_catalog.json: {exc}",
                        file=str(room_catalog_path),
                        source="python",
                    )
                )

        locations_path = data_root / "locations.json"
        if locations_path.exists():
            try:
                self._locations_tab.load_file(locations_path)
            except Exception as exc:
                load_diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="locations_load_failed",
                        message=f"Failed to load locations.json: {exc}",
                        file=str(locations_path),
                        source="python",
                    )
                )

        self._sync_catalog_to_locations()
        self._sync_generate_tab()
        self._sync_locations_to_graph()
        self._undo_stack.clear()

        if load_diagnostics:
            self._validate_tab.set_diagnostics(load_diagnostics)
            self.statusBar().showMessage(
                f"Project loaded with {len(load_diagnostics)} error(s). See Validate tab.",
                10000,
            )

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

    def _request_runtime_validation(self) -> list[Diagnostic]:
        controller = self._preview_tab.controller
        return request_runtime_validation(
            is_runtime_running=controller.is_running,
            send_validate_runtime=controller.request_runtime_validation,
        )

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
        self._graph_tab.set_validation_context(
            catalog=self._room_catalog_tab.catalog,
            entities=self._entities_tab.module.entities,
            project_layers=None,
        )

    def _on_graph_positions_changed(self) -> None:
        self._locations_tab.mark_undo_dirty()

    @Slot(int)
    def _on_undo_stack_index_changed(self, _index: int) -> None:
        self._update_title()

    def _mark_undo_clean(self) -> None:
        self._undo_stack.setClean()
        self._locations_tab.clear_undo_dirty()
        self._room_catalog_tab.clear_undo_dirty()

    def _on_graph_location_double_clicked(self, location_id: str) -> None:
        if self._locations_tab.select_location(location_id):
            self._tabs.setCurrentWidget(self._locations_tab)

    def _send_generation_preview(
        self,
        location: LocationInstance,
        preview_rows: list[PlacementResultRow],
    ) -> bool:
        ctrl = self._preview_tab.controller
        if not ctrl.is_running:
            return False

        temp_location = location.model_copy(deep=True)
        apply_preview_to_location(temp_location, preview_rows)
        snapshot = build_location_snapshot(
            self.project,
            temp_location,
            catalog=self._room_catalog_tab.catalog,
            entities=self._entities_tab.module.entities,
        )
        snapshot_path = self.project.absolute_preview_snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_preview_snapshot(snapshot_path, snapshot)
        self._preview_tab.set_active_location(temp_location.id)
        ctrl.send_load_preview()
        return True

    def _on_generation_applied(self, location: LocationInstance) -> None:
        self._locations_tab.mark_undo_dirty()
        self._preview_tab.set_active_location(location.id)
        if self._preview_tab.controller.is_running:
            self._on_location_preview()
