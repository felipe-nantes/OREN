@echo off
setlocal
title OREN - Meta Quest 3S sem certificado
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_quest_http_win.ps1"
if errorlevel 1 pause
endlocal
