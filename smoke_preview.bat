@echo off
setlocal

cd /d "%~dp0"

if exist ".venv\Scripts\activate.bat" (
    call ".venv\Scripts\activate.bat"
)

set PROJECT=%~1
if "%PROJECT%"=="" set PROJECT=projects\behemoth.json

if not exist "%PROJECT%" (
    echo ERROR: Project config not found: %PROJECT%
    echo.
    echo Usage:
    echo   smoke_preview.bat projects\behemoth.json
    exit /b 1
)

python scripts\smoke_preview.py --project "%PROJECT%"
exit /b %ERRORLEVEL%