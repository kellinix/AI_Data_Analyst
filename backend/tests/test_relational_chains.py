from itertools import permutations

import polars as pl
import pytest

from app.services.file_processor import FileProcessor
from app.services.relational_files import enrich_related_files


def sourced(data, name):
    return pl.DataFrame(data).with_columns(pl.lit(name).alias("Source file"))


def chain():
    return [
        sourced({"item_id": ["I1", "I2", "I3"], "order_id": ["O1", "O1", "O2"],
                 "product_id": ["P1", "P2", "P1"], "amount": [10, 20, 30]}, "items.csv"),
        sourced({"order_id": ["O1", "O2"], "customer_id": ["C1", "C2"], "status": ["Delivered", "Paid"]}, "orders.csv"),
        sourced({"customer_id": ["C1", "C2", "C3"], "region": ["North", "South", "Unused"]}, "customers.csv"),
        sourced({"product_id": ["P1", "P2"], "category": ["Food", "Books"]}, "products.csv"),
    ]


@pytest.mark.parametrize("order", [[0, 1, 2, 3], [3, 2, 1, 0], [2, 0, 3, 1]])
def test_chain_preserves_transactions_with_one_to_one_lookup_hops(order):
    frames = chain()
    context = {"combine_strategy": "portfolio"}
    result = FileProcessor()._combine_frames([frames[index] for index in order], context)
    assert context["combine_strategy"] == "relational"
    assert result.height == 3 and result["amount"].sum() == 60
    assert result["item_id"].to_list() == ["I1", "I2", "I3"]
    assert result["region"].to_list() == ["North", "North", "South"]
    assert result["category"].to_list() == ["Food", "Books", "Food"]
    assert result["Source file"].to_list() == ["items.csv"] * 3
    resolution = context["relationship_resolution"]
    assert resolution["fact_files"] == ["items.csv"]
    assert len(resolution["joins"]) == 3


def test_many_to_many_tables_are_not_expanded_or_aggregated():
    sales = sourced({"customer_id": ["C1", "C1"], "sale": [10, 20]}, "sales.csv")
    tickets = sourced({"customer_id": ["C1", "C1"], "ticket": [30, 40]}, "tickets.csv")
    combined, resolution = enrich_related_files([sales, tickets])
    assert combined is None and resolution["status"] == "unresolved"
    stacked = FileProcessor()._combine_frames([sales, tickets], {})
    assert stacked.height == 4 and stacked["sale"].sum() == 30 and stacked["ticket"].sum() == 70


@pytest.mark.parametrize("reverse", [False, True])
def test_ambiguous_alternate_paths_are_rejected_in_every_input_order(reverse):
    facts = sourced({"event_id": ["E1", "E2", "E3"], "employee_id": ["U1", "U2", "U3"],
                     "department_code": ["A", "A", "B"], "amount": [10, 20, 30]}, "events.csv")
    departments = sourced({"department_code": ["A", "B"], "department_name": ["First", "Second"]}, "departments.csv")
    # Staff metadata contradicts the fact table's department association.
    employees = sourced({"employee_id": ["U1", "U2", "U3"], "department_code": ["B", "B", "A"]}, "employees.csv")
    lookups = [employees, departments] if reverse else [departments, employees]
    combined, resolution = enrich_related_files([facts, *lookups])
    assert combined is None
    assert resolution["status"] == "unresolved"


@pytest.mark.parametrize("order", [[0, 1, 2], [2, 1, 0]])
def test_renamed_lookup_identifier_is_used_for_the_next_hop(order):
    facts = sourced({"item_id": ["I1", "I2", "I3"], "order_id": ["O1", "O1", "O2"],
                     "external_id": ["X1", "X2", "X3"], "amount": [10, 20, 30],
                     "__relationship_key": ["keep1", "keep2", "keep3"]}, "items.csv")
    orders = sourced({"order_id": ["O1", "O2"], "external_id": ["E1", "E1"]}, "orders.csv")
    external = sourced({"external_id": ["E1", "E2"], "region": ["Expected", "Unused"]}, "external.csv")
    frames = [facts, orders, external]
    combined, resolution = enrich_related_files([frames[index] for index in order])
    assert combined is not None and resolution["status"] == "enriched"
    assert combined.height == 3 and combined["amount"].sum() == 60
    assert combined["region"].to_list() == ["Expected"] * 3
    assert combined["external_id"].to_list() == ["X1", "X2", "X3"]
    assert combined["__relationship_key"].to_list() == ["keep1", "keep2", "keep3"]
    renamed = next(join["renamed_fields"]["external_id"] for join in resolution["joins"] if "external_id" in join["renamed_fields"])
    assert combined[renamed].to_list() == ["E1"] * 3


@pytest.mark.parametrize("reverse", [False, True])
def test_equivalent_paths_on_the_same_identifier_do_not_create_false_ambiguity(reverse):
    facts = sourced({"event_id": ["E1", "E2", "E3"], "customer_id": ["C1", "C1", "C2"], "amount": [10, 20, 30]}, "events.csv")
    names = sourced({"customer_id": ["C1", "C2"], "name": ["First", "Second"]}, "names.csv")
    regions = sourced({"customer_id": ["C1", "C2"], "region": ["North", "South"]}, "regions.csv")
    lookups = [regions, names] if reverse else [names, regions]
    combined, resolution = enrich_related_files([facts, *lookups])
    assert combined is not None and resolution["status"] == "enriched"
    assert combined.height == 3 and combined["amount"].sum() == 60
    assert combined["name"].to_list() == ["First", "First", "Second"]
    assert combined["region"].to_list() == ["North", "North", "South"]


@pytest.mark.parametrize("order", list(permutations(range(4))))
@pytest.mark.parametrize("conflicting", [True, False])
def test_ambiguous_pair_keeps_all_identifier_constraints_after_a_bridge_join(order, conflicting):
    facts = sourced({"employee_id": ["U1", "U2", "U3"], "department_code": ["A", "B", "C"],
                     "team_id": ["T1", "T1", "T2"], "amount": [10, 20, 30]}, "events.csv")
    employees = sourced({"employee_id": ["U1", "U2", "U3"],
                         "department_code": ["B", "C", "A"] if conflicting else ["A", "B", "C"],
                         "name": ["e1", "e2", "e3"]}, "employees.csv")
    departments = sourced({"department_code": ["A", "B", "C"],
                           "department_name": ["First", "Second", "Third"]}, "departments.csv")
    teams = sourced({"team_id": ["T1", "T2"], "team_name": ["One", "Two"]}, "teams.csv")
    frames = [facts, employees, departments, teams]
    combined, resolution = enrich_related_files([frames[index] for index in order])
    if conflicting:
        assert combined is None and resolution["status"] == "unresolved"
    else:
        assert combined is not None and resolution["status"] == "enriched"
        assert combined["employee_id"].to_list() == ["U1", "U2", "U3"]
        assert combined["name"].to_list() == ["e1", "e2", "e3"]
        assert combined["department_name"].to_list() == ["First", "Second", "Third"]
        assert combined["team_name"].to_list() == ["One", "One", "Two"]
        assert combined["amount"].to_list() == [10, 20, 30]


@pytest.mark.parametrize("reverse", [False, True])
@pytest.mark.parametrize("conflicting", [False, True])
def test_multiple_unique_identifier_associations_are_checked_without_a_fact_anchor(reverse, conflicting):
    facts = sourced({"employee_id": ["U1", "U2", "U3"], "department_code": ["A", "B", "C"],
                     "amount": [10, 20, 30]}, "events.csv")
    employees = sourced({"employee_id": ["U1", "U2", "U3"],
                         "department_code": ["B", "C", "A"] if conflicting else ["A", "B", "C"],
                         "name": ["First", "Second", "Third"]}, "employees.csv")
    frames = [employees, facts] if reverse else [facts, employees]
    combined, resolution = enrich_related_files(frames)
    assert combined is None and resolution["status"] == "unresolved"
    assert (resolution.get("reason_code") == "conflicting_identifiers") is conflicting


def test_explicit_single_key_join_cannot_override_conflicting_identifier_constraints():
    facts = sourced({"employee_id": ["U1", "U2", "U3"], "department_code": ["A", "B", "C"],
                     "amount": [10, 20, 30]}, "events.csv")
    employees = sourced({"employee_id": ["U1", "U2", "U3"], "department_code": ["B", "C", "A"],
                         "name": ["First", "Second", "Third"]}, "employees.csv")
    context = {"combine_strategy": "join", "suggestions": [{"type": "join", "columns": ["employee_id"]}]}
    FileProcessor()._combine_frames([facts, employees], context)
    assert context["combine_strategy"] == "portfolio"
    assert context["relationship_resolution"]["status"] == "unresolved"
    assert context["relationship_resolution"]["reason_code"] == "conflicting_identifiers"
