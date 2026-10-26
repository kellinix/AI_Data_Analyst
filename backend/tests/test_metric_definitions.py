from __future__ import annotations

import asyncio
import uuid
from pathlib import Path
from unittest.mock import AsyncMock

import duckdb
import httpx
import pytest
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine
from sqlalchemy.pool import NullPool

from app.api.deps import DB
from app.core.config import settings
from app.models.analysis import Analysis, UploadedFile
from app.models.chat import ChatMessage, ChatSession
from app.models.dashboard_revision import DashboardRevision
from app.models.metric_definition import MetricDefinition
from app.models.usage_event import UsageEvent
from app.models.user import User
from app.services.dashboard_spec import edit_spec, reconcile_spec
from app.services.metric_definitions import calculate_metric, validate_metric_source
from app.services.usage_events import finalize_analysis, record_chat_response, reserve_analysis

SCHEMA = [
    {"name": "sales", "is_numeric": True, "analysis_role": "metric"},
    {"name": "store", "is_numeric": True, "analysis_role": "identifier"},
    {"name": "region", "is_numeric": False, "analysis_role": "dimension"},
]


def test_calculations_and_role_validation():
    with duckdb.connect(":memory:") as conn:
        conn.execute("CREATE TABLE data AS SELECT * FROM (VALUES (10.0, 1, 'North'), (20.0, 1, 'North'), (NULL, 2, 'South')) t(sales, store, region)")
        assert calculate_metric(conn, "sum", "sales") == 30.0
        assert calculate_metric(conn, "average", "sales") == 15.0
        assert calculate_metric(conn, "count", None) == 3
        assert calculate_metric(conn, "distinct_count", "store") == 2
    validate_metric_source(SCHEMA, "distinct_count", "store")
    with pytest.raises(ValueError):
        validate_metric_source(SCHEMA, "sum", "store")
    with pytest.raises(ValueError):
        validate_metric_source(SCHEMA, "sum", 'sales"; DROP TABLE data; --')


def test_dashboard_edit_skips_hidden_charts_and_reconciles_rerun():
    spec = {"schema_version": 1, "chart_order": ["a", "b", "c"], "hidden_chart_ids": ["b"]}
    assert edit_spec(spec, "move_down", "a")["chart_order"] == ["c", "b", "a"]
    assert reconcile_spec(spec, [{"id": "a"}, {"id": "d"}]) == {
        "schema_version": 1, "chart_order": ["a", "d"], "hidden_chart_ids": [], "chart_palettes": {},
        "metric_family_ids": [], "saved_filters": [],
    }
    palette_spec = edit_spec(reconcile_spec(spec, [{"id": "a"}]), "set_palette", "a", palette="ocean")
    assert palette_spec["chart_palettes"] == {"a": "ocean"}
    assert reconcile_spec(palette_spec, [{"id": "d"}])["chart_palettes"] == {}
    with pytest.raises(ValueError, match="Unknown chart palette"):
        edit_spec(palette_spec, "set_palette", "a", palette="unknown")


@pytest.fixture(scope="module")
def database_url():
    async def ping():
        engine = create_async_engine(settings.database_url, poolclass=NullPool)
        try:
            async with engine.connect():
                pass
        finally:
            await engine.dispose()

    try:
        asyncio.run(ping())
    except Exception as exc:
        pytest.skip(f"No test database reachable: {exc}")

    from alembic import command
    from alembic.config import Config

    backend = Path(__file__).resolve().parents[1]
    config = Config(str(backend / "alembic.ini"))
    config.set_main_option("script_location", str(backend / "alembic"))
    command.upgrade(config, "head")
    return settings.database_url


@pytest.fixture
async def metric_client(database_url, tmp_path):
    from app.api.deps import get_current_user
    from app.db.session import get_db
    from app.main import app

    source = tmp_path / "sales.csv"
    source.write_text("sales,store,region\n10,1,North\n20,1,North\n30,2,South\n", encoding="utf-8")
    engine = create_async_engine(database_url, poolclass=NullPool)
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    tag = uuid.uuid4().hex[:8]
    async with sessions() as db:
        owner = User(supabase_id=f"metric-owner-{tag}", email=f"metric-owner-{tag}@example.test")
        stranger = User(supabase_id=f"metric-stranger-{tag}", email=f"metric-stranger-{tag}@example.test")
        db.add_all([owner, stranger])
        await db.flush()
        upload = UploadedFile(user_id=owner.id, filename="sales.csv", original_filename="sales.csv",
                              file_size=source.stat().st_size, mime_type="text/csv", storage_path=str(source))
        db.add(upload)
        await db.flush()
        analysis = Analysis(user_id=owner.id, file_id=upload.id, name="Sales", status="completed",
                            metadata_={"schema": SCHEMA}, charts=[])
        db.add(analysis)
        await db.commit()

    async def override_db():
        async with sessions() as db:
            yield db
            await db.commit()

    app.dependency_overrides[get_db] = override_db
    app.dependency_overrides[get_current_user] = lambda: owner
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield client, analysis, owner, stranger, sessions
    app.dependency_overrides.clear()
    async with sessions() as db:
        await db.execute(delete(User).where(User.id.in_([owner.id, stranger.id])))
        await db.commit()
    await engine.dispose()


async def test_preview_approve_revision_and_owner_isolation(metric_client):
    client, analysis, owner, stranger, sessions = metric_client
    root = f"/api/v1/analyses/{analysis.id}/metrics"
    total = {"name": "Total sales", "aggregation": "sum", "column_name": "sales"}
    preview = await client.post(f"{root}/preview", json=total)
    assert preview.status_code == 200, preview.text
    assert preview.json()["value"] == 60.0
    assert preview.json()["row_count"] == 3

    invalid = await client.post(f"{root}/preview", json={**total, "column_name": "store"})
    assert invalid.status_code == 422
    assert (await client.get(root)).json() == []

    created = await client.post(root, json=total)
    assert created.status_code == 201, created.text
    first = created.json()
    assert first["version"] == 1 and first["value"] == 60.0
    assert len((await client.get(root)).json()) == 1

    revised = await client.put(f"{root}/{first['family_id']}", json={
        "name": "Average sales", "aggregation": "average", "column_name": "sales",
    })
    assert revised.status_code == 200, revised.text
    assert revised.json()["version"] == 2
    assert revised.json()["value"] == 20.0
    assert [item["version"] for item in (await client.get(root)).json()] == [2]
    async with sessions() as db:
        rows = list((await db.execute(select(MetricDefinition).where(
            MetricDefinition.family_id == uuid.UUID(first["family_id"])
        ).order_by(MetricDefinition.version))).scalars())
        assert [(row.version, row.is_current) for row in rows] == [(1, False), (2, True)]
        assert analysis.charts == []

        replacement = UploadedFile(
            user_id=owner.id, filename="replacement.csv", original_filename="replacement.csv",
            file_size=0, mime_type="text/csv", storage_path="/tmp/replacement.csv",
        )
        db.add(replacement)
        await db.flush()
        saved_analysis = await db.get(Analysis, analysis.id)
        saved_analysis.file_id = replacement.id
        await db.commit()
    assert (await client.get(root)).json() == []
    assert (await client.put(f"{root}/{first['family_id']}", json=total)).status_code == 404

    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: stranger
    assert (await client.get(root)).status_code == 404
    assert (await client.post(f"{root}/preview", json=total)).status_code == 404
    assert (await client.put(f"{root}/{first['family_id']}", json=total)).status_code == 404


async def test_dashboard_layout_persists_revisions_and_undo(metric_client):
    client, analysis, owner, stranger, sessions = metric_client
    charts = [{"id": "sales", "title": "Sales"}, {"id": "regions", "title": "Regions"}]
    async with sessions() as db:
        saved = await db.get(Analysis, analysis.id)
        saved.charts = charts
        await db.commit()
    root = f"/api/v1/analyses/{analysis.id}/dashboard"
    initial = await client.get(root)
    assert initial.status_code == 200
    assert initial.json() == {"version": 0, "spec": {
        "schema_version": 1, "chart_order": ["sales", "regions"], "hidden_chart_ids": [], "chart_palettes": {},
        "metric_family_ids": [], "saved_filters": [],
    }}
    hidden = await client.post(root, json={
        "expected_version": 0, "action": "hide", "chart_id": "regions",
    })
    assert hidden.status_code == 200, hidden.text
    assert hidden.json()["version"] == 1
    assert hidden.json()["spec"]["hidden_chart_ids"] == ["regions"]
    assert (await client.post(root, json={
        "expected_version": 0, "action": "hide", "chart_id": "sales",
    })).status_code == 409
    assert (await client.post(root, json={
        "expected_version": 1, "action": "hide", "chart_id": "unknown",
    })).status_code == 422
    undone = await client.post(root, json={"expected_version": 1, "action": "undo"})
    assert undone.status_code == 200, undone.text
    assert undone.json()["version"] == 2
    assert undone.json()["spec"]["hidden_chart_ids"] == []
    assert (await client.get(root)).json()["version"] == 2
    palette = await client.post(root, json={
        "expected_version": 2, "action": "set_palette", "chart_id": "sales", "palette": "ocean",
    })
    assert palette.status_code == 200, palette.text
    assert palette.json()["spec"]["chart_palettes"] == {"sales": "ocean"}
    assert (await client.get(root)).json()["spec"]["chart_palettes"] == {"sales": "ocean"}
    async with sessions() as db:
        revisions = list((await db.execute(select(DashboardRevision).where(
            DashboardRevision.analysis_id == analysis.id
        ).order_by(DashboardRevision.version))).scalars())
        assert [revision.version for revision in revisions] == [1, 2, 3]
        saved = await db.get(Analysis, analysis.id)
        assert saved.charts == charts
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: stranger
    assert (await client.get(root)).status_code == 404
    assert (await client.post(root, json={"expected_version": 3, "action": "hide", "chart_id": "sales"})).status_code == 404


async def test_dashboard_pins_approved_metric_and_saves_validated_filters(metric_client):
    client, analysis, _owner, _stranger, _sessions = metric_client
    root = f"/api/v1/analyses/{analysis.id}/dashboard"
    metric = (await client.post(f"/api/v1/analyses/{analysis.id}/metrics", json={
        "name": "Total sales", "aggregation": "sum", "column_name": "sales",
    })).json()
    family_id = metric["family_id"]
    invalid_pin = await client.post(root, json={
        "expected_version": 0, "action": "pin_metric", "metric_family_id": str(uuid.uuid4()),
    })
    assert invalid_pin.status_code == 422
    pinned = await client.post(root, json={
        "expected_version": 0, "action": "pin_metric", "metric_family_id": family_id,
    })
    assert pinned.status_code == 200, pinned.text
    assert pinned.json()["spec"]["metric_family_ids"] == [family_id]
    invalid_filter = await client.post(root, json={
        "expected_version": 1, "action": "save_filters",
        "filters": [{"column": "store", "op": "in", "values": [1]}],
    })
    assert invalid_filter.status_code == 422
    invalid_value = await client.post(root, json={
        "expected_version": 1, "action": "save_filters",
        "filters": [{"column": "region", "op": "in", "values": [{"unexpected": "object"}]}],
    })
    assert invalid_value.status_code == 422
    saved = await client.post(root, json={
        "expected_version": 1, "action": "save_filters",
        "filters": [{"column": "region", "op": "in", "values": ["North"]}],
    })
    assert saved.status_code == 200, saved.text
    assert saved.json()["spec"]["saved_filters"] == [
        {"column": "region", "op": "in", "values": ["North"]},
    ]
    assert (await client.get(root)).json()["spec"]["metric_family_ids"] == [family_id]
    undone = await client.post(root, json={"expected_version": 2, "action": "undo"})
    assert undone.status_code == 200, undone.text
    assert undone.json()["spec"]["saved_filters"] == []
    assert undone.json()["spec"]["metric_family_ids"] == [family_id]


@pytest.mark.parametrize("failure_status", ["failed", "unsupported"])
async def test_failed_ai_followup_does_not_use_allowance(metric_client, monkeypatch, failure_status):
    from app.api.deps import get_current_user
    from app.main import app
    from app.services.ai_service import AIService

    client, analysis, owner, _stranger, sessions = metric_client
    async with sessions() as db:
        chat_session = ChatSession(analysis_id=analysis.id, title="Questions")
        db.add(chat_session)
        await db.commit()

    async def attached_user(db: DB):
        return await db.get(User, owner.id)

    app.dependency_overrides[get_current_user] = attached_user

    async def failed_chat(self, analysis, history, user_message):
        return {"content": "Please try again.", "chart_config": None,
                "metadata": {"status": failure_status, "model": "test-model"}}

    monkeypatch.setattr(AIService, "chat", failed_chat)
    url = f"/api/v1/chat/sessions/{chat_session.id}/messages"
    failed = await client.post(url, json={"content": "What changed?"})
    assert failed.status_code == 200, failed.text
    async with sessions() as db:
        assert (await db.get(User, owner.id)).ai_queries_this_month == 0

    async def successful_chat(self, analysis, history, user_message):
        return {"content": "Sales rose.", "chart_config": None,
                "metadata": {"status": "succeeded", "model": "test-model",
                             "prompt_tokens": 100, "completion_tokens": 20}}

    monkeypatch.setattr(AIService, "chat", successful_chat)
    succeeded = await client.post(url, json={"content": "What changed?"})
    assert succeeded.status_code == 200, succeeded.text
    async with sessions() as db:
        assert (await db.get(User, owner.id)).ai_queries_this_month == 1
        message = await db.get(ChatMessage, uuid.UUID(succeeded.json()["id"]))
        assert message.internal_metadata["model"] == "test-model"
        assert message.internal_metadata["prompt_tokens"] == 100


async def test_comparison_and_supporting_entries_are_owner_scoped(metric_client, monkeypatch):
    from app.api.deps import get_current_user
    from app.api.v1.endpoints import analyses
    from app.main import app
    client, analysis, _owner, stranger, _sessions = metric_client
    root = f"/api/v1/analyses/{analysis.id}"
    plan = {"aggregation": "sum", "column": "sales", "group_by": "region"}
    result = await client.post(root + "/compare", json=plan)
    assert result.status_code == 200, result.text
    comparison = result.json()
    assert [g["value"] for g in comparison["groups"]] == [30, 30]
    first = comparison["groups"][0]
    found = await client.post(root + "/entries", json={"kind": "comparison", "comparison": comparison["plan"],
        "group_value": first["group_value"], "evidence_revision": comparison["evidence_revision"]})
    assert found.status_code == 200, found.text
    assert found.json()["matched_entries"] == 2
    invalid = await client.post(root + "/compare", json={"aggregation": "sum", "column": "store"})
    assert invalid.status_code == 409
    app.dependency_overrides[get_current_user] = lambda: stranger
    calculate = AsyncMock()
    monkeypatch.setattr(analyses, "compare", calculate)
    forbidden = await client.post(root + "/compare", json=plan)
    assert forbidden.status_code == 404
    forbidden_rows = await client.post(root + "/entries", json={"kind": "quality", "issue_index": 0})
    assert forbidden_rows.status_code == 404
    calculate.assert_not_called()


async def test_usage_ledger_tracks_outcomes_without_changing_legacy_counters(metric_client):
    client, analysis, owner, stranger, sessions = metric_client
    successful_message = uuid.uuid4()
    failed_message = uuid.uuid4()
    unknown_message = uuid.uuid4()
    async with sessions() as db:
        await reserve_analysis(db, user_id=owner.id, analysis_id=analysis.id)
        await reserve_analysis(db, user_id=owner.id, analysis_id=analysis.id)
        await finalize_analysis(
            db, user_id=owner.id, analysis_id=analysis.id,
            status="completed", created_at=analysis.created_at,
        )
        await finalize_analysis(
            db, user_id=owner.id, analysis_id=analysis.id,
            status="failed", created_at=analysis.created_at,
        )
        await record_chat_response(
            db, user_id=owner.id, message_id=successful_message,
            metadata={"status": "succeeded", "model": "test-model",
                      "prompt_tokens": 100, "completion_tokens": 20},
        )
        await record_chat_response(
            db, user_id=owner.id, message_id=successful_message,
            metadata={"status": "succeeded", "prompt_tokens": 999},
        )
        await record_chat_response(
            db, user_id=owner.id, message_id=failed_message,
            metadata={"status": "failed", "model": "test-model"},
        )
        db.add(UsageEvent(
            user_id=owner.id, kind="ai_followup", resource_id=unknown_message,
            status="legacy_unknown", source="backfill",
        ))
        await db.commit()
    report = await client.get("/api/v1/users/me/usage-ledger")
    assert report.status_code == 200, report.text
    data = report.json()
    assert data["analysis_completed_lifetime"] == 1
    assert data["analysis_failed"] == 0
    assert data["analysis_reserved"] == 0
    assert data["ai_completed_lifetime"] == 1
    assert data["ai_failed"] == 1
    assert data["ai_legacy_unknown"] == 1
    assert data["prompt_tokens_recorded"] == 100
    assert data["completion_tokens_recorded"] == 20
    assert data["current_counter_analyses"] == 0
    assert data["current_counter_ai_queries"] == 0
    async with sessions() as db:
        events = list((await db.execute(select(UsageEvent).where(
            UsageEvent.user_id == owner.id
        ))).scalars())
        assert len(events) == 4
    from app.api.deps import get_current_user
    from app.main import app

    app.dependency_overrides[get_current_user] = lambda: stranger
    other_report = await client.get("/api/v1/users/me/usage-ledger")
    assert other_report.status_code == 200
    assert other_report.json()["analysis_completed_lifetime"] == 0
