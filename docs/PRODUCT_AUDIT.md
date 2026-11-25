# Auditoría de producto KingFlow Barber

**Corte:** 25 de noviembre de 2026. Auditoría estática del repositorio y validación local; no equivale a una certificación de seguridad ni a una prueba de producción.

## Resumen

El repositorio implementa un sistema operativo multi-tenant para barberías con API FastAPI, interfaz estática/PWA y MySQL 8. Incluye reservas públicas, agenda, caja, comisiones, personalización de perfil, notificaciones configurables y administración SaaS básica. La disponibilidad de proveedores externos depende de credenciales y despliegue. Los módulos listados como parciales o pendientes no deben presentarse como funciones terminadas.

## Estado de capacidades

| Capacidad | Estado observado | Evidencia / brecha |
|---|---|---|
| Registro de barbería, acceso owner/barbero, sesiones y recuperación | Implementado | API `/auth/*`, `/saas/register`; JWT con refresh persistido/revocable |
| Catálogo público, disponibilidad, reserva de invitado y gestión con token | Implementado | API de booking; no requiere cuenta cliente |
| Portal cliente con cuenta, historial, cartera y autoservicio completo | Parcial | Página pública y seguimiento de reserva; no hay experiencia autenticada integral de cliente |
| Agenda, atención, turnos presenciales, cobro y conciliación | Implementado | Flujo de cita/pago y caja; el pago de servicio se registra manualmente |
| Perfil público: marca, horarios, zona, tema, logo, portada, galería, preguntas | Implementado | Onboarding y opciones públicas; la calidad visual requiere revisión continua en varios anchos |
| Servicios con fotografía | Implementado parcialmente | Confirmar cobertura de permisos, validación y flujo visual de extremo a extremo antes de publicitar como completo |
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
- Nuevos documentos: arquitectura de permisos, sistema visual, estándar de desarrollo, decisiones de producto y revisión de seguridad.

## Validación local y límites

- `python -m pytest backend/tests -q`: 66 passed, 99 skipped. Las pruebas omitidas requieren `TEST_DATABASE_URL` y una base MySQL de pruebas; la URL/base de prueba no estuvo disponible. No se modificó la base de datos de desarrollo.
- `npm run test:browser -- --reporter=line`: 23 passed.
- `frontend`: `npm test` 106 passed; `npm run test:browser -- --reporter=line` 23 passed.
- `whatsapp-service`: `npm test` 8 passed. `npm audit` en ambos paquetes: cero vulnerabilidades reportadas.
- `pip-audit` forma parte de CI; no está instalado localmente en este entorno, por lo que el análisis de dependencias Python no se considera validado aquí.
- No se hizo prueba de penetración, prueba de carga, despliegue productivo ni verificación de entrega real con SMTP/WhatsApp.

## Siguiente orden de entrega

1. CI con MySQL dedicado y ejecución de todas las pruebas de integración.
2. Recorrido de cliente autenticado y prueba visual/manual completa de reserva y configuración del negocio.
3. Definir país, proveedor y modelo comercial antes de diseñar cobros online.
4. Especificar y priorizar CRM/fidelidad, inventario/caja y sucursales con migraciones reversibles y permisos.
5. Threat model, MFA y revisión ASVS automatizada/dinámica antes de afirmar preparación para producción.
