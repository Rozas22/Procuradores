@echo off
rem Construye el instalador en Windows. Necesita Python 3.12 y, para el instalador, Inno Setup 6.
cd /d "%~dp0"
where python >nul 2>nul || (echo Falta Python: https://www.python.org/downloads/ & pause & exit /b 1)
if not exist .venv python -m venv .venv
call .venv\Scripts\activate.bat
python -m pip install --upgrade pip
pip install -r requirements.txt pyinstaller==6.16.0 || (pause & exit /b 1)
pyinstaller --noconfirm EscritosProcura.spec || (pause & exit /b 1)
set ISCC="%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not exist %ISCC% set ISCC="%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist %ISCC% (
  %ISCC% instalador.iss && echo. && echo Instalador creado en la carpeta dist.
) else (
  echo.
  echo La aplicacion esta en dist\EscritosProcura\EscritosProcura.exe
  echo Para crear el instalador, instala Inno Setup 6: winget install JRSoftware.InnoSetup
)
pause
