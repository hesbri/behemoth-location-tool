"""Tests for catalog socket inheritance for locations.

Covers:
- New location from catalog inherits sockets
- Adding socket to catalog appears in inheriting location effective sockets
- Modifying catalog socket updates inheriting location effective sockets
- Removing catalog socket removes from inheriting location effective sockets
- Location with socket override is not affected by catalog changes
- Clearing override returns to catalog sockets
- Exit validation uses effective sockets
- Deleting catalog socket used by exit produces missing_socket_ref
- Repeated socket IDs in different locations are allowed
- Duplicate socket IDs within one effective location are error
- Migration of legacy locations
- Preview snapshot uses effective sockets
- Changing catalog room handles socket inheritance
"""

from behemoth_location_tool.io.location_factory import create_location_from_room
from behemoth_location_tool.model.location import (
    ExitDefinition,
    LocationInstance,
    LocationsFile,
    _sockets_equal,
    change_location_catalog_room,
    get_effective_sockets,
    migrate_location_sockets,
)
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import (
    RoomCatalog,
    RoomCatalogEntry,
    SocketDefinition,
)
from behemoth_location_tool.preview.snapshot import build_location_snapshot
from behemoth_location_tool.validation.validator import validate_locations

# ---- helpers ----

def _make_socket(
    sid: str,
    name: str = "",
    x: int = 0,
    y: int = 0,
    layer: str = "characters",
) -> SocketDefinition:
    return SocketDefinition(id=sid, name=name or sid, x=x, y=y, layer=layer)


def _make_room(room_id: str, sockets: list[SocketDefinition] | None = None) -> RoomCatalogEntry:
    return RoomCatalogEntry(
        id=room_id,
        name=f"Room {room_id}",
        sockets=sockets or [],
    )


def _make_catalog(rooms: list[RoomCatalogEntry] | None = None) -> RoomCatalog:
    return RoomCatalog(rooms=rooms or [])


def _make_location(loc_id: str, catalog_room_id: str, **kwargs) -> LocationInstance:
    return LocationInstance(id=loc_id, catalog_room_id=catalog_room_id, name=loc_id, **kwargs)


def _make_project() -> ProjectConfig:
    return ProjectConfig()


# ---- tests ----

class TestGetEffectiveSockets:
    """Test get_effective_sockets helper."""

    def test_inherited_returns_catalog_sockets(self):
        sock = _make_socket("s1", "Socket 1")
        catalog = _make_catalog([_make_room("room1", [sock])])
        loc = _make_location("loc1", "room1")
        result = get_effective_sockets(loc, catalog)
        assert len(result) == 1
        assert result[0].id == "s1"

    def test_inherited_empty_location_sockets(self):
        catalog = _make_catalog([_make_room("room1", [_make_socket("s1")])])
        loc = _make_location("loc1", "room1")
        assert not loc.socket_overridden
        assert loc.sockets == []
        result = get_effective_sockets(loc, catalog)
        assert len(result) == 1

    def test_overridden_returns_location_sockets(self):
        catalog = _make_catalog([_make_room("room1", [_make_socket("s1")])])
        loc = _make_location("loc1", "room1", socket_overridden=True, sockets=[_make_socket("custom_s1")])
        result = get_effective_sockets(loc, catalog)
        assert len(result) == 1
        assert result[0].id == "custom_s1"

    def test_no_catalog_returns_location_sockets(self):
        loc = _make_location("loc1", "room1", sockets=[_make_socket("s1")])
        result = get_effective_sockets(loc, None)
        assert len(result) == 1
        assert result[0].id == "s1"

    def test_no_catalog_overridden_returns_location_sockets(self):
        loc = _make_location("loc1", "room1", socket_overridden=True, sockets=[_make_socket("s1")])
        result = get_effective_sockets(loc, None)
        assert len(result) == 1

    def test_catalog_missing_room_returns_location_sockets(self):
        catalog = _make_catalog([_make_room("other_room", [])])
        loc = _make_location("loc1", "room1", sockets=[_make_socket("fallback")])
        result = get_effective_sockets(loc, catalog)
        assert len(result) == 1
        assert result[0].id == "fallback"


class TestCreateLocationFromRoom:
    """Test that create_location_from_room sets up inheritance."""

    def test_new_location_inherits_sockets(self):
        room = _make_room("room1", [_make_socket("s1"), _make_socket("s2")])
        loc = create_location_from_room(room, is_start=True)
        assert not loc.socket_overridden
        assert loc.sockets == []
        catalog = _make_catalog([room])
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 2
        assert effective[0].id == "s1"
        assert effective[1].id == "s2"


class TestCatalogSocketChanges:
    """Test that catalog socket changes propagate to inheriting locations."""

    def test_adding_socket_to_catalog_appears_in_effective(self):
        room = _make_room("room1", [_make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        assert len(get_effective_sockets(loc, catalog)) == 1

        # Add a socket to the catalog room
        room.sockets.append(_make_socket("s2"))
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 2
        assert effective[1].id == "s2"

    def test_modifying_catalog_socket_updates_effective(self):
        room = _make_room("room1", [_make_socket("s1", x=100, y=200)])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        effective = get_effective_sockets(loc, catalog)
        assert effective[0].x == 100

        # Modify catalog socket
        room.sockets[0].x = 500
        effective = get_effective_sockets(loc, catalog)
        assert effective[0].x == 500

    def test_removing_catalog_socket_removes_from_effective(self):
        room = _make_room("room1", [_make_socket("s1"), _make_socket("s2")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        assert len(get_effective_sockets(loc, catalog)) == 2

        # Remove first socket from catalog
        room.sockets.pop(0)
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 1
        assert effective[0].id == "s2"


class TestSocketOverride:
    """Test that overrides are isolated from catalog changes."""

    def test_overridden_location_not_affected_by_catalog_add(self):
        room = _make_room("room1", [_make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            socket_overridden=True,
            sockets=[_make_socket("custom_s1")],
        )
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 1
        assert effective[0].id == "custom_s1"

        # Add socket to catalog
        room.sockets.append(_make_socket("s2"))
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 1
        assert effective[0].id == "custom_s1"

    def test_overridden_location_not_affected_by_catalog_remove(self):
        room = _make_room("room1", [_make_socket("s1"), _make_socket("s2")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            socket_overridden=True,
            sockets=[_make_socket("custom_s1")],
        )
        room.sockets.pop(0)
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 1
        assert effective[0].id == "custom_s1"

    def test_clear_override_returns_to_catalog(self):
        room = _make_room("room1", [_make_socket("s1"), _make_socket("s2")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            socket_overridden=True,
            sockets=[_make_socket("custom_s1")],
        )
        # Clear override
        loc.socket_overridden = False
        loc.sockets = []
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 2
        assert effective[0].id == "s1"
        assert effective[1].id == "s2"


class TestMigration:
    """Test migration of legacy locations."""

    def test_empty_sockets_treated_as_inherited(self):
        catalog = _make_catalog([_make_room("room1", [_make_socket("s1")])])
        loc = _make_location("loc1", "room1")
        migrate_location_sockets(loc, catalog)
        assert not loc.socket_overridden

    def test_matching_catalog_sockets_treated_as_inherited(self):
        room = _make_room("room1", [_make_socket("s1"), _make_socket("s2")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            sockets=[_make_socket("s1"), _make_socket("s2")],
        )
        migrate_location_sockets(loc, catalog)
        assert not loc.socket_overridden

    def test_different_sockets_treated_as_overridden(self):
        room = _make_room("room1", [_make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            sockets=[_make_socket("custom_s1")],
        )
        migrate_location_sockets(loc, catalog)
        assert loc.socket_overridden

    def test_no_catalog_with_sockets_treated_as_overridden(self):
        loc = _make_location("loc1", "room1", sockets=[_make_socket("s1")])
        migrate_location_sockets(loc, None)
        assert loc.socket_overridden

    def test_already_overridden_skipped(self):
        room = _make_room("room1", [_make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            socket_overridden=True,
            sockets=[_make_socket("custom")],
        )
        migrate_location_sockets(loc, catalog)
        assert loc.socket_overridden
        assert loc.sockets[0].id == "custom"


class TestChangeCatalogRoom:
    """Test changing catalog room with socket inheritance."""

    def test_inherited_sockets_switch_to_new_catalog(self):
        room1 = _make_room("room1", [_make_socket("s1")])
        room2 = _make_room("room2", [_make_socket("s2a"), _make_socket("s2b")])
        catalog = _make_catalog([room1, room2])
        loc = _make_location("loc1", "room1")

        change_location_catalog_room(loc, "room2", catalog)
        assert loc.catalog_room_id == "room2"
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 2
        assert effective[0].id == "s2a"

    def test_overridden_sockets_preserved_on_catalog_change(self):
        room1 = _make_room("room1", [_make_socket("s1")])
        room2 = _make_room("room2", [_make_socket("s2")])
        catalog = _make_catalog([room1, room2])
        loc = _make_location(
            "loc1", "room1",
            socket_overridden=True,
            sockets=[_make_socket("custom_s1")],
        )
        change_location_catalog_room(loc, "room2", catalog)
        assert loc.socket_overridden
        assert len(loc.sockets) == 1
        assert loc.sockets[0].id == "custom_s1"


class TestExitValidation:
    """Test that exit validation uses effective sockets."""

    def test_exit_valid_against_inherited_socket(self):
        room = _make_room("room1", [_make_socket("door_exit")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        loc.exits.append(ExitDefinition(
            id="exit1", entity_id="exit1",
            target_location_id="loc2", socket_id="door_exit",
        ))
        loc2 = _make_location("loc2", "room1")
        loc2.exits.append(ExitDefinition(
            id="exit2", entity_id="exit2",
            target_location_id="loc1", socket_id="door_exit",
            tags=["exit.default_back"],
        ))
        lf = LocationsFile(start_location="loc1", locations=[loc, loc2])
        report = validate_locations(lf, catalog=catalog)
        missing_socket = [d for d in report.diagnostics if d.code == "missing_socket_ref"]
        assert len(missing_socket) == 0

    def test_exit_invalid_against_removed_catalog_socket(self):
        """Deleting catalog socket used by exit should produce missing_socket_ref."""
        room = _make_room("room1", [_make_socket("door_exit")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        loc.exits.append(ExitDefinition(
            id="exit1", entity_id="exit1",
            target_location_id="loc2", socket_id="door_exit",
        ))
        loc2 = _make_location("loc2", "room1")
        loc2.exits.append(ExitDefinition(
            id="exit2", entity_id="exit2",
            target_location_id="loc1", socket_id="door_exit",
            tags=["exit.default_back"],
        ))
        # Now remove the socket from catalog
        room.sockets.clear()
        lf = LocationsFile(start_location="loc1", locations=[loc, loc2])
        report = validate_locations(lf, catalog=catalog)
        missing_socket = [d for d in report.diagnostics if d.code == "missing_socket_ref"]
        assert len(missing_socket) >= 1

    def test_placed_entity_valid_against_inherited_socket(self):
        room = _make_room("room1", [_make_socket("spawn_point")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        loc.placed_entities.append(
            LocationInstance.model_validate({
                "id": "loc1", "catalogRoomId": "room1", "name": "loc1",
                "placedEntities": [{
                    "instanceId": "pe1", "entityId": "entity1",
                    "socketId": "spawn_point", "layer": "characters",
                }],
            }).placed_entities[0]
        )
        loc2 = _make_location("loc2", "room1")
        loc2.exits.append(ExitDefinition(
            id="exit2", entity_id="exit2",
            target_location_id="loc1", socket_id="spawn_point",
            tags=["exit.default_back"],
        ))
        lf = LocationsFile(start_location="loc1", locations=[loc, loc2])
        report = validate_locations(lf, catalog=catalog)
        missing_socket = [d for d in report.diagnostics if d.code == "missing_socket_ref"]
        assert len(missing_socket) == 0


class TestDuplicateSocketIds:
    """Test duplicate socket ID validation."""

    def test_repeated_socket_ids_in_different_locations_allowed(self):
        """Same socket ID in different locations/catalog entries is fine."""
        room1 = _make_room("room1", [_make_socket("spawn")])
        room2 = _make_room("room2", [_make_socket("spawn")])
        catalog = _make_catalog([room1, room2])
        loc1 = _make_location("loc1", "room1")
        loc2 = _make_location("loc2", "room2")
        loc1.exits.append(ExitDefinition(
            id="e1", entity_id="e1",
            target_location_id="loc2", socket_id="spawn",
        ))
        loc2.exits.append(ExitDefinition(
            id="e2", entity_id="e2",
            target_location_id="loc1", socket_id="spawn",
            tags=["exit.default_back"],
        ))
        lf = LocationsFile(start_location="loc1", locations=[loc1, loc2])
        report = validate_locations(lf, catalog=catalog)
        dupes = [d for d in report.diagnostics if d.code == "duplicate_location_socket_id"]
        assert len(dupes) == 0

    def test_duplicate_socket_ids_within_one_effective_location_is_error(self):
        """Duplicate socket IDs within a single location's effective sockets is an error."""
        room = _make_room("room1", [_make_socket("s1"), _make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        loc.exits.append(ExitDefinition(
            id="exit1", entity_id="exit1",
            target_location_id="loc1", socket_id="s1",
            tags=["exit.default_back"],
        ))
        lf = LocationsFile(start_location="loc1", locations=[loc])
        report = validate_locations(lf, catalog=catalog)
        dupes = [d for d in report.diagnostics if d.code == "duplicate_location_socket_id"]
        assert len(dupes) == 1


class TestPreviewSnapshot:
    """Test that preview snapshot uses effective sockets."""

    def test_snapshot_uses_inherited_sockets(self):
        room = _make_room("room1", [_make_socket("s1", "Socket 1", 100, 200)])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        project = _make_project()
        snapshot = build_location_snapshot(project, loc, catalog=catalog)
        locations = snapshot["locations"]
        assert len(locations) == 1
        sockets = locations[0]["sockets"]
        assert len(sockets) == 1
        assert sockets[0]["id"] == "s1"
        assert sockets[0]["x"] == 100

    def test_snapshot_uses_overridden_sockets(self):
        room = _make_room("room1", [_make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location(
            "loc1", "room1",
            socket_overridden=True,
            sockets=[_make_socket("custom", "Custom", 500, 600)],
        )
        project = _make_project()
        snapshot = build_location_snapshot(project, loc, catalog=catalog)
        sockets = snapshot["locations"][0]["sockets"]
        assert len(sockets) == 1
        assert sockets[0]["id"] == "custom"
        assert sockets[0]["x"] == 500

    def test_snapshot_updates_when_catalog_changes(self):
        room = _make_room("room1", [_make_socket("s1")])
        catalog = _make_catalog([room])
        loc = _make_location("loc1", "room1")
        project = _make_project()

        # Initial snapshot
        snapshot = build_location_snapshot(project, loc, catalog=catalog)
        assert len(snapshot["locations"][0]["sockets"]) == 1

        # Add socket to catalog
        room.sockets.append(_make_socket("s2"))
        snapshot = build_location_snapshot(project, loc, catalog=catalog)
        assert len(snapshot["locations"][0]["sockets"]) == 2


class TestSocketsEqual:
    """Test the _sockets_equal helper."""

    def test_equal(self):
        a = [_make_socket("s1", "S1", 10, 20), _make_socket("s2", "S2", 30, 40)]
        b = [_make_socket("s1", "S1", 10, 20), _make_socket("s2", "S2", 30, 40)]
        assert _sockets_equal(a, b)

    def test_different_length(self):
        a = [_make_socket("s1")]
        b = [_make_socket("s1"), _make_socket("s2")]
        assert not _sockets_equal(a, b)

    def test_different_id(self):
        a = [_make_socket("s1")]
        b = [_make_socket("s2")]
        assert not _sockets_equal(a, b)

    def test_different_position(self):
        a = [_make_socket("s1", x=10)]
        b = [_make_socket("s1", x=20)]
        assert not _sockets_equal(a, b)

    def test_different_layer(self):
        a = [_make_socket("s1", layer="characters")]
        b = [_make_socket("s1", layer="foreground")]
        assert not _sockets_equal(a, b)
