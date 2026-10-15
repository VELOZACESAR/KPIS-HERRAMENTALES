@echo off
rem Registra el enlace "tablero-herramentales:" para el usuario actual (no requiere administrador).
rem Con esto, el boton "Actualizar ahora" del tablero ejecuta generar_tablero.py en segundo plano.
rem Para quitarlo:  reg delete "HKCU\Software\Classes\tablero-herramentales" /f
cd /d "%~dp0"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (
  echo No encontre pythonw.exe. Verifica que Python este instalado.
  pause
  exit /b 1
)
set "CLAVE=HKCU\Software\Classes\tablero-herramentales"
reg add "%CLAVE%" /ve /d "URL:Tablero Herramentales" /f >nul
reg add "%CLAVE%" /v "URL Protocol" /d "" /f >nul
reg add "%CLAVE%\shell\open\command" /ve /d "\"%PYW%\" -W ignore \"%~dp0generar_tablero.py\"" /f >nul
if errorlevel 1 (
  echo No se pudo registrar el boton.
) else (
  echo Listo: el boton "Actualizar ahora" del tablero ya funciona en este PC.
)
pause
