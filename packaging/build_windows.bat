@echo off
setlocal
cd /d "%~dp0\.."

py -m venv packaging\.build-venv
if errorlevel 1 exit /b 1

packaging\.build-venv\Scripts\python.exe -m pip install --upgrade pip pyinstaller
if errorlevel 1 exit /b 1

packaging\.build-venv\Scripts\python.exe -m PyInstaller --noconfirm --clean packaging\GurpsCalculadora.spec
if errorlevel 1 exit /b 1

echo Executavel criado em dist\GurpsCalculadora.exe
endlocal
