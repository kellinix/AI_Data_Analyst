from itertools import permutations

import polars as pl
import pytest

from app.analytics.measure_grain import annotate_measure_grain
from app.services.relational_files import enrich_related_files


def role_field(resolution, source, column, role):
    return next(name for name, origin in resolution["field_origins"].items()
                if origin["source_table"] == source and origin["source_column"] == column
                and origin.get("source_role") == role)


@pytest.mark.parametrize("order", list(permutations(range(3))))
def test_automatic_lookup_roles_and_chains_preserve_rows_and_nullable_parent_keys(order):
    facts = pl.DataFrame({"route_id": ["R1", "R2", "R3", "R4", "R5"],
        "Source airport ID": ["01", "01", "02", "missing", None],
        "Destination airport ID": ["02", "03", "01", "02", "missing"], "amount": [1, 2, 3, 4, 5]})
    airports = pl.DataFrame({"Airport ID": ["01", "02", "03"], "Name": ["Alpha", "Beta", "Gamma"],
        "Country code": ["X", "Y", "X"]})
    countries = pl.DataFrame({"Country code": ["X", "Y"], "Country name": ["First", "Second"]})
    frames, names = [facts, airports, countries], ["routes.csv", "airports.csv", "countries.csv"]
    joined, resolution = enrich_related_files([frames[index] for index in order],
        table_names=[names[index] for index in order])
    assert joined is not None and resolution["status"] == "enriched"
    assert joined.height == 5 and joined["route_id"].to_list() == facts["route_id"].to_list()
    assert joined["amount"].sum() == 15
    for role, expected, country in [
        ("source_airport", ["Alpha", "Alpha", "Beta", None, None], ["First", "First", "Second", None, None]),
        ("destination_airport", ["Beta", "Gamma", "Alpha", "Beta", None], ["Second", "First", "First", "Second", None]),
    ]:
        name = role_field(resolution, "airports.csv", "Name", role)
        assert joined[name].to_list() == expected
        origin = resolution["field_origins"][name]
        key = origin["entity_key_columns"][0]
        assert origin["key_basis"] == "parent_primary"
        assert joined[key].null_count() == expected.count(None)
        assert resolution["field_origins"][key]["source_role"] == role
        field = role_field(resolution, "countries.csv", "Country name", role)
        assert joined[field].to_list() == country
        assert len(resolution["field_origins"][field]["relationship_path"]) == 2
    assert len(resolution["joins"]) == 4


def test_declared_roles_support_original_columns_without_identifier_name_guesses():
    facts = pl.DataFrame({"entry": [1, 2, 3], "Origin ref": ["0001", "0001", "lost"],
                         "Destination ref": ["0002", "0001", None]})
    places = pl.DataFrame({"Code": ["0001", "0002"], "Name": ["First", "Second"]})
    plan = [{"from_file": "facts", "from_columns": [column], "to_file": "places", "to_columns": ["Code"]}
            for column in ["Origin ref", "Destination ref"]]
    joined, resolution = enrich_related_files([facts, places], table_names=["entries.csv", "places.csv"],
        table_ids=["facts", "places"], declared_relationships=plan, fact_table="facts")
    assert resolution["status"] == "enriched" and joined.height == 3
    assert joined[role_field(resolution, "places.csv", "Name", "origin_ref")].to_list() == ["First", "First", None]
    assert joined[role_field(resolution, "places.csv", "Name", "destination_ref")].to_list() == ["Second", "First", None]
    assert all(join["declared"] for join in resolution["joins"])


def test_composite_lookup_roles_keep_every_parent_key_part():
    facts = pl.DataFrame({"record_id": ["R1", "R2", "R3"], "tenant_code": ["T", "T", "U"],
        "source_place_id": ["01", "01", "02"], "destination_place_id": ["02", "01", "01"]})
    places = pl.DataFrame({"tenant_code": ["T", "T", "U", "U"], "place_id": ["01", "02", "01", "02"],
        "name": ["T1", "T2", "U1", "U2"]})
    joined, resolution = enrich_related_files([facts, places], table_names=["events.csv", "places.csv"])
    assert resolution["status"] == "enriched" and joined.height == 3
    for role, expected in [("source_place", ["T1", "T1", "U2"]), ("destination_place", ["T2", "T1", "U1"])]:
        name = role_field(resolution, "places.csv", "name", role)
        assert joined[name].to_list() == expected
        assert len(resolution["field_origins"][name]["entity_key_columns"]) == 2


def test_shared_lookup_reached_through_distinct_entities_has_separate_roles():
    facts = pl.DataFrame({"entry_id": [1, 2, 3], "customer_id": ["A", "A", "B"], "warehouse_id": ["X", "Y", "X"]})
    customers = pl.DataFrame({"customer_id": ["A", "B", "C"], "country_id": ["K", "L", "L"]})
    warehouses = pl.DataFrame({"warehouse_id": ["X", "Y"], "country_id": ["L", "L"]})
    countries = pl.DataFrame({"country_id": ["K", "L"], "name": ["First", "Second"]})
    joined, resolution = enrich_related_files([facts, customers, warehouses, countries],
        table_names=["entries.csv", "customers.csv", "warehouses.csv", "countries.csv"])
    assert resolution["status"] == "enriched" and joined.height == 3
    assert joined[role_field(resolution, "countries.csv", "name", "customers")].to_list() == ["First", "First", "Second"]
    assert joined[role_field(resolution, "countries.csv", "name", "warehouses")].to_list() == ["Second"] * 3


def test_declared_cycles_and_non_unique_parent_keys_are_rejected():
    left = pl.DataFrame({"left_id": ["A", "B"], "right_id": ["X", "Y"], "value": [1, 2]})
    right = pl.DataFrame({"right_id": ["X", "Y"], "left_id": ["A", "B"]})
    plan = [
        {"from_file": "left", "from_columns": ["right_id"], "to_file": "right", "to_columns": ["right_id"]},
        {"from_file": "right", "from_columns": ["left_id"], "to_file": "left", "to_columns": ["left_id"]},
    ]
    joined, resolution = enrich_related_files([left, right], table_ids=["left", "right"], declared_relationships=plan)
    assert joined is None and resolution["reason_code"] == "invalid_declared_relationship"
    assert "cycle" in resolution["reason"]
    joined, resolution = enrich_related_files([left, pl.DataFrame({"right_id": ["X", "X"]})],
        table_ids=["left", "right"], declared_relationships=plan[:1])
    assert joined is None and resolution["reason_code"] == "invalid_declared_relationship"


def test_missing_composite_key_reference_remains_visible_after_schema_annotation():
    fields = [{"name": "amount"}, {"name": "tenant_id"}]
    origin = {"kind": "lookup", "entity_key_columns": ["tenant_id", "missing_id"]}
    result = annotate_measure_grain(fields, {"relationship_resolution": {"field_origins": {"amount": origin}}})
    assert result[0]["measure_grain"]["entity_key_columns"] == ["tenant_id", "missing_id"]


def test_partial_context_cannot_erase_known_repeated_lookup_provenance():
    origin = {"source_table": "parents.csv", "source_column": "amount", "kind": "lookup", "repeated": True,
        "entity_key_columns": ["parent_id"], "key_basis": "parent_primary"}
    fields = [{"name": "amount", "measure_grain": origin}, {"name": "parent_id"}]
    partial = {"source_table": "parents.csv", "source_column": "amount"}
    result = annotate_measure_grain(fields, {"relationship_resolution": {"field_origins": {"amount": partial}}})
    assert result[0]["measure_grain"] == origin


def test_conflicting_provenance_cannot_enable_source_entity_aggregation():
    origin = {"source_table": "parents.csv", "kind": "lookup", "repeated": True,
        "entity_key_columns": ["parent_id"], "key_basis": "parent_primary"}
    fields = [{"name": "amount", "measure_grain": origin}, {"name": "parent_id"}]
    conflicting = {**origin, "source_table": "other.csv", "repeated": False, "kind": "fact"}
    result = annotate_measure_grain(fields, {"relationship_resolution": {"field_origins": {"amount": conflicting}}})
    actual = result[0]["measure_grain"]
    assert actual["kind"] == "lookup" and actual["repeated"] is True
    assert actual["key_basis"] == "conflicting_sources" and actual["entity_key_columns"] == []


def test_declared_relationships_cannot_join_same_schema_partitions_to_themselves():
    frame = pl.DataFrame({"id": ["A"], "parent_id": ["A"]})
    plan = [{"from_file": "left", "from_columns": ["parent_id"], "to_file": "right", "to_columns": ["id"]}]
    joined, resolution = enrich_related_files([frame, frame], table_ids=["left", "right"],
        declared_relationships=plan)
    assert joined is None and resolution["reason_code"] == "invalid_declared_relationship"


def test_role_keys_keep_case_zeroes_internal_spaces_and_native_payload_types():
    facts = pl.DataFrame({"entry_id": [1, 2, 3, 4], "source_place_id": ["01", "01", "A B", "AB"],
        "destination_place_id": ["01", "a b", "AB", "missing"]})
    places = pl.DataFrame({"place_id": ["01", "A B", "AB", "a b"], "capacity": [10, 20, 30, 40]})
    joined, resolution = enrich_related_files([facts, places], table_names=["entries.csv", "places.csv"])
    assert joined is not None and joined.height == 4
    source = role_field(resolution, "places.csv", "capacity", "source_place")
    destination = role_field(resolution, "places.csv", "capacity", "destination_place")
    assert joined[source].to_list() == [10, 10, 20, 30]
    assert joined[destination].to_list() == [10, 40, 30, None]
    assert joined[source].dtype == places["capacity"].dtype


def test_reused_pre_enriched_table_preserves_inner_role_identity_and_key_paths():
    workbook = pl.DataFrame({"trip_id": ["T1", "T2"], "Airport key": ["A", "B"], "Population": [100, 200]})
    inner_path = [{"from_table": "Trips", "from_columns": ["source_airport_id"],
        "to_table": "Airports", "to_columns": ["airport_id"]}]
    origin = {"source_table": "Airports", "source_sheet": "Airports", "kind": "lookup",
        "repeated": False, "entity_key_columns": ["Airport key"], "key_basis": "parent_primary",
        "source_role": "source_airport", "source_role_label": "Source airport", "relationship_path": inner_path}
    origins = {"Airport key": {**origin, "source_column": "airport_id"},
        "Population": {**origin, "source_column": "Population"}}
    facts = pl.DataFrame({"entry_id": [1, 2, 3], "primary_trip_id": ["T1", "T1", "T2"],
        "secondary_trip_id": ["T2", "T1", "T1"]})
    joined, resolution = enrich_related_files([facts, workbook], table_names=["entries.csv", "trips.xlsx"],
        table_origins=[{}, origins])
    assert joined is not None and joined.height == 3
    for role in ["primary_trip/source_airport", "secondary_trip/source_airport"]:
        field = role_field(resolution, "Airports", "Population", role)
        measure = resolution["field_origins"][field]
        key = measure["entity_key_columns"][0]
        assert len(measure["relationship_path"]) == 2
        assert resolution["field_origins"][key]["source_role"] == role
        assert resolution["field_origins"][key]["relationship_path"] == measure["relationship_path"]
