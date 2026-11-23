"""Concurrent MySQL coverage for anonymous booking quotas."""

from concurrent.futures import ThreadPoolExecutor
from uuid import uuid4

from fastapi import HTTPException
from sqlalchemy.orm import Session

from app.api.v1.endpoints import platform
from app.models import LoginAttempt


def test_concurrent_bookings_cannot_exceed_shared_quota(mysql_test_engine, monkeypatch):
    monkeypatch.setattr(platform, "PUBLIC_BOOKING_TENANT_IP_LIMIT", 4)
    monkeypatch.setattr(platform, "PUBLIC_BOOKING_IP_LIMIT", 20)
    ip_address = f"203.0.113.{uuid4().int % 200 + 1}"
    tenant_id = uuid4().int % 1_000_000
    key_hashes = [
        platform._login_bucket_hash("booking-tenant-ip", f"{tenant_id}:{ip_address}"),
        platform._login_bucket_hash("booking-ip", ip_address),
    ]

    def try_booking(_index: int) -> int:
        with Session(mysql_test_engine) as db:
            try:
                from app.utils.datetime import utc_now_naive

                platform._consume_public_booking_quota(
                    db, tenant_id, ip_address, utc_now_naive(),
                )
                db.commit()
                return 200
            except HTTPException as exc:
                db.rollback()
                return exc.status_code

    try:
        with ThreadPoolExecutor(max_workers=12) as pool:
            statuses = list(pool.map(try_booking, range(12)))

        assert statuses.count(200) == 4
        assert statuses.count(429) == 8
        with Session(mysql_test_engine) as db:
            attempts = db.query(LoginAttempt).filter(LoginAttempt.key_hash.in_(key_hashes)).all()
            assert len(attempts) == 2
            assert {row.failed_count for row in attempts} == {4}
    finally:
        with Session(mysql_test_engine) as db:
            db.query(LoginAttempt).filter(LoginAttempt.key_hash.in_(key_hashes)).delete(
                synchronize_session=False,
            )
            db.commit()
