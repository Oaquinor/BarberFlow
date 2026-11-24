"""MySQL integration tests for tenant-scoped logo storage and audit history."""

from datetime import timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.core.config import get_settings
from app.core.security import create_access_token
from app.models import AuditLog, Barbershop, Service, Subscription, User
from app.utils.datetime import utc_now_naive

PNG_HEADER = b"\x89PNG\r\n\x1a\n"


def _image_bytes(image_format: str = "PNG") -> bytes:
    output = BytesIO()
    mode = "RGBA" if image_format == "PNG" else "RGB"
    color = (40, 90, 160, 180) if image_format == "PNG" else (40, 90, 160)
    Image.new(mode, (2, 2), color).save(output, format=image_format)
    return output.getvalue()


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
    previous_file.write_bytes(_image_bytes())
    shop.logo_url = f"/uploads/barbershops/{shop.id}/old.png"
    test_db.commit()

    response = client.post(
        "/api/v1/onboarding/upload-logo",
        headers=owner_headers,
        files={"file": ("logo.png", _image_bytes(), "image/png")},
    )
    assert response.status_code == 200
    logo_url = response.json()["logo_url"]
    new_file = tenant_dir / logo_url.rsplit("/", 1)[1]
    with Image.open(new_file) as saved_logo:
        assert saved_logo.format == "PNG"
        assert saved_logo.size == (2, 2)
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
        files={"file": ("logo.png", _image_bytes(), "image/png")},
    )
    assert foreign.status_code == 403


def test_logo_replacement_succeeds_when_old_file_cleanup_fails(
    client: TestClient, test_db: Session, monkeypatch, tmp_path,
):
    from pathlib import Path

    import app.api.v1.endpoints.onboarding as onboarding

    shop, owner = _create_owner(test_db)
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    upload_root = tmp_path / "barbershops"
    monkeypatch.setattr(onboarding, "UPLOAD_ROOT", upload_root)
    tenant_dir = upload_root / str(shop.id)
    tenant_dir.mkdir(parents=True)
    previous_file = tenant_dir / "old.png"
    previous_file.write_bytes(_image_bytes())
    shop.logo_url = f"/uploads/barbershops/{shop.id}/old.png"
    test_db.commit()

    original_unlink = Path.unlink

    def unlink_with_old_file_error(path, *args, **kwargs):
        if path == previous_file:
            raise PermissionError("old logo is temporarily locked")
        return original_unlink(path, *args, **kwargs)

    monkeypatch.setattr(Path, "unlink", unlink_with_old_file_error)
    response = client.post(
        "/api/v1/onboarding/upload-logo", headers=headers,
        files={"file": ("replacement.png", _image_bytes(), "image/png")},
    )

    assert response.status_code == 200
    test_db.refresh(shop)
    assert shop.logo_url == response.json()["logo_url"]
    assert (tenant_dir / response.json()["logo_url"].rsplit("/", 1)[1]).is_file()
    assert previous_file.is_file()


def test_owner_gallery_is_public_and_removing_a_photo_clears_service_reference(
    client: TestClient, test_db: Session, monkeypatch, tmp_path,
):
    import app.api.v1.endpoints.onboarding as onboarding

    shop, owner = _create_owner(test_db)
    shop.description = "Cortes a tu medida"
    test_db.commit()
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(owner.id)})}"}
    upload_root = tmp_path / "barbershops"
    monkeypatch.setattr(onboarding, "UPLOAD_ROOT", upload_root)

    uploaded = client.post(
        "/api/v1/onboarding/upload-gallery-image", headers=headers,
        files={"file": ("fade.png", _image_bytes(), "image/png")},
    )
    assert uploaded.status_code == 200
    image_url = uploaded.json()["gallery_images"][0]
    image_path = upload_root / str(shop.id) / image_url.rsplit("/", 1)[1]
    assert image_path.is_file()

    public_profile = client.get(f"/api/v1/public/{shop.slug}")
    assert public_profile.status_code == 200
    assert public_profile.json()["description"] == "Cortes a tu medida"
    assert public_profile.json()["gallery_images"] == [image_url]

    service = Service(
        barbershop_id=shop.id, name="Fade", duration_minutes=30,
        price=2000, category="haircut", image_url=image_url,
    )
    test_db.add(service)
    test_db.commit()
    removed = client.delete(
        "/api/v1/onboarding/gallery-image",
        params={"image_url": image_url}, headers=headers,
    )
    assert removed.status_code == 200
    assert removed.json()["gallery_images"] == []
    test_db.refresh(service)
    assert service.image_url is None
    assert not image_path.exists()

    foreign = client.delete(
        "/api/v1/onboarding/gallery-image",
        params={"barbershop_id": shop.id + 100, "image_url": image_url},
        headers=headers,
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
        files={"file": ("logo.png", PNG_HEADER + b"not a valid PNG", "image/png")},
    )
    assert invalid.status_code == 400

    mismatched_format = client.post(
        "/api/v1/onboarding/upload-logo", headers=headers,
        files={"file": ("logo.jpg", _image_bytes("PNG"), "image/jpeg")},
    )
    assert mismatched_format.status_code == 400

    import app.api.v1.endpoints.onboarding as onboarding
    monkeypatch.setattr(onboarding, "MAX_LOGO_PIXELS", 1)
    oversized_dimensions = client.post(
        "/api/v1/onboarding/upload-logo", headers=headers,
        files={"file": ("logo.png", _image_bytes(), "image/png")},
    )
    assert oversized_dimensions.status_code == 400

    too_large = client.post(
        "/api/v1/onboarding/upload-logo", headers=headers,
        files={"file": ("logo.png", PNG_HEADER + b"x" * get_settings().MAX_UPLOAD_SIZE, "image/png")},
    )
    assert too_large.status_code == 413
