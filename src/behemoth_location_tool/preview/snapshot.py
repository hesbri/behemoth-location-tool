from __future__ import annotations
from pathlib import Path
from typing import Any
from behemoth_location_tool.io.json_io import write_json
from behemoth_location_tool.model.project import ProjectConfig

def build_empty_preview_snapshot(project: ProjectConfig) -> dict[str, Any]:
    return {
        "version": 1,
        "project": {
            "designWidth": project.design_width,
            "designHeight": project.design_height,
            "imageRoot": str(project.image_root).replace("\\", "/"),
        },
        "activeLocationId": "",
        "entities": [],
        "locations": [],
        "debug": {"showSockets": True, "showClickableRects": True, "showSafeArea": False, "showLayerNames": False},
    }

def write_preview_snapshot(path: Path, snapshot: dict[str, Any]) -> None:
    write_json(path, snapshot)
