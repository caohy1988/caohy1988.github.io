"""Hermetic gates on the ordinary-SQL baseline scaffold (2026-09-19 pack, Slice A).

No client, no network, no cloud. These tests exist to stop the scaffold from quietly becoming a
result: a cell that acquires a number, a prior observation that starts filling a cell, a committed
card that drifts from its generator, or a cost row that disappears instead of saying UNMEASURED.
"""
import copy
import json

import pytest

from okf_bq_graph import sql_baseline as sb


@pytest.fixture(scope="module")
def plan():
    return sb.load_plan()


@pytest.fixture(scope="module")
def card(plan):
    return sb.build_card(copy.deepcopy(plan))


def test_shipped_plan_validates(plan):
    sb.validate_plan(plan)


@pytest.mark.parametrize("drop", ["version", "engine", "corpus", "questions", "budget", "metrics",
                                  "retrieval_cells", "consumer_cells", "cost_cells"])
def test_plan_requires_every_envelope_section(plan, drop):
    broken = {k: v for k, v in plan.items() if k != drop}
    with pytest.raises(ValueError, match=drop):
        sb.validate_plan(broken)


def test_sample_counts_must_be_predeclared(plan):
    broken = copy.deepcopy(plan)
    del broken["retrieval_cells"][0]["measured"]
    with pytest.raises(ValueError, match="does not predeclare"):
        sb.validate_plan(broken)


def test_one_concurrency_is_not_a_concurrency_answer(plan):
    broken = copy.deepcopy(plan)
    broken["retrieval_cells"] = [c for c in broken["retrieval_cells"] if c["concurrency"] == 1]
    with pytest.raises(ValueError, match="proposed concurrency beside C=1"):
        sb.validate_plan(broken)


def test_c1_is_required(plan):
    broken = copy.deepcopy(plan)
    for cell in broken["retrieval_cells"]:
        cell["concurrency"] = 5
    with pytest.raises(ValueError, match="C=1 retrieval cell"):
        sb.validate_plan(broken)


def test_both_latencies_must_be_defined(plan):
    broken = copy.deepcopy(plan)
    del broken["metrics"]["request_to_consumer_ms"]
    with pytest.raises(ValueError, match="request_to_consumer_ms"):
        sb.validate_plan(broken)


def test_prior_observations_take_the_edition_from_the_jobs():
    """`report.md` calls both forced observations on-demand; one of them ran on the reservation."""
    priors = {p["source"]: p for p in sb.prior_observations()}
    enterprise = priors["evidence/all_all-0017.json#fallback_forced"]
    ondemand = priors["evidence/landmine_forced_fallback.json"]
    assert enterprise["edition"] == "ENTERPRISE"
    assert enterprise["reservation"], "an ENTERPRISE observation must name the reservation it ran on"
    assert ondemand["edition"] == "on-demand"
    assert ondemand["reservation"] is None


def test_priors_are_retrieval_only_and_c1():
    for prior in sb.prior_observations():
        assert prior["metric"] == "retrieval_ms"
        assert prior["concurrency"] == 1
        assert prior["retrieval_ms"] > 0


def test_no_prior_observation_fills_a_cell(card):
    assert card["prior_observations"], "the recorded SQL observations must be carried, not dropped"
    for prior in card["prior_observations"]:
        assert prior["fills_cell"] is False
        assert prior["why_not_a_cell"]
    for cell in card["cells"]:
        assert cell["measured_n"] == 0


def test_a_prior_that_claims_to_fill_a_cell_fails_the_build(card):
    tampered = copy.deepcopy(card)
    tampered["cells"][0]["prior_observations"].append({"fills_cell": True})
    with pytest.raises(ValueError, match="claims to fill the cell"):
        sb.assert_no_cell_is_filled(tampered)


def test_a_cell_that_acquires_a_number_fails_the_build(card):
    tampered = copy.deepcopy(card)
    tampered["cells"][0]["p95_ms"] = 4900.0
    with pytest.raises(ValueError, match="p95_ms is set"):
        sb.assert_no_cell_is_filled(tampered)


def test_every_cell_is_empty_and_says_why(card):
    assert card["state"] == "SCAFFOLD_ONLY"
    for cell in card["cells"]:
        assert cell["state"] == "INCOMPLETE"
        assert cell["stopped_reason"] in ("NOT_RUN_DRIVER_MISSING", "NOT_IMPLEMENTED")
        assert cell["how_to_fill"]
        for field in ("p50_ms", "p95_ms", "max_ms", "success_rate", "bytes_billed", "usd_ondemand_list"):
            assert cell[field] is None


def test_the_two_latencies_are_separate_cells(card):
    metrics = {c["metric"] for c in card["cells"]}
    assert metrics == {"retrieval_ms", "request_to_consumer_ms"}
    consumer = [c for c in card["cells"] if c["metric"] == "request_to_consumer_ms"]
    assert consumer, "a full request-to-consumer cell must exist even though no runner does"
    for cell in consumer:
        assert cell["stopped_reason"] == "NOT_IMPLEMENTED"
        assert "No runner exists" in cell["how_to_fill"]
    for cell in card["cells"]:
        if cell["metric"] == "retrieval_ms":
            assert cell["concurrency"] in {1, 5}


def test_unmeasured_costs_are_listed_not_omitted(card):
    names = {c["cell"] for c in card["cost_cells"]}
    assert {"publication_visibility", "publication_upkeep", "embedding_cost",
            "storage_cost", "cost_per_success"} <= names
    for cell in card["cost_cells"]:
        assert cell["state"] == "UNMEASURED"
        assert cell["value"] is None
        assert cell["how_to_fill"]


def test_budget_projection_uses_observed_bytes_and_fits(card):
    projection = card["budget_projection"]
    assert projection["within_budget"] is True
    assert projection["bytes_billed_projected_total"] > 0
    assert projection["usd_ondemand_list_projected"] <= projection["ceiling_usd_ondemand_list"]
    assert not projection["shapes_without_observed_bytes"]
    assert projection["consumer_cells_projected"] is False
    for cell in projection["cells"]:
        assert cell["bytes_billed_projected"] == cell["bytes_per_request_observed"] * cell["requests"]


def test_a_tighter_ceiling_is_reported_as_over_budget(plan):
    tight = copy.deepcopy(plan)
    tight["budget"]["max_usd_ondemand_list"] = 0.001
    assert sb.project_budget(tight, sb.prior_observations())["within_budget"] is False


def test_a_shape_with_no_observed_bytes_is_named_not_guessed(plan):
    priors = [p for p in sb.prior_observations() if p["shape"] != "natural"]
    projection = sb.project_budget(plan, priors)
    assert projection["within_budget"] is False
    assert "sqlbase_natural_c1" in projection["shapes_without_observed_bytes"]


def test_gql_comparison_stays_optional_and_matched(card):
    assert card["gql_comparison"]["state"] == "OPTIONAL_LATER"
    rule = card["gql_comparison"]["rule"]
    assert "reservation" in rule and "28 of 100" in rule


def test_rendered_card_shows_every_empty_cell(card):
    text = sb.render_markdown(card)
    assert "SCAFFOLD_ONLY" in text
    for cell in card["cells"]:
        assert cell["cell"] in text
    assert text.count("**UNMEASURED**") == len(card["cost_cells"])
    assert "**no**" in text, "the prior-observation table must say each one fills no cell"


def test_committed_card_matches_its_generator(tmp_path):
    """The committed artefact is generated. A hand-edited number would fail here."""
    sb.main(out_dir=tmp_path)
    for name in ("plan.json", "baseline.md"):
        committed = (sb.OUT_DIR / name).read_text()
        assert (tmp_path / name).read_text() == committed, f"{name} is stale; regenerate it"
    assert json.loads((sb.OUT_DIR / "plan.json").read_text())["state"] == "SCAFFOLD_ONLY"
