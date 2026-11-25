"""MySQL integration coverage for customer-owned style records and photos."""

from datetime import timedelta
from io import BytesIO

from fastapi.testclient import TestClient
from PIL import Image
from sqlalchemy.orm import Session

from app.api.v1 import style_passport as passport_api
from app.core.security import create_access_token
from app.models import (
    Appointment,
    Barbershop,
    ClientAccountShopLink,
    Service,
    StylePassportEntry,
    StylePassportPhoto,
    Subscription,
    User,
)
from app.utils.datetime import utc_now_naive


def _style_passport_context(db: Session):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free",
        status="active",
        current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29),
        max_barbers=4,
        max_appointments_per_month=100,
        max_clients=100,
        auto_renew=False,
    )
    shop = Barbershop(
        name="Style Passport Test",
        slug="style-passport-test",
        email="style-shop@example.com",
        phone="8095550123",
        address_line1="Calle 1",
        city="Santo Domingo",
        state="DN",
        postal_code="10101",
        country="DO",
        timezone="America/Santo_Domingo",
        currency="DOP",
        subscription=subscription,
    )
    owner = User(
        email="style-owner@example.com",
        password_hash="unused",
        first_name="Dueño",
        last_name="Prueba",
        role="barbershop_owner",
        is_active=True,
        barbershop=shop,
    )
    barber = User(
        email="style-barber@example.com",
        password_hash="unused",
        first_name="Luis",
        last_name="Barbero",
        role="barber",
        is_active=True,
        barbershop=shop,
    )
    crm_client = User(
        email="style-crm@client.invalid",
        password_hash="unused",
        first_name="Ana",
        last_name="Cliente",
        role="client",
        is_active=True,
        barbershop=shop,
    )
    account = User(
        email="style-account@example.com",
        password_hash="unused",
        first_name="Ana",
        last_name="Cliente",
        role="client",
        is_active=True,
        is_verified=True,
        barbershop_id=None,
    )
    other_account = User(
        email="style-other@example.com",
        password_hash="unused",
        first_name="Otra",
        last_name="Cuenta",
        role="client",
        is_active=True,
        is_verified=True,
        barbershop_id=None,
    )
    service = Service(
        barbershop=shop,
        name="Corte clásico",
        duration_minutes=30,
        price=25000,
        category="haircut",
        is_active=True,
    )
    db.add_all([shop, owner, barber, crm_client, account, other_account, service])
    db.flush()
    appointment = Appointment(
        barbershop_id=shop.id,
        client_id=crm_client.id,
        barber_id=barber.id,
        scheduled_time=now - timedelta(days=2),
        actual_start_time=now - timedelta(days=2, minutes=30),
        actual_end_time=now - timedelta(days=2),
        estimated_duration=30,
        service_type=service.name,
        service_price=service.price,
        status="completed",
    )
    upcoming = Appointment(
        barbershop_id=shop.id,
        client_id=crm_client.id,
        barber_id=barber.id,
        scheduled_time=now + timedelta(days=2),
        estimated_duration=30,
        service_type=service.name,
        service_price=service.price,
        status="confirmed",
    )
    db.add_all([appointment, upcoming])
    db.add(
        ClientAccountShopLink(
            account_user_id=account.id,
            barbershop_id=shop.id,
            crm_client_user_id=crm_client.id,
        )
    )
    db.commit()
    return shop, owner, barber, crm_client, account, other_account, service, appointment, upcoming


def _auth(user: User) -> dict[str, str]:
    token = create_access_token({"sub": str(user.id), "role": user.role})
    return {"Authorization": f"Bearer {token}"}


def _jpeg_upload() -> bytes:
    output = BytesIO()
    Image.new("RGB", (24, 24), (135, 98, 64)).save(output, format="JPEG")
    return output.getvalue()


def test_style_passport_requires_completed_owned_appointment_and_is_consent_gated(
    client: TestClient,
    test_db: Session,
):
    shop, owner, barber, crm, account, other, _service, appointment, upcoming = (
        _style_passport_context(test_db)
    )
    headers = _auth(account)

    denied_upcoming = client.post(
        "/api/v1/client-account/style-passport",
        headers=headers,
        json={"appointment_id": upcoming.id, "haircut_type": "Crop"},
    )
    assert denied_upcoming.status_code == 404
    denied_foreign = client.post(
        "/api/v1/client-account/style-passport",
        headers=_auth(other),
        json={"appointment_id": appointment.id, "haircut_type": "Crop"},
    )
    assert denied_foreign.status_code == 404

    created = client.post(
        "/api/v1/client-account/style-passport",
        headers=headers,
        json={
            "appointment_id": appointment.id,
            "haircut_type": "Textured crop",
            "fade_style": "Low fade",
            "top_length": "Keep the top longer",
            "products_used": "Matte clay",
            "preferences": "Ask before trimming the fringe",
        },
    )
    assert created.status_code == 201, created.text
    entry = created.json()
    assert entry["share_with_shop"] is False
    assert entry["service"] == "Corte clásico"
    assert entry["service_id"] is not None
    assert entry["barber"] == "Luis Barbero"
    assert (
        client.get(
            "/api/v1/client-account/style-passport",
            headers=headers,
        ).headers["cache-control"]
        == "private, no-store, max-age=0"
    )
    assert (
        client.post(
            "/api/v1/client-account/style-passport",
            headers=headers,
            json={"appointment_id": appointment.id},
        ).status_code
        == 409
    )

    owner_url = f"/api/v1/owner/clients/{crm.id}/style-passport"
    private = client.get(owner_url, headers=_auth(owner))
    assert private.status_code == 200
    assert private.json()["items"] == []
    assert private.headers["cache-control"] == "private, no-store, max-age=0"

    shared = client.patch(
        f"/api/v1/client-account/style-passport/{entry['id']}",
        headers=headers,
        json={"share_with_shop": True},
    )
    assert shared.status_code == 200, shared.text
    assert shared.json()["share_consent_updated_at"]
    team_view = client.get(owner_url, headers=_auth(barber))
    assert team_view.status_code == 200
    assert len(team_view.json()["items"]) == 1
    assert team_view.json()["items"][0]["preferences"] == "Ask before trimming the fringe"

    staff_update = client.patch(
        f"{owner_url}/{entry['id']}",
        headers=_auth(barber),
        json={"barber_notes": "Use a guard 2 on the sides", "recommendations": "Return in 3 weeks"},
    )
    assert staff_update.status_code == 200, staff_update.text
    assert staff_update.json()["barber_notes"] == "Use a guard 2 on the sides"
    assert (
        "barber_notes"
        not in client.get(
            f"/api/v1/client-account/style-passport/{entry['id']}",
            headers=headers,
        ).json()
    )

    revoked = client.patch(
        f"/api/v1/client-account/style-passport/{entry['id']}",
        headers=headers,
        json={"share_with_shop": False},
    )
    assert revoked.status_code == 200
    assert client.get(owner_url, headers=_auth(owner)).json()["items"] == []
    assert (
        client.patch(
            f"{owner_url}/{entry['id']}",
            headers=_auth(owner),
            json={"recommendations": "No longer authorized"},
        ).status_code
        == 404
    )
    assert (
        test_db.query(StylePassportEntry).filter_by(id=entry["id"]).one().share_with_shop is False
    )


def test_style_passport_private_photos_are_sanitized_protected_and_removed(
    client: TestClient,
    test_db: Session,
    monkeypatch,
    tmp_path,
):
    shop, owner, barber, crm, account, other, _service, appointment, _upcoming = (
        _style_passport_context(test_db)
    )
    monkeypatch.setattr(passport_api, "PRIVATE_UPLOAD_ROOT", tmp_path / "private")
    headers = _auth(account)
    created = client.post(
        "/api/v1/client-account/style-passport",
        headers=headers,
        json={
            "appointment_id": appointment.id,
            "haircut_type": "Buzz cut",
            "share_with_shop": True,
        },
    )
    assert created.status_code == 201, created.text
    entry_id = created.json()["id"]
    content = _jpeg_upload()
    uploaded = client.post(
        f"/api/v1/client-account/style-passport/{entry_id}/photos?photo_kind=reference",
        headers=headers,
        files={"file": ("reference.jpg", content, "image/jpeg")},
    )
    assert uploaded.status_code == 201, uploaded.text
    photo = uploaded.json()
    path = tmp_path / "private" / str(account.id)
    file_path = path / next(path.iterdir()).name
    assert file_path.exists()
    assert (
        client.get(
            f"/uploads/private/style-passport/{account.id}/{file_path.name}",
        ).status_code
        == 404
    )

    owner_photo = client.get(
        f"/api/v1/owner/clients/{crm.id}/style-passport/{entry_id}/photos/{photo['id']}",
        headers=_auth(owner),
    )
    assert owner_photo.status_code == 200
    assert owner_photo.headers["cache-control"] == "private, no-store, max-age=0"
    assert owner_photo.headers["x-content-type-options"] == "nosniff"
    assert owner_photo.headers["content-type"] == "image/jpeg"
    assert (
        client.get(
            f"/api/v1/owner/clients/{crm.id}/style-passport/{entry_id}/photos/{photo['id']}",
            headers=_auth(barber),
        ).status_code
        == 200
    )
    assert (
        client.get(
            f"/api/v1/client-account/style-passport/{entry_id}/photos/{photo['id']}",
            headers=_auth(other),
        ).status_code
        == 404
    )

    revoked = client.patch(
        f"/api/v1/client-account/style-passport/{entry_id}",
        headers=headers,
        json={"share_with_shop": False},
    )
    assert revoked.status_code == 200
    assert (
        client.get(
            f"/api/v1/owner/clients/{crm.id}/style-passport/{entry_id}/photos/{photo['id']}",
            headers=_auth(owner),
        ).status_code
        == 404
    )
    own_photo = client.get(
        f"/api/v1/client-account/style-passport/{entry_id}/photos/{photo['id']}",
        headers=headers,
    )
    assert own_photo.status_code == 200

    removed = client.delete(
        f"/api/v1/client-account/style-passport/{entry_id}/photos/{photo['id']}",
        headers=headers,
    )
    assert removed.status_code == 200
    assert not file_path.exists()
    assert test_db.query(StylePassportPhoto).filter_by(id=photo["id"]).one().is_deleted is True
    assert (
        client.get(
            f"/api/v1/client-account/style-passport/{entry_id}/photos/{photo['id']}",
            headers=headers,
        ).status_code
        == 404
    )


def test_style_passport_upload_rejects_invalid_media_and_excess_photos(
    client: TestClient,
    test_db: Session,
    monkeypatch,
    tmp_path,
):
    _shop, _owner, _barber, _crm, account, _other, _service, appointment, _upcoming = (
        _style_passport_context(test_db)
    )
    monkeypatch.setattr(passport_api, "PRIVATE_UPLOAD_ROOT", tmp_path / "private")
    headers = _auth(account)
    created = client.post(
        "/api/v1/client-account/style-passport",
        headers=headers,
        json={"appointment_id": appointment.id},
    )
    entry_id = created.json()["id"]
    url = f"/api/v1/client-account/style-passport/{entry_id}/photos?photo_kind=reference"
    invalid = client.post(
        url,
        headers=headers,
        files={"file": ("text.jpg", b"not an image", "image/jpeg")},
    )
    assert invalid.status_code == 400
    image = _jpeg_upload()
    assert (
        client.post(
            url, headers=headers, files={"file": ("one.jpg", image, "image/jpeg")}
        ).status_code
        == 201
    )
    assert (
        client.post(
            url, headers=headers, files={"file": ("two.jpg", image, "image/jpeg")}
        ).status_code
        == 201
    )
    exceeded = client.post(url, headers=headers, files={"file": ("three.jpg", image, "image/jpeg")})
    assert exceeded.status_code == 409
    assert (
        test_db.query(StylePassportPhoto).filter_by(entry_id=entry_id, is_deleted=False).count()
        == 2
    )
