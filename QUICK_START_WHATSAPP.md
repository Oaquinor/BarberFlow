# 🚀 Guía Rápida - Inicio Completo con WhatsApp

**Sistema completo de KingFlow Barber con notificaciones WhatsApp GRATIS**

---

## ⚡ Inicio Rápido (5 minutos)

### **Paso 1: Instalar Node.js** (Si no lo tienes)

1. Ir a: https://nodejs.org/
2. Descargar **versión LTS** (Long Term Support)
3. Instalar con opciones por defecto
4. Verificar instalación:
```bash
node --version
npm --version
```

### **Paso 2: Instalar Dependencias de WhatsApp**

```bash
cd whatsapp-service
npm install
```

### **Paso 3: Iniciar TODO el Sistema**

**Opción A: Script Automático (Windows)**
```bash
# Doble click en:
START_ALL_SERVICES.bat
```

**Opción B: Manual (3 terminales)**

**Terminal 1 - WhatsApp Service:**
```bash
cd whatsapp-service
npm start
```

**Terminal 2 - Backend API:**
```bash
cd backend
.\venv\Scripts\Activate.ps1
uvicorn app.main:app --reload
```

**Terminal 3 - Frontend:**
```bash
cd backend
.\venv\Scripts\Activate.ps1
python scripts/serve_frontend.py
```

### **Paso 4: Conectar WhatsApp (Solo Primera Vez)**

1. **Ve a la terminal de WhatsApp Service**
2. **Verás un QR code**
3. **Abre WhatsApp en tu teléfono:**
   - Menú (⋮) → **Dispositivos vinculados**
   - Toca **"Vincular un dispositivo"**
   - **Escanea el QR**

4. **Verás:**
```
╔════════════════════════════════════════════════════════╗
║                                                        ║
║          ✅ WHATSAPP CONECTADO EXITOSAMENTE ✅        ║
║                                                        ║
╚════════════════════════════════════════════════════════╝
```

**¡Listo! Ya no necesitarás escanear de nuevo.**

---

## 🌐 URLs del Sistema

| Servicio | URL | Descripción |
|----------|-----|-------------|
| **WhatsApp Service** | http://localhost:3001 | API de WhatsApp |
| **Backend API** | http://127.0.0.1:8000 | API REST principal |
| **API Docs** | http://127.0.0.1:8000/docs | Swagger UI |
| **Frontend** | http://localhost:3000 | Interfaz web |

---

## 🧪 Probar WhatsApp

### Probar desde la terminal:

**PowerShell:**
```powershell
$body = @{
    phone = "+18095555555"
    message = "✅ Prueba desde KingFlow Barber!"
} | ConvertTo-Json

Invoke-RestMethod -Uri "http://localhost:3001/send" -Method Post -Body $body -ContentType "application/json"
```

**cURL (Git Bash):**
```bash
curl -X POST http://localhost:3001/send \
  -H "Content-Type: application/json" \
  -d '{"phone":"+18095555555","message":"✅ Prueba desde KingFlow!"}'
```

**Python:**
```python
import requests

requests.post('http://localhost:3001/send', json={
    'phone': '+18095555555',
    'message': '✅ Prueba desde KingFlow Barber!'
})
```

---

## 📱 Probar Notificación Completa

### Crear una cita (automáticamente envía WhatsApp):

1. **Ir a:** http://127.0.0.1:8000/docs
2. **Expandir:** `POST /api/v1/appointments/`
3. **Try it out**
4. **Body:**
```json
{
  "barbershop_id": 1,
  "barber_id": 2,
  "scheduled_time": "2024-06-01T14:00:00",
  "service_type": "haircut_beard",
  "estimated_duration": 30,
  "send_confirmation": true
}
```

5. **Execute**

**El cliente recibirá:**
- ✉️ Email de confirmación
- 💬 WhatsApp con todos los detalles

---

## 🔍 Verificar Estado

### Health Check de WhatsApp:

```bash
# PowerShell
Invoke-RestMethod http://localhost:3001/health

# Respuesta:
{
  "status": "ok",
  "connected": true,
  "waiting_qr": false,
  "timestamp": "2024-05-30T..."
}
```

### Health Check de Backend:

```bash
Invoke-RestMethod http://127.0.0.1:8000/health
```

---

## 🎯 Flujo Completo de Notificaciones

```
CLIENTE AGENDA CITA
        ↓
FastAPI crea cita en BD
        ↓
NotificationService.send_appointment_confirmation()
        ↓
    ┌───┴────┐
    ▼        ▼
 EMAIL   WHATSAPP
(SMTP)   (Baileys)
    │        │
    └────┬───┘
         ▼
  CLIENTE RECIBE
  NOTIFICACIONES
```

---

## 📊 Monitoreo

### Ver logs de WhatsApp Service:

La terminal de WhatsApp Service muestra:
- ✅ Mensajes enviados
- ❌ Errores
- 🔄 Reconexiones
- 📱 Mensajes recibidos

### Ver logs de Backend:

La terminal de FastAPI muestra:
- 📧 Emails enviados
- 💬 WhatsApp enviados
- 🔥 Servicios iniciados/finalizados
- ⚠️ Errores

---

## 🐛 Troubleshooting

### ❌ WhatsApp no conecta

**Solución:**
1. Verificar que Node.js esté instalado: `node --version`
2. Reinstalar dependencias:
```bash
cd whatsapp-service
rm -rf node_modules
npm install
```
3. Borrar sesión antigua:
```bash
rm -rf auth_info_baileys
npm start
```
4. Escanear QR de nuevo

---

### ❌ "Module not found: @whiskeysockets/baileys"

**Solución:**
```bash
cd whatsapp-service
npm install
```

---

### ❌ Mensaje no llega

**Verificar:**
1. WhatsApp Service conectado: `http://localhost:3001/health`
2. Formato de teléfono correcto: `+18095555555`
3. Número tiene WhatsApp: `http://localhost:3001/check/18095555555`

---

### ❌ QR no aparece

**Solución:**
```bash
cd whatsapp-service
rm -rf auth_info_baileys
npm start
```

---

## 🎨 Formato de Mensajes WhatsApp

### Formato Soportado:

```
*Texto en negrita*
_Texto en cursiva_
~Texto tachado~
```Texto monoespaciado```

Ejemplo:
```
👑 *Elite Barber Shop*

✅ *Cita Confirmada*

Hola Juan Pérez,

📅 *Fecha:* Viernes, 30 de Mayo
⏰ *Hora:* _2:00 PM_
✂️ *Servicio:* Corte + Barba Premium
👤 *Barbero:* Carlos Martínez

⏰ Por favor llega 5-10 minutos antes.

¡Te esperamos! 👋
```

---

## 📈 Producción

### Para correr 24/7 (Producción):

**Instalar PM2:**
```bash
npm install -g pm2
```

**Iniciar servicios:**
```bash
# WhatsApp Service
cd whatsapp-service
pm2 start server.js --name whatsapp

# Backend API
cd backend
pm2 start "uvicorn app.main:app --host 0.0.0.0 --port 8000" --name api

# Ver estado
pm2 status

# Ver logs
pm2 logs

# Reiniciar
pm2 restart all

# Iniciar al boot
pm2 startup
pm2 save
```

---

## 🔒 Seguridad

### Importante:

1. ✅ **Backup de `auth_info_baileys/`** - Contiene tu sesión
2. ✅ **No compartir** la carpeta de sesión
3. ✅ **Rate limiting** - No enviar spam
4. ✅ **Validar números** antes de enviar
5. ✅ **Respetar horarios** - No enviar de noche

---

## ✅ Checklist de Verificación

- [ ] Node.js instalado (`node --version`)
- [ ] Dependencias instaladas (`npm install` en whatsapp-service)
- [ ] WhatsApp Service corriendo (`http://localhost:3001/health`)
- [ ] Backend API corriendo (`http://127.0.0.1:8000/health`)
- [ ] Frontend accesible (`http://localhost:3000`)
- [ ] WhatsApp conectado (QR escaneado)
- [ ] Prueba de envío exitosa

---

## 📞 Soporte

Si tienes problemas:

1. **Revisar logs** en las terminales
2. **Verificar health checks** de los servicios
3. **Consultar** `whatsapp-service/README.md`
4. **Consultar** `docs/NOTIFICATIONS_SYSTEM.md`

---

## 🎉 ¡Listo para Producción!

Con esto tienes:
- ✅ Sistema de notificaciones completo
- ✅ WhatsApp GRATIS e ilimitado
- ✅ Emails profesionales
- ✅ Frontend funcional
- ✅ Backend robusto

**Todo integrado y funcionando automáticamente** 🚀

---

**Creado:** 2024-05-30  
**Versión:** 1.0.0
