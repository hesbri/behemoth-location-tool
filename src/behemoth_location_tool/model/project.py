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

    @property
    def absolute_game_root(self) -> Path:
        return self.game_root.resolve()

    @property
    def absolute_tool_root(self) -> Path:
        return (self.absolute_game_root / self.tool_data_root).resolve()

    @property
    def absolute_preview_snapshot_path(self) -> Path:
        return self.absolute_tool_root / "preview" / "current_snapshot.json"
