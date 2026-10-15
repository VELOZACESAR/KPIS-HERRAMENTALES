@echo off
rem Abre el puerto del tablero en el firewall de Windows para que los demas PCs de la red de AGP lo vean.
rem Clic derecho > Ejecutar como administrador.
cd /d "%~dp0"
for /f "tokens=2 delims==" %%p in ('findstr /b "PUERTO=" .env 2^>nul') do set PUERTO=%%p
if "%PUERTO%"=="" set PUERTO=8050
netsh advfirewall firewall delete rule name="Tablero Herramentales" >nul 2>&1
netsh advfirewall firewall add rule name="Tablero Herramentales" dir=in action=allow protocol=TCP localport=%PUERTO% profile=domain,private || (echo Hay que ejecutarlo como administrador. & pause & exit /b 1)
echo Listo. Comparte este enlace:  http://%COMPUTERNAME%:%PUERTO%
ipconfig | findstr /i "IPv4"
pause
