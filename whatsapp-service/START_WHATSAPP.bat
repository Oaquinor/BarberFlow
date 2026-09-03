@echo off
chcp 65001 >nul
title KingFlow - WhatsApp Service (Baileys)

echo.
echo ╔════════════════════════════════════════════════════════════════════╗
echo ║                                                                    ║
echo ║         🚀 INICIANDO SERVICIO WHATSAPP (BAILEYS) 🚀               ║
echo ║                                                                    ║
echo ╚════════════════════════════════════════════════════════════════════╝
echo.

REM Cambiar al directorio del servicio
cd /d "%~dp0"

echo 📍 Directorio: %CD%
echo.

REM Verificar que node_modules existe
if not exist "node_modules" (
    echo ❌ node_modules no encontrado
    echo 📦 Instalando dependencias...
    echo.
    call npm install
    echo.
)

echo ✅ Dependencias listas
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 📱 INSTRUCCIONES PARA CONECTAR WHATSAPP:
echo.
echo    1️⃣  Espera a que aparezca el código QR
echo    2️⃣  Abre WhatsApp en tu teléfono
echo    3️⃣  Ve a: Menú ^(⋮^) → Dispositivos vinculados
echo    4️⃣  Toca: "Vincular un dispositivo"
echo    5️⃣  Escanea el QR que aparecerá abajo
echo.
echo    ⚠️  IMPORTANTE: Solo necesitas escanear UNA VEZ
echo        Después, la sesión se guarda automáticamente
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.
echo 🔄 Iniciando servidor en puerto 3001...
echo.
echo ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
echo.

REM Iniciar el servidor
node server.js

echo.
echo.
echo ❌ El servicio se detuvo
echo.
pause
