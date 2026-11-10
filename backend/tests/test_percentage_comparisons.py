from types import SimpleNamespace
from uuid import uuid4

import polars as pl

from app.services.investigation import ComparisonPlan, compare, comparison_answer


async def test_unconfirmed_fraction_scale_survives_comparisons_and_replay(tmp_path):
    path = tmp_path / "fractions.parquet"
    pl.DataFrame({"oreb_pct": [.0540732, .06], "season": ["2020-21", "2021-22"]}).write_parquet(path)
    analysis = SimpleNamespace(id=uuid4(), row_count=2, file=SimpleNamespace(storage_path=str(path)), metadata_={"schema": [
        {"name": "oreb_pct", "is_numeric": True, "analysis_role": "metric", "semantic_type": "percentage", "percentage_scale": "unconfirmed"},
        {"name": "season", "analysis_role": "dimension"},
    ]})
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="oreb_pct"))
    assert result["groups"][0]["value"] == (.0540732 + .06) / 2
    assert "%" not in result["answer"]
    assert "raw scale" in result["answer"]
    assert "scale has not been confirmed" in result["scope"]
    result = await compare(analysis, ComparisonPlan(aggregation="average", column="oreb_pct", group_by="season"))
    assert "%" not in result["answer"]
    assert "0.06" in result["answer"]
    assert comparison_answer(result) == result["answer"]
