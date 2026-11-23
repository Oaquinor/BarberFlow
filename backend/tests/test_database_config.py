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
    workflow = (repository_root / ".github" / "workflows" / "ci.yml").read_text(encoding="utf-8")

    assert "CLIENT_IP_HEADER=${CLIENT_IP_HEADER:-X-Real-IP}" in compose
    assert "CLIENT_IP_HEADER=X-Real-IP" in environment_example
    assert "EMAIL_FROM: ci@kingflow.example" in workflow


def test_render_api_builds_from_repository_root_to_serve_the_frontend():
    repository_root = Path(__file__).resolve().parents[2]
    render = (repository_root / "render.yaml").read_text(encoding="utf-8")
    api_service = render.split("  - type: worker", 1)[0]

    assert "name: kingflow-api" in api_service
    assert "rootDir: backend" not in api_service
    assert "buildCommand: pip install -r backend/requirements.txt" in api_service
    assert "startCommand: cd backend && alembic upgrade head && uvicorn" in api_service
    assert "value: '[]'" in api_service
    assert "envVarKey: RENDER_EXTERNAL_URL" in api_service
    assert "plan: free" not in api_service
    assert "plan: 0.5c-512mb" in api_service
    assert api_service.count("- key: WHATSAPP_API_URL") == 1
    assert "key: WHATSAPP_API_URL\n        sync: false" in api_service
    assert "key: UPLOAD_DIR\n        value: /opt/render/project/src/frontend/uploads" in api_service
    assert "mountPath: /opt/render/project/src/frontend/uploads" in api_service
    assert "key: EMAIL_FROM\n        sync: false" in api_service

    worker_service = render.split("  - type: worker", 1)[1]
    assert worker_service.count("- key: WHATSAPP_API_URL") == 1
    assert "key: WHATSAPP_API_URL\n        sync: false" in worker_service
    assert "key: EMAIL_FROM\n        sync: false" in worker_service


def test_production_compose_requires_an_explicit_email_sender():
    repository_root = Path(__file__).resolve().parents[2]
    compose = (repository_root / "docker-compose.prod.yml").read_text(encoding="utf-8")

    assert compose.count("EMAIL_FROM=${EMAIL_FROM:?") == 2


@pytest.mark.parametrize("url", [
    "sqlite:///kingflow.db",
    "postgresql://kingflow@localhost/kingflow_barber",
    "mysql://kingflow@localhost/kingflow_barber",
])
def test_database_url_rejects_non_mysql_pymysql_drivers(url):
    with pytest.raises(RuntimeError, match="MySQL PyMySQL"):
        validate_database_url(url)
