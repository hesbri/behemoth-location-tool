"""Tests for background inheritance: model helpers, migration, factory, snapshot, validator."""
from pathlib import Path

from behemoth_location_tool.io.location_factory import create_location_from_room
from behemoth_location_tool.io.locations_loader import load_locations, save_locations
from behemoth_location_tool.model.common import DesignSize
from behemoth_location_tool.model.location import (
    LocationInstance, LocationsFile,
    change_location_catalog_room, find_catalog_room, get_effective_background,
    migrate_location_background,
)
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry
from behemoth_location_tool.preview.snapshot import build_location_snapshot
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.validation.validator import validate_locations


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_catalog(*rooms: RoomCatalogEntry) -> RoomCatalog:
    return RoomCatalog(rooms=list(rooms))


def _make_room(room_id: str, bg: str | None = None) -> RoomCatalogEntry:
    return RoomCatalogEntry(
        id=room_id, name=room_id.title(),
        background_image=bg,
        design_size=DesignSize(w=1920, h=1080),
    )


def _make_location(
    loc_id: str = "loc1",
    catalog_room_id: str = "room_a",
    bg: str | None = None,
    overridden: bool = False,
) -> LocationInstance:
    return LocationInstance(
        id=loc_id,
        catalog_room_id=catalog_room_id,
        name=f"Location {loc_id}",
        background_image=bg,
        background_overridden=overridden,
    )


def _make_project() -> ProjectConfig:
    return ProjectConfig(
        design_width=1920,
        design_height=1080,
        game_root=".",
        game_data_root="data",
        image_root="images",
    )


# ── find_catalog_room ────────────────────────────────────────────────────────


def test_find_catalog_room_found() -> None:
    catalog = _make_catalog(_make_room("hall", "hall.png"), _make_room("kitchen", "kitchen.png"))
    result = find_catalog_room(catalog, "kitchen")
    assert result is not None
    assert result.id == "kitchen"
    assert result.background_image == "kitchen.png"


def test_find_catalog_room_not_found() -> None:
    catalog = _make_catalog(_make_room("hall"))
    assert find_catalog_room(catalog, "basement") is None


def test_find_catalog_room_none_catalog() -> None:
    assert find_catalog_room(None, "hall") is None


# ── get_effective_background ────────────────────────────────────────────────


def test_effective_background_inherited() -> None:
    """When not overridden, inherits from catalog room."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="hall.png", overridden=False)
    assert get_effective_background(loc, catalog) == "hall.png"


def test_effective_background_inherited_different_value() -> None:
    """When not overridden but location has different bg, still uses catalog."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="old.png", overridden=False)
    # Since overridden=False, effective background comes from catalog
    assert get_effective_background(loc, catalog) == "hall.png"


def test_effective_background_overridden() -> None:
    """When overridden, uses location's own background."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="custom.png", overridden=True)
    assert get_effective_background(loc, catalog) == "custom.png"


def test_effective_background_overridden_none() -> None:
    """When overridden but bg is None, returns None."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg=None, overridden=True)
    assert get_effective_background(loc, catalog) is None


def test_effective_background_no_catalog() -> None:
    """Without catalog, falls back to location's own bg."""
    loc = _make_location(bg="standalone.png", overridden=False)
    assert get_effective_background(loc, None) == "standalone.png"


def test_effective_background_no_catalog_room_match() -> None:
    """When catalog room not found, falls back to location's own bg."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="basement", bg="basement.png", overridden=False)
    # No matching room, falls back to location bg
    assert get_effective_background(loc, catalog) == "basement.png"


def test_effective_background_catalog_room_none_bg() -> None:
    """When catalog room has no bg, effective is None."""
    catalog = _make_catalog(_make_room("hall", None))
    loc = _make_location(catalog_room_id="hall", bg=None, overridden=False)
    assert get_effective_background(loc, catalog) is None


# ── migrate_location_background ──────────────────────────────────────────────


def test_migrate_already_overridden() -> None:
    """No-op when already overridden."""
    loc = _make_location(bg="custom.png", overridden=True)
    migrate_location_background(loc, None)
    assert loc.background_overridden is True


def test_migrate_none_bg() -> None:
    """No-op when background is None."""
    loc = _make_location(bg=None, overridden=False)
    migrate_location_background(loc, None)
    assert loc.background_overridden is False


def test_migrate_empty_bg() -> None:
    """No-op when background is empty string."""
    loc = _make_location(bg="", overridden=False)
    migrate_location_background(loc, None)
    assert loc.background_overridden is False


def test_migrate_matches_catalog() -> None:
    """When bg matches catalog, stays inherited."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="hall.png", overridden=False)
    migrate_location_background(loc, catalog)
    assert loc.background_overridden is False


def test_migrate_differs_from_catalog() -> None:
    """When bg differs from catalog, marks overridden."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="custom.png", overridden=False)
    migrate_location_background(loc, catalog)
    assert loc.background_overridden is True


def test_migrate_no_catalog() -> None:
    """When no catalog and has bg, assumes overridden."""
    loc = _make_location(bg="custom.png", overridden=False)
    migrate_location_background(loc, None)
    assert loc.background_overridden is True


def test_migrate_no_matching_room() -> None:
    """When catalog room not found and has bg, assumes overridden."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="basement", bg="basement.png", overridden=False)
    migrate_location_background(loc, catalog)
    assert loc.background_overridden is True


# ── change_location_catalog_room ─────────────────────────────────────────────


def test_change_catalog_room_inherited() -> None:
    """Inherited bg updates to new catalog room's bg."""
    catalog = _make_catalog(
        _make_room("hall", "hall.png"),
        _make_room("kitchen", "kitchen.png"),
    )
    loc = _make_location(catalog_room_id="hall", bg="hall.png", overridden=False)
    change_location_catalog_room(loc, "kitchen", catalog)
    assert loc.catalog_room_id == "kitchen"
    assert loc.background_image == "kitchen.png"
    assert loc.background_overridden is False


def test_change_catalog_room_overridden() -> None:
    """Overridden bg is preserved when changing catalog room."""
    catalog = _make_catalog(
        _make_room("hall", "hall.png"),
        _make_room("kitchen", "kitchen.png"),
    )
    loc = _make_location(catalog_room_id="hall", bg="custom.png", overridden=True)
    change_location_catalog_room(loc, "kitchen", catalog)
    assert loc.catalog_room_id == "kitchen"
    assert loc.background_image == "custom.png"
    assert loc.background_overridden is True


def test_change_catalog_room_no_catalog() -> None:
    """When no catalog, inherited path changes ID and sets bg to None (can't look up new room)."""
    loc = _make_location(catalog_room_id="hall", bg="hall.png", overridden=False)
    change_location_catalog_room(loc, "kitchen", None)
    assert loc.catalog_room_id == "kitchen"
    # No catalog to look up new room, background becomes None
    assert loc.background_image is None


def test_change_catalog_room_new_room_no_bg() -> None:
    """Changing to a room with no background."""
    catalog = _make_catalog(
        _make_room("hall", "hall.png"),
        _make_room("void", None),
    )
    loc = _make_location(catalog_room_id="hall", bg="hall.png", overridden=False)
    change_location_catalog_room(loc, "void", catalog)
    assert loc.catalog_room_id == "void"
    assert loc.background_image is None


# ── create_location_from_room (factory) ─────────────────────────────────────


def test_create_location_from_room_not_overridden() -> None:
    """New locations from catalog inherit background, not overridden."""
    room = _make_room("hall", "hall.png")
    loc = create_location_from_room(room, is_start=True)
    assert loc.background_image == "hall.png"
    assert loc.background_overridden is False


def test_create_location_from_room_no_bg() -> None:
    """New location from room with no background."""
    room = _make_room("hall", None)
    loc = create_location_from_room(room, is_start=True)
    assert loc.background_image is None
    assert loc.background_overridden is False


# ── Roundtrip: backgroundOverridden serializes correctly ─────────────────────


def test_location_roundtrip_with_override(tmp_path: Path) -> None:
    """backgroundOverridden field roundtrips through JSON."""
    lf = LocationsFile(
        start_location="loc1",
        locations=[
            LocationInstance(
                id="loc1", catalog_room_id="hall", name="Hall",
                background_image="custom.png", background_overridden=True,
            ),
            LocationInstance(
                id="loc2", catalog_room_id="kitchen", name="Kitchen",
                background_image="kitchen.png", background_overridden=False,
            ),
        ],
    )
    path = tmp_path / "locations.json"
    save_locations(path, lf)
    reloaded = load_locations(path)
    assert reloaded.locations[0].background_overridden is True
    assert reloaded.locations[0].background_image == "custom.png"
    assert reloaded.locations[1].background_overridden is False
    assert reloaded.locations[1].background_image == "kitchen.png"


def test_location_roundtrip_default_not_overridden(tmp_path: Path) -> None:
    """Default backgroundOverridden is False, serialized correctly."""
    lf = LocationsFile(
        start_location="loc1",
        locations=[
            LocationInstance(id="loc1", catalog_room_id="hall", name="Hall"),
        ],
    )
    path = tmp_path / "locations.json"
    save_locations(path, lf)
    reloaded = load_locations(path)
    assert reloaded.locations[0].background_overridden is False


def test_legacy_file_without_overridden_field_is_rejected(tmp_path: Path) -> None:
    """Legacy schemaVersion files are rejected in v2-only mode."""
    import json
    import pytest

    legacy_data = {
        "schemaVersion": 1,
        "startLocation": "loc1",
        "locations": [{
            "id": "loc1",
            "catalogRoomId": "hall",
            "name": "Hall",
            "backgroundImage": "hall.png",
        }],
    }
    path = tmp_path / "locations.json"
    path.write_text(json.dumps(legacy_data), encoding="utf-8")
    with pytest.raises(ValueError):
        load_locations(path)


# ── Preview snapshot uses effective background ───────────────────────────────


def test_snapshot_inherited_background() -> None:
    """Snapshot uses catalog background when inherited."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="hall.png", overridden=False)
    project = _make_project()
    snap = build_location_snapshot(project, loc, catalog=catalog)
    assert snap["locations"][0]["backgroundImage"] == "hall.png"


def test_snapshot_overridden_background() -> None:
    """Snapshot uses location background when overridden."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    loc = _make_location(catalog_room_id="hall", bg="custom.png", overridden=True)
    project = _make_project()
    snap = build_location_snapshot(project, loc, catalog=catalog)
    assert snap["locations"][0]["backgroundImage"] == "custom.png"


def test_snapshot_no_catalog() -> None:
    """Snapshot without catalog uses location bg directly."""
    loc = _make_location(bg="standalone.png", overridden=False)
    project = _make_project()
    snap = build_location_snapshot(project, loc, catalog=None)
    assert snap["locations"][0]["backgroundImage"] == "standalone.png"


def test_snapshot_inherited_catalog_updated() -> None:
    """Snapshot reflects catalog bg even if location bg is stale."""
    catalog = _make_catalog(_make_room("hall", "new_hall.png"))
    # Location still has old bg but is inherited (not overridden)
    loc = _make_location(catalog_room_id="hall", bg="old_hall.png", overridden=False)
    project = _make_project()
    snap = build_location_snapshot(project, loc, catalog=catalog)
    # Effective background comes from catalog
    assert snap["locations"][0]["backgroundImage"] == "new_hall.png"


# ── Validator: background warnings ──────────────────────────────────────────


def test_validate_location_missing_effective_bg_override() -> None:
    """Warning when overridden but no bg set."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    lf = LocationsFile(
        start_location="loc1",
        locations=[
            LocationInstance(
                id="loc1", catalog_room_id="hall", name="Hall",
                background_image=None, background_overridden=True,
                exits=[],
            ),
        ],
    )
    report = validate_locations(lf, catalog=catalog)
    codes = [d.code for d in report.diagnostics]
    assert "location_missing_background_override" in codes


def test_validate_location_missing_effective_bg_inherited() -> None:
    """Warning when inherited but catalog room has no bg."""
    catalog = _make_catalog(_make_room("hall", None))
    lf = LocationsFile(
        start_location="loc1",
        locations=[
            LocationInstance(
                id="loc1", catalog_room_id="hall", name="Hall",
                background_image=None, background_overridden=False,
                exits=[],
            ),
        ],
    )
    report = validate_locations(lf, catalog=catalog)
    codes = [d.code for d in report.diagnostics]
    assert "location_missing_background_inherited" in codes


def test_validate_location_no_bg_no_catalog() -> None:
    """Warning when no catalog and no bg."""
    lf = LocationsFile(
        start_location="loc1",
        locations=[
            LocationInstance(
                id="loc1", catalog_room_id="", name="Hall",
                background_image=None, background_overridden=False,
                exits=[],
            ),
        ],
    )
    report = validate_locations(lf, catalog=None)
    codes = [d.code for d in report.diagnostics]
    assert "location_missing_background" in codes


def test_validate_location_has_bg_no_warning() -> None:
    """No background warning when effective bg is present."""
    catalog = _make_catalog(_make_room("hall", "hall.png"))
    lf = LocationsFile(
        start_location="loc1",
        locations=[
            LocationInstance(
                id="loc1", catalog_room_id="hall", name="Hall",
                background_image="hall.png", background_overridden=False,
                exits=[],
            ),
        ],
    )
    report = validate_locations(lf, catalog=catalog)
    bg_codes = [d.code for d in report.diagnostics if "background" in d.code]
    assert len(bg_codes) == 0


def test_validate_catalog_room_missing_background() -> None:
    """Warning when catalog room has no background."""
    from behemoth_location_tool.validation.validator import validate_room_catalog
    catalog = _make_catalog(_make_room("hall", None))
    report = validate_room_catalog(catalog)
    codes = [d.code for d in report.diagnostics]
    assert "catalog_room_missing_background" in codes
