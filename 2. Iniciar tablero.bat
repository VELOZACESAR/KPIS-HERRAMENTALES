@echo off
rem Arranca el tablero en esta ventana (para probar). Ctrl+C para detenerlo.
cd /d "%~dp0"
for /f "tokens=2 delims==" %%p in ('findstr /b "PUERTO=" .env 2^>nul') do set PUERTO=%%p
if "%PUERTO%"=="" set PUERTO=8050
echo Tablero en http://%COMPUTERNAME%:%PUERTO%  (en este PC: http://localhost:%PUERTO%)
start "" http://localhost:%PUERTO%
python servidor.py
pause
