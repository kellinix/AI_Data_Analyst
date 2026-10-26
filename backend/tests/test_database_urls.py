from __future__ import annotations

import pytest

from app.core.config import Settings


@pytest.mark.parametrize(
    "railway_url",
    [
        "postgresql://user:password@postgres.railway.internal:5432/railway",
        "postgres://user:password@postgres.railway.internal:5432/railway",
        "postgresql+asyncpg://user:password@postgres.railway.internal:5432/railway",
    ],
)
def test_database_urls_accept_railway_postgres_scheme(railway_url: str) -> None:
    settings = Settings.model_construct(database_url_override=railway_url)

    assert settings.database_url.startswith("postgresql+asyncpg://")
    assert settings.sync_database_url.startswith("postgresql://")
    assert settings.database_url.endswith("postgres.railway.internal:5432/railway")


def test_database_url_needs_no_separate_postgres_password(monkeypatch) -> None:
    monkeypatch.delenv("POSTGRES_PASSWORD", raising=False)
    settings = Settings(
        _env_file=None,
        debug=False,
        secret_key="test-secret",
        openai_api_key="test-key",
        DATABASE_URL="postgresql://user:password@postgres.railway.internal:5432/railway",
    )

    assert settings.postgres_password == ""
    assert settings.database_url.startswith("postgresql+asyncpg://")
