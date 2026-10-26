"""Run database integration checks in a disposable database, never the app DB.

From the backend container: python scripts/test_isolated_database.py
Uses the configured local Postgres connection without printing credentials.
"""
from __future__ import annotations

import asyncio
import os
import re
import subprocess
import sys
import uuid
from pathlib import Path

import asyncpg
from sqlalchemy.engine import make_url

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))


async def main() -> int:
    from app.core.config import settings

    source = make_url(settings.database_url)
    name = f"zephyr_release_test_{uuid.uuid4().hex}"
    assert re.fullmatch(r"zephyr_release_test_[0-9a-f]{32}", name)
    assert name != source.database
    connection = await asyncpg.connect(
        host=source.host, port=source.port or 5432, user=source.username,
        password=source.password, database=source.database,
    )
    created = False
    try:
        await connection.execute(f'CREATE DATABASE "{name}"')
        created = True
        env = dict(os.environ)
        env["DEBUG"] = "false"
        env["SEMANTIC_WRANGLING_ENABLED"] = "false"
        env["SENTRY_DSN"] = ""
        env["DATABASE_URL"] = source.set(database=name, drivername="postgresql+asyncpg").render_as_string(hide_password=False)
        env["DATABASE_URL_SYNC"] = source.set(database=name, drivername="postgresql").render_as_string(hide_password=False)
        result = await asyncio.to_thread(
            subprocess.run,
            [sys.executable, "-m", "pytest", "tests/test_metric_definitions.py",
             "tests/test_recommendation_feedback.py", "-q", "--tb=short"],
            env=env, cwd=Path(__file__).resolve().parents[1], check=False,
        )
        return result.returncode
    finally:
        if created:
            await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
