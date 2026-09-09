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
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
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
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
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
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
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
    campaign = run.build_campaign(small, cases, run_id="sqlbase-20260919T000000Z-deadbeef")

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
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
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
    assert all(re.fullmatch(r"sqlbase-\d{8}T\d{6}Z-[0-9a-f]{8}", i) for i in ids)
    assert "legacy-unlabeled" not in ids
    assert not any(i.startswith("live_") for i in ids)


def test_run_id_gate_refuses_a_retained_summary_id(tmp_path):
    summary = tmp_path / "summary.json"
    summary.write_text(json.dumps({"cells": [{"cell": "acme_c1", "run_id": "sqlbase-20260919T000000Z-deadbeef"}]}))
    with pytest.raises(ValueError, match="already has a retained summary"):
        run.assert_run_id_is_fresh("sqlbase-20260919T000000Z-deadbeef", summary_path=summary, out_dir=tmp_path)
    run.assert_run_id_is_fresh("sqlbase-20260919T000000Z-cafef00d", summary_path=summary, out_dir=tmp_path)


def test_run_id_gate_refuses_a_retained_campaign_record(tmp_path):
    (tmp_path / "run_sqlbase-20260919T000000Z-deadbeef.json").write_text("{}")
    with pytest.raises(ValueError, match="campaign record"):
        run.assert_run_id_is_fresh("sqlbase-20260919T000000Z-deadbeef", summary_path=tmp_path / "none.json", out_dir=tmp_path)


def test_run_id_gate_refuses_unlabelled_ids(tmp_path):
    for bad in ("", "legacy-unlabeled", "acme-2026", "live_restricted-x"):
        with pytest.raises(ValueError, match="must start with"):
            run.assert_run_id_is_fresh(bad, summary_path=tmp_path / "none.json", out_dir=tmp_path)


def test_committed_gql_summary_ids_cannot_collide_with_a_campaign(plan, cases):
    """The retained GQL summary is what the driver must not overwrite; its ids are not sqlbase-* ids."""
    retained = json.loads((sb.ROOT / benchmark.SUMMARY).read_text())["cells"]
    assert retained and not any(str(c.get("run_id", "")).startswith("sqlbase-") for c in retained)
    campaign = run.build_campaign(plan, cases)
    run.assert_run_id_is_fresh(campaign["run_id"], summary_path=sb.ROOT / benchmark.SUMMARY, out_dir=sb.OUT_DIR)


def test_measure_rejects_a_reused_campaign_run_id_before_submitting(plan, cases, scratch):
    (scratch / "summary.json").write_text(json.dumps({"cells": [{"cell": "sqlbase_forced_c1", "run_id": "sqlbase-20260919T000000Z-deadbeef"}]}))
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
    with pytest.raises(ValueError, match="run_id"):
        benchmark.measure(run.measure_config(campaign), lambda: pytest.fail("reused run cannot submit"))
    with pytest.raises(ValueError, match="run_id"):
        run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("no client"), measure=lambda *a: pytest.fail("no measure"))


# --- consumer cells are refused ------------------------------------------------------------------------

@pytest.mark.parametrize("name", ["sqlchain_forced_c1", "sqlchain_forced_c5"])
def test_consumer_cells_are_refused_with_both_reasons(plan, cases, name):
    with pytest.raises(run.RefusedCell) as e:
        run.select_cells(plan, [name])
    assert "FACTS_UNSELECTED" in str(e.value) and "NOT_IMPLEMENTED" in str(e.value)
    assert run.refusal_reasons(plan, name) == ["FACTS_UNSELECTED", "NOT_IMPLEMENTED"]
    with pytest.raises(run.RefusedCell):
        run.build_campaign(plan, cases, ["sqlbase_forced_c1", name])


def test_a_selected_fact_version_still_refuses_the_consumer_cells(plan):
    selected = copy.deepcopy(plan)
    selected["facts"] = dict(selected["facts"], state="SELECTED", selected_version="x", blocks=[])
    assert run.refusal_reasons(selected, "sqlchain_forced_c1") == ["NOT_IMPLEMENTED"]
    with pytest.raises(run.RefusedCell, match="NOT_IMPLEMENTED"):
        run.select_cells(selected, ["sqlchain_forced_c1"])


def test_default_selection_is_exactly_the_retrieval_cells(plan):
    assert [c["name"] for c in run.select_cells(plan)] == run.retrieval_cell_names(plan)
    assert not set(run.retrieval_cell_names(plan)) & set(run.consumer_cell_names(plan))


def test_unknown_and_duplicate_cells_fail(plan):
    with pytest.raises(ValueError, match="not a cell"):
        run.select_cells(plan, ["acme_c1"])
    with pytest.raises(ValueError, match="listed twice"):
        run.select_cells(plan, ["sqlbase_forced_c1", "sqlbase_forced_c1"])


def test_campaign_records_the_refusals_beside_the_cells(plan, cases):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
    assert campaign["refused"] == {"sqlchain_forced_c1": ["FACTS_UNSELECTED", "NOT_IMPLEMENTED"],
                                   "sqlchain_forced_c5": ["FACTS_UNSELECTED", "NOT_IMPLEMENTED"]}
    text = run.describe(campaign)
    assert "sqlchain_forced_c1: REFUSED (FACTS_UNSELECTED + NOT_IMPLEMENTED)" in text


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
    assert out.getvalue().startswith("REFUSED:") and "FACTS_UNSELECTED + NOT_IMPLEMENTED" in out.getvalue()
    assert no_client == []


def test_dry_run_reports_a_used_run_id_without_a_client(no_client, tmp_path):
    (tmp_path / "run_sqlbase-20260919T000000Z-deadbeef.json").write_text("{}")
    out = io.StringIO()
    assert run.main(["--dry-run", "--run-id", "sqlbase-20260919T000000Z-deadbeef", "--out-dir", str(tmp_path)], stdout=out) == 2
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
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
    handed = {}

    def fake_measure(config, factory):
        handed["config"] = config
        handed["factory"] = factory
        return {"cells": [{"cell": c["name"], "run_id": config["run_id"], "state": "INCOMPLETE" if c["name"].endswith("c5") else "COMPLETE",
                           "measured_n": 3, "measured_target": c["measured"], "p50_ms_all": 1, "p95_ms_all": 2,
                           "stopped_reason": "CELL_TIME_BUDGET" if c["name"].endswith("c5") else None} for c in config["cells"]]}

    record = run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("measure was faked; no client"), measure=fake_measure)
    cfg = handed["config"]
    assert cfg["run_id"] == "sqlbase-20260919T000000Z-deadbeef"
    assert [c["name"] for c in cfg["cells"]] == run.retrieval_cell_names(plan)
    assert all(c["queries"] for c in cfg["cells"]) and cfg["queries"] == []
    assert cfg["budget"]["cell_seconds"] == 900 and cfg["budget"]["deadline_reason"] == "TOTAL_TIME_BUDGET"
    assert record["state"] == "INCOMPLETE"
    saved = json.loads((scratch / "run_sqlbase-20260919T000000Z-deadbeef.json").read_text())
    assert saved["cells"] == record["cells"] and saved["reservation_window"] is None
    assert saved["edition"] is None and saved["edition_note"].startswith("NOT established: no job was checked")
    assert saved["routing"]["verified_on_demand"] is False and saved["billing"]["bytes_billed_charged"] == 0
    assert callable(cfg["budget"]["window_for_cell"]) and callable(cfg["budget"]["stop_check"])
    assert [c["query_ids"] for c in saved["cells_declared"]][0] == plan["questions"]["forced_seed_ids"]
    assert "queries" not in saved["cells_declared"][0]
    assert no_client == []


def test_live_retains_an_aborted_record(plan, cases, scratch, no_client):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")

    def boom(config, factory):
        raise KeyboardInterrupt()

    with pytest.raises(KeyboardInterrupt):
        run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("no client"), measure=boom)
    saved = json.loads((scratch / "run_sqlbase-20260919T000000Z-deadbeef.json").read_text())
    assert saved["state"] == "ABORTED" and saved["cells"] == [] and saved["error"].startswith("KeyboardInterrupt")


def test_live_refuses_a_campaign_over_the_projected_ceiling(plan, cases, scratch):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
    campaign["budget_projection"]["within_budget"] = False
    with pytest.raises(ValueError, match="exceed the declared ceiling"):
        run.live(campaign, out_dir=scratch, make_client=lambda: pytest.fail("no client"), measure=lambda *a: pytest.fail("no measure"))
    assert not list(scratch.iterdir())


def test_live_refuses_a_window(plan, cases, scratch):
    campaign = run.build_campaign(plan, cases, run_id="sqlbase-20260919T000000Z-deadbeef")
    campaign["reservation_window"] = "US.okf-demo-enterprise"
    with pytest.raises(ValueError, match="on-demand"):
        run.assert_campaign_is_runnable(campaign)


# --- the card's command lines name this driver and parse -----------------------------------------------------

def test_card_command_lines_name_this_driver_and_parse(plan):
    card = sb.build_card(copy.deepcopy(plan))
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
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery


class SyntheticBigQuery:
    """Synthetic API responses behind the real SDK. `billed` bytes per job; `enterprise` statistics; `advance_at` jumps
    the injected clock by `advance_seconds` when the n-th job is inserted; `honor_cap` fails a job whose
    maximumBytesBilled is below `billed`, the way BigQuery refuses a job over its byte limit before running it."""

    def __init__(self, monkeypatch, *, billed=0, enterprise=False, advance_at=None, advance_seconds=0, honor_cap=False):
        self.clock = [1000.0]
        self.submissions, self.cancels, self.jobs = [], [], {}
        self.billed, self.enterprise, self.honor_cap = billed, enterprise, honor_cap
        self.advance_at, self.advance_seconds = advance_at, advance_seconds
        monkeypatch.setattr(_time, "monotonic", lambda: self.clock[0])
        monkeypatch.setattr(bigquery.Client, "_call_api", self.api)

    def make_client(self):
        return bigquery.Client(project=run.PROJECT, location=run.LOCATION, credentials=AnonymousCredentials())

    def api(self, retry, **kw):   # bound here, so the SDK's `self` is not passed through
        method, path = kw["method"], kw["path"]
        if method == "POST" and path.endswith("/jobs"):
            data = json.loads(json.dumps(kw["data"]))
            cap = data["configuration"]["query"].get("maximumBytesBilled")
            self.submissions.append({"at": self.clock[0], "configuration": data["configuration"]})
            if len(self.submissions) == self.advance_at:
                self.clock[0] += self.advance_seconds
            refused = self.honor_cap and cap is not None and int(cap) < self.billed
            billed = 0 if refused else self.billed
            stat = {"creationTime": "1000", "startTime": "1000", "endTime": "1001",
                    "query": {"totalBytesProcessed": str(billed), "totalBytesBilled": str(billed), "totalSlotMs": "1", "cacheHit": False}}
            if self.enterprise:
                stat.update(edition="ENTERPRISE", reservation_id="test-project-0728-467323:US.okf-demo-enterprise")
            status = {"state": "DONE"}
            if refused:
                err = {"reason": "bytesBilledLimitExceeded", "message": f"Query exceeded limit for bytes billed: {cap}"}
                status.update(errorResult=err, errors=[err])
            job = dict(data, status=status, statistics=stat)
            self.jobs[data["jobReference"]["jobId"]] = job
            return job
        if method == "GET" and "/queries/" in path:
            return {"jobComplete": True, "totalRows": "0", "schema": {"fields": []}, "rows": []}
        if method == "POST" and path.endswith("/cancel"):
            job_id = path.split("/jobs/")[1].split("/cancel")[0]
            self.cancels.append(job_id)
            return {"job": self.jobs[job_id]}
        if method == "GET" and "/jobs/" in path:
            return self.jobs[path.split("/jobs/")[1].split("?")[0]]
        raise AssertionError(f"unexpected API call: {method} {path}")


def _small(plan, names, warmups=1, measured=3):
    small = copy.deepcopy(plan)
    for cell in small["retrieval_cells"]:
        cell["warmups"], cell["measured"] = warmups, measured
    return run.build_campaign(small, run.load_cases(), names, run_id="sqlbase-20260919T000000Z-regress0")


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
    assert record["routing"]["jobs_checked"] == len(bq.submissions) == 12
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
    guard.check({"job_id": "a", "reservation_id": None, "edition": None})
    assert guard.verified() is True
    with pytest.raises(run.RoutingViolation, match="not on-demand"):
        guard.check({"job_id": "b", "reservation_id": None, "edition": "ENTERPRISE"})
    with pytest.raises(run.RoutingViolation):
        guard.check({"job_id": "c", "reservation_id": "p:US.r", "edition": None})
    assert guard.stop_reason() == "ROUTING_VIOLATION" and guard.verified() is False and guard.jobs == 3


def test_clock_advance_during_the_last_request_cannot_complete_the_cell(plan, scratch, monkeypatch):
    """Astra PR55 #2 repro: 20 + 100 at C=1; the clock jumps 4,000 s during the 120th request's walk job.
    Before: context and nodes were submitted after both deadlines and the cell was COMPLETE, stopped_reason null."""
    bq = SyntheticBigQuery(monkeypatch, advance_at=358, advance_seconds=4000)
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1"], run_id="sqlbase-20260919T000000Z-regress0")
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
    receipt = json.loads((scratch / "jobs_sqlbase-20260919T000000Z-regress0_sqlbase_forced_c1.cleanup.json").read_text())
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
    campaign = run.build_campaign(plan, run.load_cases(), ["sqlbase_forced_c1", "sqlbase_forced_c5"], run_id="sqlbase-20260919T000000Z-regress0")
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
    campaign = run.build_campaign(plan, cases, ["sqlbase_forced_c1"], run_id="sqlbase-20260919T000000Z-regress0")
    runtime = run.CampaignRuntime(campaign, tmp_path, deadline_monotonic=_time.monotonic() + 3600)
    factory = run.client_factory("ds", make_client=lambda: object(), runtime=runtime)
    with pytest.raises(RuntimeError, match="no submission gate"):
        factory()
    window = runtime.window_for_cell(campaign["cells"][0], _time.monotonic())
    clients = factory()
    assert clients["bq"].window is window and clients["bytes_ledger"] is runtime.ledger and clients["routing"] is runtime.routing
    assert clients["routing"].reservation == "none"
