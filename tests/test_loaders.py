from pathlib import Path

import pytest

from behemoth_location_tool.io.json_io import write_json
from behemoth_location_tool.io.room_catalog_loader import load_room_catalog, save_room_catalog
from behemoth_location_tool.io.locations_loader import load_locations, save_locations
from behemoth_location_tool.io.project import load_project_or_default, save_project
from behemoth_location_tool.model.project import ProjectConfig


def test_load_room_catalog(tmp_path: Path) -> None:
    data = {"version": 2, "rooms": [
        {"id": "catalog.hall", "name": "Hall", "sockets": [
            {"id": "s1", "name": "NPC Spot", "x": 500, "y": 600, "requiredTags": ["character.talkable"]},
        ]},
    ]}
    path = tmp_path / "room_catalog.json"
    write_json(path, data)
    catalog = load_room_catalog(path)
    assert len(catalog.rooms) == 1
    assert catalog.rooms[0].id == "catalog.hall"
    assert len(catalog.rooms[0].sockets) == 1
    assert catalog.rooms[0].sockets[0].x == 500


def test_save_and_reload_room_catalog(tmp_path: Path) -> None:
    from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
    catalog = RoomCatalog(rooms=[
        RoomCatalogEntry(id="r1", name="Room 1", sockets=[
            SocketDefinition(id="s1", name="Socket 1", x=100, y=200),
        ]),
    ])
    path = tmp_path / "room_catalog.json"
    save_room_catalog(path, catalog)
    reloaded = load_room_catalog(path)
    assert reloaded.rooms[0].sockets[0].x == 100


def test_load_room_catalog_rejects_schema_version(tmp_path: Path) -> None:
    data = {"schemaVersion": 1, "rooms": []}
    path = tmp_path / "room_catalog.json"
    write_json(path, data)
    with pytest.raises(ValueError):
        load_room_catalog(path)


def test_load_locations(tmp_path: Path) -> None:
    data = {
        "version": 2,
        "startLocation": "hall_01",
        "mansionSeed": 42,
        "graph": {"nodes": [{"locationId": "hall_01", "x": 100, "y": 200}]},
        "locations": [
            {"id": "hall_01", "catalogRoomId": "catalog.hall", "name": "Main Hall",
             "layers": ["background", "characters", "foreground"],
             "exits": [{"id": "e1", "entityId": "door", "targetLocationId": "hall_01",
                        "socketId": "s_exit", "tags": ["exit.default_back"]}],
             "placedEntities": [
                 {"instanceId": "hall_01__s1__gerald", "entityId": "gerald", "socketId": "s1",
                  "placementSource": "explicit"}]},
        ],
    }
    path = tmp_path / "locations.json"
    write_json(path, data)
    lf = load_locations(path)
    assert lf.start_location == "hall_01"
    assert lf.mansion_seed == 42
    assert len(lf.locations) == 1
    assert lf.locations[0].placed_entities[0].entity_id == "gerald"
    assert lf.graph.nodes[0].x == 100


def test_save_and_reload_locations(tmp_path: Path) -> None:
    from behemoth_location_tool.model.location import LocationsFile, LocationInstance, ExitDefinition
    lf = LocationsFile(
        start_location="a", mansion_seed=99,
        locations=[LocationInstance(id="a", catalog_room_id="c", name="A",
                                    exits=[ExitDefinition(id="e1", entity_id="door",
                                                          target_location_id="a", socket_id="s1",
                                                          tags=["exit.default_back"])])],
    )
    path = tmp_path / "locations.json"
    save_locations(path, lf)
    reloaded = load_locations(path)
    assert reloaded.mansion_seed == 99
    assert reloaded.locations[0].exits[0].tags == ["exit.default_back"]


def test_load_locations_rejects_schema_version(tmp_path: Path) -> None:
    data = {"schemaVersion": 1, "startLocation": "hall_01", "locations": []}
    path = tmp_path / "locations.json"
    write_json(path, data)
    with pytest.raises(ValueError):
        load_locations(path)


def test_load_project_default() -> None:
    project = load_project_or_default(None)
    assert project.project_name == "Behemoth Mansion"
    assert project.design_width == 1920


def test_save_and_reload_project(tmp_path: Path) -> None:
    project = ProjectConfig(project_name="Test", design_width=1280, design_height=720)
    path = tmp_path / "project.json"
    save_project(path, project)
    reloaded = load_project_or_default(path)
    assert reloaded.project_name == "Test"
    assert reloaded.design_width == 1280
