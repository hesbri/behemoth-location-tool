"""Shared pytest fixtures and marks for the behemoth-location-tool test suite."""
from __future__ import annotations

import pytest


def _detect_pyside6() -> tuple[bool, str]:
    """Return (available, skip_reason).

    Tries to import PySide6.QtWidgets so that a DLL mismatch (e.g. Anaconda Qt
    vs PySide6 Qt) is caught as an OSError here rather than as a test error.
    """
    try:
        from PySide6.QtWidgets import QApplication  # noqa: F401
        return True, ""
    except (ImportError, OSError) as exc:
        return False, f"PySide6 not usable: {exc}"


_pyside6_available, _pyside6_skip_reason = _detect_pyside6()

requires_gui = pytest.mark.skipif(
    not _pyside6_available,
    reason=_pyside6_skip_reason or "PySide6 not available",
)
