@echo off
setlocal

cd /d "%~dp0.."

if not exist ".venv\Scripts\activate.bat" (
    echo ERROR: Python virtual environment not found.
    echo Expected: %CD%\.venv\Scripts\activate.bat
    echo.
    echo Create it with:
    echo   py -3.11 -m venv .venv
    echo   .venv\Scripts\activate.bat
    echo   pip install -e ".[dev]"
    exit /b 1
)

call ".venv\Scripts\activate.bat"

echo === Compile check ===
python -m compileall src\ -q
if %ERRORLEVEL% neq 0 (
    echo FAILED: compile errors detected.
    exit /b %ERRORLEVEL%
)
echo OK

echo.
echo === Running tests ===
python -m pytest tests\ -q --tb=short
if %ERRORLEVEL% neq 0 (
    echo FAILED: tests reported failures.
    exit /b %ERRORLEVEL%
)
echo All tests passed.
exit /b 0
