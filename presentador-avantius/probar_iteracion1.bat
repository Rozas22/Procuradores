@echo off
chcp 65001 >nul
cd /d "%~dp0"
set PY=.venv\Scripts\python
echo === 1. Pruebas automaticas ===
%PY% -m pytest -q tests
echo.
echo === 2. Escrito y certificado de ejemplo ===
%PY% -m presentador ejemplo
echo.
echo === 3. Datos extraidos del PDF ===
%PY% -m presentador extraer ejemplo\escrito_ejemplo.pdf
echo.
echo === 4. Firma con el certificado de PRUEBA ===
%PY% -m presentador firmar ejemplo\escrito_ejemplo.pdf --pfx ejemplo\certificado_prueba.pfx --clave 1234
echo.
echo === 5. Tus certificados de Windows ===
%PY% -m presentador certificados
echo.
start "" "ejemplo\escrito_ejemplo firmado.pdf"
pause
