"""DB-backed tests for recommendation feedback: migration 003, the endpoints,
the snapshot-survives-regeneration guarantee, and the calibration view.

Runs against the Postgres configured by POSTGRES_* — CI's service container,
or locally e.g.

    docker run -d -p 5433:5432 -e POSTGRES_USER=test_user \
        -e POSTGRES_PASSWORD=test_pass -e POSTGRES_DB=test_db postgres:16-alpine
    POSTGRES_PORT=5433 pytest tests/test_recommendation_feedback.py

Skipped when no database is reachable.
"""

from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from types import SimpleNamespace

import httpx
import pytest
from sqlalchemy import delete, select, text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.core.config import settings
from app.models.analysis import Analysis, UploadedFile
from app.models.insight import Insight
from app.models.recommendation_feedback import RecommendationFeedback
from app.models.user import User

BACKEND = Path(__file__).resolve().parents[1]


@pytest.fixture(scope="module")
def database_url() -> str:
    url = settings.database_url

    async def prepare() -> None:
        engine = create_async_engine(url, poolclass=NullPool)
        try:
            async with engine.connect() as conn:
                await conn.execute(text('CREATE EXTENSION IF NOT EXISTS "uuid-ossp"'))
                await conn.commit()
        finally:
            await engine.dispose()

    try:
        asyncio.run(prepare())
    except Exception as exc:  # pragma: no cover - depends on the environment
        pytest.skip(f"Postgres not reachable for DB-backed tests: {exc}")

    from alembic import command
    from alembic.config import Config

    config = Config(str(BACKEND / "alembic.ini"))
    config.set_main_option("script_location", str(BACKEND / "alembic"))
    command.upgrade(config, "head")
    return url


@pytest.fixture
async def sessions(database_url):
    engine = create_async_engine(database_url, poolclass=NullPool)
    yield async_sessionmaker(engine, expire_on_commit=False)
    await engine.dispose()


@pytest.fixture
async def seeded(sessions):
    """Two users; the first owns an analysis with a recommendation and an anomaly."""
    tag = uuid.uuid4().hex[:8]
    source = f"rule:t-{tag}"
    async with sessions() as session:
        owner = User(supabase_id=f"owner-{tag}", email=f"owner-{tag}@example.test")
        stranger = User(supabase_id=f"stranger-{tag}", email=f"stranger-{tag}@example.test")
        session.add_all([owner, stranger])
        await session.flush()
        upload = UploadedFile(
            user_id=owner.id,
            filename="sales.csv",
            original_filename="sales.csv",
            file_size=10,
            mime_type="text/csv",
            storage_path="/tmp/sales.csv",
        )
        session.add(upload)
        await session.flush()
        analysis = Analysis(user_id=owner.id, file_id=upload.id, name="Sales", status="completed")
        session.add(analysis)
        await session.flush()
        recommendation = Insight(
            analysis_id=analysis.id,
            type="recommendation",
            title="Review standout revenue",
            description="Compare the record with similar weeks.",
            importance="high",
            confidence=0.85,
            data={"confidence_source": source, "confidence_method": "default"},
        )
        anomaly = Insight(
            analysis_id=analysis.id,
            type="anomaly",
            title="Standout revenue",
            description="One record reached 9,999.",
            importance="high",
            confidence=0.9,
        )
        session.add_all([recommendation, anomaly])
        await session.commit()

    yield SimpleNamespace(
        owner=owner,
        stranger=stranger,
        analysis=analysis,
        recommendation=recommendation,
        anomaly=anomaly,
        source=source,
    )

    async with sessions() as session:
        await session.execute(delete(User).where(User.id.in_([owner.id, stranger.id])))
        await session.commit()


@pytest.fixture
async def client(sessions, seeded):
    from app.api.deps import get_current_user
    from app.db.session import get_db
    from app.main import app

    async def override_db():
        async with sessions() as session:
            yield session
            await session.commit()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: seeded.owner
    transport = httpx.ASGITransport(app=app)
    async with httpx.AsyncClient(transport=transport, base_url="http://test") as http:
        yield http
    app.dependency_overrides.clear()


def _feedback_url(seeded, insight=None) -> str:
    insight_id = (insight or seeded.recommendation).id
    return f"/api/v1/analyses/{seeded.analysis.id}/insights/{insight_id}/feedback"


async def _feedback_rows(sessions, seeded) -> list[RecommendationFeedback]:
    async with sessions() as session:
        result = await session.execute(
            select(RecommendationFeedback).where(
                RecommendationFeedback.analysis_id == seeded.analysis.id
            )
        )
        return list(result.scalars())


async def test_put_records_verdict_with_confidence_snapshot(client, sessions, seeded):
    response = await client.put(_feedback_url(seeded), json={"verdict": "helpful"})

    assert response.status_code == 200
    assert response.json() == {"insight_id": str(seeded.recommendation.id), "verdict": "helpful"}
    [row] = await _feedback_rows(sessions, seeded)
    assert row.user_id == seeded.owner.id
    assert row.verdict == "helpful"
    assert row.confidence == 0.85
    assert row.confidence_source == seeded.source
    assert row.confidence_method == "default"
    assert row.importance == "high"
    assert row.recommendation_title == "Review standout revenue"


async def test_put_again_changes_verdict_without_duplicating(client, sessions, seeded):
    await client.put(_feedback_url(seeded), json={"verdict": "helpful"})
    response = await client.put(_feedback_url(seeded), json={"verdict": "not_helpful"})

    assert response.status_code == 200
    rows = await _feedback_rows(sessions, seeded)
    assert [row.verdict for row in rows] == ["not_helpful"]


async def test_get_analysis_reports_the_owners_verdict(client, seeded):
    await client.put(_feedback_url(seeded), json={"verdict": "not_helpful"})

    response = await client.get(f"/api/v1/analyses/{seeded.analysis.id}")

    assert response.status_code == 200
    feedback = {item["id"]: item["user_feedback"] for item in response.json()["insights"]}
    assert feedback == {
        str(seeded.recommendation.id): "not_helpful",
        str(seeded.anomaly.id): None,
    }


async def test_delete_withdraws_the_verdict(client, sessions, seeded):
    await client.put(_feedback_url(seeded), json={"verdict": "helpful"})

    response = await client.delete(_feedback_url(seeded))

    assert response.status_code == 204
    assert await _feedback_rows(sessions, seeded) == []


async def test_other_users_cannot_rate_the_recommendation(client, sessions, seeded):
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: seeded.stranger

    response = await client.put(_feedback_url(seeded), json={"verdict": "helpful"})

    assert response.status_code == 404
    assert await _feedback_rows(sessions, seeded) == []


async def test_only_recommendations_accept_feedback(client, seeded):
    response = await client.put(_feedback_url(seeded, seeded.anomaly), json={"verdict": "helpful"})

    assert response.status_code == 422


async def test_unknown_verdicts_are_rejected(client, seeded):
    response = await client.put(_feedback_url(seeded), json={"verdict": "maybe"})

    assert response.status_code == 422


async def test_authentication_is_required(client, seeded):
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides.pop(get_current_user)

    response = await client.put(_feedback_url(seeded), json={"verdict": "helpful"})

    assert response.status_code == 401


async def test_verdict_survives_insight_regeneration_and_feeds_the_view(client, sessions, seeded):
    """A re-run deletes and recreates insights. The verdict must outlive its
    insight with the snapshot intact, and still count in the calibration view."""
    await client.put(_feedback_url(seeded), json={"verdict": "helpful"})

    async with sessions() as session:
        await session.execute(delete(Insight).where(Insight.analysis_id == seeded.analysis.id))
        await session.commit()

    [row] = await _feedback_rows(sessions, seeded)
    assert row.insight_id is None
    assert row.confidence == 0.85
    assert row.confidence_source == seeded.source

    async with sessions() as session:
        view_row = (
            await session.execute(
                text(
                    "SELECT n, mean_confidence, helpful_rate, brier_score "
                    "FROM recommendation_calibration WHERE confidence_source = :source"
                ),
                {"source": seeded.source},
            )
        ).one()
    assert view_row.n == 1
    assert float(view_row.mean_confidence) == 0.85
    assert float(view_row.helpful_rate) == 1.0
    assert float(view_row.brier_score) == pytest.approx(0.0225)
