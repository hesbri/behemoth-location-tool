from __future__ import annotations
from pathlib import Path
from behemoth_location_tool.io.json_io import read_json, write_json
from behemoth_location_tool.model.project import ProjectConfig


def load_project_or_default(path: Path | None) -> ProjectConfig:
    if path is None:
        return ProjectConfig()
    if not path.exists():
        raise FileNotFoundError(path)
    data = read_json(path)
    project = ProjectConfig.model_validate(data)
    project.resolve_paths(path.parent)
    return project


def save_project(path: Path, project: ProjectConfig) -> None:
    write_json(path, project.model_dump(by_alias=True, mode="json"))