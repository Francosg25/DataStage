# Compatibility wrapper; no PowerShell policy changes are required.
& (Join-Path $PSScriptRoot '..\datastage.cmd') stop
exit $LASTEXITCODE
