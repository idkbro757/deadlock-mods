@echo off
rem Drag your CSDK12 folder onto this file if it cant find it by itself.
if "%~1"=="" (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_materials.ps1") else (powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0fix_materials.ps1" -CsdkPath "%~1")
pause
