@echo off
rem Regenera el tablero con los datos mas recientes de SharePoint y lo abre en el navegador.
cd /d "%~dp0"
echo Actualizando indicadores...
python -W ignore generar_tablero.py
if errorlevel 1 (
  echo.
  echo Hubo un error. Revisa generar_tablero.log en esta carpeta.
  pause
  exit /b 1
)
start "" "Tablero de Indicadores.html"
