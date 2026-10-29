"""Exercise upload, persisted analysis, and exports in a disposable database.

Run inside the backend container with two local CSV paths. The parent process
creates and migrates a uniquely named database, then drops it after the check.
Authentication and the task queue are replaced only at the ASGI boundary; the
real upload, cleaning, analysis, persistence, and export code still runs.
"""

from __future__ import annotations

import asyncio
import base64
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import uuid
import zlib
from decimal import Decimal
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

import asyncpg
import duckdb
import httpx
from openpyxl import load_workbook
from sqlalchemy import select
from sqlalchemy.engine import make_url
from sqlalchemy.orm import selectinload

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def _check(response: httpx.Response, expected: int, step: str) -> dict:
    if response.status_code != expected:
        raise AssertionError(f"{step}: HTTP {response.status_code}: {response.text[:500]}")
    return response.json()


async def _run_cases(paths: list[Path]) -> None:
    from app.api.deps import get_current_user
    from app.api.v1.endpoints import analyses
    from app.db.session import AsyncSessionLocal, engine
    from app.main import app
    from app.models.analysis import Analysis
    from app.models.user import User
    from app.services.analysis_engine import AnalysisEngine
    from evals.calibration.run_eval import _OfflineAIService
    from evals.reliability.run_kaggle_eval import CASES, source_facts

    cases = {"coffee": paths[0], "supermarket": paths[1]}
    user = User(
        supabase_id=str(uuid.uuid4()),
        email=f"local-smoke-{uuid.uuid4().hex}@example.test",
    )
    async with AsyncSessionLocal() as db:
        db.add(user)
        await db.commit()
        await db.refresh(user)

    app.dependency_overrides[get_current_user] = lambda: user
    try:
        transport = httpx.ASGITransport(app=app)
        async with httpx.AsyncClient(transport=transport, base_url="http://local.test") as client:
            for name, path in cases.items():
                source = source_facts(path, **CASES[name])
                payload = path.read_bytes()
                response = await client.post(
                    "/api/v1/uploads",
                    files={"file": (path.name, payload, "text/csv")},
                )
                uploaded = _check(response, 201, f"{name} upload")
                assert uploaded["row_count"] == source["rows"], name

                with patch.object(
                    analyses.run_analysis_task,
                    "delay",
                    return_value=SimpleNamespace(id="local-smoke"),
                ):
                    response = await client.post(
                        "/api/v1/analyses",
                        json={
                            "file_id": uploaded["id"],
                            "name": f"Local {name} smoke test",
                            "cleaning": {"mode": "clean"},
                        },
                    )
                created = _check(response, 201, f"{name} analysis create")
                analysis_id = created["id"]

                # The production route has committed the row. Run the same
                # pipeline the Celery task calls, using offline narrative
                # generation so this check cannot consume an external key.
                with patch("app.services.analysis_engine.AIService", _OfflineAIService):
                    await AnalysisEngine().run(analysis_id)

                response = await client.get(f"/api/v1/analyses/{analysis_id}")
                detail = _check(response, 200, f"{name} detail")
                assert detail["status"] == "completed", (name, detail.get("error_message"))
                assert detail["row_count"] == source["rows"], name
                assert detail["charts"], f"{name}: no saved charts"

                async with AsyncSessionLocal() as db:
                    analysis = await db.scalar(
                        select(Analysis)
                        .where(Analysis.id == uuid.UUID(analysis_id))
                        .options(selectinload(Analysis.file))
                    )
                    assert analysis is not None
                    measure = CASES[name]["measure"].lower().replace(" ", "_")
                    with duckdb.connect(":memory:") as conn:
                        actual = Decimal(str(conn.execute(
                            f'SELECT SUM("{measure}") FROM read_parquet(?)',
                            [analysis.file.storage_path],
                        ).fetchone()[0]))
                    expected = Decimal(source["total"])
                    assert abs(actual - expected) <= Decimal("0.01"), (
                        name, str(actual), str(expected)
                    )

                pdf = await client.get(f"/api/v1/analyses/{analysis_id}/export/pdf")
                assert pdf.status_code == 200 and pdf.content.startswith(b"%PDF-"), name
                streams = [
                    zlib.decompress(base64.a85decode(raw, adobe=True))
                    for raw in re.findall(rb"stream\n(.*?)endstream", pdf.content, re.S)
                ]
                pdf_text = b"\n".join(streams)
                assert b"Visual Charts" in pdf_text, f"{name}: PDF charts missing"

                excel = await client.get(f"/api/v1/analyses/{analysis_id}/export/excel")
                assert excel.status_code == 200, (name, excel.status_code)
                workbook = load_workbook(io.BytesIO(excel.content), read_only=False)
                chart_count = len(workbook["Charts"]._charts) if "Charts" in workbook else 0
                assert chart_count > 0, f"{name}: Excel charts missing"
                print(json.dumps({
                    "dataset": name,
                    "rows": detail["row_count"],
                    "source_total": str(expected),
                    "saved_total": str(actual),
                    "saved_charts": len(detail["charts"]),
                    "pdf_bytes": len(pdf.content),
                    "excel_charts": chart_count,
                    "status": "passed",
                }), flush=True)
    finally:
        app.dependency_overrides.clear()
        await engine.dispose()


async def _isolated(paths: list[Path]) -> int:
    from app.core.config import settings

    source = make_url(settings.database_url)
    name = f"zephyr_upload_smoke_{uuid.uuid4().hex}"
    assert re.fullmatch(r"zephyr_upload_smoke_[0-9a-f]{32}", name)
    assert name != source.database
    connection = await asyncpg.connect(
        host=source.host,
        port=source.port or 5432,
        user=source.username,
        password=source.password,
        database=source.database,
    )
    created = False
    try:
        await connection.execute(f'CREATE DATABASE "{name}"')
        created = True
        with tempfile.TemporaryDirectory(prefix="zephyr-upload-smoke-") as upload_dir:
            env = dict(os.environ)
            env.update({
                "DATABASE_URL": source.set(
                    database=name, drivername="postgresql+asyncpg"
                ).render_as_string(hide_password=False),
                "DATABASE_URL_SYNC": source.set(
                    database=name, drivername="postgresql"
                ).render_as_string(hide_password=False),
                "UPLOAD_DIR": upload_dir,
                "DEBUG": "false",
                "SENTRY_DSN": "",
                "SEMANTIC_WRANGLING_ENABLED": "false",
                "OPENAI_API_KEY": "unused-local-smoke",
            })
            migrated = subprocess.run(
                [sys.executable, "-m", "alembic", "upgrade", "head"],
                cwd=ROOT,
                env=env,
                check=False,
            )
            if migrated.returncode:
                return migrated.returncode
            finished = subprocess.run(
                [sys.executable, str(Path(__file__).resolve()), "--run", *map(str, paths)],
                cwd=ROOT,
                env=env,
                check=False,
            )
            return finished.returncode
    finally:
        if created:
            await connection.execute(f'DROP DATABASE "{name}" WITH (FORCE)')
        await connection.close()


if __name__ == "__main__":
    arguments = sys.argv[1:]
    run = arguments[:1] == ["--run"]
    paths = [Path(value).resolve() for value in arguments[1 if run else 0:]]
    if len(paths) != 2 or any(not path.is_file() for path in paths):
        raise SystemExit("Supply the coffee and supermarket CSV paths")
    if run:
        asyncio.run(_run_cases(paths))
    else:
        raise SystemExit(asyncio.run(_isolated(paths)))
