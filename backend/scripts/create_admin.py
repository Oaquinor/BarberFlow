"""Interactively create a super administrator in the configured MySQL database."""

import getpass
import sys

from sqlalchemy.exc import IntegrityError

from app.core.database import SessionLocal
from app.core.security import hash_password
from app.models import User


def create_super_admin() -> int:
    email = input("Email: ").strip().lower()
    first_name = input("First name: ").strip()
    last_name = input("Last name: ").strip()
    phone = input("Phone (optional): ").strip() or None
    password = getpass.getpass("Password (12+ characters, uppercase and number): ")
    password_confirm = getpass.getpass("Confirm password: ")
    if not email or len(first_name) < 2 or len(last_name) < 2:
        print("Email, first name and last name are required.")
        return 1
    if (
        len(password) < 12
        or len(password.encode("utf-8")) > 72
        or not any(char.isupper() for char in password)
        or not any(char.isdigit() for char in password)
    ):
        print("Use a password of 12–72 characters with an uppercase letter and a number.")
        return 1
    if password != password_confirm:
        print("Passwords do not match.")
        return 1

    db = SessionLocal()
    try:
        if db.query(User.id).filter(User.email == email, User.is_deleted == False).first():
            print("A user with that email already exists.")
            return 1
        admin = User(
            email=email,
            password_hash=hash_password(password),
            first_name=first_name,
            last_name=last_name,
            phone=phone,
            role="super_admin",
            is_active=True,
            is_verified=True,
        )
        db.add(admin)
        db.commit()
        print(f"Super administrator created: {email}")
        return 0
    except IntegrityError:
        db.rollback()
        print("A user with that email already exists.")
        return 1
    except Exception as exc:
        db.rollback()
        print(f"Could not create the administrator ({type(exc).__name__}). Check MySQL connectivity.")
        return 1
    finally:
        db.close()


if __name__ == "__main__":
    sys.exit(create_super_admin())
