@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m instrument demo --output-dir results\instrument_demo
) else (
  py -3 -m instrument demo --output-dir results\instrument_demo
)
pause
