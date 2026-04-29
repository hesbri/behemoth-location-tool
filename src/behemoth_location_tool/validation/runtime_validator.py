from __future__ import annotations

from collections.abc import Callable
from typing import Any

from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity


def runtime_disconnected_warning() -> Diagnostic:
    return Diagnostic(
        severity=Severity.WARNING,
        code="runtime_disconnected",
        message="Runtime validation requested, but preview runtime is not running.",
        source="runtime",
    )


def request_runtime_validation(
    *,
    is_runtime_running: bool,
    send_validate_runtime: Callable[[], None],
) -> list[Diagnostic]:
    """Validation-facing bridge for runtime validation requests.

    Returns immediate diagnostics (for disconnected cases) and never raises.
    """
    if not is_runtime_running:
        return [runtime_disconnected_warning()]
    send_validate_runtime()
    return []


def parse_runtime_validation_result(message: dict[str, Any]) -> list[Diagnostic]:
    """Convert runtime_validation_result payload into diagnostics."""
    diagnostics: list[Diagnostic] = []

    def _append(entries: Any, severity: Severity) -> None:
        if not isinstance(entries, list):
            return
        for entry in entries:
            if isinstance(entry, dict):
                code = str(entry.get("code", "runtime_validation"))
                text = str(entry.get("message", ""))
            else:
                code = "runtime_validation"
                text = str(entry)
            diagnostics.append(
                Diagnostic(
                    severity=severity,
                    code=code,
                    message=text,
                    source="runtime",
                )
            )

    _append(message.get("errors", []), Severity.ERROR)
    _append(message.get("warnings", []), Severity.WARNING)
    _append(message.get("infos", []), Severity.INFO)
    return diagnostics


def diagnostics_to_runtime_entries(diagnostics: list[Diagnostic]) -> list[dict[str, str]]:
    return [
        {
            "severity": diag.severity.value,
            "code": diag.code,
            "message": diag.message,
        }
        for diag in diagnostics
    ]
