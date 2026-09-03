# 📧 Sistema de Notificaciones - KingFlow Barber

**Sistema completo de notificaciones automáticas para clientes**

---

## 🎯 **Funcionalidades Implementadas**

### ✅ **Sí, la app ESTÁ CAPACITADA para enviar notificaciones a clientes**

El sistema incluye:

1. **📧 Email (SMTP)**
   - Confirmación de cita
   - Recordatorio 24h antes
   - Notificación de cancelación
   - Agradecimiento post-servicio

2. **📱 SMS (Twilio)**
   - Recordatorios cortos
   - Confirmaciones rápidas

3. **💬 WhatsApp (Twilio WhatsApp API)**
   - Mensajes formateados
   - Confirmaciones con emojis
   - Enlaces directos

---

## 📧 **Notificaciones por Email**

### **1. Confirmación de Cita** (Automática al agendar)

**Cuándo se envía:** Inmediatamente después de crear la cita

**Contenido:**
```
Asunto: ✅ Cita Confirmada - [Nombre Barbería]

Hola [Nombre Cliente],

Tu cita ha sido confirmada exitosamente. ¡Esperamos verte pronto!

📅 Detalles de tu Cita:
   Fecha: Viernes, 30 de Mayo de 2024
   Hora: 02:00 PM
   Barbero: Carlos Martínez
   Servicio: Corte + Barba Premium
   Duración estimada: 30 minutos

📍 Ubicación:
   Elite Barber Shop
   Calle Principal #123
   📞 809-555-5555

⏰ Importante: Por favor llega 5-10 minutos antes de tu cita.

Si necesitas cancelar o reprogramar, contáctanos lo antes posible.
```

**Diseño:** HTML con gradientes morados, iconos y botones

---

### **2. Recordatorio 24h Antes** (Automático)

**Cuándo se envía:** 24 horas antes de la cita programada

**Contenido:**
```
Asunto: ⏰ Recordatorio de Cita - [Nombre Barbería]

Hola [Nombre Cliente],

Tu cita es MAÑANA

02:00 PM
Viernes, 30 de Mayo

Barbero: Carlos Martínez
Servicio: Corte + Barba Premium
Lugar: Elite Barber Shop
Calle Principal #123

¡Te esperamos! 👋
```

**Diseño:** HTML con fondo amarillo/naranja de alerta

---

### **3. Notificación de Cancelación**

**Cuándo se envía:** Cuando se cancela una cita

**Contenido:**
```
Asunto: ❌ Cita Cancelada - [Nombre Barbería]

Hola [Nombre Cliente],

Tu cita del 02:00 PM, 30 de Mayo ha sido cancelada.

Motivo: [Razón especificada]

Si deseas reagendar, contáctanos o reserva una nueva cita en nuestra app.

¡Esperamos verte pronto!
```

---

### **4. Agradecimiento Post-Servicio**

**Cuándo se envía:** Después de completar el servicio

**Contenido:**
```
Asunto: ¡Gracias por tu visita! - [Nombre Barbería]

Hola [Nombre Cliente],

Esperamos que hayas disfrutado tu servicio con Carlos Martínez.

Tu opinión es muy importante para nosotros. Si tienes un momento, 
nos encantaría que nos dejaras una reseña.

¡Esperamos verte pronto para tu próxima cita!
```

---

## 📱 **Notificaciones por SMS**

### **Recordatorio SMS** (24h antes)

**Contenido:**
```
⏰ Recordatorio: Tu cita en Elite Barber Shop es MAÑANA a las 02:00 PM. ¡Te esperamos!
```

**Proveedor:** Twilio SMS API  
**Límite de caracteres:** 160 (SMS estándar)

---

## 💬 **Notificaciones por WhatsApp**

### **Confirmación WhatsApp** (Al agendar)

**Contenido:**
```
👑 *Elite Barber Shop*

✅ *Cita Confirmada*

Hola Juan Pérez,

📅 *Fecha y Hora:* 02:00 PM, 30 de Mayo
✂️ *Servicio:* Corte + Barba Premium
👤 *Barbero:* Carlos Martínez
📍 *Dirección:* Calle Principal #123

⏰ Por favor llega 5-10 minutos antes.

¡Te esperamos! 👋
```

**Proveedor:** Twilio WhatsApp Business API  
**Ventajas:**
- Formato con negritas y emojis
- Mayor tasa de apertura que email
- Confirmación de lectura

---

## 🔧 **Configuración del Sistema**

### **Paso 1: Configurar Variables de Entorno**

Crea/edita el archivo `backend/.env`:

```env
# ==================== EMAIL CONFIGURATION ====================
SMTP_HOST=smtp.gmail.com
SMTP_PORT=587
SMTP_USER=tu-email@gmail.com
SMTP_PASSWORD=tu-password-de-app
SMTP_FROM_EMAIL=noreply@kingflowbarber.com
SMTP_TLS=True

# Enable email notifications
SEND_CONFIRMATION_EMAILS=True
SEND_REMINDER_EMAILS=True
SEND_CANCELLATION_EMAILS=True
SEND_COMPLETION_EMAILS=True

# ==================== TWILIO SMS ====================
TWILIO_ACCOUNT_SID=tu-account-sid
TWILIO_AUTH_TOKEN=tu-auth-token
TWILIO_PHONE_NUMBER=+1234567890
SEND_SMS_NOTIFICATIONS=True

# ==================== TWILIO WHATSAPP ====================
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886
SEND_WHATSAPP_NOTIFICATIONS=True
```

---

### **Paso 2: Configurar Gmail (Opción más fácil)**

1. **Ir a tu cuenta de Gmail**
2. **Activar 2FA (autenticación de dos factores)**
3. **Generar "Contraseña de aplicación":**
   - Ve a: https://myaccount.google.com/apppasswords
   - Crea una contraseña para "Mail"
   - Copia la contraseña de 16 caracteres

4. **Actualizar `.env`:**
```env
SMTP_USER=tu-email@gmail.com
SMTP_PASSWORD=xxxx xxxx xxxx xxxx  # La contraseña de app
```

---

### **Paso 3: Configurar Twilio (Para SMS/WhatsApp)**

1. **Crear cuenta en Twilio:** https://www.twilio.com/
2. **Obtener credenciales:**
   - Account SID
   - Auth Token
   - Phone Number (comprar uno)

3. **Para WhatsApp:**
   - Solicitar acceso a WhatsApp Business API
   - Configurar plantillas de mensajes
   - Obtener número de WhatsApp

4. **Actualizar `.env` con credenciales**

---

## 🚀 **Uso del Sistema**

### **1. Al Crear una Cita (Automático)**

```python
# El endpoint ya tiene notificaciones integradas
POST /api/v1/appointments/

Body:
{
  "barbershop_id": 1,
  "barber_id": 2,
  "scheduled_time": "2024-05-30T14:00:00",
  "service_type": "haircut_beard",
  "estimated_duration": 30,
  "send_confirmation": true  # ← Envía notificación automática
}

# Al crear la cita:
# 1. Se guarda en la base de datos
# 2. Se envía email de confirmación al cliente
# 3. Si tiene teléfono, se envía WhatsApp
```

---

### **2. Recordatorios Automáticos (Cron Job)**

**Configurar tarea programada:**

```bash
# En Linux/Mac (crontab)
# Ejecutar diariamente a las 9 AM
0 9 * * * cd /path/to/backend && python -m scripts.send_reminders

# En Windows (Task Scheduler)
# Crear tarea que ejecute:
cd C:\path\to\backend
python -m scripts.send_reminders
```

**Script de recordatorios:**
```python
# backend/scripts/send_reminders.py
import requests

# Llamar al endpoint de recordatorios
response = requests.get("http://localhost:8000/api/v1/appointments/upcoming/reminders")
print(response.json())
```

---

### **3. Notificación Manual (Opcional)**

```python
# Desde código Python
from app.services.notification_service import NotificationService

notification_service = NotificationService(db)

# Enviar confirmación
notification_service.send_appointment_confirmation(appointment)

# Enviar recordatorio
notification_service.send_appointment_reminder(appointment)

# Enviar cancelación
notification_service.send_appointment_cancellation(appointment, reason="Cliente canceló")

# Enviar agradecimiento
notification_service.send_appointment_completed(appointment)

# WhatsApp
notification_service.send_whatsapp_confirmation(appointment)

# SMS
notification_service.send_sms_reminder(appointment)
```

---

## 📊 **Flujo Completo de Notificaciones**

```
┌─────────────────────────────────────────────────────────────┐
│                    CICLO DE VIDA DE UNA CITA                │
└─────────────────────────────────────────────────────────────┘

1. 📅 CLIENTE AGENDA CITA
   ↓
   ✉️ Email de Confirmación (inmediato)
   💬 WhatsApp de Confirmación (inmediato)

2. ⏰ 24 HORAS ANTES
   ↓
   ✉️ Email de Recordatorio
   📱 SMS de Recordatorio

3. 🔥 DÍA DE LA CITA
   ↓
   Cliente llega → Barbero inicia servicio

4. ✅ SERVICIO COMPLETADO
   ↓
   ✉️ Email de Agradecimiento

5. ❌ SI SE CANCELA (en cualquier momento)
   ↓
   ✉️ Email de Cancelación
```

---

## 🎨 **Personalización de Templates**

Los templates están en: `backend/app/services/notification_service.py`

### **Modificar Template de Confirmación:**

```python
def _get_confirmation_email_template(self, ...):
    return f"""
    <!DOCTYPE html>
    <html>
    <head>
        <style>
            /* Agrega tus estilos aquí */
            .header {{ background: #TU_COLOR; }}
        </style>
    </head>
    <body>
        <!-- Tu HTML personalizado -->
    </body>
    </html>
    """
```

---

## 📈 **Métricas de Notificaciones**

El sistema registra:
- ✅ Notificaciones enviadas exitosamente
- ❌ Notificaciones fallidas
- 📊 Tasa de apertura (si usas proveedores con tracking)
- 📧 Emails rebotados

---

## 🔒 **Seguridad y Privacidad**

- ✅ Emails enviados por SMTP seguro (TLS)
- ✅ Contraseñas almacenadas en `.env` (no en código)
- ✅ Solo se envían notificaciones a clientes confirmados
- ✅ Opción de opt-out disponible
- ✅ Datos encriptados en tránsito

---

## 💰 **Costos**

### **Email (SMTP)**
- **Gmail:** GRATIS (hasta 500 emails/día)
- **SendGrid:** $15/mes (40,000 emails)
- **Mailgun:** $35/mes (50,000 emails)

### **SMS**
- **Twilio:** $0.0075 por SMS
  - 1,000 SMS = $7.50
  - 10,000 SMS = $75.00

### **WhatsApp**
- **Twilio:** $0.005 por mensaje
  - 1,000 mensajes = $5.00
  - 10,000 mensajes = $50.00

**Recomendación:** Comenzar con Gmail gratis para emails, agregar SMS/WhatsApp después si es necesario.

---

## 🐛 **Troubleshooting**

### **Email no llega:**
1. Verificar SMTP_USER y SMTP_PASSWORD correctos
2. Revisar carpeta de spam
3. Verificar que Gmail "App Password" esté activo
4. Revisar logs: `python -m app.main` y buscar errores

### **SMS no llega:**
1. Verificar TWILIO_ACCOUNT_SID y TWILIO_AUTH_TOKEN
2. Verificar saldo en Twilio
3. Verificar formato de teléfono: +1234567890

### **WhatsApp no llega:**
1. Verificar que plantillas estén aprobadas en Twilio
2. Verificar formato de número
3. Cliente debe haber iniciado conversación primero

---

## 📚 **Endpoints del Sistema**

### **Crear Cita con Notificación**
```http
POST /api/v1/appointments/
Content-Type: application/json

{
  "barbershop_id": 1,
  "barber_id": 2,
  "scheduled_time": "2024-05-30T14:00:00",
  "service_type": "haircut",
  "send_confirmation": true
}
```

### **Enviar Recordatorios Masivos**
```http
GET /api/v1/appointments/upcoming/reminders
```

### **Cancelar con Notificación**
```http
POST /api/v1/appointments/{id}/cancel
Content-Type: application/json

{
  "reason": "Cliente solicitó cancelación",
  "send_notification": true
}
```

---

## ✅ **Checklist de Implementación**

- [x] ✅ Servicio de notificaciones creado (`notification_service.py`)
- [x] ✅ Templates de email HTML diseñados
- [x] ✅ Templates de SMS/WhatsApp
- [x] ✅ Endpoints de appointments con notificaciones
- [x] ✅ Configuración en `config.py`
- [ ] ⚠️ Configurar Gmail SMTP (requiere credenciales)
- [ ] ⚠️ Configurar Twilio (opcional, requiere cuenta)
- [ ] ⚠️ Crear tarea programada para recordatorios
- [ ] ⚠️ Probar en producción

---

## 🎯 **Siguiente Paso: Activar Notificaciones**

Para activar las notificaciones, solo necesitas:

1. **Configurar Gmail SMTP** (5 minutos)
2. **Crear archivo `.env`** con credenciales
3. **Reiniciar servidor**

¡Y listo! Las notificaciones empezarán a enviarse automáticamente. 🚀

---

**Documentación creada:** 2024-05-30  
**Estado:** Sistema completo implementado, pendiente configuración de credenciales
