@echo off
title GoonZu Farm Launcher

echo ============================================
echo   GoonZu Farm Tracker
echo ============================================
echo.

REM ── API server (normal window) ───────────────
echo [1/2] Starting API server on http://localhost:8000 ...
start "GoonZu API" cmd /k "title GoonZu API ^& python api.py"

REM ── Short delay so API starts first ─────────
timeout /t 2 /nobreak >nul

REM ── Scanner needs Admin for memory access ───
echo [2/2] Starting loot scanner (requesting Admin)...
powershell -Command "Start-Process cmd -ArgumentList '/k title GoonZu Scanner ^&^& python \"%~dp0loot_scanner.py\"' -WorkingDirectory '%~dp0' -Verb RunAs"

REM ── Open dashboard in browser ───────────────
timeout /t 3 /nobreak >nul
echo.
echo Opening dashboard...
start http://localhost:8000

echo.
echo Both processes started. You can close this window.
timeout /t 5 /nobreak >nul
