@echo off
cd /d "%~dp0"
where py >nul 2>nul || (echo Instala Python 3.11 o superior desde python.org marcando "Add to PATH". & pause & exit /b 1)
if not exist .venv py -3 -m venv .venv
.venv\Scripts\python -m pip install --upgrade pip
.venv\Scripts\python -m pip install -r requirements.txt
echo.
echo Listo. Ahora haz doble clic en probar_iteracion1.bat
pause
