@echo off
powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0extract_door.ps1" %*
pause
