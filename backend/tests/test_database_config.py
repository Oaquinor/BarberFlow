from pathlib import Path

import pytest

from app.core.database.session import validate_database_url
from app.models.user import User


def test_database_url_accepts_mysql_pymysql():
    url = "mysql+pymysql://kingflow:secret@localhost:3307/kingflow_barber"
    assert validate_database_url(url) == url


def test_users_model_indexes_tenant_role_and_soft_delete_listings():
    indexes = {index.name: tuple(column.name for column in index.columns) for index in User.__table__.indexes}
    assert indexes["ix_users_tenant_role_deleted_id"] == (
        "barbershop_id", "role", "is_deleted", "id",
    )


def test_production_compose_uses_the_trusted_reverse_proxy_ip_header():
    repository_root = Path(__file__).resolve().parents[2]
    compose = (repository_root / "docker-compose.prod.yml").read_text(encoding="utf-8")
    environment_example = (repository_root / ".env.production.example").read_text(encoding="utf-8")

    assert "CLIENT_IP_HEADER=${CLIENT_IP_HEADER:-X-Real-IP}" in compose
    assert "CLIENT_IP_HEADER=X-Real-IP" in environment_example


@pytest.mark.parametrize("url", [
    "sqlite:///kingflow.db",
    "postgresql://kingflow@localhost/kingflow_barber",
    "mysql://kingflow@localhost/kingflow_barber",
])
def test_database_url_rejects_non_mysql_pymysql_drivers(url):
    with pytest.raises(RuntimeError, match="MySQL PyMySQL"):
        validate_database_url(url)
