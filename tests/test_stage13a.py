"""Stage 13A regression coverage: stable JSON, path robustness, scoped IDs,
inheritance, validate tab UX, atomic writes."""
from __future__ import annotations

import json
import os
import threading
from pathlib import Path

import pytest

FIXTURES = Path(__file__).parent / "fixtures" / "mansion_v2"


# ===========================================================================
# Atomic write / stable JSON
# ===========================================================================

class TestAtomicWrite:
    def test_write_json_creates_file(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.json_io import write_json
        out = tmp_path / "out.json"
        write_json(out, {"key": "value"})
        assert out.exists()
        assert json.loads(out.read_text(encoding="utf-8")) == {"key": "value"}

    def test_write_json_no_temp_file_left_on_success(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.json_io import write_json
        out = tmp_path / "data.json"
        write_json(out, {"x": 1})
        leftover = list(tmp_path.glob("*.tmp"))
        assert leftover == [], f"Temp file left behind: {leftover}"

    def test_write_json_preserves_existing_on_exception(self, tmp_path: Path) -> None:
        """If serialization fails, the existing file must not be corrupted."""
        from behemoth_location_tool.io.json_io import write_json
        out = tmp_path / "existing.json"
        original = {"original": True}
        write_json(out, original)

        class _Unserializable:
            pass

        with pytest.raises(TypeError):
            write_json(out, {"bad": _Unserializable()})

        reread = json.loads(out.read_text(encoding="utf-8"))
        assert reread == original

    def test_write_json_creates_parent_dir(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.json_io import write_json
        deep = tmp_path / "a" / "b" / "c" / "file.json"
        write_json(deep, {"nested": True})
        assert deep.exists()

    def test_write_json_newline_terminated(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.json_io import write_json
        out = tmp_path / "nl.json"
        write_json(out, {"a": 1})
        raw = out.read_bytes()
        assert raw.endswith(b"\n")

    def test_write_json_consistent_indent(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.json_io import write_json
        out = tmp_path / "indent.json"
        write_json(out, {"a": {"b": 1}})
        text = out.read_text(encoding="utf-8")
        assert '  "b": 1' in text, "Expected 2-space indent"

    def test_save_reload_round_trip_stable(self, tmp_path: Path) -> None:
        """Saving then saving again must produce identical bytes."""
        from behemoth_location_tool.io.locations_loader import load_locations, save_locations
        lf = load_locations(FIXTURES / "locations.json")
        out = tmp_path / "locations.json"
        save_locations(out, lf)
        first = out.read_bytes()
        save_locations(out, lf)
        second = out.read_bytes()
        assert first == second, "Double-save produced different bytes"


# ===========================================================================
# Project path robustness
# ===========================================================================

class TestProjectPathResolution:
    def test_absolute_game_data_root_when_game_data_root_absolute(self, tmp_path: Path) -> None:
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        p.game_data_root = tmp_path / "data"
        assert p.absolute_game_data_root == tmp_path / "data"

    def test_absolute_game_data_root_when_relative(self, tmp_path: Path) -> None:
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        p.game_root = tmp_path / "game"
        p.game_data_root = Path("data/behemoth/game")
        expected = (tmp_path / "game" / "data" / "behemoth" / "game").resolve()
        assert p.absolute_game_data_root == expected

    def test_resolve_paths_relative_to_project_dir(self, tmp_path: Path) -> None:
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        p.game_root = Path("my_game")
        project_dir = tmp_path / "projects"
        project_dir.mkdir()
        p.resolve_paths(project_dir)
        assert p.game_root.is_absolute()
        assert p.game_root == (project_dir / "my_game").resolve()

    def test_resolve_paths_game_exe_relative_to_game_root(self, tmp_path: Path) -> None:
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        p.game_root = tmp_path / "game"
        p.game_executable = Path("bin/Game.exe")
        p.resolve_paths(tmp_path)
        assert p.game_executable == (tmp_path / "game" / "bin" / "Game.exe").resolve()

    def test_resolve_paths_absolute_game_root_unchanged(self, tmp_path: Path) -> None:
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        abs_root = tmp_path / "absolute_game"
        abs_root.mkdir()
        p.game_root = abs_root
        p.resolve_paths(tmp_path)
        assert p.game_root == abs_root

    def test_preview_snapshot_path_under_tool_root(self) -> None:
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        snap = p.absolute_preview_snapshot_path
        assert snap.name == "current_snapshot.json"
        assert "preview" in snap.parts

    def test_no_absolute_paths_in_saved_project(self, tmp_path: Path) -> None:
        from behemoth_location_tool.io.project import save_project
        from behemoth_location_tool.model.project import ProjectConfig
        p = ProjectConfig()
        p.game_root = Path("relative/game")
        out = tmp_path / "project.json"
        save_project(out, p)
        data = json.loads(out.read_text(encoding="utf-8"))
        for key in ("gameRoot", "gameExecutable", "contentRoot", "imageRoot",
                    "gameDataRoot", "toolDataRoot"):
            val = data.get(key, "")
            assert not Path(val).is_absolute(), (
                f"{key} stored as absolute path: {val}"
            )


# ===========================================================================
# Scoped ID generation
# ===========================================================================

class TestScopedIdGeneration:
    def test_normalize_id_basic(self) -> None:
        from behemoth_location_tool.model.id_utils import normalize_id
        assert normalize_id("Entrance Hall") == "entrance_hall"

    def test_normalize_id_special_chars(self) -> None:
        from behemoth_location_tool.model.id_utils import normalize_id
        assert normalize_id("Grand Library (East)") == "grand_library_east"

    def test_generate_id_unique_within_scope(self) -> None:
        from behemoth_location_tool.model.id_utils import generate_id
        existing = {"entrance_hall", "entrance_hall_2"}
        result = generate_id("Entrance Hall", existing)
        assert result not in existing
        assert result == "entrance_hall_3"

    def test_generate_id_no_collision_returns_base(self) -> None:
        from behemoth_location_tool.model.id_utils import generate_id
        result = generate_id("Library", set())
        assert result == "library"

    def test_generate_padded_id_first_no_suffix(self) -> None:
        from behemoth_location_tool.model.id_utils import generate_padded_id
        result = generate_padded_id("Chair", set())
        assert result == "chair"

    def test_generate_padded_id_second_gets_02(self) -> None:
        from behemoth_location_tool.model.id_utils import generate_padded_id
        result = generate_padded_id("Chair", {"chair"})
        assert result == "chair_02"

    def test_generate_padded_id_third_gets_03(self) -> None:
        from behemoth_location_tool.model.id_utils import generate_padded_id
        result = generate_padded_id("Chair", {"chair", "chair_02"})
        assert result == "chair_03"

    def test_socket_ids_scoped_per_room(self) -> None:
        """socket IDs 'prop_01' in two different rooms must not conflict."""
        from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition, DesignSize
        sock = SocketDefinition(id="prop_01", name="Prop 1")
        room_a = RoomCatalogEntry(id="room_a", name="Room A", sockets=[sock])
        room_b = RoomCatalogEntry(id="room_b", name="Room B", sockets=[sock])
        catalog = RoomCatalog(rooms=[room_a, room_b])

        from behemoth_location_tool.validation.validator import validate_room_catalog
        report = validate_room_catalog(catalog)
        dup_errors = [d for d in report.diagnostics if "duplicate" in d.code]
        assert dup_errors == [], "Same socket ID in different rooms should not be a duplicate error"

    def test_duplicate_socket_ids_within_room_is_error(self) -> None:
        from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
        sock1 = SocketDefinition(id="prop_01", name="First")
        sock2 = SocketDefinition(id="prop_01", name="Second")
        room = RoomCatalogEntry(id="room_a", name="Room A", sockets=[sock1, sock2])
        catalog = RoomCatalog(rooms=[room])

        from behemoth_location_tool.validation.validator import validate_room_catalog
        report = validate_room_catalog(catalog)
        dup_errors = [d for d in report.diagnostics
                      if d.code == "duplicate_catalog_socket_template_id"]
        assert dup_errors, "Duplicate socket IDs within one room must be an error"

    def test_duplicate_location_ids_is_error(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, LocationsFile
        loc = LocationInstance(id="hall", catalog_room_id="", name="Hall")
        lf = LocationsFile(start_location="hall", locations=[loc, loc])
        from behemoth_location_tool.validation.validator import validate_locations
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_id" for d in report.diagnostics)

    def test_duplicate_exit_ids_within_location_is_error(self) -> None:
        from behemoth_location_tool.model.location import (
            ExitDefinition, LocationInstance, LocationsFile,
        )
        ex = ExitDefinition(id="ex1", entity_id="e1", target_location_id="b", socket_id="s1")
        loc_a = LocationInstance(id="a", catalog_room_id="", name="A", exits=[ex, ex])
        loc_b = LocationInstance(id="b", catalog_room_id="", name="B",
                                  exits=[ExitDefinition(id="back", entity_id="e1",
                                                         target_location_id="a",
                                                         socket_id="s1",
                                                         tags=["exit.default_back"])])
        lf = LocationsFile(start_location="a", locations=[loc_a, loc_b])
        from behemoth_location_tool.validation.validator import validate_locations
        report = validate_locations(lf)
        assert any(d.code == "duplicate_location_exit_id" for d in report.diagnostics)

    def test_same_exit_ids_in_different_locations_ok(self) -> None:
        from behemoth_location_tool.model.location import (
            ExitDefinition, LocationInstance, LocationsFile,
        )
        ex_a_to_b = ExitDefinition(id="exit_01", entity_id="e1",
                                    target_location_id="b", socket_id="s1")
        ex_b_to_a = ExitDefinition(id="exit_01", entity_id="e1",
                                    target_location_id="a", socket_id="s1",
                                    tags=["exit.default_back"])
        loc_a = LocationInstance(id="a", catalog_room_id="", name="A", exits=[ex_a_to_b])
        loc_b = LocationInstance(id="b", catalog_room_id="", name="B", exits=[ex_b_to_a])
        lf = LocationsFile(start_location="a", locations=[loc_a, loc_b])
        from behemoth_location_tool.validation.validator import validate_locations
        report = validate_locations(lf)
        dup_errors = [d for d in report.diagnostics if "duplicate_location_exit_id" in d.code]
        assert dup_errors == [], "Same exit ID in different locations must be allowed"


# ===========================================================================
# Background & socket inheritance regressions
# ===========================================================================

class TestInheritanceRegressions:
    def _make_catalog(self, bg: str = "bg.png") -> "RoomCatalog":
        from behemoth_location_tool.model.room import (
            RoomCatalog, RoomCatalogEntry, SocketDefinition, DesignSize,
        )
        sock = SocketDefinition(id="s1", name="Slot 1")
        room = RoomCatalogEntry(
            id="room_a", name="Room A",
            background_image=bg,
            design_size=DesignSize(w=1920, h=1080),
            sockets=[sock],
        )
        return RoomCatalog(rooms=[room])

    def test_location_inherits_background(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, get_effective_background
        catalog = self._make_catalog("rooms/hall.png")
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc")
        bg = get_effective_background(loc, catalog)
        assert bg == "rooms/hall.png"

    def test_location_override_background(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, get_effective_background
        catalog = self._make_catalog("rooms/hall.png")
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc",
                                background_image="override.png",
                                background_overridden=True)
        bg = get_effective_background(loc, catalog)
        assert bg == "override.png"

    def test_catalog_change_affects_inheriting_location(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, get_effective_background
        catalog = self._make_catalog("rooms/old.png")
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc")
        # Change catalog room background
        catalog.rooms[0].background_image = "rooms/new.png"
        bg = get_effective_background(loc, catalog)
        assert bg == "rooms/new.png"

    def test_catalog_change_does_not_affect_overridden_location(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, get_effective_background
        catalog = self._make_catalog("rooms/old.png")
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc",
                                background_image="my_override.png",
                                background_overridden=True)
        catalog.rooms[0].background_image = "rooms/new.png"
        bg = get_effective_background(loc, catalog)
        assert bg == "my_override.png"

    def test_location_inherits_sockets(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, get_effective_sockets
        catalog = self._make_catalog()
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc")
        sockets = get_effective_sockets(loc, catalog)
        assert len(sockets) == 1
        assert sockets[0].id == "s1"

    def test_location_socket_override_replaces_catalog(self) -> None:
        from behemoth_location_tool.model.location import LocationInstance, get_effective_sockets
        from behemoth_location_tool.model.room import SocketDefinition
        catalog = self._make_catalog()
        override_sock = SocketDefinition(id="custom", name="Custom Slot")
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc",
                                sockets=[override_sock], socket_overridden=True)
        sockets = get_effective_sockets(loc, catalog)
        assert len(sockets) == 1
        assert sockets[0].id == "custom"

    def test_validation_uses_effective_sockets(self) -> None:
        """Exit referencing catalog socket must pass when location inherits."""
        from behemoth_location_tool.model.location import (
            ExitDefinition, LocationInstance, LocationsFile,
        )
        from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
        sock = SocketDefinition(id="exit_sock", name="Exit")
        room = RoomCatalogEntry(id="hall", name="Hall", sockets=[sock])
        catalog = RoomCatalog(rooms=[room])

        ex = ExitDefinition(id="ex1", entity_id="door", target_location_id="b",
                             socket_id="exit_sock")
        back = ExitDefinition(id="back", entity_id="door", target_location_id="a",
                               socket_id="exit_sock", tags=["exit.default_back"])
        loc_a = LocationInstance(id="a", catalog_room_id="hall", name="Hall", exits=[ex])
        loc_b = LocationInstance(id="b", catalog_room_id="hall", name="Hall B", exits=[back])
        lf = LocationsFile(start_location="a", locations=[loc_a, loc_b])

        from behemoth_location_tool.validation.validator import validate_locations
        report = validate_locations(lf, catalog=catalog)
        socket_errors = [d for d in report.diagnostics if d.code == "missing_socket_ref"]
        assert socket_errors == [], f"Unexpected socket errors: {socket_errors}"

    def test_snapshot_uses_effective_background(self) -> None:
        from behemoth_location_tool.model.common import DesignSize
        from behemoth_location_tool.model.location import LocationInstance
        from behemoth_location_tool.model.project import ProjectConfig
        from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
        from behemoth_location_tool.preview.snapshot import build_location_snapshot

        catalog = self._make_catalog("rooms/inherited_bg.png")
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc",
                                design_size=DesignSize(w=1920, h=1080))
        project = ProjectConfig()
        snap = build_location_snapshot(project, loc, catalog=catalog)
        assert snap["locations"][0]["backgroundImage"] == "rooms/inherited_bg.png"

    def test_snapshot_uses_effective_sockets(self) -> None:
        from behemoth_location_tool.model.common import DesignSize
        from behemoth_location_tool.model.location import LocationInstance
        from behemoth_location_tool.model.project import ProjectConfig
        from behemoth_location_tool.preview.snapshot import build_location_snapshot

        catalog = self._make_catalog()
        loc = LocationInstance(id="loc", catalog_room_id="room_a", name="Loc",
                                design_size=DesignSize(w=1920, h=1080))
        project = ProjectConfig()
        snap = build_location_snapshot(project, loc, catalog=catalog)
        socket_ids = [s["id"] for s in snap["locations"][0]["sockets"]]
        assert "s1" in socket_ids


# ===========================================================================
# ValidateTab source checks (no GUI required)
# ===========================================================================

class TestValidateTabSource:
    def _src(self) -> str:
        p = (Path(__file__).parent.parent / "src" / "behemoth_location_tool"
             / "ui" / "validate_tab.py")
        return p.read_text(encoding="utf-8")

    def test_has_severity_combo(self) -> None:
        assert "QComboBox" in self._src()
        assert "_sev_combo" in self._src()

    def test_has_search_edit(self) -> None:
        assert "_search_edit" in self._src()

    def test_has_copy_button(self) -> None:
        assert "_copy_button" in self._src()

    def test_sorting_enabled(self) -> None:
        assert "setSortingEnabled(True)" in self._src()

    def test_row_colors(self) -> None:
        assert "QColor" in self._src()
        assert "setBackground" in self._src()

    def test_traceback_in_crash_handler(self) -> None:
        assert "traceback" in self._src()

    def test_severity_filter_options_cover_all_levels(self) -> None:
        src = self._src()
        for level in ("error", "warning", "info"):
            assert level in src.lower()


# ===========================================================================
# Wording: no V1/V2/legacy in normal UI
# ===========================================================================

class TestWordingClean:
    _UI_SOURCES = [
        "behemoth_location_tool.ui.main_window",
        "behemoth_location_tool.ui.project_tab",
        "behemoth_location_tool.ui.locations_tab",
        "behemoth_location_tool.ui.room_catalog_tab",
        "behemoth_location_tool.ui.entities_tab",
        "behemoth_location_tool.ui.validate_tab",
        "behemoth_location_tool.ui.preview_tab",
        "behemoth_location_tool.ui.generate_tab",
    ]

    def _src(self, module: str) -> str:
        parts = module.split(".")
        p = (Path(__file__).parent.parent / "src"
             / "/".join(parts[:-1]) / (parts[-1] + ".py"))
        return p.read_text(encoding="utf-8")

    def _user_facing_strings(self, source: str) -> list[str]:
        """Extract string literals that appear in user-facing Qt calls."""
        import re
        patterns = [
            r'QAction\("([^"]+)"',
            r'setStatusTip\("([^"]+)"',
            r'setWindowTitle\("([^"]+)"',
            r'addTab\([^,]+,\s*"([^"]+)"',
            r'QGroupBox\("([^"]+)"',
            r'QLabel\("([^"]+)"',
            r'QPushButton\("([^"]+)"',
        ]
        results: list[str] = []
        for pat in patterns:
            results.extend(re.findall(pat, source))
        return results

    @pytest.mark.parametrize("module", _UI_SOURCES)
    def test_no_legacy_wording(self, module: str) -> None:
        src = self._src(module)
        for s in self._user_facing_strings(src):
            lower = s.lower()
            assert "legacy" not in lower, f"{module}: user-facing string has 'legacy': {s!r}"
            assert " v1 " not in lower and lower.endswith(" v1") is False or "v1" not in lower, (
                f"{module}: possible v1 in user-facing string: {s!r}"
            )
