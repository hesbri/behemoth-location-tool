from __future__ import annotations
import socketserver, threading
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

JsonHandler = Callable[[dict[str, Any]], None]

class _LineJsonHandler(socketserver.StreamRequestHandler):
    def handle(self) -> None:
        server = self.server
        assert isinstance(server, PreviewTcpServer)
        server.client = self
        server.on_client_connected()
        for raw_line in self.rfile:
            import json
            try:
                message = json.loads(raw_line.decode("utf-8"))
            except json.JSONDecodeError as exc:
                server.on_message({"type": "invalid_json", "error": str(exc)})
                continue
            server.on_message(message)

class PreviewTcpServer(socketserver.ThreadingTCPServer):
    allow_reuse_address = True

    def __init__(self, host: str, port: int, on_message: JsonHandler):
        super().__init__((host, port), _LineJsonHandler)
        self.on_message = on_message
        self.client: _LineJsonHandler | None = None
        self._connected_callbacks: list[Callable[[], None]] = []

    def on_client_connected(self) -> None:
        for callback in self._connected_callbacks:
            callback()

    def add_connected_callback(self, callback: Callable[[], None]) -> None:
        self._connected_callbacks.append(callback)

    def send_json(self, message: dict[str, Any]) -> None:
        if self.client is None:
            return
        import json
        line = json.dumps(message, ensure_ascii=False) + "\n"
        self.client.wfile.write(line.encode("utf-8"))
        self.client.wfile.flush()

@dataclass
class PreviewServerController:
    host: str
    port: int
    on_message: JsonHandler
    server: PreviewTcpServer | None = field(default=None, init=False)
    thread: threading.Thread | None = field(default=None, init=False)

    def start(self) -> None:
        if self.server is not None:
            return
        self.server = PreviewTcpServer(self.host, self.port, self.on_message)
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def stop(self) -> None:
        if self.server is None:
            return
        self.server.shutdown()
        self.server.server_close()
        self.server = None
        self.thread = None

    def send_json(self, message: dict[str, Any]) -> None:
        if self.server is not None:
            self.server.send_json(message)
