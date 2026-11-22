"""
Database session management.

Handles database connections and session lifecycle.
"""

from typing import Generator

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker, Session, declarative_base

from app.core.config import get_settings

settings = get_settings()


def validate_database_url(database_url: str) -> str:
    """KingFlow's models and migrations target MySQL 8 only."""
    if not database_url.startswith("mysql+pymysql://"):
        raise RuntimeError("DATABASE_URL must use the MySQL PyMySQL driver")
    return database_url


# Create engine
engine = create_engine(
    validate_database_url(settings.DATABASE_URL),
    echo=settings.DEBUG,
    pool_size=settings.DATABASE_POOL_SIZE,
    max_overflow=settings.DATABASE_MAX_OVERFLOW,
    pool_pre_ping=True,
)

# Create session factory
SessionLocal = sessionmaker(
    bind=engine,
    autocommit=False,
    autoflush=False,
)

# Base class for models
Base = declarative_base()


def get_db() -> Generator[Session, None, None]:
    """
    Dependency for getting database session.

    Usage:
        @router.get("/items")
        def get_items(db: Session = Depends(get_db)):
            ...
    """
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def close_db() -> None:
    """Close database connections."""
    engine.dispose()
