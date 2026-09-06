"""Rendering must preserve evidence and show disclosure failures as failures."""
from copy import deepcopy

import pytest

from okf_bq_graph.report import governance_table


CASES = [("rls_hidden_intermediate", "hidden intermediate (`metrics/gross-margin`) inside GQL walk"),
         ("rls_natural", "natural question on RLS dataset"),
         ("rls_impact", "impact on RLS dataset"),
         ("authorized_views", "authorized views as graph inputs")]


def _row(table, label):
    return next(line for line in table.splitlines() if line.startswith(f"| {label} |"))


@pytest.mark.parametrize("case_name,label", CASES)
@pytest.mark.parametrize("recorded_flag", [True, False])
def test_retained_hidden_id_is_a_failure_without_mutating_record(case_name, label, recorded_flag):
    case = {"status": "OK", "leaks_hidden_id": recorded_flag, "verdict": "LEAK_OR_UNEXPECTED",
            "graph_over_views": "ACCEPTED", "full_result": {"path": ["acme|p1|Concept|metrics/gross-margin"]}}
    evidence = {"governance": {case_name: case}}
    original = deepcopy(evidence)
    row = _row(governance_table(evidence), label)
    assert "FAIL/LEAK" in row.split(" | ")[-1]
    assert "HIDDEN ID PRESENT" in row
    assert f"leaks_hidden_id={recorded_flag}" in row
    assert evidence == original
    if case_name == "authorized_views":
        assert "graph-input acceptance: ACCEPTED" in row
        assert "no-leak claim checked" not in row and "filtered view removes" not in row


@pytest.mark.parametrize("case_name,label", CASES)
def test_unretained_positive_flag_remains_inconclusive(case_name, label):
    case = {"status": "OK", "leaks_hidden_id": True, "verdict": "LEAK_OR_UNEXPECTED", "graph_over_views": "ACCEPTED"}
    row = _row(governance_table({"governance": {case_name: case}}), label)
    assert "INCONCLUSIVE" in row.split(" | ")[-1]
    assert "leaks_hidden_id=True" in row


def test_absent_view_run_is_not_run():
    row = _row(governance_table({}), "authorized views as graph inputs")
    assert row.split(" | ")[-1] == "NOT_RUN |"


def test_clean_retained_payload_does_not_erase_recorded_positive_flag():
    case = {"status": "OK", "leaks_hidden_id": True, "verdict": "LEAK_OR_UNEXPECTED",
            "full_result": {"seed": "metrics/gross-margin-legacy"}}
    row = _row(governance_table({"governance": {"rls_natural": case}}), "natural question on RLS dataset")
    assert "FAIL (recorded positive leak flag" in row.split(" | ")[-1]
    assert "leaks_hidden_id=True" in row and "LEAK_OR_UNEXPECTED" in row


def test_successful_negative_full_payload_is_enforced():
    case = {"status": "OK", "leaks_hidden_id": False, "verdict": "ENFORCED",
            "full_result": {"seed": "metrics/gross-margin-legacy"}}
    row = _row(governance_table({"governance": {"rls_natural": case}}), "natural question on RLS dataset")
    assert row.split(" | ")[-1] == "ENFORCED |"
