@echo off
rem Same as run.bat but keeps a console so errors are visible.
set "PY=python"
if exist "%~dp0.venv\Scripts\python.exe" set "PY=%~dp0.venv\Scripts\python.exe"
"%PY%" "%~dp0main.py" %*
pause
