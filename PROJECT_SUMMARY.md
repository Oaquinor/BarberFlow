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

## Verificación

La ejecución autoritativa más reciente de GitHub Actions corresponde al commit `39736c2763610b81ac528cc63f5c2afd5ec190a7` en la rama `codex/kingflow-completion` (19 de noviembre de 2026). Ambos jobs terminaron en `success`:

- Backend: MySQL **8.4.13**; Alembic aplicó desde cero todas las migraciones 001→022; `python -m pytest backend/tests -q` — **75 passed**, 157 warnings.
- Frontend: `npm test` — **19 passed**.
- WhatsApp: `npm test` — **6 passed**.
- La repetición local anterior del backend fue **28 passed, 47 skipped** porque no había una base MySQL de prueba configurada; no sustituye la ejecución MySQL de CI indicada arriba.
- Se inspeccionó la pantalla de registro en Chrome con emulación iPhone SE a 375 × 667 px. Esto no equivale a una prueba automatizada de compatibilidad móvil de todas las pantallas.
- No se validó Docker Compose en runtime en el equipo local porque Docker no está instalado.
- No se verificó entrega real de SMTP/WhatsApp porque requiere credenciales SMTP y una sesión WhatsApp autorizada.
- La pantalla y API de recuperación se probaron con SMTP simulado; producción requiere `FRONTEND_BASE_URL` HTTPS para construir los enlaces.

### Matriz de módulos y evidencia

| Módulo | Estado en código | Evidencia y límite de validación |
|---|---|---|
| Autenticación, recuperación y sesiones | Implementado | Suite backend en MySQL 8.4; sin auditoría externa ni prueba de penetración. |
| Aislamiento multitenant y permisos por rol | Implementado | Suite backend en MySQL 8.4; no equivale a una certificación de seguridad. |
| Registro SaaS, planes y configuración de plataforma | Parcial | APIs y controles probados; suscripciones y comisiones se registran tras cobro externo, sin pasarela conectada. |
| Reserva pública, disponibilidad, seguimiento y cambios | Implementado | Suite backend MySQL y pruebas frontend; la concurrencia está cubierta en CI MySQL. |
| Agenda, ausencias, servicios y clientes | Implementado | Suite backend MySQL y pruebas frontend de conexión con API. |
| Atención, cobros, caja y comisiones | Implementado | Suite backend MySQL; transiciones y reportes se basan en pagos persistidos. |
| Administración general, soporte y auditoría | Implementado | Suite backend MySQL y pruebas frontend; pagos de suscripción anotados tras cobro externo. |
| Notificaciones internas y cola durable | Implementado | Persistencia/reintentos MySQL probados; entrega efectiva depende de proveedores configurados. |
| SMTP y WhatsApp | Parcial | Pruebas de API y servicio pasan; no hubo entrega real con credenciales de producción. |
| Rendimiento, logros y pronóstico | Implementado | Datos y endpoints incluidos en suite backend MySQL; pronóstico estadístico simple, sin modelo entrenado. |
| PWA | Implementado | Suite frontend verifica service worker, caché y enlaces privados; sin matriz completa de dispositivos/navegadores. |
| Inteligencia artificial | Parcial | El pronóstico es descriptivo y no usa modelo generativo o entrenado. |
| Despliegue y operación de producción | Pendiente de validación | No se desplegó ni se validaron Compose/proveedores en producción; no se publicó ningún cambio a producción. |

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

El trabajo está en la rama `codex/kingflow-completion`, sincronizada con GitHub en el commit indicado. `main` permanece intacta.
