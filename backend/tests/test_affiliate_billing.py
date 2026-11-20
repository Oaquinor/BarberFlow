"""MySQL integration coverage for referral attribution and subscription commissions."""

from datetime import datetime, timedelta

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.security import create_access_token
from app.models import Affiliate, Barbershop, Subscription, User
from app.utils.datetime import utc_now_naive


def test_saas_signup_attributes_valid_affiliate_code(client: TestClient, test_db: Session):
    affiliate = Affiliate(
        first_name="Referente", last_name="Uno", email="signup-affiliate@example.com",
        code="SIGNUP01", commission_rate=0.15, is_active=True, is_verified=True,
        total_referrals=0, active_referrals=0, total_commissions_earned=0, total_commissions_paid=0,
    )
    test_db.add(affiliate)
    test_db.commit()
    payload = {
        "owner_email": "referred-owner@example.com", "owner_password": "SecureOwner2026",
        "owner_first_name": "Owner", "owner_last_name": "Referred", "owner_phone": "8095554010",
        "barbershop_name": "Referred Shop", "barbershop_email": "referred-shop@example.com",
        "barbershop_phone": "8095554011", "address_line1": "Calle 40",
        "city": "Santo Domingo", "state": "DN", "postal_code": "10105",
        "country": "DO", "timezone": "America/Santo_Domingo", "currency": "DOP",
        "affiliate_code": "signup01",
    }
    registered = client.post("/api/v1/saas/register", json=payload)
    assert registered.status_code == 201
    shop = test_db.query(Barbershop).filter(Barbershop.id == registered.json()["user"]["barbershop_id"]).one()
    test_db.refresh(affiliate)
    assert shop.referred_by_affiliate_id == affiliate.id
    assert affiliate.total_referrals == 1
    assert affiliate.active_referrals == 1


def test_recorded_subscription_payment_creates_and_pays_referral_commission(
    client: TestClient, test_db: Session,
):
    now = utc_now_naive()
    subscription = Subscription(
        plan="basic", status="expired", current_period_start=now - timedelta(days=31),
        current_period_end=now - timedelta(days=1), max_barbers=3,
        max_appointments_per_month=200, max_clients=500, auto_renew=False,
    )
    test_db.add(subscription)
    affiliate = Affiliate(
        first_name="Afiliado", last_name="Prueba", email="billing-affiliate@example.com",
        code="BILLINGTEST", commission_rate=0.15, is_active=True, is_verified=True,
        total_referrals=1, active_referrals=1, total_commissions_earned=0, total_commissions_paid=0,
    )
    test_db.add(affiliate)
    admin = User(
        email="billing-superadmin@example.com", password_hash="unused", first_name="Admin",
        last_name="Billing", role="super_admin", is_active=True,
    )
    test_db.add_all([admin])
    test_db.flush()
    shop = Barbershop(
        name="Affiliate Billing", slug="affiliate-billing-test", email="affiliate-shop@example.com",
        phone="8095554000", address_line1="Calle 30", city="Santo Domingo", state="DN",
        postal_code="10104", country="DO", timezone="America/Santo_Domingo", currency="DOP",
        subscription_id=subscription.id, referred_by_affiliate_id=affiliate.id,
    )
    test_db.add(shop)
    test_db.commit()

    assert client.get(f"/api/v1/public/{shop.slug}").status_code == 402

    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin.id), 'role': 'super_admin'})}"}
    body = {
        "amount_cents": 10000,
        "method": "card",
        "reference": "external-receipt-001",
        "period_start": (now - timedelta(days=1)).isoformat(),
        "period_end": (now + timedelta(days=29)).isoformat(),
    }
    payment = client.post(
        f"/api/v1/admin/tenants/{shop.id}/subscription/payments", headers=headers, json=body
    )
    assert payment.status_code == 201
    assert payment.json()["commission_id"] is not None
    assert payment.json()["subscription_status"] == "active"
    assert client.get(f"/api/v1/public/{shop.slug}").status_code == 200
    test_db.refresh(affiliate)
    assert affiliate.total_commissions_earned == 1500

    duplicate = client.post(
        f"/api/v1/admin/tenants/{shop.id}/subscription/payments", headers=headers, json=body
    )
    assert duplicate.status_code == 409

    commission_id = payment.json()["commission_id"]
    approved = client.post(f"/api/v1/admin/commissions/{commission_id}/approve", headers=headers)
    assert approved.status_code == 200
    paid = client.post(
        f"/api/v1/admin/commissions/{commission_id}/pay",
        headers=headers,
        json={"payment_method": "bank_transfer", "payment_reference": "affiliate-transfer-01"},
    )
    assert paid.status_code == 200
    test_db.refresh(affiliate)
    assert affiliate.total_commissions_paid == 1500
