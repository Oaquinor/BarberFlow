# WhatsApp en KingFlow Barber

Este documento reemplaza recomendaciones históricas de proveedores y librerías. El gateway que existe en el repositorio es `whatsapp-service/`, un proceso Node.js basado en Baileys. No usa `whatsapp-web.js`, CallMeBot ni una API oficial de Meta/Twilio. No se declara gratuito, ilimitado ni equivalente a una integración oficial; valida los términos vigentes y los requisitos de la cuenta antes de usarlo.

## Implementación actual

- FastAPI guarda avisos en `notification_deliveries` dentro de transacciones MySQL.
- `backend/scripts/notification_worker.py` procesa la bandeja y programa recordatorios. Una falla externa queda registrada y se reintenta; no confirma que WhatsApp haya entregado el mensaje.
- `whatsapp-service/` mantiene una sesión vinculada mediante QR y expone un gateway HTTP protegido con `WHATSAPP_API_TOKEN`.
- Los cargos/avisos al cliente usan el teléfono disponible. La entrega real requiere un gateway activo, sesión válida y configuración de producción.

## Configuración

Consulta [`whatsapp-service/README.md`](../whatsapp-service/README.md) para rutas, seguridad, despliegue y vinculación QR, y [`NOTIFICATIONS_SYSTEM.md`](NOTIFICATIONS_SYSTEM.md) para la bandeja MySQL y el worker.

Configura el mismo secreto aleatorio en `WHATSAPP_API_TOKEN` para el proceso Node y el backend. Configura `WHATSAPP_API_URL` en el backend para que apunte al endpoint `/send` alcanzable desde FastAPI. En Docker Compose de producción la URL interna ya apunta al servicio `whatsapp`; protege el puerto y el volumen de sesión.

No expongas el gateway a Internet sin controles de red y TLS en la capa de entrada. `/health` es público y solo informa el estado general; las demás operaciones requieren Bearer token.

## Alcance de validación

Las pruebas automatizadas verifican el contrato HTTP, autenticación, validación de solicitudes y procesamiento de cola, pero no prueban entrega real a destinatarios. Esa validación requiere credenciales/configuración externa y una sesión autorizada.
