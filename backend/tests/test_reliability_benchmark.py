"""Known-answer files must survive the same defaults used by uploads."""
import asyncio

import pytest

from evals.reliability.run_eval import CASES, run_case


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("reverse", [False, True])
def test_source_fidelity_through_analysis(name, reverse, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", False)
    result = asyncio.run(run_case(name, tmp_path, reverse=reverse))
    assert result["passed"], result["failures"]
