from __future__ import annotations

import argparse
import sys
from pathlib import Path

from PySide6.QtWidgets import QApplication

from behemoth_location_tool.io.project import load_project_or_default
from behemoth_location_tool.ui.main_window import MainWindow


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Behemoth Location Tool")
    parser.add_argument("--project", type=Path, default=None, help="Path to a project.json file")
    return parser

def main(argv: list[str] | None = None) -> int:
    args = build_arg_parser().parse_args(argv)
    project = load_project_or_default(args.project)
    app = QApplication(sys.argv if argv is None else [sys.argv[0], *argv])
    window = MainWindow(project, project_path=args.project)
    window.resize(1400, 900)
    window.show()
    return int(app.exec())
