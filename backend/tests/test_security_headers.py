"""HTTP response protections for browser-facing pages and API data."""

from types import SimpleNamespace

from fastapi.testclient import TestClient
import pytest

import app.main as main
import app.middleware.security_headers as security_headers


def test_browser_security_headers_cover_frontend_and_api(client: TestClient):
    page = client.get("/signup.html")
    assert page.status_code == 200
    assert page.headers["x-content-type-options"] == "nosniff"
    assert page.headers["x-frame-options"] == "DENY"
    assert page.headers["referrer-policy"] == "strict-origin-when-cross-origin"
    assert page.headers["permissions-policy"] == "camera=(), geolocation=(), microphone=()"

    api_response = client.get("/api/v1/saas/registration-status")
    assert api_response.status_code == 200
    assert api_response.headers["cache-control"] == "no-store"
    assert api_response.headers["pragma"] == "no-cache"


def test_production_responses_add_hsts(client: TestClient, monkeypatch):
    monkeypatch.setattr(
        security_headers,
        "get_settings",
        lambda: SimpleNamespace(ENVIRONMENT="production"),
    )
    response = client.get("/signup.html")
    assert response.headers["strict-transport-security"] == "max-age=31536000; includeSubDomains"


@pytest.mark.parametrize("origins", [[], ["*"], ["http://kingflow.example"]])
def test_production_rejects_wildcard_or_insecure_cors_origins(monkeypatch, origins):
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        ENVIRONMENT="production",
        DEBUG=False,
        SECRET_KEY="local-test-secret-that-is-long-enough-to-pass",
        DATABASE_URL="mysql+pymysql://kingflow:secret@localhost/kingflow_barber",
        CORS_ORIGINS=origins,
        FRONTEND_BASE_URL="https://kingflow.example",
    ))

    with pytest.raises(RuntimeError, match="CORS_ORIGINS"):
        main.create_application()


def test_production_requires_https_frontend_base_url(monkeypatch):
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        ENVIRONMENT="production",
        DEBUG=False,
        SECRET_KEY="local-test-secret-that-is-long-enough-to-pass",
        DATABASE_URL="mysql+pymysql://kingflow:secret@localhost/kingflow_barber",
        CORS_ORIGINS=["https://kingflow.example"],
        FRONTEND_BASE_URL="http://localhost:8000",
    ))

    with pytest.raises(RuntimeError, match="FRONTEND_BASE_URL"):
        main.create_application()


@pytest.mark.parametrize("frontend_url", ["https:///missing-host", "https://user@kingflow.example", "https://kingflow.example/?token=unsafe"])
def test_production_rejects_malformed_or_credentialed_frontend_urls(monkeypatch, frontend_url):
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        ENVIRONMENT="production",
        DEBUG=False,
        SECRET_KEY="local-test-secret-that-is-long-enough-to-pass",
        DATABASE_URL="mysql+pymysql://kingflow:secret@localhost/kingflow_barber",
        CORS_ORIGINS=["https://kingflow.example"],
        FRONTEND_BASE_URL=frontend_url,
    ))

    with pytest.raises(RuntimeError, match="FRONTEND_BASE_URL"):
        main.create_application()


def test_production_accepts_explicit_https_frontend_and_cors(monkeypatch):
    monkeypatch.setattr(main, "settings", SimpleNamespace(
        ENVIRONMENT="production",
        DEBUG=False,
        SECRET_KEY="local-test-secret-that-is-long-enough-to-pass",
        DATABASE_URL="mysql+pymysql://kingflow:secret@localhost/kingflow_barber",
        CORS_ORIGINS=["https://kingflow.example"],
        FRONTEND_BASE_URL="https://kingflow.example",
    ))

    application = main.create_application()
    assert "/api/v1/auth/password-reset/request" in application.openapi()["paths"]
