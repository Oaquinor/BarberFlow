"""MySQL integration coverage for referral attribution and subscription commissions."""

from concurrent.futures import ThreadPoolExecutor
from datetime import timedelta
from uuid import uuid4

from fastapi.testclient import TestClient
from sqlalchemy.orm import Session

from app.core.database import get_db
from app.core.security import create_access_token
from app.main import app
from app.models import (
    Affiliate, AuditLog, Barbershop, Commission, Subscription, SubscriptionPayment, User,
)
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


def test_concurrent_subscription_payments_record_one_charge_and_commission(mysql_test_engine):
    suffix = uuid4().hex
    now = utc_now_naive().replace(microsecond=0)
    period_start = now - timedelta(days=1)
    period_end = now + timedelta(days=29)
    with Session(mysql_test_engine) as db:
        subscription = Subscription(
            plan="basic", status="expired", current_period_start=now - timedelta(days=31),
            current_period_end=now - timedelta(days=1), max_barbers=3,
            max_appointments_per_month=200, max_clients=500, auto_renew=False,
        )
        affiliate = Affiliate(
            first_name="Afiliado", last_name="Concurrencia",
            email=f"billing-race-{suffix}@example.com", code=f"RACE{suffix[:12]}",
            commission_rate=0.15, is_active=True, is_verified=True,
            total_referrals=1, active_referrals=1, total_commissions_earned=0,
            total_commissions_paid=0,
        )
        admin = User(
            email=f"billing-race-admin-{suffix}@example.com", password_hash="unused",
            first_name="Admin", last_name="Race", role="super_admin", is_active=True,
        )
        db.add_all([subscription, affiliate, admin])
        db.flush()
        shop = Barbershop(
            name="Subscription Payment Race", slug=f"billing-race-{suffix}",
            email=f"billing-race-shop-{suffix}@example.com", phone="8095554099",
            address_line1="Test", city="Santo Domingo", state="DN", postal_code="10109",
            country="DO", timezone="America/Santo_Domingo", currency="DOP",
            subscription_id=subscription.id, referred_by_affiliate_id=affiliate.id,
        )
        db.add(shop)
        db.commit()
        shop_id, subscription_id = shop.id, subscription.id
        affiliate_id, admin_id = affiliate.id, admin.id

    def override_get_db():
        with Session(mysql_test_engine) as db:
            yield db

    app.dependency_overrides[get_db] = override_get_db
    headers = {"Authorization": f"Bearer {create_access_token({'sub': str(admin_id)})}"}
    payload = {
        "amount_cents": 10000,
        "method": "bank_transfer",
        "reference": f"external-race-{suffix}",
        "period_start": period_start.isoformat(),
        "period_end": period_end.isoformat(),
    }

    def record_once():
        with TestClient(app) as client:
            return client.post(
                f"/api/v1/admin/tenants/{shop_id}/subscription/payments",
                headers=headers,
                json=payload,
            )

    try:
        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(lambda _index: record_once(), range(2)))

        assert sorted(response.status_code for response in responses) == [201, 409]
        with Session(mysql_test_engine) as db:
            assert db.query(SubscriptionPayment).filter(
                SubscriptionPayment.subscription_id == subscription_id,
                SubscriptionPayment.period_start == period_start,
                SubscriptionPayment.period_end == period_end,
            ).count() == 1
            assert db.query(Commission).filter(
                Commission.subscription_id == subscription_id,
                Commission.period_start == period_start,
                Commission.period_end == period_end,
            ).count() == 1
            persisted_subscription = db.get(Subscription, subscription_id)
            assert persisted_subscription.status == "active"
            assert persisted_subscription.current_period_end == period_end
            assert db.get(Affiliate, affiliate_id).total_commissions_earned == 1500
    finally:
        app.dependency_overrides.clear()
        with Session(mysql_test_engine) as db:
            db.query(Commission).filter(Commission.subscription_id == subscription_id).delete(
                synchronize_session=False,
            )
            db.query(SubscriptionPayment).filter(
                SubscriptionPayment.subscription_id == subscription_id,
            ).delete(synchronize_session=False)
            db.query(AuditLog).filter(AuditLog.barbershop_id == shop_id).delete(
                synchronize_session=False,
            )
            db.query(Barbershop).filter(Barbershop.id == shop_id).delete(synchronize_session=False)
            db.query(Subscription).filter(Subscription.id == subscription_id).delete(
                synchronize_session=False,
            )
            db.query(User).filter(User.id == admin_id).delete(synchronize_session=False)
            db.query(Affiliate).filter(Affiliate.id == affiliate_id).delete(synchronize_session=False)
            db.commit()
