@echo off
title KingFlow Barber - System Startup

echo.
echo ==============================================
echo    KINGFLOW BARBER - SYSTEM STARTUP
echo ==============================================
echo.

cd backend
call venv\Scripts\activate.bat

cls
echo.
echo ==============================================
echo    KINGFLOW BARBER - INICIANDO SISTEMA
echo ==============================================
echo.

python scripts\start_all.py

pause
