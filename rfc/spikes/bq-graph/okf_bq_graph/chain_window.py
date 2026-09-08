"""One reusable Enterprise window controller for the chain (Slice A, U2, KTD1/KTD2).

`run.py::main` owns the only lifecycle the spike has ever run: prior-cleanup gate, budget, detached closer, capacity
open, assignment probes, workload, stop, capacity close, job cancellation. The chain cannot reach a GQL engine by
shelling out to `run.py integration`: that would run the integration cases, not the chain, and the chain's own clients
would sit outside the window's submission gate.

This module lifts that orchestration into an object the chain can own, with the clock, the transport, the opener/closer
and the watcher injected so the whole lifecycle is testable offline:

  * **an explicit canonical ledger.** The capacity manifest and the evidence directory are arguments, never defaults
    derived from the current working directory. A missing manifest is a REFUSAL, not an empty one - the historical
    `run.py` behaviour (`FileNotFoundError -> {"windows": []}`) means a fresh worktree silently forgets every earlier
    obligation, which is exactly the gate this window must not walk around.
  * **an exclusive lease.** One `flock`ed lease file per manifest, held for the whole window, so two worktrees or two
    invocations cannot open concurrent paid capacity against the same ledger.
  * **one submission gate for every client.** Operator and requester clients are registered here and handed out already
    bound; a broker receives bound clients instead of constructing untracked ones.
  * **capacity closure that does not wait for result I/O.** Stopping closes admission first; the capacity closer runs on
    its own lock, so a worker stuck in an uncancellable HTTP read or a hanging `jobs.cancel` cannot delay it.
  * **restores that run even on the failure path.** Registered restore callables (broker ACL/policy snapshots) run
    during close, each guarded, and a raising restore is recorded rather than swallowed.

What it deliberately does NOT do: decide that a window may open. `preflight` re-runs the same
`reservation.require_clean_windows` gate against the named evidence directory, and a window whose earlier obligations
are unverified stays closed. Nothing here promotes a reconstruction, waives a receipt or spends anything by itself.
"""
from __future__ import annotations

import datetime as _dt
import fcntl
import json
import threading
import time
import traceback
from pathlib import Path
from typing import Any, Callable, Optional

from . import LOCATION, PROJECT, RESERVATION
from .lifecycle import WindowJobs, WindowStopped, record_restore_obligations
from .reservation import release_own_resources, require_clean_windows, reservation_state

REFUSED, READY, OPEN, STOPPED, CLOSED = "REFUSED", "READY", "OPEN", "STOPPED", "CLOSED"
BUDGET_MINUTES = 120        # the conservative cumulative ceiling the driver has always carried
RESERVE_MINUTES = 2         # kept back for closure and audit; never spent on workload
CLEANUP_SECONDS = 90        # the separate bounded channel restores and cleanup DDL submit on, after workload stop
CLEANUP_MAX_JOBS = 20
#: A restoration that RETURNS one of these did not restore anything, even though it raised nothing. Treating a returned
#: UNVERIFIED as success is how a broker's failed ACL/policy restore reached a `clean` close (Astra PR47 re-review R3).
RESTORE_FAILED_STATUS = ("UNVERIFIED", "FAILED", "ERROR", "BLOCKED", "INCOMPLETE", "NOT_RUN")


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class WindowRefused(RuntimeError):
    """The window did not open. Carries the machine-readable reason so a caller can record it verbatim."""

    def __init__(self, code: str, detail: str, record: Optional[dict] = None):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail, self.record = code, detail, record or {}


class Lease:
    """Exclusive `flock` on one lease file. Non-blocking: a held lease is a refusal, never a queue."""

    def __init__(self, path: str | Path):
        self.path = Path(path)
        self._fh = None

    def acquire(self, holder: str) -> bool:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        fh = self.path.open("a+")
        try:
            fcntl.flock(fh, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            fh.close()
            return False
        fh.seek(0)
        fh.truncate()
        fh.write(json.dumps({"holder": holder, "at": _now()}) + "\n")
        fh.flush()
        self._fh = fh
        return True

    def release(self) -> None:
        if self._fh is not None:
            try:
                fcntl.flock(self._fh, fcntl.LOCK_UN)
            finally:
                self._fh.close()
                self._fh = None


class WindowConfig:
    """Everything about a window that must be named explicitly rather than defaulted from the cwd."""

    def __init__(self, label: str, minutes: int, manifest: str | Path, evidence_dir: str | Path,
                 lease: Optional[str | Path] = None, max_slots: int = 100, project: str = PROJECT,
                 location: str = LOCATION, reservation: str = RESERVATION, budget_minutes: int = BUDGET_MINUTES,
                 probe_successes: int = 6, probe_attempts: int = 12, probe_interval_s: float = 10.0,
                 probe_seconds: float = 120.0):
        if not label or "/" in label:
            raise ValueError("a window label must be a non-empty name without a path separator")
        self.label, self.minutes = label, int(minutes)
        self.manifest = Path(manifest)
        self.evidence_dir = Path(evidence_dir)
        self.lease = Path(lease) if lease else self.manifest.with_suffix(".lease")
        self.max_slots, self.project, self.location, self.reservation = max_slots, project, location, reservation
        self.budget_minutes = budget_minutes
        self.probe_successes, self.probe_attempts = probe_successes, probe_attempts
        self.probe_interval_s, self.probe_seconds = probe_interval_s, probe_seconds

    def journal_path(self) -> Path:
        return self.evidence_dir / f"jobs_{self.label}.json"

    def describe(self) -> dict:
        return {"label": self.label, "minutes": self.minutes, "manifest": str(self.manifest),
                "evidence_dir": str(self.evidence_dir), "lease": str(self.lease), "max_slots": self.max_slots,
                "project": self.project, "location": self.location, "reservation": self.reservation,
                "budget_minutes": self.budget_minutes,
                "probes": {"successes": self.probe_successes, "attempts": self.probe_attempts,
                           "interval_s": self.probe_interval_s, "seconds": self.probe_seconds}}


class ChainWindow:
    """Owns one window end to end. Every external effect is an injected callable."""

    def __init__(self, cfg: WindowConfig, *, opener: Callable[..., dict], closer: Callable[..., dict],
                 clock: Callable[[], float] = time.monotonic, spawn_watcher: Optional[Callable[[str], Any]] = None,
                 probe: Optional[Callable[[Any], Any]] = None, client_factory: Optional[Callable[[], Any]] = None,
                 holder: str = "chain", ownership: Optional[Callable[[], dict]] = None,
                 rollback: Optional[Callable[[str], dict]] = None,
                 cleanup_seconds: float = CLEANUP_SECONDS, cleanup_max_jobs: int = CLEANUP_MAX_JOBS):
        self.cfg, self.holder = cfg, holder
        self._opener, self._closer, self._clock = opener, closer, clock
        self._spawn_watcher, self._probe, self._client_factory = spawn_watcher, probe, client_factory
        self._ownership = ownership if ownership is not None else reservation_state
        self._rollback = rollback if rollback is not None else release_own_resources
        self._cleanup_seconds, self._cleanup_max_jobs = cleanup_seconds, cleanup_max_jobs
        self.operator: Any = None
        self._operator_raw: Any = None
        self._workers: list[dict] = []
        self._preserve_capacity = False   # set when the reservation turns out not to be ours: never delete it
        self.lease = Lease(cfg.lease)
        self.state = REFUSED
        self.jobs: Optional[WindowJobs] = None
        self.deadline: Optional[float] = None
        self.clients: list[dict] = []
        self._restores: list[dict] = []
        self._close_lock = threading.Lock()
        self._provisioning_done = threading.Event()
        self._watchdog: Optional[threading.Thread] = None
        self.record: dict[str, Any] = {"controller": "okf_bq_graph.chain_window/0.1.0", "config": cfg.describe(),
                                       "state": REFUSED, "events": []}

    # ---------------------------------------------------------------- helpers
    def _event(self, event: str, **fields: Any) -> dict:
        entry = {"event": event, "at": _now(), **fields}
        self.record["events"].append(entry)
        return entry

    def _refuse(self, code: str, detail: str) -> WindowRefused:
        self.record.update(state=REFUSED, refusal={"code": code, "detail": detail, "at": _now()})
        self._event("refused", code=code)
        self.lease.release()
        return WindowRefused(code, detail, self.record)

    # ---------------------------------------------------------------- preflight
    def preflight(self) -> dict:
        """Lease, prior-cleanup gate and cumulative budget. Nothing paid happens here and nothing is created."""
        if not self.lease.acquire(f"{self.holder}:{self.cfg.label}"):
            raise self._refuse("LEASE_HELD", f"another invocation holds {self.cfg.lease}; concurrent paid windows are refused")
        if not self.cfg.manifest.exists():
            raise self._refuse("MANIFEST_MISSING",
                               f"{self.cfg.manifest} does not exist. An absent manifest is not an empty one: a fresh "
                               "output directory must never bypass an earlier window's obligations")
        try:
            manifest = json.loads(self.cfg.manifest.read_text(encoding="utf-8"))
            windows = manifest["windows"]
            if not isinstance(windows, list):
                raise TypeError("windows is not a list")
        except (OSError, ValueError, KeyError, TypeError) as e:
            raise self._refuse("MANIFEST_UNREADABLE", f"{type(e).__name__}: {str(e)[:200]}")
        if any(w.get("label") == self.cfg.label for w in windows):
            raise self._refuse("LABEL_REUSED",
                               f"{self.cfg.label} already appears in the manifest; a new window needs an original label "
                               "so a late closer can never delete it")
        try:
            require_clean_windows(manifest, evidence_dir=self.cfg.evidence_dir, exclude=self.cfg.label)
        except RuntimeError as e:
            raise self._refuse("CLEANUP_UNVERIFIED", str(e)[:300])
        used = 0.0
        for w in windows:
            if not w.get("opened_at"):
                continue
            if not w.get("verified_gone") or not w.get("closed_at"):
                raise self._refuse("WINDOW_OUTSTANDING", f'{w.get("label")} has no verified capacity closure')
            used += (_dt.datetime.fromisoformat(w["closed_at"].replace("Z", "+00:00"))
                     - _dt.datetime.fromisoformat(w["opened_at"].replace("Z", "+00:00"))).total_seconds() / 60
        allowed = int(min(self.cfg.minutes, max(0, self.cfg.budget_minutes - used - RESERVE_MINUTES)))
        self.record["budget"] = {"cumulative_minutes_used": round(used, 2), "ceiling_minutes": self.cfg.budget_minutes,
                                 "requested_minutes": self.cfg.minutes, "granted_minutes": allowed,
                                 "reserve_minutes": RESERVE_MINUTES,
                                 "note": "manifest intervals are the driver's own open/close clocks, not a platform "
                                         "billing figure; the remaining allowance is carried conservatively"}
        if allowed <= 0:
            raise self._refuse("BUDGET_EXHAUSTED",
                               f"cumulative window minutes {used:.1f} leave no room under the {self.cfg.budget_minutes}-minute ceiling")
        self.state = READY
        self.record["state"] = READY
        self._event("preflight_ok", granted_minutes=allowed)
        return self.record["budget"]

    # ---------------------------------------------------------------- open
    def open(self) -> dict:
        """Spawn the independent closer, open capacity, then prove the assignment with real probes."""
        if self.state != READY:
            raise self._refuse("NOT_READY", f"open() needs a successful preflight; state is {self.state}")
        minutes = self.record["budget"]["granted_minutes"]
        self.deadline = self._clock() + minutes * 60
        self.cfg.evidence_dir.mkdir(parents=True, exist_ok=True)
        # the gate shares the controller's clock, so an injected clock bounds provisioning too
        self.jobs = WindowJobs(self.cfg.label, self.deadline, self.cfg.journal_path(), clock=self._clock)
        # the independent closer exists BEFORE any paid resource, so an interruption during provisioning still has one
        if self._spawn_watcher is not None:
            try:
                self.record["safety_watcher"] = {"spawned": True, "detail": str(self._spawn_watcher(self.cfg.label))[:200]}
            except Exception as e:  # noqa: BLE001 - a watcher that cannot start is a refusal, not a warning
                self.jobs.stop.set()
                raise self._refuse("WATCHER_UNAVAILABLE", f"{type(e).__name__}: {str(e)[:200]}")
        # NONOWNERSHIP FIRST: never provision on top of capacity someone else owns, because the rollback that
        # follows a refusal would then delete their reservation and assignment (Astra PR47 #2).
        ownership = self._ownership() if self._ownership is not None else {"listing_ok": True, "present": False}
        self.record["ownership_precheck"] = {k: v for k, v in ownership.items() if k != "steps"}
        if not ownership.get("listing_ok"):
            self._provisioning_done.set()
            raise self._refuse("OWNERSHIP_UNKNOWN",
                               "the reservation inventory could not be read, so nonownership is not established; "
                               "provisioning on an unknown inventory risks deleting another invocation's capacity")
        if ownership.get("present"):
            self._provisioning_done.set()
            raise self._refuse("RESERVATION_PRE_EXISTING",
                               f"the reservation {self.cfg.reservation} already exists and this controller did not "
                               "create it; nothing was provisioned and nothing was deleted")
        self._watchdog = threading.Thread(target=self._watch, name=f"chain-window-{self.cfg.label}", daemon=True)
        self._watchdog.start()
        try:
            self.jobs.check()
            opened = self._opener(self.cfg.label, self.cfg.max_slots)
        except WindowStopped:
            self._provisioning_done.set()
            raise self._refuse("DEADLINE_DURING_OPENING", "the window deadline passed while capacity was being provisioned")
        except Exception as e:  # noqa: BLE001
            self._provisioning_done.set()
            self.close(reason="open_failed")
            raise WindowRefused("OPEN_FAILED", f"{type(e).__name__}: {str(e)[:200]}", self.record)
        # The ownership decision is made BEFORE the watchdog is released. If a stop arrives during a create collision,
        # a waiting watchdog would otherwise run the production closer and delete the peer's capacity while this
        # thread is still deciding that the capacity is not ours (Astra PR47 re-review R2).
        adopted = self._adopted_existing(opened)
        if adopted:
            self._preserve_capacity = True
        self._provisioning_done.set()
        self.record["window_open"] = {k: v for k, v in opened.items() if k != "steps"}
        if adopted:
            # a race: the pre-check saw nothing, but the create found it. Roll back ONLY what this invocation made -
            # never the production closer, which deletes the reservation and every assignment pointing at it.
            # `_preserve_capacity` was set before the watchdog was released; the manifest also records the
            # `pre_existing` reservation, so a DETACHED closer or a retry honours it too.
            self.record["own_rollback"] = self._rollback(self.cfg.label) if self._rollback is not None else None
            self.stop()
            self._provisioning_done.set()
            self.lease.release()
            self.state = REFUSED
            self.record["state"] = REFUSED
            self._event("refused", code="RESERVATION_PRE_EXISTING", preserved=True)
            raise WindowRefused("RESERVATION_PRE_EXISTING",
                                f"the reservation {self.cfg.reservation} already existed: this controller will not "
                                "adopt capacity it did not create, and did not delete it", self.record)
        self.state = OPEN
        self.record["state"] = OPEN
        self._event("capacity_open", state=opened.get("state"))
        if self._client_factory is not None:
            self._operator_raw = self._client_factory()
            self.operator = self.bind_client(self._operator_raw, role="operator")
        probes = self._prove_assignment()
        self.record["assignment"] = probes
        if not probes["ready"]:
            self.close(reason="assignment_not_ready")
            raise WindowRefused("ASSIGNMENT_NOT_READY", probes["reason"], self.record)
        return self.record["window_open"]

    def _adopted_existing(self, opened: dict) -> bool:
        for step in opened.get("steps", []):
            cmd = step.get("cmd", "")
            if "mk --reservation" in cmd and step.get("rc") != 0 and \
                    "already exists" in (str(step.get("stderr", "")) + str(step.get("stdout", ""))).lower():
                return True
        return False

    def _prove_assignment(self) -> dict:
        if self._probe is None:
            return {"ready": False, "reason": "no assignment probe was configured", "probes": []}
        client = self.operator
        probes: list[dict] = []
        streak, attempts = 0, 0
        started = self._clock()
        while streak < self.cfg.probe_successes and attempts < self.cfg.probe_attempts:
            if self._clock() - started > self.cfg.probe_seconds:
                return {"ready": False, "reason": f"assignment probes exceeded {self.cfg.probe_seconds}s", "probes": probes,
                        "attempts": attempts}
            attempts += 1
            try:
                self.jobs.check()
                job_id = self._probe(client)
                streak += 1
                probes.append({"at": _now(), "job_id": job_id, "ok": True})
            except WindowStopped:
                return {"ready": False, "reason": "the window stopped during assignment probing", "probes": probes,
                        "attempts": attempts}
            except Exception as e:  # noqa: BLE001 - every failed probe stays in the inventory
                streak = 0
                probes.append({"at": _now(), "ok": False, "error": f"{type(e).__name__}: {str(e)[:150]}"})
            if streak < self.cfg.probe_successes and attempts < self.cfg.probe_attempts:
                try:
                    self.jobs.wait(self.cfg.probe_interval_s)
                except WindowStopped:
                    return {"ready": False, "reason": "the window stopped while waiting between probes", "probes": probes,
                            "attempts": attempts}
        ready = streak >= self.cfg.probe_successes
        return {"ready": ready, "probes": probes, "attempts": attempts, "successes": streak,
                "required_successes": self.cfg.probe_successes,
                "propagation_s": round(self._clock() - started, 1),
                "reason": None if ready else f"assignment never reached {self.cfg.probe_successes} consecutive successes",
                "note": "every probe, including the failures, belongs to the window's job inventory"}

    # ---------------------------------------------------------------- clients and restores
    def bind_client(self, client: Any, role: str, principal: Optional[str] = None) -> Any:
        """Register a client with the window's single submission gate and hand it back bound.

        Brokers must receive their clients from here. A client constructed behind the controller's back submits jobs
        the window neither bounds nor cleans up."""
        if self.jobs is None:
            raise WindowRefused("NO_WINDOW", "bind_client() needs an opened window", self.record)
        bound = self.jobs.bind(client)
        self.clients.append({"role": role, "principal": principal, "bound_at": _now(), "type": type(client).__name__,
                             "submission_guarded": bound.submission_guarded})
        return bound

    def cleanup_client(self, client: Any, role: str = "operator-cleanup") -> Any:
        """A client on the SEPARATE bounded cleanup channel: its submissions are still journaled and still enter the
        cleanup union, but they are admitted after workload stop."""
        if self.jobs is None:
            raise WindowRefused("NO_WINDOW", "cleanup_client() needs an opened window", self.record)
        bound = self.jobs.bind(client, cleanup=True)
        self.clients.append({"role": role, "bound_at": _now(), "type": type(client).__name__, "cleanup_channel": True,
                             "submission_guarded": bound.submission_guarded})
        return bound

    def register_worker(self, name: str, stop: Optional[Callable[[], Any]] = None,
                        join: Optional[Callable[[], Any]] = None,
                        jobs: Optional[Callable[[], list]] = None,
                        obligations: Optional[Callable[[], list]] = None) -> None:
        """A child process or thread that can submit inside this window.

        `stop` runs when admission closes, `join` before the cleanup union is sealed, and `jobs` contributes the
        references the worker retained. A worker that is not registered can submit after a "clean" close returns
        (Astra PR47 #1)."""
        self._workers.append({"name": name, "stop": stop, "join": join, "jobs": jobs, "obligations": obligations})

    def register_restore(self, name: str, restore: Callable[..., Any], takes_client: bool = False) -> None:
        """A resource restoration (broker ACLs, row policies) that must run at close even on the failure path.

        With `takes_client=True` the callable receives the bounded CLEANUP client, so restoration DDL can still be
        submitted and journaled after workload admission closed."""
        self._restores.append({"name": name, "call": restore, "takes_client": takes_client})

    # ---------------------------------------------------------------- stop and close
    def _watch(self) -> None:
        if self.jobs is None:
            return
        if not self.jobs.stop.wait(max(0, self.deadline - self._clock())):
            self.record["deadline_reached"] = True
            self._event("deadline_reached")
        self.jobs.stop.set()
        self._provisioning_done.wait()
        self._close_capacity()      # begins even while a worker is stuck in an uncancellable read

    def stop(self) -> None:
        """Close admission everywhere, including registered workers. Any send after this raises before the network."""
        if self.jobs is not None:
            self.jobs.stop.set()
        for worker in self._workers:
            if worker.get("stop") is None or worker.get("stopped"):
                continue
            try:
                worker["stop"]()
                worker["stopped"] = True
            except Exception as e:  # noqa: BLE001
                worker["stop_error"] = f"{type(e).__name__}: {str(e)[:200]}"
        self.state = STOPPED
        self.record["state"] = STOPPED
        self._event("stopped", workers=[w["name"] for w in self._workers])

    def _close_capacity(self) -> dict:
        with self._close_lock:
            if self._preserve_capacity:
                preserved = {"verified_gone": False, "preserved": True,
                             "reason": "the reservation belongs to another invocation: this controller deletes only "
                                       "what it created"}
                self.record["window_close"] = preserved
                return preserved
            existing = self.record.get("window_close")
            if existing and existing.get("verified_gone"):
                return existing
            try:
                closed = {k: v for k, v in self._closer(self.cfg.label).items() if k != "steps"}
            except Exception:  # noqa: BLE001
                closed = {"verified_gone": False, "error": traceback.format_exc()[-1500:]}
            self.record["window_close"] = closed
            self._event("capacity_close", verified_gone=bool(closed.get("verified_gone")))
            return closed

    def close(self, reason: str = "complete") -> dict:
        """Stop admission everywhere, restore resources on the bounded CLEANUP channel, close capacity WITHOUT waiting
        for job I/O, join every worker, then seal the job union.

        Order matters. Admission (including each registered worker's) closes first. Restores then run on a separate
        bounded channel, because stopping the only channel makes a policy-restoring DDL raise and the obligation
        disappear. Capacity closure starts on its own lock. The union is sealed only after every worker is joined, so a
        paused receipt child cannot submit after a "clean" close returned (Astra PR47 #1, #3)."""
        self.stop()
        self.record["close_reason"] = reason
        # a bounded second channel so restoration work can still be submitted and journaled after workload stop
        cleanup_deadline = None
        if self.jobs is not None and self._restores:
            cleanup_deadline = self.jobs.open_cleanup(self._cleanup_seconds, self._cleanup_max_jobs)
            if self._operator_raw is not None:
                self.operator = self.cleanup_client(self._operator_raw)
        # the obligations are written BEFORE they are attempted: a crash mid-restore still leaves the blocker behind
        pending = [{"name": e["name"], "ok": False, "state": "PENDING"} for e in self._restores]
        if self._restores:
            record_restore_obligations(self.cfg.label, self.cfg.evidence_dir, pending)
        restores = []
        for entry in self._restores:
            try:
                result = entry["call"](self.operator) if entry["takes_client"] else entry["call"]()
            except Exception as e:  # noqa: BLE001 - a failed restore is a durable obligation, never a silent pass
                restores.append({"name": entry["name"], "ok": False, "state": "FAILED",
                                 "error": f"{type(e).__name__}: {str(e)[:250]}"})
                continue
            # a restoration that RETURNED a failure did not restore anything either
            status = result.get("status") if isinstance(result, dict) else None
            failed = status in RESTORE_FAILED_STATUS or (isinstance(result, dict) and result.get("verified") is False)
            restores.append({"name": entry["name"], "ok": not failed, "result": result,
                             **({"state": "FAILED", "error": f"restoration returned {status}"} if failed else {})})
        self.record["restores"] = restores
        self.record["cleanup_channel"] = {"deadline": cleanup_deadline, "max_jobs": self._cleanup_max_jobs,
                                          "jobs_submitted": getattr(self.jobs, "cleanup_jobs", 0)}
        if self.jobs is not None:
            self.jobs.close_cleanup()
        self._provisioning_done.set()
        closed = self._close_capacity()
        # every worker is joined BEFORE the union is sealed, and its retained references are adopted
        workers = []
        for worker in self._workers:
            entry = {"name": worker["name"], "stopped": bool(worker.get("stopped")),
                     "stop_error": worker.get("stop_error")}
            if worker.get("join") is not None:
                try:
                    entry["join"] = worker["join"]()
                except Exception as e:  # noqa: BLE001
                    entry["join_error"] = f"{type(e).__name__}: {str(e)[:200]}"
            if worker.get("jobs") is not None:
                try:
                    refs = list(worker["jobs"]() or [])
                except Exception as e:  # noqa: BLE001
                    refs, entry["jobs_error"] = [], f"{type(e).__name__}: {str(e)[:200]}"
                entry["jobs"] = [r.get("job_id") if isinstance(r, dict) else r for r in refs]
                for ref in refs:
                    if not isinstance(ref, dict):
                        ref = {"job_id": ref}
                    job_id = ref.get("job_id")
                    if job_id:
                        # the FULL reference, and whether the worker ever confirmed the submission: an unconfirmed id
                        # read back as absent is unresolved, not done (Astra PR47 re-review R1)
                        self.jobs.adopt(job_id, client=self._operator_raw, project=ref.get("project"),
                                        location=ref.get("location"), state=ref.get("state"), worker=worker["name"])
            if worker.get("obligations") is not None:
                try:
                    entry["obligations"] = [dict(o) for o in (worker["obligations"]() or [])]
                except Exception as e:  # noqa: BLE001
                    entry["obligations"] = [{"name": f"{worker['name']}:obligations_unreadable", "ok": False,
                                             "error": f"{type(e).__name__}: {str(e)[:200]}"}]
            workers.append(entry)
        self.record["workers"] = workers
        # Every outstanding obligation - a failed restore, and any evidence a worker could not resolve into a job id -
        # is persisted together, so the reopening gate sees the complete union rather than only the chain JSON
        # (Astra PR47 re-review R1).
        worker_obligations = [dict(o, name=f"{w['name']}:{o.get('name', 'obligation')}")
                              for w in workers for o in (w.get("obligations") or [])]
        obligations = restores + worker_obligations
        if obligations:
            self.record["restore_obligations"] = str(
                record_restore_obligations(self.cfg.label, self.cfg.evidence_dir, obligations))
        self.record["worker_obligations"] = worker_obligations
        worker_failures = [w["name"] for w in workers if w.get("stop_error") or w.get("join_error") or w.get("jobs_error")]
        worker_failures += sorted({o["name"] for o in worker_obligations if not o.get("ok")})
        cancellation = self.jobs.stop_and_cancel() if self.jobs is not None else []
        self.record["job_cancellation"] = cancellation
        if self._watchdog is not None and self._watchdog.is_alive():
            self._watchdog.join(timeout=30)
        unresolved = [j for j in cancellation if not j.get("verified_done")]
        failed_restores = [r["name"] for r in restores if not r["ok"]]
        self.record["cleanup"] = {
            "capacity_verified_gone": bool(closed.get("verified_gone")),
            "jobs_total": len(cancellation), "jobs_unresolved": [j.get("job_id") for j in unresolved],
            "adopted_jobs": sorted(getattr(self.jobs, "adopted", {})),
            "journal": str(self.cfg.journal_path()),
            "receipt": str(self.cfg.journal_path().with_suffix(".cleanup.json")),
            "restores_failed": failed_restores,
            "worker_obligations_outstanding": [o["name"] for o in worker_obligations if not o.get("ok")],
            "restore_obligations": self.record.get("restore_obligations"),
            "workers_unjoined": worker_failures,
            "note": "capacity deletion is not job cleanup, and neither covers a resource this window changed and could "
                    "not restore: a failed restore is a durable obligation that blocks another window"}
        self.record["clean"] = (bool(closed.get("verified_gone")) and not unresolved and not failed_restores
                                and not worker_failures)
        self.state = CLOSED
        self.record["state"] = CLOSED
        self._event("closed", clean=self.record["clean"])
        self.lease.release()
        return self.record["cleanup"]

    # ---------------------------------------------------------------- context manager
    def __enter__(self) -> "ChainWindow":
        self.preflight()
        self.open()
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:
        self.close(reason="exception" if exc_type else "complete")
        return False
