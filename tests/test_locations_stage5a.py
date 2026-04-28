"""Tests for Stage 5A: locations, factory, exits, graph, validation, preview snapshot."""
from pathlib import Path

from behemoth_location_tool.io.location_factory import (
    DEFAULT_BACK_EXIT_ENTITY_ID,
    add_graph_node_for_location,
    create_location_from_room,
)
from behemoth_location_tool.io.json_io import read_json
from behemoth_location_tool.model.common import Conditions, DesignSize, Rect
from behemoth_location_tool.model.location import (
    ExitDefinition, GraphNode, LocationGraph, LocationInstance, LocationsFile, PlacedEntity,
)
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import LayerConfig, RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.preview.snapshot import build_location_snapshot, write_preview_snapshot
from behemoth_location_tool.validation.validator import validate_locations


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
            SocketDefinition(id="sock_1", name="Left Wall", x=200, y=500),
            SocketDefinition(id="sock_2", name="Center", x=960, y=540),
        ],
    )


def _make_project() -> ProjectConfig:
    p = ProjectConfig()
    p.game_root = Path("/tmp/game")
    p.image_root = Path("/tmp/game/data/images")
    return p


# ---- Factory tests ----


class TestCreateLocationFromRoom:
    def test_creates_location_with_inherited_sockets(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert not loc.socket_overridden
        assert loc.sockets == []
        # Effective sockets come from catalog via get_effective_sockets
        from behemoth_location_tool.model.location import get_effective_sockets
        from behemoth_location_tool.model.room import RoomCatalog
        catalog = RoomCatalog(rooms=[room])
        effective = get_effective_sockets(loc, catalog)
        assert len(effective) == 2
        assert effective[0].id == "sock_1"
        assert effective[1].id == "sock_2"

    def test_inherited_sockets_reflect_catalog_changes(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        from behemoth_location_tool.model.location import get_effective_sockets
        from behemoth_location_tool.model.room import RoomCatalog
        catalog = RoomCatalog(rooms=[room])
        # Modify the room socket; effective sockets should reflect the change
        room.sockets[0].x = 9999
        effective = get_effective_sockets(loc, catalog)
        assert effective[0].x == 9999

    def test_copies_background_image(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert loc.background_image == "rooms/library_bg.png"

    def test_copies_design_size(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert loc.design_size.w == 1920
        assert loc.design_size.h == 1080

    def test_copies_tags(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert loc.tags == ["indoor", "ground_floor"]

    def test_custom_layers_copied(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert loc.layers == ["bg", "characters", "fg"]

    def test_catalog_room_id_set(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert loc.catalog_room_id == "library"

    def test_start_location_has_no_default_back_exit(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert len(loc.exits) == 0

    def test_non_start_location_gets_default_back_exit(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=False, start_location_id="hall")
        assert len(loc.exits) == 1
        ex = loc.exits[0]
        assert ex.entity_id == DEFAULT_BACK_EXIT_ENTITY_ID
        assert ex.socket_id
        assert "exit.default_back" in ex.tags
        assert ex.target_location_id == "hall"
        assert ex.layer == "exit_behind"
        assert any(sock.id == ex.socket_id for sock in loc.sockets)

    def test_non_start_location_validates_cleanly_when_exit_entity_exists(self) -> None:
        from behemoth_location_tool.model.entity import EntityDefinition
        from behemoth_location_tool.model.room import RoomCatalog

        hall_room = RoomCatalogEntry(
            id="hall",
            name="Hall",
            layers=LayerConfig(mode="custom", order=["background", "exit_behind", "exit_front", "characters"]),
            sockets=[SocketDefinition(id="sock_hall", name="Hall Exit", x=400, y=900, layer="exit_front")],
        )
        library_room = RoomCatalogEntry(
            id="library",
            name="Library",
            layers=LayerConfig(mode="custom", order=["background", "exit_behind", "exit_front", "characters"]),
            sockets=[SocketDefinition(id="sock_lib", name="Library Exit", x=1200, y=900, layer="exit_front")],
        )
        catalog = RoomCatalog(rooms=[hall_room, library_room])

        start = create_location_from_room(hall_room, is_start=True)
        non_start = create_location_from_room(library_room, is_start=False, start_location_id=start.id)
        start.exits.append(
            ExitDefinition(
                id="exit_hall_to_library",
                entity_id=DEFAULT_BACK_EXIT_ENTITY_ID,
                target_location_id=non_start.id,
                socket_id="sock_hall",
                layer="exit_front",
                tags=["exit.door"],
            )
        )

        locations_file = LocationsFile(
            start_location=start.id,
            locations=[start, non_start],
        )
        entities = [
            EntityDefinition(
                id=DEFAULT_BACK_EXIT_ENTITY_ID,
                kind="exit",
                name="Default Back Exit",
                description="A default back exit entity.",
                tags=["exit.door"],
            )
        ]
        report = validate_locations(locations_file, catalog=catalog, entities=entities)
        errors = [diag for diag in report.diagnostics if diag.severity.value == "error"]
        assert errors == [], [diag.message for diag in errors]

    def test_custom_location_id(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, location_id="my_custom_id", is_start=True)
        assert loc.id == "my_custom_id"

    def test_placed_entities_empty(self) -> None:
        room = _make_room()
        loc = create_location_from_room(room, is_start=True)
        assert loc.placed_entities == []


# ---- Graph node tests ----


class TestGraphNode:
    def test_add_graph_node_creates_node(self) -> None:
        lf = LocationsFile(start_location="loc_1", locations=[
            LocationInstance(id="loc_1", catalog_room_id="room_1", name="Loc 1"),
        ])
        add_graph_node_for_location(lf, "loc_1")
        assert len(lf.graph.nodes) == 1
        assert lf.graph.nodes[0].location_id == "loc_1"

    def test_add_graph_node_no_duplicate(self) -> None:
        lf = LocationsFile(start_location="loc_1", graph=LocationGraph(nodes=[
            GraphNode(location_id="loc_1", x=100, y=200),
        ]), locations=[
            LocationInstance(id="loc_1", catalog_room_id="room_1", name="Loc 1"),
        ])
        add_graph_node_for_location(lf, "loc_1")
        assert len(lf.graph.nodes) == 1

    def test_add_graph_node_offsets_from_last(self) -> None:
        lf = LocationsFile(start_location="loc_1", graph=LocationGraph(nodes=[
            GraphNode(location_id="loc_1", x=100, y=200),
        ]), locations=[
            LocationInstance(id="loc_1", catalog_room_id="room_1", name="Loc 1"),
            LocationInstance(id="loc_2", catalog_room_id="room_2", name="Loc 2"),
        ])
        add_graph_node_for_location(lf, "loc_2")
        assert len(lf.graph.nodes) == 2
        assert lf.graph.nodes[1].x == 350  # 100 + 250
        assert lf.graph.nodes[1].y == 200

    def test_graph_node_save_load_roundtrip(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.locations_loader import load_locations, save_locations
        lf = LocationsFile(
            start_location="loc_1",
            graph=LocationGraph(nodes=[
                GraphNode(location_id="loc_1", x=100, y=200),
                GraphNode(location_id="loc_2", x=350, y=200),
            ]),
            locations=[
                LocationInstance(id="loc_1", catalog_room_id="room_1", name="Loc 1",
                                 exits=[ExitDefinition(id="ex_1", entity_id="door",
                                  target_location_id="loc_2", socket_id="", tags=["exit.default_back"])]),
                LocationInstance(id="loc_2", catalog_room_id="room_2", name="Loc 2",
                                 exits=[ExitDefinition(id="ex_2", entity_id="door",
                                  target_location_id="loc_1", socket_id="", tags=["exit.default_back"])]),
            ],
        )
        path = tmp_path / "locations.json"
        save_locations(path, lf)
        reloaded = load_locations(path)
        assert len(reloaded.graph.nodes) == 2
        assert reloaded.graph.nodes[0].location_id == "loc_1"
        assert reloaded.graph.nodes[0].x == 100
        assert reloaded.graph.nodes[1].location_id == "loc_2"
        assert reloaded.graph.nodes[1].x == 350


# ---- Validation tests ----


class TestLocationValidation:
    def _make_valid_locations_file(self) -> LocationsFile:
        """Two locations with reciprocal exits and default back exits."""
        return LocationsFile(
            start_location="hall",
            graph=LocationGraph(nodes=[
                GraphNode(location_id="hall", x=100, y=200),
                GraphNode(location_id="library", x=350, y=200),
            ]),
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="room_1", name="Hall",
                    exits=[
                        ExitDefinition(id="ex_hall_lib", entity_id="door",
                                       target_location_id="library", socket_id="sock_exit_north",
                                       tags=["exit.default_back"]),
                    ],
                ),
                LocationInstance(
                    id="library", catalog_room_id="room_2", name="Library",
                    exits=[
                        ExitDefinition(id="ex_lib_hall", entity_id="door",
                                       target_location_id="hall", socket_id="sock_exit_south",
                                       tags=["exit.default_back"]),
                    ],
                ),
            ],
        )

    def test_valid_locations_no_errors(self) -> None:
        from behemoth_location_tool.model.entity import EntityDefinition
        from behemoth_location_tool.model.room import RoomCatalog
        lf = self._make_valid_locations_file()
        catalog = RoomCatalog(rooms=[
            RoomCatalogEntry(id="room_1", name="Room 1",
                             sockets=[SocketDefinition(id="sock_exit_north", name="North Exit")]),
            RoomCatalogEntry(id="room_2", name="Room 2",
                             sockets=[SocketDefinition(id="sock_exit_south", name="South Exit")]),
        ])
        entities = [EntityDefinition(id="door", kind="item", name="Door")]
        report = validate_locations(lf, catalog=catalog, entities=entities)
        errors = [d for d in report.diagnostics if d.severity.value == "error"]
        assert len(errors) == 0

    def test_missing_start_location(self) -> None:
        lf = self._make_valid_locations_file()
        lf.start_location = "nonexistent"
        report = validate_locations(lf)
        assert any(d.code == "missing_start_location" for d in report.diagnostics)

    def test_duplicate_location_ids(self) -> None:
        lf = LocationsFile(
            start_location="loc_1",
            locations=[
                LocationInstance(id="loc_1", catalog_room_id="r1", name="Loc 1",
                                 exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="loc_2", socket_id="", tags=["exit.default_back"])]),
                LocationInstance(id="loc_1", catalog_room_id="r2", name="Loc 1 Dup",
                                 exits=[ExitDefinition(id="ex2", entity_id="", target_location_id="loc_1", socket_id="", tags=["exit.default_back"])]),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_id" for d in report.diagnostics)

    def test_non_start_missing_default_back_exit(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[]),
                LocationInstance(id="kitchen", catalog_room_id="r2", name="Kitchen",
                                 exits=[]),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "missing_default_back_exit" for d in report.diagnostics)

    def test_start_location_can_omit_default_back_exit(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[]),
            ],
        )
        report = validate_locations(lf)
        # No missing_default_back_exit for the start location
        back_exit_errors = [d for d in report.diagnostics if d.code == "missing_default_back_exit"]
        assert len(back_exit_errors) == 0

    def test_exit_target_missing(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="nonexistent", socket_id="", tags=["exit.default_back"])]),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "missing_target_location" for d in report.diagnostics)

    def test_exit_socket_not_found_in_location(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 sockets=[SocketDefinition(id="sock_1", name="S1")],
                                 exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="hall", socket_id="nonexistent_sock", tags=["exit.default_back"])]),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "missing_socket_ref" for d in report.diagnostics)

    def test_missing_reciprocal_exit(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="kitchen", socket_id="", tags=["exit.default_back"])]),
                LocationInstance(id="kitchen", catalog_room_id="r2", name="Kitchen",
                                 exits=[ExitDefinition(id="ex2", entity_id="", target_location_id="hall", socket_id="", tags=["exit.default_back"]),
                                        ExitDefinition(id="ex3", entity_id="", target_location_id="pantry", socket_id="")]),
                LocationInstance(id="pantry", catalog_room_id="r3", name="Pantry",
                                 exits=[ExitDefinition(id="ex4", entity_id="", target_location_id="kitchen", socket_id="", tags=["exit.default_back"])]),
            ],
        )
        # pantry links to hall (not kitchen), so kitchen→pantry lacks reciprocal
        lf.locations[2].exits = [
            ExitDefinition(id="ex5", entity_id="", target_location_id="hall", socket_id="", tags=["exit.default_back"]),
        ]
        report = validate_locations(lf)
        assert any(d.code == "missing_reciprocal_exit" for d in report.diagnostics)

    def test_unreachable_room(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[]),
                LocationInstance(id="island", catalog_room_id="r2", name="Island",
                                 exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="island", socket_id="", tags=["exit.default_back"])]),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "unreachable_location" for d in report.diagnostics)

    def test_missing_graph_node_warning(self) -> None:
        lf = self._make_valid_locations_file()
        lf.graph.nodes = [lf.graph.nodes[0]]  # Remove one node
        report = validate_locations(lf)
        assert any(d.code == "missing_graph_node" for d in report.diagnostics)

    def test_orphan_graph_node_warning(self) -> None:
        lf = self._make_valid_locations_file()
        lf.graph.nodes.append(GraphNode(location_id="phantom", x=500, y=500))
        report = validate_locations(lf)
        assert any(d.code == "orphan_graph_node" for d in report.diagnostics)

    def test_exit_invalid_layer(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="hall", socket_id="", layer="nonexistent_layer", tags=["exit.default_back"])]),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "invalid_layer_ref" for d in report.diagnostics)

    def test_exit_invalid_tag_not_in_project_layers(self) -> None:
        """Tags themselves aren't validated against project layers; layers are."""
        pass  # Tags are free-form strings, only layer references are validated

    def test_exit_entity_id_missing(self) -> None:
        """Entity ID referencing is validated when entities list is provided."""
        from behemoth_location_tool.model.entity import EntityDefinition
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall",
                                 exits=[ExitDefinition(id="ex1", entity_id="ghost_entity", target_location_id="hall", socket_id="", tags=["exit.default_back"])]),
            ],
        )
        entities = [EntityDefinition(id="skeleton", kind="item", name="Skeleton")]
        report = validate_locations(lf, entities=entities)
        assert any(d.code == "missing_entity_ref" for d in report.diagnostics)


# ---- Location preview snapshot tests ----


class TestLocationSnapshot:
    def test_snapshot_active_location_id(self) -> None:
        project = _make_project()
        loc = LocationInstance(id="hall", catalog_room_id="room_1", name="Hall")
        snap = build_location_snapshot(project, loc)
        assert snap["activeLocationId"] == "hall"

    def test_snapshot_includes_exits(self) -> None:
        project = _make_project()
        loc = LocationInstance(
            id="hall", catalog_room_id="room_1", name="Hall",
            exits=[
                ExitDefinition(
                    id="ex_1", entity_id="door", target_location_id="library",
                    socket_id="sock_1", layer="exit_front", tags=["exit.default_back"],
                    clickable_rect=Rect(x=100, y=200, w=300, h=400),
                    conditions=Conditions(requires_tags=["key_gold"], forbidden_tags=["locked"]),
                ),
            ],
        )
        snap = build_location_snapshot(project, loc)
        loc_data = snap["locations"][0]
        assert len(loc_data["exits"]) == 1
        ex = loc_data["exits"][0]
        assert ex["id"] == "ex_1"
        assert ex["targetLocationId"] == "library"
        assert ex["clickableRect"]["x"] == 100
        assert ex["clickableRect"]["w"] == 300
        assert ex["conditions"]["requiresTags"] == ["key_gold"]
        assert ex["conditions"]["forbiddenTags"] == ["locked"]

    def test_snapshot_includes_placed_entities(self) -> None:
        project = _make_project()
        loc = LocationInstance(
            id="hall", catalog_room_id="room_1", name="Hall",
            placed_entities=[
                PlacedEntity(instanceId="pe_1", entityId="ghost", socketId="sock_1", layer="characters", sortOrder=5),
            ],
        )
        snap = build_location_snapshot(project, loc)
        pe_list = snap["locations"][0]["placedEntities"]
        assert len(pe_list) == 1
        assert pe_list[0]["instanceId"] == "pe_1"
        assert pe_list[0]["entityId"] == "ghost"
        assert pe_list[0]["sortOrder"] == 5

    def test_snapshot_includes_sockets(self) -> None:
        project = _make_project()
        loc = LocationInstance(
            id="hall", catalog_room_id="room_1", name="Hall",
            sockets=[SocketDefinition(id="s1", name="Socket 1", x=100, y=200)],
        )
        snap = build_location_snapshot(project, loc)
        sockets = snap["locations"][0]["sockets"]
        assert len(sockets) == 1
        assert sockets[0]["id"] == "s1"
        assert sockets[0]["x"] == 100

    def test_snapshot_write_and_reload(self, tmp_path: Path) -> None:
        project = _make_project()
        loc = LocationInstance(
            id="hall", catalog_room_id="room_1", name="Hall",
            background_image="rooms/hall.png",
            exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="hall", socket_id="", tags=["exit.default_back"])],
        )
        snap = build_location_snapshot(project, loc)
        path = tmp_path / "loc_snap.json"
        write_preview_snapshot(path, snap)
        reloaded = read_json(path)
        assert reloaded["activeLocationId"] == "hall"
        assert len(reloaded["locations"][0]["exits"]) == 1

    def test_snapshot_custom_layers(self) -> None:
        project = _make_project()
        loc = LocationInstance(
            id="hall", catalog_room_id="room_1", name="Hall",
            layers=["bg", "characters", "fg"],
        )
        snap = build_location_snapshot(project, loc)
        layers = snap["locations"][0]["layers"]
        assert layers["mode"] == "custom"
        assert layers["order"] == ["bg", "characters", "fg"]

    def test_snapshot_no_exits(self) -> None:
        project = _make_project()
        loc = LocationInstance(id="hall", catalog_room_id="room_1", name="Hall")
        snap = build_location_snapshot(project, loc)
        assert snap["locations"][0]["exits"] == []

    def test_snapshot_exit_without_clickable_rect(self) -> None:
        project = _make_project()
        loc = LocationInstance(
            id="hall", catalog_room_id="room_1", name="Hall",
            exits=[ExitDefinition(id="ex1", entity_id="", target_location_id="hall", socket_id="")],
        )
        snap = build_location_snapshot(project, loc)
        ex = snap["locations"][0]["exits"][0]
        assert "clickableRect" not in ex
