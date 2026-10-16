@echo off
rem Double-click: starts the website and opens it in your browser. Close this window to stop it.
cd /d "%~dp0"
where python >nul 2>nul || (echo Python 3 is not installed. Get it from https://www.python.org/downloads/ and tick "Add python.exe to PATH". & pause & exit /b 1)
python server.py --open
if errorlevel 1 pause
