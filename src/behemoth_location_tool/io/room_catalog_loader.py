from __future__ import annotations

from pathlib import Path

from behemoth_location_tool.io.json_io import read_json, write_json
from behemoth_location_tool.model.room import RoomCatalog


def load_room_catalog(path: Path) -> RoomCatalog:
    """Load a room_catalog.json file."""
    data = read_json(path)
    if "schemaVersion" in data:
        raise ValueError(f"Room catalog at {path} uses deprecated 'schemaVersion'; expected 'version': 2")
    if data.get("version") != 2:
        raise ValueError(f"Room catalog at {path} must have version 2, got {data.get('version')!r}")
    return RoomCatalog.model_validate(data)


def save_room_catalog(path: Path, catalog: RoomCatalog) -> None:
    """Save a room_catalog.json file."""
    write_json(path, catalog.model_dump(by_alias=True, mode="json", exclude_defaults=False))
