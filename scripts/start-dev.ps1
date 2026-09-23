[CmdletBinding()]
param(
    [string]$PythonExe = 'python',
    [string]$NodeExe = '',
    [switch]$SkipInstall
)
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$backendDir = Join-Path $workspace 'backend'
$frontendDir = Join-Path $workspace 'frontend'
$dataDir = Join-Path $workspace '.data'
$logDir = Join-Path $dataDir 'logs'
$statePath = Join-Path $dataDir 'dev-processes.json'
$venvPython = Join-Path $workspace '.venv\Scripts\python.exe'
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

if (Test-Path -LiteralPath $statePath) {
    foreach ($record in @(Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json)) {
        $process = Get-Process -Id $record.processId -ErrorAction SilentlyContinue
        if ($process -and $process.StartTime.ToUniversalTime().ToString('o') -eq $record.startedAt) {
            throw 'La aplicación ya tiene procesos activos. Ejecuta scripts/stop-dev.ps1 primero.'
        }
    }
}
function Test-LoopbackListener([int]$Port) {
    $probe = [Net.Sockets.TcpClient]::new()
    try {
        $connection = $probe.ConnectAsync([Net.IPAddress]::Loopback, $Port)
        if (-not $connection.Wait(500)) { return $false }
        return $probe.Connected
    } catch {
        $reason = $_.Exception.GetBaseException()
        if ($reason -is [Net.Sockets.SocketException] -and $reason.SocketErrorCode -eq [Net.Sockets.SocketError]::ConnectionRefused) {
            return $false
        }
        throw "No se pudo comprobar el puerto ${Port}: $($reason.Message)"
    } finally {
        $probe.Dispose()
    }
}
foreach ($port in @(8000, 4200)) {
    if (Test-LoopbackListener -Port $port) {
        throw "El puerto $port está ocupado. Detén su proceso antes de iniciar DataStage."
    }
}

if (-not $NodeExe) {
    $bundledNode = Join-Path $env:USERPROFILE '.cache\codex-runtimes\codex-primary-runtime\dependencies\node\bin\node.exe'
    $NodeExe = if (Test-Path -LiteralPath $bundledNode) { $bundledNode } else { (Get-Command node -ErrorAction Stop).Source }
}
$NodeExe = (Get-Command $NodeExe -ErrorAction Stop).Source
$nodeDirectory = Split-Path -Parent $NodeExe
$env:PATH = "$nodeDirectory;$env:PATH"
$npmCandidates = @(
    (Join-Path $nodeDirectory 'node_modules\npm\bin\npm-cli.js'),
    (Join-Path $nodeDirectory '..\node_modules\npm\bin\npm-cli.js'),
    (Join-Path $nodeDirectory '..\lib\node_modules\npm\bin\npm-cli.js')
)
$npmCommand = Get-Command npm.cmd -ErrorAction SilentlyContinue
if ($npmCommand) { $npmCandidates += Join-Path (Split-Path -Parent $npmCommand.Source) 'node_modules\npm\bin\npm-cli.js' }
$npmCli = $npmCandidates | Where-Object { Test-Path -LiteralPath $_ } | Select-Object -First 1
if (-not $npmCli) { throw 'No se encontró npm-cli.js. Instala Node.js con npm y proporciona -NodeExe si es necesario.' }

if (-not (Test-Path -LiteralPath $venvPython)) {
    & $PythonExe -m venv (Join-Path $workspace '.venv')
    if ($LASTEXITCODE -ne 0) { throw 'No fue posible crear el entorno Python.' }
}
if (-not $SkipInstall) {
    & $venvPython -m pip install --no-deps -r (Join-Path $backendDir 'requirements.lock')
    if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias Python.' }
    & $venvPython -m pip check
    if ($LASTEXITCODE -ne 0) { throw 'Las dependencias Python no son consistentes.' }
    & $venvPython (Join-Path $workspace 'scripts\check_dependency_lock.py')
    if ($LASTEXITCODE -ne 0) { throw 'El lock Python no coincide con el contrato del proyecto.' }
    Push-Location $frontendDir
    try {
        & $NodeExe $npmCli ci
        if ($LASTEXITCODE -ne 0) { throw 'Falló la instalación de dependencias Angular.' }
    } finally { Pop-Location }
}

# This launcher always creates a local-only development instance.
$env:DATASTAGE_ENVIRONMENT = 'development'
$env:DATASTAGE_AUTH_MODE = 'development'
$env:DATASTAGE_DATABASE_URL = 'sqlite:///' + (Join-Path $dataDir 'datastage.db').Replace('\', '/')
$env:DATASTAGE_DOCUMENT_ROOT = Join-Path $dataDir 'documents'
$env:DATASTAGE_CORS_ORIGINS = '["http://127.0.0.1:4200","http://localhost:4200"]'
Push-Location $backendDir
try {
    & $venvPython -m alembic upgrade head
    if ($LASTEXITCODE -ne 0) { throw 'Falló la migración local de base de datos.' }
} finally { Pop-Location }

$started = [Collections.Generic.List[object]]::new()
function Start-OwnedProcess([string]$Role, [string]$Executable, [string[]]$Arguments, [string]$WorkingDirectory) {
    $process = Start-Process -FilePath $Executable -ArgumentList $Arguments -WorkingDirectory $WorkingDirectory -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $logDir "$Role.log") -RedirectStandardError (Join-Path $logDir "$Role.error.log")
    $process.Refresh()
    $started.Add([PSCustomObject]@{ role = $Role; processId = $process.Id; startedAt = $process.StartTime.ToUniversalTime().ToString('o'); executable = [IO.Path]::GetFullPath($Executable) })
    ConvertTo-Json -InputObject @($started.ToArray()) | Set-Content -LiteralPath $statePath -Encoding utf8
}
try {
    Start-OwnedProcess 'api' $venvPython @('-m', 'uvicorn', 'app.main:app', '--host', '127.0.0.1', '--port', '8000', '--no-proxy-headers') $backendDir
    Start-OwnedProcess 'worker' $venvPython @('-m', 'app.worker') $backendDir
    $angularCli = Join-Path $frontendDir 'node_modules\@angular\cli\bin\ng.js'
    if (-not (Test-Path -LiteralPath $angularCli)) { throw 'Falta Angular CLI; vuelve a ejecutar sin -SkipInstall.' }
    Start-OwnedProcess 'frontend' $NodeExe @(('"' + $angularCli + '"'), 'serve', '--host', '127.0.0.1', '--port', '4200', '--proxy-config', 'proxy.conf.json') $frontendDir
    $ready = $false
    for ($attempt = 0; $attempt -lt 60; $attempt++) {
        foreach ($record in $started) {
            if (-not (Get-Process -Id $record.processId -ErrorAction SilentlyContinue)) {
                throw "El proceso $($record.role) terminó. Revisa $logDir."
            }
        }
        try {
            $null = Invoke-WebRequest -Uri 'http://127.0.0.1:8000/health/ready' -UseBasicParsing -TimeoutSec 2
            $null = Invoke-WebRequest -Uri 'http://127.0.0.1:4200/' -UseBasicParsing -TimeoutSec 2
            $ready = $true
            break
        } catch { Start-Sleep -Milliseconds 500 }
    }
    if (-not $ready) { throw "La aplicación no quedó lista. Revisa $logDir." }
    Write-Host 'DataStage: http://127.0.0.1:4200'
    Write-Host 'API: http://127.0.0.1:8000/docs'
    Write-Host "Logs: $logDir"
    Write-Host 'Para detener: .\scripts\stop-dev.ps1'
} catch {
    & (Join-Path $PSScriptRoot 'stop-dev.ps1')
    throw
}
