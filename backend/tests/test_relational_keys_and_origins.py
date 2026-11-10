import polars as pl
import pytest

from app.services.relational_files import enrich_related_files


def test_table_scoped_bare_id_matches_named_foreign_key():
    facts = pl.DataFrame({"record_id": ["R1", "R2", "R3"], "theme_id": ["01", "01", "02"], "amount": [1, 2, 3]})
    themes = pl.DataFrame({"id": ["01", "02"], "name": ["First", "Second"]})
    joined, resolution = enrich_related_files([facts, themes], table_names=["sets.csv", "themes.csv"])
    assert resolution["status"] == "enriched" and joined.height == 3
    assert joined["name"].to_list() == ["First", "First", "Second"]
    assert joined["id"].to_list() == ["01", "01", "02"]


def test_unrelated_bare_ids_do_not_match_by_coincidental_values():
    facts = pl.DataFrame({"id": ["1", "2", "3"], "amount": [1, 2, 3]})
    lookup = pl.DataFrame({"id": ["1", "2"], "name": ["First", "Second"]})
    joined, resolution = enrich_related_files([facts, lookup], table_names=["transactions.csv", "employees.csv"])
    assert joined is None and resolution["status"] == "unresolved"


def test_repeated_missing_or_orphan_codes_do_not_establish_a_fact_grain():
    facts = pl.DataFrame({"entry_id": ["1", "2", "3", "4"], "customer_id": ["A", "B", r"\N", r"\N"]})
    lookup = pl.DataFrame({"customer_id": ["A", "B"], "name": ["First", "Second"]})
    joined, resolution = enrich_related_files([facts, lookup])
    assert joined is None and resolution["status"] == "unresolved"
    joined, resolution = enrich_related_files([facts.with_columns(
        pl.col("customer_id").replace(r"\N", "missing")), lookup])
    assert joined is None and resolution["status"] == "unresolved"


@pytest.mark.parametrize("reverse", [False, True])
def test_prefix_and_composite_keys_preserve_all_fact_rows(reverse):
    facts = pl.DataFrame({"id_record": ["1", "2", "3", "4"], "id_assessment": ["A", "A", "B", "C"], "score": [10, 20, 30, 40]})
    assessments = pl.DataFrame({"assessment_id": ["A", "B", "C"], "code_module": ["M", "M", "N"], "code_presentation": ["X", "Y", "X"]})
    courses = pl.DataFrame({"module_code": ["M", "M", "N", "N"], "presentation_code": ["X", "Y", "X", "Y"], "length": [10, 20, 30, 40]})
    frames = [facts, assessments, courses]
    joined, resolution = enrich_related_files(list(reversed(frames)) if reverse else frames)
    assert resolution["status"] == "enriched" and joined.height == 4
    assert joined["length"].to_list() == [10, 10, 20, 30]
    assert joined["score"].sum() == 100
    assert any(len(link["foreign_keys"]) == 2 for link in resolution["joins"])


def test_actual_parent_keys_remain_null_for_unmatched_references_and_have_origins():
    facts = pl.DataFrame({"item_id": ["I1", "I2", "I3", "I4"], "order_id": ["01", "01", "02", "missing"]})
    orders = pl.DataFrame({"order_id": ["01", "02"], "freight": [10, 20]})
    joined, resolution = enrich_related_files([facts, orders], table_names=["items.csv", "orders.csv"])
    assert resolution["status"] == "enriched" and joined.height == 4
    origin = resolution["field_origins"]["freight"]
    assert origin["source_table"] == "orders.csv" and origin["source_column"] == "freight"
    assert origin["repeated"] and origin["matched_entries"] == 3
    key = origin["entity_key_columns"][0]
    assert joined[key].to_list() == ["01", "01", "02", None]
    assert joined["freight"].to_list() == [10, 10, 20, None]
    assert resolution["field_origins"]["item_id"]["kind"] == "fact"


def test_declared_column_mapping_preserves_orphans_without_value_guessing():
    facts = pl.DataFrame({"athlete_id": ["1", "2", "3"], "nationality": ["AAA", "AAA", "ZZZ"]})
    countries = pl.DataFrame({"code": ["AAA", "BBB"], "country": ["First", "Second"]})
    plan = [{"from_file": "athletes", "from_columns": ["nationality"],
             "to_file": "countries", "to_columns": ["code"]}]
    joined, resolution = enrich_related_files([facts, countries], table_ids=["athletes", "countries"],
        table_names=["athletes.csv", "countries.csv"], declared_relationships=plan, fact_table="athletes")
    assert resolution["status"] == "enriched" and joined.height == 3
    assert joined["country"].to_list() == ["First", "First", None]
    assert resolution["joins"][0]["unmatched_entries"] == 1
    assert resolution["joins"][0]["declared"]


@pytest.mark.parametrize("plan", [
    [{"from_file": "other", "from_columns": ["nationality"], "to_file": "countries", "to_columns": ["code"]}],
    [{"from_file": "athletes", "from_columns": ["unknown"], "to_file": "countries", "to_columns": ["code"]}],
    [{"from_file": "athletes", "from_columns": ["nationality", "nationality"], "to_file": "countries", "to_columns": ["code", "code"]}],
])
def test_invalid_declared_links_stay_unresolved(plan):
    joined, resolution = enrich_related_files([
        pl.DataFrame({"athlete_id": ["1", "2"], "nationality": ["AAA", "AAA"]}),
        pl.DataFrame({"code": ["AAA"], "country": ["First"]}),
    ], table_ids=["athletes", "countries"], declared_relationships=plan)
    assert joined is None and resolution["reason_code"] == "invalid_declared_relationship"
