from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import jsonschema

from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity

_SCHEMA_DIR = Path(__file__).resolve().parent.parent / "schemas"

_SCHEMA_MAP: dict[str, str] = {
    "entities": "entities.schema.json",
    "entity_module": "entity_module.schema.json",
    "room_catalog": "room_catalog.schema.json",
    "locations": "locations.schema.json",
    "tags": "tags.schema.json",
}


def _load_schema(name: str) -> dict:
    """Load a JSON schema by short name."""
    filename = _SCHEMA_MAP[name]
    schema_path = _SCHEMA_DIR / filename
    with schema_path.open("r", encoding="utf-8") as f:
        return json.load(f)


def validate_json_against_schema(
    data: dict,
    schema_name: str,
    *,
    file_path: str | None = None,
) -> DiagnosticReport:
    """Validate a JSON data dict against a named schema.

    Args:
        data: The parsed JSON data to validate.
        schema_name: One of 'entities', 'entity_module', 'room_catalog', 'locations'.
        file_path: Optional file path to include in diagnostics.

    Returns:
        A DiagnosticReport with any schema validation errors.
    """
    schema = _load_schema(schema_name)
    validator_cls = jsonschema.Draft202012Validator
    validator = validator_cls(schema)

    diagnostics: list[Diagnostic] = []
    for error in sorted(validator.iter_errors(data), key=lambda e: list(e.absolute_path)):
        path_str = ".".join(str(p) for p in error.absolute_path) if error.absolute_path else "(root)"
        diagnostics.append(Diagnostic(
            severity=Severity.ERROR,
            code="schema_validation",
            message=f"Schema error at {path_str}: {error.message}",
            file=file_path,
        ))

    return DiagnosticReport(diagnostics=diagnostics)


def read_raw_json(path: Path) -> tuple[Any | None, list[Diagnostic]]:
    diagnostics: list[Diagnostic] = []
    if not path.exists():
        diagnostics.append(
            Diagnostic(
                severity=Severity.WARNING,
                code="missing_file",
                message=f"File does not exist: {path}",
                file=str(path),
                source="python",
            )
        )
        return None, diagnostics
    try:
        return json.loads(path.read_text(encoding="utf-8")), diagnostics
    except Exception as exc:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="json_parse_error",
                message=f"Failed to parse JSON file '{path}': {exc}",
                file=str(path),
                source="python",
            )
        )
        return None, diagnostics


def validate_json_file_against_schema(
    path: Path,
    schema_name: str,
    *,
    legacy_code: str,
) -> tuple[Any | None, list[Diagnostic]]:
    raw, diagnostics = read_raw_json(path)
    if raw is None:
        return None, diagnostics
    if isinstance(raw, dict) and "schemaVersion" in raw:
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code=legacy_code,
                message=f"{path.name} uses deprecated 'schemaVersion'; expected 'version': 2",
                file=str(path),
                source="python",
            )
        )
    if not isinstance(raw, dict):
        diagnostics.append(
            Diagnostic(
                severity=Severity.ERROR,
                code="json_root_not_object",
                message=f"{path.name} root must be a JSON object",
                file=str(path),
                source="python",
            )
        )
        return raw, diagnostics
    diagnostics.extend(validate_json_against_schema(raw, schema_name, file_path=str(path)).diagnostics)
    return raw, diagnostics
