"""Driver for the predeclared ordinary-SQL baseline cells (2026-09-19 checkpoint, Slice B).

Slice A (`sql_baseline.py`) predeclared four retrieval cells on the `fallback` engine and left every one
of them INCOMPLETE because no driver reached `benchmark.measure` with the right shape. This module is
that driver. It reads the committed plan (`fixtures/sql_baseline.json`, the file
`evidence/sql-baseline/plan.json` is rendered from), builds one `benchmark.measure` cell per retrieval
cell, and hands each cell **only its own shape's queries**: the forced cells see the three forced seeds,
the natural cells see the six natural questions, never both. Sampling, per-attempt retention in
`evidence/requests.jsonl` and nearest-rank aggregation stay in `benchmark.measure`; nothing here
re-implements them.

What the driver refuses to do, by construction rather than by comment:

* Run a consumer cell (`sqlchain_*`). Those need a request-to-consumer runner that does not exist
  (`NOT_IMPLEMENTED`) and, while `facts.state` is UNSELECTED, a fact-data version nobody has chosen
  (`FACTS_UNSELECTED`). Asking for one raises `RefusedCell` naming both reasons.
* Reuse a `run_id`. Every campaign gets a fresh `sqlbase-<utc>-<hex>` id and `assert_run_id_is_fresh`
  checks the retained summary before any client exists; `benchmark.measure` checks again.
* Open a reservation window, or *assume* on-demand. Omitting a window does not make a job on-demand: an
  unset job routing inherits whatever assignment applies to the project, and a standing Enterprise
  assignment exists in this project. Every job therefore carries BigQuery's job-level override
  `reservation = "none"` (Astra PR55 #1), and `RoutingGuard` reads every job's recorded statistics: a
  reservation_id or an edition on any job fails that request closed and stops the campaign. The record
  says `edition = "on-demand"` only when at least one job ran and none violated; the standing reservation
  `US.okf-demo-enterprise` is never listed, touched or deleted.
* Let a deadline stop only the *next* admission. Each cell gets its own `lifecycle.WindowJobs` gate
  (Astra PR55 #2) whose deadline is the earlier of the cell budget and the campaign deadline, and every
  job the cell submits goes through it: submission, result polling and row pagination all stop at the
  deadline and the in-flight jobs are cancelled. A cell stopped that way is INCOMPLETE with the reason
  named; it is never COMPLETE with `stopped_reason = null`.
* Spend past the declared bytes / USD ceiling (Astra PR55 #3). `BytesLedger` is one shared running
  account over the whole campaign — warmups, failures and concurrent jobs included. Every job takes a
  hold before submission that becomes its `maximum_bytes_billed`, so BigQuery itself refuses a job that
  would bill past the room left; the hold is settled against the bytes the job actually billed; and when
  no room is left the next job is not submitted and the cell stops `BYTES_BUDGET` / `USD_BUDGET`. The prior
  projection is a pre-flight sanity check only; it enforces nothing.
* Open a client in `--dry-run`. The BigQuery client is constructed lazily inside the per-thread factory
  that only `--live` builds, so a dry run prints the campaign and touches nothing.

`--live` (Pass 2) runs the campaign foreground, writes `evidence/sql-baseline/run_<run_id>.json` with the
cell summaries beside the plan, and leaves the card regeneration to a separate, reviewed step: a stopped
cell stays INCOMPLETE with its attempts retained, and no percentile is invented for it.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable

from google.cloud import bigquery

from . import PROJECT, LOCATION
from . import benchmark
from . import sql_baseline as sb
from google.api_core import exceptions as gexc

from .lifecycle import WindowJobs, AuditExpired
from .retrieve import RoutingViolation

ROOT = sb.ROOT
CASES = ROOT / "fixtures" / "cases.json"
OUT_DIR = sb.OUT_DIR
ENGINE = "fallback"
EMBEDDING_MODEL = "text-embedding-005"   # the natural shape embeds the question; the forced shape does not
SEED = 20260919                           # deterministic query order per cell; the checkpoint date, not a measurement
FORCED_PREFIX = "forced:"
RUN_ID_PREFIX = "sqlbase"
TOTAL_DEADLINE_REASON = "TOTAL_TIME_BUDGET"
ON_DEMAND_RESERVATION = "none"            # BigQuery job-level routing override: run on-demand regardless of assignments
PER_JOB_CAP_BYTES = 1 * sb.GIB            # sanity cap on one job; the largest recorded baseline job billed ~110 MiB
MIN_BILLED_BYTES = 10 * 1024 ** 2         # BigQuery bills at least 10 MiB per on-demand query; less room is no room
RECONCILE_SECONDS = 60                    # bounded read-only channel per sealed gate for resolving job liabilities
RECONCILE_MAX_READS = 64


class RefusedCell(ValueError):
    """A cell this driver must not pretend to fill."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


# --- plan → cells ----------------------------------------------------------------------------------

def load_cases(path: Path | str = CASES) -> dict:
    return json.loads(Path(path).read_text())


def retrieval_cell_names(plan: dict) -> list[str]:
    return [c["name"] for c in plan["retrieval_cells"]]


def consumer_cell_names(plan: dict) -> list[str]:
    return [c["name"] for c in plan["consumer_cells"]]


def refusal_reasons(plan: dict, name: str) -> list[str]:
    """Why a consumer cell cannot be run here. Always NOT_IMPLEMENTED; FACTS_UNSELECTED while it applies."""
    reasons = ["NOT_IMPLEMENTED"]
    facts = plan["facts"]
    if facts["state"] == "UNSELECTED" and name in facts.get("blocks", []):
        reasons.insert(0, "FACTS_UNSELECTED")
    return reasons


def select_cells(plan: dict, names: list[str] | None = None) -> list[dict]:
    """The retrieval cells to run, in plan order. A consumer cell name is refused, not skipped."""
    retrieval = {c["name"]: c for c in plan["retrieval_cells"]}
    consumer = set(consumer_cell_names(plan))
    if not names:
        return list(retrieval.values())
    chosen = []
    for name in names:
        if name in consumer:
            reasons = refusal_reasons(plan, name)
            raise RefusedCell(
                f"{name}: this driver measures retrieval_ms only and refuses to pretend to fill a "
                f"request_to_consumer_ms cell ({' + '.join(reasons)}). "
                + ("No fact-data version is selected, so two runs of it would not be comparable. " if "FACTS_UNSELECTED" in reasons else "")
                + "No sampled request-to-consumer runner exists; okf_bq_graph.chain runs each case once.")
        if name not in retrieval:
            raise ValueError(f"{name}: not a cell in the sql-baseline plan (retrieval cells: {sorted(retrieval)})")
        if name in {c["name"] for c in chosen}:
            raise ValueError(f"{name}: listed twice")
        chosen.append(retrieval[name])
    return chosen


def queries_for_shape(plan: dict, cases: dict, shape: str) -> list[dict]:
    """Only the pinned questions of one shape, each bound to the plan's corpus.

    The plan pins question ids; the texts come from `fixtures/cases.json` at the plan's `as_of`. A forced
    seed must carry the `forced:` prefix and a natural question must not: a text that violates its shape
    is a fixture defect, and it fails here rather than being measured under the wrong label.
    """
    q = plan["questions"]
    if cases.get("as_of") != q["as_of"]:
        raise ValueError(f"cases.json as_of {cases.get('as_of')!r} != plan questions.as_of {q['as_of']!r}")
    if shape == "forced":
        wanted, pool = q["forced_seed_ids"], cases["forced_seeds"]
    elif shape == "natural":
        wanted, pool = q["natural_query_ids"], cases["natural_queries"]
    else:
        raise ValueError(f"unknown shape {shape!r}")
    by_id = {x["id"]: x for x in pool}
    missing = [i for i in wanted if i not in by_id]
    if missing:
        raise ValueError(f"{shape}: plan pins question ids absent from cases.json: {missing}")
    out = []
    for qid in wanted:
        text = by_id[qid]["text"]
        forced = text.startswith(FORCED_PREFIX)
        if forced != (shape == "forced"):
            raise ValueError(f"{qid}: text {text!r} is not a {shape} question")
        out.append({"id": qid, "text": text, "shape": shape,
                    "bundle_id": plan["corpus"]["bundle_id"], "publication_id": plan["corpus"]["publication_id"]})
    if not out:
        raise ValueError(f"{shape}: the plan pins no questions of this shape")
    return out


def cell_config(plan: dict, cell: dict, cases: dict) -> dict:
    """One `benchmark.measure` cell: engine, corpus, sample sizes and timeout from the plan, queries of one shape."""
    if plan["engine"] != ENGINE:
        raise ValueError(f"plan engine is {plan['engine']!r}; this driver is the {ENGINE!r} comparator only")
    if cell["name"] not in retrieval_cell_names(plan):
        raise RefusedCell(f"{cell['name']}: not a retrieval cell")
    corpus = plan["corpus"]
    return {
        "name": cell["name"],
        "engine": ENGINE,
        "corpus": corpus["bundle_id"],
        "ds": corpus["dataset"],
        "publication_id": corpus["publication_id"],
        "bundles": None,
        "shape": cell["shape"],
        "concurrency": cell["concurrency"],
        "warmups": cell["warmups"],
        "measured": cell["measured"],
        "timeout_s": cell["timeout_s"],
        "as_of": plan["questions"]["as_of"],
        "seed": SEED,
        "top_k": 5,
        "model": EMBEDDING_MODEL if cell["shape"] == "natural" else None,
        "queries": queries_for_shape(plan, cases, cell["shape"]),
    }


# --- run_id -----------------------------------------------------------------------------------------

def fresh_run_id(now: _dt.datetime | None = None, token: str | None = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return f"{RUN_ID_PREFIX}-{now.strftime('%Y%m%dT%H%M%SZ')}-{token or secrets.token_hex(4)}"


def assert_run_id_is_fresh(run_id: str, summary_path: Path | str | None = None, out_dir: Path | str | None = None) -> None:
    """Refuse a run_id that any retained summary already carries. Runs before a client exists.

    `benchmark.measure` raises on the same collision; this gate exists so a `--dry-run` reports it and a
    `--live` run never reaches the client constructor with a doomed id.
    """
    if not run_id or not run_id.startswith(RUN_ID_PREFIX + "-"):
        raise ValueError(f"run_id {run_id!r} must start with {RUN_ID_PREFIX + '-'!r}: baseline campaigns are labelled")
    summary = Path(summary_path or benchmark.SUMMARY)
    if summary.exists():
        retained = json.loads(summary.read_text()).get("cells", [])
        clashes = sorted({c["cell"] for c in retained if c.get("run_id") == run_id})
        if clashes:
            raise ValueError(f"run_id {run_id!r} already has a retained summary for {clashes}; a new campaign needs a new run_id")
    record = Path(out_dir or OUT_DIR) / f"run_{run_id}.json"
    if record.exists():
        raise ValueError(f"run_id {run_id!r} already has a campaign record at {record}")


# --- execution ceilings -------------------------------------------------------------------------------

class BytesLedger:
    """One shared running account of billed bytes for a whole campaign, thread-safe.

    `hold()` reserves room for one job before it is submitted and returns the job's `maximum_bytes_billed`;
    `settle()` releases the hold and charges what the job actually billed, once the server reported a terminal
    job with statistics. A job whose billing is NOT established - a submission whose response was lost after the
    gate journaled its id, a job whose final statistics could not be read - keeps its hold as *liability* against
    that job id (`unresolved()`); the liability counts against the ceiling exactly like an outstanding hold until a
    bounded readback resolves it (`resolve()`: terminal statistics charge the actual bytes, an established
    non-submission releases the room). A hold that cannot be tied to any job id is liability nobody can resolve, and
    it stays counted for the rest of the campaign (Astra PR55 RR #1: a lost response is not zero bytes).

    Holds and liabilities count while they are out, so concurrent jobs cannot collectively exceed the ceiling, and
    the per-job cap keeps one runaway query from taking the whole campaign's room. The ceiling is the tighter of
    the declared byte ceiling and the declared USD ceiling at the plan's list rate.
    """

    def __init__(self, max_bytes: int, usd_per_tib: float, max_usd: float, per_job_cap: int = PER_JOB_CAP_BYTES):
        self.max_bytes = int(max_bytes)
        self.max_usd = float(max_usd)
        self.usd_per_tib = float(usd_per_tib)
        self.usd_cap_bytes = int(max_usd / usd_per_tib * sb.TIB)
        self.cap_bytes = min(self.max_bytes, self.usd_cap_bytes)
        self.binding = "BYTES_BUDGET" if self.max_bytes <= self.usd_cap_bytes else "USD_BUDGET"
        self.per_job_cap = int(per_job_cap)
        self.charged = 0
        self.held = 0                       # active holds + unresolved liabilities
        self.jobs = 0
        self.refused = 0
        self.max_hold_seen = 0
        self.pending: dict[str, dict] = {}  # job id (or an unresolvable key) -> liability
        self.resolved: list[dict] = []
        self._unknown = 0
        self._lock = threading.Lock()

    def usd_list(self) -> float:
        return self.charged / sb.TIB * self.usd_per_tib

    def liability(self) -> int:
        return sum(p["hold"] for p in self.pending.values())

    def room(self) -> int:
        return self.cap_bytes - self.charged - self.held

    def exhausted(self) -> bool:
        return self.room() < MIN_BILLED_BYTES

    def stop_reason(self) -> str | None:
        if not self.exhausted():
            return None
        # room that only unresolved liabilities consume is not spent yet; say so rather than call it billed
        return self.binding if self.room() + self.liability() < MIN_BILLED_BYTES else self.binding + "_UNRESOLVED"

    def hold(self) -> int | None:
        with self._lock:
            room = self.room()
            if room < MIN_BILLED_BYTES:
                self.refused += 1
                return None
            hold = min(room, self.per_job_cap)
            self.held += hold
            self.max_hold_seen = max(self.max_hold_seen, hold)
            return hold

    def settle(self, hold: int, bytes_billed: int, job_id: str | None = None) -> None:
        with self._lock:
            self.held -= hold
            self.charged += int(bytes_billed or 0)
            self.jobs += 1

    def unresolved(self, hold: int, job_id: str | None, reason: str) -> None:
        """Keep the hold as liability. The room stays consumed until `resolve()` establishes what the job billed."""
        with self._lock:
            key = job_id
            if key is None:
                self._unknown += 1
                key = f"unresolvable-{self._unknown}"
            self.pending[key] = {"job_id": job_id, "hold": hold, "reason": reason, "resolvable": job_id is not None}

    def resolve(self, job_id: str, bytes_billed: int | None = None, absent: bool = False, how: str = "readback") -> bool:
        """Terminal statistics charge the actual bytes; an established non-submission releases the room."""
        with self._lock:
            entry = self.pending.pop(job_id, None)
            if entry is None:
                return False
            self.held -= entry["hold"]
            if absent:
                outcome = "released: never submitted"
            else:
                self.charged += int(bytes_billed or 0)
                self.jobs += 1
                outcome = f"charged {int(bytes_billed or 0)} bytes"
            self.resolved.append(dict(entry, outcome=outcome, how=how))
            return True

    def snapshot(self) -> dict:
        with self._lock:
            liability = sum(p["hold"] for p in self.pending.values())
            return {"ceiling_bytes": self.cap_bytes, "ceiling_binding": self.binding,
                    "max_bytes_billed_declared": self.max_bytes, "max_usd_declared": self.max_usd,
                    "usd_per_tib": self.usd_per_tib, "per_job_cap_bytes": self.per_job_cap,
                    "jobs_settled": self.jobs, "jobs_refused_no_room": self.refused,
                    "bytes_billed_charged": self.charged, "usd_list_charged": round(self.usd_list(), 4),
                    "holds_outstanding_bytes": self.held - liability,
                    "unresolved_liability_bytes": liability, "unresolved_jobs": list(self.pending.values()),
                    "usd_list_liability": round(liability / sb.TIB * self.usd_per_tib, 4),
                    "resolved_by_readback": list(self.resolved),
                    "largest_hold_bytes": self.max_hold_seen,
                    "exhausted": self.exhausted(), "stop_reason": self.stop_reason(),
                    "note": ("warmups, failures and concurrent jobs all charge this account; a job whose billing was "
                             "never established keeps its full hold as liability; the projection did not")}


class RoutingGuard:
    """Require on-demand routing on every job and verify it from each job's own terminal statistics.

    Every submitted job is observed: a success, a failure, and a job whose outcome the caller never confirmed. A job
    counts as verified on-demand only when the server reported it DONE with statistics carrying neither a
    reservation_id nor an edition. A reservation_id or edition on ANY job - failed ones included - is a violation
    that stops admission and withholds the campaign's edition. A job without terminal statistics is unknown: it does
    not certify anything until a readback resolves it, and while any job is unknown the campaign is not labelled
    on-demand (Astra PR55 RR #2).
    """

    reservation = ON_DEMAND_RESERVATION

    def __init__(self) -> None:
        self.jobs = 0
        self.ok = 0
        self.violations: list[dict] = []
        self.unknown: dict[str, dict] = {}
        self._anonymous = 0
        self._lock = threading.Lock()

    @staticmethod
    def classify(entry: dict) -> str:
        if entry.get("reservation_id") or entry.get("edition"):
            return "VIOLATION"
        if entry.get("server_state") == "DONE" and entry.get("stats_present"):
            return "OK"
        return "UNKNOWN"

    def observe(self, entry: dict) -> str:
        verdict = self.classify(entry)
        with self._lock:
            self.jobs += 1
            if verdict == "OK":
                self.ok += 1
            elif verdict == "VIOLATION":
                self.violations.append({"job_id": entry.get("job_id"), "stage": entry.get("stage"),
                                        "reservation_id": entry.get("reservation_id"), "edition": entry.get("edition"),
                                        "job_state": entry.get("state"), "server_state": entry.get("server_state")})
            else:
                key = entry.get("job_id")
                if key is None:
                    self._anonymous += 1
                    key = f"unresolvable-{self._anonymous}"
                self.unknown[key] = {"job_id": entry.get("job_id"), "stage": entry.get("stage"),
                                     "job_state": entry.get("state"), "server_state": entry.get("server_state"),
                                     "stats_present": bool(entry.get("stats_present"))}
        return verdict

    def check(self, entry: dict) -> None:
        if self.observe(entry) == "VIOLATION":
            raise RoutingViolation(
                f"job {entry.get('job_id')} ran with reservation_id={entry.get('reservation_id')!r} "
                f"edition={entry.get('edition')!r} although reservation={self.reservation!r} was requested; "
                "this campaign is not on-demand and stops here")

    def resolve(self, job_id: str, entry: dict | None, absent: bool = False) -> bool:
        """A readback settles an unknown job: DONE statistics classify it, an established non-submission drops it."""
        with self._lock:
            if job_id not in self.unknown:
                return False
            if absent:
                self.unknown.pop(job_id)
                self.jobs -= 1                  # it was never a job
                return True
        if entry is None:
            return False
        verdict = self.classify(entry)
        if verdict == "UNKNOWN":
            return False
        with self._lock:
            self.unknown.pop(job_id, None)
            self.jobs -= 1
        self.observe(entry)
        return True

    def stop_reason(self) -> str | None:
        return "ROUTING_VIOLATION" if self.violations else None

    def verified(self) -> bool:
        return self.ok > 0 and not self.violations and not self.unknown

    def snapshot(self) -> dict:
        with self._lock:
            return {"job_reservation_requested": self.reservation, "jobs_observed": self.jobs,
                    "jobs_verified_on_demand": self.ok, "violations": list(self.violations),
                    "unknown": list(self.unknown.values()), "verified_on_demand": self.verified(),
                    "note": ("verified means every observed job - successes and failures - was reported DONE with "
                             "statistics carrying no reservation_id and no edition, and no job's outcome is unknown; "
                             "the standing reservation is neither read nor touched")}


class CampaignRuntime:
    """The live-only objects: per-cell submission gates, the shared ledger and the routing guard."""

    def __init__(self, campaign: dict, out_dir: Path, deadline_monotonic: float):
        b = campaign["budget"]
        self.campaign = campaign
        self.out_dir = Path(out_dir)
        self.deadline_monotonic = deadline_monotonic
        self.cell_seconds = b["cell_seconds"]
        self.ledger = BytesLedger(b["max_bytes_billed_gib"] * sb.GIB, b["ondemand_usd_per_tib"], b["max_usd_ondemand_list"],
                                  per_job_cap=b["per_job_cap_bytes"])
        self.routing = RoutingGuard()
        self.window: WindowJobs | None = None
        self.gates: list[dict] = []
        self.reconciliations: list[dict] = []
        self.raw_client: Any = None          # one raw client, kept for bounded readbacks after a gate is sealed
        self._lock = threading.Lock()

    def window_for_cell(self, cell: dict, started: float) -> WindowJobs:
        deadline = min(started + self.cell_seconds, self.deadline_monotonic)
        label = f"{self.campaign['run_id']}_{cell['name']}"
        window = WindowJobs(label, deadline, self.out_dir / f"jobs_{label}.json")
        with self._lock:
            self.window = window
            self.gates.append({"cell": cell["name"], "label": label, "journal": str(window.journal),
                               "deadline_seconds_from_cell_start": round(deadline - started, 1)})
        return window

    def stop_check(self) -> str | None:
        return self.routing.stop_reason() or self.ledger.stop_reason()

    def current_window(self) -> WindowJobs | None:
        with self._lock:
            return self.window

    def note_client(self, raw: Any) -> None:
        with self._lock:
            if self.raw_client is None:
                self.raw_client = raw

    def unresolved_for(self, window: WindowJobs) -> list[str]:
        ids = set(window.refs)
        return sorted((set(self.ledger.pending) | set(self.routing.unknown)) & ids)

    def reconcile(self, cell: dict, window: WindowJobs) -> dict:
        """After a gate is sealed, read back every job of that gate whose billing or routing is still unresolved,
        over the gate's bounded read-only channel. A DONE job with statistics settles both; a job the gate journaled
        but the server never saw (NotFound under its own reference) is released. Anything the channel could not read
        stays liability and unknown, and the room it holds is not spent again (Astra PR55 RR #1 / #2)."""
        outcome = {"cell": cell["name"], "gate": window.label, "jobs": [], "expired": False, "unread": []}
        ids = self.unresolved_for(window)
        if not ids:
            self.reconciliations.append(outcome)
            return outcome
        if self.raw_client is None:
            outcome["error"] = "no client to read back with"
            self.reconciliations.append(outcome)
            return outcome
        window.open_audit(RECONCILE_SECONDS, max_reads=RECONCILE_MAX_READS)
        audit = window.audit_client(self.raw_client)
        for job_id in ids:
            ref = window.refs.get(job_id) or {}
            row = {"job_id": job_id, "ledger": None, "routing": None}
            try:
                job = audit.get_job(job_id, project=ref.get("project"), location=ref.get("location"))
                st = getattr(job, "_properties", {}).get("statistics", {}) or {}
                entry = {"job_id": job_id, "stage": "readback", "state": "READBACK", "server_state": job.state,
                         "stats_present": bool(st), "bytes_billed": job.total_bytes_billed,
                         "reservation_id": st.get("reservation_id"), "edition": st.get("edition")}
                row["server_state"] = job.state
                if job.state == "DONE" and st and job.total_bytes_billed is not None:
                    row["ledger"] = "charged" if self.ledger.resolve(job_id, job.total_bytes_billed) else "not pending"
                else:
                    row["ledger"] = "still unresolved: no terminal billing"
                row["routing"] = self.routing.classify(entry)
                self.routing.resolve(job_id, entry)
            except gexc.NotFound:
                if ref.get("notfound_is_done", False) and not ref.get("adopted"):
                    row["ledger"] = "released" if self.ledger.resolve(job_id, absent=True, how="readback NotFound") else "not pending"
                    self.routing.resolve(job_id, None, absent=True)
                    row["routing"] = "released: never submitted"
                else:
                    row["ledger"] = row["routing"] = "still unresolved: absent under an unconfirmed reference"
            except AuditExpired as e:
                row["ledger"] = row["routing"] = f"still unresolved: {e}"
                outcome["expired"] = True
                outcome["jobs"].append(row)
                break
            except Exception as e:  # noqa: BLE001 - an unreadable job stays unresolved, and says why
                row["ledger"] = row["routing"] = f"still unresolved: {type(e).__name__}: {e}"[:200]
            outcome["jobs"].append(row)
        outcome["unread"] = [i for i in ids if i not in {r["job_id"] for r in outcome["jobs"]}]
        outcome["audit"] = audit.record()
        self.reconciliations.append(outcome)
        return outcome


# --- campaign ---------------------------------------------------------------------------------------

def build_campaign(plan: dict, cases: dict, names: list[str] | None = None, run_id: str | None = None) -> dict:
    """Everything `--live` will hand to `benchmark.measure`, computed without a client."""
    sb.validate_plan(plan)
    cells = [cell_config(plan, c, cases) for c in select_cells(plan, names)]
    budget = plan["budget"]
    projection = sb.project_budget(plan, sb.prior_observations(ROOT))
    return {
        "run_id": run_id or fresh_run_id(),
        "plan_version": plan["version"],
        "engine": ENGINE,
        "edition_requested": "on-demand",
        "routing": {"job_reservation": ON_DEMAND_RESERVATION,
                    "verification": "every job's statistics must report no reservation_id and no edition; "
                                    "one violation stops the campaign and the record is not labelled on-demand"},
        "reservation_window": None,
        "project": PROJECT,
        "location": LOCATION,
        "dataset": plan["corpus"]["dataset"],
        "cells": cells,
        "budget": {
            "cell_seconds": budget["max_wall_seconds_per_cell"],
            "total_seconds": budget["max_wall_seconds_total"],
            "max_bytes_billed_gib": budget["max_bytes_billed_gib"],
            "max_usd_ondemand_list": budget["max_usd_ondemand_list"],
            "ondemand_usd_per_tib": budget["ondemand_usd_per_tib"],
            "per_job_cap_bytes": PER_JOB_CAP_BYTES,
            "enforcement": "shared running ledger over every job (warmups, failures, concurrency); per-job "
                           "maximum_bytes_billed = min(room left, per_job_cap); exhausted → next job not submitted",
            "deadline_reason": TOTAL_DEADLINE_REASON,
            "stop_rule": budget["stop_rule"],
        },
        "budget_projection": {k: projection[k] for k in ("bytes_billed_projected_total", "usd_ondemand_list_projected", "within_budget",
                                                          "shapes_without_observed_bytes")},
        "cache": {"bigquery_result_cache": False, "retrieval_cache": False},
        "refused": {name: refusal_reasons(plan, name) for name in consumer_cell_names(plan)},
    }


def assert_campaign_is_runnable(campaign: dict) -> None:
    """Gates that must hold before a paid request is sent; all evaluable offline."""
    if not campaign["cells"]:
        raise ValueError("no retrieval cells selected")
    if campaign.get("reservation_window") is not None or "window" in campaign["budget"]:
        raise ValueError("baseline cells run on-demand: no reservation window may be attached")
    if campaign["routing"]["job_reservation"] != ON_DEMAND_RESERVATION:
        raise ValueError("baseline jobs must carry the on-demand routing override")
    if not campaign["budget_projection"]["within_budget"]:
        raise ValueError(f"projected bytes/usd exceed the declared ceiling: {campaign['budget_projection']}")
    if campaign["budget"]["per_job_cap_bytes"] > campaign["budget"]["max_bytes_billed_gib"] * sb.GIB:
        raise ValueError("per-job cap exceeds the campaign ceiling")
    if sum(campaign["budget"]["cell_seconds"] for _ in campaign["cells"]) > campaign["budget"]["total_seconds"]:
        raise ValueError("per-cell ceilings sum past the total ceiling; the total deadline would cut the last cell short by construction")
    for cell in campaign["cells"]:
        shapes = {q["shape"] for q in cell["queries"]}
        prefixes = {q["text"].startswith(FORCED_PREFIX) for q in cell["queries"]}
        if shapes != {cell["shape"]} or prefixes != {cell["shape"] == "forced"}:
            raise ValueError(f"{cell['name']}: query list mixes shapes ({sorted(shapes)})")
        if cell["engine"] != ENGINE:
            raise ValueError(f"{cell['name']}: engine {cell['engine']!r} is not the ordinary-SQL comparator")


def measure_config(campaign: dict, started_monotonic: float | None = None, runtime: CampaignRuntime | None = None) -> dict:
    """The `benchmark.measure` config: one shared run_id, per-cell query lists, total deadline, no reservation window.

    With a runtime, every cell also gets its own submission gate and the shared ceiling check."""
    started = time.monotonic() if started_monotonic is None else started_monotonic
    budget = {
        "cell_seconds": campaign["budget"]["cell_seconds"],
        "deadline_monotonic": started + campaign["budget"]["total_seconds"],
        "deadline_reason": campaign["budget"]["deadline_reason"],
    }
    if runtime is not None:
        budget["window_for_cell"] = runtime.window_for_cell
        budget["stop_check"] = runtime.stop_check
        budget["on_cell_sealed"] = runtime.reconcile
    return {
        "run_id": campaign["run_id"],
        "cells": [dict(c) for c in campaign["cells"]],
        "queries": [],   # every cell carries its own shape; nothing is pooled here
        "budget": budget,
    }


def client_factory(dataset: str, make_client: Callable[[], Any] | None = None,
                   runtime: CampaignRuntime | None = None) -> Callable[[], dict]:
    """Per-thread `fallback` clients with both caches off. The client is built on first use, never at import
    or at campaign-build time, which is what keeps `--dry-run` client-free.

    With a runtime the raw client is bound to the current cell's gate, and the ledger and routing guard ride
    along so `retrieve._run` caps, settles and verifies every job."""
    local = threading.local()
    make = make_client or (lambda: bigquery.Client(project=PROJECT, location=LOCATION))

    def get() -> dict:
        if not hasattr(local, "c"):
            local.c = make()
        clients = {"engine": ENGINE, "bq": local.c, "ds": dataset, "use_cache": False}
        if runtime is not None:
            runtime.note_client(local.c)
            window = runtime.current_window()
            if window is None:
                raise RuntimeError("no submission gate is open for this cell; refusing to build an unbounded client")
            clients.update(bq=window.bind(local.c), bytes_ledger=runtime.ledger, routing=runtime.routing)
        return clients
    return get


def describe(campaign: dict) -> str:
    b = campaign["budget"]
    p = campaign["budget_projection"]
    lines = [
        f"sql-baseline campaign {campaign['run_id']} — plan {campaign['plan_version']}, engine {campaign['engine']}, "
        f"requested {campaign['edition_requested']} (job reservation override {campaign['routing']['job_reservation']!r}, "
        f"verified per job), no reservation window, dataset {campaign['project']}.{campaign['dataset']}",
        f"budget: {b['cell_seconds']} s per cell, {b['total_seconds']} s total ({b['deadline_reason']} when reached), "
        f"{b['max_bytes_billed_gib']} GiB billed, ${b['max_usd_ondemand_list']:.2f} at list, enforced by a running "
        f"ledger with per-job maximum_bytes_billed ≤ {b['per_job_cap_bytes'] / sb.GIB:.1f} GiB; projection "
        f"{p['bytes_billed_projected_total'] / sb.GIB:.1f} GiB → ${p['usd_ondemand_list_projected']:.2f} "
        f"({'within' if p['within_budget'] else 'NOT within'} ceiling; a sanity check, not the enforcement)",
        "gates: one submission gate per cell (submission, result polling and pagination stop at the cell/total deadline)",
        "caches: bigquery result cache off, retrieval cache off",
    ]
    for c in campaign["cells"]:
        lines.append(f"  {c['name']}: shape={c['shape']} C={c['concurrency']} warmups={c['warmups']} measured={c['measured']} "
                     f"timeout={c['timeout_s']}s queries={[q['id'] for q in c['queries']]}")
    for name, reasons in campaign["refused"].items():
        lines.append(f"  {name}: REFUSED ({' + '.join(reasons)})")
    return "\n".join(lines)


# --- live ---------------------------------------------------------------------------------------------

def live(campaign: dict, out_dir: Path | str = OUT_DIR, make_client: Callable[[], Any] | None = None,
         measure: Callable[[dict, Callable[[], dict]], dict] | None = None) -> dict:
    """Run the campaign foreground and retain its record. Percentiles come from `benchmark.measure` only."""
    assert_campaign_is_runnable(campaign)
    assert_run_id_is_fresh(campaign["run_id"], out_dir=out_dir)
    out_dir = Path(out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    measure = measure or benchmark.measure
    started_utc, started = _now(), time.monotonic()
    runtime = CampaignRuntime(campaign, out_dir, started + campaign["budget"]["total_seconds"])
    record: dict[str, Any] = {k: v for k, v in campaign.items() if k != "cells"}
    record.update({
        "started_utc": started_utc,
        "cells_declared": [{k: v for k, v in c.items() if k != "queries"} | {"query_ids": [q["id"] for q in c["queries"]]}
                           for c in campaign["cells"]],
        "sdk": {"google-cloud-bigquery": getattr(bigquery, "__version__", None)},
        "requests_file": benchmark.REQUESTS,
        "summary_file": benchmark.SUMMARY,
        "note": ("retrieval_ms only; every attempt retained before aggregation; a cell stopped by its budget stays "
                 "INCOMPLETE / NOT_RUN_BUDGET and carries no invented percentile. The card under evidence/sql-baseline "
                 "is regenerated from this record in a separate reviewed step."),
    })
    try:
        result = measure(measure_config(campaign, started, runtime), client_factory(campaign["dataset"], make_client, runtime))
        record["cells"] = result["cells"]
        record["state"] = "COMPLETE" if all(c["state"] == "COMPLETE" for c in result["cells"]) else "INCOMPLETE"
    except BaseException as e:  # noqa: BLE001 - the record is retained with the failure named
        record["cells"] = []
        record["state"] = "ABORTED"
        record["error"] = f"{type(e).__name__}: {e}"[:500]
        raise
    finally:
        window = runtime.current_window()
        if window is not None:
            window.stop_and_cancel()      # an abort mid-cell still seals the open gate
            if runtime.unresolved_for(window):
                runtime.reconcile({"name": "(final)"}, window)
        record["reconciliations"] = runtime.reconciliations
        record["ended_utc"] = _now()
        record["wall_seconds"] = round(time.monotonic() - started, 1)
        record["billing"] = runtime.ledger.snapshot()
        record["routing"] = dict(campaign["routing"], **runtime.routing.snapshot())
        record["gates"] = runtime.gates
        verified = runtime.routing.verified()
        record["edition"] = "on-demand" if verified else None
        g = runtime.routing
        record["edition_note"] = ("every observed job, failures included, was reported DONE with no reservation_id and no edition"
                                  if verified else "NOT established: " + (
                                      "no job was checked" if g.jobs == 0 else
                                      f"{len(g.violations)} job(s) reported a reservation or edition" if g.violations else
                                      f"{len(g.unknown)} job(s) have no terminal statistics (outcome unknown)"))
        (out_dir / f"run_{campaign['run_id']}.json").write_text(json.dumps(record, indent=2, default=str) + "\n")
    return record


# --- CLI ----------------------------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m okf_bq_graph.sql_baseline_run",
                                 description="Run the predeclared ordinary-SQL baseline retrieval cells (fallback engine, on-demand).")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="print the campaign (cells, queries, budget, run_id); open no client")
    mode.add_argument("--live", action="store_true", help="run the campaign foreground against BigQuery on-demand")
    ap.add_argument("--cells", nargs="+", metavar="CELL", help="retrieval cells to run (default: all four); sqlchain_* are refused")
    ap.add_argument("--run-id", help="campaign run_id (default: fresh sqlbase-<utc>-<hex>); must be unused")
    ap.add_argument("--plan", default=str(sb.PLAN), help="sql-baseline plan JSON (default: fixtures/sql_baseline.json)")
    ap.add_argument("--cases", default=str(CASES), help="pinned question set (default: fixtures/cases.json)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="where run_<run_id>.json is retained")
    return ap


def main(argv: list[str] | None = None, stdout=None) -> int:
    out = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    try:
        campaign = build_campaign(sb.load_plan(args.plan), load_cases(args.cases), args.cells, args.run_id)
        assert_campaign_is_runnable(campaign)
        assert_run_id_is_fresh(campaign["run_id"], out_dir=args.out_dir)
    except RefusedCell as e:
        print(f"REFUSED: {e}", file=out)
        return 2
    except ValueError as e:
        print(f"INVALID: {e}", file=out)
        return 2
    print(describe(campaign), file=out)
    if args.dry_run:
        print("dry run: no client opened, nothing submitted", file=out)
        return 0
    record = live(campaign, out_dir=args.out_dir)
    for c in record["cells"]:
        print(f"  {c['cell']}: {c['state']} n={c['measured_n']}/{c['measured_target']} "
              f"p50_all={c['p50_ms_all']} p95_all={c['p95_ms_all']} stopped={c['stopped_reason']}", file=out)
    print(f"{record['state']}: retained {Path(args.out_dir) / ('run_' + record['run_id'] + '.json')}", file=out)
    return 0 if record["state"] == "COMPLETE" else 1


if __name__ == "__main__":
    sys.exit(main())
