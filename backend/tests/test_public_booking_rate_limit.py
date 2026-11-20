"""MySQL-backed quotas for anonymous booking writes."""

from datetime import datetime, timedelta
from types import SimpleNamespace

import pytest
from fastapi import HTTPException
from sqlalchemy.orm import Session


def test_booking_client_ip_uses_only_configured_proxy_headers(monkeypatch):
    from app.api.v1.endpoints import platform

    request = SimpleNamespace(headers={"cf-connecting-ip": "203.0.113.9"}, client=None)
    monkeypatch.setattr(platform.settings, "CLIENT_IP_HEADER", "CF-Connecting-IP")
    assert platform._public_booking_client_ip(request) == "203.0.113.9"

    request.headers = {"cf-connecting-ip": "not-an-ip"}
    with pytest.raises(HTTPException) as invalid_header:
        platform._public_booking_client_ip(request)
    assert invalid_header.value.status_code == 503


def test_public_booking_quota_limits_tenant_and_ip_and_expires(
    test_db: Session, monkeypatch,
):
    from app.api.v1.endpoints import platform

    monkeypatch.setattr(platform, "PUBLIC_BOOKING_TENANT_IP_LIMIT", 2)
    monkeypatch.setattr(platform, "PUBLIC_BOOKING_IP_LIMIT", 3)
    now = datetime(2030, 5, 10, 9)

    platform._consume_public_booking_quota(test_db, 1, "192.0.2.10", now)
    platform._consume_public_booking_quota(test_db, 1, "192.0.2.10", now + timedelta(minutes=1))
    with pytest.raises(HTTPException) as tenant_limited:
        platform._consume_public_booking_quota(test_db, 1, "192.0.2.10", now + timedelta(minutes=2))
    assert tenant_limited.value.status_code == 429
    assert tenant_limited.value.headers["Retry-After"]

    # A busy IP can book with another tenant until the separate global bucket fills.
    platform._consume_public_booking_quota(test_db, 2, "192.0.2.10", now + timedelta(minutes=3))
    with pytest.raises(HTTPException) as ip_limited:
        platform._consume_public_booking_quota(test_db, 3, "192.0.2.10", now + timedelta(minutes=4))
    assert ip_limited.value.status_code == 429

    platform._consume_public_booking_quota(test_db, 1, "192.0.2.10", now + timedelta(hours=1, seconds=1))
