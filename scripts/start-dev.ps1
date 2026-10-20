# Compatibility wrapper. Prefer datastage.cmd when PowerShell scripts are restricted.
[CmdletBinding()]
param([string]$PythonExe = '', [string]$NodeExe = '', [switch]$SkipInstall)
if ($PythonExe) { $env:DATASTAGE_PYTHON = $PythonExe }
if ($NodeExe) { $env:DATASTAGE_NODE = $NodeExe }
# No dependency installation, regardless of the legacy SkipInstall switch.
& (Join-Path $PSScriptRoot '..\datastage.cmd') start
exit $LASTEXITCODE
