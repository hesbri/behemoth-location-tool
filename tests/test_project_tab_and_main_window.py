"""Tests for ProjectTab, MainWindow wiring, canonicalization wording, and project save."""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from behemoth_location_tool.io.project import save_project
from behemoth_location_tool.model.project import ProjectConfig

# ---------------------------------------------------------------------------
# Helper: skip all GUI tests if PySide6 cannot be imported
# ---------------------------------------------------------------------------

pyside6_available = True
_pyside6_skip_reason = ""
try:
    # Import the widgets module specifically — a DLL mismatch (e.g. Anaconda Qt
    # vs PySide6 Qt) raises OSError here, not at the top-level PySide6 import.
    from PySide6.QtWidgets import QApplication  # noqa: F401
except (ImportError, OSError) as _e:
    pyside6_available = False
    _pyside6_skip_reason = f"PySide6 not usable: {_e}"

requires_gui = pytest.mark.skipif(
    not pyside6_available,
    reason=_pyside6_skip_reason or "PySide6 not available",
)


@pytest.fixture(scope="session")
def qapp():
    """Create a QApplication if one does not already exist."""
    from PySide6.QtWidgets import QApplication
    app = QApplication.instance()
    if app is None:
        app = QApplication(sys.argv)
    return app


# ===========================================================================
# Project config save round-trip (no GUI required)
# ===========================================================================

class TestProjectSave:
    def test_save_and_reload_project(self, tmp_path: Path) -> None:
        project = ProjectConfig()
        project.project_name = "Test Mansion"
        project.game_root = Path("my_game")
        project.preview_port = 9999

        path = tmp_path / "project.json"
        save_project(path, project)

        data = json.loads(path.read_text(encoding="utf-8"))
        assert data["projectName"] == "Test Mansion"
        assert data["previewPort"] == 9999

    def test_save_preserves_relative_paths(self, tmp_path: Path) -> None:
        """Saved JSON should store forward-slash paths (JSON convention)."""
        project = ProjectConfig()
        project.game_root = Path("../game")
        project.image_root = Path("assets/images")

        path = tmp_path / "project.json"
        save_project(path, project)

        data = json.loads(path.read_text(encoding="utf-8"))
        # On Windows, Path serializes with backslashes; use Path for comparison
        assert Path(data["gameRoot"]) == Path("../game")
        assert Path(data["imageRoot"]) == Path("assets/images")

    def test_save_all_fields_present(self, tmp_path: Path) -> None:
        project = ProjectConfig()
        path = tmp_path / "project.json"
        save_project(path, project)

        data = json.loads(path.read_text(encoding="utf-8"))
        expected_keys = {
            "projectName", "gameRoot", "gameExecutable", "contentRoot",
            "imageRoot", "gameDataRoot", "toolDataRoot", "designWidth",
            "designHeight", "previewPort", "version",
        }
        assert expected_keys.issubset(set(data.keys()))


# ===========================================================================
# Canonicalization wording (no GUI required — reads source files directly)
# ===========================================================================

class TestCanonicalizationWording:
    """Verify user-facing text does not contain V1/V2/legacy references."""

    def _read_source(self, module_path: str) -> str:
        """Read a Python source file without importing it."""
        parts = module_path.split(".")
        src = Path(__file__).parent.parent / "src" / "/".join(parts[:-1]) / (parts[-1] + ".py")
        return src.read_text(encoding="utf-8")

    def test_main_window_menu_text_no_v1_v2_legacy(self) -> None:
        """QAction labels and status tips must not contain v1/v2/legacy."""
        source = self._read_source("behemoth_location_tool.ui.main_window")
        lines = source.splitlines()
        for line in lines:
            # Check QAction constructor calls for user-facing text
            if 'QAction("' in line:
                text = line.lower()
                assert "v1" not in text, f"QAction text contains 'v1': {line.strip()}"
                assert "v2" not in text, f"QAction text contains 'v2': {line.strip()}"
                assert "legacy" not in text, f"QAction text contains 'legacy': {line.strip()}"
            if 'setStatusTip(' in line:
                text = line.lower()
                assert "legacy" not in text, f"StatusTip contains 'legacy': {line.strip()}"
                assert "v1" not in text, f"StatusTip contains 'v1': {line.strip()}"
                assert "v2" not in text, f"StatusTip contains 'v2': {line.strip()}"

    def test_main_window_uses_project_tab(self) -> None:
        """MainWindow source must import and use ProjectTab."""
        source = self._read_source("behemoth_location_tool.ui.main_window")
        assert "from behemoth_location_tool.ui.project_tab import ProjectTab" in source
        assert "self._project_tab = ProjectTab(" in source
        assert 'tabs.addTab(self._project_tab, "Project")' in source

    def test_main_window_no_project_placeholder(self) -> None:
        """MainWindow must not use placeholder for Project tab."""
        source = self._read_source("behemoth_location_tool.ui.main_window")
        for line in source.splitlines():
            if '"Project"' in line and "_placeholder" in line:
                pytest.fail("Project tab still uses placeholder")

    def test_main_window_uses_generate_tab(self) -> None:
        """MainWindow source must import and use GenerateTab."""
        source = self._read_source("behemoth_location_tool.ui.main_window")
        assert "from behemoth_location_tool.ui.generate_tab import GenerateTab" in source
        assert "self._generate_tab = GenerateTab(" in source
        assert 'tabs.addTab(self._generate_tab, "Generate")' in source

    def test_main_window_no_generate_placeholder(self) -> None:
        """MainWindow must not use placeholder for Generate tab."""
        source = self._read_source("behemoth_location_tool.ui.main_window")
        for line in source.splitlines():
            if '"Generate"' in line and "_placeholder" in line:
                pytest.fail("Generate tab still uses placeholder")

    def test_main_window_wires_generate_preview_runtime_callback(self) -> None:
        source = self._read_source("behemoth_location_tool.ui.main_window")
        assert "set_send_preview_callback(self._send_generation_preview)" in source
        assert "set_apply_callback(self._on_generation_applied)" in source
        assert "def _send_generation_preview(" in source
        assert "def _on_generation_applied(" in source


# ===========================================================================
# GUI tests (require PySide6)
# ===========================================================================

@requires_gui
class TestProjectTabGUI:
    def test_project_tab_displays_resolved_paths(self, qapp, tmp_path: Path) -> None:
        from behemoth_location_tool.ui.project_tab import ProjectTab
        project = ProjectConfig()
        project.game_root = tmp_path / "game"
        project.game_root.mkdir(parents=True, exist_ok=True)
        tab = ProjectTab(project, project_path=tmp_path / "project.json")

        assert tab._resolved_game_root.text() != ""
        assert tab._resolved_game_exe.text() != ""
        assert tab._resolved_content_root.text() != ""
        assert tab._resolved_image_root.text() != ""
        assert tab._resolved_game_data_root.text() != ""
        assert tab._resolved_preview_snapshot.text() != ""

    def test_project_tab_edit_marks_dirty(self, qapp) -> None:
        from behemoth_location_tool.ui.project_tab import ProjectTab
        project = ProjectConfig()
        tab = ProjectTab(project)
        assert not tab.is_dirty

        tab._name_edit.setText("New Project Name")
        assert tab.is_dirty
        assert tab._save_btn.isEnabled()

    def test_project_tab_save(self, qapp, tmp_path: Path) -> None:
        from behemoth_location_tool.ui.project_tab import ProjectTab
        project = ProjectConfig()
        project_path = tmp_path / "project.json"
        tab = ProjectTab(project, project_path=project_path)

        tab._name_edit.setText("Saved Project")
        tab._save_btn.click()

        assert project_path.exists()
        data = json.loads(project_path.read_text(encoding="utf-8"))
        assert data["projectName"] == "Saved Project"
        assert not tab.is_dirty

    def test_project_tab_preserves_relative_paths(self, qapp, tmp_path: Path) -> None:
        from behemoth_location_tool.ui.project_tab import ProjectTab
        project = ProjectConfig()
        project.game_root = Path("relative_game")
        project_path = tmp_path / "project.json"
        tab = ProjectTab(project, project_path=project_path)

        # Save button is only enabled after marking dirty; call _save() directly
        # since the intent here is to test path preservation, not button state.
        tab._save()

        data = json.loads(project_path.read_text(encoding="utf-8"))
        assert Path(data["gameRoot"]) == Path("relative_game")


@requires_gui
class TestMainWindowGUI:
    def _make_window(self, qapp, project: ProjectConfig | None = None,
                     project_path: Path | None = None):
        from behemoth_location_tool.ui.main_window import MainWindow
        if project is None:
            project = ProjectConfig()
        return MainWindow(project, project_path=project_path)

    def test_main_window_contains_project_tab(self, qapp) -> None:
        from behemoth_location_tool.ui.project_tab import ProjectTab
        win = self._make_window(qapp)
        assert isinstance(win._project_tab, ProjectTab)

    def test_main_window_generate_tab_is_wired(self, qapp) -> None:
        """Generate tab must be a GenerateTab instance, not a placeholder."""
        from behemoth_location_tool.ui.generate_tab import GenerateTab
        win = self._make_window(qapp)
        assert isinstance(win._generate_tab, GenerateTab)
        tabs = win.centralWidget()
        found = False
        for i in range(tabs.count()):
            if tabs.tabText(i) == "Generate":
                assert isinstance(tabs.widget(i), GenerateTab)
                found = True
                break
        assert found, "Generate tab not found in tab widget"

    def test_main_window_has_all_tabs(self, qapp) -> None:
        win = self._make_window(qapp)
        tabs = win.centralWidget()
        tab_names = [tabs.tabText(i) for i in range(tabs.count())]
        expected = ["Project", "Room Catalog", "Locations", "Graph",
                     "Entities", "Generate", "Validate", "Preview"]
        assert tab_names == expected

    def test_main_window_has_edit_menu_undo_redo(self, qapp) -> None:
        win = self._make_window(qapp)
        menu_bar = win.menuBar()
        all_actions = [
            action
            for top in menu_bar.actions()
            for action in (top.menu().actions() if top.menu() else [])
        ]
        labels = {action.text().replace("&", "") for action in all_actions}
        assert "Undo" in labels
        assert "Redo" in labels

    def test_menu_text_canonical(self, qapp) -> None:
        """Runtime check that menu text has no V1/V2/legacy."""
        win = self._make_window(qapp)
        menu_bar = win.menuBar()
        # Keep named reference to the QAction so PySide6 doesn't GC the QMenu
        # before we iterate over its children.
        first_action = menu_bar.actions()[0]
        file_menu = first_action.menu()
        for action in file_menu.actions():
            text = action.text().lower()
            tip = (action.statusTip() or "").lower()
            assert "v1" not in text
            assert "v2" not in text
            assert "legacy" not in text
            assert "legacy" not in tip

    def test_export_game_data_blocks_on_validation_errors_without_force(self, qapp, monkeypatch) -> None:
        from PySide6.QtWidgets import QMessageBox

        from behemoth_location_tool.ui.main_window import MainWindow
        from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity

        win = MainWindow(ProjectConfig())
        monkeypatch.setattr(
            win,
            "_build_export_validation_report",
            lambda: DiagnosticReport(
                diagnostics=[Diagnostic(severity=Severity.ERROR, code="x", message="bad")]
            ),
        )

        saved_calls: list[bool] = []
        monkeypatch.setattr(win, "_save_game_data", lambda **_kwargs: saved_calls.append(True) or [])
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )

        win._on_export_game_data()

        assert saved_calls == []

    def test_export_game_data_can_force_after_validation_errors(self, qapp, monkeypatch) -> None:
        from PySide6.QtWidgets import QMessageBox

        from behemoth_location_tool.ui.main_window import MainWindow
        from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity

        win = MainWindow(ProjectConfig())
        monkeypatch.setattr(
            win,
            "_build_export_validation_report",
            lambda: DiagnosticReport(
                diagnostics=[Diagnostic(severity=Severity.ERROR, code="x", message="bad")]
            ),
        )

        saved_force_values: list[bool] = []

        def _fake_save_game_data(  # type: ignore[no-untyped-def]
            *,
            force_all: bool = False,
            sync_forms: bool = True,
        ):
            del sync_forms
            saved_force_values.append(force_all)
            return []

        monkeypatch.setattr(win, "_save_game_data", _fake_save_game_data)
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Yes,
        )
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
        )

        win._on_export_game_data()

        assert saved_force_values == [True]

    def test_save_game_data_marks_undo_stack_clean(self, qapp, monkeypatch) -> None:
        from behemoth_location_tool.ui.main_window import MainWindow

        win = MainWindow(ProjectConfig())
        win._locations_tab._on_add_empty()
        assert not win._undo_stack.isClean()

        monkeypatch.setattr(win, "_save_game_data", lambda **_kwargs: [])
        win._on_save_game_data()

        assert win._undo_stack.isClean()

    def test_save_game_data_syncs_live_room_form_before_write(
        self, qapp, tmp_path: Path, monkeypatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        from behemoth_location_tool.ui.main_window import MainWindow

        project = ProjectConfig()
        project.game_root = tmp_path
        project.game_data_root = Path("data/behemoth/game")
        project.tool_data_root = Path(".behemoth_tool")
        win = MainWindow(project)
        monkeypatch.setattr(
            QMessageBox,
            "critical",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
        )

        win._room_catalog_tab._on_add()
        win._room_catalog_tab._f_name.setText("Edited Room Name")
        win._save_game_data(force_all=True)

        saved = json.loads(
            (project.absolute_game_data_root / "room_catalog.json").read_text(
                encoding="utf-8"
            )
        )
        assert saved["version"] == 2
        assert saved["rooms"][0]["name"] == "Edited Room Name"

    def test_create_fresh_v2_game_data_creates_files_and_tool_folders(
        self, qapp, tmp_path: Path, monkeypatch
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        from behemoth_location_tool.ui.main_window import MainWindow

        project = ProjectConfig()
        project.game_root = tmp_path
        project.game_data_root = Path("data/behemoth/game")
        project.tool_data_root = Path(".behemoth_tool")
        win = MainWindow(project)
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
        )

        win._on_create_fresh_v2_game_data()

        data_root = project.absolute_game_data_root
        tool_root = project.absolute_tool_root
        assert (data_root / "entities.json").exists()
        assert (data_root / "entity_modules" / "main.json").exists()
        assert (data_root / "room_catalog.json").exists()
        assert (data_root / "locations.json").exists()
        assert (data_root / "tags.json").exists()
        assert (tool_root / "preview").exists()
        assert (tool_root / "cache").exists()
        assert (tool_root / "schemas").exists()
        assert len(win._locations_tab.locations_file.locations) == 1
        assert win._locations_tab.locations_file.start_location == "location_01"

        tags = json.loads((data_root / "tags.json").read_text(encoding="utf-8"))
        assert tags == {"version": 2, "tags": []}
        assert any(
            entity.id == "exit.default_back"
            for entity in win._entities_tab.module.entities
        )

    def test_fresh_data_default_back_exit_entity_prevents_missing_entity_ref(
        self,
        qapp,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        from behemoth_location_tool.model.location import ExitDefinition
        from behemoth_location_tool.model.room import SocketDefinition
        from behemoth_location_tool.ui.main_window import MainWindow
        from behemoth_location_tool.validation.validator import validate_locations

        project = ProjectConfig()
        project.game_root = tmp_path
        project.game_data_root = Path("data/behemoth/game")
        project.tool_data_root = Path(".behemoth_tool")
        win = MainWindow(project)
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
        )

        win._on_create_fresh_v2_game_data()
        win._locations_tab._on_add_empty()

        start = win._locations_tab.locations_file.locations[0]
        non_start = win._locations_tab.locations_file.locations[1]
        start.sockets.append(
            SocketDefinition(
                id="start_socket",
                name="Start Socket",
                x=960,
                y=980,
                layer="exit_front",
            )
        )
        start.socket_overridden = True
        start.exits.append(
            ExitDefinition(
                id="start_to_non_start",
                entity_id="exit.default_back",
                target_location_id=non_start.id,
                socket_id="start_socket",
                layer="exit_front",
                tags=["exit.default_back"],
            )
        )

        report = validate_locations(
            win._locations_tab.locations_file,
            entities=win._entities_tab.module.entities,
        )
        assert not any(d.code == "missing_entity_ref" for d in report.diagnostics)

    def test_export_blocks_on_unsynced_invalid_ui_data(
        self,
        qapp,
        tmp_path: Path,
        monkeypatch,
    ) -> None:
        from PySide6.QtWidgets import QMessageBox

        from behemoth_location_tool.ui.main_window import MainWindow

        project = ProjectConfig()
        project.game_root = tmp_path
        project.game_data_root = Path("data/behemoth/game")
        project.tool_data_root = Path(".behemoth_tool")
        win = MainWindow(project)
        monkeypatch.setattr(
            QMessageBox,
            "information",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Ok,
        )
        monkeypatch.setattr(
            QMessageBox,
            "question",
            lambda *_args, **_kwargs: QMessageBox.StandardButton.Cancel,
        )

        win._on_create_fresh_v2_game_data()
        win._locations_tab._on_add_empty()
        win._locations_tab.select_location("new_location")
        win._locations_tab._exit_list.setCurrentRow(0)
        win._locations_tab._ef_socket_id.setText("")

        save_called: list[bool] = []
        monkeypatch.setattr(
            win,
            "_save_game_data",
            lambda **_kwargs: save_called.append(True) or [],
        )

        win._on_export_game_data()

        assert save_called == []
        assert any(
            diagnostic.code == "exit_empty_socket_id"
            for diagnostic in win._validate_tab._diagnostics
        )

    def test_file_menu_save_game_data_uses_standard_save_shortcut(self, qapp) -> None:
        from behemoth_location_tool.ui.main_window import MainWindow

        win = MainWindow(ProjectConfig())
        first_action = win.menuBar().actions()[0]
        file_menu = first_action.menu()
        action = next(a for a in file_menu.actions() if a.text().replace("&", "") == "Save Game Data")
        assert not action.shortcut().isEmpty()


# ===========================================================================
# Stage 11A — new non-GUI tests (no PySide6 needed)
# ===========================================================================

class TestProjectConfigAbsolutePaths:
    def test_absolute_game_data_root_relative(self, tmp_path: Path) -> None:
        project = ProjectConfig()
        project.game_root = tmp_path / "game"
        project.game_data_root = Path("data/behemoth/game")
        expected = (tmp_path / "game" / "data/behemoth/game").resolve()
        assert project.absolute_game_data_root == expected

    def test_absolute_game_data_root_absolute(self, tmp_path: Path) -> None:
        project = ProjectConfig()
        project.game_data_root = tmp_path / "absolute_data"
        assert project.absolute_game_data_root == tmp_path / "absolute_data"

    def test_absolute_game_data_root_independent_of_resolve_paths(self) -> None:
        project = ProjectConfig()
        path = project.absolute_game_data_root
        assert isinstance(path, Path)


class TestDiagnosticModel:
    def test_diagnostic_has_object_type(self) -> None:
        from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity
        d = Diagnostic(severity=Severity.ERROR, code="test", message="msg", object_type="location")
        assert d.object_type == "location"

    def test_diagnostic_has_source_default_python(self) -> None:
        from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity
        d = Diagnostic(severity=Severity.WARNING, code="test", message="msg")
        assert d.source == "python"

    def test_diagnostic_source_can_be_runtime(self) -> None:
        from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity
        d = Diagnostic(severity=Severity.INFO, code="test", message="msg", source="runtime")
        assert d.source == "runtime"

    def test_diagnostic_object_type_defaults_none(self) -> None:
        from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity
        d = Diagnostic(severity=Severity.INFO, code="test", message="msg")
        assert d.object_type is None


class TestMainWindowSourceChecks:
    """Source-level checks that don't require PySide6 runtime."""

    def _src(self, module: str) -> str:
        parts = module.split(".")
        p = Path(__file__).parent.parent / "src" / "/".join(parts[:-1]) / (parts[-1] + ".py")
        return p.read_text(encoding="utf-8")

    def test_main_window_has_save_action(self) -> None:
        src = self._src("behemoth_location_tool.ui.main_window")
        assert "Save Project" in src or "save_action" in src

    def test_main_window_has_export_actions(self) -> None:
        src = self._src("behemoth_location_tool.ui.main_window")
        assert "Export Game Data" in src
        assert "Save Game Data" in src
        assert "Save Project Config" in src

    def test_main_window_has_ctrl_s(self) -> None:
        src = self._src("behemoth_location_tool.ui.main_window")
        assert "StandardKey.Save" in src or "Ctrl+S" in src

    def test_main_window_has_dirty_check(self) -> None:
        src = self._src("behemoth_location_tool.ui.main_window")
        assert "_is_any_dirty" in src

    def test_main_window_has_close_dialog(self) -> None:
        src = self._src("behemoth_location_tool.ui.main_window")
        assert "closeEvent" in src
        assert "Unsaved" in src or "unsaved" in src.lower()

    def test_validate_tab_has_search(self) -> None:
        src = self._src("behemoth_location_tool.ui.validate_tab")
        assert "_search_edit" in src or "QLineEdit" in src

    def test_validate_tab_has_copy_button(self) -> None:
        src = self._src("behemoth_location_tool.ui.validate_tab")
        assert "_copy_button" in src or "Copy" in src

    def test_validate_tab_has_stage6_action_buttons(self) -> None:
        src = self._src("behemoth_location_tool.ui.validate_tab")
        assert "Validate All" in src
        assert "Validate Python Only" in src
        assert "Validate Runtime" in src

    def test_validate_tab_runtime_callback_hook_exists(self) -> None:
        src = self._src("behemoth_location_tool.ui.validate_tab")
        assert "set_runtime_validation_callback" in src

    def test_validate_tab_sorting_enabled(self) -> None:
        src = self._src("behemoth_location_tool.ui.validate_tab")
        assert "setSortingEnabled(True)" in src

    def test_validate_tab_row_colors(self) -> None:
        src = self._src("behemoth_location_tool.ui.validate_tab")
        assert "QColor" in src or "setBackground" in src

    def test_preview_tab_has_info_panel(self) -> None:
        src = self._src("behemoth_location_tool.ui.preview_tab")
        assert "_info_snapshot" in src
        assert "_info_command" in src
        assert "_info_active_location" in src

    def test_preview_tab_has_set_active_location(self) -> None:
        src = self._src("behemoth_location_tool.ui.preview_tab")
        assert "def set_active_location" in src

    def test_main_window_wires_runtime_validation(self) -> None:
        src = self._src("behemoth_location_tool.ui.main_window")
        assert "set_runtime_validation_callback" in src
        assert "request_runtime_validation" in src

    def test_room_catalog_tab_has_is_dirty(self) -> None:
        src = self._src("behemoth_location_tool.ui.room_catalog_tab")
        assert "def is_dirty" in src

    def test_locations_tab_has_is_dirty(self) -> None:
        src = self._src("behemoth_location_tool.ui.locations_tab")
        assert "def is_dirty" in src

    def test_entities_tab_has_is_dirty(self) -> None:
        src = self._src("behemoth_location_tool.ui.entities_tab")
        assert "def is_dirty" in src
