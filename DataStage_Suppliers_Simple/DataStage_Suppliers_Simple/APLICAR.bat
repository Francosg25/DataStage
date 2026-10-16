@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python aplicar.py %*
) else (
  py -3 aplicar.py %*
)
if errorlevel 1 echo Revisa el mensaje anterior. La actualizacion no se completo.
pause
