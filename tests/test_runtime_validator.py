from __future__ import annotations

from behemoth_location_tool.validation.runtime_validator import (
    parse_runtime_validation_result,
    request_runtime_validation,
)


def test_request_runtime_validation_disconnected_returns_warning() -> None:
    sent: list[bool] = []
    diagnostics = request_runtime_validation(
        is_runtime_running=False,
        send_validate_runtime=lambda: sent.append(True),
    )
    assert not sent
    assert len(diagnostics) == 1
    assert diagnostics[0].code == "runtime_disconnected"
    assert diagnostics[0].source == "runtime"


def test_request_runtime_validation_connected_sends_and_returns_no_immediate_diagnostics() -> None:
    sent: list[bool] = []
    diagnostics = request_runtime_validation(
        is_runtime_running=True,
        send_validate_runtime=lambda: sent.append(True),
    )
    assert sent == [True]
    assert diagnostics == []


def test_parse_runtime_validation_result_maps_all_severities() -> None:
    diagnostics = parse_runtime_validation_result(
        {
            "type": "runtime_validation_result",
            "errors": [{"code": "bad_exit", "message": "Missing exit socket"}],
            "warnings": [{"code": "warn_missing_sprite", "message": "Sprite missing"}],
            "infos": [{"code": "info_flag", "message": "Flag conditions not evaluated"}],
        }
    )
    assert [d.severity.value for d in diagnostics] == ["error", "warning", "info"]
    assert diagnostics[0].code == "bad_exit"
