@echo off
rem Crea (o reemplaza) una tarea de Windows que regenera el tablero cada hora, sin abrir ventanas.
rem Solo hay que ejecutarlo una vez. Para quitarla:  schtasks /Delete /TN "Tablero Indicadores Herramentales" /F
cd /d "%~dp0"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
  echo No encontre pythonw.exe. Verifica que Python este instalado.
  pause
  exit /b 1
)
schtasks /Create /F /SC HOURLY /MO 1 /ST 06:00 /TN "Tablero Indicadores Herramentales" ^
  /TR "\"%PYW%\" -W ignore \"%~dp0generar_tablero.py\""
if errorlevel 1 (
  echo No se pudo crear la tarea.
) else (
  echo Listo: el tablero se actualizara cada hora mientras tu sesion de Windows este abierta.
)
pause
