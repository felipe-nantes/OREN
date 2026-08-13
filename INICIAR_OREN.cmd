@echo off
setlocal
title OREN - Inicializacao
cd /d "%~dp0"

echo ============================================================
echo   OREN - MedGemma 4B + Webapp + Visualizador 3D
echo ============================================================
echo.
echo O servidor sera aberto em http://127.0.0.1:8080
echo A primeira inicializacao pode levar alguns minutos enquanto
echo o MedGemma 4B e carregado na GPU.
echo.

powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File "%~dp0run_win.ps1"
set "OREN_EXIT=%ERRORLEVEL%"

if not "%OREN_EXIT%"=="0" (
  echo.
  echo ============================================================
  echo O OREN encerrou com erro ^(codigo %OREN_EXIT%^).
  echo Consulte os logs em: %~dp0casos
  echo ============================================================
  pause
)

endlocal & exit /b %OREN_EXIT%
