from __future__ import annotations

from pathlib import Path

from behemoth_location_tool.model.entity import EntityDefinition, EntityManifest, EntityModule
from behemoth_location_tool.model.location import DEFAULT_PROJECT_LAYERS, LocationsFile
from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.validation.asset_validator import validate_assets
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity
from behemoth_location_tool.validation.schema_validator import (
    validate_json_against_schema,
    validate_json_file_against_schema,
)
from behemoth_location_tool.validation.semantic_validator import (
    validate_entities,
    validate_locations,
    validate_room_catalog,
)
from behemoth_location_tool.validation.tag_validator import load_tags_index, validate_tag_references


def validate_project(project: ProjectConfig) -> DiagnosticReport:
    diagnostics: list[Diagnostic] = []

    game_data_root = _game_data_root(project)
    if not game_data_root.exists():
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="game_data_root_missing",
                message=f"Game data root does not exist: {game_data_root}",
                file=str(game_data_root),
                source="python",
            )
        )
        return DiagnosticReport(diagnostics=diagnostics)

    entities = _load_entities(game_data_root, diagnostics)
    room_catalog = _load_room_catalog(game_data_root, diagnostics)
    locations_file = _load_locations(game_data_root, diagnostics)
    tag_index = _load_tags(game_data_root, diagnostics)

    diagnostics.extend(validate_entities(entities).diagnostics)
    if room_catalog is not None:
        diagnostics.extend(validate_room_catalog(room_catalog, entities=entities).diagnostics)
    if locations_file is not None:
        diagnostics.extend(
            validate_locations(
                locations_file,
                catalog=room_catalog,
                entities=entities,
                project_layers=DEFAULT_PROJECT_LAYERS,
            ).diagnostics
        )

    image_root = _image_root(project)
    diagnostics.extend(
        validate_assets(
            image_root=image_root,
            entities=entities,
            room_catalog=room_catalog,
            locations_file=locations_file,
        ).diagnostics
    )

    if tag_index is not None:
        diagnostics.extend(validate_tag_references(tag_index, entities, room_catalog, locations_file))

    return DiagnosticReport(diagnostics=diagnostics)


def validate_project_data(
    *,
    project: ProjectConfig,
    manifest: EntityManifest | None,
    modules: list[EntityModule],
    room_catalog: RoomCatalog,
    locations_file: LocationsFile,
    tags_raw: dict | list | None = None,
) -> DiagnosticReport:
    """Validate in-memory game data models as-if they were exported."""
    diagnostics: list[Diagnostic] = []
    game_data_root = _game_data_root(project)

    if manifest is not None:
        manifest_path = game_data_root / "entities.json"
        manifest_data = manifest.model_dump(by_alias=True, mode="json", exclude_defaults=False)
        diagnostics.extend(
            _recode(
                validate_json_against_schema(
                    manifest_data,
                    "entities",
                    file_path=str(manifest_path),
                ).diagnostics,
                "entities_manifest",
            )
        )

    entities: list[EntityDefinition] = []
    for idx, module in enumerate(modules):
        module_path = game_data_root / "entity_modules" / f"module_{idx + 1}.json"
        module_data = module.model_dump(by_alias=True, mode="json", exclude_defaults=False)
        diagnostics.extend(
            _recode(
                validate_json_against_schema(
                    module_data,
                    "entity_module",
                    file_path=str(module_path),
                ).diagnostics,
                "entity_module",
            )
        )
        entities.extend(module.entities)

    room_catalog_path = game_data_root / "room_catalog.json"
    room_catalog_data = room_catalog.model_dump(by_alias=True, mode="json", exclude_defaults=False)
    diagnostics.extend(
        _recode(
            validate_json_against_schema(
                room_catalog_data,
                "room_catalog",
                file_path=str(room_catalog_path),
            ).diagnostics,
            "room_catalog",
        )
    )

    locations_path = game_data_root / "locations.json"
    locations_data = locations_file.model_dump(by_alias=True, mode="json", exclude_defaults=False)
    diagnostics.extend(
        _recode(
            validate_json_against_schema(
                locations_data,
                "locations",
                file_path=str(locations_path),
            ).diagnostics,
            "locations",
        )
    )

    diagnostics.extend(validate_entities(entities).diagnostics)
    diagnostics.extend(validate_room_catalog(room_catalog, entities=entities).diagnostics)
    diagnostics.extend(
        validate_locations(
            locations_file,
            catalog=room_catalog,
            entities=entities,
            project_layers=DEFAULT_PROJECT_LAYERS,
        ).diagnostics
    )

    diagnostics.extend(
        validate_assets(
            image_root=_image_root(project),
            entities=entities,
            room_catalog=room_catalog,
            locations_file=locations_file,
        ).diagnostics
    )

    if tags_raw is not None:
        tag_diagnostics: list[Diagnostic] = []
        tags_path = game_data_root / "tags.json"
        tag_index = load_tags_index(tags_raw, file_path=tags_path, diagnostics=tag_diagnostics)
        diagnostics.extend(tag_diagnostics)
        if tag_index is not None:
            diagnostics.extend(
                validate_tag_references(
                    tag_index,
                    entities,
                    room_catalog,
                    locations_file,
                )
            )

    return DiagnosticReport(diagnostics=diagnostics)


def _load_entities(game_data_root: Path, diagnostics: list[Diagnostic]) -> list[EntityDefinition]:
    entities: list[EntityDefinition] = []

    manifest_path = game_data_root / "entities.json"
    manifest_raw, manifest_diags = validate_json_file_against_schema(
        manifest_path,
        "entities",
        legacy_code="entities_manifest_legacy_version",
    )
    diagnostics.extend(_recode(manifest_diags, "entities_manifest"))
    if not isinstance(manifest_raw, dict):
        return entities

    try:
        manifest = EntityManifest.model_validate(manifest_raw)
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="entities_manifest_parse_error",
                message=f"Failed to parse entities.json: {exc}",
                file=str(manifest_path),
                source="python",
            )
        )
        return entities

    for include in manifest.includes:
        module_path = (game_data_root / include).resolve()
        module_raw, module_diags = validate_json_file_against_schema(
            module_path,
            "entity_module",
            legacy_code="entity_module_legacy_version",
        )
        diagnostics.extend(_recode(module_diags, "entity_module"))
        if not isinstance(module_raw, dict):
            continue
        try:
            module = EntityModule.model_validate(module_raw)
        except Exception as exc:
            diagnostics.append(
                Diagnostic(
                    severity=Severity.ERROR,
                    code="entity_module_parse_error",
                    message=f"Failed to parse entity module '{module_path}': {exc}",
                    file=str(module_path),
                    source="python",
                )
            )
            continue
        entities.extend(module.entities)

    return entities


def _load_room_catalog(game_data_root: Path, diagnostics: list[Diagnostic]) -> RoomCatalog | None:
    path = game_data_root / "room_catalog.json"
    raw, raw_diags = validate_json_file_against_schema(
        path,
        "room_catalog",
        legacy_code="room_catalog_legacy_version",
    )
    diagnostics.extend(_recode(raw_diags, "room_catalog"))
    if not isinstance(raw, dict):
        return None
    try:
        return RoomCatalog.model_validate(raw)
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="room_catalog_parse_error",
                message=f"Failed to parse room_catalog.json: {exc}",
                file=str(path),
                source="python",
            )
        )
        return None


def _load_locations(game_data_root: Path, diagnostics: list[Diagnostic]) -> LocationsFile | None:
    path = game_data_root / "locations.json"
    raw, raw_diags = validate_json_file_against_schema(
        path,
        "locations",
        legacy_code="locations_legacy_version",
    )
    diagnostics.extend(_recode(raw_diags, "locations"))
    if not isinstance(raw, dict):
        return None
    try:
        return LocationsFile.model_validate(raw)
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="locations_parse_error",
                message=f"Failed to parse locations.json: {exc}",
                file=str(path),
                source="python",
            )
        )
        return None


def _load_tags(game_data_root: Path, diagnostics: list[Diagnostic]):
    path = game_data_root / "tags.json"
    if not path.exists():
        return None
    raw, raw_diags = validate_json_file_against_schema(
        path,
        "tags",
        legacy_code="tags_legacy_version",
    )
    diagnostics.extend(_recode(raw_diags, "tags"))
    return load_tags_index(raw, file_path=path, diagnostics=diagnostics)


def _recode(items: list[Diagnostic], prefix: str) -> list[Diagnostic]:
    recoded: list[Diagnostic] = []
    for item in items:
        if item.code in {"missing_file", "json_parse_error", "json_root_not_object"}:
            code = f"{prefix}_{item.code}"
        elif item.code == "schema_validation":
            code = f"{prefix}_schema_validation"
        else:
            code = item.code
        recoded.append(
            Diagnostic(
                severity=item.severity,
                code=code,
                message=item.message,
                file=item.file,
                object_id=item.object_id,
                object_type=item.object_type,
                source=item.source,
            )
        )
    return recoded


def _resolve_project_path(project: ProjectConfig, value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    base = Path(project.game_root)
    if base.is_absolute():
        return (base / path).resolve()
    return (Path.cwd() / base / path).resolve()


def _game_data_root(project: ProjectConfig) -> Path:
    if hasattr(project, "absolute_game_data_root"):
        return Path(project.absolute_game_data_root).resolve()
    return _resolve_project_path(project, project.game_data_root)


def _image_root(project: ProjectConfig) -> Path:
    image_root = Path(project.image_root)
    if image_root.is_absolute():
        return image_root.resolve()
    return (Path(project.absolute_game_root) / image_root).resolve()
