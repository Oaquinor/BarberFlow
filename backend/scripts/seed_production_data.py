from datetime import datetime, timedelta

from app.core.database import SessionLocal
from app.core.security.password import hash_password
from app.models.barbershop import Barbershop
from app.models.user import User
from app.models.service import Service
from app.models.subscription import Subscription


def upsert_barbershop(db):
    shop = db.query(Barbershop).filter(Barbershop.id == 1).first()
    if not shop:
        shop = Barbershop(
            id=1,
            name="KingFlow Barber",
            slug="kingflow-barber",
            email="admin@kingflow.com",
            phone="18090000000",
            address_line1="Main St",
            city="Santo Domingo",
            state="Distrito Nacional",
            postal_code="00000",
            country="DO",
            primary_color="#667eea",
            secondary_color="#764ba2",
            onboarding_completed=False,
            is_active=True,
            is_verified=True,
            timezone="America/Santo_Domingo",
            currency="USD",
            appointment_duration_minutes=30,
        )
        db.add(shop)
        db.flush()

    if not shop.subscription_id:
        sub = Subscription(
            plan="professional",
            status="active",
            current_period_start=datetime.utcnow(),
            current_period_end=datetime.utcnow() + timedelta(days=30),
            max_barbers=10,
            max_appointments_per_month=1000,
            max_clients=2000,
            auto_renew=True,
            is_trial=False,
        )
        db.add(sub)
        db.flush()
        shop.subscription_id = sub.id

    return shop


def upsert_user(db, email, first_name, last_name, phone, role, barbershop_id, password):
    user = db.query(User).filter(User.email == email).first()
    if not user:
        user = User(
            email=email,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role=role,
            barbershop_id=barbershop_id,
            is_active=True,
            is_verified=True,
        )
        db.add(user)
    else:
        user.first_name = first_name
        user.last_name = last_name
        user.phone = phone
        user.role = role
        user.barbershop_id = barbershop_id
        user.is_active = True
        user.is_verified = True
        user.password_hash = hash_password(password)


def upsert_services(db, shop_id):
    base_services = [
        ("Corte Clásico", "Corte tradicional con acabado profesional", 30, 1500, "haircut"),
        ("Arreglo de Barba", "Perfilado y recorte de barba", 20, 1000, "beard"),
        ("Corte + Barba", "Servicio combinado premium", 45, 2500, "combo"),
    ]

    for index, (name, description, duration, price, category) in enumerate(base_services, start=1):
        existing = (
            db.query(Service)
            .filter(Service.barbershop_id == shop_id, Service.name == name, Service.is_deleted == False)
            .first()
        )
        if not existing:
            db.add(
                Service(
                    barbershop_id=shop_id,
                    name=name,
                    description=description,
                    duration_minutes=duration,
                    price=price,
                    category=category,
                    display_order=index,
                    is_active=True,
                )
            )


def main():
    db = SessionLocal()
    try:
        shop = upsert_barbershop(db)

        upsert_user(
            db,
            email="superadmin@kingflow.com",
            first_name="Super",
            last_name="Admin",
            phone="18091111111",
            role="super_admin",
            barbershop_id=None,
            password="Admin123A",
        )

        upsert_user(
            db,
            email="owner@kingflow.com",
            first_name="Owner",
            last_name="Barber",
            phone="18092222222",
            role="barbershop_owner",
            barbershop_id=shop.id,
            password="Owner123A",
        )

        upsert_user(
            db,
            email="barber@kingflow.com",
            first_name="Carlos",
            last_name="Barbero",
            phone="18093333333",
            role="barber",
            barbershop_id=shop.id,
            password="Barber123A",
        )

        upsert_services(db, shop.id)
        db.commit()
        print("OK: Datos productivos sembrados.")
    finally:
        db.close()


if __name__ == "__main__":
    main()
