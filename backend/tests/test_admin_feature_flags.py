"""MySQL integration tests for observable super-admin feature controls."""

from datetime import timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Barbershop, Subscription, User
from app.utils.datetime import utc_now_naive


def _headers(user: User) -> dict[str, str]:
    return {"Authorization": f"Bearer {create_access_token({'sub': str(user.id), 'role': user.role})}"}


def test_branding_feature_state_is_returned_and_consumed_by_user_session(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="free", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=2,
        max_appointments_per_month=50, max_clients=100, auto_renew=False,
    )
    test_db.add(subscription)
    test_db.flush()
    shop = Barbershop(
        name="Brand Feature", slug="brand-feature-test", email="brand-shop@example.com",
        phone="8095556100", address_line1="Calle 21", city="Santo Domingo", state="DN",
        postal_code="10106", country="DO", timezone="America/Santo_Domingo", currency="DOP",
        subscription_id=subscription.id, onboarding_completed=True,
        primary_color="#123456", secondary_color="#654321",
    )
    test_db.add(shop)
    test_db.flush()
    admin = User(
        email="brand-admin@example.com", password_hash="unused", first_name="Admin",
        last_name="Platform", role="super_admin", is_active=True,
    )
    barber = User(
        email="brand-barber@example.com", password_hash="unused", first_name="Barber",
        last_name="Brand", role="barber", is_active=True, barbershop_id=shop.id,
    )
    test_db.add_all([admin, barber])
    test_db.commit()

    overview = client.get("/api/v1/admin/overview", headers=_headers(admin))
    assert overview.status_code == 200
    assert overview.json()["tenant_count"] == 1
    assert overview.json()["active_tenant_count"] == 1
    assert overview.json()["active_subscription_count"] == 1
    assert overview.json()["active_user_count"] == 2
    assert overview.json()["collected_this_month_by_currency"] == []
    assert client.get("/api/v1/admin/overview", headers=_headers(barber)).status_code == 403

    listed = client.get(f"/api/v1/admin/users?barbershop_id={shop.id}", headers=_headers(admin))
    assert listed.status_code == 200
    item = next(row for row in listed.json()["items"] if row["id"] == barber.id)
    assert item["feature_flags"] == {}

    enabled = client.put(
        f"/api/v1/admin/users/{barber.id}/features", headers=_headers(admin),
        json={"feature_key": "branding_auto", "enabled": True},
    )
    assert enabled.status_code == 200
    assert enabled.json()["enabled"] is True

    listed_again = client.get(f"/api/v1/admin/users?barbershop_id={shop.id}", headers=_headers(admin))
    updated = next(row for row in listed_again.json()["items"] if row["id"] == barber.id)
    assert updated["feature_flags"] == {"branding_auto": True}
    session_user = client.get("/api/v1/auth/me", headers=_headers(barber))
    assert session_user.status_code == 200
    assert session_user.json()["feature_flags"] == {"branding_auto": True}

    unsupported = client.put(
        f"/api/v1/admin/users/{barber.id}/features", headers=_headers(admin),
        json={"feature_key": "imaginary_feature", "enabled": True},
    )
    assert unsupported.status_code == 422


def test_super_admin_user_list_supports_tenant_scoped_search_and_pagination(
    client: TestClient, test_db: Session,
):
    shop = Barbershop(
        name="User paging", slug="admin-user-paging", email="paging-shop@example.com",
        phone="8095556101", address_line1="Calle 22", city="Santo Domingo",
        state="DN", postal_code="10107", country="DO", timezone="America/Santo_Domingo",
    )
    test_db.add(shop)
    test_db.flush()
    other_shop = Barbershop(
        name="Other tenant", slug="admin-user-paging-other", email="paging-other-shop@example.com",
        phone="8095556102", address_line1="Calle 23", city="Santo Domingo",
        state="DN", postal_code="10108", country="DO", timezone="America/Santo_Domingo",
    )
    test_db.add(other_shop)
    test_db.flush()
    admin = User(
        email="paging-admin@example.com", password_hash="unused", first_name="Admin",
        last_name="Paging", role="super_admin", is_active=True,
    )
    matches = [
        User(email=f"paging-match-{index}@example.com", password_hash="unused",
             first_name=name, last_name="Needle", role="barber", is_active=True,
             barbershop_id=shop.id)
        for index, name in enumerate(("Ada", "Grace"), start=1)
    ]
    other = User(
        email="paging-other@example.com", password_hash="unused", first_name="Linus",
        last_name="Other", role="barber", is_active=True, barbershop_id=shop.id,
    )
    cross_tenant_match = User(
        email="paging-cross-tenant@example.com", password_hash="unused", first_name="Margaret",
        last_name="Needle", role="barber", is_active=True, barbershop_id=other_shop.id,
    )
    test_db.add_all([admin, *matches, other, cross_tenant_match])
    test_db.commit()

    url = f"/api/v1/admin/users?barbershop_id={shop.id}&search=Needle&limit=1"
    first = client.get(url, headers=_headers(admin))
    second = client.get(f"{url}&offset=1", headers=_headers(admin))
    assert first.status_code == second.status_code == 200
    assert first.json()["total"] == second.json()["total"] == 2
    assert first.json()["offset"] == 0 and first.json()["limit"] == 1
    assert second.json()["offset"] == 1 and second.json()["limit"] == 1
    assert first.json()["items"][0]["id"] != second.json()["items"][0]["id"]

    beyond = client.get(f"{url}&offset=2", headers=_headers(admin))
    assert beyond.json()["items"] == []
    assert beyond.json()["total"] == 2


def test_super_admin_tenant_list_includes_owner_and_subscription_without_dropping_empty_tenants(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="professional", status="active", current_period_start=now - timedelta(days=1),
        current_period_end=now + timedelta(days=29), max_barbers=10,
        max_appointments_per_month=1000, max_clients=2000,
    )
    test_db.add(subscription)
    test_db.flush()
    subscribed_shop = Barbershop(
        name="Subscribed tenant", slug="admin-subscribed-tenant",
        email="admin-subscribed@example.com", phone="8095556103", address_line1="Calle 24",
        city="Santo Domingo", state="DN", postal_code="10109", country="DO",
        timezone="America/Santo_Domingo", subscription_id=subscription.id,
    )
    empty_shop = Barbershop(
        name="Tenant without owner or subscription", slug="admin-empty-tenant",
        email="admin-empty@example.com", phone="8095556104", address_line1="Calle 25",
        city="Santo Domingo", state="DN", postal_code="10110", country="DO",
        timezone="America/Santo_Domingo",
    )
    admin = User(
        email="tenant-list-admin@example.com", password_hash="unused", first_name="Admin",
        last_name="Tenants", role="super_admin", is_active=True,
    )
    owner = User(
        email="tenant-list-owner@example.com", password_hash="unused", first_name="Tenant",
        last_name="Owner", role="barbershop_owner", is_active=True,
        barbershop_id=subscribed_shop.id,
    )
    test_db.add_all([subscribed_shop, empty_shop, admin])
    test_db.flush()
    owner.barbershop_id = subscribed_shop.id
    test_db.add(owner)
    test_db.commit()

    response = client.get("/api/v1/admin/tenants", headers=_headers(admin))
    assert response.status_code == 200
    tenants = {row["barbershop_id"]: row for row in response.json()["items"]}
    assert tenants[subscribed_shop.id]["owner_email"] == owner.email
    assert tenants[subscribed_shop.id]["plan"] == "professional"
    assert tenants[subscribed_shop.id]["subscription_status"] == "active"
    assert tenants[empty_shop.id]["owner_email"] is None
    assert tenants[empty_shop.id]["plan"] is None
    assert tenants[empty_shop.id]["subscription_status"] is None
