from behemoth_location_tool.model.entity import EntityDefinition, EntityRenderData
from behemoth_location_tool.model.location import (
    ExitDefinition, LocationInstance, LocationsFile, PlacedEntity,
)
from behemoth_location_tool.model.room import (
    AmbientRule, DesignSize, LayerConfig, RoomCatalog, RoomCatalogEntry,
    SocketDefinition, WeightedEntityEntry, WeightedFillEntry,
)
from behemoth_location_tool.validation.diagnostics import Severity
from behemoth_location_tool.validation.validator import (
    validate_entities, validate_locations, validate_room_catalog, validate_unique_ids,
)


def test_duplicate_ids_are_errors() -> None:
    report = validate_unique_ids(["a", "b", "a"], label="entity")
    assert report.has_errors
    assert report.diagnostics[0].code == "duplicate_id"  # default code


def test_unique_ids_no_errors() -> None:
    report = validate_unique_ids(["a", "b", "c"], label="entity")
    assert not report.has_errors


def test_validate_entities_duplicate_ids() -> None:
    entities = [
        EntityDefinition(id="lantern", kind="item", name="Lantern", tags=["entity.spawnable"]),
        EntityDefinition(id="lantern", kind="item", name="Lantern 2", tags=[]),
    ]
    report = validate_entities(entities)
    assert report.has_errors
    assert any(d.code == "duplicate_entity_id" for d in report.diagnostics)


def test_validate_entities_spawnable_no_render_warns() -> None:
    entities = [
        EntityDefinition(id="ghost", kind="item", name="Ghost", tags=["entity.spawnable"]),
    ]
    report = validate_entities(entities)
    assert not report.has_errors
    assert any(d.code == "spawnable_no_render" and d.severity == Severity.WARNING for d in report.diagnostics)


def test_validate_entities_interactable_no_rect_warns() -> None:
    entities = [
        EntityDefinition(
            id="key", kind="item", name="Key",
            tags=["item.pickable"],
            render=EntityRenderData(sprite="key.png", default_layer="front_props"),
        ),
    ]
    report = validate_entities(entities)
    assert any(d.code == "interactable_no_clickable_rect" for d in report.diagnostics)


def test_validate_room_catalog_duplicate_room_ids() -> None:
    catalog = RoomCatalog(rooms=[
        RoomCatalogEntry(id="room_a", name="Room A"),
        RoomCatalogEntry(id="room_a", name="Room A Copy"),
    ])
    report = validate_room_catalog(catalog)
    assert report.has_errors


def test_validate_room_catalog_no_sockets_warns() -> None:
    catalog = RoomCatalog(rooms=[RoomCatalogEntry(id="r1", name="R1")])
    report = validate_room_catalog(catalog)
    assert any(d.code == "room_no_sockets" for d in report.diagnostics)


def test_validate_locations_missing_start() -> None:
    lf = LocationsFile(start_location="missing", locations=[])
    report = validate_locations(lf)
    assert any(d.code == "missing_start_location" for d in report.diagnostics)


def test_validate_locations_missing_default_back_exit() -> None:
    lf = LocationsFile(
        start_location="start",
        locations=[
            LocationInstance(id="start", catalog_room_id="cat", name="Start",
                             exits=[ExitDefinition(id="e1", entity_id="exit_door",
                                                   target_location_id="room_b", socket_id="s1",
                                                   tags=["exit.default_back"])]),
            LocationInstance(id="room_b", catalog_room_id="cat", name="Room B"),
        ],
    )
    report = validate_locations(lf)
    assert any(d.code == "missing_default_back_exit" for d in report.diagnostics)


def test_validate_locations_missing_reciprocal_exit() -> None:
    lf = LocationsFile(
        start_location="a",
        locations=[
            LocationInstance(id="a", catalog_room_id="c", name="A",
                             exits=[ExitDefinition(id="e1", entity_id="door",
                                                   target_location_id="b", socket_id="s1",
                                                   tags=["exit.default_back"])]),
            LocationInstance(id="b", catalog_room_id="c", name="B",
                             exits=[ExitDefinition(id="e2", entity_id="door",
                                                   target_location_id="a", socket_id="s1",
                                                   tags=["exit.default_back"])]),
        ],
    )
    report = validate_locations(lf)
    assert not any(d.code == "missing_reciprocal_exit" for d in report.diagnostics)


# ---- Ambient rule validation tests ----

def _make_catalog_with_socket(sock: SocketDefinition) -> RoomCatalog:
    return RoomCatalog(rooms=[
        RoomCatalogEntry(
            id="room1", name="Room 1",
            background_image="bg.png",
            sockets=[sock],
        ),
    ])


def test_ambient_chance_gt_zero_but_mode_none_warns() -> None:
    sock = SocketDefinition(id="s1", name="S1", ambient_spawn_chance=50,
                            ambient_rule=AmbientRule(mode="none"))
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog)
    assert any(d.code == "ambient_chance_but_no_rule" for d in report.diagnostics)


def test_ambient_rule_configured_but_chance_zero_warns() -> None:
    sock = SocketDefinition(id="s1", name="S1", ambient_spawn_chance=0,
                            ambient_rule=AmbientRule(mode="tag_query", required_tags=["npc"]))
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog)
    assert any(d.code == "ambient_rule_no_chance" for d in report.diagnostics)


def test_ambient_weighted_entity_list_not_100() -> None:
    # Use model_construct to bypass Pydantic model-level validation
    # so we can test the validator-level check
    rule = AmbientRule.model_construct(
        mode="weighted_entity_list",
        entries=[
            WeightedEntityEntry(entity_id="e1", weight=30),
            WeightedEntityEntry(entity_id="e2", weight=30),
        ],
        fill_entries=[], required_tags=[], forbidden_tags=[],
    )
    sock = SocketDefinition.model_construct(
        id="s1", name="S1", ambient_spawn_chance=50, ambient_rule=rule,
        description="", x=0, y=0, rotation=0.0, scale=1.0,
        pivot_mode="center", layer="", sort_order=0,
        required_tags=[], forbidden_tags=[],
    )
    room = RoomCatalogEntry.model_construct(
        id="room1", name="Room 1", background_image="bg.png",
        sockets=[sock], description="", tags=[], layers=LayerConfig(mode="project_default"),
        design_size=DesignSize(),
    )
    catalog = RoomCatalog(rooms=[room])
    report = validate_room_catalog(catalog)
    assert any(d.code == "weighted_list_not_100" for d in report.diagnostics)


def test_ambient_weighted_entity_list_valid() -> None:
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=50,
        ambient_rule=AmbientRule(
            mode="weighted_entity_list",
            entries=[
                WeightedEntityEntry(entity_id="e1", weight=50),
                WeightedEntityEntry(entity_id="e2", weight=50),
            ],
        ),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog)
    assert not any(d.code == "weighted_list_not_100" for d in report.diagnostics)


def test_ambient_weighted_entity_list_unknown_entity() -> None:
    entities = [EntityDefinition(id="e1", kind="item", name="E1", tags=[])]
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=50,
        ambient_rule=AmbientRule(
            mode="weighted_entity_list",
            entries=[
                WeightedEntityEntry(entity_id="e1", weight=50),
                WeightedEntityEntry(entity_id="unknown_entity", weight=50),
            ],
        ),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog, entities=entities)
    assert any(d.code == "ambient_entity_id_missing" for d in report.diagnostics)


def test_ambient_tag_query_no_tags_warns() -> None:
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=50,
        ambient_rule=AmbientRule(mode="tag_query"),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog)
    assert any(d.code == "tag_query_no_tags" for d in report.diagnostics)


def test_ambient_tag_query_zero_matching_entities() -> None:
    entities = [EntityDefinition(id="e1", kind="item", name="E1", tags=["entity.spawnable"])]
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=50,
        ambient_rule=AmbientRule(mode="tag_query", required_tags=["nonexistent_tag"]),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog, entities=entities)
    assert any(d.code == "tag_query_zero_matches" for d in report.diagnostics)


def test_ambient_weighted_entries_not_100() -> None:
    # Use model_construct to bypass Pydantic model-level validation
    rule = AmbientRule.model_construct(
        mode="weighted_entries",
        fill_entries=[
            WeightedFillEntry(type="entity", entity_id="e1", weight=30),
            WeightedFillEntry(type="entity", entity_id="e2", weight=30),
        ],
        entries=[], required_tags=[], forbidden_tags=[],
    )
    sock = SocketDefinition.model_construct(
        id="s1", name="S1", ambient_spawn_chance=50, ambient_rule=rule,
        description="", x=0, y=0, rotation=0.0, scale=1.0,
        pivot_mode="center", layer="", sort_order=0,
        required_tags=[], forbidden_tags=[],
    )
    room = RoomCatalogEntry.model_construct(
        id="room1", name="Room 1", background_image="bg.png",
        sockets=[sock], description="", tags=[], layers=LayerConfig(mode="project_default"),
        design_size=DesignSize(),
    )
    catalog = RoomCatalog(rooms=[room])
    report = validate_room_catalog(catalog)
    assert any(d.code == "weighted_entries_not_100" for d in report.diagnostics)


def test_ambient_weighted_entries_valid() -> None:
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=50,
        ambient_rule=AmbientRule(
            mode="weighted_entries",
            fill_entries=[
                WeightedFillEntry(type="entity", entity_id="e1", weight=50),
                WeightedFillEntry(type="tag_query", required_tags=["npc"], weight=50),
            ],
        ),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog)
    assert not any(d.code == "weighted_entries_not_100" for d in report.diagnostics)


def test_ambient_weighted_entries_unknown_entity() -> None:
    entities = [EntityDefinition(id="e1", kind="item", name="E1", tags=[])]
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=50,
        ambient_rule=AmbientRule(
            mode="weighted_entries",
            fill_entries=[
                WeightedFillEntry(type="entity", entity_id="e1", weight=50),
                WeightedFillEntry(type="entity", entity_id="missing", weight=50),
            ],
        ),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog, entities=entities)
    assert any(d.code == "ambient_entity_id_missing" for d in report.diagnostics)


def test_ambient_none_mode_no_warnings_when_clean() -> None:
    sock = SocketDefinition(
        id="s1", name="S1", ambient_spawn_chance=0,
        ambient_rule=AmbientRule(mode="none"),
    )
    catalog = _make_catalog_with_socket(sock)
    report = validate_room_catalog(catalog)
    ambient_codes = {"ambient_chance_but_no_rule", "ambient_rule_no_chance"}
    assert not any(d.code in ambient_codes for d in report.diagnostics)
