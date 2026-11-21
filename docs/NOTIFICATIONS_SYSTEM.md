# Notificaciones de KingFlow Barber

## Entrega durable

Las notificaciones externas se escriben en `notification_deliveries` dentro de la misma transacción MySQL que confirma la operación del negocio. Las claves únicas hacen idempotente la creación de las confirmaciones, cancelaciones, reprogramaciones, turnos presenciales, pagos y recordatorios.

El proceso `notification-worker` revisa la cola cada 30 segundos, reclama filas con bloqueos MySQL `SKIP LOCKED`, recupera trabajos cuyo lease expiró y aplica reintentos con espera incremental hasta ocho intentos. Los estados persistidos son `pending`, `processing`, `sent` y `failed`. La entrega externa es de tipo al menos una vez: una caída justo después de que el proveedor acepte un mensaje y antes de guardar `sent` puede provocar un reintento duplicado. Un fallo del proveedor no revierte una cita o pago.

Los recordatorios de email y WhatsApp se programan al entrar la cita en la ventana de 24 horas. Si la reserva se hace dentro de esa ventana, se encolan inmediatamente. El worker descarta recordatorios de citas canceladas o ya completadas. Los clientes sin correo reciben únicamente el canal para el que haya un dato válido. SMS no está configurado.

## WhatsApp

El servicio Baileys requiere el mismo secreto aleatorio en `WHATSAPP_API_TOKEN` para Node.js, backend y worker. `WHATSAPP_API_URL` apunta a `/send`; dentro de Docker Compose queda en `http://whatsapp:3001/send`. El servicio escucha en `0.0.0.0` dentro de la red privada de Compose. Su sesión se guarda en el volumen `whatsapp_auth` y el primer inicio requiere escanear el QR que muestra `docker compose logs whatsapp`.

Los endpoints de envío y administración de sesión requieren `Authorization: Bearer <WHATSAPP_API_TOKEN>`. `/health` no requiere token e informa estado general de conexión. Si WhatsApp no está conectado, la cola conserva los mensajes y los vuelve a intentar.

## Correo

Configura `SMTP_HOST`, `SMTP_PORT`, `SMTP_USER`, `SMTP_PASSWORD` y `EMAIL_FROM` en el entorno de Docker/backend. El backend admite SMTP con STARTTLS o SSL en el puerto 465. Sin credenciales válidas, los mensajes quedan pendientes, pasan por reintentos y terminan registrados como fallidos.

## Operación

Docker Compose levanta `notification-worker` junto al backend, MySQL y el servicio WhatsApp. Para ejecutar el worker directamente, desde `backend` usa `python -m scripts.notification_worker` con la misma `DATABASE_URL=mysql+pymysql://...` y las variables de proveedor configuradas. La migración `017_notification_delivery_outbox` crea la cola en MySQL.

La entrega real depende de credenciales SMTP válidas y de que la sesión autorizada de WhatsApp permanezca conectada. Las pruebas automatizadas verifican persistencia, idempotencia y manejo de la cola, pero no envían mensajes reales.
