import json
from pathlib import Path

import pytest

from behemoth_location_tool.io.entity_loader import load_entity_manifest, save_entity_manifest, load_entity_module, save_entity_module, load_all_entities
from behemoth_location_tool.io.json_io import write_json


def test_load_entity_manifest(tmp_path: Path) -> None:
    data = {"version": 2, "includes": ["entity_modules/items.json"]}
    manifest_path = tmp_path / "entities.json"
    write_json(manifest_path, data)
    manifest = load_entity_manifest(manifest_path)
    assert manifest.version == 2
    assert manifest.includes == ["entity_modules/items.json"]


def test_save_and_reload_entity_manifest(tmp_path: Path) -> None:
    from behemoth_location_tool.model.entity import EntityManifest
    manifest = EntityManifest(version=2, includes=["a.json", "b.json"])
    path = tmp_path / "entities.json"
    save_entity_manifest(path, manifest)
    reloaded = load_entity_manifest(path)
    assert reloaded.includes == ["a.json", "b.json"]


def test_load_entity_module(tmp_path: Path) -> None:
    data = {"version": 2, "entities": [
        {
            "id": "lantern",
            "kind": "item",
            "name": "Lantern",
            "description": "An old lantern.",
            "tags": ["entity.spawnable"],
        },
    ]}
    path = tmp_path / "items.json"
    write_json(path, data)
    module = load_entity_module(path)
    assert len(module.entities) == 1
    assert module.entities[0].id == "lantern"


def test_load_all_entities(tmp_path: Path) -> None:
    manifest_data = {"version": 2, "includes": ["mods/items.json"]}
    write_json(tmp_path / "entities.json", manifest_data)
    mod_data = {"version": 2, "entities": [
        {"id": "key", "kind": "item", "name": "Key", "description": "A brass key."},
        {"id": "door", "kind": "exit", "name": "Door", "description": "A heavy door."},
    ]}
    (tmp_path / "mods").mkdir()
    write_json(tmp_path / "mods" / "items.json", mod_data)
    manifest, modules, all_entities = load_all_entities(tmp_path / "entities.json")
    assert len(modules) == 1
    assert len(all_entities) == 2
    assert all_entities[0].id == "key"


def test_load_entity_manifest_rejects_schema_version(tmp_path: Path) -> None:
    data = {"schemaVersion": 1, "includes": ["entity_modules/items.json"]}
    manifest_path = tmp_path / "entities.json"
    write_json(manifest_path, data)
    with pytest.raises(ValueError):
        load_entity_manifest(manifest_path)


def test_load_entity_module_rejects_schema_version(tmp_path: Path) -> None:
    data = {"schemaVersion": 1, "entities": []}
    path = tmp_path / "items.json"
    write_json(path, data)
    with pytest.raises(ValueError):
        load_entity_module(path)
