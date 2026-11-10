import polars as pl
import pytest
from fastapi import HTTPException

from app.api.v1.endpoints.analyses import _require_resolved_relationship
from app.services.file_processor import FileProcessor


def test_unresolved_combination_is_rejected_before_report_creation():
    with pytest.raises(HTTPException) as caught:
        _require_resolved_relationship({"relationship_resolution": {"status": "unresolved", "reason": "Repeated keys on both sides."}})
    assert caught.value.status_code == 422
    assert "matched safely" in caught.value.detail


def test_explicit_unique_key_join_remains_supported():
    context = {"combine_strategy": "join", "suggestions": [{"type": "join", "columns": ["region"]}]}
    result = FileProcessor()._combine_frames([
        pl.DataFrame({"region": ["UK", "US"], "sales": [10, 20]}),
        pl.DataFrame({"region": ["UK", "CA"], "cost": [3, 4]}),
    ], context)
    _require_resolved_relationship(context)
    assert result.height == 3
    assert result["sales"].sum() == 30 and result["cost"].sum() == 7
    assert context["relationship_resolution"]["status"] == "joined"
