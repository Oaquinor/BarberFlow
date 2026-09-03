@echo off
title KingFlow Barber - Complete System Startup

echo.
echo ============================================================
echo    KINGFLOW BARBER - COMPLETE SYSTEM STARTUP
echo ============================================================
echo.
echo Este script iniciara:
echo   1. WhatsApp Service (Node.js - Puerto 3001)
echo   2. Backend API (FastAPI - Puerto 8000)
echo   3. Frontend Server (Python - Puerto 3000)
echo.
echo Presiona cualquier tecla para continuar...
pause >nul

echo.
echo ============================================================
echo    PASO 1: Verificando Node.js
echo ============================================================
echo.

where node >nul 2>&1
if %errorlevel% neq 0 (
    echo [ERROR] Node.js no esta instalado
    echo.
    echo Por favor instala Node.js desde: https://nodejs.org/
    echo Descarga la version LTS (Long Term Support^)
    echo.
    pause
    exit /b 1
)

node --version
npm --version
echo.
echo [OK] Node.js esta instalado

echo.
echo ============================================================
echo    PASO 2: Instalando dependencias de WhatsApp Service
echo ============================================================
echo.

cd whatsapp-service

if not exist node_modules (
    echo Instalando dependencias...
    call npm install
    if %errorlevel% neq 0 (
        echo [ERROR] Fallo la instalacion de dependencias
        pause
        exit /b 1
    )
    echo [OK] Dependencias instaladas
) else (
    echo [OK] Dependencias ya instaladas
)

cd ..

echo.
echo ============================================================
echo    PASO 3: Iniciando servicios
echo ============================================================
echo.

echo Iniciando WhatsApp Service en ventana separada...
start "KingFlow - WhatsApp Service" cmd /k "cd whatsapp-service && npm start"

timeout /t 3 /nobreak >nul

echo Iniciando Backend API en ventana separada...
cd backend
start "KingFlow - Backend API" cmd /k "call venv\Scripts\activate.bat && uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

timeout /t 3 /nobreak >nul

echo Iniciando Frontend Server en ventana separada...
start "KingFlow - Frontend" cmd /k "call venv\Scripts\activate.bat && python scripts\serve_frontend.py"

timeout /t 5 /nobreak >nul

echo.
echo ============================================================
echo    SISTEMA COMPLETAMENTE INICIADO
echo ============================================================
echo.
echo WhatsApp Service:  http://localhost:3001
echo Backend API:       http://127.0.0.1:8000
echo API Docs:          http://127.0.0.1:8000/docs
echo Frontend:          http://localhost:3000
echo.
echo ============================================================
echo    IMPORTANTE - WHATSAPP
echo ============================================================
echo.
echo Si es la PRIMERA VEZ que usas WhatsApp Service:
echo.
echo 1. Ve a la ventana "KingFlow - WhatsApp Service"
echo 2. Veras un codigo QR en la consola
echo 3. Abre WhatsApp en tu telefono
echo 4. Ve a Menu (tres puntos^) ^> Dispositivos vinculados
echo 5. Toca "Vincular un dispositivo"
echo 6. Escanea el QR que aparece en la consola
echo 7. Espera el mensaje: "WHATSAPP CONECTADO EXITOSAMENTE"
echo.
echo Despues de escanear una vez, no necesitaras hacerlo de nuevo.
echo La sesion quedara guardada automaticamente.
echo.
echo ============================================================
echo.

timeout /t 3 /nobreak >nul

echo Abriendo navegadores...
start http://localhost:3000
timeout /t 2 /nobreak >nul
start http://127.0.0.1:8000/docs

echo.
echo [OK] Sistema completamente operacional
echo.
echo Para detener todos los servicios, cierra las ventanas abiertas.
echo.
pause
