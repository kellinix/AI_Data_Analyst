# conftest.py — shared pytest fixtures
from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Ensure CI environment variables don't leak between tests."""
    monkeypatch.setenv("ENVIRONMENT", "development")
    monkeypatch.setenv("SECRET_KEY", "test-secret-key-32-characters-ok!!")
    monkeypatch.setenv("OPENAI_API_KEY", "sk-test-fake")
    monkeypatch.setenv("SUPABASE_URL", "https://test.supabase.co")
    monkeypatch.setenv("SUPABASE_ANON_KEY", "test-anon-key")
    monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "test-service-key")
    monkeypatch.setenv("SUPABASE_JWT_SECRET", "test-jwt-secret-32-chars-minimum!!")
    monkeypatch.setenv("POSTGRES_SERVER", "localhost")
    monkeypatch.setenv("POSTGRES_USER", "test_user")
    monkeypatch.setenv("POSTGRES_PASSWORD", "test_pass")
    monkeypatch.setenv("POSTGRES_DB", "test_db")
    monkeypatch.setenv("REDIS_HOST", "localhost")
