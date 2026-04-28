from __future__ import annotations

import subprocess
import threading
from collections.abc import Callable
from pathlib import Path
from typing import Any

from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.preview.protocol import (
    PreviewMessage,
    hello,
    load_preview_snapshot,
    set_debug_overlay,
    validate_runtime,
)
from behemoth_location_tool.preview.server import PreviewServerController
from behemoth_location_tool.preview.snapshot import build_empty_preview_snapshot, write_preview_snapshot


class ConnectionState:
    DISCONNECTED = "disconnected"
    WAITING = "waiting"
    CONNECTED = "connected"


class PreviewController:
    """Orchestrates the preview TCP server, game process, and snapshot protocol.

    Uses plain callbacks instead of Qt signals so it can be tested without PySide6.
    Wrap with QtPreviewAdapter for UI integration.
    """

    def __init__(self, project: ProjectConfig) -> None:
        self.project = project
        self._state = ConnectionState.DISCONNECTED
        self._game_process: subprocess.Popen | None = None
        self._server = PreviewServerController(
            "127.0.0.1", project.preview_port, self._on_raw_message
        )
        self._server.add_connected_callback(self._on_client_connected)

        # Callbacks (set by adapter or tests)
        self.on_connection_changed: Callable[[str], None] = lambda state: None
        self.on_log_message: Callable[[str, str], None] = lambda direction, line: None
        self.on_diagnostic: Callable[[str, str], None] = lambda level, msg: None
        self.on_runtime_validation_result: Callable[[list[dict[str, str]]], None] = lambda diagnostics: None

    @property
    def state(self) -> str:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._server.server is not None

    def start(self) -> None:
        """Write snapshot and start the TCP server. Does NOT launch the game."""
        if self.is_running:
            return

        # 1. Write current_snapshot.json
        snapshot = build_empty_preview_snapshot(self.project)
        snapshot_path = self.project.absolute_preview_snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_preview_snapshot(snapshot_path, snapshot)
        self.on_diagnostic("info", f"Wrote snapshot: {snapshot_path}")

        # 2. Start TCP server
        self._server.start()
        self.project.preview_port = self._server.port
        self._set_state(ConnectionState.WAITING)
        self.on_diagnostic("info", f"Preview server listening on 127.0.0.1:{self.listening_port}")

    def launch_game(self) -> None:
        """Launch the game executable with --editor-preview flags.

        Call after start(). The game must connect back to the TCP server.
        """
        exe = self.project.game_executable
        if not exe or str(exe) in (".", ""):
            self.on_diagnostic("warn", "No game executable configured")
            return
        self._launch_game()

    def stop(self) -> None:
        """Stop the preview server and terminate the game process."""
        self._terminate_game()
        self._server.stop()
        self._set_state(ConnectionState.DISCONNECTED)
        self.on_diagnostic("info", "Preview server stopped")

    def _snapshot_protocol_path(self) -> str:
        snapshot_path = self.project.absolute_preview_snapshot_path.resolve()
        game_root = Path(self.project.game_root).resolve()

        try:
            path = snapshot_path.relative_to(game_root)
        except ValueError:
            path = snapshot_path

        return str(path).replace("\\", "/")

    def refresh_snapshot(self) -> None:
        """Re-write snapshot and send load_preview_snapshot to the connected client."""
        snapshot = build_empty_preview_snapshot(self.project)
        snapshot_path = self.project.absolute_preview_snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_preview_snapshot(snapshot_path, snapshot)

        msg = load_preview_snapshot(self._snapshot_protocol_path())
        self._send_message(msg)

    def send_load_preview(self) -> None:
        """Send load_preview_snapshot without rewriting the snapshot file.

        Use when the snapshot has already been written by another component
        (e.g. the room catalog editor).
        """
        msg = load_preview_snapshot(self._snapshot_protocol_path())
        self._send_message(msg)

    def send_debug_overlay(
        self,
        *,
        show_sockets: bool,
        show_socket_names: bool,
        show_clickable_rects: bool,
        show_safe_area: bool,
        show_layer_names: bool,
        show_placed_instance_ids: bool,
    ) -> None:
        """Send set_debug_overlay message to the connected client."""
        msg = set_debug_overlay(
            show_sockets=show_sockets,
            show_socket_names=show_socket_names,
            show_clickable_rects=show_clickable_rects,
            show_safe_area=show_safe_area,
            show_layer_names=show_layer_names,
            show_placed_instance_ids=show_placed_instance_ids,
        )
        self._send_message(msg)

    def request_runtime_validation(self) -> None:
        """Request runtime-side validation from the connected preview client."""
        self._send_message(validate_runtime())

    def _set_state(self, state: str) -> None:
        self._state = state
        self.on_connection_changed(state)

    def _launch_game(self) -> None:
        """Launch game process in a background thread."""

        port = self.listening_port

        def _run() -> None:
            try:
                game_root = Path(self.project.game_root).resolve()

                game_exe = Path(self.project.game_executable)
                if game_exe.is_absolute():
                    game_exe = game_exe.resolve()
                else:
                    game_exe = (game_root / game_exe).resolve()

                content_root = Path(self.project.content_root)
                if content_root.is_absolute():
                    mount_root = content_root.resolve()
                else:
                    mount_root = (game_root / content_root).resolve()

                settings_file = mount_root / "config" / "settings.json"

                if not game_exe.exists():
                    self.on_diagnostic("error", f"Game executable not found: {game_exe}")
                    return

                if not settings_file.exists():
                    self.on_diagnostic("error", f"settings.json not found at expected mount path: {settings_file}")
                    return

                cmd = [
                    str(game_exe),
                    "--editor-preview",
                    "--editor-host",
                    "127.0.0.1",
                    "--editor-port",
                    str(port),
                    "--project-root",
                    str(game_root),

                    # Positional mount path required by Brutalist/brInit.
                    str(mount_root),
                ]
                self.on_diagnostic("info", f"Launching: {' '.join(cmd)}")
                self._game_process = subprocess.Popen(cmd, cwd=str(game_root))
                self._game_process.wait()
                self.on_diagnostic("info", "Game process exited")
            except FileNotFoundError as exc:
                self.on_diagnostic("error", f"Game executable not found: {exc}")
            except Exception as exc:
                self.on_diagnostic("error", f"Failed to launch game: {exc}")
            finally:
                self._game_process = None

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()

    @property
    def listening_port(self) -> int:
        """Return the currently bound TCP port, or configured fallback."""
        if self._server.server is not None:
            return int(self._server.server.server_address[1])
        return int(self.project.preview_port)

    def _terminate_game(self) -> None:
        if self._game_process is not None:
            try:
                self._game_process.terminate()
                self._game_process.wait(timeout=5)
            except Exception:
                try:
                    self._game_process.kill()
                except Exception:
                    pass
            self._game_process = None

    def _on_client_connected(self) -> None:
        """Called when a client connects to the TCP server (runs in server thread)."""
        self._set_state(ConnectionState.CONNECTED)
        self.on_diagnostic("info", "Game client connected")
        # Send hello, then load_preview_snapshot
        self._send_message(hello())
        self._send_message(load_preview_snapshot(self._snapshot_protocol_path()))

    def _on_raw_message(self, message: dict[str, Any]) -> None:
        """Handle incoming message from the game client."""
        import json
        msg_type = message.get("type", "unknown")
        self.on_log_message("RX", json.dumps(message, ensure_ascii=False))

        if msg_type == "preview_loaded":
            ok = bool(message.get("ok", False))
            diagnostics = message.get("diagnostics", [])

            if ok:
                self.on_diagnostic("info", "Preview loaded successfully")
            else:
                self.on_diagnostic("error", "Preview failed to load")

            if isinstance(diagnostics, list):
                for diag in diagnostics:
                    if isinstance(diag, dict):
                        severity = str(diag.get("severity", "info"))
                        code = str(diag.get("code", "diagnostic"))
                        text = str(diag.get("message", ""))
                        self.on_diagnostic(severity, f"[{code}] {text}")
        elif msg_type == "invalid_json":
            self.on_diagnostic("error", f"Invalid JSON from client: {message.get('error', '')}")
        elif msg_type == "error":
            self.on_diagnostic("error", message.get("message", "Unknown error from client"))
        elif msg_type == "runtime_validation_result":
            runtime_diagnostics: list[dict[str, str]] = []

            def _append_entries(entries: Any, severity: str) -> None:
                if not isinstance(entries, list):
                    return
                for entry in entries:
                    if isinstance(entry, dict):
                        code = str(entry.get("code", "runtime_validation"))
                        text = str(entry.get("message", ""))
                    else:
                        code = "runtime_validation"
                        text = str(entry)
                    runtime_diagnostics.append(
                        {"severity": severity, "code": code, "message": text}
                    )
                    self.on_diagnostic(severity, f"[{code}] {text}")

            _append_entries(message.get("errors", []), "error")
            _append_entries(message.get("warnings", []), "warning")
            _append_entries(message.get("infos", []), "info")
            self.on_runtime_validation_result(runtime_diagnostics)

    def _send_message(self, msg: PreviewMessage) -> None:
        """Send a PreviewMessage, logging it."""
        self.on_log_message("TX", msg.to_json_line().rstrip("\n"))
        self._server.send_json({"type": msg.type, **msg.payload})
