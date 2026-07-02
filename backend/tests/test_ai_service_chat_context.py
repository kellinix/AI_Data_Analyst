from __future__ import annotations

from types import SimpleNamespace

import pytest

pytest.importorskip("pydantic_settings")

from app.services.ai_service import (
    _chart_config_markdown_answer,
    _compute_team_performance_context,
    _known_metric_notes,
)


def test_known_metric_notes_explain_goals_opponent():
    analysis = SimpleNamespace(
        metadata_={
            "schema": [
                {"name": "team", "is_numeric": False},
                {"name": "goals_team", "is_numeric": True},
                {"name": "goals_opponent", "is_numeric": True},
            ]
        }
    )

    notes = _known_metric_notes(analysis)

    assert "goals_opponent" in notes
    assert "opposing team" in notes
    assert "lower values" in notes


def test_chart_config_markdown_answer_uses_attached_values():
    answer = _chart_config_markdown_answer(
        {
            "title": "Top 5 Teams by Goals Scored",
            "yAxis": "Goals scored",
            "echarts_option": {
                "xAxis": {"data": ["Brazil", "France"]},
                "series": [{"name": "Goals scored", "data": [42, 39]}],
            },
        }
    )

    assert "Brazil" in answer
    assert "42 goals scored" in answer
    assert "France" in answer
    assert "hypothetical" not in answer.lower()


@pytest.mark.asyncio
async def test_team_performance_context_ranks_teams_from_uploaded_file(tmp_path):
    pytest.importorskip("duckdb")

    csv_path = tmp_path / "football.csv"
    csv_path.write_text(
        "\n".join(
            [
                "team,goals_team,goals_opponent,goals,match_result",
                "Alpha,2,1,1,W",
                "Alpha,1,1,0,D",
                "Alpha,3,1,2,W",
                "Beta,1,2,1,L",
                "Beta,0,1,0,L",
                "Beta,2,2,1,D",
            ]
        ),
        encoding="utf-8",
    )
    analysis = SimpleNamespace(
        file=SimpleNamespace(storage_path=str(csv_path)),
        metadata_={
            "schema": [
                {"name": "team", "is_numeric": False},
                {"name": "goals_team", "is_numeric": True},
                {"name": "goals_opponent", "is_numeric": True},
                {"name": "goals", "is_numeric": True},
                {"name": "match_result", "is_numeric": False},
            ]
        },
    )

    context = await _compute_team_performance_context(
        analysis,
        "Which team performed better overall?",
    )

    assert "Team performance aggregate computed" in context
    assert context.index("Alpha") < context.index("Beta")
    assert "win_rate=66.7%" in context
    assert "avg_goal_diff=1.00" in context
