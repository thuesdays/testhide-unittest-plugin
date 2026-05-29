@echo off
REM ============================================================================
REM Publish testhide-unittest-plugin to PyPI.
REM Reads tokens/env from .env.local (gitignored). Copy .env.local.example first.
REM Usage:  publish.bat
REM ============================================================================
setlocal enabledelayedexpansion
cd /d "%~dp0"

if not exist ".env.local" (
  echo [publish] ERROR: .env.local not found.
  echo [publish] Copy .env.local.example to .env.local and add your PyPI token.
  exit /b 1
)

REM Load KEY=VALUE lines (ignore # comments and blank lines)
for /f "usebackq eol=# tokens=1,* delims==" %%a in (".env.local") do set "%%a=%%b"

if "%PYPI_API_TOKEN%"=="" (
  echo [publish] ERROR: PYPI_API_TOKEN is not set in .env.local
  exit /b 1
)

echo [publish] Installing package + build tools...
python -m pip install -e . build twine >nul || exit /b 1

echo [publish] Running conformance tests...
python -m unittest discover -s tests -p "test_*.py" || exit /b 1
python conformance\validate_report.py conformance\golden_report.xml || exit /b 1

echo [publish] Building sdist + wheel...
if exist dist rmdir /s /q dist
python -m build || exit /b 1

echo [publish] Uploading to PyPI...
set "TWINE_USERNAME=__token__"
set "TWINE_PASSWORD=%PYPI_API_TOKEN%"
python -m twine upload dist\* || exit /b 1

echo [publish] Done.
endlocal
