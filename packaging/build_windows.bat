@echo off
setlocal
cd /d "%~dp0\.."

py -m pip install --upgrade pyinstaller
if errorlevel 1 exit /b 1

py -m PyInstaller --noconfirm --clean packaging\GurpsCalculadora.spec
if errorlevel 1 exit /b 1

echo Executavel criado em dist\GurpsCalculadora.exe
endlocal
