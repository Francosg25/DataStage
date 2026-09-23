[CmdletBinding()]
param()
$ErrorActionPreference = 'Stop'
$workspace = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..'))
$statePath = Join-Path $workspace '.data\dev-processes.json'
if (-not (Test-Path -LiteralPath $statePath)) {
    Write-Host 'No hay procesos DataStage registrados por el lanzador.'
    return
}
$records = @(Get-Content -Raw -LiteralPath $statePath | ConvertFrom-Json)
$processSnapshot = @(Get-CimInstance Win32_Process -ErrorAction Stop)

function Test-OwnedIdentity($Current, [datetime]$StartedAt, [string]$Executable) {
    if (-not $Current -or -not $Current.CreationDate -or -not $Current.ExecutablePath -or -not $Executable) { return $false }
    $sameTime = [Math]::Abs(($Current.CreationDate.ToUniversalTime() - $StartedAt.ToUniversalTime()).TotalMilliseconds) -lt 1
    return $sameTime -and [string]::Equals($Current.ExecutablePath, $Executable, [StringComparison]::OrdinalIgnoreCase)
}
function Get-OwnedDescendants($Parent, [int]$Depth = 0) {
    foreach ($child in $processSnapshot | Where-Object { $_.ParentProcessId -eq $Parent.ProcessId }) {
        if (-not $child.CreationDate -or -not $child.ExecutablePath -or $child.CreationDate -lt $Parent.CreationDate) { continue }
        [PSCustomObject]@{ node = $child; depth = $Depth }
        Get-OwnedDescendants $child ($Depth + 1)
    }
}
function Stop-VerifiedProcess($Expected) {
    $current = Get-CimInstance Win32_Process -Filter "ProcessId=$($Expected.ProcessId)"
    if (-not $current) { return }
    if (-not (Test-OwnedIdentity $current $Expected.CreationDate $Expected.ExecutablePath)) {
        throw "El PID $($Expected.ProcessId) cambió de identidad; se conservó."
    }
    # CIM avoids a .NET Stop-Process failure affecting Windows Python launchers.
    try {
        $result = Invoke-CimMethod -InputObject $current -MethodName Terminate -ErrorAction Stop
    } catch {
        # Siblings may exit when their parent or esbuild worker shuts down.
        $after = Get-CimInstance Win32_Process -Filter "ProcessId=$($Expected.ProcessId)"
        if (-not $after -or -not (Test-OwnedIdentity $after $Expected.CreationDate $Expected.ExecutablePath)) { return }
        throw
    }
    if ($result.ReturnValue -ne 0) {
        $after = Get-CimInstance Win32_Process -Filter "ProcessId=$($Expected.ProcessId)"
        if ($after -and (Test-OwnedIdentity $after $Expected.CreationDate $Expected.ExecutablePath)) {
            throw "Windows no pudo detener el PID $($Expected.ProcessId): $($result.ReturnValue)."
        }
        return
    }
    for ($attempt = 0; $attempt -lt 30; $attempt++) {
        $after = Get-CimInstance Win32_Process -Filter "ProcessId=$($Expected.ProcessId)"
        if (-not $after -or -not (Test-OwnedIdentity $after $Expected.CreationDate $Expected.ExecutablePath)) { return }
        Start-Sleep -Milliseconds 100
    }
    throw "El PID $($Expected.ProcessId) no terminó. Se conserva el registro para revisión."
}
foreach ($record in $records) {
    if ($record.role -notin @('api', 'worker', 'frontend')) { throw 'Registro de proceso no reconocido.' }
    $parent = $processSnapshot | Where-Object ProcessId -eq $record.processId | Select-Object -First 1
    if (-not $parent) { continue }
    if (-not (Test-OwnedIdentity $parent ([datetime]$record.startedAt) $record.executable)) {
        throw "El PID $($record.processId) no coincide con el proceso original; se conservó."
    }
    $descendants = @(Get-OwnedDescendants $parent)
    foreach ($child in $descendants | Sort-Object depth -Descending) { Stop-VerifiedProcess $child.node }
    Stop-VerifiedProcess $parent
    Write-Host "Detenido: $($record.role) ($($record.processId))."
}
# A failure above leaves this file intact, allowing diagnosis and retry.
Remove-Item -LiteralPath $statePath
