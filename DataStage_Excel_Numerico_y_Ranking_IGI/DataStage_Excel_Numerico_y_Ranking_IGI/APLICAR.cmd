@echo off
setlocal
chcp 65001 >nul
set "DS_PROJECT=%~1"
if not defined DS_PROJECT set "DS_PROJECT=%USERPROFILE%\OneDrive - JE\Desktop\PROYECTOS GRANDES\DataStage"
set "DS_PYTHON=%DS_PROJECT%\.venv\Scripts\python.exe"
if exist "%DS_PYTHON%" goto ejecutar
set "DS_PYTHON=python"
:ejecutar
"%DS_PYTHON%" "%~dp0aplicar.py" "%DS_PROJECT%"
set "DS_RESULT=%ERRORLEVEL%"
echo.
pause
exit /b %DS_RESULT%
