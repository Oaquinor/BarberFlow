"""MySQL integration coverage for onboarding tenant selection."""

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Barbershop, User


def test_owner_cannot_read_another_tenants_onboarding_profile(
    client: TestClient, test_db: Session,
):
    shops = [
        Barbershop(
            name=f"Onboarding Tenant {index}",
            slug=f"onboarding-tenant-{index}",
            email=f"onboarding-tenant-{index}@example.com",
            phone=f"80955500{index:02d}",
            address_line1="Calle Principal 1",
            city="Santo Domingo",
            state="DN",
            postal_code="10101",
            country="DO",
            timezone="America/Santo_Domingo",
            currency="DOP",
        )
        for index in (1, 2)
    ]
    test_db.add_all(shops)
    test_db.flush()
    owner = User(
        email="onboarding-tenant-owner@example.com",
        password_hash="unused",
        first_name="Dueño",
        last_name="Tenant",
        role="barbershop_owner",
        is_active=True,
        barbershop_id=shops[0].id,
    )
    test_db.add(owner)
    test_db.commit()

    headers = {
        "Authorization": f"Bearer {create_access_token({'sub': str(owner.id), 'role': owner.role})}"
    }
    own_profile = client.get(
        f"/api/v1/onboarding/profile?barbershop_id={shops[0].id}", headers=headers,
    )
    assert own_profile.status_code == 200
    assert own_profile.json()["id"] == shops[0].id

    foreign_profile = client.get(
        f"/api/v1/onboarding/profile?barbershop_id={shops[1].id}", headers=headers,
    )
    assert foreign_profile.status_code == 403
    assert "barbería" in foreign_profile.json()["detail"].lower()
