# Estándar de desarrollo

## Arquitectura acordada

- Backend: Python/FastAPI, SQLAlchemy síncrono y PyMySQL; MySQL 8 es el único motor soportado. No introducir SQLite.
- Esquema: cambios versionados mediante Alembic; migraciones compatibles y con downgrade razonable. Nunca usar `create_all()` para producción.
- Frontend: HTML/CSS/JavaScript estático/PWA. No introducir framework o bundler sin una decisión documentada y plan de migración.
- API: rutas bajo `/api/v1`; esquemas Pydantic para entrada/salida; separar responsabilidades en routers/servicios según el patrón existente.

## Datos, negocio y seguridad

- Dinero se guarda en centavos y con moneda explícita; no usar floats para cálculos monetarios.
- Fecha/hora se interpreta en zona IANA del tenant; guardar/convertir con reglas explícitas.
- Transaccionar conjuntamente cambios que representen una sola acción de negocio; diseñar concurrencia para MySQL real.
- Scope por tenant en cada query. Rol y tenant son controles separados; incluir prueba de acceso cruzado.
- Nunca registrar secretos, tokens o datos personales innecesarios. Configuración sensible viene del entorno.
- No marcar cobro recibido, cita pagada ni suscripción activa hasta confirmar el registro de pago real.
- Integraciones externas deben ser idempotentes, tener timeout/reintento controlado y no bloquear el request de negocio.

## Cambios y pruebas

- Añadir pruebas de unidad para reglas y pruebas MySQL para transacciones, índices, concurrencia y consultas tenant-scoped.
- Ejecutar `python -m pytest backend/tests -q`, `npm test`, `npm run test:browser -- --reporter=line` y `npm audit` para los paquetes frontend/WhatsApp pertinentes.
- CI incluye `pip-audit`; ejecutarlo o dejar constancia si no se encuentra disponible localmente.
- No considerar completa una suite cuando integra tests omitidos por falta de `TEST_DATABASE_URL`.
- Para CSS/JS público, browser tests deben cubrir vista móvil estrecha y escritorio cuando afecta layout/interacción.
- Actualizar `docs/API_REFERENCE.md`, `ARCHITECTURE.md` y matrices cuando cambien contratos o permisos.

## Accesibilidad, revisión y entrega

- Formularios con labels asociados, errores anunciados, teclado funcional, contraste y foco visible.
- Revisión de `git diff --check`; revisar que no se agreguen secretos ni artefactos generados.
- Informar validaciones reales y sus omisiones. La suite automatizada no reemplaza revisión visual, threat model ni pruebas de producción.
