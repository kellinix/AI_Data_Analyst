# conftest.py — shared pytest fixtures
from __future__ import annotations

import os

import pytest

# Safe, non-secret values only. Nothing here is a real credential.
_TEST_ENV = {
    "ENVIRONMENT": "development",
    "SECRET_KEY": "test-secret-key-32-characters-ok!!",
    "OPENAI_API_KEY": "sk-test-fake",
    "SUPABASE_URL": "https://test.supabase.co",
    "SUPABASE_ANON_KEY": "test-anon-key",
    "SUPABASE_SERVICE_ROLE_KEY": "test-service-key",
    "SUPABASE_JWT_SECRET": "test-jwt-secret-32-chars-minimum!!",
    "POSTGRES_SERVER": "localhost",
    "POSTGRES_USER": "test_user",
    "POSTGRES_PASSWORD": "test_pass",
    "POSTGRES_DB": "test_db",
    "REDIS_HOST": "localhost",
}

# app.core.config builds Settings() at import time, which happens during test
# collection — before any fixture runs. Seed the environment here so a clean
# clone can run `pytest` with nothing exported. setdefault keeps values that
# CI or the shell already provide.
for _key, _value in _TEST_ENV.items():
    os.environ.setdefault(_key, _value)


@pytest.fixture(autouse=True)
def isolate_env(monkeypatch):
    """Ensure CI environment variables don't leak between tests."""
    for key, value in _TEST_ENV.items():
        monkeypatch.setenv(key, value)


@pytest.fixture(autouse=True)
def empty_calibration_table(tmp_path, monkeypatch):
    """Point confidence lookups at an absent table so tests see hand-set
    defaults regardless of what the committed calibration table contains.
    Tests that need measured values write their own table to this path."""
    from app.analytics import calibration

    path = tmp_path / "calibration_table.json"
    monkeypatch.setattr(calibration, "CALIBRATION_TABLE_PATH", path)
    calibration.load_calibration_table.cache_clear()
    yield path
    calibration.load_calibration_table.cache_clear()
