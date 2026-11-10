"""Known-answer files must survive the same defaults used by uploads."""
import asyncio

import polars as pl
import pytest

from evals.reliability.run_eval import CASES, _source_fidelity_failures, run_case


@pytest.mark.parametrize("name", CASES)
@pytest.mark.parametrize("reverse", [False, True])
def test_source_fidelity_through_analysis(name, reverse, tmp_path, monkeypatch):
    from app.core.config import settings
    monkeypatch.setattr(settings, "semantic_wrangling_enabled", False)
    result = asyncio.run(run_case(name, tmp_path, reverse=reverse))
    assert result["passed"], result["failures"]


def test_source_fidelity_uses_the_saved_camelcase_header_mapping():
    frame = pl.DataFrame({"country_code": ["NA", "US"]})
    report = {"renamed_columns": {"CountryCode": "country_code"}}
    assert _source_fidelity_failures(["CountryCode"], [["NA"], ["US"]], frame, report) == []


@pytest.mark.parametrize("column", ["other", "countrycode"])
def test_source_fidelity_still_fails_when_the_declared_source_column_is_missing(column):
    frame = pl.DataFrame({column: ["NA", "US"]})
    report = {"renamed_columns": {"CountryCode": "country_code"}}
    assert _source_fidelity_failures(["CountryCode"], [["NA"], ["US"]], frame, report) == ["Source column CountryCode was lost"]


def test_source_fidelity_keeps_original_headers_when_no_rename_is_declared():
    frame = pl.DataFrame({"CountryCode": ["NA", "US"]})
    assert _source_fidelity_failures(["CountryCode"], [["NA"], ["US"]], frame, {}) == []


def test_saved_header_mapping_does_not_hide_changed_identifier_values():
    frame = pl.DataFrame({"customer_id": ["1", "2"]})
    report = {"renamed_columns": {"Customer ID": "customer_id"}}
    assert _source_fidelity_failures(["Customer ID"], [["001"], ["002"]], frame, report) == ["Identifier values changed: Customer ID"]
