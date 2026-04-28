import json
from pathlib import Path
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.preview.controller import ConnectionState, PreviewController
from behemoth_location_tool.preview.protocol import hello, load_preview_snapshot, set_debug_overlay
from behemoth_location_tool.preview.snapshot import build_empty_preview_snapshot, write_preview_snapshot


def test_build_empty_preview_snapshot() -> None:
    project = ProjectConfig(project_name="Test")
    snapshot = build_empty_preview_snapshot(project)
    assert snapshot["version"] == 1
    assert snapshot["project"]["designWidth"] == 1920
    assert snapshot["project"]["designHeight"] == 1080
    assert isinstance(snapshot["entities"], list)
    assert isinstance(snapshot["locations"], list)


def test_write_preview_snapshot(tmp_path: Path) -> None:
    project = ProjectConfig(project_name="Test")
    snapshot = build_empty_preview_snapshot(project)
    path = tmp_path / "current_snapshot.json"
    write_preview_snapshot(path, snapshot)
    data = json.loads(path.read_text(encoding="utf-8"))
    assert data["version"] == 1


def test_preview_controller_initial_state() -> None:
    project = ProjectConfig(project_name="Test")
    ctrl = PreviewController(project)
    assert ctrl.state == ConnectionState.DISCONNECTED
    assert not ctrl.is_running


def test_preview_controller_stop_when_not_started() -> None:
    project = ProjectConfig(project_name="Test")
    ctrl = PreviewController(project)
    ctrl.stop()  # should not raise
    assert ctrl.state == ConnectionState.DISCONNECTED


def test_protocol_hello_message() -> None:
    msg = hello()
    assert msg.type == "hello"
    line = msg.to_json_line()
    data = json.loads(line)
    assert data["type"] == "hello"
    assert data["toolProtocolVersion"] == 1


def test_protocol_load_preview_snapshot() -> None:
    msg = load_preview_snapshot("/some/path.json")
    data = json.loads(msg.to_json_line())
    assert data["type"] == "load_preview_snapshot"
    assert data["path"] == "/some/path.json"


def test_protocol_set_debug_overlay() -> None:
    msg = set_debug_overlay(show_sockets=True, show_clickable_rects=False, show_safe_area=True, show_layer_names=False)
    data = json.loads(msg.to_json_line())
    assert data["type"] == "set_debug_overlay"
    assert data["showSockets"] is True
    assert data["showClickableRects"] is False
    assert data["showSafeArea"] is True
    assert data["showLayerNames"] is False


def test_preview_server_start_stop(tmp_path: Path) -> None:
    """Test TCP server start/stop without actual game launch."""
    game_root = tmp_path / "game"
    game_root.mkdir(parents=True, exist_ok=True)
    project = ProjectConfig(project_name="Test", game_root=game_root, preview_port=0)  # port 0 = OS picks one
    # Use a non-existent exe so the game launch emits a warning but doesn't crash
    project.game_executable = Path("nonexistent_game.exe")
    ctrl = PreviewController(project)

    received_messages: list[tuple[str, str]] = []
    ctrl.on_diagnostic = lambda level, msg: received_messages.append((level, msg))
    ctrl.start()
    assert ctrl.is_running
    assert ctrl.listening_port > 0

    # Server should be waiting
    assert ctrl.state == ConnectionState.WAITING

    ctrl.stop()
    assert not ctrl.is_running
    assert ctrl.state == ConnectionState.DISCONNECTED


def test_snapshot_writes_on_start(tmp_path: Path) -> None:
    """Verify controller writes snapshot file on start."""
    project = ProjectConfig(
        project_name="Test",
        tool_data_root=str(tmp_path / ".tool"),
    )
    project.game_executable = Path("nonexistent.exe")
    ctrl = PreviewController(project)
    ctrl.start()
    snapshot_path = project.absolute_preview_snapshot_path
    assert snapshot_path.exists()
    data = json.loads(snapshot_path.read_text(encoding="utf-8"))
    assert data["version"] == 1
    ctrl.stop()
