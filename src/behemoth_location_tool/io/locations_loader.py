from __future__ import annotations

from pathlib import Path

from behemoth_location_tool.io.json_io import read_json, write_json
from behemoth_location_tool.model.location import LocationsFile


def load_locations(path: Path) -> LocationsFile:
    """Load a locations.json file."""
    data = read_json(path)
    if "schemaVersion" in data:
        raise ValueError(f"Locations file at {path} uses deprecated 'schemaVersion'; expected 'version': 2")
    if data.get("version") != 2:
        raise ValueError(f"Locations file at {path} must have version 2, got {data.get('version')!r}")
    return LocationsFile.model_validate(data)


def save_locations(path: Path, locations: LocationsFile) -> None:
    """Save a locations.json file."""
    write_json(path, locations.model_dump(by_alias=True, mode="json", exclude_defaults=False))
