"""Concurrent MySQL coverage for login password guessing limits."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.endpoints.platform import _login_buckets
from app.core.database import get_db
from app.main import app
from app.models import LoginAttempt


def test_login_failure_limit_cannot_be_bypassed_by_concurrent_requests(mysql_test_engine):
    email = f"unknown-{uuid4().hex}@example.com"
    ip_address = f"login-{uuid4().hex}"
    buckets = _login_buckets(email, ip_address)

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    def attempt_login(_index: int):
        with TestClient(app, client=(ip_address, 12345)) as client:
            return client.post("/api/v1/auth/login", json={
                "email": email,
                "password": "WrongPassword123",
            })

    try:
        with ThreadPoolExecutor(max_workers=7) as pool:
            responses = list(pool.map(attempt_login, range(7)))

        assert sum(response.status_code == 401 for response in responses) == 5
        assert sum(response.status_code == 429 for response in responses) == 2
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            for key_hash, _ in buckets:
                db.query(LoginAttempt).filter(LoginAttempt.key_hash == key_hash).delete()
            db.commit()
