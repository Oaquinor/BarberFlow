"""Concurrent MySQL coverage for the public support-message quota."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.api.v1.endpoints.platform import SUPPORT_MESSAGE_LIMIT, _login_bucket_hash
from app.core.database import get_db
from app.main import app
from app.models import LoginAttempt, SupportTicket


def test_support_ip_quota_cannot_be_exceeded_by_concurrent_requests(mysql_test_engine):
    ip_address = f"support-{uuid4().hex}"
    sender_email = f"support-{uuid4().hex}@example.com"

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db

    def send_message(_index: int):
        with TestClient(app, client=(ip_address, 12345)) as client:
            return client.post("/api/v1/support/contact", json={
                "name": "Concurrent visitor",
                "email": sender_email,
                "message": "Necesito ayuda con mi cita",
            })

    try:
        with ThreadPoolExecutor(max_workers=SUPPORT_MESSAGE_LIMIT + 2) as pool:
            responses = list(pool.map(send_message, range(SUPPORT_MESSAGE_LIMIT + 2)))

        assert sum(response.status_code == 200 for response in responses) == SUPPORT_MESSAGE_LIMIT
        assert sum(response.status_code == 429 for response in responses) == 2
        with Session(mysql_test_engine) as db:
            assert db.query(SupportTicket.id).filter(
                SupportTicket.sender_email == sender_email,
            ).count() == SUPPORT_MESSAGE_LIMIT
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(SupportTicket).filter(
                SupportTicket.sender_email == sender_email,
            ).delete(synchronize_session=False)
            db.query(LoginAttempt).filter(
                LoginAttempt.key_hash == _login_bucket_hash("support-ip", ip_address),
            ).delete(synchronize_session=False)
            db.commit()
