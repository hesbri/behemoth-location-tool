from pathlib import Path
from behemoth_location_tool.io.json_io import write_json
from behemoth_location_tool.validation.schema_validator import validate_json_against_schema


def test_valid_entities_manifest(tmp_path: Path) -> None:
    data = {"version": 2, "includes": ["entity_modules/items.json"]}
    report = validate_json_against_schema(data, "entities")
    assert not report.has_errors


def test_invalid_entities_manifest_wrong_version(tmp_path: Path) -> None:
    data = {"version": 1, "includes": ["items.json"]}
    report = validate_json_against_schema(data, "entities")
    assert report.has_errors


def test_valid_room_catalog(tmp_path: Path) -> None:
    data = {"version": 2, "rooms": [
        {"id": "hall", "name": "Hall", "sockets": [
            {"id": "s1", "x": 100, "y": 200, "ambientSpawnChance": 50},
        ]},
    ]}
    report = validate_json_against_schema(data, "room_catalog")
    assert not report.has_errors


def test_invalid_room_catalog_missing_name(tmp_path: Path) -> None:
    data = {"version": 2, "rooms": [{"id": "hall"}]}
    report = validate_json_against_schema(data, "room_catalog")
    assert report.has_errors


def test_valid_locations(tmp_path: Path) -> None:
    data = {
        "version": 2, "startLocation": "hall",
        "locations": [{"id": "hall", "catalogRoomId": "c", "name": "Hall"}],
    }
    report = validate_json_against_schema(data, "locations")
    assert not report.has_errors


def test_invalid_locations_missing_start(tmp_path: Path) -> None:
    data = {"version": 2, "locations": []}
    report = validate_json_against_schema(data, "locations")
    assert report.has_errors


def test_valid_entity_module() -> None:
    data = {"version": 2, "entities": [
        {"id": "key", "kind": "item", "name": "Key", "description": "A key.", "tags": ["entity.spawnable"],
         "render": {"sprite": "key.png", "defaultLayer": "front_props"}},
    ]}
    report = validate_json_against_schema(data, "entity_module")
    assert not report.has_errors


def test_valid_tags_schema() -> None:
    data = {
        "version": 2,
        "tags": {
            "furniture": {"chair": {"armchair": {}}},
            "style": {"victorian": {}},
        },
    }
    report = validate_json_against_schema(data, "tags")
    assert not report.has_errors
