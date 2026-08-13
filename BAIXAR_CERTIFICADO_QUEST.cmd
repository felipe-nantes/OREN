@echo off
setlocal
title OREN - Certificado Meta Quest
cd /d "%~dp0"
powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0servir_certificado_quest.ps1"
if errorlevel 1 pause
endlocal
