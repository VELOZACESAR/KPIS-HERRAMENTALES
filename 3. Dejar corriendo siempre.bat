@echo off
rem Deja el tablero arrancando solo cada vez que se inicia sesion en este PC, sin ventanas.
rem Usa la carpeta Inicio de Windows: no necesita permisos de administrador.
rem (OneDrive solo sincroniza con la sesion abierta, por eso es al iniciar sesion y no al encender.)
rem Para quitarlo: borrar "Tablero Herramentales.lnk" de la carpeta  shell:startup
cd /d "%~dp0"
set "PYW="
for /f "delims=" %%i in ('where pythonw 2^>nul') do if not defined PYW set "PYW=%%i"
if not defined PYW (echo No encontre pythonw.exe. & pause & exit /b 1)
powershell -NoProfile -Command "$s=(New-Object -ComObject WScript.Shell).CreateShortcut([Environment]::GetFolderPath('Startup')+'\Tablero Herramentales.lnk'); $s.TargetPath='%PYW%'; $s.Arguments='\"%~dp0servidor.py\"'; $s.WorkingDirectory='%~dp0'; $s.WindowStyle=7; $s.Save()" || (echo No se pudo crear el acceso directo de inicio. & pause & exit /b 1)
netstat -ano | findstr ":8050 " | findstr LISTENING >nul && (
  echo El tablero ya esta corriendo. Desde el proximo inicio de sesion arranca solo.
) || (
  start "" "%PYW%" "%~dp0servidor.py"
  echo Listo: el tablero quedo corriendo y arranca solo cada vez que inicies sesion.
)
echo Si otros PCs no lo abren, corre "4. Abrir puerto (como administrador).bat".
pause
