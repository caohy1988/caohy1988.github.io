"""Offline summary recovery must retain attempts without combining repeated runs."""
import json
from pathlib import Path
import runpy
import time

import pytest


ROOT = Path(__file__).resolve().parents[1]


def _workspace(tmp_path, monkeypatch, records, summary=None):
    spec = json.loads((ROOT / "fixtures/scale.json").read_text())
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "evidence").mkdir()
    (tmp_path / "fixtures/scale.json").write_text(json.dumps(spec))
    (tmp_path / "evidence/requests.jsonl").write_text("".join(json.dumps(r) + "\n" for r in records))
    if summary is not None:
        (tmp_path / "evidence/summary.json").write_text(json.dumps(summary))
    monkeypatch.chdir(tmp_path)


def _aggregate():
    runpy.run_module("okf_bq_graph.partial", run_name="__main__")
    return json.loads(Path("evidence/summary.json").read_text())


def _record(run_id=None, total_ms=10):
    record = {"cell": "acme_c1", "engine": "gql", "corpus": "acme", "concurrency": 1,
              "publication_id": "p1", "request_id": "acme_c1-0020", "warmup": False,
              "status": "OK", "ok": True, "timeout": False, "total_ms": total_ms}
    if run_id is not None:
        record["run_id"] = run_id
    return record


def test_refresh_after_retained_measured_requests_arrive(tmp_path, monkeypatch):
    records = [json.loads(line) for line in (ROOT / "evidence/requests.jsonl").read_text().splitlines()]
    _workspace(tmp_path, monkeypatch, records[:20])
    before = _aggregate()["cells"][0]
    assert before["state"] == "NOT_RUN_BUDGET" and before["measured_n"] == 0
    with Path("evidence/requests.jsonl").open("a") as fh:
        for record in records[20:]:
            fh.write(json.dumps(record) + "\n")
    refreshed = _aggregate()
    after = refreshed["cells"][0]
    assert after["state"] == "INCOMPLETE"
    assert after["warmups_done"] == 20 and after["measured_n"] == 28
    assert (after["p50_ms_all"], after["p95_ms_all"], after["max_ms_all"]) == (4384.5, 5441.3, 10868.6)
    assert after["jobs_total"] == 101 and after["slot_ms_total"] == 609261
    assert _aggregate() == refreshed  # repeated recovery is stable


def test_repeated_cell_runs_are_separate_and_completed_summary_is_preserved(tmp_path, monkeypatch):
    complete = dict(_record("old"), state="COMPLETE", measured_n=100, p50_ms_all=99)
    _workspace(tmp_path, monkeypatch, [_record("old"), _record("new", 20)], {"cells": [complete]})
    rows = {r["run_id"]: r for r in _aggregate()["cells"] if r["cell"] == "acme_c1"}
    assert rows["old"] == complete
    assert rows["new"]["measured_n"] == 1 and rows["new"]["p50_ms_all"] == 20


def test_legacy_requests_are_not_combined_with_explicit_run(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch, [_record(), _record("new", 20)])
    rows = [r for r in _aggregate()["cells"] if r["cell"] == "acme_c1"]
    assert len(rows) == 2
    assert {r["run_id"] for r in rows} == {"legacy-unlabeled", "new"}
    assert [r["measured_n"] for r in rows] == [1, 1]


def test_incomplete_refresh_counts_new_failure_and_timeout(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch, [_record("run")])
    assert _aggregate()["cells"][0]["measured_n"] == 1
    failure = dict(_record("run", 100), request_id="acme_c1-0021", status="ERROR", ok=False, timeout=True)
    with Path("evidence/requests.jsonl").open("a") as fh:
        fh.write(json.dumps(failure) + "\n")
    row = _aggregate()["cells"][0]
    assert row["measured_n"] == 2 and row["success_rate"] == 0.5
    assert row["errors"] == 1 and row["timeouts"] == 1
    assert row["p95_ms_all"] == 100 and row["p95_ms_ok"] == 10


def test_missing_raw_for_unfinished_summary_does_not_discard_measurements(tmp_path, monkeypatch):
    original = {"cells": [{"cell": "acme_c1", "state": "INCOMPLETE", "measured_n": 1}]}
    _workspace(tmp_path, monkeypatch, [], original)
    with pytest.raises(ValueError, match="raw records do not cover"):
        _aggregate()
    assert json.loads(Path("evidence/summary.json").read_text()) == original


def test_ambiguous_legacy_run_boundary_fails_without_overwriting_summary(tmp_path, monkeypatch):
    original = {"cells": [{"cell": "acme_c1", "state": "NOT_RUN_BUDGET"}]}
    _workspace(tmp_path, monkeypatch, [_record(), _record(total_ms=20)], original)
    with pytest.raises(ValueError, match="run_id|duplicate"):
        _aggregate()
    assert json.loads(Path("evidence/summary.json").read_text()) == original


def test_all_nine_unrun_cells_have_known_metadata(tmp_path, monkeypatch):
    _workspace(tmp_path, monkeypatch, [])
    rows = _aggregate()["cells"]
    assert len(rows) == 9
    assert {(r["corpus"], r["concurrency"]) for r in rows} == {
        (corpus, concurrency) for corpus in ["acme", "copies_100", "copies_1000"] for concurrency in [1, 5, 10]}
    for row in rows:
        assert row["state"] == "NOT_RUN_BUDGET"
        assert row["measured_target"] == 100 and row["measured_n"] == 0
        assert row["warmups_target"] == 20 and row["warmups_done"] == 0
        assert row["p50_ms_all"] is None and row["p95_ms_all"] is None and row["max_ms_all"] is None


def test_new_measurement_run_preserves_previous_complete_receipt(tmp_path, monkeypatch):
    from okf_bq_graph import benchmark
    from okf_bq_graph.partial import aggregate
    path = tmp_path / "summary.json"
    monkeypatch.setattr(benchmark, "SUMMARY", str(path))
    complete = dict(_record("old"), state="COMPLETE", measured_n=100, p50_ms_all=99)
    path.write_text(json.dumps({"cells": [complete]}))
    spec = {"name": "acme_c1", "engine": "gql", "corpus": "acme", "concurrency": 1,
            "publication_id": "p1", "measured": 100}
    config = {"cells": [spec], "queries": [], "run_id": "new", "budget": {"deadline_monotonic": time.monotonic() - 1}}
    benchmark.measure(config, lambda: pytest.fail("expired run cannot submit"))
    saved = json.loads(path.read_text())
    recovered = aggregate([_record("old")], saved, {"acme_c1": spec})
    rows = {r["run_id"]: r for r in recovered["cells"]}
    assert rows["old"] == complete
    assert rows["new"]["state"] == "NOT_RUN_BUDGET"
    with pytest.raises(ValueError, match="run_id"):
        benchmark.measure(config, lambda: pytest.fail("reused run cannot submit"))
    assert json.loads(path.read_text()) == saved
