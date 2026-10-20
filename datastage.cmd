@echo off
setlocal
if defined DATASTAGE_PYTHON goto corporate
if exist "%~dp0.venv\Scripts\python.exe" (
  "%~dp0.venv\Scripts\python.exe" "%~dp0scripts\dev.py" %*
  exit /b
)
python "%~dp0scripts\dev.py" %*
exit /b
:corporate
"%DATASTAGE_PYTHON%" "%~dp0scripts\dev.py" %*
exit /b
