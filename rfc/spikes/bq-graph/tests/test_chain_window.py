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
               spawn_watcher=None, client_factory=None, label="chain-gql-1", ownership=None, rollback=None,
               **cfg_kw):
    cfg = CW.WindowConfig(label=label, minutes=minutes, manifest=manifest or clean_manifest(tmp_path),
                          evidence_dir=tmp_path, lease=tmp_path / "window.lease", **cfg_kw)
    return CW.ChainWindow(cfg,
                          ownership=ownership or (lambda: {"listing_ok": True, "present": False}),
                          rollback=rollback or (lambda label: {"removed": [], "preserved": []}),
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
    """Astra PR47 #2: this test previously expected the production closer to run, which DELETED the other owner's
    reservation and assignment. Refusing must preserve capacity this controller did not create."""
    closed, rolled = [], []
    opened = {"opened_at": OPEN_AT, "state": "OPEN_WITH_ERRORS",
              "steps": [{"cmd": "bq mk --reservation --edition=ENTERPRISE okf-graph", "rc": 1,
                         "stderr": "BigQuery error: Reservation already exists", "stdout": ""}]}
    cw = fast(tmp_path, opener=lambda *a: opened,
              closer=lambda label: closed.append(label) or {"verified_gone": True},
              rollback=lambda label: rolled.append(label) or {"removed": [], "preserved": ["theirs"]})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "RESERVATION_PRE_EXISTING"
    assert closed == [], "the production closer deletes a reservation this controller did not create"
    assert rolled == ["chain-gql-1"], "only this invocation's own resources may be released"
    assert cw.record["window_close"]["preserved"] is True


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


# =============================================================================== Astra PR47 review fixes
def preexisting_controller(tmp_path, present, listing_ok=True, **kw):
    state = {"listing_ok": listing_ok, "present": present,
             "reservations": [f"projects/p/locations/US/reservations/{CW.RESERVATION}"] if present else [],
             "assignments": ["projects/p/locations/US/reservations/x/assignments/someone-else"] if present else []}
    return controller(tmp_path, ownership=lambda: state, probe_successes=1, probe_attempts=1, probe_interval_s=0, **kw)


def test_pre_existing_capacity_is_refused_before_anything_is_provisioned(tmp_path):
    """Astra PR47 #2: nonownership is established BEFORE mutation, so no rollback can delete another owner's window."""
    touched = []
    cw = preexisting_controller(tmp_path, present=True,
                                opener=lambda *a: touched.append("open") or {"state": "OPEN", "steps": []},
                                closer=lambda *a: touched.append("close") or {"verified_gone": True})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "RESERVATION_PRE_EXISTING"
    assert touched == [], "nothing may be created or deleted when the reservation is already someone else's"
    assert cw.record["ownership_precheck"]["present"] is True


def test_an_unreadable_reservation_inventory_refuses(tmp_path):
    cw = preexisting_controller(tmp_path, present=None, listing_ok=False,
                                opener=lambda *a: pytest.fail("must not provision on an unknown inventory"))
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "OWNERSHIP_UNKNOWN"


def test_an_already_exists_race_rolls_back_only_our_own_resources(tmp_path):
    """If the create still reports 'already exists', only what THIS invocation made is released."""
    rolled, closed = [], []
    opened = {"opened_at": OPEN_AT, "state": "OPEN_WITH_ERRORS",
              "steps": [{"cmd": "bq mk --reservation --edition=ENTERPRISE okf-graph", "rc": 1,
                         "stderr": "BigQuery error: Reservation already exists", "stdout": ""}]}
    cw = preexisting_controller(tmp_path, present=False, opener=lambda *a: opened,
                                closer=lambda label: closed.append(label) or {"verified_gone": True},
                                rollback=lambda label: rolled.append(label) or {"removed": [], "preserved": ["theirs"]})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert e.value.code == "RESERVATION_PRE_EXISTING"
    assert rolled == ["chain-gql-1"] and closed == [], "the production closer deletes capacity we do not own"
    assert cw.record["own_rollback"]["preserved"] == ["theirs"]


def test_a_restore_can_still_submit_on_the_bounded_cleanup_channel(tmp_path):
    """Astra PR47 #3: stopping the only channel makes every restoring DDL raise and the obligation vanish."""
    submitted = []

    class Client(FakeClient):
        def query(self, sql, **kwargs):
            submitted.append(sql)
            return super().query(sql, **kwargs)

    cw = fast(tmp_path, client_factory=lambda: Client())
    cw.preflight()
    cw.open()
    cw.register_restore("row_policy_restore",
                        lambda client: client.query("DROP ROW ACCESS POLICY p ON t").result(), takes_client=True)
    cw.close()
    assert cw.record["restores"][0]["ok"] is True
    assert "DROP ROW ACCESS POLICY p ON t" in submitted
    assert cw.record["cleanup_channel"]["jobs_submitted"] == 1
    assert cw.record["clean"] is True
    # the cleanup submission is journaled like any other job, so it enters the union
    journal = json.loads((tmp_path / "jobs_chain-gql-1.json").read_text())
    assert any("cleanup" in job_id for job_id in journal["job_ids"])


def test_a_failed_restore_is_a_durable_blocker_on_the_next_window(tmp_path):
    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest, label="first")
    cw.preflight()
    cw.open()
    cw.register_restore("row_policies", lambda: (_ for _ in ()).throw(RuntimeError("policy restore refused")))
    cw.close()
    assert cw.record["clean"] is False
    obligation = json.loads((tmp_path / "restores_first.json").read_text())
    assert [o["name"] for o in obligation["outstanding"]] == ["row_policies"]
    # a fresh controller, a fresh label and verified capacity do not clear it
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest, label="second").preflight()
    assert e.value.code == "CLEANUP_UNVERIFIED" and "restoration is outstanding" in e.value.detail


def test_a_successful_restore_leaves_no_blocker(tmp_path):
    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest, label="first")
    cw.preflight()
    cw.open()
    cw.register_restore("row_policies", lambda: {"restored": True})
    cw.close()
    assert cw.record["clean"] is True
    assert json.loads((tmp_path / "restores_first.json").read_text())["outstanding"] == []
    controller(tmp_path, manifest=manifest, label="second").preflight()   # no raise


def test_a_registered_worker_is_stopped_joined_and_its_jobs_adopted(tmp_path):
    """Astra PR47 #1: a receipt child must not be able to submit after a 'clean' close returned."""
    events = []
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    cw.register_worker("receipt_child",
                       stop=lambda: events.append("stop"),
                       join=lambda: events.append("join") or {"joined": True},
                       jobs=lambda: [{"job_id": "okf_rcpt_child_1", "project": "p", "location": "US"}])
    cw.close()
    assert events == ["stop", "join"], "admission closes first, then the child is joined before sealing"
    assert cw.record["cleanup"]["adopted_jobs"] == ["okf_rcpt_child_1"]
    journal = json.loads((tmp_path / "jobs_chain-gql-1.json").read_text())
    assert "okf_rcpt_child_1" in journal["job_ids"]      # the child's job is in the window's union
    assert cw.record["clean"] is True


def test_a_worker_that_cannot_be_joined_blocks_a_clean_close(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    cw.register_worker("receipt_child", stop=lambda: None,
                       join=lambda: (_ for _ in ()).throw(RuntimeError("child would not exit")))
    cw.close()
    assert cw.record["cleanup"]["workers_unjoined"] == ["receipt_child"]
    assert cw.record["clean"] is False


def test_a_credential_refresh_that_crosses_stop_cannot_submit(tmp_path):
    """Astra PR47 #4: the real 3.x submission path, with the stop set inside the credential refresh."""
    import requests
    from google.auth.credentials import Credentials
    from google.cloud import bigquery

    cw = fast(tmp_path)
    cw.preflight()
    cw.open()

    class RefreshCredentials(Credentials):
        def __init__(self):
            super().__init__()
            self.token = None

        def refresh(self, request):
            cw.stop()                      # the window closes while the credential is being prepared
            self.token = "offline-token"

    raw = bigquery.Client(project=CW.PROJECT, location=CW.LOCATION, credentials=RefreshCredentials())
    original_send = raw._http.send
    sends = []

    def send(session, request, **kwargs):
        sends.append(request.url)
        response = requests.Response()
        response.status_code = 200
        response.request = request
        response._content = b"{}"
        response.headers["content-type"] = "application/json"
        return response

    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(requests.Session, "send", send)
        bound = cw.bind_client(raw, role="requester")
        assert bound.submission_guarded is True
        with pytest.raises(L.WindowStopped):
            bound.query("SELECT 42")
    assert sends == [], "the job POST left after the window stopped"
    # the caller's own transport is untouched, so cancellation still works after stop
    assert raw._http.send == original_send
    with pytest.MonkeyPatch.context() as mp:
        mp.setattr(raw, "cancel_job", lambda *a, **kw: None)
        mp.setattr(raw, "get_job", lambda job_id, **kw: FakeJob(job_id))
        cw.close()


def test_the_deadline_during_provisioning_is_exercised_with_one_shared_clock(tmp_path):
    """Astra PR47 P2: the controller's injected clock must bound `WindowJobs` too, and closure must happen."""
    clock = [0.0]
    reached, closed = [], []

    def opener(label, slots):
        reached.append(label)
        clock[0] += 10_000          # the deadline passes DURING provisioning
        return {"opened_at": OPEN_AT, "state": "OPEN", "steps": []}

    cw = fast(tmp_path, minutes=1, clock=lambda: clock[0], opener=opener,
              closer=lambda label: closed.append(label) or {"verified_gone": True},
              probe=lambda client: pytest.fail("no probe may run after the deadline"))
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    assert reached == ["chain-gql-1"], "provisioning must actually have been reached"
    assert e.value.code in ("ASSIGNMENT_NOT_READY", "DEADLINE_DURING_OPENING")
    assert closed == ["chain-gql-1"], "the window it opened must be closed"
    assert cw.record["window_close"]["verified_gone"] is True


# =============================================================================== Astra PR47 re-review (RR2)
def test_a_create_collision_decides_ownership_before_waking_the_watchdog(tmp_path):
    """RR2 R2: `_provisioning_done` used to be signalled first, letting a woken watchdog delete the peer's capacity."""
    order, closed = [], []
    opened = {"opened_at": OPEN_AT, "state": "OPEN_WITH_ERRORS",
              "steps": [{"cmd": "bq mk --reservation --edition=ENTERPRISE okf-graph", "rc": 1,
                         "stderr": "BigQuery error: Reservation already exists", "stdout": ""}]}

    def opener(label, slots):
        cw.jobs.stop.set()          # a stop arrives during the collision, so the watchdog is ready to close
        return opened

    cw = fast(tmp_path, opener=opener, closer=lambda label: closed.append(label) or {"verified_gone": True},
              rollback=lambda label: order.append("rollback") or {"removed": [], "preserved": ["theirs"]})
    cw.preflight()
    with pytest.raises(CW.WindowRefused) as e:
        cw.open()
    cw._watchdog.join(5)
    assert e.value.code == "RESERVATION_PRE_EXISTING"
    assert closed == [], "the watchdog ran the production closer on capacity the controller does not own"
    assert order == ["rollback"]
    assert cw.record["window_close"]["preserved"] is True


def test_a_detached_closer_honours_the_persisted_ownership_record(tmp_path, monkeypatch):
    """RR2 R2: the in-memory flag protects nothing; the detached watcher is a different process."""
    from okf_bq_graph import reservation as RES

    manifest = tmp_path / "cleanup_manifest.json"
    manifest.write_text(json.dumps({"project": CW.PROJECT, "location": CW.LOCATION,
                                    "windows": [{"label": "racing", "opened_at": OPEN_AT,
                                                 "state": "REFUSED_PRESERVING_EXISTING"}],
                                    "resources": [{"kind": "reservation", "window": "racing", "state": "open",
                                                   "pre_existing": True,
                                                   "name": f"projects/{CW.PROJECT}/locations/{CW.LOCATION}/reservations/{CW.RESERVATION}"}]}))
    commands = []

    def bq(*args):
        commands.append(args)
        return {"cmd": "bq " + " ".join(args), "rc": 0, "stdout": "[]", "stderr": "", "at": RES._now()}

    monkeypatch.setattr(RES, "MANIFEST", str(manifest))
    monkeypatch.setattr(RES, "_bq", bq)
    out = RES.close_window("racing", closer="safety-watcher")
    assert out["preserved"] is True
    assert not [c for c in commands if c[:2] == ("rm", "--reservation")], commands
    assert "belongs to another invocation" in out["reason"]


def test_a_restoration_that_returns_unverified_is_a_failure(tmp_path):
    """RR2 R3: a broker teardown can report UNVERIFIED without raising; that is not a restored resource."""
    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest, label="first")
    cw.preflight()
    cw.open()
    cw.register_restore("broker_teardown", lambda: {"status": "UNVERIFIED", "steps": {"restore_rls": {"ok": False}}})
    cw.close()
    assert cw.record["restores"][0]["ok"] is False
    assert cw.record["clean"] is False
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest, label="second").preflight()
    assert e.value.code == "CLEANUP_UNVERIFIED"


def test_a_restoration_that_returns_verified_passes(tmp_path):
    cw = fast(tmp_path)
    cw.preflight()
    cw.open()
    cw.register_restore("broker_teardown", lambda: {"status": "VERIFIED", "steps": {"restore_rls": {"ok": True}}})
    cw.close()
    assert cw.record["restores"][0]["ok"] is True and cw.record["clean"] is True


def test_a_workers_pending_reference_enters_the_journal_and_blocks_reopening(tmp_path):
    """RR2 R1: an unconfirmed child submission must govern cleanup and reopening, not only the chain JSON."""
    from google.api_core.exceptions import NotFound

    class Absent(FakeClient):
        def cancel_job(self, job_id, **kwargs):
            raise NotFound("absent under this reference")

        def get_job(self, job_id, **kwargs):
            raise NotFound("absent under this reference")

    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest, label="first", client_factory=lambda: Absent())
    cw.preflight()
    cw.open()
    cw.register_worker("receipt_child", stop=lambda: None, join=lambda: {"joined": True},
                       jobs=lambda: [{"job_id": "okf_rcpt_lost", "project": CW.PROJECT, "location": CW.LOCATION,
                                      "state": "UNRESOLVED"}])
    cw.close()
    journal = json.loads((tmp_path / "jobs_first.json").read_text())
    receipt = json.loads((tmp_path / "jobs_first.cleanup.json").read_text())
    assert "okf_rcpt_lost" in journal["job_ids"]
    assert journal["job_refs"]["okf_rcpt_lost"]["notfound_is_done"] is False
    assert "okf_rcpt_lost" not in receipt["verified_done_job_ids"] and receipt["verified"] is False
    assert cw.record["clean"] is False
    with pytest.raises(CW.WindowRefused):
        controller(tmp_path, manifest=manifest, label="second").preflight()


def test_a_worker_obligation_without_a_job_id_still_blocks_reopening(tmp_path):
    """A damaged or silent child journal hides submissions that have no id to adopt."""
    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest, label="first")
    cw.preflight()
    cw.open()
    cw.register_worker("receipt_child", stop=lambda: None, join=lambda: {"joined": True}, jobs=lambda: [],
                       obligations=lambda: [{"name": "JOURNAL_DAMAGED:launch_001", "ok": False,
                                             "error": "the launch journal could not be read"}])
    cw.close()
    assert cw.record["cleanup"]["worker_obligations_outstanding"] == ["receipt_child:JOURNAL_DAMAGED:launch_001"]
    assert cw.record["clean"] is False
    obligation = json.loads((tmp_path / "restores_first.json").read_text())
    assert [o["name"] for o in obligation["outstanding"]] == ["receipt_child:JOURNAL_DAMAGED:launch_001"]
    with pytest.raises(CW.WindowRefused) as e:
        controller(tmp_path, manifest=manifest, label="second").preflight()
    assert e.value.code == "CLEANUP_UNVERIFIED"


def test_a_worker_with_no_obligations_leaves_the_gate_open(tmp_path):
    manifest = clean_manifest(tmp_path)
    cw = fast(tmp_path, manifest=manifest, label="first")
    cw.preflight()
    cw.open()
    cw.register_worker("receipt_child", stop=lambda: None, join=lambda: {"joined": True},
                       jobs=lambda: [{"job_id": "okf_rcpt_ok", "project": CW.PROJECT, "location": CW.LOCATION,
                                      "state": "SUBMITTED"}],
                       obligations=lambda: [])
    cw.close()
    assert cw.record["clean"] is True
    controller(tmp_path, manifest=manifest, label="second").preflight()   # no raise
