"""Hermetic gates on the ordinary-SQL baseline scaffold (2026-09-19 pack, Slice A).

No client, no network, no cloud. These tests exist to stop the scaffold from quietly becoming a
result: a cell that acquires a number, a prior observation that starts filling a cell, a committed
card that drifts from its generator, or a cost row that disappears instead of saying UNMEASURED.
"""
import copy
import json

import pytest

from okf_bq_graph import fact_content as fc
from okf_bq_graph import sql_baseline as sb


@pytest.fixture(scope="module")
def plan():
    return sb.load_plan()


@pytest.fixture(scope="module")
def card(plan):
    """The scaffold: no campaign record. Cards built from records are covered in test_sql_baseline_card.py."""
    return sb.build_card(copy.deepcopy(plan), records=[])


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
    committed = json.loads((sb.OUT_DIR / "plan.json").read_text())
    records = sb.campaign_records()
    assert committed["state"] == sb.card_state(
        [c for c in committed["cells"] if c["metric"] == "retrieval_ms"], records)[0]
    assert [c["run_id"] for c in committed["campaigns"]] == [r["run_id"] for r in records]


# --- fact-data version (PR 46 P1; SELECTED as the synthetic fixture digest on 2026-09-09) --------------

FACTS = sb.FACTS_DIR
CONSUMER_CELLS = ["sqlchain_forced_c1", "sqlchain_forced_c5"]


def _unselected(plan):
    """The shape the committed plan had before 2026-09-09: the UNSELECTED gates still have to hold."""
    out = copy.deepcopy(plan)
    facts = out["facts"]
    facts["state"] = "UNSELECTED"
    facts.pop("selected_version", None)
    facts.pop("customer_data", None)
    facts["blocks"] = list(CONSUMER_CELLS)
    facts["what_is_missing"] = "A data version."
    facts["how_to_select"] = "Name the fact dataset together with a reproducible version for it."
    return out


@pytest.fixture(scope="module")
def unselected_card(plan):
    return sb.build_card(_unselected(plan), records=[])


def test_fact_version_is_selected_synthetic_and_says_so(card):
    """Selected on 2026-09-09 as the receipt example's synthetic fixture digest; customer data stays unselected."""
    facts = card["facts"]
    assert facts["state"] == "SELECTED"
    assert facts["blocks"] == []
    assert "what_is_missing" not in facts
    version = facts["selected_version"]
    assert version["synthetic"] is True
    assert version["kind"].startswith("loaded-fixture-digest") and "synthetic" in version["kind"]
    assert version["customer_data"].startswith("none")
    assert facts["customer_data"]["state"] == "NOT SELECTED"
    assert "Alder" in facts["customer_data"]["cohort"]
    assert "not ours to invent" in facts["customer_data"]["note"]
    assert facts["why_it_matters"] and facts["how_to_select"]
    observed = facts["observed_in_the_retained_chain"]
    assert observed["synthetic_fixture"] is True
    assert len(observed["tables"]) == 7
    assert observed["publication_id"] != card["corpus"]["publication_id"], \
        "the fact publication is a separate identity from the graph publication"


def test_the_selection_names_what_the_retained_chain_used(plan):
    """dataset, tables, pin and computation bytes equal the chain record, which the next test reads directly."""
    chain = json.loads((sb.ROOT / "evidence" / "chain" / "chain_live_restricted.json").read_text())
    version = plan["facts"]["selected_version"]
    assert sorted(chain["sdk"]["dependencies"]) == [f"{version['dataset']}.{t}" for t in version["tables"]]
    assert chain["sdk"]["pin"] == version["sdk_pin"]
    assert chain["sdk"]["computation_sha256"] == version["computation_sha256"]
    observed = plan["facts"]["observed_in_the_retained_chain"]
    assert version["dataset"] == observed["dataset"] and version["sdk_pin"] == observed["sdk_pin"]
    assert version["tables"] == sorted(observed["tables"])


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
    """The finding behind the field: the chain names the tables and never versions them. The selection is
    a new record beside the chain, not a repair of the chain's evidence."""
    chain = json.loads((sb.ROOT / "evidence" / "chain" / "chain_live_restricted.json").read_text())
    assert not any(k in chain["sdk"] for k in ("snapshot", "as_of", "fact_version", "data_version"))
    assert chain["as_of"] == chain["started_at"][:19] + "Z", \
        "the chain's as_of is its run timestamp, not a fact cutoff"


def test_every_recorded_digest_is_the_sha256_of_a_vendored_file(plan):
    version = plan["facts"]["selected_version"]
    for name, key in (("fixture.sql", "fixture_sha256"), ("expected.json", "expected_results_sha256"),
                      ("content.json", "content_manifest_sha256")):
        assert fc.sha256((FACTS / name).read_bytes()) == version[key], name
    assert (FACTS / "fixture.sql").stat().st_size == version["fixture_bytes"]
    assert version["sdk_pin"] in (FACTS / "SOURCE.md").read_text()
    assert version["fixture_sha256"] in (FACTS / "SOURCE.md").read_text()


def test_the_content_manifest_re_derives_from_the_vendored_script(plan):
    """The digest of a script says nothing about its rows; the canonical manifest does, and it must reproduce."""
    version = plan["facts"]["selected_version"]
    manifest = fc.extract((FACTS / "fixture.sql").read_text())
    raw = fc.canonical_bytes(manifest)
    assert raw == (FACTS / "content.json").read_bytes()
    assert fc.sha256(raw) == version["content_manifest_sha256"]
    assert manifest["format"] == version["content_manifest_format"] == "okf-fact-content/1"
    assert list(manifest["tables"]) == version["tables"]


def test_row_counts_derive_from_the_script_including_the_empty_fx_table(plan):
    version = plan["facts"]["selected_version"]
    derived = fc.row_counts(fc.extract((FACTS / "fixture.sql").read_text()))
    assert derived == version["row_counts"]
    assert derived["fx_daily_rates"] == 0, "the FX table is created and never inserted into; the fixture is USD-only"
    assert sum(derived.values()) == version["row_count_total"] == 14


def test_per_table_digests_match_the_reviewer_lens_audit(plan):
    """Cross-check against the 2026-09-09 reviewer memo's independently computed per-table digests."""
    digests = fc.per_table_digests(fc.extract((FACTS / "fixture.sql").read_text()))
    assert digests == {
        "fulfillment_cost": "59a07e008af4edc582462b77ef49bbaf40dc10b0f8973fb99c4d13c633749c3c",
        "fx_daily_rates": "aeb571faba19044c72b137de94c286963eca41b0a381a70f79f05ca6352ddc15",
        "order_lines": "f1cde5aaa318bc7275f12927ae56ccfc4bed601c5cdf87ff13da5da6366b3801",
        "orders": "88eac1e0a3ffee154427e04e41f1f5d892a5fc4a51e605146fcea849e420cfe8",
        "payment_fees": "04396d33c91149c651a0f944348ee80459730219073f37fb635f86040db65b6d",
        "products": "af055afb384a4f580b8f3be1b2ea1aa9d9a7611e2c66ebc72427332e257256f4",
        "shipment_cost": "00d583a463d5b0e4c13a0fe41bccdd8de79cc147164c3a25b7424de974671250",
    }


def test_the_january_expectation_is_what_the_chain_released(plan):
    version = plan["facts"]["selected_version"]
    expected = json.loads((FACTS / "expected.json").read_text())
    assert version["expected_gross_margin_usd_2026_01"] == expected["approved_january"]["gross_margin_usd"] == "400"
    chain = json.loads((sb.ROOT / "evidence" / "chain" / "chain_live_restricted.json").read_text())
    case = next(c for c in chain["cases"] if c["case"] == "approved-restricted")
    assert case["consume"]["decision"] == "RELEASED" and "$400.00" in case["consume"]["display"]
    assert case["consume"]["display"] in version["conformance_observed"]
    assert version["historical_chain_equivalence"].startswith("UNPROVEN"), \
        "a matching number is consistent with the content; it is not byte-equivalence"
    assert version["live_materialization"].startswith("UNVERIFIED"), "nothing in this slice read the live tables"


def test_the_load_job_is_on_record_as_a_600_byte_query_prefix_not_the_full_script(plan):
    """The listing index keeps a trimmed query; the job proves a fixture load at that time, not byte identity."""
    version = plan["facts"]["selected_version"]
    job_id = version["loaded_by_job"].split(".")[1].split(" ")[0]
    index = json.loads((sb.ROOT / "evidence" / "legacy-reconcile" / "episode_listing_index.json").read_text())
    job = next(j for j in index["jobs"] if j["jobReference"]["jobId"] == job_id)
    assert job["status"]["state"] == "DONE" and job["statistics"]["numChildJobs"] == "13"
    assert job["jobReference"]["projectId"] == version["dataset"].split(".")[0]
    assert job["jobReference"]["location"] == version["location"]
    prefix = job["configuration"]["query"]["query"]
    assert len(prefix) == 600 and (FACTS / "fixture.sql").read_text().startswith(prefix)
    assert "prefix" in version["load_evidence"]


def test_validity_window_and_expiry_are_recorded(plan):
    version = plan["facts"]["selected_version"]
    assert version["valid_for_runs_on_or_after"] == "2026-03-12"
    assert "CURRENT_DATE()" in version["validity_note"] and "computation_sha256" in version["validity_note"]
    assert "2026-10-05" in version["materialization_expires_utc"]
    assert version["live_precheck"].startswith("NOT IMPLEMENTED") and "FACTS_DRIFTED" in version["live_precheck"]


# --- the UNSELECTED gates still hold on a plan flipped back -------------------------------------------

def test_unselected_facts_block_only_the_consumer_cells(unselected_card):
    card = unselected_card
    blocked = {c["cell"] for c in card["cells"] if c["fact_version_blocked"]}
    assert blocked == set(card["facts"]["blocks"]) == set(CONSUMER_CELLS)
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
    broken = _unselected(plan)
    broken["facts"]["state"] = "SELECTED"
    broken["facts"]["blocks"] = []
    with pytest.raises(ValueError, match="no selected_version is recorded"):
        sb.validate_plan(broken)


@pytest.mark.parametrize("drop", ["why_it_matters", "what_is_missing", "blocks", "how_to_select"])
def test_an_unselected_fact_version_must_explain_itself(plan, drop):
    broken = _unselected(plan)
    del broken["facts"][drop]
    with pytest.raises(ValueError, match=drop):
        sb.validate_plan(broken)


def test_facts_cannot_block_a_cell_that_does_not_exist(plan):
    broken = _unselected(plan)
    broken["facts"]["blocks"] = ["sqlchain_forced_c1", "sqlchain_forced_c99"]
    with pytest.raises(ValueError, match="cells that do not exist"):
        sb.validate_plan(broken)


def test_a_silently_unblocked_cell_fails_the_build(unselected_card):
    tampered = copy.deepcopy(unselected_card)
    for cell in tampered["cells"]:
        cell["fact_version_blocked"] = False
    with pytest.raises(ValueError, match="but the card blocks"):
        sb.assert_no_cell_is_filled(tampered)


def test_a_blocked_cell_must_give_its_reason(unselected_card):
    tampered = copy.deepcopy(unselected_card)
    for cell in tampered["cells"]:
        if cell["fact_version_blocked"]:
            cell["blocked_by"] = None
    with pytest.raises(ValueError, match="gives no reason"):
        sb.assert_no_cell_is_filled(tampered)


def test_rendered_unselected_card_carries_the_fact_gap(unselected_card):
    text = sb.render_markdown(unselected_card)
    assert "## Fact data — **UNSELECTED**" in text
    for table in unselected_card["facts"]["observed_in_the_retained_chain"]["tables"]:
        assert f"`{table}`" in text
    assert unselected_card["facts"]["observed_in_the_retained_chain"]["sdk_pin"] in text
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


# --- the SELECTED state: record gates and rendering (PR 46 round 2 P2, tightened 2026-09-09) --------

BARE_LABEL = "okf_receipt_spike_20260905 @ snapshot 2026-09-07T22:00:00Z (fixture digest sha256:0f17ac…)"


def _selected(plan, version=None, keep_optional=True, **facts_overrides):
    """The committed plan is SELECTED; this returns a copy with the version or fact fields altered."""
    out = copy.deepcopy(plan)
    facts = out["facts"]
    if version is not None:
        facts["selected_version"] = version
    if not keep_optional:
        for key in ("why_it_matters", "how_to_select", "observed_in_the_retained_chain"):
            facts.pop(key, None)
    facts.update(facts_overrides)
    return out


def _version(plan, **overrides):
    version = copy.deepcopy(plan["facts"]["selected_version"])
    version.update(overrides)
    return version


def test_the_committed_plan_is_selected(plan):
    assert plan["facts"]["state"] == "SELECTED"
    sb.validate_plan(plan)


def test_a_bare_label_is_not_a_version_record(plan):
    """`selected_version: "x"` used to validate. A string identifies nothing recomputable."""
    with pytest.raises(ValueError, match="bare label"):
        sb.validate_plan(_selected(plan, version=BARE_LABEL))
    with pytest.raises(ValueError, match="bare label"):
        sb.validate_plan(_selected(plan, version="x"))


@pytest.mark.parametrize("drop", list(sb.SELECTED_VERSION_REQUIRED))
def test_every_identity_field_of_the_record_is_required(plan, drop):
    version = _version(plan)
    del version[drop]
    with pytest.raises(ValueError, match="missing"):
        sb.validate_plan(_selected(plan, version=version))


@pytest.mark.parametrize("key", ["fixture_sha256", "expected_results_sha256", "content_manifest_sha256"])
def test_a_wrong_digest_is_refused(plan, key):
    wrong = "0" * 64
    with pytest.raises(ValueError, match="hashes to"):
        sb.validate_plan(_selected(plan, version=_version(plan, **{key: wrong})))
    with pytest.raises(ValueError, match="full lowercase SHA-256"):
        sb.validate_plan(_selected(plan, version=_version(plan, **{key: "940aacdc…"})))


def test_a_truncated_pin_or_non_boolean_synthetic_is_refused(plan):
    with pytest.raises(ValueError, match="full commit hash"):
        sb.validate_plan(_selected(plan, version=_version(plan, sdk_pin="6719eb5")))
    with pytest.raises(ValueError, match="must be the boolean true"):
        sb.validate_plan(_selected(plan, version=_version(plan, synthetic="true")))


def test_row_counts_must_agree_with_the_script_and_with_the_total(plan):
    counts = dict(plan["facts"]["selected_version"]["row_counts"], orders=4)
    with pytest.raises(ValueError, match="row_count_total does not equal"):
        sb.validate_plan(_selected(plan, version=_version(plan, row_counts=counts)))
    with pytest.raises(ValueError, match="differ from the script"):
        sb.validate_plan(_selected(plan, version=_version(plan, row_counts=counts, row_count_total=15)))
    counts = {k: v for k, v in plan["facts"]["selected_version"]["row_counts"].items() if k != "fx_daily_rates"}
    with pytest.raises(ValueError, match="one non-negative count per selected table"):
        sb.validate_plan(_selected(plan, version=_version(plan, row_counts=counts, row_count_total=14)))


def test_the_selection_may_not_disagree_with_the_retained_chain(plan):
    with pytest.raises(ValueError, match="differs from what the retained chain used"):
        sb.validate_plan(_selected(plan, version=_version(plan, dataset="test-project-0728-467323.other")))
    with pytest.raises(ValueError, match="differ from what the retained chain used"):
        sb.validate_plan(_selected(plan, version=_version(
            plan, tables=["orders"], row_counts={"orders": 3}, row_count_total=3)))


def test_a_selected_version_must_state_the_customer_data_status(plan):
    with pytest.raises(ValueError, match="customer_data"):
        sb.validate_plan(_selected(plan, customer_data=None))
    with pytest.raises(ValueError, match="customer_data"):
        sb.validate_plan(_selected(plan, customer_data={"state": "PENDING"}))


# --- Astra P2 #2: the gate refuses promotions this record cannot carry ---------------------------------

PROMOTIONS = {
    "synthetic_false": dict(version=dict(synthetic=False)),
    "live_verified": dict(version=dict(live_materialization="VERIFIED")),
    "chain_proven": dict(version=dict(historical_chain_equivalence="PROVEN")),
    "live_free_text": dict(version=dict(live_materialization="probably fine")),
    "chain_free_text": dict(version=dict(historical_chain_equivalence="matched $400")),
    "customer_selected": dict(customer_data={"state": "SELECTED", "cohort": "Alder cohort"}),
    "customer_pending": dict(customer_data={"state": "PENDING", "cohort": "Alder cohort"}),
    "customer_missing": dict(customer_data=None),
}


@pytest.mark.parametrize("name", sorted(PROMOTIONS))
def test_unsupported_promotions_are_refused_at_validate_and_build(plan, name):
    """A bare word is not evidence: VERIFIED, PROVEN, a non-synthetic fixture or a selected customer cohort each
    need a separately validated record that no schema defines yet. Refused at both public boundaries."""
    change = PROMOTIONS[name]
    promoted = _selected(plan, version=_version(plan, **change["version"]) if "version" in change else None,
                         **{k: v for k, v in change.items() if k != "version"})
    with pytest.raises(ValueError):
        sb.validate_plan(promoted)
    with pytest.raises(ValueError):
        sb.build_card(promoted, records=[])


def test_the_promotion_refusals_say_what_evidence_would_be_needed(plan):
    with pytest.raises(ValueError, match="readback record"):
        sb.validate_plan(_selected(plan, version=_version(plan, live_materialization="VERIFIED")))
    with pytest.raises(ValueError, match="not byte-equivalence"):
        sb.validate_plan(_selected(plan, version=_version(plan, historical_chain_equivalence="PROVEN")))
    with pytest.raises(ValueError, match="own evidence and owner record"):
        sb.validate_plan(_selected(plan, version=_version(plan, synthetic=False)))
    with pytest.raises(ValueError, match="own record with its own owner"):
        sb.validate_plan(_selected(plan, customer_data={"state": "SELECTED", "cohort": "Alder cohort"}))


@pytest.mark.parametrize("state", ["SELECTED", "PENDING", None])
def test_the_unselected_path_also_refuses_a_customer_promotion(plan, state):
    """Astra re-review of 93e3534: the guard ran only for SELECTED, so an UNSELECTED plan printed Alder as SELECTED."""
    tampered = _unselected(plan)
    tampered["facts"]["customer_data"] = {"state": state, "cohort": "Alder cohort"}
    with pytest.raises(ValueError, match="customer_data must be a record with state NOT SELECTED"):
        sb.validate_plan(tampered)
    with pytest.raises(ValueError, match="customer_data"):
        sb.build_card(tampered, records=[])


def test_the_legacy_unselected_shape_without_a_customer_block_still_validates(plan):
    legacy = _unselected(plan)
    assert "customer_data" not in legacy["facts"]
    sb.validate_plan(legacy)
    text = sb.render_markdown(sb.build_card(legacy, records=[]))
    assert "Customer fact data" not in text and "## Fact data — **UNSELECTED**" in text


def test_an_unselected_plan_may_carry_the_honest_customer_block(plan):
    honest = _unselected(plan)
    honest["facts"]["customer_data"] = {"state": "NOT SELECTED", "cohort": "Alder cohort", "note": "never selected"}
    text = sb.render_markdown(sb.build_card(honest, records=[]))
    assert "**Customer fact data (Alder cohort) — NOT SELECTED.**" in text


@pytest.mark.parametrize("state", ["SELECTED", "PENDING"])
def test_render_fails_closed_on_a_tampered_customer_block(card, unselected_card, state):
    """A card tampered after validation must not print a customer selection either."""
    for base in (card, unselected_card):
        tampered = copy.deepcopy(base)
        tampered["facts"]["customer_data"] = {"state": state, "cohort": "Alder cohort"}
        with pytest.raises(ValueError, match="refusing to render"):
            sb.render_markdown(tampered)


def test_the_rendered_card_never_prints_a_selected_customer_cohort(card):
    text = sb.render_markdown(card)
    assert "Alder cohort) — NOT SELECTED" in text
    assert "Alder cohort) — SELECTED" not in text
    assert "* **live_materialization:** UNVERIFIED" in text and "* **historical_chain_equivalence:** UNPROVEN" in text


# --- Astra P2 #3: source identity is bound to vendored provenance, not accepted as syntax ---------------

@pytest.mark.parametrize("change,match", [
    (dict(computation_sha256="0" * 64), "gross-margin-period.md hashes to"),
    (dict(publication_manifest_sha256="1" * 64), "publication.json hashes to"),
    (dict(publication_manifest_sha256="x"), "full lowercase SHA-256"),
    (dict(fixture_path="missing.sql"), "not the pinned SDK path"),
    (dict(expected_results_path="examples/other/expected.json"), "not the pinned SDK path"),
    (dict(sdk_pin="f" * 40), "differs from what the retained chain used"),
    (dict(location="EU"), "differ from the vendored publication manifest"),
])
def test_a_false_source_identity_claim_is_refused(plan, change, match):
    with pytest.raises(ValueError, match=match):
        sb.validate_plan(_selected(plan, version=_version(plan, **change)))


def test_a_pin_that_is_valid_syntax_but_not_the_vendored_one_is_refused_without_the_chain_block(plan):
    """With the chain cross-check dropped, source.json still binds the pin."""
    with pytest.raises(ValueError, match="vendored provenance pin"):
        sb.validate_plan(_selected(plan, version=_version(plan, sdk_pin="f" * 40), keep_optional=False))


def test_the_vendored_publication_manifest_and_declaration_are_the_pinned_objects(plan):
    version = plan["facts"]["selected_version"]
    source = json.loads((FACTS / "source.json").read_text())
    assert source["sdk_pin"] == version["sdk_pin"]
    for name, key in sb.ARTIFACT_DIGESTS:
        assert fc.sha256((FACTS / name).read_bytes()) == version[key] == source["artifacts"][name]["sha256"], name
        assert (FACTS / name).stat().st_size == source["artifacts"][name]["bytes"], name
    publication = json.loads((FACTS / "publication.json").read_text())
    assert publication["synthetic"] is True
    assert publication["computation_sha256"] == version["computation_sha256"]
    assert sorted(publication["table_map"].values()) == version["tables"]
    assert f"{publication['project']}.{publication['dataset']}" == version["dataset"]
    assert (FACTS / "gross-margin-period.md").read_text().startswith("---\ntype: Attested Computation")


def test_a_missing_or_disagreeing_provenance_pin_is_refused(plan, tmp_path):
    version = plan["facts"]["selected_version"]
    for name, _ in sb.ARTIFACT_DIGESTS:
        (tmp_path / name).write_bytes((FACTS / name).read_bytes())
    with pytest.raises(ValueError, match="no offline provenance pin"):
        sb._verify_selected_artifacts(version, facts_dir=tmp_path)
    source = json.loads((FACTS / "source.json").read_text())
    source["artifacts"]["publication.json"]["sha256"] = "0" * 64
    (tmp_path / "source.json").write_text(json.dumps(source))
    with pytest.raises(ValueError, match="not what source.json pins"):
        sb._verify_selected_artifacts(version, facts_dir=tmp_path)


# --- Astra P2 #4: dates are calendar dates; the expiry is explicitly approximate ------------------------

@pytest.mark.parametrize("value", ["2026-99-99", "2026-3-12", "March 12", None, 20260312])
def test_the_validity_date_must_be_a_real_calendar_date(plan, value):
    with pytest.raises(ValueError, match="real calendar date"):
        sb.validate_plan(_selected(plan, version=_version(plan, valid_for_runs_on_or_after=value)))


@pytest.mark.parametrize("value", [None, "", "2026-10-05T00:00:00Z", "2026-10-05", "about 2026-13-01", "soon", 20261005])
def test_the_expiry_must_be_explicitly_approximate_or_unknown(plan, value):
    with pytest.raises(ValueError, match="materialization_expires_utc"):
        sb.validate_plan(_selected(plan, version=_version(plan, materialization_expires_utc=value)))


def test_an_unknown_expiry_is_an_honest_value(plan):
    sb.validate_plan(_selected(plan, version=_version(plan, materialization_expires_utc="unknown: not read back")))
    sb.validate_plan(_selected(plan, version=_version(plan, materialization_expires_utc="about 2026-10-05")))


def test_selected_utc_when_present_is_a_calendar_date(plan):
    with pytest.raises(ValueError, match="selected_utc"):
        sb.validate_plan(_selected(plan, version=_version(plan, selected_utc="yesterday")))


# --- Astra P2 #1: counts plus the January answer are not content identity --------------------------------

def test_counts_and_the_january_answer_do_not_identify_the_content(plan):
    """Astra's counterexample: bump the February delivered order's amount. Every count and January's 400 hold;
    the content digest and the January–February result change. Hence the recorded precheck is a full readback."""
    version = plan["facts"]["selected_version"]
    script = (FACTS / "fixture.sql").read_text()
    needle = "'delivered', NUMERIC '200.00', NUMERIC '0', NUMERIC '200.00'"
    assert script.count(needle) == 1
    mutated = fc.extract(script.replace(needle, "'delivered', NUMERIC '200.00', NUMERIC '0', NUMERIC '201.00'"))
    assert fc.row_counts(mutated) == version["row_counts"]
    assert fc.sha256(fc.canonical_bytes(mutated)) != version["content_manifest_sha256"]
    assert "full" in version["live_precheck"] and "smoke checks" in version["live_precheck"]
    assert "content_manifest_sha256" in version["live_precheck"]
    assert version["live_precheck"].startswith("NOT IMPLEMENTED")


def test_a_mutated_vendored_row_or_a_dropped_table_changes_the_digest(plan, tmp_path):
    """Negative checks on the artifacts themselves, against a scratch copy of the vendored directory."""
    version = plan["facts"]["selected_version"]
    for name in [n for n, _ in sb.ARTIFACT_DIGESTS] + ["source.json"]:
        (tmp_path / name).write_bytes((FACTS / name).read_bytes())
    sb._verify_selected_artifacts(version, facts_dir=tmp_path)
    script = (tmp_path / "fixture.sql").read_text()
    assert "'sku-400', 'Widget'" in script or "sku-400" in script
    (tmp_path / "fixture.sql").write_text(script.replace("sku-400", "sku-401", 1))
    with pytest.raises(ValueError, match="fixture.sql hashes to"):
        sb._verify_selected_artifacts(version, facts_dir=tmp_path)
    mutated_manifest = fc.extract((tmp_path / "fixture.sql").read_text())
    assert fc.sha256(fc.canonical_bytes(mutated_manifest)) != version["content_manifest_sha256"]
    (tmp_path / "fixture.sql").write_bytes((FACTS / "fixture.sql").read_bytes())
    manifest = json.loads((tmp_path / "content.json").read_text())
    del manifest["tables"]["fx_daily_rates"]
    (tmp_path / "content.json").write_bytes(fc.canonical_bytes(manifest))
    with pytest.raises(ValueError, match="content.json hashes to"):
        sb._verify_selected_artifacts(version, facts_dir=tmp_path)
    (tmp_path / "content.json").unlink()
    with pytest.raises(ValueError, match="is not vendored"):
        sb._verify_selected_artifacts(version, facts_dir=tmp_path)


def test_a_selected_version_may_not_also_block_cells(plan):
    broken = _selected(plan)
    broken["facts"]["blocks"] = ["sqlchain_forced_c1"]
    with pytest.raises(ValueError, match="still blocks cells"):
        sb.validate_plan(broken)


def test_a_selected_version_unblocks_the_consumer_cells_but_fills_nothing(card):
    assert card["facts"]["state"] == "SELECTED"
    for cell in card["cells"]:
        assert cell["fact_version_blocked"] is False
        assert cell["blocked_by"] is None
        assert "Select a fact-data version first" not in cell["how_to_fill"]
        if cell["metric"] == "request_to_consumer_ms":
            assert cell["stopped_reason"] == "NOT_IMPLEMENTED" and cell["state"] == "INCOMPLETE"
            assert cell["measured_n"] == 0 and cell["p50_ms"] is None
            assert "Fact version: SELECTED" in cell["how_to_fill"] and "synthetic" in cell["how_to_fill"]
            assert "read the live tables back in full" in cell["how_to_fill"]
            assert "smoke checks, not identity" in cell["how_to_fill"]
    for cost in card["cost_cells"]:
        assert cost["state"] == "UNMEASURED" and cost["value"] is None
    sb.assert_no_cell_is_filled(card)


def test_markdown_reports_the_selected_state_and_its_version(card):
    text = sb.render_markdown(card)
    version = card["facts"]["selected_version"]
    assert "## Fact data — **SELECTED**" in text
    assert "**Selected version.**" in text
    assert f"* **label:** {version['label']}" in text
    assert "* **synthetic:** true" in text
    assert f"* **fixture_sha256:** {version['fixture_sha256']}" in text
    assert "* **row_counts:** fulfillment_cost=2, fx_daily_rates=0, order_lines=3" in text
    assert "* **tables:** `fulfillment_cost`, `fx_daily_rates`" in text
    assert "**Customer fact data (Alder cohort) — NOT SELECTED.**" in text
    assert "**Cells this blocks.** None" in text and "clears `FACTS_UNSELECTED` only" in text
    assert "**How it was selected.**" in text
    assert "**What is missing.**" not in text
    assert "UNSELECTED**" not in text
    assert "| NOT_IMPLEMENTED |" in text and "+ FACTS_UNSELECTED" not in text


def test_selected_render_does_not_require_the_optional_fields(plan):
    """With the chain block dropped the chain cross-check is skipped; the artifact gates still run."""
    card = sb.build_card(_selected(plan, keep_optional=False))
    text = sb.render_markdown(card)
    assert "## Fact data — **SELECTED**" in text
    assert "**What the retained chain identifies**" not in text
    assert "**How it was selected.**" not in text
    assert "Cells this blocks.** None" in text


def test_the_two_states_do_not_share_a_hardcoded_heading(plan, card, unselected_card):
    unselected = sb.render_markdown(unselected_card)
    selected = sb.render_markdown(card)
    assert "## Fact data — **UNSELECTED**" in unselected
    assert "## Fact data — **SELECTED**" in selected
    assert unselected != selected
