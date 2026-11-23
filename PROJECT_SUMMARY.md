# KingFlow Barber — estado técnico actual

Este resumen refleja el código y las pruebas disponibles, no una lista de funciones futuras.

## Stack

- API: Python, FastAPI, SQLAlchemy y Alembic.
- Base de datos: **MySQL 8.4**, mediante `mysql+pymysql`.
- Frontend: HTML, CSS y JavaScript; PWA con service worker.
- Mensajería: outbox transaccional MySQL; SMTP y gateway WhatsApp Baileys configurables.
- Worker: `backend/scripts/notification_worker.py`; Celery y Redis no se usan.

## Flujos implementados

- Registro de barbería y owner, login, renovación/revocación de sesiones, cambio de contraseña desde los portales de owner/barbero y superadmin, y recuperación por correo con token de un solo uso. Las contraseñas nuevas comparten una regla uniforme de 12 caracteres, mayúscula y número.
- Autorización por rol y aislamiento por `barbershop_id` en rutas de negocio.
- Página pública: catálogo, turnos calculados para la duración del servicio y filtrados por citas/ausencias, reserva sin cuenta, seguimiento mediante token, reprogramación y cancelación.
- Operación de barbero: agenda día/semana/mes, transiciones de cita, atención presencial, cobro y comisión. El checkout persiste pago, cita, notificaciones, rendimiento y logros en una sola transacción MySQL.
- Disponibilidad y ausencias: el barbero genera turnos y registra bloqueos futuros; el backend protege los rangos contra citas existentes y nuevas reservas.
- Operación de negocio: equipo (alta, perfil, estado y comisiones), clientes (alta manual, edición, estado con historial conservado, lista paginada con búsqueda tenant-scoped e historial paginado de citas y cobros), servicios, caja diaria y cierre.
- Configuración del negocio: owner edita nombre, horarios, zona horaria, logo y marca; la carga de logos valida y vuelve a codificar PNG/JPEG estáticos antes de guardarlos, y los cambios de perfil y onboarding se auditan y se reflejan en el perfil público. Los portales permiten imágenes del mismo origen o del origen API configurado.
- El enfoque del dashboard devuelve consejos concretos según el objetivo del negocio; se limita a funciones presentes en agenda, historial, notas y servicios, sin prometer feedback, widgets o métricas que el panel no implementa.
- Los portales de owner/barbero, cliente, administración y onboarding comparten avisos accesibles y confirmaciones con diálogo; el service worker entrega esos recursos también desde la caché offline.
- Superadministración: overview global, tenants, usuarios, suscripciones, parámetros de registro y periodo inicial, pagos externos registrados, afiliados, comisiones, bandeja MySQL de soporte y auditoría.
- La administración de suscripciones muestra renovación manual; las suscripciones nuevas no activan auto-renovación mientras no exista una pasarela conectada.
- La lista de tenants entrega su moneda ISO desde MySQL y el formulario de cobro SaaS la muestra junto al importe para evitar registros en una moneda equivocada.
- El owner puede consultar el estado efectivo del periodo de suscripción y el uso real de límites por barbería.
- Cuando el periodo vence o quedan siete días o menos, el owner puede registrar una solicitud auditada y tenant-scoped en la bandeja de soporte; no cobra ni reactiva la suscripción, y reutiliza una solicitud que siga abierta.
- La bandeja de soporte del superadmin muestra el total de solicitudes abiertas, consulta cambios cada 60 segundos mientras la pestaña está visible y avisa cuando llega una nueva solicitud.
- Notificaciones internas y entregas durables SMTP/WhatsApp con recordatorios programados.
- Logros, modo de servicio, onboarding y personalización de marca.
- Analítica de rendimiento y referencia estadística de demanda de siete días para owners.
- Reporte financiero por rango de hasta 366 días con desglose por fecha comercial, método y barbero, basado en pagos efectivamente registrados.

## Verificación

En el commit `480fdb91d06d150cb987e5682edd5c4b8288b110`, el workflow de GitHub [run 45091464047](https://github.com/Oaquinor/BarberFlow/actions/runs/45091464047) pasó los tres jobs: backend y migraciones sobre MySQL 8.4, frontend/WhatsApp/responsive Chromium e imágenes/Compose de producción. Se ejecutaron **163 pruebas backend**, **100 pruebas frontend**, **22 pruebas Chromium** y **8 pruebas WhatsApp**. La nueva regresión MySQL verifica que la administración no pueda crear, actualizar ni reactivar un plan pagado como activo sin un pago registrado; la ruta de pago externo es la que activa el periodo. El backend también comprueba que una suscripción nueva no active auto-renovación aunque un cliente API antiguo envíe ese campo. `main` permanece intacta y no se hizo despliegue de producción.

- Backend: **163 pruebas** en CI sobre MySQL 8.4; aplica y revierte las migraciones. El alcance detallado por flujo está en `VALIDATION_GUIDE.md` y en los archivos de prueba.
- Frontend: `npm test` — **100 passed en CI**; Playwright — **22 passed en CI** y seis páginas evaluadas en Chromium a 320 × 640, 375 × 667 y 768 × 1024 px, además de interacciones de reserva, onboarding, avisos y configuración gratuita.
- WhatsApp: pruebas y auditoría de dependencias pasaron.
- Imágenes de producción: builds, usuario sin privilegios y smoke test de API pasaron.
- Compose de producción: `docker compose -f docker-compose.prod.yml config --quiet` pasó con variables de CI.
- El CI ejecutó `pip-audit -r backend/requirements.txt` y `npm audit` en frontend y WhatsApp sin vulnerabilidades conocidas.
- Las ejecuciones previas incluyen pruebas específicas de bloqueo de envíos dobles, manejo de respuestas de red inciertas, gestión de la ficha del barbero, bandeja de soporte y estado visible de carga del logo.
- Se actualizaron dependencias Python vulnerables, se sustituyó `python-jose` por `PyJWT`, se usa `httpx2` para el TestClient compatible con Starlette actual y se consolidaron los tres archivos de instalación para evitar perfiles inconsistentes; MySQL sigue siendo la única base admitida.
- La base MySQL de pruebas no está configurada en este equipo; las pruebas de integración que la requieren se omiten localmente. La verificación autoritativa de backend en esta rama es CI sobre MySQL 8.4. No se cuentan las pruebas omitidas como aprobadas.
- El control estático local `flake8 --select=F401,F821,F822,F823 backend/app backend/tests` pasó sin hallazgos después de retirar imports obsoletos. El flake8 general conserva avisos históricos de estilo (líneas extensas y comparaciones booleanas SQLAlchemy), fuera del control CI enfocado.
- Las cuotas de login, recuperación, soporte y reserva ahora comparten la resolución de IP: socket por defecto o `CF-Connecting-IP`/`X-Real-IP` configurado explícitamente. No se acepta `X-Forwarded-For` como fuente de IP.
- Se inspeccionó la pantalla de registro en Chrome con emulación iPhone SE a 375 × 667 px. Playwright amplía la verificación a seis páginas en Chromium; no equivale a una matriz de navegadores ni a pruebas en dispositivos físicos.
- No se validó Docker Compose en runtime en el equipo local porque Docker no está instalado.
- No se verificó entrega real de SMTP/WhatsApp porque requiere credenciales SMTP y una sesión WhatsApp autorizada.
- La pantalla y API de recuperación se probaron con SMTP simulado; producción requiere `FRONTEND_BASE_URL` HTTPS para construir los enlaces.

### Matriz de módulos y evidencia

| Módulo | Estado en código | Evidencia y límite de validación |
|---|---|---|
| Autenticación, recuperación y sesiones | Implementado | Suite backend en MySQL 8.4; sin auditoría externa ni prueba de penetración. |
| Aislamiento multitenant y permisos por rol | Implementado | Suite backend en MySQL 8.4; no equivale a una certificación de seguridad. |
| Registro SaaS, planes y configuración de plataforma | Parcial | APIs y controles probados; registro muestra el periodo configurado y el uso/límite mensual coincide. Suscripciones y comisiones se registran tras cobro externo, sin pasarela ni catálogo de precios configurados. |
| Reserva pública, disponibilidad, seguimiento y cambios | Implementado | Suite backend MySQL y pruebas frontend; la concurrencia está cubierta en CI MySQL. |
| Equipo, agenda, ausencias, servicios y clientes | Implementado | Suite backend MySQL y pruebas frontend; perfiles, búsqueda, paginación e historial de citas/cobros son tenant-scoped, alta manual sujeta a límite del plan. |
| Atención, cobros, caja y comisiones | Implementado | Suite backend MySQL; transiciones y reportes se basan en pagos persistidos. |
| Administración general, soporte y auditoría | Implementado | Suite backend MySQL y pruebas frontend; solicitudes de soporte persisten si falla SMTP y solo superadmin gestiona su estado. |
| Notificaciones internas y cola durable | Implementado | Persistencia/reintentos MySQL probados; entrega efectiva depende de proveedores configurados. |
| SMTP y WhatsApp | Parcial | Pruebas de API y servicio pasan; no hubo entrega real con credenciales de producción. |
| Rendimiento, logros y pronóstico | Implementado | Datos y endpoints incluidos en suite backend MySQL; pronóstico estadístico simple, sin modelo entrenado. |
| PWA | Implementado | Suite frontend verifica service worker, caché, recursos offline y enlaces privados; Playwright verifica seis páginas responsivas y el modal compartido en Chromium; sin matriz completa de dispositivos/navegadores. |
| Inteligencia artificial | Parcial | El pronóstico es descriptivo y no usa modelo generativo o entrenado. |
| Despliegue y operación de producción | Pendiente de validación | No se desplegó ni se validaron Compose/proveedores en producción; no se publicó ningún cambio a producción. |

Para repetir la suite del backend, crea una base **desechable MySQL** cuyo nombre termine en `_test`, establece `TEST_DATABASE_URL=mysql+pymysql://...` y ejecuta `python -m pytest backend/tests -q`. La fixture rechaza URLs que no sean MySQL o que no terminen en `_test`.

## Límites confirmados

- Los cobros de suscripción y las comisiones de afiliado se registran después de recibir un pago externo; no existe pasarela de pago conectada.
- El pronóstico es un promedio histórico explicable; no usa un modelo entrenado ni un proveedor generativo.
- El portal usa bandeja interna con consulta periódica; no hay un canal WebSocket activo.
- No hay notificaciones push ni proveedor SMS.
- Credenciales y secretos de infraestructura se administran mediante configuración de despliegue, no desde la interfaz de plataforma.
- La entrega depende de la configuración del proveedor; la cola reintenta y registra fallos, pero no garantiza entrega externa.
- El calendario de ausencias usa rangos locales de una fecha y la migración 018 persiste los bloqueos en MySQL.
- El portal del owner muestra plan, estado efectivo del periodo y uso de límites desde MySQL; una suscripción vencida se presenta como vencida sin mutar al consultarla.
- La PWA conserva el diálogo nativo de instalación en páginas sin botón propio y usa el botón personalizado solo en la pantalla que lo ofrece.
- Las respuestas HTTP incluyen cabeceras anti-iframe, anti-MIME-sniffing, política de referencia y permisos; las rutas API usan `Cache-Control: no-store`, y producción activa HSTS.
- `.gitignore` excluye archivos de entorno reales como `.env.production` y conserva los archivos `.env.*.example`; Git verificó ambas reglas en la rama de implementación.
- El inicio en producción rechaza CORS vacío, comodín o HTTP y requiere `FRONTEND_BASE_URL` HTTPS; Compose exige el secreto, el origen frontend y la lista CORS. El blueprint Render sirve frontend/API bajo el mismo origen en cómputo de pago, persiste logos en un disco de 1 GB y solicita la URL del gateway WhatsApp y un remitente SMTP verificado para API y worker.
- La recuperación usa tokens de 256 bits con hash SHA-256 en MySQL, 30 minutos de vigencia, uso único, limitación de solicitudes y revocación global de sesiones. La columna auth_version invalida también access tokens ya emitidos al cambiar o recuperar contraseña.
- Los buckets de login/soporte/recuperación se depuran de forma periódica, conservando solo el último día; cada ciclo borra como máximo 1.000 buckets vencidos y 1.000 tokens expirados por proceso.
- El portal valida el destino para compartir por WhatsApp contra `https://wa.me` y abre la pestaña con `noopener,noreferrer`; el service worker renueva la caché al incluir ese control.

## Fuentes de detalle

- Rutas y permisos: [`docs/API_REFERENCE.md`](docs/API_REFERENCE.md).
- Arquitectura existente y limitaciones: [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md).
- Base de datos y migraciones: [`docs/DATABASE.md`](docs/DATABASE.md).
- Operación de notificaciones: [`docs/NOTIFICATIONS_SYSTEM.md`](docs/NOTIFICATIONS_SYSTEM.md).
- Despliegue: [`docs/DEPLOYMENT.md`](docs/DEPLOYMENT.md).

Los cambios de estabilización, gestión del equipo y los clientes, persistencia de soporte, actualización auditada del logo, auditoría de onboarding, estado de carga, atomicidad del checkout, reactivación segura de recordatorios y presentación del periodo gratuito configurado están validados en GitHub en la rama indicada.
