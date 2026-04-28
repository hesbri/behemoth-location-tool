from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import (
    DEFAULT_PROJECT_LAYERS,
    LocationInstance, LocationsFile, get_effective_background, get_effective_layers, get_effective_sockets,
)
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry
from behemoth_location_tool.model.tags import TagIndex, extract_known_tags, matches_all, matches_none
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity


def validate_unique_ids(ids: Iterable[str], *, label: str, code: str = "duplicate_id") -> DiagnosticReport:
    """Check for duplicate IDs in a sequence."""
    seen: set[str] = set()
    diagnostics: list[Diagnostic] = []
    for item_id in ids:
        if item_id in seen:
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code=code,
                message=f"Duplicate {label} id: {item_id}",
                object_id=item_id,
            ))
        seen.add(item_id)
    return DiagnosticReport(diagnostics=diagnostics)


def validate_entities(entities: list[EntityDefinition]) -> DiagnosticReport:
    """Validate entity definitions for semantic errors and warnings."""
    diagnostics: list[Diagnostic] = []

    # Duplicate entity IDs
    report = validate_unique_ids((e.id for e in entities), label="entity", code="duplicate_entity_id")
    diagnostics.extend(report.diagnostics)

    # Build a set of all known entity IDs for later reference lookups
    entity_ids = {e.id for e in entities}

    for entity in entities:
        # Entity marked spawnable but has no render data
        if "entity.spawnable" in entity.tags and entity.render is None:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="spawnable_no_render",
                message=f"Entity '{entity.id}' is marked spawnable but has no render data",
                object_id=entity.id,
            ))

        # Entity has no clickable rectangle but is interactable
        interactable_tags = {"item.pickable", "character.talkable"}
        if interactable_tags.intersection(entity.tags):
            if entity.render is None or entity.render.clickable_rect is None:
                diagnostics.append(Diagnostic(
                    severity=Severity.WARNING,
                    code="interactable_no_clickable_rect",
                    message=f"Entity '{entity.id}' is interactable but has no clickable rectangle",
                    object_id=entity.id,
                ))

    return DiagnosticReport(diagnostics=diagnostics)


def validate_room_catalog(catalog: RoomCatalog, *, entities: list[EntityDefinition] | None = None) -> DiagnosticReport:
    """Validate room catalog entries for semantic errors and warnings."""
    diagnostics: list[Diagnostic] = []

    # Duplicate room catalog IDs
    report = validate_unique_ids((room.id for room in catalog.rooms), label="room_catalog", code="duplicate_room_catalog_id")
    diagnostics.extend(report.diagnostics)

    for room in catalog.rooms:
        # Duplicate socket IDs within same room
        report = validate_unique_ids((s.id for s in room.sockets), label="catalog_socket_template", code="duplicate_catalog_socket_template_id")
        diagnostics.extend(report.diagnostics)

        # Room overrides project design size
        if room.design_size.w != 1920 or room.design_size.h != 1080:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="room_overrides_design_size",
                message=f"Room '{room.id}' overrides project design size ({room.design_size.w}x{room.design_size.h})",
                object_id=room.id,
            ))

        # Validate socket ambient rules
        entity_ids = {e.id for e in entities} if entities else set()
        entity_tags_map: dict[str, set[str]] = {}
        if entities:
            entity_tags_map = {e.id: set(e.tags) for e in entities}

        for socket in room.sockets:
            _validate_socket_ambient(socket, room, entity_ids, entity_tags_map, diagnostics)

            # Socket has no matching spawnables
            if entities:
                _check_socket_matching_spawnables(socket, room, entities, diagnostics)

        # Room has no sockets
        if not room.sockets:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="room_no_sockets",
                message=f"Room catalog entry '{room.id}' has no sockets",
                object_id=room.id,
            ))

        # Room catalog entry missing background
        if not room.background_image:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="catalog_room_missing_background",
                message=f"Room catalog entry '{room.id}' has no background image",
                object_id=room.id,
            ))

    return DiagnosticReport(diagnostics=diagnostics)


def _check_socket_matching_spawnables(
    socket: object, room: RoomCatalogEntry, entities: list[EntityDefinition], diagnostics: list[Diagnostic]
) -> None:
    """Check if any spawnable entity can match this socket."""
    socket_def = socket  # SocketDefinition
    has_match = False
    for entity in entities:
        if "entity.spawnable" not in entity.tags:
            continue
        if matches_all(set(entity.tags), socket_def.required_tags):
            has_match = True
            break
    if not has_match and socket_def.required_tags:
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code="socket_no_matching_spawnables",
            message=f"Socket '{socket_def.id}' in room '{room.id}' has no matching spawnables",
            object_id=socket_def.id,
        ))


def validate_locations(
    locations_file: LocationsFile,
    *,
    catalog: RoomCatalog | None = None,
    entities: list[EntityDefinition] | None = None,
    project_layers: list[str] | None = None,
) -> DiagnosticReport:
    """Validate locations for semantic errors and warnings."""
    diagnostics: list[Diagnostic] = []
    layers = project_layers or list(DEFAULT_PROJECT_LAYERS)

    # Start location must exist
    location_ids = {loc.id for loc in locations_file.locations}
    if locations_file.start_location not in location_ids:
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="missing_start_location",
            message=f"startLocation '{locations_file.start_location}' does not exist",
            object_id=locations_file.start_location,
        ))

    # Duplicate location IDs
    report = validate_unique_ids((loc.id for loc in locations_file.locations), label="location", code="duplicate_location_id")
    diagnostics.extend(report.diagnostics)

    # Build entity ID set for reference checks
    entity_id_set = {e.id for e in entities} if entities else set()
    catalog_id_set = {r.id for r in catalog.rooms} if catalog else set()

    # Build a map of location IDs to exits for reciprocal checking
    exit_targets: dict[str, set[str]] = defaultdict(set)

    for loc in locations_file.locations:
        # Missing effective background
        effective_bg = get_effective_background(loc, catalog)
        if not effective_bg:
            if loc.background_overridden:
                diagnostics.append(Diagnostic(
                    severity=Severity.WARNING,
                    code="location_missing_background_override",
                    message=f"Location '{loc.id}' has background override set but no background image",
                    object_id=loc.id,
                ))
            elif loc.catalog_room_id and loc.catalog_room_id in catalog_id_set:
                diagnostics.append(Diagnostic(
                    severity=Severity.WARNING,
                    code="location_missing_background_inherited",
                    message=f"Location '{loc.id}' inherits empty background from catalog room '{loc.catalog_room_id}'",
                    object_id=loc.id,
                ))
            else:
                diagnostics.append(Diagnostic(
                    severity=Severity.WARNING,
                    code="location_missing_background",
                    message=f"Location '{loc.id}' has no effective background image",
                    object_id=loc.id,
                ))

        # Missing referenced room catalog ID
        if loc.catalog_room_id and loc.catalog_room_id not in catalog_id_set:
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code="missing_catalog_room",
                message=f"Location '{loc.id}' references unknown catalog room '{loc.catalog_room_id}'",
                object_id=loc.id,
            ))

        # Duplicate socket IDs within same location (use effective sockets)
        effective_sockets = get_effective_sockets(loc, catalog)
        report = validate_unique_ids((s.id for s in effective_sockets), label="location_socket", code="duplicate_location_socket_id")
        diagnostics.extend(report.diagnostics)

        # Duplicate exit IDs within same location
        report = validate_unique_ids((ex.id for ex in loc.exits), label="location_exit", code="duplicate_location_exit_id")
        diagnostics.extend(report.diagnostics)

        # Duplicate placed entity instance IDs within same location
        report = validate_unique_ids((pe.instance_id for pe in loc.placed_entities), label="location_placed_entity", code="duplicate_location_placed_entity_id")
        diagnostics.extend(report.diagnostics)

        # Non-start location must have default back exit
        if loc.id != locations_file.start_location:
            has_default_back = any("exit.default_back" in ex.tags for ex in loc.exits)
            if not has_default_back:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_default_back_exit",
                    message=f"Non-start location '{loc.id}' lacks a default/back exit (tag 'exit.default_back')",
                    object_id=loc.id,
                ))

        # Effective layers for this location
        effective_layer_names = set(get_effective_layers(loc, layers))

        # Validate exits
        for ex in loc.exits:
            # Missing entity ID (empty)
            if not ex.entity_id:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="exit_empty_entity_id",
                    message=f"Exit '{ex.id}' in location '{loc.id}' has no entityId",
                    object_id=ex.id,
                ))

            # Missing socket ID (empty)
            if not ex.socket_id:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="exit_empty_socket_id",
                    message=f"Exit '{ex.id}' in location '{loc.id}' has no socketId",
                    object_id=ex.id,
                ))

            # Exit layer not in effective layers
            if ex.layer and ex.layer not in effective_layer_names:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="exit_layer_not_in_effective_layers",
                    message=f"Exit '{ex.id}' layer '{ex.layer}' not in effective layers for location '{loc.id}'",
                    object_id=ex.id,
                ))

            # Missing target location ID
            if ex.target_location_id and ex.target_location_id not in location_ids:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_target_location",
                    message=f"Exit '{ex.id}' in location '{loc.id}' targets unknown location '{ex.target_location_id}'",
                    object_id=ex.id,
                ))

            # Missing referenced entity ID
            if ex.entity_id and ex.entity_id not in entity_id_set:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_entity_ref",
                    message=f"Exit '{ex.id}' references unknown entity '{ex.entity_id}'",
                    object_id=ex.id,
                ))

            # Invalid layer reference
            if ex.layer and ex.layer not in layers:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="invalid_layer_ref",
                    message=f"Exit '{ex.id}' uses unknown layer '{ex.layer}'",
                    object_id=ex.id,
                ))

            # Collect exit targets for reciprocal check
            exit_targets[loc.id].add(ex.target_location_id)

            # Missing referenced socket ID (use effective sockets)
            socket_ids = {s.id for s in effective_sockets}
            if ex.socket_id and ex.socket_id not in socket_ids:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_socket_ref",
                    message=f"Exit '{ex.id}' references unknown socket '{ex.socket_id}' in location '{loc.id}'",
                    object_id=ex.id,
                ))

        # Validate placed entities
        for pe in loc.placed_entities:
            # Missing entity ID (empty)
            if not pe.entity_id:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="placed_entity_empty_entity_id",
                    message=f"Placed entity '{pe.instance_id}' in location '{loc.id}' has no entityId",
                    object_id=pe.instance_id,
                ))

            # Missing socket ID (empty)
            if not pe.socket_id:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="placed_entity_empty_socket_id",
                    message=f"Placed entity '{pe.instance_id}' in location '{loc.id}' has no socketId",
                    object_id=pe.instance_id,
                ))

            # Layer not in effective layers
            if pe.layer and pe.layer not in effective_layer_names:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="placed_entity_layer_not_in_effective_layers",
                    message=f"Placed entity '{pe.instance_id}' layer '{pe.layer}' not in effective layers for location '{loc.id}'",
                    object_id=pe.instance_id,
                ))

            if pe.entity_id and pe.entity_id not in entity_id_set:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_entity_ref",
                    message=f"Placed entity '{pe.instance_id}' references unknown entity '{pe.entity_id}'",
                    object_id=pe.instance_id,
                ))

            socket_ids = {s.id for s in effective_sockets}
            if pe.socket_id and pe.socket_id not in socket_ids:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_socket_ref",
                    message=f"Placed entity '{pe.instance_id}' references unknown socket '{pe.socket_id}'",
                    object_id=pe.instance_id,
                ))

        # Location has no effective sockets
        if not effective_sockets:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="location_no_sockets",
                message=f"Location '{loc.id}' has no sockets",
                object_id=loc.id,
            ))

        # Location has no exits
        if not loc.exits:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="location_no_exits",
                message=f"Location '{loc.id}' has no exits",
                object_id=loc.id,
            ))

    # Missing reciprocal exits
    for loc_id, targets in exit_targets.items():
        for target_id in targets:
            if target_id in exit_targets and loc_id not in exit_targets[target_id]:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_reciprocal_exit",
                    message=f"Location '{loc_id}' links to '{target_id}', but no reciprocal exit exists",
                    object_id=loc_id,
                ))

    # Unreachable rooms: locations not reachable from start location
    reachable = _find_reachable(locations_file)
    for loc in locations_file.locations:
        if loc.id not in reachable:
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code="unreachable_location",
                message=f"Location '{loc.id}' is unreachable from start location",
                object_id=loc.id,
            ))

    # Graph node checks
    graph_node_ids = {n.location_id for n in locations_file.graph.nodes}
    for loc in locations_file.locations:
        if loc.id not in graph_node_ids:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="missing_graph_node",
                message=f"Location '{loc.id}' has no graph node (auto-fix available)",
                object_id=loc.id,
            ))

    location_id_set = {loc.id for loc in locations_file.locations}
    for gn in locations_file.graph.nodes:
        if gn.location_id not in location_id_set:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="orphan_graph_node",
                message=f"Graph node '{gn.location_id}' has no matching location",
                object_id=gn.location_id,
            ))

    # Validate weighted lists in ambient rules (use effective sockets)
    for loc in locations_file.locations:
        for socket in get_effective_sockets(loc, catalog):
            _validate_ambient_rule_weights(socket, diagnostics)

    return DiagnosticReport(diagnostics=diagnostics)


def _validate_socket_ambient(
    socket: object,
    room: RoomCatalogEntry,
    entity_ids: set[str],
    entity_tags_map: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> None:
    """Validate ambient fill configuration for a socket."""
    rule = socket.ambient_rule
    mode = rule.mode
    chance = socket.ambient_spawn_chance

    # ambientSpawnChance > 0 but mode is none → warn
    if chance > 0 and mode == "none":
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code="ambient_chance_but_no_rule",
            message=f"Socket '{socket.id}' in room '{room.id}' has ambientSpawnChance > 0 but mode is 'none'",
            object_id=socket.id,
        ))

    # ambientSpawnChance == 0 but ambient rule is configured → warn
    has_rule_config = (
        mode != "none"
        or rule.entries
        or rule.fill_entries
        or rule.required_tags
        or rule.forbidden_tags
    )
    if chance == 0 and has_rule_config:
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code="ambient_rule_no_chance",
            message=(
                f"Socket '{socket.id}' in room '{room.id}' has ambient rule configured "
                f"but ambientSpawnChance is 0%. Explicit placement may still use this socket."
            ),
            object_id=socket.id,
        ))

    # Mode-specific validation
    if mode == "weighted_entity_list":
        _validate_weighted_entity_list(socket, entity_ids, diagnostics)
    elif mode == "tag_query":
        _validate_tag_query_rule(socket, entity_ids, entity_tags_map, diagnostics)
    elif mode == "weighted_entries":
        _validate_weighted_entries(socket, entity_ids, entity_tags_map, diagnostics)


def _validate_weighted_entity_list(
    socket: object,
    entity_ids: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    """Validate weighted_entity_list ambient rule."""
    rule = socket.ambient_rule
    if not rule.entries:
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code="weighted_list_empty",
            message=f"Socket '{socket.id}' weighted_entity_list is empty",
            object_id=socket.id,
        ))
        return
    total = sum(e.weight for e in rule.entries)
    if total != 100:
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="weighted_list_not_100",
            message=f"Socket '{socket.id}' weighted_entity_list weights sum to {total}, expected 100",
            object_id=socket.id,
        ))
    # Check entity references
    for entry in rule.entries:
        if entry.entity_id and entity_ids and entry.entity_id not in entity_ids:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="ambient_entity_id_missing",
                message=f"Socket '{socket.id}' references unknown entity '{entry.entity_id}' in weighted_entity_list",
                object_id=socket.id,
            ))


def _validate_tag_query_rule(
    socket: object,
    entity_ids: set[str],
    entity_tags_map: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> None:
    """Validate tag_query ambient rule."""
    rule = socket.ambient_rule
    if not rule.required_tags and not rule.forbidden_tags:
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code="tag_query_no_tags",
            message=f"Socket '{socket.id}' tag_query mode has no tags specified (matches all entities)",
            object_id=socket.id,
        ))
        return
    # Check for zero matching entities
    if entity_tags_map:
        matching = 0
        for eid, tags in entity_tags_map.items():
            if matches_all(tags, rule.required_tags) and matches_none(tags, rule.forbidden_tags):
                matching += 1
        if matching == 0:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="tag_query_zero_matches",
                message=f"Socket '{socket.id}' tag_query matches zero entities",
                object_id=socket.id,
            ))


def _validate_weighted_entries(
    socket: object,
    entity_ids: set[str],
    entity_tags_map: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> None:
    """Validate weighted_entries ambient rule."""
    rule = socket.ambient_rule
    if not rule.fill_entries:
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code="weighted_entries_empty",
            message=f"Socket '{socket.id}' weighted_entries list is empty",
            object_id=socket.id,
        ))
        return
    total = sum(e.weight for e in rule.fill_entries)
    if total != 100:
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="weighted_entries_not_100",
            message=f"Socket '{socket.id}' weighted_entries weights sum to {total}, expected 100",
            object_id=socket.id,
        ))
    # Check per-entry references
    for entry in rule.fill_entries:
        if entry.type == "entity" and entry.entity_id and entity_ids and entry.entity_id not in entity_ids:
            diagnostics.append(Diagnostic(
                severity=Severity.WARNING,
                code="ambient_entity_id_missing",
                message=f"Socket '{socket.id}' references unknown entity '{entry.entity_id}' in weighted_entries",
                object_id=socket.id,
            ))
        elif entry.type == "tag_query":
            if entity_tags_map:
                matching = 0
                for eid, tags in entity_tags_map.items():
                    if matches_all(tags, entry.required_tags) and matches_none(tags, entry.forbidden_tags):
                        matching += 1
                if matching == 0:
                    diagnostics.append(Diagnostic(
                        severity=Severity.WARNING,
                        code="weighted_entry_tag_query_zero_matches",
                        message=f"Socket '{socket.id}' weighted_entries tag_query entry matches zero entities",
                        object_id=socket.id,
                    ))


def _validate_ambient_rule_weights(
    socket: object, diagnostics: list[Diagnostic]
) -> None:
    """Validate weighted entity list rules in socket ambient rules (for locations)."""
    rule = socket.ambient_rule
    if rule.mode == "weighted_entity_list" and rule.entries:
        total = sum(e.weight for e in rule.entries)
        if total != 100:
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code="weighted_list_not_100",
                message=f"Socket '{socket.id}' weighted_entity_list weights sum to {total}, expected 100",
                object_id=socket.id,
            ))
    if rule.mode == "weighted_entries" and rule.fill_entries:
        total = sum(e.weight for e in rule.fill_entries)
        if total != 100:
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code="weighted_entries_not_100",
                message=f"Socket '{socket.id}' weighted_entries weights sum to {total}, expected 100",
                object_id=socket.id,
            ))


def _find_reachable(locations_file: LocationsFile) -> set[str]:
    """BFS from start location following exits to find all reachable locations."""
    start = locations_file.start_location
    location_ids = {loc.id for loc in locations_file.locations}
    if start not in location_ids:
        return set()

    # Build adjacency from exits
    adjacency: dict[str, set[str]] = defaultdict(set)
    for loc in locations_file.locations:
        for ex in loc.exits:
            if ex.target_location_id in location_ids:
                adjacency[loc.id].add(ex.target_location_id)

    visited: set[str] = set()
    queue = [start]
    while queue:
        current = queue.pop(0)
        if current in visited:
            continue
        visited.add(current)
        for neighbor in adjacency[current]:
            if neighbor not in visited:
                queue.append(neighbor)

    return visited
    
import json
from pathlib import Path
from typing import Any

from behemoth_location_tool.model.project import ProjectConfig


def _resolve_project_path(project: ProjectConfig, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()

    game_root = Path(project.game_root)
    if game_root.is_absolute():
        return (game_root / path).resolve()

    # ProjectConfig should normally already hold resolved game_root by now.
    return (Path.cwd() / game_root / path).resolve()


def _game_data_root(project: ProjectConfig) -> Path:
    if hasattr(project, "absolute_game_data_root"):
        return Path(project.absolute_game_data_root).resolve()

    return _resolve_project_path(project, project.game_data_root)


def _read_json_file(path: Path, diagnostics: list[Diagnostic], *, code_prefix: str) -> dict[str, Any] | None:
    if not path.exists():
        diagnostics.append(Diagnostic(
            severity=Severity.WARNING,
            code=f"{code_prefix}_missing_file",
            message=f"File does not exist: {path}",
            file=str(path),
            source="python",
        ))
        return None

    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code=f"{code_prefix}_parse_error",
            message=f"Failed to parse JSON file '{path}': {exc}",
            file=str(path),
            source="python",
        ))
        return None


def _load_entities_from_game_data(game_data_root: Path, diagnostics: list[Diagnostic]) -> list[EntityDefinition]:
    entities: list[EntityDefinition] = []

    manifest_path = game_data_root / "entities.json"
    manifest = _read_json_file(manifest_path, diagnostics, code_prefix="entities_manifest")
    if manifest is None:
        return entities
    if "schemaVersion" in manifest:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="entities_manifest_legacy_version",
                message="entities.json uses deprecated 'schemaVersion'; expected 'version': 2",
                file=str(manifest_path),
                source="python",
            )
        )
        return entities
    if manifest.get("version") != 2:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="entities_manifest_invalid_version",
                message=f"entities.json must have version 2, got {manifest.get('version')!r}",
                file=str(manifest_path),
                source="python",
            )
        )
        return entities

    includes = manifest.get("includes", [])
    if not isinstance(includes, list):
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="entities_manifest_invalid_includes",
            message="entities.json field 'includes' must be a list.",
            file=str(manifest_path),
            source="python",
        ))
        return entities

    for include in includes:
        if not isinstance(include, str):
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code="entities_manifest_invalid_include",
                message=f"entities.json include must be a string, got: {include!r}",
                file=str(manifest_path),
                source="python",
            ))
            continue

        module_path = (game_data_root / include).resolve()
        module_data = _read_json_file(module_path, diagnostics, code_prefix="entity_module")
        if module_data is None:
            continue
        if "schemaVersion" in module_data:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="entity_module_legacy_version",
                    message=f"Entity module '{module_path}' uses deprecated 'schemaVersion'; expected 'version': 2",
                    file=str(module_path),
                    source="python",
                )
            )
            continue
        if module_data.get("version") != 2:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="entity_module_invalid_version",
                    message=f"Entity module '{module_path}' must have version 2, got {module_data.get('version')!r}",
                    file=str(module_path),
                    source="python",
                )
            )
            continue

        module_entities = module_data.get("entities", [])
        if not isinstance(module_entities, list):
            diagnostics.append(Diagnostic(
                severity=Severity.ERROR,
                code="entity_module_invalid_entities",
                message=f"Entity module '{module_path}' field 'entities' must be a list.",
                file=str(module_path),
                source="python",
            ))
            continue

        for index, entity_data in enumerate(module_entities):
            try:
                entities.append(EntityDefinition.model_validate(entity_data))
            except Exception as exc:
                diagnostics.append(Diagnostic(
                    severity=Severity.ERROR,
                    code="entity_parse_error",
                    message=f"Failed to parse entity #{index} in '{module_path}': {exc}",
                    file=str(module_path),
                    source="python",
                ))

    return entities


def _load_room_catalog(game_data_root: Path, diagnostics: list[Diagnostic]) -> RoomCatalog | None:
    path = game_data_root / "room_catalog.json"
    data = _read_json_file(path, diagnostics, code_prefix="room_catalog")
    if data is None:
        return None
    if "schemaVersion" in data:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="room_catalog_legacy_version",
                message="room_catalog.json uses deprecated 'schemaVersion'; expected 'version': 2",
                file=str(path),
                source="python",
            )
        )
        return None
    if data.get("version") != 2:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="room_catalog_invalid_version",
                message=f"room_catalog.json must have version 2, got {data.get('version')!r}",
                file=str(path),
                source="python",
            )
        )
        return None

    try:
        return RoomCatalog.model_validate(data)
    except Exception as exc:
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="room_catalog_parse_error",
            message=f"Failed to parse room_catalog.json: {exc}",
            file=str(path),
            source="python",
        ))
        return None


def _load_locations(game_data_root: Path, diagnostics: list[Diagnostic]) -> LocationsFile | None:
    path = game_data_root / "locations.json"
    data = _read_json_file(path, diagnostics, code_prefix="locations")
    if data is None:
        return None
    if "schemaVersion" in data:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="locations_legacy_version",
                message="locations.json uses deprecated 'schemaVersion'; expected 'version': 2",
                file=str(path),
                source="python",
            )
        )
        return None
    if data.get("version") != 2:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="locations_invalid_version",
                message=f"locations.json must have version 2, got {data.get('version')!r}",
                file=str(path),
                source="python",
            )
        )
        return None

    try:
        return LocationsFile.model_validate(data)
    except Exception as exc:
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="locations_parse_error",
            message=f"Failed to parse locations.json: {exc}",
            file=str(path),
            source="python",
        ))
        return None


def _load_tags_index(game_data_root: Path, diagnostics: list[Diagnostic]) -> TagIndex | None:
    path = game_data_root / "tags.json"
    data = _read_json_file(path, diagnostics, code_prefix="tags")
    if data is None:
        return None
    try:
        if isinstance(data, dict) and data.get("version") not in (None, 2):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="tags_invalid_version",
                    message=f"tags.json must have version 2, got {data.get('version')!r}",
                    file=str(path),
                    source="python",
                )
            )
            return None
        return TagIndex(known_tags=extract_known_tags(data))
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="tags_parse_error",
                message=f"Failed to parse tags.json: {exc}",
                file=str(path),
                source="python",
            )
        )
        return None


def _validate_tag_references(
    tag_index: TagIndex,
    entities: list[EntityDefinition],
    room_catalog: RoomCatalog | None,
    locations_file: LocationsFile | None,
) -> list[Diagnostic]:
    diagnostics: list[Diagnostic] = []

    def _check_tags(tags: list[str], *, object_id: str, object_type: str, field: str) -> None:
        for tag in tags:
            if not tag_index.is_known(tag):
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="invalid_tag_reference",
                        message=f"Unknown tag '{tag}' in {object_type}.{field}",
                        object_id=object_id,
                        object_type=object_type,
                        source="python",
                    )
                )

    for entity in entities:
        _check_tags(entity.tags, object_id=entity.id, object_type="entity", field="tags")
        _check_tags(
            entity.spawn_rules.required_context_tags,
            object_id=entity.id,
            object_type="entity",
            field="spawnRules.requiredContextTags",
        )
        _check_tags(
            entity.spawn_rules.forbidden_context_tags,
            object_id=entity.id,
            object_type="entity",
            field="spawnRules.forbiddenContextTags",
        )

    if room_catalog is not None:
        for room in room_catalog.rooms:
            _check_tags(room.tags, object_id=room.id, object_type="room", field="tags")
            for socket in room.sockets:
                _check_tags(socket.required_tags, object_id=socket.id, object_type="socket", field="requiredTags")
                _check_tags(socket.forbidden_tags, object_id=socket.id, object_type="socket", field="forbiddenTags")
                _check_tags(
                    socket.ambient_rule.required_tags,
                    object_id=socket.id,
                    object_type="socket",
                    field="ambientRule.requiredTags",
                )
                _check_tags(
                    socket.ambient_rule.forbidden_tags,
                    object_id=socket.id,
                    object_type="socket",
                    field="ambientRule.forbiddenTags",
                )

    if locations_file is not None:
        for location in locations_file.locations:
            _check_tags(location.tags, object_id=location.id, object_type="location", field="tags")
            for socket in location.sockets:
                _check_tags(socket.required_tags, object_id=socket.id, object_type="socket", field="requiredTags")
                _check_tags(socket.forbidden_tags, object_id=socket.id, object_type="socket", field="forbiddenTags")
            for exit_def in location.exits:
                _check_tags(exit_def.tags, object_id=exit_def.id, object_type="exit", field="tags")
                _check_tags(
                    exit_def.conditions.requires_tags,
                    object_id=exit_def.id,
                    object_type="exit",
                    field="conditions.requiresTags",
                )
                _check_tags(
                    exit_def.conditions.forbidden_tags,
                    object_id=exit_def.id,
                    object_type="exit",
                    field="conditions.forbiddenTags",
                )

    return diagnostics


def validate_project(project: ProjectConfig) -> DiagnosticReport:
    """Project-level validation entry point used by ValidateTab."""
    diagnostics: list[Diagnostic] = []

    game_data_root = _game_data_root(project)

    if not game_data_root.exists():
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="game_data_root_missing",
            message=f"Game data root does not exist: {game_data_root}",
            file=str(game_data_root),
            source="python",
        ))
        return DiagnosticReport(diagnostics=diagnostics)

    entities = _load_entities_from_game_data(game_data_root, diagnostics)
    room_catalog = _load_room_catalog(game_data_root, diagnostics)
    locations_file = _load_locations(game_data_root, diagnostics)
    tag_index = _load_tags_index(game_data_root, diagnostics)

    diagnostics.extend(validate_entities(entities).diagnostics)

    if room_catalog is not None:
        diagnostics.extend(validate_room_catalog(room_catalog, entities=entities).diagnostics)

    if locations_file is not None:
        diagnostics.extend(validate_locations(
            locations_file,
            catalog=room_catalog,
            entities=entities,
            project_layers=DEFAULT_PROJECT_LAYERS,
        ).diagnostics)

    if tag_index is not None:
        diagnostics.extend(_validate_tag_references(tag_index, entities, room_catalog, locations_file))

    return DiagnosticReport(diagnostics=diagnostics)
