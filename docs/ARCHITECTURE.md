# Arquitectura de KingFlow Barber

## Estado implementado

KingFlow Barber es una aplicación web SaaS con frontend estático/PWA y API FastAPI. La API usa SQLAlchemy ORM síncrono con PyMySQL y **MySQL 8 como única base de datos soportada**. No se admite SQLite. Las migraciones del esquema se administran con Alembic.

Esta guía describe el código actualmente conectado. Los ejemplos y módulos no montados no representan funciones disponibles en producción.

## Componentes

- `frontend/`: páginas HTML, CSS y JavaScript del panel, portal público y PWA. No es una aplicación React.
- `backend/app/main.py`: configura FastAPI, seguridad HTTP, CORS, router `/api/v1`, health check dependiente de MySQL y servicio de archivos estáticos.
- `backend/app/api/v1/__init__.py`: punto de registro de los routers activos: onboarding, plataforma, reservas, notificaciones, administración general, gestión de barbería, catálogo de servicios, logros, rendimiento, analítica, ajustes de administración, billing, recuperación de contraseña, inventario, POS minorista y gastos operativos.
- `backend/app/api/v1/endpoints/platform.py`: implementa autenticación, registro SaaS, soporte y operaciones de agenda, pagos y caja.
- `backend/app/api/v1/endpoints/notifications.py`: expone la bandeja tenant-scoped de notificaciones internas y el marcado de lectura para el usuario autenticado; mantiene los paths y el tag público existentes.
- `backend/app/api/v1/endpoints/booking.py`: implementa el portal público, reserva/seguimiento/cambios de citas, disponibilidad, turnos del barbero y ausencias; conserva los paths y tags de API.
- `backend/app/api/v1/endpoints/booking_waitlist.py` y `backend/app/services/waitlist_offer_service.py`: registran solicitudes públicas no vinculantes, calculan coincidencias y emiten ofertas de un solo uso. El worker busca turnos libres compatibles y encola ofertas FIFO con vencimiento; la aceptación revalida y confirma la cita/turno transaccionalmente en MySQL. Entregas WhatsApp usan el outbox durable existente.
- `backend/app/models/barber_live_state.py` guarda el estado operacional del profesional y su hora de regreso prevista. La API calcula las proyecciones de espera usando agenda, llegada y ese horario; los tiempos siguen siendo aproximados y la actualización de Live Chair es por consulta periódica.
- `backend/app/api/v1/inventory.py` y `backend/app/api/v1/retail_sales.py`: administran catálogo e historial append-only; el POS de propietario vende sin cita, descuenta stock y registra una venta idempotente en la misma transacción MySQL.
- `backend/app/api/v1/expenses.py`: registra y consulta gastos del propietario dentro de su tenant. Las entradas son idempotentes, auditadas y no se editan ni borran desde la API; el efectivo pagado se integra con el cierre y los reportes.
- `backend/app/api/v1/endpoints/admin.py`: implementa soporte de plataforma, tenants, afiliados, suscripciones, usuarios y auditoría. Comparte los helpers de autenticación y auditoría del módulo `platform.py`; ambos routers conservan el tag público `platform`.
- `backend/app/api/v1/endpoints/owner.py`: implementa gestión de barberos, comisiones y clientes para owners y barberos. Reutiliza los controles compartidos de tenant, suscripción y auditoría; mantiene los paths y el tag API existentes.
- `backend/app/api/v1/endpoints/common.py`: centraliza los helpers de autenticación, autorización de tenant, suscripción, zona horaria y auditoría compartidos por los routers activos.
- `backend/app/api/v1/endpoints/onboarding.py` y `backend/app/services/onboarding_service.py`: configuración inicial y ajustes del tenant autenticado.
- `backend/app/models/` y `backend/app/schemas/`: entidades ORM y validación/serialización de solicitudes y respuestas.
- `backend/app/models/barber_live_state.py` y `043_barber_live_state`: estado operacional explícito disponible/descanso en MySQL; atención, retraso y próximo turno siguen derivándose de citas persistidas.
- `backend/app/services/`: lógica de servicios conectada a endpoints, notificaciones, auditoría, rendimiento y pronóstico.
- `backend/app/core/database/session.py`: valida `DATABASE_URL` con el prefijo `mysql+pymysql://`, construye el engine y sesiones síncronas.
- `backend/alembic/`: cambios versionados de esquema MySQL.
- `backend/scripts/notification_worker.py`: procesa entregas de notificación persistidas en MySQL.

## Base de datos y transacciones

Configura `DATABASE_URL` como `mysql+pymysql://usuario:contraseña@host:3306/base`. El backend rechaza otros drivers. Usa MySQL 8 tanto en desarrollo como en CI y producción. No crear tablas con `Base.metadata.create_all()` como sustituto de migraciones en despliegues; aplica `alembic upgrade head`.

Los endpoints que acceden a datos usan `sqlalchemy.orm.Session` síncrona. `get_db()` abre la sesión, confirma al finalizar la solicitud, revierte ante excepción y la cierra. Las operaciones que requieren límites transaccionales específicos hacen su propio commit/rollback según el flujo.

Los límites y consultas concurrentes deben respetar las garantías de MySQL. En especial, para insertar o actualizar cuotas/contadores por clave única se usa la sintaxis atómica de MySQL y las filas se bloquean cuando el flujo lo requiere. La suite de integración exige una base de pruebas MySQL dedicada; el proyecto no incluye una ruta de pruebas con SQLite.

## Rutas y flujos

Los routers se montan bajo `/api/v1`; la referencia de rutas y permisos está en `docs/API_REFERENCE.md`. El cliente público reserva sin crear una cuenta. El seguimiento, cancelación y reprogramación de la reserva requieren un token privado aleatorio cuyo hash se conserva en la base de datos.

Las preferencias del cliente y las respuestas a preguntas configuradas por el negocio se validan frente al cuestionario público vigente y se persisten como JSON en `appointments.booking_answers`. Solo se incluyen en las respuestas de agenda autorizadas por rol y tenant; el frontend las inserta en DOM mediante escape HTML. `client_notes` permanece separado para notas libres heredadas.

Los usuarios autenticados derivan el tenant de su identidad. Las operaciones de administración general que permiten elegir barbería lo hacen explícitamente y deben comprobar el rol autorizado. Las consultas y mutaciones del negocio restringen sus registros al tenant correspondiente. La ruta compartida de reprogramación acepta un token privado para el flujo público o una sesión cliente verificada junto con la cita CRM vinculada; el ID de cita no funciona como credencial.

Los cobros de servicios se guardan junto al cambio de estado de la cita. Las ventas de productos usan su entidad independiente, sin crear citas ficticias, y enlazan venta, snapshots, movimiento de inventario y auditoría dentro de la misma transacción. Los gastos pagados se almacenan como movimientos financieros append-only. La conciliación descuenta gastos en efectivo y comisiones pagadas de las entradas en efectivo; al cerrar suma el fondo inicial declarado. El reporte muestra cobros, egresos y cobros menos gastos registrados, que no representa utilidad neta.

## Autenticación y controles

Las cuentas owner y superadmin pueden habilitar TOTP opcional desde el control de seguridad de cuenta. Login valida contraseña y, si MFA está activo, exige un segundo envío con TOTP/código de recuperación antes de crear la sesión refresh. El secreto provisional y activo se cifra con AES-GCM; los códigos de recuperación se almacenan como SHA-256 y son de un uso. La clave estable `MFA_ENCRYPTION_KEY` se configura por entorno.

La API emite JWT de acceso y refresh; las sesiones refresh se guardan y revocan en MySQL. La rotación y la versión de autenticación invalidan sesiones anteriores al cambiar o recuperar la contraseña. Las dependencias de API validan identidad y rol; la pertenencia al tenant se verifica en las consultas y operaciones.

Las cuentas autenticadas de cliente son globales (`users.barbershop_id=NULL`) y solo se activan después de verificar correo. `client_account_shop_links` une cada cuenta con un perfil CRM nuevo y tenant-scoped. Una cita guest se puede reclamar únicamente mediante su token privado aleatorio, cuyo hash ya está asociado a la cita; el teléfono no autoriza acceso ni fusiona historiales. El portal incluye login verificado, historial, reserva autenticada, reclamación por token, cancelación/reprogramación de citas futuras vinculadas y favoritos de barberías, barberos y servicios. Los favoritos se guardan en `client_account_favorites` con control de propietario y validación tenant-scoped; el contenido histórico se elimina lógicamente. La migración `035_shop_favorites` amplía de forma compatible el conjunto de tipos permitidos.

Los límites por IP de login, recuperación de contraseña, solicitudes de soporte y reservas públicas se guardan en MySQL con actualizaciones atómicas. La IP procede del socket por defecto; `CLIENT_IP_HEADER` permite seleccionar únicamente `CF-Connecting-IP` o `X-Real-IP` cuando un proxy confiable los sobrescribe. No se confía en `X-Forwarded-For`. Las credenciales de producción y URLs se suministran por variables de entorno. En producción, `main.py` exige clave secreta robusta, HTTPS para los orígenes configurados y URL de frontend HTTPS.

## Notificaciones y tareas de fondo

Las operaciones relevantes escriben notificaciones internas y entregas email/WhatsApp en una outbox MySQL. El worker procesa entregas con idempotencia, leases y reintentos, y ejecuta lotes limitados de limpieza de Style Passport según la política de cada tenant. La disponibilidad externa depende de la configuración del proveedor. La bandeja del frontend consulta periódicamente; cuando está cerrada solo actualiza el contador de no leídas y, cuando está abierta, renueva la lista. Ese es el mecanismo de actualización de notificaciones disponible; no hay un canal WebSocket activo.

## Analítica

El pronóstico de demanda usa el historial de citas completadas y las reservas conocidas; es una estimación estadística explicable, no aprendizaje automático. Los reportes financieros usan pagos almacenados y la zona horaria del tenant. No hay Redis, almacenamiento analítico separado ni cola Celery configurados.

## Módulos desconectados

Los módulos antiguos de rutas async de citas y modo en servicio, que no estaban montados y eran incompatibles con las sesiones síncronas MySQL, fueron retirados. El flujo vigente usa `/barber/appointments/{appointment_id}/status` para iniciar y `/barber/appointments/{appointment_id}/payment` para completar con pago, métricas, logros y notificaciones en una transacción. El recorrido está cubierto en `backend/tests/test_operational_flow.py`; no debe reintroducirse una ruta que marque una cita completada sin pago.

## Guías relacionadas

- `docs/API_REFERENCE.md`: rutas activas, permisos y contratos principales.
- `docs/DATABASE.md`: configuración y operaciones de base de datos.
- `docs/STANDARDS.md`: convenciones de contribución; cualquier ejemplo debe mantenerse alineado con MySQL y los patrones realmente usados.
- `docs/PRODUCT_AUDIT.md`, `docs/PERMISSION_MATRIX.md`, `docs/DESIGN_SYSTEM.md`, `docs/DEVELOPMENT_STANDARD.md`, `docs/DECISIONS.md` y `docs/SECURITY_REVIEW.md`: corte de estado, permisos, tokens visuales, estándar y riesgos conocidos.
