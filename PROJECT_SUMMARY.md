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
- Operación de barbero: agenda día/semana/mes, transiciones de cita, atención presencial, cobro y comisión. El checkout persiste pago, cita, notificaciones, rendimiento y logros en una sola transacción MySQL.
- Disponibilidad y ausencias: el barbero genera turnos y registra bloqueos futuros; el backend protege los rangos contra citas existentes y nuevas reservas.
- Operación de negocio: equipo (alta, perfil, estado y comisiones), clientes (alta manual, edición, estado con historial conservado, lista paginada con búsqueda tenant-scoped e historial paginado de citas y cobros), servicios, caja diaria y cierre.
- Configuración del negocio: owner edita nombre, horarios, zona horaria, logo y marca; los cambios de perfil, logo y onboarding se auditan y se reflejan en el perfil público.
- Los portales de owner/barbero, cliente, administración y onboarding comparten avisos accesibles y confirmaciones con diálogo; el service worker entrega esos recursos también desde la caché offline.
- Superadministración: overview global, tenants, usuarios, suscripciones, parámetros de registro y periodo inicial, pagos externos registrados, afiliados, comisiones, bandeja MySQL de soporte y auditoría.
- El owner puede consultar el estado efectivo del periodo de suscripción y el uso real de límites por barbería.
- Notificaciones internas y entregas durables SMTP/WhatsApp con recordatorios programados.
- Logros, modo de servicio, onboarding y personalización de marca.
- Analítica de rendimiento y referencia estadística de demanda de siete días para owners.
- Reporte financiero por rango de hasta 366 días con desglose por fecha comercial, método y barbero, basado en pagos efectivamente registrados.

## Verificación

La ejecución integral más reciente de GitHub Actions validó el commit `4901eef` de la rama `codex/kingflow-completion` (20 de noviembre de 2026) y terminó en `success`: [run 44728375352](https://github.com/Oaquinor/BarberFlow/actions/runs/44728375352). El backend ejecutó **125 pruebas sobre MySQL 8.4, sin advertencias de pytest**; el frontend pasó **77 pruebas unitarias y 19 comprobaciones Chromium** —18 responsivas más el flujo real del aviso y la confirmación accesibles—, y WhatsApp pasó **8 pruebas**. También pasaron las auditorías de dependencias, las imágenes de producción y la validación de `docker-compose.prod.yml`. CI aplicó y revirtió la cadena de migraciones hasta `026_users_client_listing`, comprobando también su nueva ruta de downgrade que conserva el índice necesario para la clave foránea MySQL; levantó la API con Compose contra MySQL efímero y verificó `/health`, luego retiró los contenedores y el volumen descartable. El control estático enfocado de imports sin uso y nombres no definidos pasó para la aplicación y sus pruebas. La prueba `backend/tests/test_api_reference.py` verifica las **98 operaciones API** contra OpenAPI y su referencia publicada. Las acciones oficiales de CI usan runtime Node 24. La cobertura incluye carreras de cierre de caja entre propietario y barbero, cobro frente a cierre, recálculo del rendimiento diario, actualización durable de recordatorios y renovaciones SaaS simultáneas. `main` permanece intacta.

- Backend: **125 pruebas** en CI sobre MySQL 8.4; aplica y revierte las migraciones. Incluye la aplicación de vencimiento de suscripción al portal público, recuperación de recordatorios cuando vuelve a estar disponible el contacto del cliente, persistencia de cambios en recordatorios existentes, carreras de caja, prueba concurrente de resumen de rendimiento por barbero y fecha, búsquedas paginadas de clientes verificadas por nombre/teléfono y aislamiento de tenant, historial de citas/pagos con permisos de propietario y límite por tenant, y cobertura para evitar desajustes entre rutas OpenAPI y `API_REFERENCE.md`.
- Frontend: `npm test` — **77 passed**; Playwright — **19 passed** en Chromium para seis páginas con viewports 320 × 640, 375 × 667 y 768 × 1024 px, más el flujo real de avisos y confirmaciones compartidos. Se comprobaron overflow horizontal, controles visibles y la apertura de reserva y onboarding. Las pruebas cubren también paginación del historial del cliente, importes persistidos, escape de nombres de servicio no confiables y avisos/confirmaciones accesibles. Una regresión inyecta etiquetas y atributos de evento maliciosos en los datos de una cita y verifica que el DOM los renderice como texto. Playwright usa un worker para mantener estable la emulación móvil en equipos con menos recursos.
- WhatsApp: pruebas y auditoría de dependencias pasaron.
- Imágenes de producción: builds, usuario sin privilegios y smoke test de API pasaron.
- Compose de producción: `docker compose -f docker-compose.prod.yml config --quiet` pasó con variables de CI.
- El CI ejecutó `pip-audit -r backend/requirements.txt` y `npm audit` en frontend y WhatsApp sin vulnerabilidades conocidas.
- Las ejecuciones previas incluyen pruebas específicas de bloqueo de envíos dobles, manejo de respuestas de red inciertas, gestión de la ficha del barbero, bandeja de soporte y estado visible de carga del logo.
- Se actualizaron dependencias Python vulnerables, se sustituyó `python-jose` por `PyJWT`, se usa `httpx2` para el TestClient compatible con Starlette actual y se consolidaron los tres archivos de instalación para evitar perfiles inconsistentes; MySQL sigue siendo la única base admitida.
- La suite local, sin base MySQL de prueba configurada, fue **40 passed, 83 skipped** en Python 3.14.5. El entorno virtual local no tiene instalado `httpx2` (incluido en las dependencias de pruebas), por eso Starlette emitió una advertencia al usar `httpx`; esta ejecución no sustituye la suite MySQL de CI indicada arriba.
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
| Registro SaaS, planes y configuración de plataforma | Parcial | APIs y controles probados; suscripciones y comisiones se registran tras cobro externo, sin pasarela conectada. |
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
- El manager WebSocket es un prototipo sin ruta autenticada ni emisión conectada a las citas. El portal usa bandeja interna con consulta periódica.
- No hay notificaciones push ni proveedor SMS.
- Credenciales y secretos de infraestructura se administran mediante configuración de despliegue, no desde la interfaz de plataforma.
- La entrega depende de la configuración del proveedor; la cola reintenta y registra fallos, pero no garantiza entrega externa.
- El calendario de ausencias usa rangos locales de una fecha y la migración 018 persiste los bloqueos en MySQL.
- El portal del owner muestra plan, estado efectivo del periodo y uso de límites desde MySQL; una suscripción vencida se presenta como vencida sin mutar al consultarla.
- La PWA conserva el diálogo nativo de instalación en páginas sin botón propio y usa el botón personalizado solo en la pantalla que lo ofrece.
- Las respuestas HTTP incluyen cabeceras anti-iframe, anti-MIME-sniffing, política de referencia y permisos; las rutas API usan `Cache-Control: no-store`, y producción activa HSTS.
- `.gitignore` excluye archivos de entorno reales como `.env.production` y conserva los archivos `.env.*.example`; Git verificó ambas reglas en la rama de implementación.
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

Los cambios de estabilización, gestión del equipo y los clientes, persistencia de soporte, actualización auditada del logo, auditoría de onboarding, estado de carga, atomicidad del checkout y reactivación segura de recordatorios están validados en GitHub en la rama indicada.
