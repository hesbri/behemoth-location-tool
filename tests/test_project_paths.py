"""Tests for ProjectConfig path resolution relative to config file location."""
from pathlib import Path
from behemoth_location_tool.io.json_io import write_json
from behemoth_location_tool.io.project import load_project_or_default, save_project
from behemoth_location_tool.model.project import ProjectConfig


def test_default_project_has_relative_paths() -> None:
    """Default (no-file) project keeps relative paths as-is."""
    project = load_project_or_default(None)
    assert project.game_root == Path(".")
    assert project.game_executable == Path("bin/Behemoth.exe")
    assert not project.game_root.is_absolute()


def test_resolve_paths_makes_game_root_absolute(tmp_path: Path) -> None:
    """gameRoot resolves relative to the project config file's directory."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    project = ProjectConfig(game_root=Path("../game"))
    project.resolve_paths(config_dir)
    assert project.game_root.is_absolute()
    assert project.game_root == (config_dir / ".." / "game").resolve()


def test_resolve_paths_game_exec_relative_to_game_root(tmp_path: Path) -> None:
    """gameExecutable resolves relative to resolved gameRoot."""
    config_dir = tmp_path / "tool"
    config_dir.mkdir()
    project = ProjectConfig(
        game_root=Path("../game"),
        game_executable=Path("bin/BehemothLauncher/x64/Release/BehemothLauncher.exe"),
    )
    project.resolve_paths(config_dir)
    game_root = (config_dir / ".." / "game").resolve()
    assert project.game_executable.is_absolute()
    assert project.game_executable == game_root / "bin" / "BehemothLauncher" / "x64" / "Release" / "BehemothLauncher.exe"


def test_resolve_paths_content_roots_relative_to_game_root(tmp_path: Path) -> None:
    """contentRoot, imageRoot, gameDataRoot, toolDataRoot resolve relative to gameRoot."""
    config_dir = tmp_path / "tool"
    config_dir.mkdir()
    project = ProjectConfig(
        game_root=Path("../Brutalist"),
        content_root=Path("data/behemoth"),
        image_root=Path("data/behemoth/assets/images"),
        game_data_root=Path("data/behemoth/game"),
        tool_data_root=Path(".behemoth_tool"),
    )
    project.resolve_paths(config_dir)
    game_root = (config_dir / ".." / "Brutalist").resolve()

    assert project.content_root == game_root / "data" / "behemoth"
    assert project.image_root == game_root / "data" / "behemoth" / "assets" / "images"
    assert project.game_data_root == game_root / "data" / "behemoth" / "game"
    assert project.tool_data_root == game_root / ".behemoth_tool"
    assert all(p.is_absolute() for p in [
        project.content_root, project.image_root,
        project.game_data_root, project.tool_data_root,
    ])


def test_absolute_paths_stay_absolute(tmp_path: Path) -> None:
    """Paths that are already absolute should not be changed."""
    config_dir = tmp_path / "tool"
    config_dir.mkdir()
    abs_game = (tmp_path / "Games" / "Brutalist").resolve()
    abs_tool = (tmp_path / "absolute_tool").resolve()
    project = ProjectConfig(game_root=abs_game, tool_data_root=abs_tool)
    project.resolve_paths(config_dir)
    assert project.game_root == abs_game
    assert project.tool_data_root == abs_tool


def test_examples_project_json_resolves_correctly() -> None:
    """Load examples/project.json and verify all paths resolve correctly."""
    examples_dir = Path(__file__).parent.parent / "examples"
    project_path = examples_dir / "project.json"
    if not project_path.exists():
        return  # skip if running from different cwd

    project = load_project_or_default(project_path)
    # All paths should be absolute after loading
    assert project.game_root.is_absolute()
    assert project.game_executable.is_absolute()
    assert project.content_root.is_absolute()
    assert project.image_root.is_absolute()
    assert project.game_data_root.is_absolute()
    assert project.tool_data_root.is_absolute()

    # gameRoot should be examples/../../Brutalist resolved
    assert project.game_root == (examples_dir / ".." / ".." / "Brutalist").resolve()

    # gameExecutable should be under gameRoot
    assert project.game_executable == (
        project.game_root / "bin" / "BehemothLauncher" / "x64" / "Release" / "BehemothLauncher.exe"
    )


def test_load_save_roundtrip_preserves_resolved_paths(tmp_path: Path) -> None:
    """Save a resolved project and reload it — paths should still be absolute."""
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    project = ProjectConfig(
        game_root=Path("../game"),
        game_executable=Path("bin/game.exe"),
        content_root=Path("data/content"),
    )
    project.resolve_paths(config_dir)

    # Save the resolved project
    path = config_dir / "project.json"
    save_project(path, project)

    # Reload
    reloaded = load_project_or_default(path)
    # Paths are re-resolved from the same config_dir, should match
    assert reloaded.game_root == project.game_root
    assert reloaded.game_executable == project.game_executable
    assert reloaded.content_root == project.content_root


def test_absolute_tool_root_after_resolve(tmp_path: Path) -> None:
    """absolute_tool_root property works correctly after resolve_paths."""
    config_dir = tmp_path / "tool"
    config_dir.mkdir()
    project = ProjectConfig(
        game_root=Path("../game"),
        tool_data_root=Path(".behemoth_tool"),
    )
    project.resolve_paths(config_dir)
    assert project.absolute_tool_root == project.game_root / ".behemoth_tool"
    assert project.absolute_preview_snapshot_path == (
        project.game_root / ".behemoth_tool" / "preview" / "current_snapshot.json"
    )