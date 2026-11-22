@echo off
cd /d "%~dp0"
powershell.exe -NoProfile -ExecutionPolicy Bypass -File "%~dp0INICIAR_WINDOWS.ps1"
if errorlevel 1 (
  echo.
  echo Houve um erro. Leia a mensagem acima.
  pause
)
