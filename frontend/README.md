# KingFlow Barber frontend

Frontend responsive basado en HTML, CSS y JavaScript sin framework. Los portales de barbero, cliente, propietario, onboarding y administración general consumen la API del backend.

## Desarrollo local

Inicia primero MySQL y el backend desde `backend`:

```powershell
alembic upgrade head
uvicorn app.main:app --reload --host 127.0.0.1 --port 8000
```

En otra terminal inicia el servidor estático desde el repositorio:

```powershell
cd backend
python scripts/serve_frontend.py
```

Abre `http://localhost:3000`. `js/config.js` dirige las llamadas de API al backend `http://localhost:8000`; en producción, las páginas usan el mismo origen. Abrir HTML mediante `file://` no es compatible con el service worker, el routing de API ni las reglas CORS.

Para instalar el esquema en una base local, configura antes `DATABASE_URL=mysql+pymysql://...` y ejecuta `alembic upgrade head`. Desde `backend`, crea la cuenta inicial con `python -m scripts.create_admin`; el comando solicita credenciales y el repositorio no incluye cuentas de demostración.

## Portales y flujos

- `index.html`: acceso del equipo y operación del barbero.
- `client.html`: búsqueda de barberías, reserva y seguimiento público.
- `signup.html` y `onboarding.html`: alta de barbería y configuración inicial.
- `admin.html`: administración general de la plataforma.
- `js/auth.js`: manejo de sesión y llamadas autenticadas.
- `js/pwa.js`, `sw.js`, `manifest.webmanifest`: instalación y shell offline.

El service worker solo guarda recursos de la app. No almacena respuestas API autenticadas ni páginas cuya query contenga tokens, datos de contacto o credenciales. Sin conexión, no se pueden consultar ni modificar citas o datos operativos; la app muestra el aviso offline.

## Pruebas

Ejecuta las pruebas del service worker, manifiesto y rutas de entrada desde `frontend`:

```powershell
npm test
```

Las pruebas verifican que los recursos precargados existan, que las pantallas registren la PWA, que las claves de seguimiento no se almacenen en caché y que la limpieza de cachés no afecte a otras aplicaciones del mismo origen.
