"""Fixtures for integration tests against an explicitly named MySQL test database."""

import os
from collections.abc import Generator

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker

import app.models  # noqa: F401 - register all mapped tables with Base.metadata
from app.core.database import Base, get_db
from app.main import app


@pytest.fixture(scope="session")
def mysql_test_engine():
    url = os.environ.get("TEST_DATABASE_URL")
    if not url:
        pytest.skip("Set TEST_DATABASE_URL to a dedicated MySQL database ending in _test")
    if not url.startswith("mysql+pymysql://"):
        pytest.fail("TEST_DATABASE_URL must use mysql+pymysql")
    if not url.partition("/")[2].split("?", 1)[0].endswith("_test"):
        pytest.fail("Refusing to create or drop schema unless the MySQL database name ends in _test")

    engine = create_engine(url, connect_args={"connect_timeout": 3}, pool_pre_ping=True)
    try:
        with engine.connect() as connection:
            connection.execute(text("SELECT 1"))
    except Exception:
        engine.dispose()
        pytest.skip("The configured MySQL test database is unavailable")

    # This URL is explicitly guarded as a disposable test database above.
    # Recreate its schema so a previous interrupted run cannot contaminate this one.
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    yield engine
    Base.metadata.drop_all(engine)
    engine.dispose()


@pytest.fixture
def test_db(mysql_test_engine) -> Generator[Session, None, None]:
    connection = mysql_test_engine.connect()
    outer_transaction = connection.begin()
    session_factory = sessionmaker(
        bind=connection,
        expire_on_commit=False,
        join_transaction_mode="create_savepoint",
    )
    session = session_factory()
    try:
        yield session
    finally:
        session.close()
        outer_transaction.rollback()
        connection.close()


@pytest.fixture
def client(test_db: Session) -> Generator[TestClient, None, None]:
    def override_get_db():
        yield test_db

    app.dependency_overrides[get_db] = override_get_db
    try:
        with TestClient(app) as test_client:
            yield test_client
    finally:
        app.dependency_overrides.clear()
