"""Roundtrip tests: build model → save JSON → reload → compare."""
from pathlib import Path

from behemoth_location_tool.io.entity_loader import load_entity_module, save_entity_module
from behemoth_location_tool.io.room_catalog_loader import load_room_catalog, save_room_catalog
from behemoth_location_tool.model.common import DesignSize, PivotMode, Rect, SavePolicy
from behemoth_location_tool.model.entity import (
    EntityDefinition,
    EntityModule,
    EntityRenderData,
    EntitySpawnRules,
)
from behemoth_location_tool.model.room import (
    LayerConfig,
    RoomCatalog,
    RoomCatalogEntry,
    SocketDefinition,
)

# ── Entity roundtrip ──────────────────────────────────────────────────────────


def test_entity_module_roundtrip_minimal(tmp_path: Path) -> None:
    """Save and reload an entity module with minimal fields."""
    module = EntityModule(entities=[
        EntityDefinition(id="candle", kind="prop", name="Candle"),
        EntityDefinition(id="ghost", kind="character", name="Ghost", tags=["spooky", "ambient"]),
    ])
    path = tmp_path / "entities.json"
    save_entity_module(path, module)
    reloaded = load_entity_module(path)
    assert len(reloaded.entities) == 2
    assert reloaded.entities[0].id == "candle"
    assert reloaded.entities[0].kind == "prop"
    assert reloaded.entities[1].tags == ["spooky", "ambient"]


def test_entity_module_roundtrip_full_render(tmp_path: Path) -> None:
    """Entity with render data (sprite, clickable rect, pivot) roundtrips."""
    module = EntityModule(entities=[
        EntityDefinition(
            id="painting", kind="interactable", name="Painting",
            render=EntityRenderData(
                sprite="assets/images/painting.png",
                default_layer="characters",
                clickable_rect=Rect(x=10, y=20, w=100, h=150),
            ),
        ),
    ])
    path = tmp_path / "entities.json"
    save_entity_module(path, module)
    reloaded = load_entity_module(path)
    ent = reloaded.entities[0]
    assert ent.render is not None
    assert ent.render.sprite == "assets/images/painting.png"
    assert ent.render.default_layer == "characters"
    assert ent.render.clickable_rect == Rect(x=10, y=20, w=100, h=150)


def test_entity_module_roundtrip_spawn_rules(tmp_path: Path) -> None:
    """Entity spawn rules roundtrip correctly."""
    module = EntityModule(entities=[
        EntityDefinition(
            id="key", kind="item", name="Key",
            spawn_rules=EntitySpawnRules(
                required_context_tags=["indoor"],
                forbidden_context_tags=["boss_room"],
                exclusive_groups=["keys"],
                save_policy=SavePolicy.PERSISTENT,
            ),
        ),
    ])
    path = tmp_path / "entities.json"
    save_entity_module(path, module)
    reloaded = load_entity_module(path)
    sr = reloaded.entities[0].spawn_rules
    assert sr.required_context_tags == ["indoor"]
    assert sr.forbidden_context_tags == ["boss_room"]
    assert sr.exclusive_groups == ["keys"]
    assert sr.save_policy == SavePolicy.PERSISTENT


def test_entity_module_roundtrip_multiple_entities(tmp_path: Path) -> None:
    """Multiple entities with mixed fields roundtrip."""
    module = EntityModule(entities=[
        EntityDefinition(
            id="chest", kind="container", name="Chest",
            tags=["interactable", "loot"],
            render=EntityRenderData(sprite="chest.png"),
            spawn_rules=EntitySpawnRules(save_policy=SavePolicy.REGENERATE_ON_NEW_GAME),
        ),
        EntityDefinition(
            id="door", kind="prop", name="Door",
            tags=["exit"],
            render=EntityRenderData(
                sprite="door.png",
                clickable_rect=Rect(x=0, y=0, w=80, h=200),
            ),
        ),
    ])
    path = tmp_path / "entities.json"
    save_entity_module(path, module)
    reloaded = load_entity_module(path)
    assert len(reloaded.entities) == 2
    assert reloaded.entities[0].tags == ["interactable", "loot"]
    assert reloaded.entities[1].render.clickable_rect.w == 80


# ── Room Catalog roundtrip ────────────────────────────────────────────────────


def test_room_catalog_roundtrip_minimal(tmp_path: Path) -> None:
    """Minimal room catalog save/load roundtrip."""
    catalog = RoomCatalog(rooms=[
        RoomCatalogEntry(id="hall", name="Grand Hall"),
        RoomCatalogEntry(id="kitchen", name="Kitchen", tags=["ground_floor"]),
    ])
    path = tmp_path / "room_catalog.json"
    save_room_catalog(path, catalog)
    reloaded = load_room_catalog(path)
    assert len(reloaded.rooms) == 2
    assert reloaded.rooms[0].id == "hall"
    assert reloaded.rooms[1].tags == ["ground_floor"]


def test_room_catalog_roundtrip_full_room(tmp_path: Path) -> None:
    """Room with background, design size, tags, layers roundtrips."""
    catalog = RoomCatalog(rooms=[
        RoomCatalogEntry(
            id="library", name="Library",
            description="A dusty old library.",
            background_image="rooms/library_bg.png",
            design_size=DesignSize(w=1920, h=1080),
            tags=["indoor", "ground_floor"],
            layers=LayerConfig(
                mode="custom",
                order=["bg", "furniture", "characters", "fg"],
                overrides=["furniture"],
            ),
        ),
    ])
    path = tmp_path / "room_catalog.json"
    save_room_catalog(path, catalog)
    reloaded = load_room_catalog(path)
    room = reloaded.rooms[0]
    assert room.background_image == "rooms/library_bg.png"
    assert room.design_size.w == 1920
    assert room.tags == ["indoor", "ground_floor"]
    assert room.layers.mode == "custom"
    assert room.layers.order == ["bg", "furniture", "characters", "fg"]
    assert room.layers.overrides == ["furniture"]


def test_room_catalog_roundtrip_sockets(tmp_path: Path) -> None:
    """Room with sockets roundtrips correctly."""
    catalog = RoomCatalog(rooms=[
        RoomCatalogEntry(
            id="attic", name="Attic",
            sockets=[
                SocketDefinition(
                    id="socket_left", name="Left Wall",
                    description="Left side socket",
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
        ),
    ])
    path = tmp_path / "room_catalog.json"
    save_room_catalog(path, catalog)
    reloaded = load_room_catalog(path)
    sockets = reloaded.rooms[0].sockets
    assert len(sockets) == 2
    assert sockets[0].id == "socket_left"
    assert sockets[0].ambient_spawn_chance == 50
    assert sockets[0].allowed_entity_ids == ["ghost", "spider"]
    assert sockets[0].required_tags == ["dark"]
    assert sockets[0].pivot_mode == PivotMode.BOTTOM
    assert sockets[1].id == "socket_center"
    assert sockets[1].x == 960


def test_room_catalog_roundtrip_multiple_rooms(tmp_path: Path) -> None:
    """Multiple rooms with mixed fields roundtrip."""
    catalog = RoomCatalog(rooms=[
        RoomCatalogEntry(
            id="cellar", name="Cellar",
            background_image="rooms/cellar.png",
            tags=["basement"],
            sockets=[SocketDefinition(id="s1", name="Spot 1", x=100, y=800)],
        ),
        RoomCatalogEntry(
            id="roof", name="Roof",
            tags=["top_floor", "outside"],
            layers=LayerConfig(mode="custom", order=["sky", "roof", "characters"]),
        ),
    ])
    path = tmp_path / "room_catalog.json"
    save_room_catalog(path, catalog)
    reloaded = load_room_catalog(path)
    assert len(reloaded.rooms) == 2
    assert reloaded.rooms[0].sockets[0].id == "s1"
    assert reloaded.rooms[1].layers.order == ["sky", "roof", "characters"]