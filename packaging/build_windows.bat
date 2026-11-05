@echo off
setlocal
cd /d "%~dp0\.."
if errorlevel 1 exit /b 1

set "VENV=packaging\.build-venv\windows"
if not exist "%VENV%\Scripts\python.exe" py -3 -m venv "%VENV%"
if errorlevel 1 exit /b 1

"%VENV%\Scripts\python.exe" -m pip install --disable-pip-version-check --no-deps -r packaging\requirements-build.txt -r packaging\requirements-build-windows.txt
if errorlevel 1 exit /b 1

"%VENV%\Scripts\python.exe" tools\build_archives.py %*
exit /b %errorlevel%
