from __future__ import annotations

import shutil
import sys
from pathlib import Path

import pytest

from behemoth_location_tool.model.project import ProjectConfig
from conftest import requires_gui


def _fixture_root() -> Path:
    return Path(__file__).parent / "fixtures" / "mansion_v2"


def _copy_fixture_tree(target_data_root: Path) -> None:
    source = _fixture_root()
    target_data_root.mkdir(parents=True, exist_ok=True)
    shutil.copy2(source / "entities.json", target_data_root / "entities.json")
    shutil.copy2(source / "room_catalog.json", target_data_root / "room_catalog.json")
    shutil.copy2(source / "locations.json", target_data_root / "locations.json")
    shutil.copytree(source / "entity_modules", target_data_root / "entity_modules")


def test_app_main_passes_project_path(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import behemoth_location_tool.app as app_mod

    project_path = tmp_path / "projects" / "behemoth.json"
    project = ProjectConfig()
    captured: dict[str, object] = {}

    class _FakeApp:
        def __init__(self, _argv: list[str]) -> None:
            pass

        def exec(self) -> int:
            return 0

    class _FakeWindow:
        def __init__(self, _project: ProjectConfig, *, project_path: Path | None = None) -> None:
            captured["project_path"] = project_path

        def resize(self, _w: int, _h: int) -> None:
            pass

        def show(self) -> None:
            pass

    monkeypatch.setattr(app_mod, "load_project_or_default", lambda _path: project)
    monkeypatch.setattr(app_mod, "QApplication", _FakeApp)
    monkeypatch.setattr(app_mod, "MainWindow", _FakeWindow)
    monkeypatch.setattr(app_mod.sys, "argv", [sys.argv[0]])

    code = app_mod.main(["--project", str(project_path)])

    assert code == 0
    assert captured["project_path"] == project_path


@requires_gui
def test_main_window_loads_project_data_on_startup(tmp_path: Path) -> None:
    from PySide6.QtWidgets import QApplication

    from behemoth_location_tool.ui.main_window import MainWindow

    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    game_root = tmp_path / "game_root"
    data_root = game_root / "data" / "behemoth" / "game"
    _copy_fixture_tree(data_root)

    project = ProjectConfig(
        project_name="Fixture Game",
        game_root=game_root,
        game_data_root=Path("data/behemoth/game"),
    )
    win = MainWindow(project, project_path=tmp_path / "projects" / "behemoth.json")

    assert len(win._room_catalog_tab.catalog.rooms) == 3
    assert len(win._locations_tab.locations_file.locations) == 3
    assert len(win._entities_tab.module.entities) == 4
    assert win._graph_tab._locations_file is win._locations_tab.locations_file
