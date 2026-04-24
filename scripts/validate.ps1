$ErrorActionPreference = "Stop"
. .\.venv\Scripts\Activate.ps1
ruff check .
mypy src
pytest
