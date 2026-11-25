# Decisiones y límites de producto

## D-001: MySQL 8 es el motor soportado

**Decisión:** backend SQLAlchemy síncrono con driver PyMySQL y migraciones Alembic sobre MySQL 8. No SQLite.

**Motivo:** las reglas de concurrencia y sintaxis de varias operaciones dependen de MySQL; CI usa MySQL. Una alternativa requeriría pruebas y soporte explícito, no una sustitución silenciosa.

## D-002: modular monolith y frontend actual

**Decisión:** mantener FastAPI con routers/servicios y frontend HTML/CSS/JS mientras se ejecuta la auditoría; no reescribir framework como parte implícita de cambios visuales.

**Motivo:** se reduce riesgo sobre flujos de reservas/caja. Una migración requiere alcance, pruebas funcionales equivalentes y despliegue gradual.

## D-003: no simular integraciones comerciales

**Decisión:** suscripciones se renuevan con registro manual de un pago externo confirmado. No conectar pasarela ni crear éxito de pago ficticio sin país, proveedor y reglas de reembolso/conciliación.

## D-004: comunicar estado por evidencia

**Decisión:** nombres del mandato (marketplace, Style Passport, Live Chair, Smart Match, Coach, Studio) permanecen como pendientes hasta tener código conectado, permisos, UX, migración y pruebas.
