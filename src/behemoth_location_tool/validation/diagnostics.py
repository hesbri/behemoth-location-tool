from __future__ import annotations
from enum import StrEnum
from pydantic import BaseModel

class Severity(StrEnum):
    ERROR = "error"
    WARNING = "warning"
    INFO = "info"

class Diagnostic(BaseModel):
    severity: Severity
    code: str
    message: str
    file: str | None = None
    object_id: str | None = None
    object_type: str | None = None
    source: str = "python"

class DiagnosticReport(BaseModel):
    diagnostics: list[Diagnostic]

    @property
    def has_errors(self) -> bool:
        return any(item.severity == Severity.ERROR for item in self.diagnostics)
