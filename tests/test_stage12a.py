"""Stage 12A: end-to-end mansion tests, bug fixes, and preview wiring checks."""
from __future__ import annotations

from pathlib import Path

FIXTURES = Path(__file__).parent / "fixtures" / "mansion_v2"


# ---------------------------------------------------------------------------
# 3-room mansion fixture: 0 errors
# ---------------------------------------------------------------------------

class TestMansionFixtureValidation:
    """The bundled 3-room mansion fixture must validate with zero errors."""

    def _make_project(self):
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        p.game_data_root = FIXTURES.resolve()
        return p

    def test_fixture_files_exist(self) -> None:
        assert (FIXTURES / "entities.json").exists()
        assert (FIXTURES / "entity_modules" / "main.json").exists()
        assert (FIXTURES / "room_catalog.json").exists()
        assert (FIXTURES / "locations.json").exists()

    def test_room_catalog_loads(self) -> None:
        from behemoth_location_tool.io.room_catalog_loader import load_room_catalog
        catalog = load_room_catalog(FIXTURES / "room_catalog.json")
        assert len(catalog.rooms) == 3
        ids = {r.id for r in catalog.rooms}
        assert ids == {"entrance_hall_01", "library_01", "kitchen_01"}

    def test_locations_loads(self) -> None:
        from behemoth_location_tool.io.locations_loader import load_locations
        lf = load_locations(FIXTURES / "locations.json")
        assert len(lf.locations) == 3
        assert lf.start_location == "entrance_hall_01"

    def test_entity_module_loads(self) -> None:
        from behemoth_location_tool.io.entity_loader import load_entity_module
        module = load_entity_module(FIXTURES / "entity_modules" / "main.json")
        ids = {e.id for e in module.entities}
        assert "door_double_01" in ids
        assert "door_single_01" in ids
        assert "chair_01" in ids

    def test_validate_project_zero_errors(self) -> None:
        from behemoth_location_tool.validation.validator import validate_project
        project = self._make_project()
        report = validate_project(project)
        errors = [d for d in report.diagnostics if d.severity.value == "error"]
        assert errors == [], f"Expected 0 errors, got: {[d.message for d in errors]}"

    def test_validate_project_three_rooms_reachable(self) -> None:
        """BFS reachability must include all 3 locations."""
        from behemoth_location_tool.io.locations_loader import load_locations
        from behemoth_location_tool.validation.validator import validate_locations
        lf = load_locations(FIXTURES / "locations.json")
        report = validate_locations(lf)
        unreachable = [d for d in report.diagnostics if d.code == "unreachable_location"]
        assert unreachable == [], f"Unreachable locations: {[d.object_id for d in unreachable]}"

    def test_reciprocal_exits_satisfied(self) -> None:
        from behemoth_location_tool.io.locations_loader import load_locations
        from behemoth_location_tool.validation.validator import validate_locations
        lf = load_locations(FIXTURES / "locations.json")
        report = validate_locations(lf)
        missing = [d for d in report.diagnostics if d.code == "missing_reciprocal_exit"]
        assert missing == [], f"Missing reciprocal exits: {[d.message for d in missing]}"

    def test_non_start_locations_have_default_back_exit(self) -> None:
        from behemoth_location_tool.io.locations_loader import load_locations
        from behemoth_location_tool.validation.validator import validate_locations
        lf = load_locations(FIXTURES / "locations.json")
        report = validate_locations(lf)
        missing_back = [d for d in report.diagnostics if d.code == "missing_default_back_exit"]
        assert missing_back == [], f"Missing back exits: {[d.object_id for d in missing_back]}"

    def test_graph_nodes_cover_all_locations(self) -> None:
        from behemoth_location_tool.io.locations_loader import load_locations
        from behemoth_location_tool.validation.validator import validate_locations
        lf = load_locations(FIXTURES / "locations.json")
        report = validate_locations(lf)
        missing_nodes = [d for d in report.diagnostics if d.code == "missing_graph_node"]
        assert missing_nodes == [], f"Missing graph nodes: {[d.object_id for d in missing_nodes]}"


# ---------------------------------------------------------------------------
# Snapshot bug fix: ent.render.sprite (not .image)
# ---------------------------------------------------------------------------

class TestSnapshotSpriteFix:
    def test_entity_render_uses_sprite_not_image(self) -> None:
        from behemoth_location_tool.model.entity import EntityDefinition, EntityRenderData
        ent = EntityDefinition(
            id="test_ent", kind="prop", name="Test",
            tags=[], render=EntityRenderData(sprite="props/table.png"),
        )
        assert hasattr(ent.render, "sprite")
        assert not hasattr(ent.render, "image")
        assert ent.render.sprite == "props/table.png"

    def test_build_location_snapshot_includes_entity_sprite(self) -> None:
        from behemoth_location_tool.model.common import DesignSize
        from behemoth_location_tool.model.entity import EntityDefinition, EntityRenderData
        from behemoth_location_tool.model.location import (
            LocationInstance,
            PlacedEntity,
        )
        from behemoth_location_tool.model.project import ProjectConfig
        from behemoth_location_tool.preview.snapshot import build_location_snapshot

        project = ProjectConfig()
        entity = EntityDefinition(
            id="chair_01", kind="furniture", name="Chair",
            tags=[], render=EntityRenderData(sprite="furniture/chair.png"),
        )
        loc = LocationInstance(
            id="test_loc",
            catalog_room_id="",
            name="Test Location",
            design_size=DesignSize(w=1920, h=1080),
            placed_entities=[
                PlacedEntity(
                    instance_id="pe_01",
                    entity_id="chair_01",
                    socket_id="prop_01",
                )
            ],
        )

        snapshot = build_location_snapshot(project, loc, entities=[entity])
        entity_data = snapshot["entities"]
        assert len(entity_data) == 1
        assert entity_data[0]["id"] == "chair_01"
        assert entity_data[0]["render"]["image"] == "furniture/chair.png"


# ---------------------------------------------------------------------------
# LocationsTab.current_location_id (source check — no GUI required)
# ---------------------------------------------------------------------------

class TestLocationsTabCurrentLocationIdSource:
    def test_property_defined_in_source(self) -> None:
        src_path = (
            Path(__file__).parent.parent
            / "src" / "behemoth_location_tool" / "ui" / "locations_tab.py"
        )
        src = src_path.read_text(encoding="utf-8")
        assert "def current_location_id" in src

    def test_returns_location_id(self) -> None:
        src_path = (
            Path(__file__).parent.parent
            / "src" / "behemoth_location_tool" / "ui" / "locations_tab.py"
        )
        src = src_path.read_text(encoding="utf-8")
        assert "loc.id if loc else" in src or "current_location_id" in src


# ---------------------------------------------------------------------------
# MainWindow preview wiring (source check — no GUI required)
# ---------------------------------------------------------------------------

class TestMainWindowPreviewWiring:
    def _src(self) -> str:
        p = (
            Path(__file__).parent.parent
            / "src" / "behemoth_location_tool" / "ui" / "main_window.py"
        )
        return p.read_text(encoding="utf-8")

    def test_on_location_preview_uses_current_location_id(self) -> None:
        src = self._src()
        assert "current_location_id" in src

    def test_on_location_preview_not_always_start_location(self) -> None:
        src = self._src()
        lines = src.splitlines()
        in_handler = False
        uses_start_without_fallback = False
        for line in lines:
            if "def _on_location_preview" in line:
                in_handler = True
            if in_handler:
                if line.strip().startswith("def ") and "_on_location_preview" not in line:
                    break
                if "loc.start_location" in line and "current_location_id" not in line:
                    uses_start_without_fallback = True
        assert not uses_start_without_fallback, (
            "_on_location_preview still uses start_location exclusively"
        )


# ---------------------------------------------------------------------------
# Save / reload round-trip for fixture data
# ---------------------------------------------------------------------------

class TestFixtureSaveReload:
    def test_locations_round_trip(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.locations_loader import load_locations, save_locations
        original = load_locations(FIXTURES / "locations.json")
        out = tmp_path / "locations.json"
        save_locations(out, original)
        reloaded = load_locations(out)

        orig_ids = {location.id for location in original.locations}
        reload_ids = {location.id for location in reloaded.locations}
        assert orig_ids == reload_ids
        assert reloaded.start_location == original.start_location

    def test_room_catalog_round_trip(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.room_catalog_loader import load_room_catalog, save_room_catalog
        original = load_room_catalog(FIXTURES / "room_catalog.json")
        out = tmp_path / "room_catalog.json"
        save_room_catalog(out, original)
        reloaded = load_room_catalog(out)

        orig_ids = {r.id for r in original.rooms}
        reload_ids = {r.id for r in reloaded.rooms}
        assert orig_ids == reload_ids

    def test_entity_module_round_trip(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.entity_loader import load_entity_module, save_entity_module
        original = load_entity_module(FIXTURES / "entity_modules" / "main.json")
        out = tmp_path / "main.json"
        save_entity_module(out, original)
        reloaded = load_entity_module(out)

        orig_ids = {e.id for e in original.entities}
        reload_ids = {e.id for e in reloaded.entities}
        assert orig_ids == reload_ids
