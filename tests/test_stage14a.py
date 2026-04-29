"""Stage 14A: socket editor and asset browser polish."""
from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "mansion_v2"
SRC = Path(__file__).parent.parent / "src" / "behemoth_location_tool"


# ===========================================================================
# AmbientRule model
# ===========================================================================

class TestAmbientRuleModel:
    def test_ambient_rule_default_mode(self) -> None:
        from behemoth_location_tool.model.room import AmbientRule
        rule = AmbientRule()
        assert rule.mode in {"none", "tag_query"}  # model default is tag_query

    def test_ambient_rule_roundtrip_tag_query(self) -> None:
        from behemoth_location_tool.model.room import AmbientRule
        rule = AmbientRule(mode="tag_query", required_tags=["furniture"], forbidden_tags=["broken"])
        dumped = rule.model_dump(by_alias=True)
        rule2 = AmbientRule.model_validate(dumped)
        assert rule2.mode == "tag_query"
        assert rule2.required_tags == ["furniture"]
        assert rule2.forbidden_tags == ["broken"]

    def test_ambient_rule_roundtrip_weighted_entity_list(self) -> None:
        from behemoth_location_tool.model.room import AmbientRule, WeightedEntityEntry
        rule = AmbientRule(
            mode="weighted_entity_list",
            entries=[WeightedEntityEntry(entity_id="chair_01", weight=60),
                     WeightedEntityEntry(entity_id="bookcase_01", weight=40)],
        )
        dumped = rule.model_dump(by_alias=True)
        rule2 = AmbientRule.model_validate(dumped)
        assert len(rule2.entries) == 2
        assert rule2.entries[0].entity_id == "chair_01"
        assert rule2.entries[0].weight == 60

    def test_ambient_rule_roundtrip_weighted_entries(self) -> None:
        from behemoth_location_tool.model.room import AmbientRule, WeightedFillEntry
        rule = AmbientRule(
            mode="weighted_entries",
            fill_entries=[
                WeightedFillEntry(type="entity", entity_id="chair_01", weight=70),
                WeightedFillEntry(type="tag_query", required_tags=["decoration"], weight=30),
            ],
        )
        dumped = rule.model_dump(by_alias=True)
        rule2 = AmbientRule.model_validate(dumped)
        assert len(rule2.fill_entries) == 2
        assert rule2.fill_entries[1].type == "tag_query"

    def test_socket_ambient_spawn_chance_range(self) -> None:
        from behemoth_location_tool.model.room import SocketDefinition
        sock = SocketDefinition(id="s1", name="S1")
        assert sock.ambient_spawn_chance == 0
        sock.ambient_spawn_chance = 75
        assert sock.ambient_spawn_chance == 75

    def test_socket_default_ambient_rule_mode(self) -> None:
        from behemoth_location_tool.model.room import SocketDefinition
        sock = SocketDefinition(id="s2", name="S2")
        assert sock.ambient_rule.mode in {"none", "tag_query"}  # model default


# ===========================================================================
# Tag query matching entity count
# ===========================================================================

def _make_entities():
    from behemoth_location_tool.model.entity import EntityDefinition
    return [
        EntityDefinition(id="chair_01", kind="prop", name="Chair",
                         tags=["entity.spawnable", "furniture", "furniture.chair"]),
        EntityDefinition(id="bookcase_01", kind="prop", name="Bookcase",
                         tags=["entity.spawnable", "furniture", "furniture.bookcase"]),
        EntityDefinition(id="door_01", kind="prop", name="Door",
                         tags=["entity.spawnable", "door"]),
        EntityDefinition(id="npc_01", kind="character", name="NPC",
                         tags=["character"]),  # no entity.spawnable
    ]


class TestTagQueryMatchCount:
    def _fn(self):
        from behemoth_location_tool.ui.room_catalog_tab import _count_matching_entities
        return _count_matching_entities

    def test_count_all_spawnable(self) -> None:
        fn = self._fn()
        result = fn(_make_entities(), [], [])
        assert result == 3  # chair, bookcase, door (not npc — no entity.spawnable)

    def test_count_required_tag_furniture(self) -> None:
        fn = self._fn()
        result = fn(_make_entities(), ["furniture"], [])
        assert result == 2  # chair, bookcase

    def test_count_required_tag_hierarchical(self) -> None:
        fn = self._fn()
        result = fn(_make_entities(), ["furniture.chair"], [])
        assert result == 1  # chair only

    def test_count_forbidden_tag_excludes(self) -> None:
        fn = self._fn()
        result = fn(_make_entities(), [], ["door"])
        assert result == 2  # chair, bookcase (door excluded)

    def test_count_no_spawnable_excluded(self) -> None:
        fn = self._fn()
        result = fn(_make_entities(), ["character"], [])
        assert result == 0  # npc has no entity.spawnable

    def test_count_empty_entities(self) -> None:
        fn = self._fn()
        result = fn([], ["furniture"], [])
        assert result == 0


# ===========================================================================
# Asset path relative to imageRoot
# ===========================================================================

class TestAssetPathRelative:
    def test_bg_path_relative_stored(self, tmp_path: Path) -> None:
        """Background path stored relative to imageRoot when inside imageRoot."""
        image_root = tmp_path / "images"
        image_root.mkdir()
        # Create a fake png (just a file, QFileDialog won't run in tests)
        (image_root / "bg.png").write_bytes(b"")
        # Simulate what _on_browse_bg does
        chosen = str(image_root / "bg.png")
        try:
            rel = Path(chosen).relative_to(image_root)
            stored = str(rel).replace("\\", "/")
        except ValueError:
            stored = chosen.replace("\\", "/")
        assert stored == "bg.png"

    def test_sprite_path_relative_stored(self, tmp_path: Path) -> None:
        """Sprite path stored relative to imageRoot when inside imageRoot."""
        image_root = tmp_path / "images" / "sprites"
        image_root.mkdir(parents=True)
        chosen = str(image_root / "chair.png")
        try:
            rel = Path(chosen).relative_to(image_root)
            stored = str(rel).replace("\\", "/")
        except ValueError:
            stored = chosen.replace("\\", "/")
        assert stored == "chair.png"

    def test_path_outside_image_root_stored_absolute(self, tmp_path: Path) -> None:
        """Path outside imageRoot stored as-is (absolute fallback)."""
        image_root = tmp_path / "images"
        image_root.mkdir()
        chosen = str(tmp_path / "external" / "bg.png")
        try:
            rel = Path(chosen).relative_to(image_root)
            stored = str(rel).replace("\\", "/")
        except ValueError:
            stored = chosen.replace("\\", "/")
        assert "external" in stored


# ===========================================================================
# Source-level checks (no Qt runtime needed)
# ===========================================================================

class TestRoomCatalogTabSource:
    def _src(self) -> str:
        return (SRC / "ui" / "room_catalog_tab.py").read_text(encoding="utf-8")

    def test_ambient_info_wording_exact(self) -> None:
        src = self._src()
        assert "Ambient Spawn Chance controls random filler." in src
        assert "Explicit placement can still use this socket when Ambient Spawn Chance is 0%." in src

    def test_ambient_info_no_old_wording(self) -> None:
        src = self._src()
        assert "controls whether random filler appears here" not in src

    def test_bg_thumbnail_widget_exists(self) -> None:
        src = self._src()
        assert "_f_bg_thumb" in src
        assert "setFixedSize(160, 90)" in src

    def test_bg_warn_label_exists(self) -> None:
        src = self._src()
        assert "_f_bg_warn" in src

    def test_match_label_exists_in_tag_query_page(self) -> None:
        src = self._src()
        assert "_sf_ar_match_label" in src

    def test_set_entities_method_exists(self) -> None:
        src = self._src()
        assert "def set_entities(" in src

    def test_refresh_bg_thumbnail_method_exists(self) -> None:
        src = self._src()
        assert "def _refresh_bg_thumbnail(" in src

    def test_count_matching_entities_method_exists(self) -> None:
        src = self._src()
        assert "def _count_matching_entities(" in src

    def test_no_allowed_entity_ids_label(self) -> None:
        src = self._src()
        assert "Allowed Entity IDs" not in src


class TestEntitiesTabSource:
    def _src(self) -> str:
        return (SRC / "ui" / "entities_tab.py").read_text(encoding="utf-8")

    def test_sprite_browse_button_exists(self) -> None:
        src = self._src()
        assert "_f_sprite_browse" in src

    def test_sprite_thumbnail_widget_exists(self) -> None:
        src = self._src()
        assert "_f_sprite_thumb" in src
        assert "setFixedSize(128, 128)" in src

    def test_sprite_warn_label_exists(self) -> None:
        src = self._src()
        assert "_f_sprite_warn" in src

    def test_on_browse_sprite_method_exists(self) -> None:
        src = self._src()
        assert "def _on_browse_sprite(" in src

    def test_refresh_sprite_thumbnail_method_exists(self) -> None:
        src = self._src()
        assert "def _refresh_sprite_thumbnail(" in src

    def test_project_param_in_init(self) -> None:
        src = self._src()
        assert "project: ProjectConfig | None = None" in src

    def test_qpixmap_imported(self) -> None:
        src = self._src()
        assert "QPixmap" in src

    def test_qfiledialog_imported(self) -> None:
        src = self._src()
        assert "QFileDialog" in src


class TestMainWindowSource:
    def _src(self) -> str:
        return (SRC / "ui" / "main_window.py").read_text(encoding="utf-8")

    def test_entities_tab_created_with_project(self) -> None:
        src = self._src()
        assert "EntitiesTab(project=self.project)" in src

    def test_sync_generate_tab_calls_set_entities_on_room_catalog(self) -> None:
        src = self._src()
        assert "self._room_catalog_tab.set_entities(" in src
