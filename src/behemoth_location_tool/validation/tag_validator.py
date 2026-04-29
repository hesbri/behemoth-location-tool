from __future__ import annotations

from pathlib import Path
from typing import Any

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationsFile
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.model.tags import TagIndex, extract_known_tags
from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity


def load_tags_index(
    tags_raw: Any,
    *,
    file_path: Path,
    diagnostics: list[Diagnostic],
) -> TagIndex | None:
    if tags_raw is None:
        return None
    try:
        return TagIndex(known_tags=extract_known_tags(tags_raw))
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="tags_parse_error",
                message=f"Failed to parse tags.json: {exc}",
                file=str(file_path),
                source="python",
            )
        )
        return None


def validate_tag_references(
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
                _check_tags(
                    socket.required_tags,
                    object_id=socket.id,
                    object_type="socket",
                    field="requiredTags",
                )
                _check_tags(
                    socket.forbidden_tags,
                    object_id=socket.id,
                    object_type="socket",
                    field="forbiddenTags",
                )
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
                _check_tags(
                    socket.required_tags,
                    object_id=socket.id,
                    object_type="socket",
                    field="requiredTags",
                )
                _check_tags(
                    socket.forbidden_tags,
                    object_id=socket.id,
                    object_type="socket",
                    field="forbiddenTags",
                )
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
