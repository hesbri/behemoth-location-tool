from __future__ import annotations

import json
from pathlib import Path

from behemoth_location_tool.io.json_io import write_json
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.validation.validation_service import validate_project


def _make_project(tmp_path: Path) -> tuple[ProjectConfig, Path, Path]:
    game_root = tmp_path / "game"
    data_root = game_root / "data" / "behemoth" / "game"
    image_root = game_root / "data" / "behemoth" / "assets" / "images"
    data_root.mkdir(parents=True, exist_ok=True)
    image_root.mkdir(parents=True, exist_ok=True)
    project = ProjectConfig(
        game_root=game_root,
        game_data_root=Path("data/behemoth/game"),
        image_root=Path("data/behemoth/assets/images"),
    )
    return project, data_root, image_root


def _write_minimal_valid_files(data_root: Path) -> None:
    write_json(
        data_root / "entities.json",
        {"version": 2, "includes": ["entity_modules/main.json"]},
    )
    (data_root / "entity_modules").mkdir(parents=True, exist_ok=True)
    write_json(
        data_root / "entity_modules" / "main.json",
        {
            "version": 2,
            "entities": [
                {
                    "id": "entity.chair",
                    "kind": "furniture",
                    "name": "Chair",
                    "description": "A chair",
                    "tags": ["entity.spawnable"],
                    "render": {"sprite": "furniture/chair.png"},
                }
            ],
        },
    )
    write_json(
        data_root / "room_catalog.json",
        {
            "version": 2,
            "rooms": [
                {
                    "id": "room.hall",
                    "name": "Hall",
                    "backgroundImage": "bg/hall.png",
                    "sockets": [],
                }
            ],
        },
    )
    write_json(
        data_root / "locations.json",
        {
            "version": 2,
            "startLocation": "hall_01",
            "locations": [{"id": "hall_01", "catalogRoomId": "room.hall", "name": "Hall"}],
        },
    )


def test_validate_project_reports_schema_diagnostics_for_invalid_raw_json(tmp_path: Path) -> None:
    project, data_root, _image_root = _make_project(tmp_path)
    _write_minimal_valid_files(data_root)

    # Corrupt room_catalog schema (missing required "name" on room object).
    write_json(
        data_root / "room_catalog.json",
        {"version": 2, "rooms": [{"id": "room.hall"}]},
    )

    report = validate_project(project)
    codes = {diag.code for diag in report.diagnostics}
    assert "room_catalog_schema_validation" in codes


def test_validate_project_reports_json_parse_errors_without_crashing(tmp_path: Path) -> None:
    project, data_root, _image_root = _make_project(tmp_path)
    _write_minimal_valid_files(data_root)

    path = data_root / "locations.json"
    path.write_text("{ this is not valid json ", encoding="utf-8")

    report = validate_project(project)
    assert any(diag.code == "locations_json_parse_error" for diag in report.diagnostics)


def test_validate_project_reports_asset_diagnostics(tmp_path: Path) -> None:
    project, data_root, image_root = _make_project(tmp_path)
    _write_minimal_valid_files(data_root)

    # Missing background + missing sprite should be surfaced.
    report = validate_project(project)
    codes = {diag.code for diag in report.diagnostics}
    assert "missing_background_image" in codes
    assert "missing_sprite_image" in codes

    # Unsupported extension.
    module_path = data_root / "entity_modules" / "main.json"
    module = json.loads(module_path.read_text(encoding="utf-8"))
    module["entities"][0]["render"]["sprite"] = "furniture/chair.tga"
    write_json(module_path, module)
    report = validate_project(project)
    assert any(diag.code == "unsupported_image_extension" for diag in report.diagnostics)

    # Unreadable png.
    module["entities"][0]["render"]["sprite"] = "furniture/corrupt.png"
    write_json(module_path, module)
    (image_root / "furniture").mkdir(parents=True, exist_ok=True)
    (image_root / "furniture" / "corrupt.png").write_text("not an image", encoding="utf-8")
    report = validate_project(project)
    assert any(diag.code == "image_unreadable" for diag in report.diagnostics)


def test_validate_project_reports_invalid_tag_references_when_tags_json_present(tmp_path: Path) -> None:
    project, data_root, _image_root = _make_project(tmp_path)
    _write_minimal_valid_files(data_root)

    write_json(
        data_root / "tags.json",
        {
            "version": 2,
            "tags": {
                "entity": {"spawnable": {}},
                "furniture": {"chair": {}},
            },
        },
    )

    module_path = data_root / "entity_modules" / "main.json"
    module = json.loads(module_path.read_text(encoding="utf-8"))
    module["entities"][0]["tags"] = ["unknown_domain.sofa", "entity.spawnable"]
    write_json(module_path, module)

    report = validate_project(project)
    assert any(diag.code == "invalid_tag_reference" for diag in report.diagnostics)


def test_validate_project_rejects_legacy_schema_version_files(tmp_path: Path) -> None:
    project, data_root, _image_root = _make_project(tmp_path)
    _write_minimal_valid_files(data_root)
    write_json(
        data_root / "locations.json",
        {
            "schemaVersion": 1,
            "startLocation": "hall_01",
            "locations": [{"id": "hall_01", "catalogRoomId": "room.hall", "name": "Hall"}],
        },
    )

    report = validate_project(project)
    assert any(diag.code == "locations_legacy_version" for diag in report.diagnostics)
