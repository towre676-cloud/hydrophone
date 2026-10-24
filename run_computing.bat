@echo off
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python -m computing demo --output-dir results\demo
) else (
  py -3 -m computing demo --output-dir results\demo
)
if errorlevel 1 exit /b 1
echo Offline results are in results\demo. No hardware commands were issued.
pause
