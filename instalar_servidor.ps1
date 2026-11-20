# instalar_servidor.ps1
# Instala o ACTUALIZA el Tablero de Herramentales como servidor web en ESTA PC, SIN permisos de administrador.
# Se corre con instalar_servidor.bat (desde la carpeta de red o desde la carpeta del proyecto).
#
#   1. Detiene la versión anterior (solo la suya)
#   2. Copia el código a %USERPROFILE%\TableroHerramentales_servidor (el .env, el .venv y los logs no se tocan)
#   3. Si no hay .env, lo arma pidiendo las claves en pantalla (la clave NUNCA queda en la carpeta de red)
#   4. Prepara Python (.venv) e instala lo necesario
#   5. Revisa que esta PC vea los Excel por OneDrive, la base y Edge (para el reporte a Teams)
#   6. Tarea programada del usuario: al iniciar sesión + vigilante cada 5 min (si se cae, se levanta sola)
#   7. La arranca y comprueba que responda

param(
    [string]$Destino = (Join-Path $env:USERPROFILE 'TableroHerramentales_servidor'),
    [int]$Puerto = 8050,
    [string]$Tarea = 'Tablero Herramentales'
)
$ErrorActionPreference = 'Stop'
$Origen = $PSScriptRoot

function Paso($texto) { Write-Host "`n>> $texto" -ForegroundColor Cyan }
function Ok($texto)   { Write-Host "   OK  $texto" -ForegroundColor Green }
function Ojo($texto)  { Write-Host "   OJO $texto" -ForegroundColor Yellow }

# ---------------------------------------------------------------- 1. detener
Paso 'Deteniendo la versión anterior (si existe)'
try { Stop-ScheduledTask -TaskName $Tarea -ErrorAction SilentlyContinue } catch { }
$nuestros = Get-CimInstance Win32_Process | Where-Object { $_.Name -in 'python.exe', 'pythonw.exe' -and $_.ExecutablePath -like "$Destino\*" }
foreach ($p in $nuestros) {
    Get-CimInstance Win32_Process -Filter "ParentProcessId=$($p.ProcessId)" | ForEach-Object { Stop-Process -Id $_.ProcessId -Force -ErrorAction SilentlyContinue }
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}
Start-Sleep -Seconds 2
$ocupado = Get-NetTCPConnection -LocalPort $Puerto -State Listen -ErrorAction SilentlyContinue
if ($ocupado) {
    $quien = (Get-Process -Id $ocupado[0].OwningProcess -ErrorAction SilentlyContinue).Path
    Ojo "el puerto $Puerto sigue ocupado por: $quien"
    throw "Puerto $Puerto ocupado: cierra esa copia y vuelve a correr el instalador"
}
Ok 'listo'

# ---------------------------------------------------------------- 2. copiar código
if ($Origen -ne $Destino) {
    Paso "Copiando el código a $Destino"
    New-Item -ItemType Directory -Force -Path $Destino | Out-Null
    robocopy $Origen $Destino /E /XD .venv logs __pycache__ tests .git /XF .env *.pyc /R:2 /W:2 /NJH /NJS /NDL /NFL /NP | Out-Null
    if ($LASTEXITCODE -ge 8) { throw "No se pudo copiar el código (robocopy $LASTEXITCODE)" }
    Ok 'código actualizado'
}

# ---------------------------------------------------------------- 3. .env
Paso 'Revisando el archivo .env'
$envDestino = Join-Path $Destino '.env'
$envRed = Join-Path $Origen '.env'
if (-not (Test-Path $envDestino) -and (Test-Path $envRed) -and $Origen -ne $Destino) {
    # el .env se deja en la carpeta de red solo para la instalación: se copia a esta PC y se borra de la red
    Copy-Item $envRed $envDestino
    Remove-Item $envRed -Force -ErrorAction SilentlyContinue
    if (Test-Path $envRed) { Ojo "no se pudo borrar $envRed de la red: bórralo a mano" } else { Ok '.env copiado a esta PC y borrado de la carpeta de red' }
}
if (-not (Test-Path $envDestino)) {
    Ojo 'Esta PC aún no tiene las claves. Se piden UNA vez y quedan solo en esta PC.'
    function Clave($texto) {
        $s = Read-Host $texto -AsSecureString
        [Runtime.InteropServices.Marshal]::PtrToStringAuto([Runtime.InteropServices.Marshal]::SecureStringToBSTR($s))
    }
    $usuario = Read-Host 'Usuario de la base AGP_Ingenieria'
    $clave = Clave 'Clave de ese usuario'
    $edicion = Clave 'Clave de edición del tablero (Enter = sin clave)'
    $teams = Clave 'URL del flujo de Teams (Enter = sin reporte a Teams)'
    $lineas = @(
        'DB_SERVER=agpcolombia.database.windows.net', 'DB_NAME=AGP_Ingenieria', "DB_USER=$usuario", "DB_PASSWORD=$clave",
        'DB_DRIVER=ODBC Driver 18 for SQL Server', 'HOST=0.0.0.0', "PUERTO=$Puerto", "CLAVE_EDICION=$edicion",
        'SEGUNDOS_REVISION=60', "TEAMS_FLUJO_URL=$teams"
    )
    [IO.File]::WriteAllLines($envDestino, $lineas, (New-Object Text.UTF8Encoding $false))
    Ok '.env creado en esta PC'
} else { Ok '.env ya existe (no se toca)' }

# ---------------------------------------------------------------- 4. Python
Paso 'Preparando Python'
$py = $null; $pyArgs = @(); $v = $null
$verScript = "import sys; print('%d.%d' % sys.version_info[:2])"
if (Get-Command py -ErrorAction SilentlyContinue) {
    try { $v = & py -3 -c $verScript 2>$null; if ($LASTEXITCODE -eq 0 -and $v) { $py = 'py'; $pyArgs = @('-3') } } catch { }
}
if (-not $py -and (Get-Command python -ErrorAction SilentlyContinue)) {
    try { $v = & python -c $verScript 2>$null; if ($LASTEXITCODE -eq 0 -and $v) { $py = 'python' } } catch { }
}
if (-not $py) { throw 'No encontré Python. Instala Python 3.11+ (marca "Add to PATH") y vuelve a correr.' }
if ([version]"$v" -lt [version]'3.10') { throw "Python $v es muy viejo: instala 3.11 o superior." }
Ok "Python $v"
$venvPy = Join-Path $Destino '.venv\Scripts\python.exe'
$venvPyw = Join-Path $Destino '.venv\Scripts\pythonw.exe'
if (-not (Test-Path $venvPy)) {
    & $py @pyArgs -m venv (Join-Path $Destino '.venv')
    if (-not (Test-Path $venvPy)) { throw 'No se pudo crear el entorno .venv' }
}
& $venvPy -m pip install --disable-pip-version-check -q -r (Join-Path $Destino 'requirements.txt')
if ($LASTEXITCODE -ne 0) { throw 'No se pudieron instalar las dependencias (revisa internet / proxy)' }
Ok 'dependencias instaladas'

# ---------------------------------------------------------------- 5. revisiones
Paso 'Revisando los Excel (OneDrive), la base y Edge'
& $venvPy (Join-Path $Destino 'scripts\revisar_fuentes.py')
$faltan = $LASTEXITCODE
if ($faltan -gt 0) {
    Ojo "$faltan Excel no aparecen en el OneDrive de esta PC. Abre OneDrive con tu cuenta AGP y espera a que aparezca"
    Ojo 'la carpeta "Shortcuts" (los accesos directos de SharePoint viajan con la cuenta). El servidor arranca igual'
    Ojo 'y los toma solo cuando aparezcan; mientras tanto esas fuentes salen en rojo al final del tablero.'
} else { Ok 'los Excel se ven desde esta PC' }
$edge = @("${env:ProgramFiles(x86)}\Microsoft\Edge\Application\msedge.exe", "$env:ProgramFiles\Microsoft\Edge\Application\msedge.exe") | Where-Object { Test-Path $_ } | Select-Object -First 1
if ($edge) { Ok 'Edge encontrado (reporte a Teams)' } else { Ojo 'No encontré Microsoft Edge: el botón de Teams no va a funcionar en esta PC' }

# ---------------------------------------------------------------- 6. inicio automático
Paso 'Configurando el inicio automático (al iniciar sesión + vigilante cada 5 min)'
$accion = New-ScheduledTaskAction -Execute $venvPyw -Argument 'servidor.py' -WorkingDirectory $Destino
$alIniciar = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$alIniciar.Delay = 'PT1M'
$vigilante = New-ScheduledTaskTrigger -Once -At (Get-Date).AddMinutes(1) -RepetitionInterval (New-TimeSpan -Minutes 5)
$ajustes = New-ScheduledTaskSettingsSet -ExecutionTimeLimit ([TimeSpan]::Zero) -MultipleInstances IgnoreNew `
    -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable
$principal = New-ScheduledTaskPrincipal -UserId "$env:USERDOMAIN\$env:USERNAME" -LogonType Interactive -RunLevel Limited
Register-ScheduledTask -TaskName $Tarea -Action $accion -Trigger @($alIniciar, $vigilante) -Settings $ajustes -Principal $principal -Force | Out-Null
Ok "tarea '$Tarea' registrada (si el servidor se cae, a los 5 min se levanta solo)"

# ---------------------------------------------------------------- 7. arrancar y probar
Paso 'Arrancando y comprobando'
Start-ScheduledTask -TaskName $Tarea
$responde = $false
for ($i = 0; $i -lt 60 -and -not $responde; $i++) {
    Start-Sleep -Seconds 2
    try { $r = Invoke-RestMethod "http://127.0.0.1:$Puerto/api/salud" -TimeoutSec 5; $responde = $r.bd -eq 'ok' } catch { }
}
$log = Join-Path $Destino 'logs\servidor.log'
if (-not $responde) {
    Ojo 'el servidor todavía no responde. Últimas líneas del registro:'
    Get-Content $log -Tail 25 -ErrorAction SilentlyContinue
    throw "Revisa $log"
}
$nombre = [System.Net.Dns]::GetHostEntry($env:COMPUTERNAME).HostName.ToLower()
Write-Host ''
Write-Host '============================================================' -ForegroundColor Green
Write-Host ' El Tablero de Herramentales quedó funcionando en esta PC' -ForegroundColor Green
Write-Host "   http://$($nombre):$Puerto" -ForegroundColor Green
Write-Host " Registro: $log" -ForegroundColor Green
Write-Host ' La primera carga de los Excel tarda unos minutos.' -ForegroundColor Green
Write-Host ' Para actualizar: volver a correr instalar_servidor.bat desde la carpeta de red' -ForegroundColor Green
Write-Host '============================================================' -ForegroundColor Green
Ojo "Abre el link DESDE OTRA PC. Si no abre, el firewall bloquea el puerto ${Puerto}: pídele a TI una regla de entrada TCP $Puerto."
Ojo 'Si antes corría en otra PC, apágalo allá para no tener dos servidores cargando a la misma base.'
