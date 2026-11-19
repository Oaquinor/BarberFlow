"""MySQL integration tests for tenant-scoped logo storage and audit history."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import AuditLog, Barbershop, Subscription, User
from app.utils.datetime import utc_now_naive


PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _create_owner(test_db: Session) -> tuple[Barbershop, User]:
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=1,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Logo Shop", slug="logo-shop-test", email="logo-shop@example.com",
        phone="8095553090", address_line1="Calle 90", city="Santo Domingo",
        state="DN", postal_code="10109", country="DO",
        timezone="America/Santo_Domingo", currency="DOP", subscription_id=subscription.id,
    )
    test_db.add(shop)
    test_db.flush()
    owner = User(
        email="logo-owner@example.com", password_hash="unused", first_name="Logo",
        last_name="Owner", role="barbershop_owner", is_active=True,
        barbershop_id=shop.id,
    )
    test_db.add(owner)
    test_db.commit()
    return shop, owner


def test_owner_logo_replacement_is_tenant_scoped_and_audited(
    client: TestClient, test_db: Session, monkeypatch, tmp_path,
):
    import app.api.v1.endpoints.onboarding as onboarding

    shop, owner = _create_owner(test_db)
    owner_headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"
    }
    upload_root = tmp_path / "barbershops"
    monkeypatch.setattr(onboarding, "UPLOAD_ROOT", upload_root)

    tenant_dir = upload_root / str(shop.id)
    tenant_dir.mkdir(parents=True)
    previous_file = tenant_dir / "old.png"
    previous_file.write_bytes(PNG_HEADER + b"old")
    shop.logo_url = f"/uploads/barbershops/{shop.id}/old.png"
    test_db.commit()

    response = client.post(
        "/api/v1/onboarding/upload-logo",
        headers=owner_headers,
        files={"file": ("logo.png", PNG_HEADER + b"new", "image/png")},
    )
    assert response.status_code == 200
    logo_url = response.json()["logo_url"]
    new_file = tenant_dir / logo_url.rsplit("/", 1)[1]
    assert new_file.read_bytes() == PNG_HEADER + b"new"
    assert not previous_file.exists()
    assert test_db.get(Barbershop, shop.id).logo_url == logo_url

    audit = test_db.query(AuditLog).filter_by(
        action="barbershop.logo_updated", entity_id=shop.id, barbershop_id=shop.id,
    ).one()
    assert audit.actor_user_id == owner.id
    assert audit.details == {
        "previous_logo_url": f"/uploads/barbershops/{shop.id}/old.png",
        "logo_url": logo_url,
    }

    foreign = client.post(
        f"/api/v1/onboarding/upload-logo?barbershop_id={shop.id + 100}",
        headers=owner_headers,
        files={"file": ("logo.png", PNG_HEADER + b"foreign", "image/png")},
    )
    assert foreign.status_code == 403


def test_logo_upload_rejects_wrong_content_type_and_oversized_payload(
    client: TestClient, test_db: Session, monkeypatch, tmp_path,
):
    import app.api.v1.endpoints.onboarding as onboarding

    _, owner = _create_owner(test_db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    monkeypatch.setattr(onboarding, "UPLOAD_ROOT", tmp_path / "barbershops")

    invalid = client.post(
        "/api/v1/onboarding/upload-logo", headers=headers,
        files={"file": ("logo.png", b"not an image", "image/png")},
    )
    assert invalid.status_code == 400

    too_large = client.post(
        "/api/v1/onboarding/upload-logo", headers=headers,
        files={"file": ("logo.png", PNG_HEADER + b"x" * get_settings().MAX_UPLOAD_SIZE, "image/png")},
    )
    assert too_large.status_code == 413
