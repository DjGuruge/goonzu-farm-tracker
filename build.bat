@echo off
title GoonZu Farm — Build EXE

echo ============================================
echo   Building GoonZuFarm.exe ...
echo ============================================
echo.

pip install pyinstaller >nul 2>&1

pyinstaller GoonZuFarm.spec --clean --noconfirm

if %ERRORLEVEL% EQU 0 (
    echo.
    echo ============================================
    echo   Build successful!
    echo   Output: dist\GoonZuFarm.exe
    echo ============================================
    explorer dist
) else (
    echo.
    echo [ERROR] Build failed. Check output above.
)

pause
