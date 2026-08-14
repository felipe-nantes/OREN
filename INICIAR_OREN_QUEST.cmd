@echo off
setlocal
title OREN - Meta Quest (IP automatico)
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\start_oren_quest_dynamic.ps1" -NoBuild
if errorlevel 1 pause
endlocal
