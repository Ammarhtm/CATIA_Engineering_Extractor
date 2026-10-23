@echo off
setlocal
cd /d "%~dp0"
set "PYTHONPATH=%CD%\src;%PYTHONPATH%"
python -m catia_extractor.pipeline_unified.desktop_app
if errorlevel 1 pause
endlocal