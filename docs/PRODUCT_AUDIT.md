# Auditoría de producto KingFlow Barber

**Corte:** 25 de noviembre de 2026. Auditoría estática del repositorio y validación local; no equivale a una certificación de seguridad ni a una prueba de producción.

## Resumen

El repositorio implementa un sistema operativo multi-tenant para barberías con API FastAPI, interfaz estática/PWA y MySQL 8. Incluye reservas públicas, agenda, caja, comisiones, personalización de perfil, notificaciones configurables y administración SaaS básica. La disponibilidad de proveedores externos depende de credenciales y despliegue. Los módulos listados como parciales o pendientes no deben presentarse como funciones terminadas.

## Estado de capacidades

| Capacidad | Estado observado | Evidencia / brecha |
|---|---|---|
| Registro de barbería, acceso owner/barbero, sesiones y recuperación | Implementado | API `/auth/*`, `/saas/register`; JWT con refresh persistido/revocable |
| Catálogo público, disponibilidad, reserva de invitado y gestión con token | Implementado | API de booking admite invitados y cuentas verificadas; no requiere cuenta para reserva, y da seguimiento/cambio con token privado |
| Portal cliente con cuenta, historial, cartera y autoservicio completo | Parcial; cuenta verificada en evolución | Registro y login cliente con verificación SMTP, edición de nombre/teléfono, historial multi-barbería, reserva autenticada, reclamación con token privado, cancelación y reprogramación de citas vinculadas con política de negocio. Aún faltan cartera, pagos, beneficios, favoritos, exportación y eliminación de perfil |
| Agenda, atención, turnos presenciales, cobro y conciliación | Implementado | Flujo de cita/pago y caja; el pago de servicio se registra manualmente |
| Política por barbería para anticipación de cancelación/reprogramación | Implementado en este incremento | Columna MySQL versionada, rango 0–168h, aviso público y validación en ambos cambios |
| Perfil público: marca, horarios, zona, tema, logo, portada, galería, preguntas | Implementado | Onboarding y opciones públicas; la calidad visual requiere revisión continua en varios anchos |
| Servicios con fotografía | Implementado en UI/API; validación MySQL pendiente | El owner sube o selecciona fotos de galería tenant-scoped, las asigna al servicio y se muestran en el portal público y el catálogo del owner; quitar una imagen limpia sus referencias. Revisar endpoints en integración MySQL antes de certificar persistencia |
| CRM básico, clientes e historial | Implementado | Alta/edición, paginación e historial tenant-scoped |
| Comunicaciones email/WhatsApp | Parcial, proveedor opcional | Outbox y reintentos existen; entrega depende de configuración SMTP/Baileys y operación del worker; no hay SMS ni push |
| Administración de tenants, planes, soporte y afiliados | Implementado parcialmente | Operaciones administrativas existentes; cobro SaaS externo se registra manualmente |
| Mercado/directorio y descubrimiento multi-barbería | No implementado | El modelo de producto documentado se centra en operar una barbería |
| Pagos online, depósitos y reembolsos | No implementado | Sin pasarela conectada; no simular pago exitoso ni reactivación automática |
| Inventario minorista, POS de productos y gastos | No implementado | Caja actual no es inventario ni contabilidad integral |
| Fidelidad, membresías y referidos | No implementado | No hay motor de puntos o suscripciones de cliente |
| Lista de espera, citas grupales o recurrentes | No implementado | No aparecen en rutas activas |
| Multi-sucursal, renta de silla, empleo | No implementado | No afirmar soporte de sedes, contratos o nómina |
| Live Chair, Style Passport, Coach, Smart Match, Barber Studio | No implementado | Nombres del mandato sin implementación conectada constatada |
| Pronóstico de demanda | Parcial | Promedio estadístico explicable; no es ML ni predicción comercial validada |
| MFA, WebSocket, notificaciones push | No implementado | No hay MFA ni canal push/WebSocket activo |

## Contraste de mercado

La revisión de páginas oficiales de [SQUIRE](https://getsquire.com/), [Booksy](https://biz.booksy.com/who-loves-us/barber), [Fresha](https://www.fresha.com/for-business/barber), [Vagaro](https://www.vagaro.com/pro/barber-software), [Square Appointments](https://squareup.com/us/en/appointments/features?country_redirection=true), [theCut](https://thecut.co/barber-features) y [GlossGenius](https://glossgenius.com/pricing) muestra un patrón de producto: reserva ligada a agenda y recordatorios, perfil/historial de cliente, pagos/caja, herramientas de marketing y, según proveedor, lista de espera, inventario, fidelidad o descubrimiento. Esto es una referencia de mercado, no prueba de que KingFlow ya ofrezca esas capacidades ni una especificación para copiar.

## Seguridad y calidad

Hay controles útiles ya presentes: roles, aislamiento de tenant, refresh revocable, rate limits persistidos, migraciones Alembic y restricciones transaccionales MySQL. Requieren seguimiento: verificación de autorización por objeto en nuevas rutas, gestión de secretos y proxy en despliegue, pruebas de integración obligatorias contra MySQL, auditoría dinámica/penetración y matriz ASVS por requisito. Referencia: [OWASP ASVS](https://asvs.owasp.org/) y [OWASP API Security Top 10](https://owasp.org/www-project-api-security/).

## Cambios cerrados en este incremento

- Se añadieron al catálogo API cuatro rutas activas de imagen de portada y galería que faltaban en la referencia.
- Se reparó una expectativa obsoleta de expiración de sesión y dos pruebas con selectores/flujo de inicialización desactualizados.
- El menú del portal público ahora se distribuye en una cuadrícula en móviles pequeños; las pruebas de navegador comprobaron 320 y 375 px.
- El formulario de configuración del negocio ahora tiene una vista previa con el nombre, descripción, primer servicio real, logo/portada configurados y contraste calculado; se corrigieron los botones, campos e inputs de archivos que aparecían sin estructura en la captura de revisión. Las cuatro paletas tienen pares de color distintos y selección accesible.
- Se añadió una política por tenant para la anticipación mínima de cancelación/reprogramación, con migración compatible, valor histórico cero y enforcement en la API pública.
- El catálogo del owner ahora muestra las fotos reales asignadas a cada servicio; rechaza visualmente URLs fuera del origen confiable y mantiene el icono accesible para servicios sin foto.
- Se añadió una cuenta global de cliente con activación por email, límite de reenvío, token de un uso, perfiles CRM aislados por barbería e importación de una cita solo con su token privado. La pantalla cliente permite entrar, revisar historial y reclamar una cita desde su enlace; no relaciona cuentas por teléfono.
- La cuenta cliente permite reprogramar citas futuras pendientes/confirmadas desde el historial. Reutiliza las mismas reglas, política de anticipación, bloqueos de barbero, límites de agenda, reserva transaccional de disponibilidad, auditoría y notificaciones del flujo de reprogramación con enlace privado.
- El perfil de cliente permite consultar correo verificado y actualizar nombre/teléfono propios, con validación, auditoría de los campos modificados y email de solo lectura.
- Migración nueva `033_client_accounts`: crea tablas de verificación/link sin tocar citas existentes. Requiere ejecutar `alembic upgrade head` y configurar SMTP antes de habilitar altas.
- Evidencia visual: [antes](evidence/owner-settings-before.png) y [después](evidence/owner-settings-after.png).
- Nuevos documentos: arquitectura de permisos, sistema visual, estándar de desarrollo, decisiones de producto y revisión de seguridad.

## Validación local y límites

- `python -m pytest backend/tests -q`: 69 passed, 102 skipped en el último intento completo. Las pruebas omitidas requieren `TEST_DATABASE_URL` y una base MySQL de pruebas; no había instancia configurada. No se modificó la base de datos de desarrollo.
- Validación del commit `6966fc3`: `frontend/npm test` 110 passed; 4 pruebas de cuenta localmente en Chromium; GitHub Actions completó los tres motores (66 flujos por motor: Chromium, Firefox y WebKit), 171 pruebas backend en MySQL 8.4 y build/smoke test/Compose de producción. La integración MySQL incluye reserva de cuenta, rechazo de reprogramación entre cuentas, reprogramación autorizada y liberación de los turnos al reprogramar y cancelar. Run: [GitHub Actions 45617774351](https://github.com/Oaquinor/BarberFlow/actions/runs/45617774351).
- El incremento de perfil posterior a `6966fc3` pasó localmente `frontend/npm test` (110) y los cinco recorridos de cuenta en Chromium. `compileall`, las reglas de imports/nombres de CI y `git diff --check` también pasaron. La prueba MySQL del perfil debe ejecutarse en la CI del siguiente commit; localmente las tres pruebas de esta suite se omitieron por falta de `TEST_DATABASE_URL`.
- Las páginas iniciales se verifican a 320, 375, 390, 430, 768, 1024, 1366 y 1920 px.
- GitHub Actions en MySQL 8.4 confirmó migración limpia, downgrade y recuperación, y ejecutó `python -m pytest backend/tests -q`: **171 passed**, incluyendo los flujos autenticados de reserva, cancelación y reprogramación y los casos de acceso cruzado rechazado. Los tres jobs terminaron exitosamente en `6966fc3`.
- La suite completa de navegador quedó comprobada en CI: 66 flujos por motor en Chromium, Firefox y WebKit; incluye ocho anchos para las siete páginas de entrada y los flujos del portal de cuenta.
- Alembic reconoce `033_client_accounts` como head y `python -m alembic upgrade 032_cancellation_window:033_client_accounts --sql` generó el SQL MySQL esperado. No se aplicó la migración a una base local en este entorno.
- `pip-audit` y `npm audit` están en CI; las verificaciones de dependencias del workflow pasaron en `ed2520f`. No se ejecutó aquí una prueba de penetración ni de carga.
- No se hizo prueba de penetración, prueba de carga, despliegue productivo ni verificación de entrega real con SMTP/WhatsApp.

## Siguiente orden de entrega

1. CI con MySQL dedicado y ejecución de todas las pruebas de integración.
2. Recorrido de cliente autenticado y prueba visual/manual completa de reserva y configuración del negocio.
3. Definir país, proveedor y modelo comercial antes de diseñar cobros online.
4. Especificar y priorizar CRM/fidelidad, inventario/caja y sucursales con migraciones reversibles y permisos.
5. Threat model, MFA y revisión ASVS automatizada/dinámica antes de afirmar preparación para producción.
