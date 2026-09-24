@echo off
if "%~1"=="" (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_materials.ps1" -Check) else (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_materials.ps1" -Check -CsdkPath "%~1")
pause
