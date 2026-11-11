"""Native cache names cannot replace original upload source identities."""

from __future__ import annotations

import mimetypes
import uuid
from datetime import UTC, datetime
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import Mock

import httpx
import polars as pl
import pytest
from fastapi import FastAPI

from app.analytics.data_dictionary import apply_data_dictionary
from app.analytics.measure_grain import annotate_measure_grain
from app.api.deps import get_current_user
from app.api.v1.endpoints import uploads
from app.api.v1.endpoints.analyses import _cleaning_options, _dictionary_upload_context
from app.db.session import get_db
from app.services.analysis_engine import compute_analysis
from app.services.file_processor import FileProcessor
from evals.calibration.run_eval import _OfflineAIService


@pytest.fixture
async def upload_client(tmp_path, monkeypatch):
    saved = []
    owner = SimpleNamespace(id=uuid.uuid4(), storage_used_bytes=0)

    class Database:
        def add(self, item):
            saved.append(item)

        async def flush(self):
            pass

        async def refresh(self, item):
            item.id = uuid.uuid4()
            item.created_at = datetime.now(UTC)
            item.updated_at = item.created_at

    async def database():
        yield Database()

    app = FastAPI()
    app.include_router(uploads.router, prefix="/api/v1/uploads")
    app.dependency_overrides[get_db] = database
    app.dependency_overrides[get_current_user] = lambda: owner
    monkeypatch.setattr(uploads.settings, "upload_dir", str(tmp_path / "uploads"))
    monkeypatch.setattr(uploads.limiter, "enabled", False)
    quota = Mock()
    monkeypatch.setattr(uploads, "ensure_storage_quota", quota)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        yield SimpleNamespace(client=client, saved=saved, owner=owner, quota=quota)


@pytest.mark.parametrize("original_name", [
    "inventory.csv", "Annual stock 2026.csv", "Résumé #1? 20%.csv",
    'report"; name="renamed.csv', "l'année.csv", " stock.csv",
])
async def test_native_filename_metadata_preserves_exact_source_identity(upload_client, original_name):
    content = b"Product_ID,Stock_On_Hand\nP1,2\nP2,3\n"
    response = await upload_client.client.post(
        "/api/v1/uploads",
        data={"original_filename": original_name},
        files={"file": (f"{uuid.uuid4()}.bin", content, "application/octet-stream")},
    )
    assert response.status_code == 201, response.text
    body = response.json()
    assert body["original_filename"] == original_name
    assert body["filename"] != original_name
    assert Path(body["storage_path"]).suffix == ".csv"
    assert Path(body["storage_path"]).read_bytes() == content
    assert body["mime_type"] == mimetypes.guess_type(original_name)[0]
    assert body["row_count"] == 2
    assert {column["name"] for column in body["columns"]} == {"Product_ID", "Stock_On_Hand"}
    upload_client.quota.assert_called_once_with(upload_client.owner, len(content))
    assert upload_client.owner.storage_used_bytes == len(content)

    context = {"data_dictionary": {"version": 1, "fields": [{
        "source_table": original_name, "source_column": "Stock_On_Hand", "label": "Units in stock",
    }]}}
    fields = apply_data_dictionary(body["columns"], context, file_name=body["original_filename"])
    field = next(field for field in fields if field["name"] == "Stock_On_Hand")
    assert field["display_label"] == "Units in stock"
    assert field["data_definition"]["source_table"] == original_name


async def test_old_upload_callers_keep_the_multipart_filename(upload_client):
    response = await upload_client.client.post(
        "/api/v1/uploads", files={"file": ("legacy.csv", b"id,amount\nA,2\nB,3\n", "text/csv")},
    )
    assert response.status_code == 201, response.text
    assert response.json()["original_filename"] == "legacy.csv"
    assert response.json()["row_count"] == 2


@pytest.mark.parametrize("original_name", [
    "", " ", "../inventory.csv", "folder/inventory.csv", "folder\\inventory.csv",
    "bad\nname.csv", "bad\0name.csv", "bad\x80name.csv", "unsupported.exe", "x" * 513 + ".csv",
])
async def test_malformed_original_name_is_rejected_before_storage(upload_client, original_name):
    response = await upload_client.client.post(
        "/api/v1/uploads", data={"original_filename": original_name},
        files={"file": ("cache.csv", b"amount\n2\n", "text/csv")},
    )
    assert response.status_code in {400, 422}, response.text
    assert upload_client.saved == []
    assert upload_client.owner.storage_used_bytes == 0
    upload_client.quota.assert_not_called()


async def test_native_upload_names_reach_relationships_and_combined_guide_binding(upload_client, tmp_path):
    sources = {
        "inventory.csv": b"Store_ID,Product_ID,Stock_On_Hand\nS1,P1,2\nS1,P2,3\nS2,P1,4\n",
        "products.csv": b"Product_ID,Product_Name\nP1,Blocks\nP2,Puzzle\n",
        "stores.csv": b"Store_ID,Store_Name\nS1,Downtown\nS2,Airport\n",
    }
    responses = []
    for name, content in sources.items():
        response = await upload_client.client.post(
            "/api/v1/uploads", data={"original_filename": name},
            files={"file": (f"{uuid.uuid4()}.csv", content, "text/csv")},
        )
        assert response.status_code == 201, response.text
        responses.append(response.json())
    assert [file["original_filename"] for file in responses] == list(sources)
    assert [column["name"] for column in responses[0]["columns"]][:2] == ["Store_ID", "Product_ID"]
    context = _dictionary_upload_context({"data_dictionary": {"version": 1, "fields": [{
        "source_table": "inventory.csv", "source_column": "Stock_On_Hand", "label": "Units in stock",
    }]}}, upload_client.saved)
    assert [file["name"] for file in context["source_files"]] == list(sources)
    output = tmp_path / "combined.parquet"
    profile = await FileProcessor().combine_uploaded_files(upload_client.saved, str(output), context)
    assert context["relationship_resolution"]["status"] == "enriched"
    assert profile["row_count"] == 3
    frame = pl.read_parquet(output)
    assert frame["Stock_On_Hand"].sum() == 9
    assert frame["Product_Name"].to_list() == ["Blocks", "Puzzle", "Blocks"]
    assert frame["Store_Name"].to_list() == ["Downtown", "Downtown", "Airport"]
    fields = apply_data_dictionary(annotate_measure_grain(profile["columns"], context), context)
    field = next(field for field in fields if field.get("data_definition"))
    assert field["display_label"] == "Units in stock"
    assert field["data_definition"]["source_table"] == "inventory.csv"


@pytest.mark.parametrize("mode", ["raw", "clean"])
@pytest.mark.parametrize("content,column,numeric", [
    ("amount\n2\n3\n", "amount", True),
    ("Category\nToys\nGames\n", "Category", False),
    ("Invoice_Date\n2025-01-01\n2025-02-01\n", "Invoice_Date", False),
    ("Temperature\n2\n3\n", "Temperature", True),
    ("2\n3\n", "column_1", True),
    ("North\nSouth\n", "column_1", False),
    ("2025-01-01\n2025-02-01\n", "column_1", False),
])
async def test_single_column_upload_and_analysis_keep_data_rows(
    upload_client, tmp_path, monkeypatch, mode, content, column, numeric,
):
    monkeypatch.setattr(uploads.settings, "semantic_wrangling_enabled", False)
    response = await upload_client.client.post(
        "/api/v1/uploads", files={"file": ("single.csv", content.encode(), "text/csv")},
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["row_count"] == 2
    assert uploaded["column_count"] == 1
    assert uploaded["columns"][0]["name"] == column
    processor = FileProcessor()
    storage_path = uploaded["storage_path"]
    context = {"analysis_mode": "single", "current_file_name": "single.csv"}
    if mode == "clean":
        output = tmp_path / "cleaned.parquet"
        profile = await processor.clean_file(
            storage_path, ".csv", str(output), str(tmp_path / "cleaned.csv"),
            _cleaning_options({"mode": "clean"}),
        )
        storage_path = str(output)
        context["cleaning"] = {"enabled": True, "mode": "clean", "source_filename": "single.csv",
                               "report": profile["cleaning_report"]}
    computed = await compute_analysis(
        file_processor=processor, ai_service=_OfflineAIService(), storage_path=storage_path,
        file_name="single.csv", analysis_id=str(uuid.uuid4()), upload_context=context,
    )
    expected_column = column.lower() if mode == "clean" else column
    assert computed["row_count"] == 2
    assert [field["name"] for field in computed["statistics"]["schema"]] == [expected_column]
    if numeric:
        values = computed["statistics"]["numeric_stats"][expected_column]
        assert values["count"] == 2
        assert values["total"] == 5


@pytest.mark.parametrize("content,column,rows", [
    ("amount\n", "amount", 0),
    ("North\n", "column_1", 1),
])
async def test_header_only_upload_and_singleton_list(upload_client, content, column, rows):
    response = await upload_client.client.post(
        "/api/v1/uploads", files={"file": ("single.csv", content.encode(), "text/csv")},
    )
    assert response.status_code == 201, response.text
    uploaded = response.json()
    assert uploaded["row_count"] == rows
    assert uploaded["column_count"] == 1
    assert uploaded["columns"][0]["name"] == column
