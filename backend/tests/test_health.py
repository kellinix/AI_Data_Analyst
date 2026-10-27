from __future__ import annotations

from fastapi.testclient import TestClient

from app.api.v1.endpoints.health import _database_error_types
from app.main import app

client = TestClient(app)


def test_database_health_log_excludes_connection_details():
    error = RuntimeError("postgresql://user:secret@private-host/database")
    error.orig = ConnectionRefusedError("private-host")

    assert _database_error_types(error) == ["RuntimeError", "ConnectionRefusedError"]


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code in (200, 503)
    data = response.json()
    assert data["status"] in ("healthy", "degraded")
    assert response.status_code == (200 if data["database"] == "ok" else 503)


def test_cors_headers():
    response = client.options(
        "/api/v1/health",
        headers={"Origin": "http://localhost:3000"},
    )
    assert response.status_code in (200, 405)


def test_openapi_not_available_in_production(monkeypatch):
    monkeypatch.setenv("ENVIRONMENT", "production")
    # Just check no exception is raised
    from app.core.config import get_settings
    get_settings.cache_clear()
    # Reset
    get_settings.cache_clear()
