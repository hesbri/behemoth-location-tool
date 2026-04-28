from __future__ import annotations

import argparse
import subprocess
import sys
import time
from pathlib import Path

from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.preview.controller import ConnectionState, PreviewController

def load_project_config(path: Path) -> ProjectConfig:
    # Adjust this if GLM created a dedicated project loader.
    import json

    data = json.loads(path.read_text(encoding="utf-8"))

    # Support both camelCase and snake_case configs.
    return ProjectConfig(
        project_name=data.get("projectName", data.get("project_name", "Behemoth Mansion")),
        game_root=Path(data.get("gameRoot", data.get("game_root", "."))),
        game_executable=Path(data.get("gameExecutable", data.get("game_executable", ""))),
        content_root=data.get("contentRoot", data.get("content_root", "data/behemoth")),
        image_root=data.get("imageRoot", data.get("image_root", "data/behemoth/assets/images")),
        game_data_root=data.get("gameDataRoot", data.get("game_data_root", "data/behemoth/game")),
        tool_data_root=data.get("toolDataRoot", data.get("tool_data_root", ".behemoth_tool")),
        design_width=data.get("designWidth", data.get("design_width", 1920)),
        design_height=data.get("designHeight", data.get("design_height", 1080)),
        preview_port=data.get("previewPort", data.get("preview_port", 38171)),
    )

def resolve_config_path(config_path: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (config_path.parent / path).resolve()

def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--project", required=True)
    parser.add_argument("--timeout", type=float, default=25.0)
    parser.add_argument("--keep-open", action="store_true")
    args = parser.parse_args()

    project_path = Path(args.project).resolve()
    project = load_project_config(project_path)

    game_root = resolve_config_path(project_path, str(project.game_root))

    project = project.model_copy(update={
        "game_root": game_root,
    })
    
    game_exe = Path(project.game_executable)
    if game_exe.is_absolute():
        game_exe = game_exe.resolve()
    else:
        game_exe = (game_root / game_exe).resolve()

    if not game_exe.exists():
        print(f"[FAIL] Game executable not found: {game_exe}")
        return 1

    state_changes: list[str] = []
    diagnostics: list[str] = []
    logs: list[str] = []

    ctrl = PreviewController(project)

    ctrl.on_connection_changed = lambda state: state_changes.append(str(state))
    ctrl.on_diagnostic = lambda level, msg: diagnostics.append(f"{level}: {msg}")
    ctrl.on_log_message = lambda direction, line: logs.append(f"{direction}: {line}")

    print("[START] Preview controller")
    ctrl.start()

    content_root = Path(project.content_root)
    if content_root.is_absolute():
        mount_root = content_root.resolve()
    else:
        mount_root = (game_root / content_root).resolve()

    cmd = [
        str(game_exe),
        "--editor-preview",
        "--editor-host",
        "127.0.0.1",
        "--editor-port",
        str(project.preview_port),
        "--project-root",
        str(game_root),

        # Positional data mount root for brInit/brContext::Current().GetDataDir().
        str(mount_root),
    ]
    
    print("[RUN]", " ".join(cmd))
    
    settings_file = mount_root / "config" / "settings.json"
    if not settings_file.exists():
        print(f"[FAIL] settings.json not found at expected mount path: {settings_file}")
        return 1

    process = subprocess.Popen(
        cmd,
        cwd=str(game_root),
    )

    deadline = time.monotonic() + args.timeout
    saw_connected = False
    saw_preview_loaded = False

    try:
        while time.monotonic() < deadline:
            joined_states = " ".join(state_changes)
            joined_diags = " ".join(diagnostics)
            joined_logs = " ".join(logs)

            if "CONNECTED" in joined_states or str(ConnectionState.CONNECTED) in joined_states:
                saw_connected = True

            if "Preview loaded successfully" in joined_diags:
                saw_preview_loaded = True

            if "preview_loaded" in joined_logs:
                saw_preview_loaded = True
                
            if "file_not_found" in joined_diags or "file_not_found" in joined_logs:
                print("[FAIL] Runtime reported file_not_found while loading preview snapshot.")
                print("[DIAGNOSTICS]")
                print("\n".join(diagnostics))
                print("[LOGS]")
                print("\n".join(logs[-40:]))
                return 1

            if saw_connected and saw_preview_loaded:
                print("[PASS] Game connected and preview snapshot loaded successfully.")
                return 0

            if process.poll() is not None:
                print(f"[FAIL] Game process exited early with code {process.returncode}")
                print("\n".join(diagnostics))
                print("\n".join(logs[-20:]))
                return 1

            time.sleep(0.1)

        print("[FAIL] Timed out waiting for game preview roundtrip.")
        print("[states]", state_changes)
        print("[diagnostics]")
        print("\n".join(diagnostics))
        print("[logs tail]")
        print("\n".join(logs[-40:]))
        return 1

    finally:
        ctrl.stop()

        if not args.keep_open and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()


if __name__ == "__main__":
    raise SystemExit(main())
