@echo off
rem Launch without a console window. Optional argument: a folder to open.
rem Keep this file ASCII-only and CRLF: cmd needs both.
rem Uses the project .venv when present, otherwise pythonw on PATH.
set "PYW=pythonw"
if exist "%~dp0.venv\Scripts\pythonw.exe" set "PYW=%~dp0.venv\Scripts\pythonw.exe"
start "Filer" "%PYW%" "%~dp0main.py" %*
