# Arquitectura de KingFlow Barber

## Estado implementado

KingFlow Barber es una aplicación web SaaS con frontend estático/PWA y API FastAPI. La API usa SQLAlchemy ORM síncrono con PyMySQL y **MySQL 8 como única base de datos soportada**. No se admite SQLite. Las migraciones del esquema se administran con Alembic.

Esta guía describe el código actualmente conectado. Los ejemplos y módulos no montados no representan funciones disponibles en producción.

## Componentes

- `frontend/`: páginas HTML, CSS y JavaScript del panel, portal público y PWA. No es una aplicación React.
- `backend/app/main.py`: configura FastAPI, seguridad HTTP, CORS, router `/api/v1`, health check dependiente de MySQL y servicio de archivos estáticos.
- `backend/app/api/v1/__init__.py`: punto de registro de los routers activos: onboarding, plataforma, catálogo de servicios, logros, rendimiento, analítica, ajustes de administración, billing y recuperación de contraseña.
- `backend/app/api/v1/endpoints/platform.py`: concentra los flujos de autenticación, registro SaaS, portal público, reservas, agenda, pagos/caja y administración que documenta `docs/API_REFERENCE.md`.
- `backend/app/api/v1/endpoints/onboarding.py` y `backend/app/services/onboarding_service.py`: configuración inicial y ajustes del tenant autenticado.
- `backend/app/models/` y `backend/app/schemas/`: entidades ORM y validación/serialización de solicitudes y respuestas.
- `backend/app/services/`: lógica de servicios conectada a endpoints, notificaciones, auditoría, rendimiento y pronóstico.
- `backend/app/core/database/session.py`: valida `DATABASE_URL` con el prefijo `mysql+pymysql://`, construye el engine y sesiones síncronas.
- `backend/alembic/`: cambios versionados de esquema MySQL.
- `backend/scripts/notification_worker.py`: procesa entregas de notificación persistidas en MySQL.

## Base de datos y transacciones

Configura `DATABASE_URL` como `mysql+pymysql://usuario:contraseña@host:3306/base`. El backend rechaza otros drivers. Usa MySQL 8 tanto en desarrollo como en CI y producción. No crear tablas con `Base.metadata.create_all()` como sustituto de migraciones en despliegues; aplica `alembic upgrade head`.

Los endpoints que acceden a datos usan `sqlalchemy.orm.Session` síncrona. `get_db()` abre la sesión, confirma al finalizar la solicitud, revierte ante excepción y la cierra. Las operaciones que requieren límites transaccionales específicos hacen su propio commit/rollback según el flujo.

Los límites y consultas concurrentes deben respetar las garantías de MySQL. En especial, para insertar o actualizar cuotas/contadores por clave única se usa la sintaxis atómica de MySQL y las filas se bloquean cuando el flujo lo requiere. Las pruebas de integración con SQLite no son equivalentes y no deben usarse para validar estas garantías.

## Rutas y flujos

Los routers se montan bajo `/api/v1`; la referencia de rutas y permisos está en `docs/API_REFERENCE.md`. El cliente público reserva sin crear una cuenta. El seguimiento, cancelación y reprogramación de la reserva requieren un token privado aleatorio cuyo hash se conserva en la base de datos.

Los usuarios autenticados derivan el tenant de su identidad. Las operaciones de administración general que permiten elegir barbería lo hacen explícitamente y deben comprobar el rol autorizado. Las consultas y mutaciones del negocio restringen sus registros al tenant correspondiente.

Los cobros se guardan como pagos reales y alimentan conciliación, rendimiento y reportes. El registro del pago y el cambio de estado de la cita se realizan dentro de una sola transacción. El sistema no debe presentar reservas pendientes como ingresos recibidos.

## Autenticación y controles

La API emite JWT de acceso y refresh; las sesiones refresh se guardan y revocan en MySQL. La rotación y la versión de autenticación invalidan sesiones anteriores al cambiar o recuperar la contraseña. Las dependencias de API validan identidad y rol; la pertenencia al tenant se verifica en las consultas y operaciones.

La protección de intentos de login y solicitudes de soporte usa límites persistidos en MySQL con actualizaciones atómicas. Las credenciales de producción y URLs se suministran por variables de entorno. En producción, `main.py` exige clave secreta robusta, HTTPS para los orígenes configurados y URL de frontend HTTPS.

## Notificaciones y tareas de fondo

Las operaciones relevantes escriben notificaciones internas y entregas email/WhatsApp en una outbox MySQL. El worker procesa entregas con idempotencia, leases y reintentos. La disponibilidad externa depende de la configuración del proveedor. La bandeja del frontend consulta periódicamente; no existe una ruta WebSocket activa. `backend/app/websocket/manager.py` es un prototipo desconectado.

## Analítica

El pronóstico de demanda usa el historial de citas completadas y las reservas conocidas; es una estimación estadística explicable, no aprendizaje automático. Los reportes financieros usan pagos almacenados y la zona horaria del tenant. No hay Redis, almacenamiento analítico separado ni cola Celery configurados.

## Módulos desconectados

`backend/app/api/v1/appointments.py` no está incluido en el router v1. Sus handlers dependen de `AsyncSession`, mientras que el backend configurado entrega sesiones síncronas. Por tanto, sus endpoints no están disponibles y no deben usarse como referencia del flujo activo. Lo mismo aplica al `AppointmentService` y repositorios async que solo utiliza ese router desconectado. `backend/app/api/v1/service_mode.py` y `ServiceModeService` tampoco están montados; el panel usa `/barber/dashboard`, `/barber/appointments/{appointment_id}/status` y `/barber/appointments/{appointment_id}/payment`, que conservan límites de tenant, trazabilidad y pago obligatorio. No se debe conectar el endpoint antiguo de finalización, que marca la cita completada sin registrar cobro. La fuente vigente de rutas es `docs/API_REFERENCE.md` junto con el registro de routers.

## Guías relacionadas

- `docs/API_REFERENCE.md`: rutas activas, permisos y contratos principales.
- `docs/DATABASE.md`: configuración y operaciones de base de datos.
- `docs/STANDARDS.md`: convenciones de contribución; cualquier ejemplo debe mantenerse alineado con MySQL y los patrones realmente usados.
