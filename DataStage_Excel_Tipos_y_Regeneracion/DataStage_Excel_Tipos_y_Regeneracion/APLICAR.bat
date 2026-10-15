@echo off
setlocal
chcp 65001 >nul
set "DS_PROJECT=%USERPROFILE%\OneDrive - JE\Desktop\PROYECTOS GRANDES\DataStage"
if not "%~1"=="" set "DS_PROJECT=%~1"
if not exist "%DS_PROJECT%\frontend\package.json" (
  echo No se encontro DataStage en la ruta predeterminada.
  set /p "DS_PROJECT=Escribe la ruta completa de la carpeta DataStage: "
)
if exist "%DS_PROJECT%\.venv\Scripts\python.exe" (
  "%DS_PROJECT%\.venv\Scripts\python.exe" "%~dp0aplicar.py" "%DS_PROJECT%"
) else (
  python "%~dp0aplicar.py" "%DS_PROJECT%"
)
set "DS_EXIT=%ERRORLEVEL%"
echo.
if not "%DS_EXIT%"=="0" echo Revisa el mensaje de error anterior.
pause
exit /b %DS_EXIT%
