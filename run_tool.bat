@echo off
setlocal

cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Python virtual environment not found.
    echo Expected: %CD%\.venv\Scripts\activate.bat
    echo.
    echo Create it with:
    echo   py -3.11 -m venv .venv
    echo   .venv\Scripts\activate.bat
    echo   python -m pip install --upgrade pip
    echo   pip install -e ".[dev]"
    exit /b 1
)

call ".venv\Scripts\activate.bat"

set PROJECT=%~1
if "%PROJECT%"=="" set PROJECT=projects\behemoth.json

echo Running Behemoth Location Tool
echo Project config: %PROJECT%
echo.

behemoth-location-tool --project "%PROJECT%"
exit /b %ERRORLEVEL%