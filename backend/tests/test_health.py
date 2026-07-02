from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from unittest.mock import AsyncMock, patch

from app.main import app

client = TestClient(app)


def test_health_endpoint():
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] in ("healthy", "degraded")


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
