@echo off
setlocal

cd /d "%~dp0"

if not "%~1"=="" (
  powershell -NoProfile -ExecutionPolicy Bypass -File "%~dp0tools\graphify_argos.ps1" %*
  exit /b %errorlevel%
)

set "GRAPHIFY_VIEW=%~dp0graphify-out\GRAPH_TREE.html"
if not exist "%GRAPHIFY_VIEW%" set "GRAPHIFY_VIEW=%~dp0graphify-out\graph.html"

if not exist "%GRAPHIFY_VIEW%" (
  echo [ERRO] A visualizacao do Graphify ainda nao existe.
  echo Execute:
  echo   ABRIR_GRAPHIFY.cmd -Action Build
  pause
  exit /b 1
)

start "Graphify - ARGOS" "%GRAPHIFY_VIEW%"
exit /b 0
