"""Health check must verify the active database connection."""

from fastapi.testclient import TestClient


def test_health_reports_mysql_as_connected_when_query_succeeds(client: TestClient):
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "healthy", "database": "connected"}
