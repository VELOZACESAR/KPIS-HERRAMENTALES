@echo off
rem Programa el tablero para que arranque solo cada vez que se inicia sesion en este PC, sin ventanas.
rem (OneDrive solo sincroniza con la sesion abierta, por eso es al iniciar sesion y no al encender.)
rem Para quitarlo:  schtasks /Delete /TN "Tablero Herramentales" /F
cd /d "%~dp0"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (echo No encontre pythonw.exe. & pause & exit /b 1)
schtasks /Create /F /SC ONLOGON /RL LIMITED /TN "Tablero Herramentales" /TR "\"%PYW%\" \"%~dp0servidor.py\"" || (echo No se pudo crear la tarea. & pause & exit /b 1)
schtasks /Run /TN "Tablero Herramentales" >nul
echo Listo: el tablero queda corriendo y arranca solo al iniciar sesion.
echo Si otros PCs no lo abren, corre "4. Abrir puerto (como administrador).bat".
pause
