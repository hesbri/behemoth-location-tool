from __future__ import annotations

from pathlib import Path

from behemoth_location_tool.io.json_io import read_json, write_json
from behemoth_location_tool.model.entity import EntityDefinition, EntityManifest, EntityModule


def _require_v2(data: dict, *, label: str, path: Path) -> None:
    if "schemaVersion" in data:
        raise ValueError(f"{label} at {path} uses deprecated 'schemaVersion'; expected 'version': 2")
    version = data.get("version")
    if version != 2:
        raise ValueError(f"{label} at {path} must have version 2, got {version!r}")


def load_entity_manifest(path: Path) -> EntityManifest:
    """Load the entities.json manifest file."""
    data = read_json(path)
    _require_v2(data, label="Entity manifest", path=path)
    return EntityManifest.model_validate(data)


def save_entity_manifest(path: Path, manifest: EntityManifest) -> None:
    """Save the entities.json manifest file."""
    write_json(path, manifest.model_dump(by_alias=True, mode="json", exclude_defaults=False))


def load_entity_module(path: Path) -> EntityModule:
    """Load a single entity module file."""
    data = read_json(path)
    _require_v2(data, label="Entity module", path=path)
    return EntityModule.model_validate(data)


def save_entity_module(path: Path, module: EntityModule) -> None:
    """Save a single entity module file."""
    write_json(path, module.model_dump(by_alias=True, mode="json", exclude_defaults=False))


def load_all_entities(
    manifest_path: Path,
) -> tuple[EntityManifest, list[EntityModule], list[EntityDefinition]]:
    """Load the entity manifest and all included entity modules.

    Returns:
        A tuple of (manifest, modules, all_entities) where all_entities is a
        flat list of every EntityDefinition from all loaded modules.
    """
    manifest = load_entity_manifest(manifest_path)
    modules: list[EntityModule] = []
    all_entities: list[EntityDefinition] = []
    base_dir = manifest_path.parent

    for include_path in manifest.includes:
        module_file = base_dir / include_path
        module = load_entity_module(module_file)
        modules.append(module)
        all_entities.extend(module.entities)

    return manifest, modules, all_entities
