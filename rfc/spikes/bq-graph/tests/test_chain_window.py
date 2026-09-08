"""U2: the reusable chain window controller.

Every cloud effect (opener, closer, watcher, clients, probes) is injected. Nothing here needs ADC, a reservation, or a
job. The properties under test are the ones a paid window depends on: the prior-cleanup gate cannot be walked around by
a fresh directory, one lease at a time, every client on one submission gate, capacity closure that does not queue behind
result I/O, and restores that still run when the workload raised.
"""
import json
import threading
import time

import pytest

from okf_bq_graph import chain_window as CW
from okf_bq_graph import lifecycle as L
from okf_bq_graph import reconcile_window as RW

OPEN_AT, CLOSE_AT = "2026-09-05T23:43:43Z", "2026-09-05T23:47:20Z"


# ----------------------------------------------------------------------------- fixtures
def clean_manifest(tmp_path, windows=None):
    path = tmp_path / "cleanup_manifest.json"
    path.write_text(json.dumps({"project": CW.PROJECT, "location": CW.LOCATION,
                                "windows": windows if windows is not None else [], "resources": []}))
    return path


def verified_window(tmp_path, label="old-1", minutes=3):
    """A manifest row whose capacity AND job cleanup are both verified."""
    (tmp_path / f"jobs_{label}.json").write_text(json.dumps(
        {"label": label, "project": CW.PROJECT, "location": CW.LOCATION, "job_ids": ["j1"], "finished_job_ids": ["j1"]}))
    (tmp_path / f"jobs_{label}.cleanup.json").write_text(json.dumps(
        {"label": label, "project": CW.PROJECT, "location": CW.LOCATION, "job_ids": ["j1"],
         "verified_done_job_ids": ["j1"], "jobs": [{"job_id": "j1", "verified_done": True}], "verified": True}))
    end = f"2026-09-05T23:4{3 + minutes}:43Z"
    return {"label": label, "opened_at": OPEN_AT, "closed_at": end, "verified_gone": True, "state": "CLOSED_VERIFIED"}


class FakeClient:
    """A minimal BigQuery-shaped client: records submissions, returns a job object with an id."""

    def __init__(self):
        self.submitted = []

    def query(self, sql, **kwargs):
        self.submitted.append({"sql": sql, "job_id": kwargs.get("job_id")})
        return FakeJob(kwargs.get("job_id"))

    def cancel_job(self, job_id, **kwargs):
        return None

    def get_job(self, job_id, **kwargs):
        return FakeJob(job_id, state="DONE")


class FakeJob:
    def __init__(self, job_id, state="DONE"):
        self.job_id, self.state = job_id, state

    def result(self, **kwargs):
        return []


def controller(tmp_path, *, manifest=None, minutes=10, opener=None, closer=None, probe=None, clock=None,
               spawn_watcher=None, client_factory=None, label="chain-gql-1", **cfg_kw):
    cfg = CW.WindowConfig(label=label, minutes=minutes, manifest=manifest or clean_manifest(tmp_path),
                          evidence_dir=tmp_path, lease=tmp_path / "window.lease", **cfg_kw)
    return CW.ChainWindow(cfg,
                          opener=opener or (lambda label, slots: {"label": label, "opened_at": OPEN_AT, "state": "OPEN", "steps": []}),
                          closer=closer or (lambda label: {"label": label, "verified_gone": True, "steps": []}),
                          probe=probe if probe is not None else (lambda client: "probe-job"),
                          clock=clock or time.monotonic, spawn_watcher=spawn_watcher,
                          client_factory=client_factory or (lambda: FakeClient()))


def fast(tmp_path, **kw):
    """A controller whose probes need one success and no waiting."""
    return controller(tmp_path, probe_successes=1, probe_attempts=1, probe_interval_s=0, **kw)


# ----------------------------------------------------------------------------- preflight
def test_a_missing_manifest_is_a_refusal_not_an_empty_ledger(tmp_path):
    """The historical `run.py` read FileNotFoundError as `{"windows": []}`: a fresh worktree forgot every obligation."""
    cw = controller(tmp_path, manifest=tmp_path / "nope.json")
    with pytest.raises(CW.WindowRefused) as e:
        cw.preflight()
    assert e.value.code == "MANIFEST_MISSING"
    assert cw.record["state"] == CW.REFUSED


def test_unreadable_manifest_refuses(tmp_path):
    path = tmp_path / "cleanup_manifest.json"
    path.write_text("{not json")
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=path).preflight()
    assert e.value.code == "MANIFEST_UNREADABLE"


def test_an_earlier_window_without_a_job_receipt_keeps_the_window_closed(tmp_path):
    manifest = clean_manifest(tmp_path, [{"label": "smoke-1", "opened_at": OPEN_AT, "closed_at": CLOSE_AT,
                                          "verified_gone": True}])
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest).preflight()
    assert e.value.code == "CLEANUP_UNVERIFIED" and "smoke-1" in e.value.detail


def test_a_staged_reconstruction_opens_the_gate_in_place(tmp_path):
    """`preflight` reads the evidence directory it was given, so a staged reconstruction can be gated before publication."""
    manifest = clean_manifest(tmp_path, [{"label": "smoke-1", "opened_at": OPEN_AT, "closed_at": CLOSE_AT,
                                          "verified_gone": True}])
    with pytest.raises(CW.WindowRefused):
        controller(tmp_path, manifest=manifest).preflight()
    (tmp_path / "jobs_smoke-1.json").write_text(json.dumps(
        {"label": "smoke-1", "project": CW.PROJECT, "location": CW.LOCATION, "job_ids": ["a"], "finished_job_ids": ["a"],
         "reconstructed": True}))
    (tmp_path / "jobs_smoke-1.cleanup.json").write_text(json.dumps(
        {"label": "smoke-1", "project": CW.PROJECT, "location": CW.LOCATION, "job_ids": ["a"],
         "verified_done_job_ids": ["a"], "jobs": [], "verified": True, "reconstructed": True}))
    budget = controller(tmp_path, manifest=manifest).preflight()
    assert budget["granted_minutes"] > 0


def test_capacity_deleted_but_jobs_unverified_still_refuses(tmp_path):
    manifest = clean_manifest(tmp_path, [{"label": "all-0017", "opened_at": OPEN_AT, "closed_at": CLOSE_AT,
                                          "verified_gone": True, "state": "CLOSED_RECONSTRUCTED_FROM_PLATFORM_RECORD"}])
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest).preflight()
    assert e.value.code == "CLEANUP_UNVERIFIED"


def test_an_outstanding_capacity_window_refuses(tmp_path):
    manifest = clean_manifest(tmp_path, [{"label": "stuck", "opened_at": OPEN_AT, "state": "DELETE_UNVERIFIED"}])
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest).preflight()
    assert e.value.code == "CLEANUP_UNVERIFIED"   # the job gate runs first and is also unmet


def test_label_reuse_is_refused(tmp_path):
    manifest = clean_manifest(tmp_path, [verified_window(tmp_path, "chain-gql-1")])
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest, label="chain-gql-1").preflight()
    assert e.value.code == "LABEL_REUSED"


def test_budget_is_carried_across_windows_and_can_exhaust(tmp_path):
    manifest = clean_manifest(tmp_path, [verified_window(tmp_path, "old-1", minutes=4)])
    budget = controller(tmp_path, manifest=manifest, minutes=10).preflight()
    assert budget["cumulative_minutes_used"] == pytest.approx(4.0, abs=0.1)
    assert budget["granted_minutes"] == 10
    cw = controller(tmp_path, manifest=manifest, minutes=10, budget_minutes=5)
    with pytest.raises(CW.WindowRefused) as e:
        cw.preflight()
    assert e.value.code == "BUDGET_EXHAUSTED"


# ----------------------------------------------------------------------------- lease
def test_one_lease_at_a_time(tmp_path):
    manifest = clean_manifest(tmp_path)
    first = controller(tmp_path, manifest=manifest, label="a")
    first.preflight()
    second = controller(tmp_path, manifest=manifest, label="b")
    with pytest.raises(CW.WindowRefused) as e:
        second.preflight()
    assert e.value.code == "LEASE_HELD"
    first.lease.release()
    second.preflight()          # the lease is available again


def test_a_refused_preflight_releases_the_lease(tmp_path):
    manifest = clean_manifest(tmp_path, [{"label": "smoke-1", "opened_at": OPEN_AT, "closed_at": CLOSE_AT,
                                          "verified_gone": True}])
    with pytest.raises(CW.WindowRefused):
        controller(tmp_path, manifest=manifest).preflight()
    assert CW.Lease(tmp_path / "window.lease").acquire("other") is True


def test_two_worktrees_share_one_canonical_ledger(tmp_path):
    """Two configs pointing at the same manifest cannot both open, even from different evidence directories."""
    manifest = clean_manifest(tmp_path)
    other = tmp_path / "worktree-2"
    other.mkdir()
    a = controller(tmp_path, manifest=manifest, label="a")
    a.preflight()
    cfg = CW.WindowConfig("b", 10, manifest, other, lease=tmp_path / "window.lease")
    b = CW.ChainWindow(cfg, opener=lambda *a: pytest.fail("must not provision"), closer=lambda *a: {})
    with pytest.raises(CW.WindowRefused) as e:
        b.preflight()
    assert e.value.code == "LEASE_HELD"


# ----------------------------------------------------------------------------- open
def test_the_independent_closer_is_spawned_before_any_paid_resource(tmp_path):
    order = []
    cw = fast(tmp_path, spawn_watcher=lambda label: order.append(("watcher", label)),
              opener=lambda label, slots: order.append(("open", label)) or {"opened_at": OPEN_AT, "state": "OPEN", "steps": []})
    cw.preflight()
    cw.open()
    assert [step[0] for step in order] == ["watcher", "open"]
    cw.close()


def test_a_watcher_that_cannot_start_refuses_before_provisioning(tmp_path):
    def opener(*a):
        pytest.fail("capacity must not be provisioned without an independent closer")

    cw = fast(tmp_path, spawn_watcher=lambda label: (_ for _ in ()).throw(OSError("no bash")), opener=opener)
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "WATCHER_UNAVAILABLE"


def test_a_pre_existing_reservation_is_never_adopted(tmp_path):
    closed = []
    opened = {"opened_at": OPEN_AT, "state": "OPEN_WITH_ERRORS",
              "steps": [{"cmd": "bq mk --reservation --edition=ENTERPRISE okf-graph", "rc": 1,
                         "stderr": "BigQuery error: Reservation already exists", "stdout": ""}]}
    cw = fast(tmp_path, opener=lambda *a: opened, closer=lambda label: closed.append(label) or {"verified_gone": True})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "RESERVATION_PRE_EXISTING"
    assert closed == ["chain-gql-1"]          # the controller closed what it had, rather than running on borrowed capacity


def test_deadline_during_opening_refuses_and_closes(tmp_path):
    clock = [0.0]
    closed = []

    def opener(label, slots):
        clock[0] = 10_000        # the deadline passes while capacity is being provisioned
        raise L.WindowStopped("stopped")

    cw = fast(tmp_path, minutes=1, clock=lambda: clock[0], opener=opener,
              closer=lambda label: closed.append(label) or {"verified_gone": True})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "DEADLINE_DURING_OPENING"


def test_every_failed_assignment_probe_is_retained_and_readiness_is_required(tmp_path):
    calls = [0]

    def probe(client):
        calls[0] += 1
        raise RuntimeError("assignment not propagated")

    closed = []
    cw = controller(tmp_path, probe=probe, probe_successes=2, probe_attempts=3, probe_interval_s=0,
                    closer=lambda label: closed.append(label) or {"verified_gone": True})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "ASSIGNMENT_NOT_READY"
    probes = cw.record["assignment"]["probes"]
    assert len(probes) == 3 and all(p["ok"] is False for p in probes)
    assert closed == ["chain-gql-1"]


def test_a_broken_streak_restarts_the_count(tmp_path):
    outcomes = iter([True, False, True, True])

    def probe(client):
        if not next(outcomes):
            raise RuntimeError("transient")
        return "job"

    cw = controller(tmp_path, probe=probe, probe_successes=2, probe_attempts=5, probe_interval_s=0)
    cw.preflight()
    cw.open()
    assert cw.record["assignment"]["successes"] == 2
    # the failure resets the streak: one success before it does not count towards readiness
    assert [p["ok"] for p in cw.record["assignment"]["probes"]] == [True, False, True, True]
    cw.close()


def test_open_needs_a_preflight(tmp_path):
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path).open()
    assert e.value.code == "NOT_READY"


# ----------------------------------------------------------------------------- clients on one gate
def test_every_registered_client_shares_the_submission_gate(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    raw = FakeClient()
    requester = cw.bind_client(raw, role="requester", principal="sa:okf-receipt-restricted")
    job = requester.query("SELECT 1")
    assert job.job_id.startswith("okf_graph_chain-gql-1_")
    journal = json.loads((tmp_path / "jobs_chain-gql-1.json").read_text())
    assert job.job_id in journal["job_ids"]         # journaled BEFORE the result is waited on
    assert [c["role"] for c in cw.clients] == ["operator", "requester"]
    cw.close()


def test_no_workload_send_after_stop(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    raw = FakeClient()
    requester = cw.bind_client(raw, role="requester")
    cw.stop()
    with pytest.raises(L.WindowStopped):
        requester.query("SELECT 1")
    assert not any(s["sql"] == "SELECT 1" for s in raw.submitted)
    cw.close()


def test_bind_client_before_open_is_refused(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.bind_client(FakeClient(), role="requester")
    assert e.value.code == "NO_WINDOW"


# ----------------------------------------------------------------------------- closing
def test_capacity_closure_starts_without_waiting_for_stuck_job_io(tmp_path):
    """A worker stuck in an uncancellable read must not delay capacity deletion."""
    release = threading.Event()
    started = threading.Event()
    close_started = []

    def closer(label):
        close_started.append(time.monotonic())
        return {"verified_gone": True}

    cw = fast(tmp_path, closer=closer)
    cw.preflight()
    cw.open()

    class Stuck(FakeClient):
        def cancel_job(self, job_id, **kwargs):
            started.set()
            release.wait(5)      # a hanging jobs.cancel
            return None

    cw.bind_client(Stuck(), role="requester").query("SELECT 1")
    t0 = time.monotonic()
    worker = threading.Thread(target=cw.close, daemon=True)
    worker.start()
    assert started.wait(2), "cancellation never began"
    # capacity closure has already happened while cancellation is still blocked
    assert close_started, "capacity close queued behind job cancellation"
    assert close_started[0] - t0 < 0.5
    release.set()
    worker.join(10)
    assert cw.record["window_close"]["verified_gone"] is True


def test_the_watchdog_closes_capacity_at_the_deadline(tmp_path):
    closed = threading.Event()
    cw = fast(tmp_path, minutes=1, closer=lambda label: closed.set() or {"verified_gone": True})
    cw.preflight()
    cw.open()
    cw.jobs.deadline = time.monotonic() - 1     # the watchdog is waiting on the stop event with this deadline
    cw.jobs.stop.set()
    assert closed.wait(5)
    cw.close()


def test_a_failing_closer_is_recorded_not_swallowed(tmp_path):
    cw = fast(tmp_path, closer=lambda label: (_ for _ in ()).throw(RuntimeError("bq unavailable")))
    cw.preflight()
    cw.open()
    cleanup = cw.close()
    assert cleanup["capacity_verified_gone"] is False
    assert "bq unavailable" in cw.record["window_close"]["error"]
    assert cw.record["clean"] is False


def test_close_is_idempotent_and_does_not_redelete(tmp_path):
    calls = []
    cw = fast(tmp_path, closer=lambda label: calls.append(label) or {"verified_gone": True})
    cw.preflight()
    cw.open()
    cw.close()
    cw.close()
    assert calls == ["chain-gql-1"]     # a late closer must not delete a window that is already verified gone


def test_restores_run_on_the_failure_path_and_a_raising_restore_blocks_clean(tmp_path):
    ran = []
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    cw.register_restore("dataset_acl", lambda: ran.append("acl") or {"restored": True})
    cw.register_restore("row_policies", lambda: (_ for _ in ()).throw(RuntimeError("policy restore failed")))
    cw.register_restore("credentials", lambda: ran.append("creds"))
    cw.close(reason="exception")
    assert ran == ["acl", "creds"]          # a raising restore does not stop the others
    assert cw.record["cleanup"]["restores_failed"] == ["row_policies"]
    assert cw.record["clean"] is False


def test_unresolved_jobs_prevent_a_clean_close_and_the_next_window(tmp_path):
    class Unreadable(FakeClient):
        def cancel_job(self, job_id, **kwargs):
            raise RuntimeError("cancel refused")

    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest)
    cw.preflight()
    cw.open()
    cw.bind_client(Unreadable(), role="requester").query("SELECT 1")
    cleanup = cw.close()
    assert cleanup["jobs_unresolved"] and cw.record["clean"] is False
    # the receipt the close wrote does not satisfy the structural gate, so nothing may reopen against it
    assert L.job_cleanup_verified("chain-gql-1", tmp_path / "jobs_chain-gql-1.json") is False
    assert RW.gate(tmp_path, ["chain-gql-1"])["all_verified"] is False


def test_a_clean_close_writes_a_receipt_the_gate_accepts(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    cw.bind_client(FakeClient(), role="requester").query("SELECT 1")
    cw.close()
    assert cw.record["clean"] is True
    assert L.job_cleanup_verified("chain-gql-1", tmp_path / "jobs_chain-gql-1.json") is True


def test_context_manager_closes_on_exception(tmp_path):
    cw = fast(tmp_path)
    with pytest.raises(ValueError):
        with cw:
            raise ValueError("workload failed")
    assert cw.state == CW.CLOSED and cw.record["close_reason"] == "exception"
    assert cw.record["window_close"]["verified_gone"] is True


def test_the_record_carries_the_explicit_configuration(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    cfg = cw.record["config"]
    assert cfg["manifest"].endswith("cleanup_manifest.json") and cfg["evidence_dir"] == str(tmp_path)
    assert cfg["max_slots"] == 100 and cfg["reservation"] == CW.RESERVATION
    cw.close()
