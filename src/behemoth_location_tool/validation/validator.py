from __future__ import annotations

from collections.abc import Iterable

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationsFile
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.validation.diagnostics import DiagnosticReport
from behemoth_location_tool.validation.semantic_validator import (
    validate_entities as _validate_entities,
)
from behemoth_location_tool.validation.semantic_validator import (
    validate_locations as _validate_locations,
)
from behemoth_location_tool.validation.semantic_validator import (
    validate_room_catalog as _validate_room_catalog,
)
from behemoth_location_tool.validation.semantic_validator import (
    validate_unique_ids as _validate_unique_ids,
)
from behemoth_location_tool.validation.validation_service import (
    validate_project as _validate_project,
)


def validate_unique_ids(ids: Iterable[str], *, label: str, code: str = "duplicate_id") -> DiagnosticReport:
    return _validate_unique_ids(ids, label=label, code=code)


def validate_entities(entities: list[EntityDefinition]) -> DiagnosticReport:
    return _validate_entities(entities)


def validate_room_catalog(
    catalog: RoomCatalog,
    *,
    entities: list[EntityDefinition] | None = None,
) -> DiagnosticReport:
    return _validate_room_catalog(catalog, entities=entities)


def validate_locations(
    locations_file: LocationsFile,
    *,
    catalog: RoomCatalog | None = None,
    entities: list[EntityDefinition] | None = None,
    project_layers: list[str] | None = None,
) -> DiagnosticReport:
    return _validate_locations(
        locations_file,
        catalog=catalog,
        entities=entities,
        project_layers=project_layers,
    )


def validate_project(project: ProjectConfig) -> DiagnosticReport:
    return _validate_project(project)
