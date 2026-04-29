from __future__ import annotations

import traceback
from collections.abc import Callable

from PySide6.QtCore import Qt
from PySide6.QtGui import QColor
from PySide6.QtWidgets import (
    QApplication,
    QCheckBox,
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from behemoth_location_tool.model.project import ProjectConfig
from behemoth_location_tool.validation.diagnostics import Diagnostic, DiagnosticReport, Severity
from behemoth_location_tool.validation.validation_service import validate_project

_ROW_BG = QColor(66, 66, 66)
_TEXT_WHITE = QColor(255, 255, 255)
_SEV_TEXT_COLOR = {
    "error": QColor(220, 70, 70),
    "warning": QColor(245, 170, 60),
    "info": _TEXT_WHITE,
}
_SEV_ORDER = {"error": 0, "warning": 1, "info": 2}

_SEV_FILTER_OPTIONS = ["All", "Errors only", "Warnings only", "Info only",
                       "Errors + Warnings"]
_SEV_FILTER_SETS: dict[str, set[str] | None] = {
    "All":               None,
    "Errors only":       {"error"},
    "Warnings only":     {"warning"},
    "Info only":         {"info"},
    "Errors + Warnings": {"error", "warning"},
}


class ValidateTab(QWidget):
    def __init__(self, project: ProjectConfig) -> None:
        super().__init__()
        self.project = project
        self._diagnostics: list[Diagnostic] = []
        self._runtime_validate_callback: Callable[[], list[Diagnostic]] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ---- toolbar ----
        toolbar = QHBoxLayout()

        self._validate_all_button = QPushButton("Validate All")
        self._validate_all_button.clicked.connect(self.run_validation)
        toolbar.addWidget(self._validate_all_button)

        self._validate_python_button = QPushButton("Validate Python Only")
        self._validate_python_button.clicked.connect(self.run_python_validation)
        toolbar.addWidget(self._validate_python_button)

        self._validate_runtime_button = QPushButton("Validate Runtime")
        self._validate_runtime_button.clicked.connect(self.run_runtime_validation)
        toolbar.addWidget(self._validate_runtime_button)

        self._clear_button = QPushButton("Clear")
        self._clear_button.clicked.connect(self.clear)
        toolbar.addWidget(self._clear_button)

        self._copy_button = QPushButton("Copy Selected")
        self._copy_button.clicked.connect(self._copy_selected)
        toolbar.addWidget(self._copy_button)

        self._runtime_checkbox = QCheckBox("Include Runtime Validation")
        toolbar.addWidget(self._runtime_checkbox)

        toolbar.addStretch(1)

        self._counts_label = QLabel("Errors: 0 | Warnings: 0 | Info: 0")
        toolbar.addWidget(self._counts_label)

        root.addLayout(toolbar)

        # ---- filter row (search + severity) ----
        filter_row = QHBoxLayout()
        filter_row.addWidget(QLabel("Filter:"))

        self._search_edit = QLineEdit()
        self._search_edit.setPlaceholderText("Search message, code, or object…")
        self._search_edit.textChanged.connect(self._apply_filter)
        filter_row.addWidget(self._search_edit)

        filter_row.addWidget(QLabel("Severity:"))
        self._sev_combo = QComboBox()
        for opt in _SEV_FILTER_OPTIONS:
            self._sev_combo.addItem(opt)
        self._sev_combo.currentIndexChanged.connect(self._apply_filter)
        filter_row.addWidget(self._sev_combo)

        root.addLayout(filter_row)

        # ---- table ----
        self._table = QTableWidget(0, 7)
        self._table.setHorizontalHeaderLabels([
            "Severity", "Code", "Message", "Object Type", "Object ID", "File", "Source",
        ])
        header = self._table.horizontalHeader()
        # Allow manual column resizing (especially Message) for long diagnostics.
        header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)
        header.setStretchLastSection(False)
        self._table.setColumnWidth(0, 110)
        self._table.setColumnWidth(1, 190)
        self._table.setColumnWidth(2, 520)
        self._table.setColumnWidth(3, 140)
        self._table.setColumnWidth(4, 130)
        self._table.setColumnWidth(5, 480)
        self._table.setColumnWidth(6, 110)

        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self._table)

    # ---- public ----

    def clear(self) -> None:
        self._diagnostics.clear()
        self._table.setRowCount(0)
        self._update_counts()

    def set_diagnostics(self, diagnostics: list[Diagnostic]) -> None:
        self._diagnostics = _sort_diagnostics(list(diagnostics))
        self._populate_table()
        self._update_counts()

    def run_validation(self) -> None:
        """Validate all: python validation + optional runtime validation."""
        self.clear()
        self._run_python_validation()
        if self._runtime_checkbox.isChecked():
            self._request_runtime_validation()

    def run_python_validation(self) -> None:
        self.clear()
        self._run_python_validation()

    def run_runtime_validation(self) -> None:
        self.clear()
        self._request_runtime_validation()

    def _run_python_validation(self) -> None:
        try:
            report = validate_project(self.project)
        except Exception as exc:
            report = DiagnosticReport(diagnostics=[
                Diagnostic(
                    severity=Severity.ERROR,
                    code="validation_crash",
                    message=f"Validation crashed: {exc}\n{traceback.format_exc()}",
                    source="python",
                )
            ])
        self.set_diagnostics(report.diagnostics)

    def _request_runtime_validation(self) -> None:
        if self._runtime_validate_callback is None:
            return
        try:
            immediate = self._runtime_validate_callback()
        except Exception as exc:
            immediate = [
                Diagnostic(
                    severity=Severity.WARNING,
                    code="runtime_validation_request_failed",
                    message=f"Failed to request runtime validation: {exc}",
                    source="runtime",
                )
            ]
        if immediate:
            self.add_runtime_diagnostics(immediate)

    def set_runtime_validation_callback(self, callback: Callable[[], list[Diagnostic]]) -> None:
        self._runtime_validate_callback = callback

    def add_runtime_diagnostics(self, diagnostics: list[Diagnostic]) -> None:
        """Merge runtime diagnostics into the current results."""
        self._diagnostics = _sort_diagnostics(self._diagnostics + diagnostics)
        self._populate_table()
        self._update_counts()

    # ---- private ----

    def _populate_table(self) -> None:
        self._table.setSortingEnabled(False)
        self._table.setRowCount(0)
        query = self._search_edit.text().lower()
        sev_filter = _SEV_FILTER_SETS.get(self._sev_combo.currentText())

        for diag in self._diagnostics:
            sev = _sev_str(diag)

            if sev_filter is not None and sev not in sev_filter:
                continue

            row_values = [
                sev,
                diag.code or "",
                diag.message or "",
                diag.object_type or "",
                diag.object_id or "",
                diag.file or "",
                diag.source or "",
            ]
            if query and not any(query in v.lower() for v in row_values):
                continue

            r = self._table.rowCount()
            self._table.insertRow(r)
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(_ROW_BG)
                # Keep all text white for readability except severity label itself.
                if col == 0:
                    item.setForeground(_SEV_TEXT_COLOR.get(sev, _TEXT_WHITE))
                else:
                    item.setForeground(_TEXT_WHITE)
                self._table.setItem(r, col, item)

        self._table.setSortingEnabled(True)

    def _apply_filter(self) -> None:
        self._populate_table()

    def _copy_selected(self) -> None:
        rows = {idx.row() for idx in self._table.selectedIndexes()}
        if not rows:
            return
        lines: list[str] = []
        for r in sorted(rows):
            cols = [self._table.item(r, c) for c in range(self._table.columnCount())]
            lines.append("\t".join(item.text() if item else "" for item in cols))
        QApplication.clipboard().setText("\n".join(lines))

    def _update_counts(self) -> None:
        errors = warnings = infos = 0
        for d in self._diagnostics:
            s = _sev_str(d)
            if s == "error":
                errors += 1
            elif s == "warning":
                warnings += 1
            else:
                infos += 1
        self._counts_label.setText(f"Errors: {errors} | Warnings: {warnings} | Info: {infos}")


# ---- helpers ----

def _sev_str(diag: Diagnostic) -> str:
    s = getattr(diag, "severity", Severity.INFO)
    return s.value if isinstance(s, Severity) else str(s)


def _sort_diagnostics(diagnostics: list[Diagnostic]) -> list[Diagnostic]:
    return sorted(
        diagnostics,
        key=lambda d: (
            _SEV_ORDER.get(_sev_str(d), 99),
            d.code or "",
            d.object_id or "",
        ),
    )
