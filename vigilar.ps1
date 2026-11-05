# Si el tablero no está escuchando en el 8050 lo vuelve a levantar. Lo corre una tarea programada cada 3 minutos.
$carpeta = $PSScriptRoot
$python = "$env:LOCALAPPDATA\Python\pythoncore-3.14-64\pythonw.exe"
if (Get-NetTCPConnection -LocalPort 8050 -State Listen -ErrorAction SilentlyContinue) { exit 0 }
Add-Content "$carpeta\logs\vigilante.log" "$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss') servidor caído, se reinicia"
Start-Process -FilePath $python -ArgumentList "servidor.py" -WorkingDirectory $carpeta -WindowStyle Hidden
