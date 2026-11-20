# Guía de validación de KingFlow Barber

Esta guía describe comprobaciones que existen en el repositorio. No presupone cuentas de demostración, servicios externos conectados ni un despliegue de producción.

## Requisitos

- MySQL 8 con una base de desarrollo y una base desechable para pruebas.
- Python 3.12 o posterior, con dependencias de `backend/requirements.txt`.
- Node.js 20 o posterior para las pruebas de frontend y WhatsApp.

KingFlow usa SQLAlchemy síncrono con PyMySQL y MySQL. SQLite no está soportado.

## Entorno local

Desde PowerShell, configura `backend/.env` a partir de `backend/.env.example` y establece `DATABASE_URL` con una base MySQL local. Luego ejecuta:

```powershell
cd backend
python -m pip install -r requirements.txt
alembic upgrade head
python -m scripts.create_admin
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

El comando de administrador solicita las credenciales de forma interactiva; el repositorio no incluye contraseñas de prueba. La API sirve el frontend en `http://127.0.0.1:8000`. Swagger y ReDoc aparecen solo cuando `DEBUG=True`; se deshabilitan en producción.

Para servir el frontend por separado durante el desarrollo, inicia `python scripts/serve_frontend.py` desde `backend` y abre `http://localhost:3000`. `frontend/js/config.js` dirige ese origen local a la API en el puerto 8000.

Los datos de demostración son opcionales y deben crearse solo en una base de desarrollo vacía:

```powershell
$env:ENVIRONMENT = "development"
python -m scripts.seed_db --allow-demo-data
```

El script solicita confirmación explícita, rechaza otros entornos y se niega a modificar un tenant de demostración existente.

## Pruebas

Las pruebas de integración backend borran y recrean el esquema de `TEST_DATABASE_URL`. Usa una base MySQL desechable cuyo nombre termine en `_test`; nunca apuntes esta variable a datos que quieras conservar.

```powershell
cd backend
$env:TEST_DATABASE_URL = "mysql+pymysql://usuario:clave@localhost:3306/kingflow_barber_test"
python -m pytest tests -q
```

Frontend:

```powershell
cd frontend
npm test
```

WhatsApp:

```powershell
cd whatsapp-service
npm ci
npm test
```

La CI de GitHub prueba migraciones MySQL 8.4, ejecuta downgrade/upgrade de recuperación y corre las suites backend, frontend y WhatsApp.

## Recorrido operativo y cobertura

- `backend/tests/test_operational_flow.py` valida reserva pública, confirmación, agenda, inicio, pago, rendimiento, caja y seguimiento.
- `backend/tests/test_concurrent_booking.py` valida reservas concurrentes y conflictos con el inicio de servicios.
- `backend/tests/test_checkout_cash.py` cubre cobro, doble cobro, cierre de caja y límites de concurrencia.
- `frontend/tests/service-worker.test.js` valida el shell PWA, caché de recursos, protección de tokens y recuperación offline.

El inicio usa `PUT /api/v1/barber/appointments/{id}/status`; completar una atención requiere registrar el cobro en `POST /api/v1/barber/appointments/{id}/payment`. No hay una ruta que finalice el servicio omitiendo el pago.

Para contratos, permisos y campos completos, consulta `docs/API_REFERENCE.md`. La ejecución de CI es la evidencia para las pruebas que necesitan MySQL; una prueba local omitida no cuenta como ejecución exitosa.
