@echo off
rem Funny Valentine -> Doorman. Edit these three paths, then double-click.
set "BLENDER=C:\Program Files\Blender Foundation\Blender 4.2\blender.exe"
set "MODEL=%~dp0..\funny-valentine-d4c-sbr\source\D$C_blend3_66.blend"
set "HERO_DIR=C:\CSDK12\content\citadel_addons\funny_valentine\models\heroes_wip\doorman_v2"

rem Any extra options (e.g. --with-stand --scale 1.05) can be passed on the command line.
"%BLENDER%" -b -P "%~dp0fv_build.py" -- --model "%MODEL%" --hero-dir "%HERO_DIR%" --preview "%~dp0fv_preview" --save-blend "%~dp0fv_fitted.blend" --gun "%~dp0props\fv_revolver.glb" %*
pause
