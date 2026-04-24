from __future__ import annotations
from collections.abc import Iterable
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity

def validate_unique_ids(ids: Iterable[str], *, label: str) -> DiagnosticReport:
    seen: set[str] = set()
    diagnostics: list[Diagnostic] = []
    for item_id in ids:
        if item_id in seen:
            diagnostics.append(Diagnostic(severity=Severity.ERROR, code="duplicate_id", message=f"Duplicate {label} id: {item_id}", object_id=item_id))
        seen.add(item_id)
    return DiagnosticReport(diagnostics=diagnostics)
