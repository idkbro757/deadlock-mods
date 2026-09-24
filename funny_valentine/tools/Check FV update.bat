@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0install_update.ps1" -Check %*
pause
