from __future__ import annotations

from behemoth_location_tool.model.location import ExitDefinition, LocationInstance, LocationsFile
from behemoth_location_tool.ui.graph_tab import (
    STATUS_INVALID_TARGET,
    STATUS_MISSING_DEFAULT_BACK,
    STATUS_MISSING_RECIPROCAL,
    STATUS_START,
    STATUS_UNREACHABLE,
    _build_status_badge,
    classify_graph_location_statuses,
)
from behemoth_location_tool.validation.diagnostics import Diagnostic, Severity


def test_classify_graph_location_statuses_maps_location_diagnostics() -> None:
    lf = LocationsFile(
        start_location="start",
        locations=[
            LocationInstance(
                id="start",
                catalog_room_id="",
                name="Start",
                exits=[
                    ExitDefinition(
                        id="exit_start_to_missing",
                        entity_id="door",
                        target_location_id="missing",
                        socket_id="sock_a",
                        tags=["exit.default_back"],
                    )
                ],
            ),
            LocationInstance(
                id="kitchen",
                catalog_room_id="",
                name="Kitchen",
                exits=[],
            ),
        ],
    )
    diagnostics = [
        Diagnostic(
            severity=Severity.ERROR,
            code="missing_reciprocal_exit",
            message="no reciprocal",
            object_id="start",
        ),
        Diagnostic(
            severity=Severity.ERROR,
            code="unreachable_location",
            message="unreachable",
            object_id="kitchen",
        ),
        Diagnostic(
            severity=Severity.ERROR,
            code="missing_default_back_exit",
            message="missing default back",
            object_id="kitchen",
        ),
        Diagnostic(
            severity=Severity.ERROR,
            code="missing_target_location",
            message="bad target",
            object_id="exit_start_to_missing",
        ),
    ]

    statuses = classify_graph_location_statuses(lf, diagnostics)

    assert STATUS_START in statuses["start"]
    assert STATUS_MISSING_RECIPROCAL in statuses["start"]
    assert STATUS_INVALID_TARGET in statuses["start"]
    assert STATUS_UNREACHABLE in statuses["kitchen"]
    assert STATUS_MISSING_DEFAULT_BACK in statuses["kitchen"]


def test_graph_status_badge_contains_human_tokens() -> None:
    badge = _build_status_badge(
        {
            STATUS_START,
            STATUS_MISSING_DEFAULT_BACK,
            STATUS_INVALID_TARGET,
            STATUS_UNREACHABLE,
            STATUS_MISSING_RECIPROCAL,
        }
    )
    assert "START" in badge
    assert "NO_BACK" in badge
    assert "BAD_TARGET" in badge
    assert "UNREACHABLE" in badge
    assert "NO_RECIP" in badge
