@echo off
title GoonZu Farm Tracker - Launcher
color 0A

echo ========================================
echo    GoonZu Farm Tracker - Multi-Client
echo ========================================
echo.

:: Verifica se Python è installato
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERRORE] Python non trovato!
    echo Installa Python da https://python.org
    pause
    exit /b 1
)

:: Verifica dipendenze
echo [1/4] Verifica dipendenze Python...
pip show psutil >nul 2>&1
if errorlevel 1 (
    echo Installazione psutil...
    pip install psutil
)

pip show pywin32 >nul 2>&1
if errorlevel 1 (
    echo Installazione pywin32...
    pip install pywin32
)

pip show fastapi >nul 2>&1
if errorlevel 1 (
    echo Installazione fastapi...
    pip install fastapi uvicorn
)

echo [2/4] Avvio API Server...
start "GoonZu API Server" cmd /k "title API Server && echo API Server in esecuzione su http://localhost:8000 && python api.py"

:: Attendi che l'API sia pronta
timeout /t 3 /nobreak >nul

echo [3/4] Avvio dashboard web...
start "GoonZu Dashboard" cmd /k "title Dashboard && echo Dashboard disponibile su http://localhost:8000 && start http://localhost:8000"

echo [4/4] Configurazione completata!
echo.
echo ========================================
echo    STATO SERVIZI:
echo ========================================
echo ✅ API Server: http://localhost:8000
echo ✅ Dashboard: http://localhost:8000
echo.
echo ℹ️  NOTA: Lo scanner verra' avviato dal dashboard
echo    quando selezioni un client GoonZu.
echo.
echo ========================================
echo Premi un tasto per chiudere questa finestra
echo (i servizi continueranno a funzionare)
echo ========================================
pause >nul