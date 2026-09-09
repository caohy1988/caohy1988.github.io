"""Hermetic gates on the ordinary-SQL baseline driver (2026-09-19 pack, Slice B, Pass 1).

No client, no network, no cloud. The driver's job is to reach `benchmark.measure` with exactly the
predeclared cells and nothing else; these tests pin the wiring that the live pass will rely on:
plan → cell mapping, one shape per cell, a fresh labelled run_id, refusal of the consumer cells, and
a dry run that constructs no BigQuery client.
"""
import copy
import json
import re
import io

import pytest

from okf_bq_graph import benchmark
from okf_bq_graph import sql_baseline as sb
from okf_bq_graph import sql_baseline_run as run

@pytest.fixture(scope="module")
def plan():
    return sb.load_plan()


@pytest.fixture(scope="module")
def cases():
    return run.load_cases()


@pytest.fixture
def no_client(monkeypatch):
    """Any BigQuery client construction fails the test."""
    calls = []

    class Forbidden:
        def __init__(self, *a, **kw):
            calls.append((a, kw))
            raise AssertionError("a BigQuery client was constructed")

    monkeypatch.setattr(run.bigquery, "Client", Forbidden)
    return calls


@pytest.fixture
def scratch(tmp_path, monkeypatch):
    """Retention files redirected so no test touches the committed evidence."""
    monkeypatch.setattr(benchmark, "REQUESTS", str(tmp_path / "requests.jsonl"))
    monkeypatch.setattr(benchmark, "SUMMARY", str(tmp_path / "summary.json"))
    return tmp_path


# --- plan → cells ----------------------------------------------------------------------------------

def test_every_retrieval_cell_maps_from_the_plan_not_scale_json(plan, cases):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    names = [c["name"] for c in campaign["cells"]]
    assert names == ["sqlbase_forced_c1", "sqlbase_forced_c5", "sqlbase_natural_c1", "sqlbase_natural_c5"]
    scale = json.loads((sb.ROOT / "fixtures" / "scale.json").read_text())
    assert not set(names) & {c["name"] for c in scale["cells"]}
    by_name = {c["name"]: c for c in plan["retrieval_cells"]}
    for cell in campaign["cells"]:
        declared = by_name[cell["name"]]
        assert cell["engine"] == "fallback"
        assert cell["concurrency"] == declared["concurrency"]
        assert cell["warmups"] == declared["warmups"] == 20
        assert cell["measured"] == declared["measured"] == 100
        assert cell["timeout_s"] == declared["timeout_s"] == 60
        assert cell["corpus"] == plan["corpus"]["bundle_id"]
        assert cell["ds"] == plan["corpus"]["dataset"]
        assert cell["publication_id"] == plan["corpus"]["publication_id"]
        assert cell["as_of"] == plan["questions"]["as_of"]
        assert cell["bundles"] is None      # no synthetic tenant copies: this is the pinned Acme corpus


def test_budget_comes_from_the_plan_and_has_no_window(plan, cases):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    assert campaign["budget"]["cell_seconds"] == plan["budget"]["max_wall_seconds_per_cell"] == 900
    assert campaign["budget"]["total_seconds"] == plan["budget"]["max_wall_seconds_total"] == 3600
    assert campaign["reservation_window"] is None and campaign["edition_requested"] == "on-demand"
    assert campaign["routing"]["job_reservation"] == "none"
    assert "edition" not in campaign          # the label is earned by the record, never declared by the campaign
    cfg = run.measure_config(campaign, started_monotonic=1000.0)
    assert cfg["budget"] == {"cell_seconds": 900, "deadline_monotonic": 4600.0, "deadline_reason": "TOTAL_TIME_BUDGET"}
    assert "window" not in cfg["budget"]
    assert cfg["queries"] == []             # nothing pooled at the config level
    assert cfg["run_id"] == campaign["run_id"]
    run.assert_campaign_is_runnable(campaign)


def test_driver_never_imports_the_reservation_layer():
    """On-demand by construction: no module that opens or binds a reservation window is imported."""
    import ast
    tree = ast.parse((sb.ROOT / "okf_bq_graph" / "sql_baseline_run.py").read_text())
    imported = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imported |= {a.name for a in node.names}
        elif isinstance(node, ast.ImportFrom):
            imported |= {a.name for a in node.names} | {node.module or ""}
    assert not imported & {"reservation", "run", "open_window", "close_window", "require_clean_windows"}
    assert not hasattr(run, "open_window")
    # the submission gate it does use is lifecycle's job inventory, which opens no capacity
    assert run.WindowJobs.__module__ == "okf_bq_graph.lifecycle"


def test_engine_other_than_fallback_is_refused(plan, cases):
    other = copy.deepcopy(plan)
    other["engine"] = "gql"
    with pytest.raises(ValueError, match="fallback"):
        run.cell_config(other, other["retrieval_cells"][0], cases)


# --- shape isolation ---------------------------------------------------------------------------------

def test_each_cell_carries_only_its_own_shape(plan, cases):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    forced_ids = set(plan["questions"]["forced_seed_ids"])
    natural_ids = set(plan["questions"]["natural_query_ids"])
    assert not forced_ids & natural_ids
    for cell in campaign["cells"]:
        ids = [q["id"] for q in cell["queries"]]
        texts = [q["text"] for q in cell["queries"]]
        if cell["shape"] == "forced":
            assert set(ids) == forced_ids and all(t.startswith("forced:") for t in texts)
            assert cell["model"] is None
        else:
            assert set(ids) == natural_ids and not any(t.startswith("forced:") for t in texts)
            assert cell["model"] == "text-embedding-005"
        assert {q["shape"] for q in cell["queries"]} == {cell["shape"]}
        assert {q["bundle_id"] for q in cell["queries"]} == {plan["corpus"]["bundle_id"]}
        assert {q["publication_id"] for q in cell["queries"]} == {plan["corpus"]["publication_id"]}


def test_a_mislabelled_fixture_text_fails_instead_of_being_measured(plan, cases):
    broken = copy.deepcopy(cases)
    broken["natural_queries"][0]["text"] = "forced:metrics/revenue.md"
    with pytest.raises(ValueError, match="not a natural question"):
        run.queries_for_shape(plan, broken, "natural")
    broken = copy.deepcopy(cases)
    broken["forced_seeds"][0]["text"] = "How do we calculate gross margin?"
    with pytest.raises(ValueError, match="not a forced question"):
        run.queries_for_shape(plan, broken, "forced")


def test_plan_ids_missing_from_cases_fail(plan, cases):
    broken = copy.deepcopy(plan)
    broken["questions"]["forced_seed_ids"].append("f_nonexistent")
    with pytest.raises(ValueError, match="f_nonexistent"):
        run.queries_for_shape(broken, cases, "forced")


def test_as_of_mismatch_between_plan_and_cases_fails(plan, cases):
    stale = dict(cases, as_of="2026-01-01T00:00:00Z")
    with pytest.raises(ValueError, match="as_of"):
        run.queries_for_shape(plan, stale, "forced")


def test_measure_samples_each_cell_from_its_own_shape(plan, cases, scratch, monkeypatch, no_client):
    """End to end through the real `benchmark.measure`: the per-cell query list is honoured."""
    seen: dict[str, list[str]] = {}

    def fake_retrieve(query, bundle_id, publication_id, requester, as_of, clients, top_k=5):
        assert clients["engine"] == "fallback" and clients["use_cache"] is False and "cache" not in clients
        seen.setdefault(clients["_cell"], []).append(query)
        return {"status": "OK", "concepts": [], "paths": [], "computations": [],
                "timing": {"total_ms": 1.0, "stages_ms": {"walk": 1.0}, "jobs": []}}

    monkeypatch.setattr(benchmark, "retrieve", fake_retrieve)
    small = copy.deepcopy(plan)
    for cell in small["retrieval_cells"]:
        cell["warmups"], cell["measured"] = 1, 6
    campaign = run.build_campaign(small, cases, run_id="sqlbase-20260919-000000-deadbeef")

    real_one_request = benchmark.one_request

    def tagged_one_request(cell, i, q, clients, timeout_s):
        return real_one_request(cell, i, q, dict(clients, _cell=cell["name"]), timeout_s)

    monkeypatch.setattr(benchmark, "one_request", tagged_one_request)
    factory = run.client_factory(campaign["dataset"], make_client=lambda: object())
    result = benchmark.measure(run.measure_config(campaign), factory)
    assert [c["state"] for c in result["cells"]] == ["COMPLETE"] * 4
    for cell in campaign["cells"]:
        texts = seen[cell["name"]]
        assert len(texts) == 7
        assert all(t.startswith("forced:") for t in texts) == (cell["shape"] == "forced")
        assert set(texts) <= {q["text"] for q in cell["queries"]}
    records = [json.loads(line) for line in (scratch / "requests.jsonl").read_text().splitlines()]
    assert len(records) == 28 and {r["run_id"] for r in records} == {campaign["run_id"]}
    assert {r["engine"] for r in records} == {"fallback"} and {r["cache"] for r in records} == {False}
    summary = json.loads((scratch / "summary.json").read_text())
    assert {c["run_id"] for c in summary["cells"]} == {campaign["run_id"]}
    assert no_client == []                  # the fake client stood in; the real constructor was never reached


def test_total_deadline_is_labelled_as_a_budget_not_a_window(plan, cases, scratch, monkeypatch):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    cfg = run.measure_config(campaign, started_monotonic=-1e9)       # deadline already passed
    result = benchmark.measure(cfg, lambda: pytest.fail("an expired campaign must not build a client"))
    assert {c["state"] for c in result["cells"]} == {"NOT_RUN_BUDGET"}
    assert {c["stopped_reason"] for c in result["cells"]} == {"TOTAL_TIME_BUDGET"}
    assert all(c["p50_ms_all"] is None and c["measured_n"] == 0 for c in result["cells"])


def test_window_runner_keeps_its_own_deadline_label(scratch):
    """The extension must not relabel the reservation-window runner's stop reason."""
    cfg = {"run_id": "window-run", "queries": [], "budget": {"deadline_monotonic": -1e9},
           "cells": [{"name": "acme_c1", "engine": "gql", "corpus": "acme", "concurrency": 1, "publication_id": "p", "measured": 100}]}
    result = benchmark.measure(cfg, lambda: pytest.fail("no client"))
    assert result["cells"][0]["stopped_reason"] == "WINDOW_DEADLINE"


# --- run_id -------------------------------------------------------------------------------------------

def test_fresh_run_ids_are_labelled_and_never_repeat():
    ids = {run.fresh_run_id() for _ in range(50)}
    assert len(ids) == 50
    assert all(re.fullmatch(r"sqlbase-\d{8}-\d{6}-[0-9a-f]{8}", i) for i in ids)
    assert "legacy-unlabeled" not in ids
    assert not any(i.startswith("live_") for i in ids)
    # every gate label the id seeds is a legal BigQuery label value: the first live campaign failed on exactly this
    for i in ids:
        for cell in ("sqlbase_forced_c1", "sqlbase_forced_c5", "sqlbase_natural_c1", "sqlbase_natural_c5"):
            assert run.LABEL_RE.match(run.gate_label(i, cell))


def test_a_run_id_that_seeds_an_illegal_job_label_is_refused_offline(plan, cases, no_client, tmp_path):
    """Regression for the first live campaign: `sqlbase-20260909T062840Z-a3fc21f5` (uppercase T and Z) became the
    `window` label of every job, BigQuery rejected every insert (400, invalid label characters), each rejected job
    kept its hold as liability, and the campaign stopped BYTES_BUDGET_UNRESOLVED having billed nothing. The gate
    now runs before any client exists, in the freshness check, in the campaign check, and in the CLI."""
    bad = "sqlbase-20260909T062840Z-a3fc21f5"
    with pytest.raises(ValueError, match="not a legal BigQuery label value"):
        run.assert_run_id_is_fresh(bad, summary_path=tmp_path / "none.json", out_dir=tmp_path)
    campaign = run.build_campaign(plan, cases, run_id=bad)
    with pytest.raises(ValueError, match="gate label"):
        run.assert_campaign_is_runnable(campaign)
    out = io.StringIO()
    rc = run.main(["--dry-run", "--run-id", bad, "--out-dir", str(tmp_path)], stdout=out)
    assert rc == 2 and out.getvalue().startswith("INVALID:") and "label" in out.getvalue()
    too_long = "sqlbase-" + "a" * 60
    with pytest.raises(ValueError, match="not a legal BigQuery label value"):
        run.assert_campaign_is_runnable(run.build_campaign(plan, cases, run_id=too_long))
    good = run.build_campaign(plan, cases, run_id="sqlbase-20260909-062840-a3fc21f5")
    run.assert_campaign_is_runnable(good)


def test_run_id_gate_refuses_a_retained_summary_id(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"cells": [{"cell": "acme_c1", "run_id": "sqlbase-20260919-000000-deadbeef"}]}))
    with pytest.raises(ValueError, match="already has a retained summary"):
        run.assert_run_id_is_fresh("sqlbase-20260919-000000-deadbeef", summary_path=summary, out_dir=tmp_path)
    run.assert_run_id_is_fresh("sqlbase-20260919-000000-cafef00d", summary_path=summary, out_dir=tmp_path)


def test_run_id_gate_refuses_a_retained_campaign_record(tmp_path):
    (tmp_path / "run_sqlbase-20260919-000000-deadbeef.json").write_text("{}")
    with pytest.raises(ValueError, match="campaign record"):
        run.assert_run_id_is_fresh("sqlbase-20260919-000000-deadbeef", summary_path=tmp_path / "none.json", out_dir=tmp_path)


def test_run_id_gate_refuses_unlabelled_ids(tmp_path):
    for bad in ("", "legacy-unlabeled", "acme-2026", "live_restricted-x"):
        with pytest.raises(ValueError, match="must start with"):
            run.assert_run_id_is_fresh(bad, summary_path=tmp_path / "none.json", out_dir=tmp_path)


def test_committed_gql_summary_ids_cannot_collide_with_a_campaign(plan, cases):
    """The retained summary is what the driver must not overwrite. Its non-sqlbase ids are the GQL cells; every
    sqlbase-* id it carries must be a campaign whose record is retained beside the plan, and a fresh campaign
    collides with none of them."""
    retained = json.loads((sb.ROOT / benchmark.SUMMARY).read_text())["cells"]
    assert retained and any(not str(c.get("run_id", "")).startswith("sqlbase-") for c in retained)
    records = {p.name[len("run_"):-len(".json")] for p in sb.OUT_DIR.glob("run_sqlbase-*.json")}
    for c in retained:
        if str(c.get("run_id", "")).startswith("sqlbase-"):
            assert c["run_id"] in records, f"summary carries campaign {c['run_id']} with no retained record"
    campaign = run.build_campaign(plan, cases)
    run.assert_run_id_is_fresh(campaign["run_id"], summary_path=sb.ROOT / benchmark.SUMMARY, out_dir=sb.OUT_DIR)


def test_measure_rejects_a_reused_campaign_run_id_before_submitting(plan, cases, scratch):
    (scratch / "summary.json").write_text(json.dumps({"cells": [{"cell": "sqlbase_forced_c1", "run_id": "sqlbase-20260919-000000-deadbeef"}]}))
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    with pytest.raises(ValueError, match="run_id"):
        benchmark.measure(run.measure_config(campaign), lambda: pytest.fail("reused run cannot submit"))
    with pytest.raises(ValueError, match="run_id"):
        run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("no client"), measure=lambda *a: pytest.fail("no measure"))


# --- consumer cells are refused ------------------------------------------------------------------------

def _unselected(plan):
    """The committed plan has been SELECTED since 2026-09-09; the UNSELECTED refusal path still has to work."""
    out = copy.deepcopy(plan)
    out["facts"] = dict(out["facts"], state="UNSELECTED", blocks=["sqlchain_forced_c1", "sqlchain_forced_c5"])
    return out


@pytest.mark.parametrize("name", ["sqlchain_forced_c1", "sqlchain_forced_c5"])
def test_consumer_cells_are_refused_for_the_missing_runner_only(plan, cases, name):
    """Selecting the synthetic fixture digest cleared FACTS_UNSELECTED; NOT_IMPLEMENTED is the one reason left."""
    assert plan["facts"]["state"] == "SELECTED"
    with pytest.raises(run.RefusedCell) as e:
        run.select_cells(plan, [name])
    assert "NOT_IMPLEMENTED" in str(e.value) and "FACTS_UNSELECTED" not in str(e.value)
    assert "No fact-data version is selected" not in str(e.value)
    assert run.refusal_reasons(plan, name) == ["NOT_IMPLEMENTED"]
    with pytest.raises(run.RefusedCell):
        run.build_campaign(plan, cases, ["sqlbase_forced_c1", name])


@pytest.mark.parametrize("name", ["sqlchain_forced_c1", "sqlchain_forced_c5"])
def test_an_unselected_fact_version_is_still_a_second_refusal_reason(plan, name):
    unselected = _unselected(plan)
    assert run.refusal_reasons(unselected, name) == ["FACTS_UNSELECTED", "NOT_IMPLEMENTED"]
    with pytest.raises(run.RefusedCell) as e:
        run.select_cells(unselected, [name])
    assert "FACTS_UNSELECTED + NOT_IMPLEMENTED" in str(e.value)


def test_default_selection_is_exactly_the_retrieval_cells(plan):
    assert [c["name"] for c in run.select_cells(plan)] == run.retrieval_cell_names(plan)
    assert not set(run.retrieval_cell_names(plan)) & set(run.consumer_cell_names(plan))


def test_unknown_and_duplicate_cells_fail(plan):
    with pytest.raises(ValueError, match="not a cell"):
        run.select_cells(plan, ["acme_c1"])
    with pytest.raises(ValueError, match="listed twice"):
        run.select_cells(plan, ["sqlbase_forced_c1", "sqlbase_forced_c1"])


def test_campaign_records_the_refusals_beside_the_cells(plan, cases):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    assert campaign["refused"] == {"sqlchain_forced_c1": ["NOT_IMPLEMENTED"],
                                   "sqlchain_forced_c5": ["NOT_IMPLEMENTED"]}
    text = run.describe(campaign)
    assert "sqlchain_forced_c1: REFUSED (NOT_IMPLEMENTED)" in text and "FACTS_UNSELECTED" not in text


# --- CLI: dry run opens no client ---------------------------------------------------------------------------

def test_dry_run_opens_no_client_and_prints_the_campaign(no_client, tmp_path):
    out = io.StringIO()
    assert run.main(["--dry-run", "--out-dir", str(tmp_path)], stdout=out) == 0
    text = out.getvalue()
    for name in ("sqlbase_forced_c1", "sqlbase_forced_c5", "sqlbase_natural_c1", "sqlbase_natural_c5"):
        assert f"{name}: shape=" in text
    assert "requested on-demand (job reservation override 'none', verified per job), no reservation window" in text
    assert "per-job maximum_bytes_billed" in text
    assert "900 s per cell, 3600 s total" in text
    assert "no client opened" in text
    assert no_client == []
    assert not list(tmp_path.iterdir())     # a dry run retains nothing


def test_dry_run_reports_a_consumer_cell_refusal_without_a_client(no_client, tmp_path):
    out = io.StringIO()
    assert run.main(["--dry-run", "--cells", "sqlchain_forced_c1", "--out-dir", str(tmp_path)], stdout=out) == 2
    assert out.getvalue().startswith("REFUSED:") and "NOT_IMPLEMENTED" in out.getvalue()
    assert "FACTS_UNSELECTED" not in out.getvalue()
    assert no_client == []


def test_dry_run_reports_a_used_run_id_without_a_client(no_client, tmp_path):
    (tmp_path / "run_sqlbase-20260919-000000-deadbeef.json").write_text("{}")
    out = io.StringIO()
    assert run.main(["--dry-run", "--run-id", "sqlbase-20260919-000000-deadbeef", "--out-dir", str(tmp_path)], stdout=out) == 2
    assert out.getvalue().startswith("INVALID:") and "campaign record" in out.getvalue()
    assert no_client == []


def test_live_and_dry_run_are_exclusive_and_one_is_required():
    with pytest.raises(SystemExit):
        run.build_parser().parse_args([])
    with pytest.raises(SystemExit):
        run.build_parser().parse_args(["--dry-run", "--live"])


def test_client_factory_builds_lazily_per_thread_with_caches_off():
    built = []
    factory = run.client_factory("ds_x", make_client=lambda: built.append(1) or object())
    assert built == []
    clients = factory()
    assert built == [1] and clients["engine"] == "fallback" and clients["use_cache"] is False and clients["ds"] == "ds_x"
    assert "cache" not in clients and "journal" not in clients
    assert factory()["bq"] is clients["bq"] and built == [1]


# --- live: record retained, aggregation left to measure ----------------------------------------------------

def test_live_hands_measure_one_config_and_retains_the_record(plan, cases, scratch, no_client):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    handed = {}

    def fake_measure(config, factory):
        handed["config"] = config
        handed["factory"] = factory
        return {"cells": [{"cell": c["name"], "run_id": config["run_id"], "state": "INCOMPLETE" if c["name"].endswith("c5") else "COMPLETE",
                           "measured_n": 3, "measured_target": c["measured"], "p50_ms_all": 1, "p95_ms_all": 2,
                           "stopped_reason": "CELL_TIME_BUDGET" if c["name"].endswith("c5") else None} for c in config["cells"]]}

    record = run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("measure was faked; no client"), measure=fake_measure,
                      preflight=lambda make: {"state": "OK", "reason": None})
    cfg = handed["config"]
    assert cfg["run_id"] == "sqlbase-20260919-000000-deadbeef"
    assert [c["name"] for c in cfg["cells"]] == run.retrieval_cell_names(plan)
    assert all(c["queries"] for c in cfg["cells"]) and cfg["queries"] == []
    assert cfg["budget"]["cell_seconds"] == 900 and cfg["budget"]["deadline_reason"] == "TOTAL_TIME_BUDGET"
    assert record["state"] == "INCOMPLETE"
    saved = json.loads((scratch / "run_sqlbase-20260919-000000-deadbeef.json").read_text())
    assert saved["cells"] == record["cells"] and saved["reservation_window"] is None
    assert saved["edition"] is None and saved["edition_note"].startswith("NOT established: no job was checked")
    assert saved["routing"]["verified_on_demand"] is False and saved["billing"]["bytes_billed_charged"] == 0
    assert callable(cfg["budget"]["window_for_cell"]) and callable(cfg["budget"]["stop_check"])
    assert [c["query_ids"] for c in saved["cells_declared"]][0] == plan["questions"]["forced_seed_ids"]
    assert "queries" not in saved["cells_declared"][0]
    assert no_client == []


def test_live_retains_an_aborted_record(plan, cases, scratch, no_client):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")

    def boom(config, factory):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("no client"), measure=boom,
                 preflight=lambda make: {"state": "OK", "reason": None})
    saved = json.loads((scratch / "run_sqlbase-20260919-000000-deadbeef.json").read_text())
    assert saved["state"] == "ABORTED" and saved["cells"] == [] and saved["error"].startswith("KeyboardInterrupt")


def test_live_preflight_denied_override_stops_before_any_hold_or_job(plan, scratch, monkeypatch):
    """Regression for the second live campaign (`sqlbase-20260909-063150-d30baa0e`): the project denies the on-demand
    override, every insert was rejected 400, and 64 rejected inserts kept 64 GiB of liability with $0 billed. The
    preflight dry run is validated the same way, creates no job, and stops the campaign with nothing held."""
    bq = SyntheticBigQuery(monkeypatch, billed=50 * 1024 ** 2, deny_override=True)
    record = _live(_small(plan, None), bq, scratch)
    assert len(bq.preflights) == 1 and bq.preflights[0]["configuration"]["reservation"] == "none"
    assert bq.preflights[0]["configuration"]["dryRun"] is True and "maximumBytesBilled" not in bq.preflights[0]["configuration"]["query"]
    assert bq.submissions == [] and bq.jobs == {}
    pre = record["preflight"]
    assert pre["state"] == "DENIED" and pre["reason"] == run.PREFLIGHT_DENIED and pre["creates_job"] is False
    assert "reservation_override_mode" in pre["server_message"] and "ALLOW_ANY_OVERRIDE" in pre["remedy"]
    assert pre["requires"] == {"option": "reservation_override_mode", "value": "ALLOW_ANY_OVERRIDE",
                               "scope": "project or organization", "docs": run.OVERRIDE_MODE_DOCS}
    assert record["state"] == "INCOMPLETE" and [c["cell"] for c in record["cells"]] == run.retrieval_cell_names(plan)
    assert all(c["state"] == "NOT_RUN_PREFLIGHT" and c["stopped_reason"] == run.PREFLIGHT_DENIED and c["measured_n"] == 0
               and c["p50_ms_all"] is None for c in record["cells"])
    b = record["billing"]
    assert b["bytes_billed_charged"] == 0 and b["unresolved_liability_bytes"] == 0 and b["holds_outstanding_bytes"] == 0 and b["jobs_settled"] == 0
    assert record["routing"]["jobs_observed"] == 0 and record["edition"] is None and record["gates"] == []
    assert "not_run_note" in record
    saved = json.loads((scratch / f"run_{record['run_id']}.json").read_text())
    assert saved["preflight"]["state"] == "DENIED" and saved["cells"] == record["cells"]


def test_live_preflight_error_fails_closed(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=50 * 1024 ** 2)
    record = run.live(_small(plan, ["sqlbase_forced_c1"]), out_dir=scratch, make_client=bq.make_client,
                      preflight=lambda make: run.preflight_on_demand(lambda: (_ for _ in ()).throw(ConnectionError("synthetic: no route"))))
    assert record["preflight"]["state"] == "ERROR" and record["preflight"]["reason"] == run.PREFLIGHT_ERROR
    assert bq.submissions == [] and record["cells"][0]["stopped_reason"] == run.PREFLIGHT_ERROR


def test_live_preflight_passes_then_every_job_is_submitted_with_the_override(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=50 * 1024 ** 2)
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    assert len(bq.preflights) == 1 and record["preflight"]["state"] == "OK" and record["preflight"]["creates_job"] is False
    assert bq.submissions and record["cells"][0]["state"] == "COMPLETE"


def test_cli_live_prints_the_preflight_outcome_and_exits_nonzero_when_denied(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=50 * 1024 ** 2, deny_override=True)
    real_client = bigquery.Client
    monkeypatch.setattr(bigquery, "Client", lambda **kw: real_client(project=run.PROJECT, location=run.LOCATION, credentials=AnonymousCredentials()))
    out = io.StringIO()
    rc = run.main(["--live", "--run-id", "sqlbase-20260919-000000-regress0", "--out-dir", str(scratch)], stdout=out)
    text = out.getvalue()
    assert rc == 1 and "preflight: DENIED (ON_DEMAND_OVERRIDE_DENIED)" in text and "NOT_RUN_PREFLIGHT" in text
    assert bq.submissions == []


def test_live_refuses_a_campaign_over_the_projected_ceiling(plan, cases, scratch):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    campaign["budget_projection"]["within_budget"] = False
    with pytest.raises(ValueError, match="exceed the declared ceiling"):
        run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("no client"), measure=lambda *a: pytest.fail("no measure"))
    assert not list(scratch.iterdir())


def test_live_refuses_a_window(plan, cases, scratch):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919-000000-deadbeef")
    campaign["reservation_window"] = "US.okf-demo-enterprise"
    with pytest.raises(ValueError, match="on-demand"):
        run.assert_campaign_is_runnable(campaign)


# --- the card's command lines name this driver and parse -----------------------------------------------------

def test_card_command_lines_name_this_driver_and_parse(plan):
    card = sb.build_card(copy.deepcopy(plan), records=[])
    for cell in card["cells"]:
        if cell["metric"] != "retrieval_ms":
            assert "sql_baseline_run" not in cell["how_to_fill"] or "refuses" in cell["how_to_fill"]
            continue
        assert cell["stopped_reason"] == "NOT_RUN"
        commands = re.findall(r"`(python3 -m okf_bq_graph\.sql_baseline_run[^`]*)`", cell["how_to_fill"])
        assert commands, cell["cell"]
        for command in commands:
            args = run.build_parser().parse_args(command.split()[3:])
            assert args.cells == [cell["cell"]]
        assert any("--dry-run" in c for c in commands) and any("--live" in c for c in commands)


# --- Astra PR55 P1 regressions: the real driver → measure → retrieve → SDK path, offline -------------------------------
#
# Only `bigquery.Client._call_api` is replaced (at the class, so the job-local result client the gate builds is covered
# too), with AnonymousCredentials and no network. The clock is injected. These are counterexamples, not measurements.

import time as _time
from google.api_core.exceptions import BadRequest, NotFound, ServiceUnavailable
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery
from requests.exceptions import ConnectionError, ReadTimeout


class SyntheticBigQuery:
    """Synthetic API responses behind the real SDK. `billed` bytes per job; `enterprise` statistics; `advance_at` jumps
    the injected clock by `advance_seconds` when the n-th job is inserted; `honor_cap` fails a job whose
    maximumBytesBilled is below `billed`, the way BigQuery refuses a job over its byte limit before running it."""

    def __init__(self, monkeypatch, *, billed=0, enterprise=False, advance_at=None, advance_seconds=0, honor_cap=False,
                 bill_hold=False, lose_submit_at=(), lose_result_at=(), readback_unavailable=False,
                 fail_at=(), fail_enterprise_at=(), omit_stats=False,
                 defer_insert_at=(), never_commit=False, reveal_enterprise_at_readback=False, deny_override=False):
        self.clock = [1000.0]
        self.submissions, self.cancels, self.jobs, self.readbacks = [], [], {}, []
        self.preflights, self.deny_override = [], deny_override
        self.billed, self.enterprise, self.honor_cap = billed, enterprise, honor_cap
        self.advance_at, self.advance_seconds = advance_at, advance_seconds
        self.bill_hold = bill_hold                       # bill exactly the transmitted cap (min 1 GiB): Astra's ledger probe
        self.lose_submit_at, self.lose_result_at = set(lose_submit_at), set(lose_result_at)
        self.readback_unavailable = readback_unavailable
        self.fail_at, self.fail_enterprise_at, self.omit_stats = set(fail_at), set(fail_enterprise_at), omit_stats
        self.lost_ids, self.pending_result = set(), set()
        # Astra RR3 fault model: the insert times out client-side but stays queued remotely; reads and cancels return a
        # truthful 404 until it commits, which happens when the next gate's first insert arrives (or never).
        self.defer_insert_at, self.never_commit = set(defer_insert_at), never_commit
        self.deferred, self.commits = {}, []
        self.reveal_enterprise_at_readback = reveal_enterprise_at_readback
        monkeypatch.setattr(_time, "monotonic", lambda: self.clock[0])
        monkeypatch.setattr(bigquery.Client, "_call_api", self.api)

    def make_client(self):
        return bigquery.Client(project=run.PROJECT, location=run.LOCATION, credentials=AnonymousCredentials())

    def api(self, retry, **kw):   # bound here, so the SDK's `self` is not passed through
        method, path = kw["method"], kw["path"]
        if method == "POST" and path.endswith("/jobs"):
            data = json.loads(json.dumps(kw["data"]))
            if data["configuration"].get("dryRun"):
                # the on-demand preflight: BigQuery validates a dry run against the project configuration but creates no
                # job (no jobReference in the response); it is not a submission and takes no ordinal
                self.preflights.append(data)
                if self.deny_override:
                    raise BadRequest("400 POST .../jobs?prettyPrint=false: Override to 'none' is not enabled. The option "
                                     "'reservation_override_mode' is set to 'RESERVATION_OVERRIDE_MODE_UNSPECIFIED'. "
                                     "See https://cloud.google.com/bigquery/docs/default-configuration")
                return {"kind": "bigquery#job", "configuration": data["configuration"], "status": {"state": "DONE"},
                        "statistics": {"creationTime": "1000", "query": {"totalBytesProcessed": "0", "totalBytesBilled": "0"}}}
            cap = data["configuration"]["query"].get("maximumBytesBilled")
            self.submissions.append({"at": self.clock[0], "configuration": data["configuration"]})
            if len(self.submissions) == self.advance_at:
                self.clock[0] += self.advance_seconds
            n = len(self.submissions)
            refused = self.honor_cap and cap is not None and int(cap) < self.billed
            billed = 0 if refused else (min(run.PER_JOB_CAP_BYTES, int(cap)) if self.bill_hold else self.billed)
            stat = {"creationTime": "1000", "startTime": "1000", "endTime": "1001",
                    "query": {"totalBytesProcessed": str(billed), "totalBytesBilled": str(billed), "totalSlotMs": "1", "cacheHit": False}}
            if self.enterprise or n in self.fail_enterprise_at:
                stat.update(edition="ENTERPRISE", reservation_id="test-project-0728-467323:US.okf-demo-enterprise")
            status = {"state": "DONE"}
            if refused:
                err = {"reason": "bytesBilledLimitExceeded", "message": f"Query exceeded limit for bytes billed: {cap}"}
                status.update(errorResult=err, errors=[err])
            if n in self.fail_at or n in self.fail_enterprise_at:
                err = {"reason": "invalidQuery", "message": "synthetic invalidQuery"}
                status.update(errorResult=err, errors=[err])
            job = dict(data, status=status)
            if not self.omit_stats:
                job["statistics"] = stat
            job_id = data["jobReference"]["jobId"]
            window = data["configuration"]["labels"]["window"]
            if self.deferred and not self.never_commit and any(w != window for _, w in self.deferred.values()):
                for jid, (deferred_job, _) in list(self.deferred.items()):
                    self.jobs[jid] = deferred_job         # the queued insert commits once the next gate is at work
                    self.commits.append(jid)
                self.deferred.clear()
            if n in self.defer_insert_at:
                if self.reveal_enterprise_at_readback:
                    job["statistics"] = dict(stat, edition="ENTERPRISE", reservation_id="test-project-0728-467323:US.okf-demo-enterprise")
                self.deferred[job_id] = (job, window)
                raise ReadTimeout("synthetic: insert queued remotely, no response before the client timeout")
            self.jobs[job_id] = job                       # the server keeps the job even when the client loses the response
            if n in self.lose_submit_at:
                self.lost_ids.add(job_id)
                raise ConnectionError("synthetic: job accepted, connection closed before the response")
            if n in self.lose_result_at:
                self.pending_result.add(job_id)
                return dict(data, status={"state": "RUNNING"}, statistics={"creationTime": "1000"})
            return job
        if method == "GET" and "/queries/" in path:
            job_id = path.split("/queries/")[1].split("?")[0]
            if job_id in self.pending_result:                 # the final result stays unreadable until the gate seals
                raise ReadTimeout("synthetic: result response lost")
            return {"jobComplete": True, "totalRows": "0", "schema": {"fields": []}, "rows": []}
        if method == "POST" and path.endswith("/cancel"):
            job_id = path.split("/jobs/")[1].split("/cancel")[0]
            self.cancels.append(job_id)
            if job_id in self.deferred or (self.never_commit and job_id not in self.jobs):
                raise NotFound("synthetic: the insert has not committed")
            self.pending_result.discard(job_id)                # after the seal the server's terminal record is readable
            if self.reveal_enterprise_at_readback and job_id in self.jobs and "statistics" in self.jobs[job_id]:
                self.jobs[job_id]["statistics"].update(edition="ENTERPRISE", reservation_id="test-project-0728-467323:US.okf-demo-enterprise")
            return {"job": self.jobs[job_id]}
        if method == "GET" and "/jobs/" in path:
            job_id = path.split("/jobs/")[1].split("?")[0]
            self.readbacks.append(job_id)
            if job_id in self.deferred or (self.never_commit and job_id not in self.jobs):
                raise NotFound("synthetic: the insert has not committed")
            if self.readback_unavailable or job_id in self.pending_result:
                raise ServiceUnavailable("synthetic: job status unavailable")
            return self.jobs[job_id]
        raise AssertionError(f"unexpected API call: {method} {path}")


def _small(plan, names, warmups=1, measured=3):
    small = copy.deepcopy(plan)
    for cell in small["retrieval_cells"]:
        cell["warmups"], cell["measured"] = warmups, measured
    return run.build_campaign(small, run.load_cases(), names, run_id="sqlbase-20260919-000000-regress0")


def _live(campaign, synthetic, scratch):
    return run.live(campaign, out_dir=scratch, make_client=synthetic.make_client)


def test_every_job_carries_the_on_demand_override_and_a_byte_cap(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=50 * 1024 ** 2)
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    assert bq.submissions and all(s["configuration"]["reservation"] == "none" for s in bq.submissions)
    caps = [int(s["configuration"]["query"]["maximumBytesBilled"]) for s in bq.submissions]
    assert all(0 < c <= run.PER_JOB_CAP_BYTES for c in caps)
    cell = record["cells"][0]
    assert cell["state"] == "COMPLETE" and cell["stopped_reason"] is None and cell["measured_n"] == 3
    assert record["edition"] == "on-demand" and record["routing"]["verified_on_demand"] is True
    assert record["routing"]["jobs_observed"] == record["routing"]["jobs_verified_on_demand"] == len(bq.submissions) == 12
    assert record["billing"]["bytes_billed_charged"] == 12 * 50 * 1024 ** 2 and record["billing"]["exhausted"] is False
    assert record["billing"]["holds_outstanding_bytes"] == 0
    assert record["state"] == "COMPLETE"


def test_inherited_enterprise_assignment_fails_closed(plan, scratch, monkeypatch):
    """Astra PR55 #1: synthetic ENTERPRISE statistics used to yield an on-demand COMPLETE campaign."""
    bq = SyntheticBigQuery(monkeypatch, enterprise=True)
    record = _live(_small(plan, ["sqlbase_forced_c1", "sqlbase_forced_c5"]), bq, scratch)
    first, second = record["cells"]
    # the very first (warmup) job violated, so no measured attempt exists: NOT_RUN_BUDGET is the runner's label for that
    assert first["state"] == "NOT_RUN_BUDGET" and first["stopped_reason"] == "ROUTING_VIOLATION"
    assert first["warmups_done"] == 1 and first["measured_n"] == 0
    assert second["state"] == "NOT_RUN_BUDGET" and second["stopped_reason"] == "ROUTING_VIOLATION"
    assert record["state"] == "INCOMPLETE"
    assert record["edition"] is None and "1 job(s) reported a reservation or edition" in record["edition_note"]
    assert record["routing"]["verified_on_demand"] is False
    assert record["routing"]["violations"][0]["edition"] == "ENTERPRISE"
    assert record["routing"]["violations"][0]["reservation_id"].endswith("US.okf-demo-enterprise")
    assert len(bq.submissions) == 1                    # the first job's statistics stopped everything after it
    assert bq.submissions[0]["configuration"]["reservation"] == "none"
    attempts = [json.loads(line) for line in (scratch / "requests.jsonl").read_text().splitlines()]
    assert [a["status"] for a in attempts] == ["ROUTING_VIOLATION"]
    # nothing touched the standing reservation: the only calls were the job insert and the query read
    assert bq.cancels == []


def test_routing_guard_unit():
    guard = run.RoutingGuard()
    assert guard.verified() is False and guard.stop_reason() is None
    done = {"server_state": "DONE", "stats_present": True, "reservation_id": None, "edition": None}
    guard.check(dict(done, job_id="a"))
    assert guard.verified() is True
    # no terminal statistics: unknown, and unknown withholds the label until a readback resolves it
    assert guard.observe({"job_id": "u", "server_state": "RUNNING", "stats_present": False}) == "UNKNOWN"
    assert guard.verified() is False and guard.stop_reason() is None
    assert guard.resolve("u", {"server_state": "RUNNING", "stats_present": False}) is False
    assert guard.resolve("u", dict(done, job_id="u")) is True and guard.verified() is True
    assert guard.observe({"job_id": None, "server_state": None, "stats_present": False}) == "UNKNOWN"
    assert guard.resolve("unresolvable-1", None, absent=True) is True and guard.verified() is True
    # a failed job with a reservation is a violation too
    assert guard.observe(dict(done, job_id="f", state="FAILED", edition="ENTERPRISE")) == "VIOLATION"
    with pytest.raises(run.RoutingViolation, match="not on-demand"):
        guard.check({"job_id": "b", "reservation_id": None, "edition": "ENTERPRISE", "server_state": "DONE", "stats_present": True})
    with pytest.raises(run.RoutingViolation):
        guard.check({"job_id": "c", "reservation_id": "p:US.r", "edition": None})
    assert guard.stop_reason() == "ROUTING_VIOLATION" and guard.verified() is False
    assert guard.snapshot()["violations"][0]["job_state"] == "FAILED"


def test_clock_advance_during_the_last_request_cannot_complete_the_cell(plan, scratch, monkeypatch):
    """Astra PR55 #2 repro: 20 + 100 at C=1; the clock jumps 4,000 s during the 120th request's walk job.
    Before: context and nodes were submitted after both deadlines and the cell was COMPLETE, stopped_reason null."""
    bq = SyntheticBigQuery(monkeypatch, advance_at=358, advance_seconds=4000)
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1"], run_id="sqlbase-20260919-000000-regress0")
    record = _live(campaign, bq, scratch)
    cell = record["cells"][0]
    assert len(bq.submissions) == 358                  # the walk that crossed the deadline was the last submission
    assert sum(s["at"] >= 4600 for s in bq.submissions) == 0
    assert cell["state"] == "INCOMPLETE" and cell["stopped_reason"] == "TOTAL_TIME_BUDGET"
    assert cell["measured_n"] == 100 and cell["gated"] == 1 and cell["success_rate"] < 1
    assert record["state"] == "INCOMPLETE"
    attempts = [json.loads(line) for line in (scratch / "requests.jsonl").read_text().splitlines()]
    assert len(attempts) == 120 and attempts[-1]["status"] == "STOPPED"
    assert [j["stage"] for j in attempts[-1]["timing"]["jobs"]] == ["walk"]      # no context, no nodes
    assert bq.cancels                                  # the in-flight walk was cancelled through the gate
    receipt = json.loads((scratch / "jobs_sqlbase-20260919-000000-regress0_sqlbase_forced_c1.cleanup.json").read_text())
    assert receipt["verified"] is True


def test_cell_deadline_stops_one_cell_and_the_next_cell_gets_a_fresh_gate(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, advance_at=10, advance_seconds=1000)   # walk of the 4th and last request
    record = _live(_small(plan, ["sqlbase_forced_c1", "sqlbase_forced_c5"]), bq, scratch)
    first, second = record["cells"]
    assert first["state"] == "INCOMPLETE" and first["stopped_reason"] == "CELL_TIME_BUDGET"
    assert first["measured_n"] == 3 and first["gated"] == 1
    assert second["state"] == "COMPLETE" and second["stopped_reason"] is None and second["measured_n"] == 3
    assert len(bq.submissions) == 10 + 12
    assert [g["cell"] for g in record["gates"]] == ["sqlbase_forced_c1", "sqlbase_forced_c5"]
    assert all(g["deadline_seconds_from_cell_start"] <= 900 for g in record["gates"])


def test_billed_bytes_stop_the_campaign_when_the_server_reports_more_than_the_cap(plan, scratch, monkeypatch):
    """Astra PR55 #3 repro: synthetic 30 GiB per job used to submit all 360 jobs and return COMPLETE against 64 GiB."""
    bq = SyntheticBigQuery(monkeypatch, billed=30 * sb.GIB)
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1", "sqlbase_forced_c5"], run_id="sqlbase-20260919-000000-regress0")
    record = _live(campaign, bq, scratch)
    first, second = record["cells"]
    # the first warmup request alone charged 90 GiB, so the cell stopped before a measured attempt existed
    assert first["state"] == "NOT_RUN_BUDGET" and first["stopped_reason"] == "BYTES_BUDGET"
    assert first["warmups_done"] == 1 and first["measured_n"] == 0   # the ceiling check refused the second admission
    assert second["state"] == "NOT_RUN_BUDGET" and second["stopped_reason"] == "BYTES_BUDGET"
    assert record["state"] == "INCOMPLETE"
    assert len(bq.submissions) == 3                    # walk, then context + nodes; the next walk found no room
    assert all(int(s["configuration"]["query"]["maximumBytesBilled"]) <= run.PER_JOB_CAP_BYTES for s in bq.submissions)
    billing = record["billing"]
    assert billing["exhausted"] is True
    assert billing["bytes_billed_charged"] == 3 * 30 * sb.GIB and billing["holds_outstanding_bytes"] == 0
    assert billing["ceiling_bytes"] == 64 * sb.GIB and billing["ceiling_binding"] == "BYTES_BUDGET"
    attempts = [json.loads(line) for line in (scratch / "requests.jsonl").read_text().splitlines()]
    assert len(attempts) == 1 and attempts[0]["warmup"] is True


def test_a_job_with_no_room_is_never_submitted(scratch):
    """The in-request path: `_run` takes its hold before `query()`; with none available nothing reaches the client."""
    from okf_bq_graph import retrieve as R

    class NeverClient:
        def query(self, *a, **kw):
            raise AssertionError("a job was submitted without room in the ledger")

    ledger = run.BytesLedger(max_bytes=64 * sb.GIB, usd_per_tib=6.25, max_usd=0.5)
    ledger.charged = ledger.cap_bytes
    clients = {"engine": "fallback", "bq": NeverClient(), "bytes_ledger": ledger, "routing": run.RoutingGuard()}
    with pytest.raises(R.BudgetExhausted, match="BYTES_BUDGET"):
        R._run(clients, "walk", "SELECT 1", [], R.Timer())
    assert ledger.refused == 1 and ledger.jobs == 0
    rec = benchmark.one_request({"name": "c", "engine": "fallback", "corpus": "acme", "publication_id": "p", "run_id": "r",
                                 "warmups": 0, "as_of": "2026-09-05T00:00:00Z", "concurrency": 1},
                                0, {"id": "f_current", "text": "forced:metrics/gross-margin.md", "bundle_id": "acme_retail"}, clients, 60)
    assert rec["status"] == "BUDGET_EXHAUSTED" and rec["ok"] is False and rec["timing"]["jobs"] == []


def test_server_side_cap_refuses_a_job_over_its_limit_without_charging(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=30 * sb.GIB, honor_cap=True)
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    cell = record["cells"][0]
    assert cell["state"] == "COMPLETE" and cell["success_rate"] == 0 and cell["errors"] == 3
    assert record["billing"]["bytes_billed_charged"] == 0 and record["billing"]["exhausted"] is False
    assert len(bq.submissions) == 4                    # one refused walk per request; no context/nodes follow a failed walk
    attempts = [json.loads(line) for line in (scratch / "requests.jsonl").read_text().splitlines()]
    assert all("bytesBilledLimitExceeded" in a["error"] or "exceeded limit" in a["error"] for a in attempts)


def test_ledger_unit_holds_concurrency_and_failures():
    ledger = run.BytesLedger(max_bytes=100 * sb.GIB, usd_per_tib=6.25, max_usd=0.5, per_job_cap=sb.GIB)
    assert ledger.cap_bytes == int(0.5 / 6.25 * sb.TIB) and ledger.binding == "USD_BUDGET"   # $0.50 is tighter than 100 GiB
    holds = [ledger.hold() for _ in range(10)]
    assert all(h == sb.GIB for h in holds) and ledger.held == 10 * sb.GIB
    for h in holds:
        ledger.settle(h, 9 * sb.GIB)                   # every job billed past its hold: still charged, failures included
    assert ledger.charged == 90 * sb.GIB and ledger.held == 0 and ledger.jobs == 10   # 90 GiB > the $0.50 ceiling (81.9 GiB)
    assert ledger.exhausted() and ledger.stop_reason() == "USD_BUDGET" and ledger.hold() is None
    assert ledger.refused == 1
    tight = run.BytesLedger(max_bytes=64 * sb.GIB, usd_per_tib=6.25, max_usd=0.5)
    assert tight.binding == "BYTES_BUDGET" and tight.per_job_cap == run.PER_JOB_CAP_BYTES
    small = run.BytesLedger(max_bytes=5 * 1024 ** 2, usd_per_tib=6.25, max_usd=0.5)
    assert small.hold() is None                        # less than BigQuery's 10 MiB minimum is no room at all


def test_stop_check_hook_stops_a_cell_between_requests(plan, cases, scratch, monkeypatch):
    calls = []
    monkeypatch.setattr(benchmark, "retrieve", lambda *a, **kw: calls.append(1) or {
        "status": "OK", "concepts": [], "paths": [], "computations": [], "timing": {"total_ms": 1.0, "stages_ms": {}, "jobs": []}})
    campaign = _small(plan, ["sqlbase_forced_c1"], warmups=0, measured=5)
    cfg = run.measure_config(campaign)
    cfg["budget"]["stop_check"] = lambda: "USD_BUDGET" if len(calls) >= 2 else None
    result = benchmark.measure(cfg, run.client_factory("ds", make_client=lambda: object()))
    cell = result["cells"][0]
    assert cell["state"] == "INCOMPLETE" and cell["stopped_reason"] == "USD_BUDGET" and cell["measured_n"] == 2


def test_client_factory_with_a_runtime_refuses_an_unbounded_client(plan, cases, tmp_path):
    campaign = run.build_campaign(plan, cases, ["sqlbase_forced_c1"], run_id="sqlbase-20260919-000000-regress0")
    runtime = run.CampaignRuntime(campaign, tmp_path, deadline_monotonic=_time.monotonic() + 3600)
    factory = run.client_factory("ds", make_client=lambda: object(), runtime=runtime)
    with pytest.raises(RuntimeError, match="no submission gate"):
        factory()
    window = runtime.window_for_cell(campaign["cells"][0], _time.monotonic())
    clients = factory()
    assert clients["bq"].window is window and clients["bytes_ledger"] is runtime.ledger and clients["routing"] is runtime.routing
    assert clients["routing"].reservation == "none"


# --- Astra PR55 re-review residuals ---------------------------------------------------------------------------------------

def _attempts(scratch):
    return [json.loads(line) for line in (scratch / "requests.jsonl").read_text().splitlines()]


def test_lost_submission_keeps_its_hold_until_the_readback_charges_it(plan, scratch, monkeypatch):
    """RR #1: an accepted job whose response was lost used to settle as zero bytes."""
    bq = SyntheticBigQuery(monkeypatch, billed=sb.GIB, lose_submit_at={1})
    record = _live(_small(plan, ["sqlbase_forced_c1"], warmups=0, measured=4), bq, scratch)
    attempts = _attempts(scratch)
    first = attempts[0]
    assert first["status"] == "ERROR" and "ConnectionError" in first["error"]
    lost = first["timing"]["jobs"][0]
    assert lost["state"] == "SUBMISSION_UNCONFIRMED" and lost["job_id"] in bq.lost_ids
    assert lost["job_ref"]["window"].endswith("sqlbase_forced_c1") and lost["job_ref"]["notfound_is_done"] is True
    # the lost job is charged after the gate sealed and read it back: 1 (lost) + 3 requests x 3 jobs
    billing = record["billing"]
    assert billing["bytes_billed_charged"] == 10 * sb.GIB and billing["unresolved_liability_bytes"] == 0
    assert billing["resolved_by_readback"][0]["job_id"] == lost["job_id"]
    assert billing["resolved_by_readback"][0]["outcome"] == f"charged {sb.GIB} bytes"
    rec = record["reconciliations"][0]
    assert rec["cell"] == "sqlbase_forced_c1" and rec["jobs"][0]["ledger"] == "charged" and rec["jobs"][0]["routing"] == "OK"
    assert lost["job_id"] in bq.readbacks and lost["job_id"] in bq.cancels    # cancelled at seal, then read for billing
    assert record["edition"] == "on-demand" and record["routing"]["unknown"] == []
    assert record["cells"][0]["state"] == "COMPLETE" and record["cells"][0]["errors"] == 1


def test_lost_submissions_cannot_push_the_server_bill_past_the_ceiling(plan, scratch, monkeypatch):
    """Astra's ledger probe: every job bills exactly its transmitted cap. One lost response used to allow 65 GiB."""
    bq = SyntheticBigQuery(monkeypatch, bill_hold=True, lose_submit_at={1, 2, 3})
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1"], run_id="sqlbase-20260919-000000-regress0")
    record = _live(campaign, bq, scratch)
    server_billed = sum(int(s["configuration"]["query"]["maximumBytesBilled"]) for s in bq.submissions)
    assert server_billed <= 64 * sb.GIB
    billing = record["billing"]
    assert billing["bytes_billed_charged"] + billing["unresolved_liability_bytes"] == server_billed
    assert billing["unresolved_liability_bytes"] == 0          # the seal read all three lost jobs back
    assert record["cells"][0]["stopped_reason"] in ("BYTES_BUDGET", "BYTES_BUDGET_UNRESOLVED")
    assert record["state"] == "INCOMPLETE"


def test_unavailable_final_billing_keeps_the_hold(plan, scratch, monkeypatch):
    """RR #1: a job whose result and status could not be read used to settle as zero bytes."""
    bq = SyntheticBigQuery(monkeypatch, billed=sb.GIB, lose_result_at={1}, readback_unavailable=True)
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    first = _attempts(scratch)[0]
    assert first["status"] == "ERROR" and ("ReadTimeout" in first["error"] or "ServiceUnavailable" in first["error"])
    assert first["timing"]["jobs"][0]["server_state"] == "RUNNING" and first["timing"]["jobs"][0]["bytes_billed"] is None
    billing = record["billing"]
    assert billing["unresolved_liability_bytes"] == sb.GIB and len(billing["unresolved_jobs"]) == 1
    assert billing["unresolved_jobs"][0]["job_id"] == first["timing"]["jobs"][0]["job_id"]
    assert billing["bytes_billed_charged"] == 9 * sb.GIB      # the other nine jobs; the unknown one is liability, not zero
    assert record["reconciliations"][0]["jobs"][0]["ledger"].startswith("still unresolved: ServiceUnavailable")
    assert record["edition"] is None and "1 job(s) have no terminal statistics" in record["edition_note"]
    assert record["routing"]["unknown"][0]["server_state"] == "RUNNING"


def test_unavailable_final_billing_resolves_when_the_readback_succeeds(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=sb.GIB, lose_result_at={1})
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    billing = record["billing"]
    assert billing["unresolved_liability_bytes"] == 0 and billing["bytes_billed_charged"] == 10 * sb.GIB
    assert record["edition"] == "on-demand" and record["routing"]["unknown"] == []


def test_unresolved_liability_consumes_room_and_is_named_as_such(plan, scratch, monkeypatch):
    """Liability nobody can resolve stays counted; the stop reason says the room is unresolved, not billed."""
    bq = SyntheticBigQuery(monkeypatch, bill_hold=True, lose_result_at=set(range(1, 400)), readback_unavailable=True)
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1"], run_id="sqlbase-20260919-000000-regress0")
    record = _live(campaign, bq, scratch)
    billing = record["billing"]
    assert billing["bytes_billed_charged"] == 0
    assert billing["unresolved_liability_bytes"] == sum(int(s["configuration"]["query"]["maximumBytesBilled"]) for s in bq.submissions)
    assert billing["unresolved_liability_bytes"] <= 64 * sb.GIB
    assert record["cells"][0]["stopped_reason"] == "BYTES_BUDGET_UNRESOLVED"
    assert record["edition"] is None


def test_a_hold_with_no_journaled_id_is_liability_nobody_can_resolve():
    from okf_bq_graph import retrieve as R

    class LosesTheResponse:
        def query(self, *a, **kw):
            raise ConnectionError("no gate, no id")

    ledger = run.BytesLedger(max_bytes=64 * sb.GIB, usd_per_tib=6.25, max_usd=0.5)
    clients = {"engine": "fallback", "bq": LosesTheResponse(), "bytes_ledger": ledger, "routing": run.RoutingGuard()}
    with pytest.raises(ConnectionError):
        R._run(clients, "walk", "SELECT 1", [], R.Timer())
    snap = ledger.snapshot()
    assert snap["unresolved_liability_bytes"] == run.PER_JOB_CAP_BYTES and snap["unresolved_jobs"][0]["resolvable"] is False
    assert ledger.room() == ledger.cap_bytes - run.PER_JOB_CAP_BYTES
    assert ledger.resolve("unresolvable-1", 0) is True     # only the caller's own key can release it; no readback ever will


def test_ledger_resolve_unit():
    ledger = run.BytesLedger(max_bytes=64 * sb.GIB, usd_per_tib=6.25, max_usd=0.5)
    hold = ledger.hold()
    ledger.unresolved(hold, "job-a", "lost")
    assert ledger.room() == ledger.cap_bytes - hold and ledger.liability() == hold
    assert ledger.resolve("job-a", 123) is True and ledger.charged == 123 and ledger.held == 0
    hold = ledger.hold(); ledger.unresolved(hold, "job-b", "lost")
    assert ledger.resolve("job-b", absent=True) is True and ledger.charged == 123 and ledger.held == 0
    assert ledger.resolve("job-b") is False
    exhausted = run.BytesLedger(max_bytes=2 * sb.GIB, usd_per_tib=6.25, max_usd=0.5)
    for jid in ("x", "y"):
        exhausted.unresolved(exhausted.hold(), jid, "lost")
    assert exhausted.stop_reason() == "BYTES_BUDGET_UNRESOLVED"
    exhausted.resolve("x", sb.GIB); exhausted.resolve("y", sb.GIB)
    assert exhausted.stop_reason() == "BYTES_BUDGET"


def test_failed_enterprise_job_is_a_violation_that_stops_admission(plan, scratch, monkeypatch):
    """RR #2: a failed job carrying ENTERPRISE statistics used to skip verification; 297 jobs followed it."""
    bq = SyntheticBigQuery(monkeypatch, billed=10 * 1024 ** 2, fail_enterprise_at={2})
    record = _live(_small(plan, ["sqlbase_forced_c1", "sqlbase_forced_c5"]), bq, scratch)
    first, second = record["cells"]
    assert first["stopped_reason"] == "ROUTING_VIOLATION" and first["state"] == "NOT_RUN_BUDGET"
    assert second["state"] == "NOT_RUN_BUDGET" and second["stopped_reason"] == "ROUTING_VIOLATION"
    assert len(bq.submissions) <= 3                    # request 1's walk, context, nodes; nothing after the mismatch
    assert record["edition"] is None and "reported a reservation or edition" in record["edition_note"]
    violation = record["routing"]["violations"][0]
    assert violation["job_state"] == "FAILED" and violation["edition"] == "ENTERPRISE"
    attempts = _attempts(scratch)
    assert attempts[0]["status"] == "ERROR" and "invalidQuery" in attempts[0]["error"]


def test_failed_enterprise_job_on_the_first_warmup(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=10 * 1024 ** 2, fail_enterprise_at={1})
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    assert len(bq.submissions) == 1 and record["edition"] is None
    assert record["cells"][0]["stopped_reason"] == "ROUTING_VIOLATION"


def test_missing_statistics_leave_routing_unknown(plan, scratch, monkeypatch):
    """RR #2: jobs without statistics used to certify on-demand."""
    bq = SyntheticBigQuery(monkeypatch, omit_stats=True)
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    assert record["cells"][0]["state"] == "COMPLETE"      # unknown routing is withheld, not a stop
    assert record["edition"] is None and "12 job(s) have no terminal statistics" in record["edition_note"]
    assert record["routing"]["verified_on_demand"] is False and len(record["routing"]["unknown"]) == 12
    assert record["billing"]["unresolved_liability_bytes"] == 12 * run.PER_JOB_CAP_BYTES     # unknown billing is liability too
    assert record["reconciliations"][0]["jobs"][0]["ledger"] == "still unresolved: no terminal billing"


def test_ordinary_context_error_is_a_retained_failure_not_a_cell_deadline(plan, scratch, monkeypatch):
    """RR #3: an invalidQuery in the context job used to cancel the gate and label the cell CELL_TIME_BUDGET at wall 0."""
    bq = SyntheticBigQuery(monkeypatch, billed=10 * 1024 ** 2, fail_at={2})
    record = _live(_small(plan, ["sqlbase_forced_c1"], warmups=0, measured=4), bq, scratch)
    cell = record["cells"][0]
    assert cell["state"] == "COMPLETE" and cell["stopped_reason"] is None and cell["errors"] == 1
    assert cell["measured_n"] == 4 and len(bq.submissions) == 12
    attempts = _attempts(scratch)
    assert attempts[0]["status"] == "ERROR" and "invalidQuery" in attempts[0]["error"]
    failed = next(j["job_id"] for j in attempts[0]["timing"]["jobs"] if j["state"] == "FAILED")
    assert set(bq.cancels) <= {failed}                 # the seal re-checks the failed job only; no live job was cancelled
    assert record["edition"] == "on-demand"             # the failed job was observed and was on-demand


def test_gate_stopped_for_a_non_deadline_reason_keeps_that_reason(plan, cases, scratch, monkeypatch, tmp_path):
    from okf_bq_graph.lifecycle import WindowJobs
    gate = {}

    def window_for_cell(cell, started):
        gate["w"] = WindowJobs("t", started + 900, tmp_path / "jobs.json")
        return gate["w"]

    def retrieve(*a, **kw):
        gate["w"].stop.set()                           # something other than a deadline stopped the gate
        raise RuntimeError("synthetic cancellation cause")

    monkeypatch.setattr(benchmark, "retrieve", retrieve)
    campaign = _small(plan, ["sqlbase_forced_c1"], warmups=0, measured=5)
    cfg = run.measure_config(campaign)
    cfg["budget"]["window_for_cell"] = window_for_cell
    cell = benchmark.measure(cfg, run.client_factory("ds", make_client=lambda: object()))["cells"][0]
    assert cell["stopped_reason"] == "GATE_STOPPED" and cell["stopped_detail"] == "RuntimeError: synthetic cancellation cause"
    assert cell["state"] == "INCOMPLETE" and cell["wall_seconds"] < 900


def test_a_gate_refusal_before_journaling_releases_the_hold():
    """A WindowStopped raised at admission carries no id: nothing was sent, so the room is not liability."""
    from okf_bq_graph import retrieve as R
    from okf_bq_graph.lifecycle import WindowStopped

    class RefusesAdmission:
        def query(self, *a, **kw):
            raise WindowStopped("reservation window stopped or deadline reached")

    ledger = run.BytesLedger(max_bytes=64 * sb.GIB, usd_per_tib=6.25, max_usd=0.5)
    guard = run.RoutingGuard()
    clients = {"engine": "fallback", "bq": RefusesAdmission(), "bytes_ledger": ledger, "routing": guard}
    with pytest.raises(WindowStopped):
        R._run(clients, "walk", "SELECT 1", [], R.Timer())
    assert ledger.room() == ledger.cap_bytes and ledger.liability() == 0 and ledger.jobs == 1
    assert guard.jobs == 0 and guard.unknown == {}


# --- Astra PR55 re-review 3: a NotFound readback is not proof of non-submission --------------------------------------------

def _server_billed(bq):
    return sum(int(j["statistics"]["query"]["totalBytesBilled"]) for j in bq.jobs.values() if j.get("statistics"))


def test_deferred_insert_cannot_push_the_server_bill_past_the_ceiling(plan, scratch, monkeypatch):
    """Astra RR3 #1 repro at full scale: the first insert times out client-side and stays queued remotely; the 404 at
    the first seal used to release its hold, the next cell spent that room, and the server billed 65 GiB."""
    bq = SyntheticBigQuery(monkeypatch, bill_hold=True, defer_insert_at={1})
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1", "sqlbase_forced_c5"], run_id="sqlbase-20260919-000000-regress0")
    record = _live(campaign, bq, scratch)
    deferred_id = next(iter(bq.deferred))
    billing = record["billing"]
    # the queued insert is still liability, so the room it may bill is never spent: server + queued <= ceiling
    assert _server_billed(bq) + sb.GIB <= 64 * sb.GIB
    assert billing["bytes_billed_charged"] + billing["unresolved_liability_bytes"] == 64 * sb.GIB
    assert billing["unresolved_jobs"][0]["job_id"] == deferred_id
    assert record["cells"][0]["stopped_reason"] == "BYTES_BUDGET_UNRESOLVED"
    assert record["cells"][1]["state"] == "NOT_RUN_BUDGET" and record["cells"][1]["stopped_reason"] == "BYTES_BUDGET_UNRESOLVED"
    assert record["edition"] is None and record["unresolved_note"]


def test_absent_at_readback_stays_liability_until_a_later_seal_sees_the_job(plan, scratch, monkeypatch):
    """Astra RR3 #1, the cross-cell path: absent at the first seal, present at the next; charged then, not released."""
    bq = SyntheticBigQuery(monkeypatch, bill_hold=True, defer_insert_at={1})
    record = _live(_small(plan, ["sqlbase_forced_c1", "sqlbase_forced_c5"]), bq, scratch)
    assert bq.commits and _server_billed(bq) <= 64 * sb.GIB
    first_seal, second_seal = record["reconciliations"][0], record["reconciliations"][1]
    deferred_id = bq.commits[0]
    assert first_seal["absent_at_readback"] == [deferred_id]
    assert first_seal["jobs"][0]["ledger"].startswith("still unresolved: absent at readback")
    later = next(r for r in second_seal["jobs"] if r["job_id"] == deferred_id)
    assert later["ledger"] == "charged" and later["routing"] == "OK" and later["gate"].endswith("sqlbase_forced_c1")
    billing = record["billing"]
    assert billing["bytes_billed_charged"] + billing["unresolved_liability_bytes"] == _server_billed(bq)
    assert billing["resolved_by_readback"][0]["job_id"] == deferred_id and billing["resolved_by_readback"][0]["how"] == "readback"
    assert record["routing"]["jobs_verified_on_demand"] == len(bq.jobs) == 22   # every job, the late one included
    assert billing["unresolved_liability_bytes"] == 0 and record["edition"] == "on-demand"
    assert [c["state"] for c in record["cells"]] == ["COMPLETE", "COMPLETE"]


def test_a_job_that_never_commits_stays_liability_for_the_whole_campaign(plan, scratch, monkeypatch):
    bq = SyntheticBigQuery(monkeypatch, billed=sb.GIB, defer_insert_at={1}, never_commit=True)
    record = _live(_small(plan, ["sqlbase_forced_c1", "sqlbase_forced_c5"]), bq, scratch)
    lost = next(iter(bq.deferred))
    billing = record["billing"]
    assert billing["unresolved_liability_bytes"] == sb.GIB and billing["unresolved_jobs"][0]["job_id"] == lost
    assert billing["resolved_by_readback"] == []
    # read again at every seal: this gate's, the next cell's, and never released
    assert [r["absent_at_readback"] for r in record["reconciliations"]] == [[lost], [lost]]
    assert bq.readbacks.count(lost) >= 2
    assert record["edition"] is None and "1 job(s) have no terminal statistics" in record["edition_note"]
    assert record["unresolved_note"].startswith("jobs remain with unknown billing")
    assert record["cells"][1]["state"] == "COMPLETE"                       # the other cell ran within the reduced room


def test_an_exhausted_readback_channel_preserves_uncertainty(plan, scratch, monkeypatch):
    monkeypatch.setattr(run, "RECONCILE_SECONDS", 0)
    bq = SyntheticBigQuery(monkeypatch, billed=sb.GIB, lose_result_at={1})
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    rec = record["reconciliations"][0]
    assert rec["expired"] is True and rec["jobs"][0]["ledger"].startswith("still unresolved: the audit deadline passed")
    assert record["billing"]["unresolved_liability_bytes"] == sb.GIB and record["billing"]["resolved_by_readback"] == []
    assert record["edition"] is None and len(record["routing"]["unknown"]) == 1


def test_reconcile_never_releases_on_notfound():
    """The only release path is a gate refusal before an id exists; a readback cannot establish non-submission."""
    import inspect
    source = inspect.getsource(run.CampaignRuntime.reconcile)
    assert "absent=True" not in source


def test_a_late_enterprise_reveal_at_the_seal_marks_the_final_cell(plan, scratch, monkeypatch):
    """Astra RR3 #2: the last cell's unknown job revealing ENTERPRISE at readback used to leave COMPLETE / null."""
    bq = SyntheticBigQuery(monkeypatch, billed=sb.GIB, lose_result_at={12}, reveal_enterprise_at_readback=True)
    record = _live(_small(plan, ["sqlbase_forced_c1"]), bq, scratch)
    cell = record["cells"][0]
    assert cell["state"] == "INCOMPLETE" and cell["stopped_reason"] == "ROUTING_VIOLATION"
    assert record["state"] == "INCOMPLETE" and record["edition"] is None
    assert record["routing"]["violations"][0]["stage"] == "readback"
    assert record["reconciliations"][0]["jobs"][0]["routing"] == "VIOLATION"
