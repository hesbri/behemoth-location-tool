from __future__ import annotations

import sys

from conftest import requires_gui
from PySide6.QtWidgets import QApplication

from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.ui.validate_tab import ValidateTab
from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity


@requires_gui
def test_validate_tab_runtime_action_uses_callback_and_merges_diagnostics() -> None:
    app = QApplication.instance() or QApplication(sys.argv)
    assert app is not None

    tab = ValidateTab(ProjectConfig())
    called: list[bool] = []

    def _runtime_callback() -> list[Diagnostic]:
        called.append(True)
        return [
            Diagnostic(
                severity=Severity.WARNING,
                code="runtime_disconnected",
                message="runtime not connected",
                source="runtime",
            )
        ]

    tab.set_runtime_validation_callback(_runtime_callback)
    tab.run_runtime_validation()

    assert called == [True]
    assert any(d.code == "runtime_disconnected" for d in tab._diagnostics)
