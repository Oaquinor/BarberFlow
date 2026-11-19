# KingFlow Barber — estado técnico actual

Este resumen refleja el código y las pruebas disponibles, no una lista de funciones futuras.

## Stack

- API: Python, FastAPI, SQLAlchemy y Alembic.
- Base de datos: **MySQL 8.4**, mediante `mysql+pymysql`.
- Frontend: HTML, CSS y JavaScript; PWA con service worker.
- Mensajería: outbox transaccional MySQL; SMTP y gateway WhatsApp Baileys configurables.
- Worker: `backend/scripts/notification_worker.py`; Celery y Redis no se usan.

## Flujos implementados

- Registro de barbería y owner, login, renovación/revocación de sesiones, cambio de contraseña desde los portales de owner/barbero y superadmin, y recuperación por correo con token de un solo uso.
- Autorización por rol y aislamiento por `barbershop_id` en rutas de negocio.
- Página pública: catálogo, turnos calculados para la duración del servicio y filtrados por citas/ausencias, reserva sin cuenta, seguimiento mediante token, reprogramación y cancelación.
- Operación de barbero: agenda día/semana/mes, transiciones de cita, atención presencial, cobro y comisión.
- Disponibilidad y ausencias: el barbero genera turnos y registra bloqueos futuros; el backend protege los rangos contra citas existentes y nuevas reservas.
- Operación de negocio: personal, gestión de clientes (edición y estado con historial conservado), servicios, caja diaria, cierre y comisiones.
- Configuración del negocio: owner edita nombre, horarios, zona horaria y marca; los cambios se auditan y se reflejan en el perfil.
- Superadministración: overview global, tenants, usuarios, suscripciones, parámetros de registro y periodo inicial, pagos externos registrados, afiliados, comisiones y auditoría.
- El owner puede consultar el estado efectivo del periodo de suscripción y el uso real de límites por barbería.
- Notificaciones internas y entregas durables SMTP/WhatsApp con recordatorios programados.
- Logros, modo de servicio, onboarding y personalización de marca.
- Analítica de rendimiento y referencia estadística de demanda de siete días para owners.
- Reporte financiero por rango de hasta 366 días con desglose por fecha comercial, método y barbero, basado en pagos efectivamente registrados.

## Verificación local

Verificaciones disponibles en este workspace (distinguiendo ejecuciones anteriores de la repetición actual):

- Backend, ejecución completa previamente registrada: `python -m pytest backend/tests -q` — **73 passed** en MySQL 8.4 desechable; 2 advertencias de dependencias de prueba. Incluyó recuperación no enumerativa y limitada, tokens vencidos/de un solo uso, contraseñas robustas, retención acotada de buckets y revocación inmediata de access y refresh tokens.
- Backend, repetición actual: **28 passed, 47 skipped**. Los tests de integración omitieron ejecución porque `TEST_DATABASE_URL` no está configurada y no hay servidor MySQL local disponible; el listener local de 3306 pertenece a PostgreSQL. Esta repetición no valida ahora los flujos de integración MySQL.
- Frontend, ejecución actual: `npm test` desde `frontend/` — **19 passed**. Incluye reserva pública por duración de servicio y reprogramación por duración de la cita, además de cambio de contraseña, carga PWA y otras conexiones del portal.
- WhatsApp, ejecución actual: `npm test` desde `whatsapp-service/` — **6 passed**.
- Se añadió `.github/workflows/ci.yml` para ejecutar migraciones y las tres suites en GitHub Actions con MySQL 8.4. GitHub reporta **0 ejecuciones** en el repositorio y el workflow aún no se ha ejecutado desde esta rama local.
- Python compileall, `node --check` y `git diff --check` pasaron.
- La aplicación también inicializó en modo producción con secreto válido, MySQL y una lista CORS HTTPS; la prueba rechazó valores vacíos, wildcard y HTTP.
- Alembic 001→022 se aplicó desde una base MySQL 8.4 vacía; se hizo downgrade y re-upgrade de 021 y quedó en head. Las migraciones 020–021 añaden recuperación de contraseña y revocación de access tokens por versión; la 022 indexa la depuración de buckets caducados.
- La pantalla de registro se inspeccionó en Chrome con emulación iPhone SE a 375 × 667 px; el formulario se presenta en una columna. Se corrigió el listener PWA que cancelaba la instalación nativa en páginas sin botón personalizado. Auditoría y tablas de afiliados ahora exponen etiquetas por celda en el diseño móvil.
- No se pudo validar Docker Compose en runtime porque Docker no está instalado en el equipo.
- No se enviaron mensajes reales: dependen de credenciales SMTP y una sesión WhatsApp autorizada.
- La pantalla y API de recuperación se probaron con envío SMTP simulado; hace falta configurar SMTP para validar entrega real. Producción ahora requiere `FRONTEND_BASE_URL` HTTPS para construir los enlaces de recuperación.

Para repetir la suite del backend, crea una base **desechable MySQL** cuyo nombre termine en `_test`, establece `TEST_DATABASE_URL=mysql+pymysql://...` y ejecuta `python -m pytest backend/tests -q`. La fixture rechaza URLs que no sean MySQL o que no terminen en `_test`.

## Límites confirmados

- Los cobros de suscripción y las comisiones de afiliado se registran después de recibir un pago externo; no existe pasarela de pago conectada.
- El pronóstico es un promedio histórico explicable; no usa un modelo entrenado ni un proveedor generativo.
- El manager WebSocket es un prototipo sin ruta autenticada ni emisión conectada a las citas. El portal usa bandeja interna con consulta periódica.
- No hay notificaciones push ni proveedor SMS.
- Credenciales y secretos de infraestructura se administran mediante configuración de despliegue, no desde la interfaz de plataforma.
- La entrega depende de la configuración del proveedor; la cola reintenta y registra fallos, pero no garantiza entrega externa.
- El calendario de ausencias usa rangos locales de una fecha y la migración 018 persiste los bloqueos en MySQL.
- El portal del owner muestra plan, estado efectivo del periodo y uso de límites desde MySQL; una suscripción vencida se presenta como vencida sin mutar al consultarla.
- La PWA conserva el diálogo nativo de instalación en páginas sin botón propio y usa el botón personalizado solo en la pantalla que lo ofrece.
- Las respuestas HTTP incluyen cabeceras anti-iframe, anti-MIME-sniffing, política de referencia y permisos; las rutas API usan `Cache-Control: no-store`, y producción activa HSTS.
- El inicio en producción rechaza CORS vacío, comodín o HTTP y requiere `FRONTEND_BASE_URL` HTTPS; Compose exige el secreto, el origen frontend y la lista CORS, y Render deja ambos orígenes como configuración explícita.
- La recuperación usa tokens de 256 bits con hash SHA-256 en MySQL, 30 minutos de vigencia, uso único, limitación de solicitudes y revocación global de sesiones. La columna auth_version invalida también access tokens ya emitidos al cambiar o recuperar contraseña.
- Los buckets de login/soporte/recuperación se depuran de forma periódica, conservando solo el último día; cada ciclo borra como máximo 1.000 buckets vencidos y 1.000 tokens expirados por proceso.
- El portal valida el destino para compartir por WhatsApp contra `https://wa.me` y abre la pestaña con `noopener,noreferrer`; el service worker renueva la caché al incluir ese control.

## Fuentes de detalle

- Rutas y permisos: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).
- Arquitectura existente y limitaciones: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- Base de datos y migraciones: [`docs/DATABASE.md`](docs/DATABASE.md).
- Operación de notificaciones: [`docs/NOTIFICATIONS_SYSTEM.md`](docs/NOTIFICATIONS_SYSTEM.md).
- Despliegue: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

El trabajo está en la rama `codex/kingflow-completion`. Los cambios locales aún no están comprometidos ni publicados.
