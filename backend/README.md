# KingFlow Barber API

FastAPI backend for the KingFlow Barber SaaS. The production database engine is **MySQL 8** through SQLAlchemy's `mysql+pymysql` driver. SQLite is not supported.

## Local setup

1. Create a MySQL database and account.
2. Copy `.env.example` to `.env`; configure `DATABASE_URL`, `SECRET_KEY`, CORS origins, and optional SMTP/WhatsApp credentials.
3. Install dependencies with `pip install -r requirements.txt`.
4. Apply migrations using `alembic upgrade head`.
5. Start the API with `uvicorn app.main:app --reload`.

The root route serves the PWA from `frontend/`. Swagger and ReDoc are enabled only when `DEBUG=True`.

## Tests

Integration tests require a dedicated, disposable MySQL database whose name ends in `_test`. Set `TEST_DATABASE_URL=mysql+pymysql://...` and run `python -m pytest tests -q` from this directory. The fixture refuses non-MySQL URLs and database names without the `_test` suffix, then recreates that test schema.

## Worker

Run `python scripts/notification_worker.py` to process the MySQL notification outbox and due appointment reminders. SMTP and the WhatsApp gateway are optional providers; failed or unconfigured deliveries are recorded in the queue. No Celery or Redis service is used.

See [API reference](../docs/API_REFERENCE.md), [database guide](../docs/DATABASE.md), [deployment notes](../docs/DEPLOYMENT.md), and [notification operations](../docs/NOTIFICATIONS_SYSTEM.md).
