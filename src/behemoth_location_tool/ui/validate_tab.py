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
from behemoth_location_tool.validation.validator import validate_project

_SEV_COLOR = {
    "error":   QColor(255, 235, 238),   # pale red
    "warning": QColor(255, 248, 225),   # pale amber
    "info":    QColor(255, 255, 255),   # white
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
        self._runtime_validate_callback: Callable[[], None] | None = None
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)

        # ---- toolbar ----
        toolbar = QHBoxLayout()

        self._run_button = QPushButton("Run Validation")
        self._run_button.clicked.connect(self.run_validation)
        toolbar.addWidget(self._run_button)

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
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(3, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(4, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(5, QHeaderView.ResizeMode.Stretch)
        header.setSectionResizeMode(6, QHeaderView.ResizeMode.ResizeToContents)

        self._table.setSortingEnabled(True)
        self._table.setSelectionBehavior(QTableWidget.SelectionBehavior.SelectRows)
        self._table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        root.addWidget(self._table)

    # ---- public ----

    def clear(self) -> None:
        self._diagnostics.clear()
        self._table.setRowCount(0)
        self._update_counts()

    def run_validation(self) -> None:
        self.clear()
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
        self._diagnostics = _sort_diagnostics(list(report.diagnostics))
        self._populate_table()
        self._update_counts()
        if self._runtime_checkbox.isChecked() and self._runtime_validate_callback is not None:
            self._runtime_validate_callback()

    def set_runtime_validation_callback(self, callback: Callable[[], None]) -> None:
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
            bg = _SEV_COLOR.get(sev, QColor(255, 255, 255))
            for col, value in enumerate(row_values):
                item = QTableWidgetItem(value)
                item.setFlags(item.flags() & ~Qt.ItemFlag.ItemIsEditable)
                item.setBackground(bg)
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
