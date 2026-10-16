@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>nul
if errorlevel 1 (
  python aplicar.py %*
) else (
  py -3 aplicar.py %*
)
if errorlevel 1 echo No se pudo completar la actualizacion. Revisa el mensaje anterior.
pause
