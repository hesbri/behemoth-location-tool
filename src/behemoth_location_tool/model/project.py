from __future__ import annotations

from pathlib import Path

from pydantic import BaseModel, Field


class ProjectConfig(BaseModel):
    version: int = 1
    project_name: str = Field(default="Behemoth Mansion", alias="projectName")
    game_root: Path = Field(default=Path("."), alias="gameRoot")
    game_executable: Path = Field(default=Path("bin/Behemoth.exe"), alias="gameExecutable")
    content_root: Path = Field(default=Path("data/behemoth"), alias="contentRoot")
    image_root: Path = Field(default=Path("data/behemoth/assets/images"), alias="imageRoot")
    game_data_root: Path = Field(default=Path("data/behemoth/game"), alias="gameDataRoot")
    tool_data_root: Path = Field(default=Path(".behemoth_tool"), alias="toolDataRoot")
    design_width: int = Field(default=1920, alias="designWidth")
    design_height: int = Field(default=1080, alias="designHeight")
    preview_port: int = Field(default=38171, alias="previewPort")
    model_config = {"populate_by_name": True, "extra": "forbid"}

    def resolve_paths(self, project_dir: Path) -> None:
        """Resolve all relative paths relative to the project config file location.

        Resolution order:
          - gameRoot        → relative to project_dir
          - gameExecutable  → relative to resolved gameRoot
          - contentRoot     → relative to resolved gameRoot
          - imageRoot       → relative to resolved gameRoot
          - gameDataRoot    → relative to resolved gameRoot
          - toolDataRoot    → relative to resolved gameRoot (unless already absolute)
        """
        project_dir = project_dir.resolve()

        # gameRoot: resolve relative to project config file directory
        if not self.game_root.is_absolute():
            self.game_root = (project_dir / self.game_root).resolve()

        # gameExecutable: resolve relative to gameRoot
        if not self.game_executable.is_absolute():
            self.game_executable = (self.game_root / self.game_executable).resolve()

        # All other data roots: resolve relative to gameRoot
        for attr in ("content_root", "image_root", "game_data_root", "tool_data_root"):
            value = getattr(self, attr)
            if not value.is_absolute():
                setattr(self, attr, (self.game_root / value).resolve())

    @property
    def absolute_game_root(self) -> Path:
        return self.game_root if self.game_root.is_absolute() else self.game_root.resolve()

    @property
    def absolute_game_data_root(self) -> Path:
        gdr = self.game_data_root
        if gdr.is_absolute():
            return gdr
        return (self.absolute_game_root / gdr).resolve()

    @property
    def absolute_tool_root(self) -> Path:
        base = self.absolute_game_root
        tool = self.tool_data_root
        if tool.is_absolute():
            return tool
        return (base / tool).resolve()

    @property
    def absolute_preview_snapshot_path(self) -> Path:
        return self.absolute_tool_root / "preview" / "current_snapshot.json"