"""Offline lifecycle integration: real guards, runner, executors and shell watcher."""
import json
import inspect
import os
from pathlib import Path
import subprocess
import sys
import threading
import time
from types import SimpleNamespace

import pytest

from okf_bq_graph import lifecycle as L, run as R, benchmark as B, reservation as RES
from okf_bq_graph import safety


class Client:
    def __init__(self, events, result=None):
        self.events, self.on_result, self.ids = events, result, []

    def query(self, query, **kwargs):
        self.events.append("submit")
        self.ids.append(kwargs["job_id"])
        assert kwargs["job_id"].startswith("okf_graph_")
        assert kwargs["job_config"].labels["window"]
        assert kwargs["job_retry"] is None
        return SimpleNamespace(result=self.on_result or (lambda **kw: []))

    def load_table_from_json(self, *args, **kwargs):
        inspect.signature(L.bigquery.Client.load_table_from_json).bind(self, *args, **kwargs)
        self.events.append("load")
        self.ids.append(kwargs["job_id"])
        assert kwargs["job_config"].labels["window"]
        return SimpleNamespace(result=self.on_result or (lambda **kw: []))

    def cancel_job(self, job_id, **kwargs):
        assert job_id in self.ids
        self.events.append("cancel")

    def get_job(self, job_id, **kwargs):
        self.events.append("readback")
        return SimpleNamespace(state="DONE")


def test_deadline_blocks_query_and_load_before_submission(tmp_path):
    events = []
    window = L.WindowJobs("expired", time.monotonic() - 1, tmp_path / "jobs.json")
    client = window.bind(Client(events))
    with pytest.raises(L.WindowStopped):
        client.query("SELECT 1")
    with pytest.raises(L.WindowStopped):
        client.load_table_from_json([], "table")
    assert events == []


def test_deadline_during_readiness_cancels_before_close(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures/cases.json").write_text("{}")
    events, clock = [], [0.0]
    monkeypatch.setattr(R.time, "monotonic", lambda: clock[0])

    def result(**kwargs):
        clock[0] = 61
        raise TimeoutError()

    raw = Client(events, result)
    monkeypatch.setattr(R.bigquery, "Client", lambda **kw: raw)
    monkeypatch.setattr(R, "resolve_pointer", lambda *a: "pub")
    monkeypatch.setattr(R, "open_window", lambda label: events.append("open") or {"opened_at": "now", "state": "OPEN"})
    monkeypatch.setattr(R, "close_window", lambda label: events.append("close") or {"verified_gone": True})
    monkeypatch.setattr(R, "integration", lambda *a: events.append("integration"))
    monkeypatch.setattr(R.threading, "Thread", lambda **kw: SimpleNamespace(start=lambda: None, join=lambda: None))
    launches = []
    monkeypatch.setattr(subprocess, "Popen", lambda args, **kw: launches.append(args))
    assert R.main(["run", "integration", "--minutes", "1"]) == 1
    assert events == ["open", "submit", "cancel", "readback", "close"]
    journal = json.loads(next((tmp_path / "evidence").glob("jobs_*.json")).read_text())
    assert journal["job_ids"] == raw.ids
    assert launches[0][-1] == sys.executable
    assert launches[0][-2] == journal["label"]


def test_expired_budget_and_outstanding_window_open_nothing(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    monkeypatch.setattr(R, "open_window", lambda *a: pytest.fail("must not provision"))
    monkeypatch.setattr(R.bigquery, "Client", lambda **kw: pytest.fail("must not submit"))
    assert R.main(["run", "integration", "--minutes", "0"]) == 1
    (tmp_path / "evidence/cleanup_manifest.json").write_text(json.dumps({"windows": [
        {"label": "old", "opened_at": "2026-09-06T01:00:00Z", "state": "DELETE_UNVERIFIED"}]}))
    assert R.main(["run", "integration", "--minutes", "1"]) == 1


def test_interrupt_cancels_before_executor_wait(monkeypatch, tmp_path):
    events, submitted, released = [], threading.Event(), threading.Event()
    window = L.WindowJobs("interrupted", time.monotonic() + 60, tmp_path / "jobs.json")

    def result(**kwargs):
        submitted.set()
        if not released.wait(kwargs["timeout"]):
            raise TimeoutError()
        return []

    raw = Client(events, result)
    original_cancel = raw.cancel_job

    def cancel(*args, **kwargs):
        original_cancel(*args, **kwargs)
        released.set()

    raw.cancel_job = cancel
    client = window.bind(raw)

    def request(*args):
        try:
            client.query("SELECT 1").result()
        finally:
            events.append("worker-finished")

    def interrupt(*args, **kwargs):
        assert submitted.wait(2)
        raise KeyboardInterrupt("injected")

    monkeypatch.setattr(B, "one_request", request)
    monkeypatch.setattr(B, "wait", interrupt)
    cell = {"name": "c", "seed": 1, "warmups": 0, "measured": 1, "concurrency": 1}
    with pytest.raises(KeyboardInterrupt):
        B.run_cell(cell, [{}], lambda: {}, {"cell_seconds": 60, "window": window})
    assert events.index("cancel") < events.index("worker-finished")
    assert window.stop.is_set()
    with pytest.raises(L.WindowStopped):
        client.query("SELECT 2")


def test_load_jobs_are_journaled_and_cancelled(tmp_path):
    events = []
    window = L.WindowJobs("loads", time.monotonic() + 60, tmp_path / "jobs.json")
    raw = Client(events)
    window.bind(raw).load_table_from_json([], "table")
    assert window.stop_and_cancel()[0]["verified_done"]
    assert events == ["load", "cancel", "readback"]


def test_watcher_closes_capacity_before_job_cancellation_io(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / 'evidence').mkdir()
    events = []
    monkeypatch.setattr(safety, 'close_window', lambda *a, **kw: events.append('close') or {'verified_gone': True})
    monkeypatch.setattr(safety.bigquery, 'Client', lambda **kw: object())
    def cancel(*args):
        assert events == ['close']
        events.append('cancel')
        return []
    monkeypatch.setattr(safety, 'cancel_journal', cancel)
    assert safety.cleanup('old', attempts=1)
    assert events == ['close', 'cancel']


@pytest.mark.parametrize("recover", [False, True])
def test_actual_shell_watcher_retries_failed_inventory_with_original_label(tmp_path, recover):
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "evidence").mkdir()
    manifest = tmp_path / "evidence/cleanup_manifest.json"
    manifest.write_text(json.dumps({"windows": [{"label": "original", "opened_at": "2026-09-06T01:00:00Z", "steps": []}],
                                    "resources": [{"kind": "reservation", "window": "original", "state": "open"}]}))
    (tmp_path / "evidence/jobs_original.json").write_text(json.dumps({"label": "original", "project": L.PROJECT,
                                                                    "location": L.LOCATION, "job_ids": []}))
    # Executable adapter stubs only cloud transport; the actual shell/module/manifest chain runs.
    adapter = tmp_path / "offline-python"
    adapter.write_text(f'''#!{sys.executable}
import sys
sys.path.insert(0, {str(root)!r})
from okf_bq_graph import safety as S, reservation as R
S.bigquery.Client = lambda **kwargs: object()
count = 0
def bq(*args):
    global count
    count += 1
    fail = count <= 4 or not {recover!r}
    return {{"cmd": " ".join(args), "at": "offline", "rc": 1 if fail else 0,
             "stdout": "" if fail else "[]", "stderr": "inventory unavailable" if fail else ""}}
R._bq = bq
sys.exit(0 if S.cleanup(sys.argv[-1], attempts=3, retry_seconds=0) else 1)
''')
    adapter.chmod(0o755)
    result = subprocess.run(["/bin/bash", str(root / "bin/safety_teardown.sh"), "999999999", "original", str(adapter)],
                            env=dict(os.environ, OKF_SPIKE_DIR=str(tmp_path)), capture_output=True, text=True, timeout=10)
    assert result.returncode == (0 if recover else 1), result.stderr
    m = json.loads(manifest.read_text())
    assert len(m["windows"]) == 1
    w = m["windows"][0]
    assert w["cleanup_attempts"][0]["verified_gone"] is False
    assert len(w["cleanup_attempts"]) == (2 if recover else 3)
    assert w["verified_gone"] is recover
    assert m["resources"][0]["state"] == ("deleted" if recover else "DELETE_UNVERIFIED")
    if recover:
        assert w["closed_by"] == "safety-watcher" and w["closed_at"]
    else:
        assert "closed_at" not in w


def test_completed_job_does_not_need_cancellation(tmp_path):
    events = []
    w = L.WindowJobs("complete", time.monotonic() + 60, tmp_path / "jobs.json")
    w.bind(Client(events)).query("SELECT 1").result()
    assert w.stop_and_cancel() == []
    assert events == ["submit"]


def test_unknown_window_cannot_close_another_window(monkeypatch, tmp_path):
    monkeypatch.setattr(RES, "MANIFEST", str(tmp_path / "m.json"))
    RES._save({"windows": [{"label": "original", "steps": []}], "resources": []})
    monkeypatch.setattr(RES, "_bq", lambda *a: pytest.fail("unknown window must not delete"))
    with pytest.raises(ValueError, match="original opening label"):
        RES.close_window("safety-original")


def test_late_watcher_preserves_verified_receipt_and_newer_window(monkeypatch, tmp_path):
    monkeypatch.setattr(RES, "MANIFEST", str(tmp_path / "m.json"))
    RES._save({"windows": [
        {"label": "old", "verified_gone": True, "closed_at": "receipt", "steps": []},
        {"label": "new", "opened_at": "later", "steps": []}], "resources": []})
    monkeypatch.setattr(RES, "_bq", lambda *a: pytest.fail("late watcher must not delete newer reservation"))
    assert RES.close_window("old", closer="safety-watcher")["closed_at"] == "receipt"


def test_benchmark_deadline_row_is_renderable_without_partial_repair(monkeypatch, tmp_path):
    from okf_bq_graph.report import benchmark_table
    monkeypatch.setattr(B, "SUMMARY", str(tmp_path / "summary.json"))
    config = {"cells": [{"name": "acme_c1", "engine": "gql", "corpus": "acme", "concurrency": 1,
                         "publication_id": "p", "measured": 100}], "queries": [], "run_id": "new-run",
              "budget": {"deadline_monotonic": time.monotonic() - 1}}
    out = B.measure(config, lambda: pytest.fail("deadline must prevent requests"))
    row = out["cells"][0]
    assert row["run_id"] == "new-run" and row["measured_n"] == 0
    assert "NOT_RUN_BUDGET" in benchmark_table(out)
    assert json.loads((tmp_path / "summary.json").read_text())["cells"] == out["cells"]


def test_benchmark_request_retains_run_id(monkeypatch, tmp_path):
    monkeypatch.setattr(B, "REQUESTS", str(tmp_path / "requests.jsonl"))
    monkeypatch.setattr(B, "retrieve", lambda *a, **kw: {"status": "OK", "concepts": [], "paths": [],
                                                       "computations": [], "timing": {"total_ms": 1}})
    cell = {"name": "acme_c1", "engine": "gql", "corpus": "acme", "concurrency": 1, "publication_id": "p",
            "run_id": "explicit-run", "warmups": 0, "as_of": "2026-09-06T01:00:00Z"}
    rec = B.one_request(cell, 0, {"bundle_id": "b", "id": "q", "text": "forced:x"}, {}, 60)
    assert rec["run_id"] == json.loads((tmp_path / "requests.jsonl").read_text())["run_id"] == "explicit-run"


def test_nested_executor_interrupt_cancels_before_wait(tmp_path):
    events, submitted, released = [], threading.Event(), threading.Event()
    window = L.WindowJobs("nested", time.monotonic() + 60, tmp_path / "jobs.json")

    def result(**kwargs):
        submitted.set()
        if not released.wait(kwargs["timeout"]):
            raise TimeoutError()
        return []

    raw = Client(events, result)
    original_cancel = raw.cancel_job

    def cancel(*args, **kwargs):
        original_cancel(*args, **kwargs)
        released.set()

    raw.cancel_job = cancel
    client = window.bind(raw)
    with pytest.raises(KeyboardInterrupt):
        with L.window_executor(client, 1) as executor:
            job = client.query("SELECT 1")
            executor.submit(job.result)
            assert submitted.wait(2)
            raise KeyboardInterrupt()
    assert released.is_set() and window.stop.is_set()
    assert events == ["submit", "cancel", "readback"]


def test_signal_handler_does_not_wait_on_submission_cancellation_lock(tmp_path):
    # Run the real main/signal handler in a child with a hard timeout: the old
    # handler deadlocks if a watchdog owns cancellation while submission owns admission.
    root = Path(__file__).resolve().parents[1]
    (tmp_path / "evidence").mkdir()
    (tmp_path / "fixtures").mkdir()
    (tmp_path / "fixtures/cases.json").write_text("{}")
    script = '''
import signal, threading, subprocess
from types import SimpleNamespace
from okf_bq_graph import run as R
windows=[]
original=R.WindowJobs
def window(*args, **kwargs):
    w=original(*args, **kwargs); windows.append(w); return w
R.WindowJobs=window
class Client:
    def query(self, *args, **kwargs):
        w=windows[0]
        held=threading.Event()
        def deadline():
            with w._cancel_lock:
                held.set()
                with w._lock: pass
        t=threading.Thread(target=deadline, daemon=True); t.start()
        assert held.wait(2)
        signal.getsignal(signal.SIGTERM)(signal.SIGTERM, None)
        raise AssertionError("handler must unwind submission")
    def cancel_job(self, *a, **kw): pass
    def get_job(self, *a, **kw): return SimpleNamespace(state="DONE")
R.bigquery.Client=lambda **kw: Client()
R.resolve_pointer=lambda *a: "pub"
R.open_window=lambda label: {"opened_at":"now", "state":"OPEN"}
R.close_window=lambda label: {"verified_gone":True}
subprocess.Popen=lambda *a, **kw: None
assert R.main(["run", "integration", "--minutes", "1"]) == 1
print("signal-race-exit=0")
'''
    result = subprocess.run([sys.executable, "-c", script], cwd=tmp_path,
                            env=dict(os.environ, PYTHONPATH=str(root)), text=True, capture_output=True, timeout=8)
    assert result.returncode == 0, result.stdout + result.stderr
    assert "signal-race-exit=0" in result.stdout


@pytest.mark.parametrize("recover", [False, True])
def test_watcher_retries_raised_cleanup_errors(monkeypatch, tmp_path, recover):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    monkeypatch.setattr(RES, "MANIFEST", str(tmp_path / "m.json"))
    RES._save({"windows": [{"label": "original", "steps": [], "state": "OPEN"}], "resources": []})
    monkeypatch.setattr(safety.bigquery, "Client", lambda **kw: object())
    monkeypatch.setattr(safety, "cancel_journal", lambda *a: [])
    attempts = []

    def close(label, **kwargs):
        attempts.append(label)
        if len(attempts) == 1 or not recover:
            raise OSError("process spawn temporarily unavailable")
        return {"verified_gone": True}

    monkeypatch.setattr(safety, "close_window", close)
    assert safety.cleanup("original", retry_seconds=0) is recover
    assert attempts == ["original"] * (2 if recover else 3)
    receipts = [json.loads(line) for line in (tmp_path / "evidence/watcher_original.jsonl").read_text().splitlines()]
    assert len(receipts) == len(attempts)
    assert receipts[0]["verified_gone"] is False and "OSError" in receipts[0]["errors"][0]


def test_bq_spawn_failure_is_a_failed_step(monkeypatch):
    def unavailable(*args, **kwargs):
        raise OSError("temporarily unavailable")
    monkeypatch.setattr(RES.subprocess, "run", unavailable)
    step = RES._bq("ls", "--reservation")
    assert step["rc"] != 0 and RES._parse_list(step) is None


def test_late_watcher_receipt_never_rewrites_shared_manifest(monkeypatch, tmp_path):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    monkeypatch.setattr(RES, "MANIFEST", str(tmp_path / "evidence/m.json"))
    manifest = {"windows": [{"label": "old", "verified_gone": True, "closed_at": "receipt", "steps": []}], "resources": []}
    RES._save(manifest)
    monkeypatch.setattr(safety.bigquery, "Client", lambda **kw: object())
    monkeypatch.setattr(safety, "cancel_journal", lambda *a: [])

    def concurrent_open_and_close(label, **kwargs):
        closed = RES.close_window(label, **kwargs)
        # A new driver opens immediately after old-window cleanup returns.
        m = RES._load()
        m["windows"].append({"label": "new", "state": "OPEN", "steps": []})
        m["resources"].append({"window": "new", "kind": "reservation", "state": "open"})
        RES._save(m)
        return closed

    monkeypatch.setattr(safety, "close_window", concurrent_open_and_close)
    assert safety.cleanup("old", retry_seconds=0)
    saved = RES._load()
    assert saved["windows"][-1]["label"] == "new" and saved["resources"][-1]["state"] == "open"
    assert "watcher_attempts" not in saved["windows"][0]
    assert json.loads((tmp_path / "evidence/watcher_old.jsonl").read_text())["verified_gone"]


@pytest.mark.parametrize("initial", ["missing", "wrong-label"])
@pytest.mark.parametrize("recover", [False, True])
def test_invalid_job_journal_does_not_skip_capacity_cleanup_or_claim_success(monkeypatch, tmp_path, initial, recover):
    monkeypatch.chdir(tmp_path)
    (tmp_path / "evidence").mkdir()
    path = tmp_path / "evidence/jobs_original.json"
    journal = {"label": "original", "project": L.PROJECT, "location": L.LOCATION, "job_ids": []}
    if initial == "wrong-label":
        path.write_text(json.dumps(dict(journal, label="another-window")))
    monkeypatch.setattr(safety.bigquery, "Client", lambda **kw: object())
    calls = []

    def close(label, **kwargs):
        calls.append(label)
        if recover and len(calls) == 2:
            path.write_text(json.dumps(journal))
        return {"verified_gone": True}

    monkeypatch.setattr(safety, "close_window", close)
    assert safety.cleanup("original", retry_seconds=0) is recover
    assert calls == ["original"] * (2 if recover else 3)
    receipts = [json.loads(line) for line in (tmp_path / "evidence/watcher_original.jsonl").read_text().splitlines()]
    assert receipts[0]["verified_gone"] is True  # capacity can close despite unknown job state
    assert receipts[0]["jobs"][0]["verified_done"] is False
    assert ("FileNotFoundError" if initial == "missing" else "ValueError") in receipts[0]["jobs"][0]["error"]
    assert receipts[-1]["jobs"] == ([] if recover else receipts[0]["jobs"])


@pytest.mark.parametrize("failed", [False, True])
def test_real_load_job_poll_has_bounded_rpc_timeout(monkeypatch, tmp_path, failed):
    from google.auth.credentials import AnonymousCredentials
    from google.api_core.exceptions import BadRequest
    from google.cloud import bigquery
    client = bigquery.Client(project=L.PROJECT, credentials=AnonymousCredentials())
    destination = bigquery.TableReference.from_string(f"{L.PROJECT}.offline.table")
    job = bigquery.LoadJob("offline-load", [], destination, client)
    job._set_properties(dict(job._properties, status={"state": "RUNNING"}))
    rpc_timeouts = []

    def get_job(*args, **kwargs):
        rpc_timeouts.append(kwargs["timeout"])
        assert 0 < kwargs["timeout"] <= 1, "result polling timeout must also bound transport"
        completed = bigquery.LoadJob("offline-load", [], destination, client)
        status = {"state": "DONE"}
        if failed:
            status["errorResult"] = {"reason": "invalid", "message": "invalid load input"}
        completed._set_properties(dict(completed._properties, status=status))
        return completed

    monkeypatch.setattr(client, "get_job", get_job)
    window = L.WindowJobs("load-rpc", time.monotonic() + 60, tmp_path / "jobs.json")
    wrapped = L.WindowJob(job, window, job.job_id, False)
    if failed:
        with pytest.raises(BadRequest, match="invalid load input"):
            wrapped.result(timeout=.05)
    else:
        assert wrapped.result(timeout=.05) is job
    assert len(rpc_timeouts) == 1


# =============================================================================== Astra PR47: cleanup channel + adoption
def test_the_cleanup_channel_admits_after_workload_stop(tmp_path):
    """A restoring DDL must still be submittable and journaled once workload admission closed."""
    events = []
    window = L.WindowJobs("cleanup-channel", time.monotonic() + 60, tmp_path / "jobs.json")
    client = Client(events, lambda **kw: [])
    workload = window.bind(client)
    workload.query("SELECT 1")
    window.stop.set()
    with pytest.raises(L.WindowStopped):
        workload.query("SELECT 2")
    window.open_cleanup(30, max_jobs=2)
    restore = window.bind(client, cleanup=True)
    job = restore.query("DROP ROW ACCESS POLICY p ON t")
    assert window.cleanup_jobs == 1
    assert "cleanup" in job.job_id
    journal = json.loads((tmp_path / "jobs.json").read_text())
    assert job.job_id in journal["job_ids"]          # a cleanup submission is in the union like any other


def test_the_cleanup_channel_is_bounded(tmp_path):
    events = []
    window = L.WindowJobs("bounded-cleanup", time.monotonic() + 60, tmp_path / "jobs.json")
    client = Client(events, lambda **kw: [])
    window.stop.set()
    window.open_cleanup(30, max_jobs=1)
    restore = window.bind(client, cleanup=True)
    restore.query("DROP ONE")
    with pytest.raises(L.WindowStopped, match="budget"):
        restore.query("DROP TWO")
    window.close_cleanup()
    with pytest.raises(L.WindowStopped):
        restore.query("DROP THREE")             # the channel is closed again: back to the workload gate


def test_a_cleanup_job_waits_on_the_cleanup_deadline_not_the_workload_stop(tmp_path):
    events = []
    window = L.WindowJobs("cleanup-result", time.monotonic() + 60, tmp_path / "jobs.json")
    window.stop.set()
    window.open_cleanup(30)
    job = window.bind(Client(events, lambda **kw: []), cleanup=True).query("DROP ROW ACCESS POLICY p ON t")
    assert list(job.result()) == []             # the stopped workload channel does not abort the restore's readback


class _Terminal:
    """A client that can cancel and read back any id, including one it never submitted."""

    def cancel_job(self, job_id, **kwargs):
        return None

    def get_job(self, job_id, **kwargs):
        return SimpleNamespace(state="DONE")


def test_adopting_a_workers_job_puts_it_in_the_union_and_the_cleanup(tmp_path):
    client = _Terminal()
    window = L.WindowJobs("adopt", time.monotonic() + 60, tmp_path / "jobs.json")
    window.adopt("okf_rcpt_child_1", client=client, worker="receipt_child")
    journal = json.loads((tmp_path / "jobs.json").read_text())
    assert journal["job_ids"] == ["okf_rcpt_child_1"]
    results = window.stop_and_cancel()
    assert [r["job_id"] for r in results] == ["okf_rcpt_child_1"]
    receipt = json.loads((tmp_path / "jobs.cleanup.json").read_text())
    assert receipt["verified"] is True and receipt["job_ids"] == ["okf_rcpt_child_1"]


def test_an_adopted_job_without_a_client_stays_unresolved(tmp_path):
    window = L.WindowJobs("adopt-unowned", time.monotonic() + 60, tmp_path / "jobs.json")
    window.adopt("okf_rcpt_orphan")
    results = window.stop_and_cancel()
    assert results[0]["verified_done"] is False
    assert json.loads((tmp_path / "jobs.cleanup.json").read_text())["verified"] is False


def test_an_outstanding_restore_obligation_is_durable(tmp_path):
    L.record_restore_obligations("w", tmp_path, [{"name": "acl", "ok": True},
                                                 {"name": "row_policies", "ok": False, "error": "refused"}])
    assert L.restores_clear("w", tmp_path) is False
    body = json.loads((tmp_path / "restores_w.json").read_text())
    assert [o["name"] for o in body["outstanding"]] == ["row_policies"]
    L.record_restore_obligations("w", tmp_path, [{"name": "acl", "ok": True}, {"name": "row_policies", "ok": True}])
    assert L.restores_clear("w", tmp_path) is True


def test_a_missing_obligation_file_is_clear_but_a_malformed_one_is_not(tmp_path):
    assert L.restores_clear("never-changed-anything", tmp_path) is True
    (tmp_path / "restores_broken.json").write_text("{not json")
    assert L.restores_clear("broken", tmp_path) is False


# =============================================================================== Astra PR47 re-review (RR2)
def test_the_auth_refresh_session_is_guarded_too(tmp_path):
    """RR2 R4: AuthorizedSession's internal 401 refresh goes through its OWN plain `_auth_request` Session."""
    import requests
    from google.auth.credentials import Credentials
    from google.cloud import bigquery

    window = L.WindowJobs("refresh", time.monotonic() + 2, tmp_path / "jobs.json")
    seen = []

    class Creds(Credentials):
        def __init__(self):
            super().__init__()
            self.token = "synthetic-offline-token"

        def refresh(self, request):
            request("https://offline.invalid/token", method="POST")
            self.token = "synthetic-refreshed-token"

    class Adapter(requests.adapters.HTTPAdapter):
        def send(self, req, **kw):
            seen.append({"url": req.url, "stopped": window.stop.is_set(), "timeout": kw.get("timeout")})
            response = requests.Response()
            response.request, response.url, response._content = req, req.url, b"{}"
            if "/jobs?" in req.url:
                window.stop.set()          # a concurrent stop, while the platform answers 401
                response.status_code = 401
            else:
                response.status_code = 200
            return response

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(requests.adapters.HTTPAdapter, "send", Adapter.send)
        client = bigquery.Client(project=L.PROJECT, location=L.LOCATION, credentials=Creds())
        original, auth_session = client._http.send, client._http._auth_request.session
        original_auth = auth_session.send
        with pytest.raises(L.WindowStopped):
            window.bind(client).query("SELECT 1")
        assert [s["url"] for s in seen] == [seen[0]["url"]], f"a refresh dispatched after stop: {seen}"
        assert seen[0]["stopped"] is False
        # both of the caller's transports are left exactly as they were, so cancellation still works after stop
        assert client._http.send == original and auth_session.send == original_auth
        client.close()


def test_transport_sessions_finds_the_auth_request_session():
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import bigquery

    client = bigquery.Client(project=L.PROJECT, location=L.LOCATION, credentials=AnonymousCredentials())
    sessions = L._transport_sessions(client)
    assert client._http in sessions and client._http._auth_request.session in sessions
    assert len(sessions) == 2
    assert L._transport_sessions(SimpleNamespace()) == []


def test_a_parent_dry_run_is_a_bounded_operation_not_a_phantom_job(tmp_path):
    """RR2 P2: BigQuery returns no jobReference for a dry run; inventing one puts a phantom in the cleanup union."""
    events = []
    window = L.WindowJobs("dry", time.monotonic() + 60, tmp_path / "jobs.json")

    class Probe:
        def query(self, sql, **kwargs):
            events.append(kwargs)
            assert "job_id" not in kwargs, "a dry run must not be given an invented job id"
            return SimpleNamespace(job_id=None, result=lambda **kw: [])

        def cancel_job(self, job_id, **kwargs):
            pytest.fail("a dry run creates no server job to cancel")

    job = window.bind(Probe()).query("SELECT 1 FROM t WHERE FALSE",
                                     job_config=L.bigquery.QueryJobConfig(dry_run=True))
    assert job.job_id is None and job.dry_run is True
    assert events[0]["job_config"].dry_run is True
    journal = json.loads((tmp_path / "jobs.json").read_text())
    assert journal["job_ids"] == [] and journal["dry_run_operations"] == 1
    assert window.stop_and_cancel() == []
    receipt = json.loads((tmp_path / "jobs.cleanup.json").read_text())
    assert receipt["job_ids"] == [] and receipt["jobs"] == []   # no phantom id to cancel and 404 into "verified"


def test_a_dry_run_still_needs_admission(tmp_path):
    window = L.WindowJobs("dry-stopped", time.monotonic() + 60, tmp_path / "jobs.json")
    window.stop.set()
    with pytest.raises(L.WindowStopped):
        window.bind(_Terminal()).query("SELECT 1", job_config=L.bigquery.QueryJobConfig(dry_run=True))


def test_an_adopted_reference_is_read_back_under_its_own_project_and_location(tmp_path):
    """RR2 R1: a worker's job in another project read under the module defaults returns NotFound while it runs on."""
    from google.api_core.exceptions import NotFound
    seen = []

    class Client:
        def cancel_job(self, job_id, **kwargs):
            seen.append(kwargs)
            raise NotFound("absent under this reference")

        def get_job(self, job_id, **kwargs):
            raise NotFound("absent under this reference")

    window = L.WindowJobs("adopt-qualified", time.monotonic() + 60, tmp_path / "jobs.json")
    window.adopt("outside-job", client=Client(), project="other-project", location="EU", state="UNRESOLVED")
    results = window.stop_and_cancel()
    assert seen[0]["project"] == "other-project" and seen[0]["location"] == "EU"
    # the window never confirmed this submission, so an absent job does NOT close the obligation
    assert results[0]["verified_done"] is False and results[0]["state"] == "NOT_FOUND"
    assert json.loads((tmp_path / "jobs.cleanup.json").read_text())["verified"] is False


def test_a_confirmed_adoption_may_close_on_absence(tmp_path):
    """A reference the worker confirmed it submitted keeps the journalled-before-submit reading."""
    from google.api_core.exceptions import NotFound

    class Client:
        def cancel_job(self, job_id, **kwargs):
            raise NotFound("gone")

        def get_job(self, job_id, **kwargs):
            raise NotFound("gone")

    window = L.WindowJobs("adopt-confirmed", time.monotonic() + 60, tmp_path / "jobs.json")
    window.adopt("child-job", client=Client(), state="SUBMITTED")
    assert window.stop_and_cancel()[0]["verified_done"] is True


# =============================================================================== Astra PR47 RR3
def test_detached_recovery_carries_the_qualified_references(tmp_path):
    """RR3 N1: `cancel_journal` dropped `job_refs`, so recovery read every job under the module defaults."""
    from google.api_core.exceptions import NotFound
    seen = []

    class Client:
        def cancel_job(self, job_id, **kwargs):
            seen.append(dict(kwargs, job_id=job_id))
            if (kwargs.get("project"), kwargs.get("location")) != ("other-project", "EU"):
                raise NotFound("wrong project/location")

        def get_job(self, job_id, **kwargs):
            return SimpleNamespace(state="RUNNING")

    journal = tmp_path / "jobs_w.json"
    journal.write_text(json.dumps({
        "label": "w", "project": L.PROJECT, "location": L.LOCATION,
        "job_ids": ["outside-job"], "finished_job_ids": [],
        "job_refs": {"outside-job": {"project": "other-project", "location": "EU", "adopted": True,
                                     "notfound_is_done": False}}}))
    results = L.cancel_journal(Client(), "w", journal)
    assert seen[0]["project"] == "other-project" and seen[0]["location"] == "EU"
    assert results[0]["state"] == "RUNNING" and results[0]["verified_done"] is False
    receipt = json.loads((tmp_path / "jobs_w.cleanup.json").read_text())
    assert receipt["verified"] is False
    assert receipt["job_refs"]["outside-job"]["notfound_is_done"] is False   # the refs travel into the receipt too


def test_detached_recovery_does_not_certify_an_unconfirmed_absent_job(tmp_path):
    """A lost-response id: absent under its own reference is still unresolved, not verified completion."""
    from google.api_core.exceptions import NotFound

    class Client:
        def cancel_job(self, job_id, **kwargs):
            raise NotFound("no such job")

        def get_job(self, job_id, **kwargs):
            raise NotFound("no such job")

    journal = tmp_path / "jobs_w.json"
    journal.write_text(json.dumps({
        "label": "w", "project": L.PROJECT, "location": L.LOCATION,
        "job_ids": ["okf_rcpt_lost"], "finished_job_ids": [],
        "job_refs": {"okf_rcpt_lost": {"project": L.PROJECT, "location": L.LOCATION, "adopted": True,
                                       "notfound_is_done": False}}}))
    results = L.cancel_journal(Client(), "w", journal)
    assert results[0]["verified_done"] is False and results[0]["state"] == "NOT_FOUND"
    assert json.loads((tmp_path / "jobs_w.cleanup.json").read_text())["verified"] is False


def test_a_legacy_journal_without_refs_still_recovers(tmp_path):
    """A journal written before `job_refs` existed keeps the journalled-before-submit reading."""
    from google.api_core.exceptions import NotFound

    class Client:
        def cancel_job(self, job_id, **kwargs):
            raise NotFound("gone")

        def get_job(self, job_id, **kwargs):
            raise NotFound("gone")

    journal = tmp_path / "jobs_w.json"
    journal.write_text(json.dumps({"label": "w", "project": L.PROJECT, "location": L.LOCATION,
                                   "job_ids": ["okf_graph_w_1"], "finished_job_ids": []}))
    assert L.cancel_journal(Client(), "w", journal)[0]["verified_done"] is True


def test_the_result_client_guards_its_own_refresh_transport(tmp_path):
    """RR3 N3: a 401 DURING result reads refreshes through the shared `_auth_request`, which `__dict__.update`
    carried straight onto the copied session."""
    import requests
    from google.auth.credentials import Credentials
    from google.cloud import bigquery

    window = L.WindowJobs("result-refresh", time.monotonic() + 60, tmp_path / "jobs.json")
    seen = []

    class Creds(Credentials):
        def __init__(self):
            super().__init__()
            self.token = "offline-token"

        def refresh(self, request):
            request("https://offline.invalid/token", method="POST")
            self.token = "offline-refreshed"

    class Adapter(requests.adapters.HTTPAdapter):
        def send(self, req, **kw):
            seen.append({"method": req.method, "url": req.url, "stopped": window.stop.is_set()})
            response = requests.Response()
            response.request, response.url, response.status_code = req, req.url, 200
            response.headers["content-type"] = "application/json"
            if req.method == "POST" and "/jobs?" in req.url:
                body = json.loads(req.body)
                data = {"jobReference": body["jobReference"], "configuration": body["configuration"],
                        "status": {"state": "DONE"}}
            elif req.method == "GET" and "/queries/" in req.url:
                window.stop.set()                 # a concurrent stop, while the platform answers 401
                response.status_code = 401
                data = {"error": {"message": "offline token expired"}}
            elif req.url == "https://offline.invalid/token":
                data = {}
            else:
                raise AssertionError(f"unexpected request {req.method} {req.url}")
            response._content = json.dumps(data).encode()
            return response

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(requests.adapters.HTTPAdapter, "send", Adapter.send)
        client = bigquery.Client(project=L.PROJECT, location=L.LOCATION, credentials=Creds())
        original_request = client._http._auth_request
        original_send = original_request.session.send
        with pytest.raises((L.WindowStopped, TimeoutError)):
            list(window.bind(client).query("SELECT 1").result())
        assert not [s for s in seen if s["stopped"]], f"a send left after stop: {seen}"
        assert "https://offline.invalid/token" not in [s["url"] for s in seen]
        # the caller's own refresh transport is untouched: cancellation still works after stop
        assert client._http._auth_request is original_request
        assert original_request.session.send == original_send
        client.close()


def test_the_result_guard_installs_on_the_job_local_copy_only():
    from google.auth.credentials import AnonymousCredentials
    from google.cloud import bigquery

    client = bigquery.Client(project=L.PROJECT, location=L.LOCATION, credentials=AnonymousCredentials())
    original = client._http._auth_request
    guarded = L._ResultHTTP(client._http, lambda: 5.0)
    assert guarded.guarded_auth_transport is True
    assert guarded.raw._auth_request is not original          # the copy has its own Request
    assert client._http._auth_request is original             # the caller's is untouched
    client.close()


def test_the_audit_client_bounds_every_read_and_exposes_reads_only(tmp_path):
    """RR5 F2: explicit per-read timeout from the remaining budget, and no blanket delegation."""
    clock = [100.0]
    calls = []

    class Client:
        def get_job(self, job_id, **kwargs):
            calls.append(dict(kwargs, job_id=job_id))
            return SimpleNamespace(user_email="operator@example.test")

        def query(self, sql, **kwargs):
            raise AssertionError("an audit channel must not be able to submit")

    window = L.WindowJobs("audit", 100.0, tmp_path / "jobs.json", clock=lambda: clock[0])
    window.open_audit(30, max_reads=3)
    audit = window.audit_client(Client())
    audit.get_job("j1", project="other-project", location="EU")
    assert calls[0]["project"] == "other-project" and calls[0]["location"] == "EU"
    assert 0 < calls[0]["timeout"] <= 10 and calls[0]["retry"] is None
    assert audit.reads == 1 and audit.expired is False
    assert not hasattr(audit, "query")


def test_the_audit_client_expires_and_retains_unread_references(tmp_path):
    clock = [100.0]

    class Client:
        def get_job(self, job_id, **kwargs):
            raise AssertionError("nothing may dispatch after the audit deadline")

    window = L.WindowJobs("audit", 100.0, tmp_path / "jobs.json", clock=lambda: clock[0])
    deadline = window.open_audit(30)
    audit = window.audit_client(Client())
    clock[0] = deadline + 1
    with pytest.raises(L.AuditExpired):
        audit.get_job("j1")
    record = audit.record()
    assert record["expired"] is True and record["reads"] == 0
    assert record["unread"][0]["job_id"] == "j1"
    assert "deadline passed" in record["unread"][0]["reason"]


def test_the_audit_read_budget_is_enforced(tmp_path):
    reads = []

    class Client:
        def get_job(self, job_id, **kwargs):
            reads.append(job_id)
            return SimpleNamespace(user_email="e")

    window = L.WindowJobs("audit", time.monotonic() + 600, tmp_path / "jobs.json")
    window.open_audit(60, max_reads=2)
    audit = window.audit_client(Client())
    audit.get_job("j1")
    audit.get_job("j2")
    with pytest.raises(L.AuditExpired, match="read budget"):
        audit.get_job("j3")
    assert reads == ["j1", "j2"] and audit.unread[0]["job_id"] == "j3"
