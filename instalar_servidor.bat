@echo off
rem Instala o ACTUALIZA el Tablero de Herramentales como servidor en ESTA PC. Doble clic (NO necesita administrador).
rem Al abrir desde la carpeta de red Windows avisa "no se permiten rutas UNC": es normal.
pushd "%~dp0"
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0instalar_servidor.ps1"
if errorlevel 1 (echo. & echo Hubo un error: lee el mensaje de arriba.)
echo.
pause
popd
