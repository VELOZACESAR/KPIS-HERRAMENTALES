@echo off
rem Instala lo necesario y crea las tablas del tablero en AGP_Ingenieria. Se puede correr las veces que sea.
cd /d "%~dp0"
python --version >nul 2>&1 || (echo No encontre Python. Instala Python 3.12 o superior y marca "Add to PATH". & pause & exit /b 1)
python -m pip install -q -r requirements.txt || (echo Fallo la instalacion de paquetes. & pause & exit /b 1)
if not exist ".env" (
  copy ".env.example" ".env" >nul
  echo Se creo el archivo .env. Abrelo, llena DB_USER y DB_PASSWORD y vuelve a correr este instalador.
  notepad ".env"
  pause
  exit /b 0
)
python instalar_bd.py || (echo No se pudo crear el esquema en la base de datos. Revisa el .env & pause & exit /b 1)
schtasks /Delete /TN "Tablero Indicadores Herramentales" /F >nul 2>&1
reg delete "HKCU\Software\Classes\tablero-herramentales" /f >nul 2>&1
echo.
echo Listo. Ahora corre "2. Iniciar tablero.bat" para probarlo.
pause
