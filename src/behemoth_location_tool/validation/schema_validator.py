from __future__ import annotations

import json
from pathlib import Path

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


def validate_json_against_schema(data: dict, schema_name: str, *, file_path: str | None = None) -> DiagnosticReport:
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
