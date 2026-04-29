from __future__ import annotations

from pathlib import Path

from PIL import Image, UnidentifiedImageError

from behemoth_location_tool.model.entity import EntityDefinition
from behemoth_location_tool.model.location import LocationsFile, get_effective_background
from behemoth_location_tool.model.room import RoomCatalog
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity

_SUPPORTED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".bmp", ".webp"}


def validate_assets(
    *,
    image_root: Path,
    entities: list[EntityDefinition],
    room_catalog: RoomCatalog | None,
    locations_file: LocationsFile | None,
) -> DiagnosticReport:
    diagnostics: list[Diagnostic] = []

    for entity in entities:
        sprite_path = entity.render.sprite if entity.render is not None else None
        if not sprite_path:
            continue
        _validate_image_reference(
            image_root=image_root,
            rel_path=sprite_path,
            diagnostics=diagnostics,
            missing_code="missing_sprite_image",
            object_type="entity",
            object_id=entity.id,
            label="sprite",
        )

    if room_catalog is not None:
        for room in room_catalog.rooms:
            if not room.background_image:
                continue
            _validate_image_reference(
                image_root=image_root,
                rel_path=room.background_image,
                diagnostics=diagnostics,
                missing_code="missing_background_image",
                object_type="room",
                object_id=room.id,
                label="background",
            )

    if locations_file is not None:
        for location in locations_file.locations:
            effective = get_effective_background(location, room_catalog)
            if not effective:
                continue
            _validate_image_reference(
                image_root=image_root,
                rel_path=effective,
                diagnostics=diagnostics,
                missing_code="missing_background_image",
                object_type="location",
                object_id=location.id,
                label="background",
            )

    return DiagnosticReport(diagnostics=diagnostics)


def _validate_image_reference(
    *,
    image_root: Path,
    rel_path: str,
    diagnostics: list[Diagnostic],
    missing_code: str,
    object_type: str,
    object_id: str,
    label: str,
) -> None:
    full_path = _resolve_image_path(image_root, rel_path)
    suffix = full_path.suffix.lower()
    if suffix not in _SUPPORTED_EXTENSIONS:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="unsupported_image_extension",
                message=f"{object_type} '{object_id}' {label} uses unsupported extension: {rel_path}",
                file=str(full_path),
                object_type=object_type,
                object_id=object_id,
                source="python",
            )
        )
        return

    if not full_path.exists():
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code=missing_code,
                message=f"{object_type} '{object_id}' {label} image is missing: {rel_path}",
                file=str(full_path),
                object_type=object_type,
                object_id=object_id,
                source="python",
            )
        )
        return

    try:
        with Image.open(full_path) as image:
            image.verify()
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="image_unreadable",
                message=f"{object_type} '{object_id}' {label} image is unreadable: {rel_path} ({exc})",
                file=str(full_path),
                object_type=object_type,
                object_id=object_id,
                source="python",
            )
        )


def _resolve_image_path(image_root: Path, value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path.resolve()
    return (image_root / path).resolve()
