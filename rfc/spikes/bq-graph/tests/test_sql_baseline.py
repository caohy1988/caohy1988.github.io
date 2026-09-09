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


@pytest.mark.parametrize("drop", ["version", "engine", "corpus", "questions", "facts", "budget", "metrics",
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
        assert cell["stopped_reason"] in ("NOT_RUN", "NOT_IMPLEMENTED")
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


# --- fact-data version (PR 46 P1) ------------------------------------------------------------------

def test_fact_version_is_unselected_and_says_so(card):
    """The corpus pin fixes definitions and the graph projection. It identifies no fact data."""
    facts = card["facts"]
    assert facts["state"] == "UNSELECTED"
    for key in ("why_it_matters", "what_is_missing", "blocks", "how_to_select"):
        assert facts[key]
    observed = facts["observed_in_the_retained_chain"]
    assert observed["synthetic_fixture"] is True
    assert len(observed["tables"]) == 7
    assert observed["publication_id"] != card["corpus"]["publication_id"], \
        "the fact publication is a separate identity from the graph publication"


def test_the_recorded_fact_fixture_matches_the_retained_chain():
    """Read from the chain record, not restated: a drifted copy would be worse than no copy."""
    chain = json.loads((sb.ROOT / "evidence" / "chain" / "chain_live_restricted.json").read_text())
    observed = sb.load_plan()["facts"]["observed_in_the_retained_chain"]
    dataset = observed["dataset"]
    assert sorted(chain["sdk"]["dependencies"]) == sorted(f"{dataset}.{t}" for t in observed["tables"])
    assert chain["sdk"]["pin"] == observed["sdk_pin"]
    assert chain["sdk_publication"]["publication_id"] == observed["publication_id"]
    assert chain["sdk"]["synthetic_fixture"] == observed["synthetic_fixture"]
    assert observed["derived_from"] == chain["sdk_publication"]["derived_from"]


def test_no_fact_version_is_pinned_anywhere_in_that_chain():
    """The finding behind the field: the chain names the tables and never versions them."""
    chain = json.loads((sb.ROOT / "evidence" / "chain" / "chain_live_restricted.json").read_text())
    assert not any(k in chain["sdk"] for k in ("snapshot", "as_of", "fact_version", "data_version"))
    assert chain["as_of"] == chain["started_at"][:19] + "Z", \
        "the chain's as_of is its run timestamp, not a fact cutoff"


def test_unselected_facts_block_only_the_consumer_cells(card):
    blocked = {c["cell"] for c in card["cells"] if c["fact_version_blocked"]}
    assert blocked == set(card["facts"]["blocks"])
    for cell in card["cells"]:
        if cell["fact_version_blocked"]:
            assert cell["metric"] == "request_to_consumer_ms"
            assert cell["blocked_by"] and "UNSELECTED" in cell["blocked_by"]
            assert "Select a fact-data version first" in cell["how_to_fill"]
        else:
            assert cell["metric"] == "retrieval_ms"
            assert cell["blocked_by"] is None


def test_a_missing_fact_state_reads_as_chosen_and_is_refused(plan):
    broken = copy.deepcopy(plan)
    del broken["facts"]["state"]
    with pytest.raises(ValueError, match="facts.state must be SELECTED or UNSELECTED"):
        sb.validate_plan(broken)


def test_selecting_a_fact_version_requires_recording_it(plan):
    broken = copy.deepcopy(plan)
    broken["facts"]["state"] = "SELECTED"
    with pytest.raises(ValueError, match="no selected_version is recorded"):
        sb.validate_plan(broken)


@pytest.mark.parametrize("drop", ["why_it_matters", "what_is_missing", "blocks", "how_to_select"])
def test_an_unselected_fact_version_must_explain_itself(plan, drop):
    broken = copy.deepcopy(plan)
    del broken["facts"][drop]
    with pytest.raises(ValueError, match=drop):
        sb.validate_plan(broken)


def test_facts_cannot_block_a_cell_that_does_not_exist(plan):
    broken = copy.deepcopy(plan)
    broken["facts"]["blocks"] = ["sqlchain_forced_c1", "sqlchain_forced_c99"]
    with pytest.raises(ValueError, match="cells that do not exist"):
        sb.validate_plan(broken)


def test_a_silently_unblocked_cell_fails_the_build(card):
    tampered = copy.deepcopy(card)
    for cell in tampered["cells"]:
        cell["fact_version_blocked"] = False
    with pytest.raises(ValueError, match="but the card blocks"):
        sb.assert_no_cell_is_filled(tampered)


def test_a_blocked_cell_must_give_its_reason(card):
    tampered = copy.deepcopy(card)
    for cell in tampered["cells"]:
        if cell["fact_version_blocked"]:
            cell["blocked_by"] = None
    with pytest.raises(ValueError, match="gives no reason"):
        sb.assert_no_cell_is_filled(tampered)


def test_rendered_card_carries_the_fact_gap(card):
    text = sb.render_markdown(card)
    assert "## Fact data — **UNSELECTED**" in text
    for table in card["facts"]["observed_in_the_retained_chain"]["tables"]:
        assert f"`{table}`" in text
    assert card["facts"]["observed_in_the_retained_chain"]["sdk_pin"] in text
    assert "FACTS_UNSELECTED" in text


# --- cost-per-success denominator (PR 46 P2) --------------------------------------------------------

def test_cost_per_success_states_one_formula(plan, card):
    spec = next(c for c in plan["cost_cells"] if c["name"] == "cost_per_success")
    cell = next(c for c in card["cost_cells"] if c["cell"] == "cost_per_success")
    assert spec["formula"] == "total cost of all attempts / released, receipt-verified answers"
    assert cell["formula"] == spec["formula"]
    assert sb.render_markdown(card).count(spec["formula"]) == 1


def test_failed_attempts_are_never_placed_in_the_denominator(plan, card):
    """The fixture and the module said opposite things about this until PR 46."""
    surfaces = [json.dumps(plan), json.dumps(card), sb.render_markdown(card)]
    for text in surfaces:
        assert "included in the denominator" not in text
        assert "in the denominator" not in text or "must not appear in the denominator" in text
    how = next(c for c in card["cost_cells"] if c["cell"] == "cost_per_success")["how_to_fill"]
    assert "belongs in the numerator" in how and "must not appear in the denominator" in how


def test_cost_per_success_must_declare_a_formula(plan):
    broken = copy.deepcopy(plan)
    del next(c for c in broken["cost_cells"] if c["name"] == "cost_per_success")["formula"]
    with pytest.raises(ValueError, match="must state its formula"):
        sb.validate_plan(broken)


# --- a later SELECTED fact state must render as one (PR 46 round 2, P2) -----------------------------

SELECTED_VERSION = "okf_receipt_spike_20260905 @ snapshot 2026-09-07T22:00:00Z (fixture digest sha256:0f17ac…)"


def _selected(plan, version=SELECTED_VERSION, keep_optional=True):
    """The committed plan stays UNSELECTED; this is the shape a later selection would take."""
    facts = copy.deepcopy(plan)["facts"]
    facts["state"] = "SELECTED"
    facts["selected_version"] = version
    facts.pop("blocks", None)
    if not keep_optional:
        for key in ("why_it_matters", "what_is_missing", "how_to_select", "observed_in_the_retained_chain"):
            facts.pop(key, None)
    return dict(copy.deepcopy(plan), facts=facts)


def test_the_committed_plan_is_still_unselected(plan):
    """This slice fixes rendering. It does not select a fact version for the pack."""
    assert plan["facts"]["state"] == "UNSELECTED"


def test_a_selected_plan_validates(plan):
    sb.validate_plan(_selected(plan))


def test_a_selected_version_may_not_also_block_cells(plan):
    broken = _selected(plan)
    broken["facts"]["blocks"] = ["sqlchain_forced_c1"]
    with pytest.raises(ValueError, match="still blocks cells"):
        sb.validate_plan(broken)


def test_a_selected_version_unblocks_the_consumer_cells(plan):
    card = sb.build_card(_selected(plan))
    assert card["facts"]["state"] == "SELECTED"
    for cell in card["cells"]:
        assert cell["fact_version_blocked"] is False
        assert cell["blocked_by"] is None
        assert "Select a fact-data version first" not in cell["how_to_fill"]
    sb.assert_no_cell_is_filled(card)


def test_markdown_reports_the_selected_state_and_its_version(plan):
    """The render used to hardcode UNSELECTED, so the JSON and the Markdown disagreed."""
    text = sb.render_markdown(sb.build_card(_selected(plan)))
    assert "## Fact data — **SELECTED**" in text
    assert "UNSELECTED" not in text
    assert SELECTED_VERSION in text
    assert "**Selected version.**" in text
    assert "**Cells this blocks.** None" in text
    assert "FACTS_UNSELECTED" not in text


def test_markdown_renders_a_structured_selected_version(plan):
    version = {"dataset": "okf_receipt_spike_20260905", "snapshot": "2026-09-07T22:00:00Z", "rows": 4211}
    text = sb.render_markdown(sb.build_card(_selected(plan, version=version)))
    for key, value in version.items():
        assert f"* **{key}:** {value}" in text


def test_selected_render_does_not_require_the_unselected_fields(plan):
    """A selection makes "what is missing" and "how to select one" meaningless; they may be dropped."""
    card = sb.build_card(_selected(plan, keep_optional=False))
    text = sb.render_markdown(card)
    assert "## Fact data — **SELECTED**" in text
    assert SELECTED_VERSION in text
    assert "**What is missing.**" not in text
    assert "Cells this blocks.** None" in text


def test_the_two_states_do_not_share_a_hardcoded_heading(plan):
    unselected = sb.render_markdown(sb.build_card(plan))
    selected = sb.render_markdown(sb.build_card(_selected(plan)))
    assert "## Fact data — **UNSELECTED**" in unselected
    assert "## Fact data — **SELECTED**" in selected
    assert unselected != selected
