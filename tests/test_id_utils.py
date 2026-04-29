"""Tests for unified scoped ID generation and scoped duplicate validation."""
from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.id_utils import generate_id, generate_padded_id, normalize_id
from behemoth_location_tool.model.location import (
    ExitDefinition,
    LocationInstance,
    LocationsFile,
    PlacedEntity,
)
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.validation.validator import (
    validate_entities,
    validate_locations,
    validate_room_catalog,
    validate_unique_ids,
)

# ── normalize_id ─────────────────────────────────────────────────────────────


class TestNormalizeId:
    def test_lowercase(self) -> None:
        assert normalize_id("HelloWorld") == "helloworld"

    def test_spaces_to_underscores(self) -> None:
        assert normalize_id("Entrance Hall") == "entrance_hall"

    def test_hyphens_to_underscores(self) -> None:
        assert normalize_id("my-cool-room") == "my_cool_room"

    def test_strip_special_chars(self) -> None:
        assert normalize_id("Room #1 (Main!)") == "room_1_main"

    def test_collapse_repeated_underscores(self) -> None:
        assert normalize_id("a---b   c") == "a_b_c"

    def test_trim_leading_trailing_underscores(self) -> None:
        assert normalize_id("--hello world--") == "hello_world"

    def test_empty_string_uses_fallback(self) -> None:
        assert normalize_id("") == "object"

    def test_custom_fallback(self) -> None:
        assert normalize_id("", fallback="entity") == "entity"

    def test_only_special_chars_uses_fallback(self) -> None:
        assert normalize_id("###!!!") == "object"

    def test_mixed_case_preserved_as_lower(self) -> None:
        assert normalize_id("MyRoomID") == "myroomid"


# ── generate_id ──────────────────────────────────────────────────────────────


class TestGenerateId:
    def test_simple_no_collision(self) -> None:
        result = generate_id("entrance_hall", existing_ids=set())
        assert result == "entrance_hall"

    def test_collision_appends_suffix(self) -> None:
        result = generate_id("entrance_hall", existing_ids={"entrance_hall"})
        assert result == "entrance_hall_2"

    def test_collision_increments(self) -> None:
        result = generate_id("entrance_hall", existing_ids={"entrance_hall", "entrance_hall_2"})
        assert result == "entrance_hall_3"

    def test_collision_skips_used(self) -> None:
        result = generate_id(
            "entrance_hall",
            existing_ids={"entrance_hall", "entrance_hall_2", "entrance_hall_3"},
        )
        assert result == "entrance_hall_4"

    def test_with_prefix(self) -> None:
        result = generate_id("entrance_hall", existing_ids=set(), prefix="catalog")
        assert result == "catalog.entrance_hall"

    def test_with_prefix_collision(self) -> None:
        result = generate_id("entrance_hall", existing_ids={"catalog.entrance_hall"}, prefix="catalog")
        assert result == "catalog.entrance_hall_2"

    def test_list_input(self) -> None:
        result = generate_id("room", existing_ids=["room", "room_2"])
        assert result == "room_3"

    def test_fallback_used_for_empty_display_name(self) -> None:
        result = generate_id("", existing_ids=set(), fallback="entity")
        assert result == "entity"

    def test_fallback_collision(self) -> None:
        result = generate_id("", existing_ids={"entity"}, fallback="entity")
        assert result == "entity_2"


# ── generate_padded_id ───────────────────────────────────────────────────────


class TestGeneratePaddedId:
    def test_simple_no_collision(self) -> None:
        result = generate_padded_id("entrance_hall", existing_ids=set())
        assert result == "entrance_hall"

    def test_collision_padded_suffix(self) -> None:
        result = generate_padded_id("entrance_hall", existing_ids={"entrance_hall"})
        assert result == "entrance_hall_02"

    def test_collision_increments_padded(self) -> None:
        result = generate_padded_id("entrance_hall", existing_ids={"entrance_hall", "entrance_hall_02"})
        assert result == "entrance_hall_03"

    def test_with_prefix(self) -> None:
        result = generate_padded_id("hall", existing_ids=set(), prefix="loc")
        assert result == "loc.hall"

    def test_custom_width(self) -> None:
        result = generate_padded_id("hall", existing_ids={"hall"}, width=3)
        assert result == "hall_002"


# ── Scoped duplicate validation ──────────────────────────────────────────────


class TestScopedDuplicateValidation:
    """Verify that duplicate IDs are only errors within their owning scope."""

    def test_duplicate_entity_id(self) -> None:
        entities = [
            EntityDefinition(id="lantern", kind="item", name="Lantern"),
            EntityDefinition(id="lantern", kind="item", name="Lantern 2"),
        ]
        report = validate_entities(entities)
        assert any(d.code == "duplicate_entity_id" for d in report.diagnostics)

    def test_duplicate_room_catalog_id(self) -> None:
        catalog = RoomCatalog(rooms=[
            RoomCatalogEntry(id="hall", name="Hall"),
            RoomCatalogEntry(id="hall", name="Hall Copy"),
        ])
        report = validate_room_catalog(catalog)
        assert any(d.code == "duplicate_room_catalog_id" for d in report.diagnostics)

    def test_duplicate_catalog_socket_template_id_same_room(self) -> None:
        """Duplicate socket template IDs within the SAME room entry are errors."""
        catalog = RoomCatalog(rooms=[
            RoomCatalogEntry(
                id="hall", name="Hall",
                sockets=[
                    SocketDefinition(id="spawn_1", name="Spawn 1"),
                    SocketDefinition(id="spawn_1", name="Spawn 1 Dup"),
                ],
            ),
        ])
        report = validate_room_catalog(catalog)
        assert any(d.code == "duplicate_catalog_socket_template_id" for d in report.diagnostics)

    def test_same_socket_id_different_rooms_allowed(self) -> None:
        """The same socket ID in DIFFERENT room entries is allowed (scoped)."""
        catalog = RoomCatalog(rooms=[
            RoomCatalogEntry(
                id="hall", name="Hall",
                sockets=[SocketDefinition(id="spawn_1", name="Spawn 1")],
            ),
            RoomCatalogEntry(
                id="kitchen", name="Kitchen",
                sockets=[SocketDefinition(id="spawn_1", name="Spawn 1")],
            ),
        ])
        report = validate_room_catalog(catalog)
        assert not any("duplicate" in d.code for d in report.diagnostics)

    def test_duplicate_location_id(self) -> None:
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(id="hall", catalog_room_id="r1", name="Hall"),
                LocationInstance(id="hall", catalog_room_id="r2", name="Hall Dup"),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_id" for d in report.diagnostics)

    def test_duplicate_location_socket_id_same_location(self) -> None:
        """Duplicate socket IDs within the SAME location are errors."""
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="r1", name="Hall",
                    sockets=[
                        SocketDefinition(id="s1", name="Socket 1"),
                        SocketDefinition(id="s1", name="Socket 1 Dup"),
                    ],
                ),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_socket_id" for d in report.diagnostics)

    def test_same_socket_id_different_locations_allowed(self) -> None:
        """The same socket ID in DIFFERENT locations is allowed (scoped)."""
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="r1", name="Hall",
                    sockets=[SocketDefinition(id="s1", name="Socket 1")],
                ),
                LocationInstance(
                    id="kitchen", catalog_room_id="r2", name="Kitchen",
                    sockets=[SocketDefinition(id="s1", name="Socket 1")],
                ),
            ],
        )
        report = validate_locations(lf)
        assert not any(d.code == "duplicate_location_socket_id" for d in report.diagnostics)

    def test_duplicate_location_exit_id_same_location(self) -> None:
        """Duplicate exit IDs within the SAME location are errors."""
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="r1", name="Hall",
                    exits=[
                        ExitDefinition(
                            id="exit_1",
                            entity_id="",
                            target_location_id="hall",
                            socket_id="",
                            tags=["exit.default_back"],
                        ),
                        ExitDefinition(id="exit_1", entity_id="", target_location_id="hall", socket_id=""),
                    ],
                ),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_exit_id" for d in report.diagnostics)

    def test_same_exit_id_different_locations_allowed(self) -> None:
        """The same exit ID in DIFFERENT locations is allowed (scoped)."""
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="r1", name="Hall",
                    exits=[
                        ExitDefinition(
                            id="exit_1",
                            entity_id="",
                            target_location_id="kitchen",
                            socket_id="",
                            tags=["exit.default_back"],
                        )
                    ],
                ),
                LocationInstance(
                    id="kitchen", catalog_room_id="r2", name="Kitchen",
                    exits=[
                        ExitDefinition(
                            id="exit_1",
                            entity_id="",
                            target_location_id="hall",
                            socket_id="",
                            tags=["exit.default_back"],
                        )
                    ],
                ),
            ],
        )
        report = validate_locations(lf)
        assert not any(d.code == "duplicate_location_exit_id" for d in report.diagnostics)

    def test_duplicate_placed_entity_id_same_location(self) -> None:
        """Duplicate placed entity instance IDs within the SAME location are errors."""
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="r1", name="Hall",
                    placed_entities=[
                        PlacedEntity(instanceId="pe_1", entityId="ghost", socketId="s1"),
                        PlacedEntity(instanceId="pe_1", entityId="skeleton", socketId="s1"),
                    ],
                ),
            ],
        )
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_placed_entity_id" for d in report.diagnostics)

    def test_same_placed_entity_id_different_locations_allowed(self) -> None:
        """The same placed entity instance ID in DIFFERENT locations is allowed (scoped)."""
        lf = LocationsFile(
            start_location="hall",
            locations=[
                LocationInstance(
                    id="hall", catalog_room_id="r1", name="Hall",
                    placed_entities=[PlacedEntity(instanceId="pe_1", entityId="ghost", socketId="s1")],
                ),
                LocationInstance(
                    id="kitchen", catalog_room_id="r2", name="Kitchen",
                    placed_entities=[PlacedEntity(instanceId="pe_1", entityId="ghost", socketId="s1")],
                ),
            ],
        )
        report = validate_locations(lf)
        assert not any(d.code == "duplicate_location_placed_entity_id" for d in report.diagnostics)

    def test_validate_unique_ids_custom_code(self) -> None:
        """validate_unique_ids supports a custom diagnostic code."""
        report = validate_unique_ids(["a", "a"], label="test", code="custom_duplicate")
        assert report.diagnostics[0].code == "custom_duplicate"
