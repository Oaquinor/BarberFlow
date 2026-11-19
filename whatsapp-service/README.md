# 💬 KingFlow Barber - WhatsApp Service (Baileys)

**Gateway opcional de WhatsApp usando Baileys**

---

## 🎯 ¿Qué es esto?

Un servicio Node.js independiente que expone una API REST autenticada. Se vincula a una cuenta con QR y FastAPI lo usa para enviar los mensajes encolados. La conexión requiere una sesión activa y las entregas reales dependen del estado del servicio y de las condiciones aplicables a la cuenta.

---

## ✅ Características

- ✅ Vinculación de cuenta mediante QR
- ✅ Sesión persistente en volumen protegido
- ✅ API REST autenticada para el backend
- ✅ **Reconexión automática** - Si se cae, se reconecta solo
- ✅ **Formato completo** - Negritas, cursivas, emojis, imágenes
- ✅ **Sesión persistente** - Escanea QR una sola vez
- ✅ **API REST** - Fácil de integrar con FastAPI

---

## 📦 Instalación

### Paso 1: Instalar Node.js

**Windows:**
1. Descargar desde: https://nodejs.org/
2. Instalar versión LTS (Long Term Support)
3. Verificar instalación:
```bash
node --version
npm --version
```

### Paso 2: Instalar Dependencias

```bash
cd whatsapp-service
npm install
```

Esto instalará:
- `@whiskeysockets/baileys` - Cliente WhatsApp
- `express` - Servidor web
- `qrcode-terminal` - Para mostrar QR en consola
- `pino` - Logger
- `cors` - CORS para API

---

## 🚀 Uso

### Seguridad de la API

Antes de iniciar el servicio, configura un secreto largo y aleatorio en `WHATSAPP_API_TOKEN` tanto en el proceso Node.js como en `backend/.env`. FastAPI lo envía como `Authorization: Bearer ...`. Los endpoints de envío, consulta de número, información de la sesión y desconexión responden `401` sin el token; si falta la configuración responden `503`. `/health` permanece disponible sin autenticación y no revela el número vinculado. El servicio escucha en `127.0.0.1` por defecto; define `WHATSAPP_BIND_HOST` solo si necesitas otro enlace de red y protege esa red.

Las solicitudes JSON están limitadas a 16 KB. Los cuerpos demasiado grandes reciben `413`; el JSON malformado recibe `400`. Los errores internos se registran en el servicio y la API devuelve mensajes genéricos sin detalles de la excepción.

Ejemplo PowerShell (usa el mismo valor en ambas consolas):

```powershell
$env:WHATSAPP_API_TOKEN = "<secreto-aleatorio-largo>"
npm start
```

Si FastAPI está en otra máquina o contenedor, define `WHATSAPP_API_URL` con una dirección alcanzable desde el backend y configura el acceso de red de forma explícita.

### Primera Vez: Conectar WhatsApp

```bash
cd whatsapp-service
npm start
```

**Verás algo así:**

```
╔════════════════════════════════════════════════════════╗
║                                                        ║
║       🚀 KINGFLOW WHATSAPP SERVICE INICIADO 🚀        ║
║                                                        ║
╚════════════════════════════════════════════════════════╝

📍 Servidor corriendo en: http://localhost:3001
⏳ Conectando a WhatsApp...

╔════════════════════════════════════════════════════════╗
║                                                        ║
║     📱 ESCANEA ESTE QR CON TU WHATSAPP 📱            ║
║                                                        ║
╚════════════════════════════════════════════════════════╝

█▀▀▀▀▀█ ▄▀▄█▀▀▄▄ ▄█▀ █▀▀▀▀▀█
█ ███ █ █ ▄ █▄▀▀█▀▄█ █ ███ █
█ ▀▀▀ █ ▄██▀ ▄▄ ▀▀▄█ █ ▀▀▀ █
...

✅ Después de escanear, la sesión quedará guardada
⏱️  No necesitarás escanear de nuevo la próxima vez
```

### Escanear QR:

1. Abre WhatsApp en tu teléfono
2. Ve a **Menú (⋮) > Dispositivos vinculados**
3. Toca **"Vincular un dispositivo"**
4. Escanea el QR que aparece en la consola

**¡Listo!** Una vez conectado:

```
╔════════════════════════════════════════════════════════╗
║                                                        ║
║          ✅ WHATSAPP CONECTADO EXITOSAMENTE ✅        ║
║                                                        ║
╚════════════════════════════════════════════════════════╝
```

---

## 📡 API Endpoints

### 1. Health Check

```http
GET http://localhost:3001/health
```

**Respuesta:**
```json
{
  "status": "ok",
  "connected": true,
  "waiting_qr": false,
  "timestamp": "2024-05-30T18:30:00.000Z"
}
```

---

### 2. Enviar Mensaje

```http
POST http://localhost:3001/send
Content-Type: application/json
Authorization: Bearer <WHATSAPP_API_TOKEN>

{
  "phone": "+18095555555",
  "message": "✅ Tu cita está confirmada para mañana 2:00 PM"
}
```

**Respuesta exitosa:**
```json
{
  "success": true,
  "message": "Message sent successfully",
  "messageId": "3EB0A...",
  "timestamp": "2024-05-30T18:30:00.000Z"
}
```

**Respuesta error (no conectado):**
```json
{
  "success": false,
  "error": "WhatsApp not connected",
  "waiting_qr": true
}
```

---

### 3. Enviar Mensaje con Formato

```http
POST http://localhost:3001/send-formatted
Content-Type: application/json

{
  "phone": "+18095555555",
  "message": "👑 *Elite Barber Shop*\n\n✅ *Cita Confirmada*\n\n📅 Fecha: _30 de Mayo_\n⏰ Hora: *2:00 PM*"
}
```

**Formato soportado:**
- `*texto*` - Negrita
- `_texto_` - Cursiva
- `~texto~` - Tachado
- ``` ```texto``` ``` - Monoespaciado

---

### 4. Enviar Imagen

```http
POST http://localhost:3001/send-image
Content-Type: application/json

{
  "phone": "+18095555555",
  "imageUrl": "https://example.com/promo.jpg",
  "caption": "🎉 Promoción especial del mes"
}
```

---

### 5. Verificar si un Número tiene WhatsApp

```http
GET http://localhost:3001/check/18095555555
Authorization: Bearer <WHATSAPP_API_TOKEN>
```

**Respuesta:**
```json
{
  "success": true,
  "exists": true,
  "jid": "18095555555@s.whatsapp.net"
}
```

---

### 6. Info de Conexión

```http
GET http://localhost:3001/info
Authorization: Bearer <WHATSAPP_API_TOKEN>
```

**Respuesta:**
```json
{
  "connected": true,
  "user": {
    "id": "18095555555:12@s.whatsapp.net",
    "name": "Elite Barber Shop"
  },
  "platform": "baileys",
  "version": "1.0.0"
}
```

---

### 7. Desconectar (Mantenimiento)

```http
POST http://localhost:3001/disconnect
Authorization: Bearer <WHATSAPP_API_TOKEN>
```

---

## 🔗 Integración con FastAPI

El backend usa `WHATSAPP_API_URL` y envía el secreto configurado en `WHATSAPP_API_TOKEN`. Los flujos activos intentan enviar WhatsApp al crear, cancelar o reprogramar una reserva pública y al registrar un pago. La entrega es de mejor esfuerzo: una caída del servicio no revierte la cita ni el pago y actualmente no hay cola ni reintentos. Los métodos SMTP de `notification_service.py` no se llaman automáticamente desde esos flujos.

---

## 🔄 Reconexión Automática

Si el servicio se desconecta (internet, reinicio, etc.), **se reconecta automáticamente** sin necesidad de escanear QR de nuevo.

**Logs:**
```
⚠️  Conexión cerrada: Connection Closed
🔄 Reconectando automáticamente en 5 segundos...

✅ WHATSAPP CONECTADO EXITOSAMENTE
```

---

## 📁 Archivos Importantes

```
whatsapp-service/
├── server.js              # Servidor principal
├── package.json           # Dependencias
├── auth_info_baileys/     # Sesión guardada (NO BORRAR)
│   ├── creds.json        # Credenciales
│   └── ...               # Otros archivos de sesión
└── README.md             # Este archivo
```

⚠️ **IMPORTANTE:** No borres la carpeta `auth_info_baileys`. Contiene tu sesión de WhatsApp. Si la borras, tendrás que escanear el QR de nuevo.

---

## 🚀 Iniciar en Producción

### Opción 1: PM2 (Recomendado)

```bash
# Instalar PM2
npm install -g pm2

# Iniciar servicio
cd whatsapp-service
pm2 start server.js --name whatsapp-service

# Ver logs
pm2 logs whatsapp-service

# Ver estado
pm2 status

# Reiniciar
pm2 restart whatsapp-service

# Detener
pm2 stop whatsapp-service

# Iniciar automáticamente al boot
pm2 startup
pm2 save
```

### Opción 2: Nodemon (Desarrollo)

```bash
npm install -g nodemon
nodemon server.js
```

### Opción 3: Windows Service

Usa `node-windows` para ejecutarlo como servicio de Windows.

---

## 🐛 Troubleshooting

### ❌ Error: "WhatsApp not connected"

**Solución:**
1. Verificar que el servicio esté corriendo: `http://localhost:3001/health`
2. Si `waiting_qr: true`, escanear el QR de nuevo
3. Reiniciar servicio: `npm start`

---

### ❌ Error: "Module not found"

**Solución:**
```bash
cd whatsapp-service
rm -rf node_modules
npm install
```

---

### ❌ QR no aparece

**Solución:**
1. Borrar carpeta `auth_info_baileys`
2. Reiniciar servicio
3. Escanear QR nuevo

---

### ❌ Mensajes no llegan

**Solución:**
1. Verificar formato de teléfono: `+18095555555`
2. Verificar que el número tenga WhatsApp: `GET /check/:phone`
3. Ver logs del servidor Node.js
4. Verificar conexión a internet

---

### ❌ Se desconecta constantemente

**Posibles causas:**
1. Misma sesión abierta en otro dispositivo
2. WhatsApp bloqueó el número (spam)
3. Problema de internet

**Solución:**
- Cerrar WhatsApp Web en otros navegadores
- Esperar 24 horas si fue bloqueado
- Verificar conexión estable

---

## 🔒 Seguridad

### Buenas Prácticas:

1. ✅ **No compartir `auth_info_baileys/`** - Contiene tu sesión
2. ✅ **Usar HTTPS en producción** - No HTTP
3. ✅ **Validar números** antes de enviar
4. ✅ **Rate limiting** - Limitar mensajes por minuto
5. ✅ **Logs** - Mantener registro de mensajes enviados

### Rate Limiting Recomendado:

```javascript
// Agregar en server.js
const rateLimit = require('express-rate-limit');

const limiter = rateLimit({
  windowMs: 1 * 60 * 1000, // 1 minuto
  max: 30 // máximo 30 mensajes por minuto
});

app.use('/send', limiter);
```

---

## 📊 Monitoreo

### Ver logs en tiempo real:

```bash
# PM2
pm2 logs whatsapp-service

# Directamente
npm start
```

### Métricas importantes:

- Total de mensajes enviados
- Tasa de éxito/fallo
- Tiempo de respuesta
- Estado de conexión

---

## 🔄 Actualizar Baileys

```bash
cd whatsapp-service
npm update @whiskeysockets/baileys
```

---

## 💡 Tips Avanzados

### 1. Enviar a Múltiples Números

```javascript
app.post('/send-bulk', async (req, res) => {
    const { phones, message } = req.body;

    const results = await Promise.all(
        phones.map(phone => 
            sock.sendMessage(formatPhoneNumber(phone), { text: message })
        )
    );

    res.json({ success: true, sent: results.length });
});
```

### 2. Programar Mensajes

Usar `node-cron`:

```javascript
const cron = require('node-cron');

// Enviar recordatorios diarios a las 9 AM
cron.schedule('0 9 * * *', async () => {
    // Llamar a FastAPI para obtener citas del día
    // Enviar recordatorios
});
```

### 3. Webhook para Respuestas

```javascript
sock.ev.on('messages.upsert', async ({ messages }) => {
    // Procesar respuestas de clientes
    // Enviar a FastAPI para actualizar estado
});
```

---

## 📚 Recursos

- **Baileys GitHub:** https://github.com/WhiskeySockets/Baileys
- **Documentación:** https://whiskeysockets.github.io/Baileys/
- **WhatsApp Business API:** https://business.whatsapp.com/

---

## ⚖️ Términos de Uso

⚠️ **Importante:** Este servicio es para uso legítimo. **NO usar para:**
- Spam
- Mensajes no solicitados
- Violación de términos de WhatsApp

WhatsApp puede **banear tu número** si detecta abuso.

**Uso responsable:**
- Solo enviar a clientes que dieron su consentimiento
- Respetar horarios (no enviar de noche)
- Dar opción de opt-out
- Máximo 2-3 mensajes por cliente al día

---

## ✅ Checklist de Producción

- [ ] Servicio corriendo 24/7 (PM2)
- [ ] Backup de `auth_info_baileys/`
- [ ] Monitoreo de logs
- [ ] Rate limiting configurado
- [ ] HTTPS en producción
- [ ] Validación de números
- [ ] Manejo de errores
- [ ] Sistema de reintentos
- [ ] Alertas de desconexión

---

**Versión:** 1.0.0  
**Última actualización:** 2024-05-30  
**Mantenido por:** KingFlow Barber Team
