# Inicio rápido de WhatsApp

WhatsApp es opcional. KingFlow usa el gateway Node.js en [`whatsapp-service/README.md`](whatsapp-service/README.md), basado en Baileys. No utiliza una integración oficial de Meta ni garantiza un servicio gratuito o ilimitado.

## Requisitos

- MySQL: la API y la cola de notificaciones usan MySQL; SQLite no está soportado.
- Node.js compatible con el proyecto (consulta `whatsapp-service/package.json`).
- Un `WHATSAPP_API_TOKEN` largo y aleatorio, configurado tanto en el backend como en el gateway.
- Para producción, almacenamiento persistente y protegido para la sesión vinculada, además de red privada entre FastAPI y el gateway.

## Desarrollo local

1. Configura MySQL y las variables del backend siguiendo [la guía de instalación](README.md) y `.env.example`.
2. En una terminal, inicia el gateway:

   ```powershell
   cd whatsapp-service
   npm ci
   $env:WHATSAPP_API_TOKEN = "<mismo-secreto-largo-aleatorio-que-el-backend>"
   npm start
   ```

3. En otra terminal, inicia FastAPI con su entorno y `.env` configurados para usar el mismo `WHATSAPP_API_TOKEN`; `WHATSAPP_API_URL` debe apuntar a `http://127.0.0.1:3001/send`.
4. En la primera vinculación, escanea el QR desde **WhatsApp → Dispositivos vinculados**. Protege el directorio de sesión; no lo subas al repositorio ni lo compartas.
5. Inicia el worker desde `backend` con la configuración MySQL del backend:

   ```powershell
   python -m scripts.notification_worker
   ```

La API del gateway incluye `GET /health` para estado general y operaciones protegidas como `POST /send`; consulta el README del servicio para el contrato completo. No pruebes `/send` sin `Authorization: Bearer <WHATSAPP_API_TOKEN>`.

## Qué significa el estado

La API puede aceptar la cita aunque una entrega externa falle. Los mensajes quedan en la bandeja MySQL y el worker aplica reintentos, con entrega potencialmente repetida en ciertos fallos de red. El estado de cola no equivale a confirmación de lectura o entrega por WhatsApp. Las pruebas automatizadas no sustituyen una prueba real con una sesión autorizada.
