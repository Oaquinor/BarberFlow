# KingFlow Barber

KingFlow Barber is a multi-tenant barber shop management SaaS with a FastAPI backend, static JavaScript PWA, MySQL database, and an optional WhatsApp gateway.

## Requirements

- Python 3.12 or newer
- MySQL 8.0 or newer
- Node.js 24 LTS for frontend and WhatsApp tests
- Docker Compose only if using the container deployment

## Start locally

1. Create a MySQL database and user.
2. Copy `backend/.env.example` to `backend/.env`, then set `DATABASE_URL` and a secret key.
3. From `backend/`, install `requirements.txt`, run `alembic upgrade head`, and start `uvicorn app.main:app --reload`.
4. Open `http://localhost:8000/`. The API documentation is available at `/docs` when `DEBUG=True`.

See [QUICKSTART.md](QUICKSTART.md) for full commands and [docs/DEPLOYMENT.md](docs/DEPLOYMENT.md) for deployment configuration.

## Verify

- Frontend tests: `cd frontend && npm test`
- Backend tests require a dedicated disposable MySQL database with a name ending in `_test`; configure `TEST_DATABASE_URL` and run `python -m pytest backend/tests -q` from the repository root.
- WhatsApp service tests: `cd whatsapp-service && npm test`
- GitHub Actions runs the migration check and all three test suites on pushes and pull requests, using a disposable MySQL 8.4 service for backend integration tests.

Current implementation status and verified limits are summarized in [PROJECT_SUMMARY.md](PROJECT_SUMMARY.md). API access and routes are documented in [docs/API_REFERENCE.md](docs/API_REFERENCE.md).

The current branch is under active implementation. External email and WhatsApp delivery require provider configuration; subscription charges are recorded after an external payment and are not processed by a payment gateway.
