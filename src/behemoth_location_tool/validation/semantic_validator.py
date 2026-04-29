from __future__ import annotations

from collections import defaultdict
from collections.abc import Iterable

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import (
    DEFAULT_PROJECT_LAYERS,
    LocationsFile,
    get_effective_background,
    get_effective_layers,
    get_effective_sockets,
)
from behemoth_location_tool.model.room import RoomCatalog, RoomCatalogEntry, SocketDefinition
from behemoth_location_tool.model.tags import matches_all, matches_none
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity


def validate_unique_ids(ids: Iterable[str], *, label: str, code: str = "duplicate_id") -> DiagnosticReport:
    seen: set[str] = set()
    diagnostics: list[Diagnostic] = []
    for item_id in ids:
        if item_id in seen:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code=code,
                    message=f"Duplicate {label} id: {item_id}",
                    object_id=item_id,
                )
            )
        seen.add(item_id)
    return DiagnosticReport(diagnostics=diagnostics)


def validate_entities(entities: list[EntityDefinition]) -> DiagnosticReport:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(
        validate_unique_ids(
            (entity.id for entity in entities),
            label="entity",
            code="duplicate_entity_id",
        ).diagnostics
    )

    interactable_tags = {"item.pickable", "character.talkable"}
    for entity in entities:
        if "entity.spawnable" in entity.tags and entity.render is None:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="spawnable_no_render",
                    message=f"Entity '{entity.id}' is marked spawnable but has no render data",
                    object_id=entity.id,
                )
            )

        if interactable_tags.intersection(entity.tags) and (
            entity.render is None or entity.render.clickable_rect is None
        ):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="interactable_no_clickable_rect",
                    message=f"Entity '{entity.id}' is interactable but has no clickable rectangle",
                    object_id=entity.id,
                )
            )

    return DiagnosticReport(diagnostics=diagnostics)


def validate_room_catalog(
    catalog: RoomCatalog,
    *,
    entities: list[EntityDefinition] | None = None,
) -> DiagnosticReport:
    diagnostics: list[Diagnostic] = []
    diagnostics.extend(
        validate_unique_ids(
            (room.id for room in catalog.rooms),
            label="room_catalog",
            code="duplicate_room_catalog_id",
        ).diagnostics
    )

    entity_ids = {entity.id for entity in entities} if entities else set()
    entity_tags_map = {entity.id: set(entity.tags) for entity in entities or []}

    for room in catalog.rooms:
        diagnostics.extend(
            validate_unique_ids(
                (socket.id for socket in room.sockets),
                label="catalog_socket_template",
                code="duplicate_catalog_socket_template_id",
            ).diagnostics
        )

        if room.design_size.w != 1920 or room.design_size.h != 1080:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="room_overrides_design_size",
                    message=(
                        f"Room '{room.id}' overrides project design size "
                        f"({room.design_size.w}x{room.design_size.h})"
                    ),
                    object_id=room.id,
                )
            )

        for socket in room.sockets:
            _validate_socket_ambient(socket, room, entity_ids, entity_tags_map, diagnostics)
            if entities:
                _check_socket_matching_spawnables(socket, room, entities, diagnostics)

        if not room.sockets:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="room_no_sockets",
                    message=f"Room catalog entry '{room.id}' has no sockets",
                    object_id=room.id,
                )
            )

        if not room.background_image:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="catalog_room_missing_background",
                    message=f"Room catalog entry '{room.id}' has no background image",
                    object_id=room.id,
                )
            )

    return DiagnosticReport(diagnostics=diagnostics)


def validate_locations(
    locations_file: LocationsFile,
    *,
    catalog: RoomCatalog | None = None,
    entities: list[EntityDefinition] | None = None,
    project_layers: list[str] | None = None,
) -> DiagnosticReport:
    diagnostics: list[Diagnostic] = []
    layers = project_layers or list(DEFAULT_PROJECT_LAYERS)

    location_ids = {loc.id for loc in locations_file.locations}
    if locations_file.start_location not in location_ids:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="missing_start_location",
                message=f"startLocation '{locations_file.start_location}' does not exist",
                object_id=locations_file.start_location,
            )
        )

    diagnostics.extend(
        validate_unique_ids(
            (loc.id for loc in locations_file.locations),
            label="location",
            code="duplicate_location_id",
        ).diagnostics
    )

    entity_id_set = {entity.id for entity in entities} if entities else set()
    catalog_id_set = {room.id for room in catalog.rooms} if catalog else set()
    exit_targets: dict[str, set[str]] = defaultdict(set)

    for loc in locations_file.locations:
        exit_targets[loc.id]
        _validate_location_background(
            loc_id=loc.id,
            catalog_room_id=loc.catalog_room_id,
            background_overridden=loc.background_overridden,
            effective_background=get_effective_background(loc, catalog),
            catalog_id_set=catalog_id_set,
            diagnostics=diagnostics,
        )

        if loc.catalog_room_id and loc.catalog_room_id not in catalog_id_set:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_catalog_room",
                    message=f"Location '{loc.id}' references unknown catalog room '{loc.catalog_room_id}'",
                    object_id=loc.id,
                )
            )

        effective_sockets = get_effective_sockets(loc, catalog)
        socket_ids = {socket.id for socket in effective_sockets}
        effective_layer_names = set(get_effective_layers(loc, layers))

        diagnostics.extend(
            validate_unique_ids(
                (socket.id for socket in effective_sockets),
                label="location_socket",
                code="duplicate_location_socket_id",
            ).diagnostics
        )
        diagnostics.extend(
            validate_unique_ids(
                (exit_def.id for exit_def in loc.exits),
                label="location_exit",
                code="duplicate_location_exit_id",
            ).diagnostics
        )
        diagnostics.extend(
            validate_unique_ids(
                (entity.instance_id for entity in loc.placed_entities),
                label="location_placed_entity",
                code="duplicate_location_placed_entity_id",
            ).diagnostics
        )

        if loc.id != locations_file.start_location and not any(
            "exit.default_back" in exit_def.tags for exit_def in loc.exits
        ):
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="missing_default_back_exit",
                    message=(
                        f"Non-start location '{loc.id}' lacks a default/back exit "
                        "(tag 'exit.default_back')"
                    ),
                    object_id=loc.id,
                )
            )

        for exit_def in loc.exits:
            if exit_def.conditions.requires_flags or exit_def.conditions.forbidden_flags:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        code="flag_conditions_not_evaluated",
                        message=(
                            f"Exit '{exit_def.id}' in location '{loc.id}' stores flag conditions, "
                            "but preview/runtime validation does not evaluate flags yet"
                        ),
                        object_id=exit_def.id,
                    )
                )
            _validate_exit(
                location_id=loc.id,
                exit_id=exit_def.id,
                entity_id=exit_def.entity_id,
                socket_id=exit_def.socket_id,
                layer=exit_def.layer,
                target_location_id=exit_def.target_location_id,
                valid_location_ids=location_ids,
                known_entity_ids=entity_id_set,
                socket_ids=socket_ids,
                effective_layers=effective_layer_names,
                project_layers=set(layers),
                diagnostics=diagnostics,
            )
            exit_targets[loc.id].add(exit_def.target_location_id)

        for placed in loc.placed_entities:
            _validate_placed_entity(
                location_id=loc.id,
                instance_id=placed.instance_id,
                entity_id=placed.entity_id,
                socket_id=placed.socket_id,
                layer=placed.layer,
                known_entity_ids=entity_id_set,
                socket_ids=socket_ids,
                effective_layers=effective_layer_names,
                diagnostics=diagnostics,
            )

        if not effective_sockets:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="location_no_sockets",
                    message=f"Location '{loc.id}' has no sockets",
                    object_id=loc.id,
                )
            )
        if not loc.exits:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="location_no_exits",
                    message=f"Location '{loc.id}' has no exits",
                    object_id=loc.id,
                )
            )

    for loc_id, targets in exit_targets.items():
        for target_id in targets:
            if target_id in location_ids and loc_id not in exit_targets[target_id]:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.ERROR,
                        code="missing_reciprocal_exit",
                        message=(
                            f"Location '{loc_id}' links to '{target_id}', "
                            "but no reciprocal exit exists"
                        ),
                        object_id=loc_id,
                    )
                )

    reachable = _find_reachable(locations_file)
    for loc in locations_file.locations:
        if loc.id not in reachable:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="unreachable_location",
                    message=f"Location '{loc.id}' is unreachable from start location",
                    object_id=loc.id,
                )
            )

    graph_node_ids = {node.location_id for node in locations_file.graph.nodes}
    for loc in locations_file.locations:
        if loc.id not in graph_node_ids:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="missing_graph_node",
                    message=f"Location '{loc.id}' has no graph node (auto-fix available)",
                    object_id=loc.id,
                )
            )

    valid_location_ids = {location.id for location in locations_file.locations}
    for node in locations_file.graph.nodes:
        if node.location_id not in valid_location_ids:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="orphan_graph_node",
                    message=f"Graph node '{node.location_id}' has no matching location",
                    object_id=node.location_id,
                )
            )

    for loc in locations_file.locations:
        for socket in get_effective_sockets(loc, catalog):
            _validate_ambient_rule_weights(socket, diagnostics)

    return DiagnosticReport(diagnostics=diagnostics)


def _check_socket_matching_spawnables(
    socket: SocketDefinition,
    room: RoomCatalogEntry,
    entities: list[EntityDefinition],
    diagnostics: list[Diagnostic],
) -> None:
    has_match = False
    for entity in entities:
        if "entity.spawnable" not in entity.tags:
            continue
        if matches_all(set(entity.tags), socket.required_tags):
            has_match = True
            break
    if not has_match and socket.required_tags:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="socket_no_matching_spawnables",
                message=f"Socket '{socket.id}' in room '{room.id}' has no matching spawnables",
                object_id=socket.id,
            )
        )


def _validate_socket_ambient(
    socket: SocketDefinition,
    room: RoomCatalogEntry,
    entity_ids: set[str],
    entity_tags_map: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> None:
    rule = socket.ambient_rule
    chance = socket.ambient_spawn_chance

    if chance > 0 and rule.mode == "none":
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="ambient_chance_but_no_rule",
                message=(
                    f"Socket '{socket.id}' in room '{room.id}' has ambientSpawnChance > 0 "
                    "but mode is 'none'"
                ),
                object_id=socket.id,
            )
        )

    has_rule_config = any(
        (
            rule.mode != "none",
            rule.entries,
            rule.fill_entries,
            rule.required_tags,
            rule.forbidden_tags,
        )
    )
    if chance == 0 and has_rule_config:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="ambient_rule_no_chance",
                message=(
                    f"Socket '{socket.id}' in room '{room.id}' has ambient rule configured "
                    "but ambientSpawnChance is 0%. Explicit placement may still use this socket."
                ),
                object_id=socket.id,
            )
        )

    if rule.mode == "weighted_entity_list":
        _validate_weighted_entity_list(socket, entity_ids, diagnostics)
    elif rule.mode == "tag_query":
        _validate_tag_query_rule(socket, entity_tags_map, diagnostics)
    elif rule.mode == "weighted_entries":
        _validate_weighted_entries(socket, entity_ids, entity_tags_map, diagnostics)


def _validate_weighted_entity_list(
    socket: SocketDefinition,
    entity_ids: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    rule = socket.ambient_rule
    if not rule.entries:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="weighted_list_empty",
                message=f"Socket '{socket.id}' weighted_entity_list is empty",
                object_id=socket.id,
            )
        )
        return

    total = sum(entry.weight for entry in rule.entries)
    if total != 100:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="weighted_list_not_100",
                message=(
                    f"Socket '{socket.id}' weighted_entity_list weights sum to {total}, "
                    "expected 100"
                ),
                object_id=socket.id,
            )
        )

    for entry in rule.entries:
        if entry.entity_id and entity_ids and entry.entity_id not in entity_ids:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="ambient_entity_id_missing",
                    message=(
                        f"Socket '{socket.id}' references unknown entity '{entry.entity_id}' "
                        "in weighted_entity_list"
                    ),
                    object_id=socket.id,
                )
            )


def _validate_tag_query_rule(
    socket: SocketDefinition,
    entity_tags_map: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> None:
    rule = socket.ambient_rule
    if not rule.required_tags and not rule.forbidden_tags:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="tag_query_no_tags",
                message=f"Socket '{socket.id}' tag_query mode has no tags specified (matches all entities)",
                object_id=socket.id,
            )
        )
        return

    if entity_tags_map:
        matching = 0
        for tags in entity_tags_map.values():
            if matches_all(tags, rule.required_tags) and matches_none(tags, rule.forbidden_tags):
                matching += 1
        if matching == 0:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="tag_query_zero_matches",
                    message=f"Socket '{socket.id}' tag_query matches zero entities",
                    object_id=socket.id,
                )
            )


def _validate_weighted_entries(
    socket: SocketDefinition,
    entity_ids: set[str],
    entity_tags_map: dict[str, set[str]],
    diagnostics: list[Diagnostic],
) -> None:
    rule = socket.ambient_rule
    if not rule.fill_entries:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="weighted_entries_empty",
                message=f"Socket '{socket.id}' weighted_entries list is empty",
                object_id=socket.id,
            )
        )
        return

    total = sum(entry.weight for entry in rule.fill_entries)
    if total != 100:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="weighted_entries_not_100",
                message=(
                    f"Socket '{socket.id}' weighted_entries weights sum to {total}, "
                    "expected 100"
                ),
                object_id=socket.id,
            )
        )

    for entry in rule.fill_entries:
        if entry.type == "entity" and entry.entity_id and entity_ids and entry.entity_id not in entity_ids:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.WARNING,
                    code="ambient_entity_id_missing",
                    message=(
                        f"Socket '{socket.id}' references unknown entity '{entry.entity_id}' "
                        "in weighted_entries"
                    ),
                    object_id=socket.id,
                )
            )
        elif entry.type == "tag_query" and entity_tags_map:
            matching = 0
            for tags in entity_tags_map.values():
                if matches_all(tags, entry.required_tags) and matches_none(tags, entry.forbidden_tags):
                    matching += 1
            if matching == 0:
                diagnostics.append(
                    Diagnostic(
                        severity=Severity.WARNING,
                        code="weighted_entry_tag_query_zero_matches",
                        message=(
                            f"Socket '{socket.id}' weighted_entries tag_query entry "
                            "matches zero entities"
                        ),
                        object_id=socket.id,
                    )
                )


def _validate_ambient_rule_weights(socket: SocketDefinition, diagnostics: list[Diagnostic]) -> None:
    rule = socket.ambient_rule
    if rule.mode == "weighted_entity_list" and rule.entries:
        total = sum(entry.weight for entry in rule.entries)
        if total != 100:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="weighted_list_not_100",
                    message=(
                        f"Socket '{socket.id}' weighted_entity_list weights sum to {total}, "
                        "expected 100"
                    ),
                    object_id=socket.id,
                )
            )

    if rule.mode == "weighted_entries" and rule.fill_entries:
        total = sum(entry.weight for entry in rule.fill_entries)
        if total != 100:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="weighted_entries_not_100",
                    message=(
                        f"Socket '{socket.id}' weighted_entries weights sum to {total}, "
                        "expected 100"
                    ),
                    object_id=socket.id,
                )
            )


def _validate_location_background(
    *,
    loc_id: str,
    catalog_room_id: str,
    background_overridden: bool,
    effective_background: str | None,
    catalog_id_set: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    if effective_background:
        return
    if background_overridden:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="location_missing_background_override",
                message=f"Location '{loc_id}' has background override set but no background image",
                object_id=loc_id,
            )
        )
        return
    if catalog_room_id and catalog_room_id in catalog_id_set:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="location_missing_background_inherited",
                message=(
                    f"Location '{loc_id}' inherits empty background from catalog room "
                    f"'{catalog_room_id}'"
                ),
                object_id=loc_id,
            )
        )
        return
    diagnostics.append(
        Diagnostic(
            severity=Severity.WARNING,
            code="location_missing_background",
            message=f"Location '{loc_id}' has no effective background image",
            object_id=loc_id,
        )
    )


def _validate_exit(
    *,
    location_id: str,
    exit_id: str,
    entity_id: str,
    socket_id: str,
    layer: str,
    target_location_id: str,
    valid_location_ids: set[str],
    known_entity_ids: set[str],
    socket_ids: set[str],
    effective_layers: set[str],
    project_layers: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    if not entity_id:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="exit_empty_entity_id",
                message=f"Exit '{exit_id}' in location '{location_id}' has no entityId",
                object_id=exit_id,
            )
        )
    if not socket_id:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="exit_empty_socket_id",
                message=f"Exit '{exit_id}' in location '{location_id}' has no socketId",
                object_id=exit_id,
            )
        )
    if layer and layer not in effective_layers:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="exit_layer_not_in_effective_layers",
                message=(
                    f"Exit '{exit_id}' layer '{layer}' not in effective layers for location "
                    f"'{location_id}'"
                ),
                object_id=exit_id,
            )
        )
    if target_location_id and target_location_id not in valid_location_ids:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="missing_target_location",
                message=(
                    f"Exit '{exit_id}' in location '{location_id}' targets unknown location "
                    f"'{target_location_id}'"
                ),
                object_id=exit_id,
            )
        )
    if entity_id and entity_id not in known_entity_ids:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="missing_entity_ref",
                message=f"Exit '{exit_id}' references unknown entity '{entity_id}'",
                object_id=exit_id,
            )
        )
    if layer and layer not in project_layers:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="invalid_layer_ref",
                message=f"Exit '{exit_id}' uses unknown layer '{layer}'",
                object_id=exit_id,
            )
        )
    if socket_id and socket_id not in socket_ids:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="missing_socket_ref",
                message=(
                    f"Exit '{exit_id}' references unknown socket '{socket_id}' in location "
                    f"'{location_id}'"
                ),
                object_id=exit_id,
            )
        )


def _validate_placed_entity(
    *,
    location_id: str,
    instance_id: str,
    entity_id: str,
    socket_id: str,
    layer: str | None,
    known_entity_ids: set[str],
    socket_ids: set[str],
    effective_layers: set[str],
    diagnostics: list[Diagnostic],
) -> None:
    if not entity_id:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="placed_entity_empty_entity_id",
                message=f"Placed entity '{instance_id}' in location '{location_id}' has no entityId",
                object_id=instance_id,
            )
        )
    if not socket_id:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="placed_entity_empty_socket_id",
                message=f"Placed entity '{instance_id}' in location '{location_id}' has no socketId",
                object_id=instance_id,
            )
        )
    if layer and layer not in effective_layers:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="placed_entity_layer_not_in_effective_layers",
                message=(
                    f"Placed entity '{instance_id}' layer '{layer}' not in effective layers "
                    f"for location '{location_id}'"
                ),
                object_id=instance_id,
            )
        )
    if entity_id and entity_id not in known_entity_ids:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="missing_entity_ref",
                message=f"Placed entity '{instance_id}' references unknown entity '{entity_id}'",
                object_id=instance_id,
            )
        )
    if socket_id and socket_id not in socket_ids:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="missing_socket_ref",
                message=f"Placed entity '{instance_id}' references unknown socket '{socket_id}'",
                object_id=instance_id,
            )
        )


def _find_reachable(locations_file: LocationsFile) -> set[str]:
    start = locations_file.start_location
    location_ids = {loc.id for loc in locations_file.locations}
    if start not in location_ids:
        return set()

    adjacency: dict[str, set[str]] = defaultdict(set)
    for location in locations_file.locations:
        for exit_def in location.exits:
            if exit_def.target_location_id in location_ids:
                adjacency[location.id].add(exit_def.target_location_id)

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
