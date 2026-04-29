"""Tests for room catalog visual preview snapshot generation."""
from pathlib import Path

from behemoth_location_tool.io.json_io import read_json
from behemoth_location_tool.model.common import DesignSize, PivotMode
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import (
    LayerConfig,
    RoomCatalogEntry,
    SocketDefinition,
)
from behemoth_location_tool.preview.snapshot import (
    build_room_catalog_snapshot,
    write_preview_snapshot,
)


def _make_project(tmp_path: Path) -> ProjectConfig:
    """Create a test project with resolved paths."""
    p = ProjectConfig()
    p.game_root = tmp_path / "game"
    p.image_root = tmp_path / "game" / "data" / "images"
    p.tool_data_root = Path(".behemoth_tool")
    return p


def _make_room() -> RoomCatalogEntry:
    return RoomCatalogEntry(
        id="library",
        name="Library",
        description="A dusty library.",
        background_image="rooms/library_bg.png",
        design_size=DesignSize(w=1920, h=1080),
        tags=["indoor", "ground_floor"],
        layers=LayerConfig(mode="custom", order=["bg", "characters", "fg"]),
        sockets=[
            SocketDefinition(
                id="socket_left", name="Left Wall",
                x=200, y=500, rotation=0.0, scale=1.0,
                pivot_mode=PivotMode.BOTTOM,
                layer="characters",
                sort_order=1,
                ambient_spawn_chance=50,
                allowed_entity_ids=["ghost", "spider"],
                required_tags=["dark"],
                forbidden_tags=["lit"],
            ),
            SocketDefinition(
                id="socket_center", name="Center",
                x=960, y=540,
            ),
        ],
    )


class TestRoomCatalogSnapshot:
    """Test build_room_catalog_snapshot output structure."""

    def test_snapshot_has_active_location_id(self) -> None:
        """Snapshot must include activeLocationId (not empty)."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        assert snap["activeLocationId"] == "preview_room_catalog_library"

    def test_snapshot_version(self) -> None:
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        assert snap["version"] == 1

    def test_snapshot_project_design_size(self) -> None:
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        assert snap["project"]["designWidth"] == 1920
        assert snap["project"]["designHeight"] == 1080

    def test_snapshot_image_root(self) -> None:
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        assert "imageRoot" in snap["project"]
        assert "/" in snap["project"]["imageRoot"] or "\\" in snap["project"]["imageRoot"]

    def test_snapshot_sockets_serialize(self) -> None:
        """Sockets from room must appear in the snapshot's location."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert len(loc["sockets"]) == 2
        s0 = loc["sockets"][0]
        assert s0["id"] == "socket_left"
        assert s0["x"] == 200
        assert s0["y"] == 500
        assert s0["pivotMode"] == "bottom"
        assert s0["ambientSpawnChance"] == 50
        assert s0["allowedEntityIds"] == ["ghost", "spider"]
        assert s0["requiredTags"] == ["dark"]
        assert s0["forbiddenTags"] == ["lit"]

    def test_snapshot_background_image(self) -> None:
        """backgroundImage from room must appear in the snapshot location."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["backgroundImage"] == "rooms/library_bg.png"

    def test_snapshot_layers_custom(self) -> None:
        """Custom layer config serializes correctly."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["layers"]["mode"] == "custom"
        assert loc["layers"]["order"] == ["bg", "characters", "fg"]

    def test_snapshot_layers_project_default(self) -> None:
        """Default layer config serializes as project_default."""
        project = _make_project(Path("/tmp/test"))
        room = RoomCatalogEntry(id="hall", name="Hall")
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["layers"]["mode"] == "project_default"

    def test_snapshot_location_has_room_id(self) -> None:
        """Location entry must include roomId matching the catalog entry."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["roomId"] == "library"

    def test_snapshot_location_design_size(self) -> None:
        """Location designSize matches the room's design_size."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["designSize"]["w"] == 1920
        assert loc["designSize"]["h"] == 1080

    def test_snapshot_debug_flags(self) -> None:
        """Debug overlay flags are present."""
        project = _make_project(Path("/tmp/test"))
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        assert "debug" in snap
        assert "showSockets" in snap["debug"]
        assert "showClickableRects" in snap["debug"]

    def test_snapshot_write_to_file(self, tmp_path: Path) -> None:
        """Snapshot can be written to disk and reloaded."""
        project = _make_project(tmp_path)
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        path = tmp_path / "snap.json"
        write_preview_snapshot(path, snap)
        reloaded = read_json(path)
        assert reloaded["activeLocationId"] == "preview_room_catalog_library"
        assert len(reloaded["locations"]) == 1

    def test_snapshot_path_is_project_root_relative(self, tmp_path: Path) -> None:
        """The path sent over protocol is relative to gameRoot."""
        project = _make_project(tmp_path)
        room = _make_room()
        snap = build_room_catalog_snapshot(project, room)
        snapshot_path = project.absolute_preview_snapshot_path
        snapshot_path.parent.mkdir(parents=True, exist_ok=True)
        write_preview_snapshot(snapshot_path, snap)

        # The protocol path should be relative to game root
        protocol_path = ".behemoth_tool/preview/current_snapshot.json"
        assert snapshot_path == project.game_root / protocol_path.replace("/", "\\")

        # File should exist
        assert snapshot_path.exists()
        data = read_json(snapshot_path)
        assert data["activeLocationId"] == "preview_room_catalog_library"

    def test_snapshot_no_background_image(self) -> None:
        """Room with no background produces empty string in snapshot."""
        project = _make_project(Path("/tmp/test"))
        room = RoomCatalogEntry(id="dark_room", name="Dark Room")
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["backgroundImage"] == ""

    def test_snapshot_no_sockets(self) -> None:
        """Room with no sockets produces empty list."""
        project = _make_project(Path("/tmp/test"))
        room = RoomCatalogEntry(id="empty_room", name="Empty Room")
        snap = build_room_catalog_snapshot(project, room)
        loc = snap["locations"][0]
        assert loc["sockets"] == []