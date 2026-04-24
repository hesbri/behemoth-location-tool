from __future__ import annotations
from dataclasses import dataclass
from typing import Any

@dataclass(frozen=True)
class PreviewMessage:
    type: str
    payload: dict[str, Any]

    def to_json_line(self) -> str:
        import json
        return json.dumps({"type": self.type, **self.payload}, ensure_ascii=False) + "\n"

def hello() -> PreviewMessage:
    return PreviewMessage("hello", {"toolProtocolVersion": 1})

def load_preview_snapshot(path: str) -> PreviewMessage:
    return PreviewMessage("load_preview_snapshot", {"path": path})

def set_debug_overlay(*, show_sockets: bool, show_clickable_rects: bool, show_safe_area: bool, show_layer_names: bool) -> PreviewMessage:
    return PreviewMessage("set_debug_overlay", {
        "showSockets": show_sockets,
        "showClickableRects": show_clickable_rects,
        "showSafeArea": show_safe_area,
        "showLayerNames": show_layer_names,
    })
