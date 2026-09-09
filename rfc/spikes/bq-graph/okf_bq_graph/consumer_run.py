"""Hermetic sampled request-to-consumer runner (FS-1, 2026-09-09). Dry-run and hermetic modes only.

The ordinary-SQL comparison's two consumer cells (`sqlchain_forced_c1`, `sqlchain_forced_c5`) need a driver that
repeats one predeclared requester question through governed retrieval, binding, the caller-delegated job,
independent verification and the consumer decision, retaining every attempt. `chain.py` runs each of its cases once;
`benchmark.py` stops at retrieval. This module is the sampled loop, reusing the chain's stages unchanged
(`governed`, `pick_computation`, `declaration`, `bind`, `run_receipt`, `consume`, `accept`).

What a hermetic pass establishes: the stages run in order, every attempt is retained, the predeclared refusal
(`f_revenue`, a computation the receipt publication does not carry) refuses at bind with the SDK never invoked, and
the gates fire (SELECTED only, validity window, vendored drift, row oracle, SDK provenance, publication pin). What it
does not establish: data equivalence, GoogleSQL execution, a job identity, a latency, a cost, a filled cell. The
hermetic receipt leg returns the SDK example's planned `400` without reading the seven tables, so this module also
carries a row-based oracle over the vendored content manifest (`gross_margin_from_manifest`), which must reproduce the
expected January and January–February results before any attempt runs; it is Python `Decimal`, not GoogleSQL.

There is no `--live` flag and no BigQuery client anywhere in this module. `admit_live` is the live admission FS-2
must call before its first attempt (expiry, `FACTS_DRIFTED`, `OK` with the digest to bind); here it is exercised by
tests only. Consumer cells stay `INCOMPLETE / RUNNER_HERMETIC_ONLY`; a hermetic attempt never fills a live cell.

Contract: rfc/board-pack/spec-sqlchain-consumer-fs1.md.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import decimal
import hashlib
import json
import math
import os
import re
import secrets
import subprocess
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any, Callable, Optional

from . import BUNDLE_ID, SOURCE_PIN
from . import fact_content, sql_baseline as sb
from .chain import (COMPUTATION_PATH, EXAMPLE_REL, MISMATCH_PATH, MISMATCH_SEED, PUBLICATION_PIN, SEED, SDK_PIN,
                    accept, bind, consume, declaration, governed, pick_computation, run_receipt, sdk_publication,
                    sdk_root as default_sdk_root)

RUNNER_VERSION = "okf_bq_graph.consumer_run/0.1.2"  # 0.1.2: launch evidence tracked across the receipt helper, preflight failures retained; 0.1.1: atomic run-id ownership, attempt-boundary retention, retained CLI refusals, SQL NULL/FX oracle semantics
ROOT = sb.ROOT
OUT_DIR = ROOT / "evidence" / "consumer"
FACTS_DIR = ROOT / "fixtures" / "facts"
CASES = ROOT / "fixtures" / "cases.json"
RECORD_GLOB = "run_consumer-hermetic-*.json"
RUN_ID_RE = re.compile(r"^consumer-hermetic-\d{8}T\d{6}Z-[0-9a-f]{8}$")
QUESTION_ID, PROBE_ID = "f_current", "f_revenue"
JAN = {"period_start": "2026-01-01", "period_end": "2026-01-31"}
JAN_FEB = {"period_start": "2026-01-01", "period_end": "2026-02-28"}
OK, REFUSED = "OK", "REFUSED"
RUNNER_OK, RUNNER_INCOMPLETE, RUNNER_BROKEN = "RUNNER_HERMETIC_OK", "RUNNER_HERMETIC_INCOMPLETE", "RUNNER_HERMETIC_BROKEN"
CLAIMS = {
    "establishes": ["the stages run in order: retrieval, declaration, bind, caller-delegated (emulated) job, verification, consumer decision",
                    "every attempt is retained with its stage outcomes, refusals included",
                    "the predeclared refusal (f_revenue) refuses at bind with the SDK never invoked",
                    "the gates fire: SELECTED only, validity window, vendored drift, row oracle, SDK provenance, publication pin"],
    "does_not_establish": ["data equivalence between the vendored manifest and any live table",
                           "GoogleSQL execution of the sanctioned SQL (the hermetic SDK returns its planned value; the row oracle is Python Decimal)",
                           "a job identity (the emulation's okf_rcpt ids are not BigQuery jobs)",
                           "a latency: hermetic_orchestration_ms is in-process oracle plus subprocess emulation on one machine, not request_to_consumer_ms",
                           "a cost", "a filled consumer cell (stopped_reason stays RUNNER_HERMETIC_ONLY)"],
}
Runner = Callable[..., subprocess.CompletedProcess]
D = decimal.Decimal


class Refusal(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


# ----------------------------------------------------------------------------- row-based oracle
def _rows(manifest: dict, table: str) -> list[dict]:
    t = manifest["tables"].get(table)
    if t is None:
        raise KeyError(table)
    names = [f["name"] for f in t["schema"]]
    return [dict(zip(names, row)) for row in t["rows"]]


def _dec(v) -> Optional[D]:
    return None if v is None else D(v)


def _date_of_ts(ts: str) -> _dt.date:
    return _dt.datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone(_dt.timezone.utc).date()


def gross_margin_from_manifest(manifest: dict, period_start: _dt.date, period_end: _dt.date, evaluation_date: _dt.date) -> Optional[D]:
    """The sanctioned SQL's semantics over `okf-fact-content/1` rows, join graph reproduced row for row.

    recognized_orders: delivered, DATE(order_ts) at least 30 days before `evaluation_date` (CURRENT_DATE()), inside
    the period; the FX LEFT JOIN happens before the CASE, so every matching rate row yields a recognised row (USD too);
    revenue = net_amount (USD) or net_amount * rate_to_usd (no rate -> NULL, dropped by SUM; all NULL -> the SUM and the
    whole expression are NULL). cogs_full: order_lines JOIN products LEFT JOIN fulfillment_cost, shipment_cost, payment_fees, summed per
    order over the joined rows exactly as the SQL would (a duplicated join row duplicates its cost). Result:
    SUM(revenue) - SUM(COALESCE(components, 0)) over recognized LEFT JOIN cogs; None when nothing is recognised."""
    fx = {}
    for r in _rows(manifest, "fx_daily_rates"):
        fx.setdefault((r["currency"], _dt.date.fromisoformat(r["rate_date"])), []).append(_dec(r["rate_to_usd"]))
    recognized: list[tuple[str, Optional[D]]] = []
    for o in _rows(manifest, "orders"):
        d = _date_of_ts(o["order_ts"])
        if o["order_status"] != "delivered" or (evaluation_date - d).days < 30 or not (period_start <= d <= period_end):
            continue
        net = _dec(o["net_amount"])
        # the SQL LEFT JOINs fx_daily_rates BEFORE the CASE: one recognised row per matching rate row (or one with a NULL
        # rate), for USD orders too, so duplicated rate rows duplicate the order's revenue exactly as the SQL would
        for rate in fx.get((o["currency"], d)) or [None]:
            if o["currency"] == "USD":
                recognized.append((o["order_id"], net))
            else:
                recognized.append((o["order_id"], None if (net is None or rate is None) else net * rate))
    products = {}
    for p in _rows(manifest, "products"):
        products.setdefault(p["product_id"], []).append(_dec(p["cost"]))
    by_order = lambda table, col: _group(_rows(manifest, table), "order_id", col)   # noqa: E731
    fc, sc, pf = by_order("fulfillment_cost", "allocated_cost"), by_order("shipment_cost", "shipping_cost"), by_order("payment_fees", "fee_amount")
    cogs: dict[str, dict[str, Optional[D]]] = {}
    for ol in _rows(manifest, "order_lines"):
        oid, qty = ol["order_id"], _dec(ol["quantity"])
        for cost in products.get(ol["product_id"], []):          # inner join
            for a in fc.get(oid) or [None]:
                for b in sc.get(oid) or [None]:
                    for c in pf.get(oid) or [None]:
                        acc = cogs.setdefault(oid, {"product_cost": None, "fulfillment_cost": None, "shipping_cost": None, "payment_fee": None})
                        for key, val in (("product_cost", None if (qty is None or cost is None) else qty * cost),
                                         ("fulfillment_cost", a), ("shipping_cost", b), ("payment_fee", c)):
                            if val is not None:
                                acc[key] = val if acc[key] is None else acc[key] + val
    if not recognized:
        return None
    revenues = [v for _, v in recognized if v is not None]
    if not revenues:
        return None          # SUM over all-NULL revenue is NULL, and NULL minus anything is NULL (GoogleSQL SUM)
    revenue = sum(revenues, D(0))
    total_cogs = D(0)
    for oid, _ in recognized:
        c = cogs.get(oid) or {}
        total_cogs += sum((c.get(k) or D(0)) for k in ("product_cost", "fulfillment_cost", "shipping_cost", "payment_fee"))
    return revenue - total_cogs


def _group(rows: list[dict], key: str, col: str) -> dict[str, list[Optional[D]]]:
    out: dict[str, list[Optional[D]]] = {}
    for r in rows:
        out.setdefault(r[key], []).append(_dec(r[col]))
    return out


def _plain(d: Optional[D]) -> Optional[str]:
    if d is None:
        return None
    s = format(d, "f")
    return s.rstrip("0").rstrip(".") if "." in s else s


def _expected_jan_feb() -> str:
    return json.loads((FACTS_DIR / "expected.json").read_text())["approved_january_february"]["gross_margin_usd"]


def row_oracle_check(version: dict, manifest: dict, evaluation_date: _dt.date) -> dict:
    """The vendored rows must reproduce the expected January (selection record) and January–February (expected.json)
    results under the sanctioned SQL's semantics. Python Decimal; not GoogleSQL; not a live read."""
    jan = gross_margin_from_manifest(manifest, _dt.date.fromisoformat(JAN["period_start"]), _dt.date.fromisoformat(JAN["period_end"]), evaluation_date)
    jf = gross_margin_from_manifest(manifest, _dt.date.fromisoformat(JAN_FEB["period_start"]), _dt.date.fromisoformat(JAN_FEB["period_end"]), evaluation_date)
    want_jan, want_jf = D(str(version["expected_gross_margin_usd_2026_01"])), D(_expected_jan_feb())
    out = {"engine": "python-decimal", "not": "googlesql", "evaluation_date": evaluation_date.isoformat(),
           "january": _plain(jan), "january_february": _plain(jf),
           "expected": {"january": _plain(want_jan), "january_february": _plain(want_jf)},
           "note": "a bounded re-implementation of the sanctioned SQL over the vendored okf-fact-content/1 manifest; it establishes "
                   "consistency of the vendored rows with expected.json, not GoogleSQL execution or any live table's content"}
    reasons = []
    if jan is None or jan != want_jan:
        reasons.append(f"january: oracle {_plain(jan)} != expected {_plain(want_jan)}")
    if jf is None or jf != want_jf:
        reasons.append(f"january_february: oracle {_plain(jf)} != expected {_plain(want_jf)}")
    out["status"] = "ORACLE_DISAGREES" if reasons else OK
    if reasons:
        out["reason"] = "; ".join(reasons)
    return out


# ----------------------------------------------------------------------------- live admission (pure; FS-2 calls it)
def expiry_date(version: dict) -> Optional[_dt.date]:
    m = sb._ABOUT_DATE.match(str(version.get("materialization_expires_utc", "")))
    return _dt.date.fromisoformat(m.group(1)) if m else None


def admit_live(version: dict, readback_manifest: dict, today: _dt.date, evaluation_date: _dt.date) -> dict:
    """Before any live attempt: the readback (every selected table, full schema and rows, canonicalised as
    okf-fact-content/1) must hash to the selected content digest, and the materialization must not have expired.
    Row counts and the January result are reported as smoke checks and decide nothing."""
    expires = expiry_date(version)
    if expires is not None and today >= expires:
        return {"status": "MATERIALIZATION_EXPIRED", "expires_about": expires.isoformat(), "today": today.isoformat(),
                "reason": f"the materialization expires about {expires.isoformat()}; reload the same digest under the owner's gate and record the new load job"}
    raw = fact_content.canonical_bytes(readback_manifest)
    digest = fact_content.sha256(raw)
    vendored = json.loads((FACTS_DIR / "content.json").read_text())
    theirs, ours = fact_content.per_table_digests(readback_manifest), fact_content.per_table_digests(vendored)
    differing = sorted(t for t in set(theirs) | set(ours) if theirs.get(t) != ours.get(t))
    drifted = digest != version["content_manifest_sha256"]      # the verdict, established before any advisory check runs
    smoke: dict[str, Any] = {"row_counts_match": False, "january_matches": False,
                             "note": "smoke checks only: a changed non-January amount leaves both true while the content digest changes; "
                                     "they never decide admission and a failure to evaluate them is a diagnostic, not a crash"}
    try:
        smoke["row_counts_match"] = fact_content.row_counts(readback_manifest) == version["row_counts"]
        jan = gross_margin_from_manifest(readback_manifest, _dt.date.fromisoformat(JAN["period_start"]), _dt.date.fromisoformat(JAN["period_end"]), evaluation_date)
        smoke["january_matches"] = jan is not None and jan == D(str(version["expected_gross_margin_usd_2026_01"]))
    except Exception as e:  # noqa: BLE001 - a readback whose schema drifted may not evaluate; the digest already decided
        smoke["error"] = f"{type(e).__name__}: {str(e)[:200]}"
    if drifted:
        return {"status": "FACTS_DRIFTED", "readback_digest": digest, "selected_digest": version["content_manifest_sha256"],
                "differing_tables": differing, "smoke": smoke,
                "reason": "the readback does not hash to the selected content digest: the campaign stops with no cell filled"}
    return {"status": OK, "bound_content_digest": digest, "expires_about": expires.isoformat() if expires else None,
            "smoke": smoke, "note": "a passing readback is necessary, not proof the rows stayed equal during the campaign; bind the digest to every attempt"}


# ----------------------------------------------------------------------------- gates
def _gate(code: str, ok: bool, detail: str) -> dict:
    return {"code": code, "status": OK if ok else REFUSED, "detail": detail}


def fresh_run_id(now: Optional[_dt.datetime] = None) -> str:
    now = now or _dt.datetime.now(_dt.timezone.utc)
    return f"consumer-hermetic-{now:%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"


def _pinned_questions(cases_path: Path | str) -> dict:
    cases = json.loads(Path(cases_path).read_text())
    return {q["id"]: q for q in cases["forced_seeds"]}


def run_gates(plan: Optional[dict], cells: Optional[list[str]], run_id: str, out_dir: Path | str, evaluation_date: _dt.date,
              cases_path: Path | str = CASES, owned: bool = False, plan_error: Optional[str] = None) -> list[dict]:
    """The subprocess-free gates, in order; the list stops at the first refusal. `owned` says this invocation has
    already claimed the run directory atomically (run_hermetic), so its own directory is not a reuse."""
    gates: list[dict] = []

    def add(code: str, ok: bool, detail: str) -> bool:
        gates.append(_gate(code, ok, detail))
        return ok

    if plan is None:
        add("PLAN_INVALID", False, plan_error or "the plan could not be read")
        return gates
    try:
        sb.validate_plan(plan)
        add("PLAN_INVALID", True, "validate_plan passed (vendored artifacts re-hashed, manifest re-derived)")
    except (ValueError, KeyError, TypeError, OSError, AttributeError) as e:
        add("PLAN_INVALID", False, f"{type(e).__name__}: {str(e)[:300]}")
        return gates
    if cells is None:      # derived only after the plan validated: a cell without a name is PLAN_INVALID above, not a crash
        cells = [c["name"] for c in plan["consumer_cells"]]
    facts = plan["facts"]
    if not add("FACTS_UNSELECTED", facts.get("state") == "SELECTED", f"facts.state = {facts.get('state')}"):
        return gates
    consumer = {c["name"]: c for c in plan["consumer_cells"]}
    retrieval = {c["name"] for c in plan["retrieval_cells"]}
    for name in cells:
        if name in retrieval:
            add("NOT_A_CONSUMER_CELL", False, f"{name} is a retrieval cell: okf_bq_graph.sql_baseline_run measures it; this driver never pretends to")
            return gates
        if name not in consumer:
            add("UNKNOWN_CELL", False, f"{name} is not a cell in the plan (consumer cells: {sorted(consumer)})")
            return gates
    if len(set(cells)) != len(cells):
        add("UNKNOWN_CELL", False, "a cell is listed twice")
        return gates
    add("NOT_A_CONSUMER_CELL", True, f"cells: {', '.join(cells)}")
    if not add("RUN_ID_UNLABELLED", bool(RUN_ID_RE.match(run_id)), f"run_id {run_id}"):
        return gates
    out_dir = Path(out_dir)
    used = (out_dir / f"run_{run_id}.json").exists() or (not owned and (out_dir / run_id).exists())
    if not add("RUN_ID_REUSED", not used, ("owned: this invocation created the run directory atomically" if owned else
                                            "no retained record or run directory carries this id") if not used
               else f"a record or run directory for {run_id} already exists"):
        return gates
    version = facts["selected_version"]
    valid_from = _dt.date.fromisoformat(version["valid_for_runs_on_or_after"])
    if not add("VALIDITY_WINDOW", evaluation_date >= valid_from,
               f"evaluation date {evaluation_date.isoformat()} vs valid_for_runs_on_or_after {valid_from.isoformat()}: the sanctioned SQL's 30-day "
               "recognition clause" + (" recognises every fixture order" if evaluation_date >= valid_from else " would not recognise the February order, so the expected results do not hold")):
        return gates
    try:
        q = _pinned_questions(cases_path)
    except (OSError, ValueError, KeyError, TypeError) as e:
        add("QUESTION_PINNED", False, f"the pinned question set {cases_path} could not be read: {type(e).__name__}: {str(e)[:200]}")
        return gates
    pinned = (q.get(QUESTION_ID, {}).get("text") == SEED and q.get(QUESTION_ID, {}).get("expect_computation") == COMPUTATION_PATH
              and q.get(PROBE_ID, {}).get("text") == MISMATCH_SEED and q.get(PROBE_ID, {}).get("expect_computation") == MISMATCH_PATH)
    if not add("QUESTION_PINNED", pinned, f"{QUESTION_ID} = {SEED} -> {COMPUTATION_PATH}; {PROBE_ID} = {MISMATCH_SEED} -> {MISMATCH_PATH}"
               if pinned else f"fixtures/cases.json does not pin {QUESTION_ID}/{PROBE_ID} to the chain's seeds and computations"):
        return gates
    try:
        derived = fact_content.extract((FACTS_DIR / "fixture.sql").read_text())
        derived_digest = fact_content.sha256(fact_content.canonical_bytes(derived))
        vendored_digest = fact_content.sha256((FACTS_DIR / "content.json").read_bytes())
    except (OSError, ValueError) as e:
        add("VENDORED_FACTS_DRIFTED", False, f"{type(e).__name__}: {str(e)[:200]}")
        return gates
    want = version["content_manifest_sha256"]
    if not add("VENDORED_FACTS_DRIFTED", derived_digest == want == vendored_digest,
               f"extract(fixture.sql) {derived_digest[:12]}…, content.json {vendored_digest[:12]}…, selected {want[:12]}… (hermetic stand-in for the live precheck: no live read)"):
        return gates
    oracle = row_oracle_check(version, derived, evaluation_date)
    add("ORACLE_DISAGREES", oracle["status"] == OK, oracle.get("reason") or f"january {oracle['january']}, january_february {oracle['january_february']} as expected")
    return gates


def _first_refusal(gates: list[dict]) -> Optional[dict]:
    return next((g for g in gates if g["status"] == REFUSED), None)


# ----------------------------------------------------------------------------- records
def consumer_records(out_dir: Path | str = OUT_DIR) -> list[dict]:
    """Every retained hermetic run, oldest first."""
    out_dir = Path(out_dir)
    records = []
    for path in sorted(out_dir.glob(RECORD_GLOB)):
        rec = json.loads(path.read_text())
        rec["_file"] = f"evidence/consumer/{path.name}"
        records.append(rec)
    records.sort(key=lambda r: (r.get("started_utc") or "", r["_file"]))
    return records


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _nearest_rank(values: list[float], q: float) -> Optional[float]:
    if not values:
        return None
    s = sorted(values)
    return s[max(1, math.ceil(q * len(s))) - 1]


def _stage_error(e: BaseException) -> dict:
    return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:300]}"}


# ----------------------------------------------------------------------------- one attempt
def _attempt(cell: str, index: int, kind: str, ctx: dict) -> dict:
    """One attempt, with every stage failure retained on the record: a stage that raises leaves what came before it,
    an `error`, a REFUSED decision and a NOT_REACHED acceptance. Nothing raises out of here (Kimi P1 / Astra #2)."""
    probe = kind == "probe"
    a: dict[str, Any] = {"cell": cell, "index": index, "kind": kind,
                         "question_id": PROBE_ID if probe else QUESTION_ID, "seed": MISMATCH_SEED if probe else SEED,
                         "expected_decision": REFUSED if probe else "RELEASED", "started_utc": _now(),
                         "selected_content_digest": ctx["digest"], "evaluation_date": ctx["evaluation_date"], "error": None}
    t0 = time.monotonic()
    try:
        _run_stages(a, probe, ctx, cell, index)
    except Exception as e:  # noqa: BLE001 - the attempt boundary: retained, never raised into the pool
        a["error"] = f"{type(e).__name__}: {str(e)[:300]}"
        a["stage_failed"] = a.get("stage_failed") or "unknown"
    a.setdefault("retrieval", {"status": "NOT_RUN", "reached": False})
    a.setdefault("computation", None); a.setdefault("declaration", None)
    a.setdefault("bind", {"status": "NOT_REACHED", "reason": "a stage before bind failed", "failed_checks": []})
    if "receipt" not in a or a["receipt"].get("_pending"):
        a["receipt"] = _receipt_evidence(a.get("receipt") or {}, a["error"])
    if "consume" not in a:
        a["consume"] = {"decision": REFUSED, "reasons": [f"stage {a.get('stage_failed')} failed: {a['error']}"], "display": None}
    a["finished_utc"] = _now()
    a["request_to_consumer_ms"] = round((time.monotonic() - t0) * 1000, 1)
    if "acceptance" not in a:
        a["acceptance"] = {"status": "NOT_REACHED", "failed": [f"stage {a.get('stage_failed')} raised: {a['error']}"],
                           "rule": "a stage exception is an outage before the intended stage: unproven, not contradicted"}
    a.pop("_bind_full", None)
    return a


def _receipt_evidence(pending: dict, error: Optional[str]) -> dict:
    """What can be said about the SDK child when the receipt helper did not return normally (Astra RR #1).

    Invocation is asserted only from the runner call itself: no runner call means the child was never launched; a
    runner that was entered but never returned means invocation is UNKNOWN, retained as uncertainty rather than as
    non-invocation; a runner that returned means the child completed, and its private diagnostic — still in the
    invocation directory because the retention step is what failed — is referenced in place with its digest."""
    launch = pending.get("launch") or {}
    if not pending.get("_pending"):
        return {"invoked": False, "launch_attempted": False, "diag_present": False, "reason": "a stage before the receipt failed"}
    if not launch:
        return {"invoked": False, "launch_attempted": False, "child_completed": False, "diag_present": False, "sdk_case": pending.get("sdk_case"),
                "reason": f"the receipt helper raised before calling the runner: nothing was launched ({error})"}
    out: dict[str, Any] = {"invoked": "UNKNOWN" if "exit_code" not in launch else True, "launch_attempted": True,
                           "child_completed": "exit_code" in launch, "sdk_case": pending.get("sdk_case"),
                           "argv": launch.get("argv"), "launched_at_utc": launch.get("launched_at_utc"),
                           "exit_code": launch.get("exit_code"), "elapsed_ms": launch.get("elapsed_ms"), "stdout": launch.get("stdout"),
                           "invocation_dir": launch.get("invocation_dir"), "diag_present": False, "diag_path": None, "diag_sha256": None,
                           "request_id": None, "receipt_id": None, "verdict": None, "execution_match": None,
                           "retention": f"FAILED: the helper did not return after the launch ({error}); the invocation directory is left in place",
                           "job_times": {"submitted_at": None, "done_at": None, "note": "hermetic emulation: no BigQuery job"}}
    if "exit_code" not in launch:
        out["reason"] = "the runner was entered and raised: whether the child ran to completion cannot be established from here"
        return out
    private = Path(launch["invocation_dir"]) / "case_approved_hermetic.json" if launch.get("invocation_dir") else None
    try:
        if private is not None and private.is_file():
            raw = private.read_bytes()
            diag = json.loads(raw.decode("utf-8"))
            issued = (diag.get("issue_out") or {}).get("receipt") or {}
            out.update({"diag_present": True, "diag_path": str(private), "diag_sha256": hashlib.sha256(raw).hexdigest(),
                        "request_id": diag.get("request_id"), "receipt_id": issued.get("receipt_id"), "verdict": issued.get("verdict"),
                        "execution_match": issued.get("execution_match"), "released": diag.get("released"), "job": issued.get("job"),
                        "diag_note": "private diagnostic referenced in place: retention into the run's receipt directory failed"})
        else:
            out["diag_note"] = "the child completed but no private diagnostic was found in its invocation directory"
    except (OSError, ValueError) as e:
        out["diag_note"] = f"the private diagnostic could not be read: {type(e).__name__}: {str(e)[:120]}"
    return out


def _run_stages(a: dict, probe: bool, ctx: dict, cell: str, index: int) -> None:
    seed, path = (MISMATCH_SEED, MISMATCH_PATH) if probe else (SEED, COMPUTATION_PATH)
    comp = decl = None
    a["stage_failed"] = "retrieval"
    try:
        r0 = time.monotonic()
        r = governed(seed, ctx["pub"], ctx["requester"], ctx["as_of"], ctx["clients"])
        a["retrieval"] = {"status": r.get("status"), "reached": False, "cache": (r.get("scope") or {}).get("cache"),
                          "elapsed_ms": round((time.monotonic() - r0) * 1000, 1), "stages": r.get("timing"),
                          "warnings": list(r.get("warnings") or [])}
        comp = pick_computation(r, path) if r.get("status") == "OK" else None
        a["retrieval"]["reached"] = comp is not None
    except Exception as e:  # noqa: BLE001 - retained, never raised out of the loop
        a["retrieval"] = dict(_stage_error(e), reached=False)
        a["error"] = a["retrieval"]["error"]
    a["computation"] = None if comp is None else {"path": comp.get("path"), "concept_hops": comp.get("concept_hops"),
                                                   "runtime_verdict": comp.get("runtime_verdict"), "sql_chars": len(comp.get("sql") or "")}
    a["stage_failed"] = "declaration"
    if comp is not None:
        try:
            decl = declaration(ctx["clients"], comp["computation_id"], ctx["pub"])
        except Exception as e:  # noqa: BLE001
            decl = _stage_error(e)
            a["error"] = decl["error"]
    a["declaration"] = None if decl is None else {"status": decl.get("status"), "type": decl.get("type")}
    a["stage_failed"] = "bind"
    if comp is None or decl is None or decl.get("status") != "OK":
        a["bind"] = {"status": "NOT_BOUND", "reason": "computation not reached or declaration not visible", "failed_checks": []}
    else:
        b = bind(comp, decl, ctx["sdk_pub"], ctx["as_of"], source_pin=SOURCE_PIN)
        a["bind"] = {"status": b["status"], "failed_checks": sorted(k for k, v in b["checks"].items() if not v["ok"]),
                     "computation_digest": b.get("computation_digest")}
        a["_bind_full"] = b
    b_full = a.pop("_bind_full", {"status": a["bind"]["status"]})
    a["stage_failed"] = "receipt"
    if a["bind"]["status"] == "BOUND":
        launch: dict[str, Any] = {}
        a["receipt"] = {"_pending": True, "sdk_case": "approved", "launch": launch}   # replaced below; read by _receipt_evidence on failure
        inner = ctx["runner"]

        def tracking_runner(argv, **kw):
            """Evidence of the launch survives whatever happens after the runner returns (Astra RR #1)."""
            launch["argv"] = list(argv)
            launch["invocation_dir"] = argv[argv.index("--evidence-dir") + 1] if "--evidence-dir" in argv else None
            launch["launched_at_utc"] = _now()
            t = time.monotonic()
            r = inner(argv, **kw)
            launch["elapsed_ms"] = round((time.monotonic() - t) * 1000, 1)
            launch["exit_code"] = getattr(r, "returncode", None)
            launch["stdout"] = (getattr(r, "stdout", "") or "")[-500:]
            return r

        rec = run_receipt("approved", ctx["sdk_root"], ctx["receipt_dir"], live=False, runner=tracking_runner, label=f"{cell}_{index:03d}")
        receipt, out = rec.get("receipt") or {}, rec.get("output") or {}
        a["receipt"] = {"invoked": True, "sdk_case": "approved", "exit_code": rec["exit_code"], "elapsed_ms": rec["elapsed_ms"],
                        "diag_present": rec["diag_present"], "request_id": rec.get("request_id"), "receipt_id": receipt.get("receipt_id"),
                        "verdict": receipt.get("verdict"), "output_verdict": out.get("verdict"), "execution_match": receipt.get("execution_match"),
                        "reason_codes": out.get("reason_codes"), "job": receipt.get("job"),
                        "job_times": {"submitted_at": None, "done_at": None,
                                      "note": "hermetic: the SDK emulation submits no BigQuery job and reports no timestamps; a live diagnostic would carry the job's creation and end times"},
                        "issued_at": receipt.get("issued_at"), "expires_at": receipt.get("expires_at"), "released": rec.get("released"),
                        "diag_path": rec.get("diag_path"), "diag_sha256": rec.get("diag_sha256"), "stderr_tail": (rec.get("stderr_tail") or "")[-300:]}
        rec_for_consume = rec
    else:
        a["receipt"] = {"invoked": False, "reason": f"bind {a['bind']['status']}: nothing was executed", "diag_present": False}
        rec_for_consume = {"invoked": False}
    a["stage_failed"] = "consume"
    decision = consume(b_full, rec_for_consume)
    a["consume"] = {"decision": decision["decision"], "reasons": decision["reasons"], "display": decision.get("display")}
    a["stage_failed"] = "accept"
    shim = {"case": "declaration-mismatch" if probe else "approved",
            "retrieval": {"status": a["retrieval"].get("status"), "reached": a["retrieval"].get("reached")},
            "declaration": {"status": (decl or {}).get("status")}, "bind": b_full,
            "receipt": {"invoked": a["receipt"]["invoked"], "exit_code": a["receipt"].get("exit_code"), "diag_present": a["receipt"].get("diag_present")},
            "consume": a["consume"]}
    v = accept(shim)
    a["acceptance"] = {"status": v["status"], "failed": v["failed"],
                       "rule": "chain.accept: the question follows the `approved` case, the probe the `declaration-mismatch` case"}
    a["stage_failed"] = None


# ----------------------------------------------------------------------------- the campaign
def run_hermetic(plan: Optional[dict], cells: Optional[list[str]], out_dir: Path | str = OUT_DIR, sdk_root: Optional[str] = None,
                 acme_root: Optional[str] = None, as_of: Optional[str] = None, runner: Runner = subprocess.run,
                 run_id: Optional[str] = None, cases_path: Path | str = CASES, plan_error: Optional[str] = None) -> dict:
    """`plan=None` with `plan_error` is a preflight failure (unreadable or malformed plan) that still owns a run id and
    retains its refusal (Astra RR #2); `cells=None` derives the plan's consumer cells after validation."""
    from .authz import operator, redact
    from .compile import compile_bundle
    from .oracle import Graph
    out_dir = Path(out_dir)
    sdk_root = sdk_root or default_sdk_root()
    acme_root = acme_root or os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail")
    as_of = as_of or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evaluation_date = _dt.date.fromisoformat(as_of[:10])
    run_id = run_id or fresh_run_id()
    # ---- ownership first (Astra #1): the run directory is claimed atomically before any gate, subprocess or write.
    # A second invocation with the same id, concurrent or later, cannot own it and retains nothing; the owner's
    # record and journal are never touched by anyone else.
    run_dir = out_dir / run_id
    owned = _claim(run_dir) if RUN_ID_RE.match(run_id) and not (out_dir / f"run_{run_id}.json").exists() else False
    rec: dict[str, Any] = {"runner": RUNNER_VERSION, "run_id": run_id, "mode": "hermetic", "engine": "oracle", "started_utc": _now(),
                           "as_of": as_of, "evaluation_date": evaluation_date.isoformat(), "bundle_id": BUNDLE_ID, "source_pin": SOURCE_PIN,
                           "requester": {"mode": "same-requester", "note": "hermetic: the oracle graph and the SDK emulation submit no job; no identity exists to read"},
                           "question": {"id": QUESTION_ID, "seed": SEED, "computation": COMPUTATION_PATH, "parameters": dict(JAN), "expected_decision": "RELEASED",
                                        "note": "the SDK example's fixed January `approved` case; the parameters are the CLI's own, this runner passes none"},
                           "probe": {"id": PROBE_ID, "seed": MISMATCH_SEED, "computation": MISMATCH_PATH, "expected_decision": REFUSED, "expected_stage": "bind",
                                     "expected_failed_checks": ["file_sha256", "sql_text"], "sdk_invoked": False,
                                     "note": "a computation the receipt publication does not carry: declared in advance to refuse, never a substituted answer"},
                           "claims": CLAIMS, "attempts": [], "cells": []}
    if not owned:
        code = "RUN_ID_UNLABELLED" if not RUN_ID_RE.match(run_id) else "RUN_ID_REUSED"
        rec["gates"] = [_gate(code, False, f"run_id {run_id}: " + ("not labelled consumer-hermetic-<utc>-<hex8>" if code == "RUN_ID_UNLABELLED"
                                                                   else "another invocation owns this id (its record and journal are left as they are)"))]
        rec["verdict"] = REFUSED; rec["refusal"] = rec["gates"][0]; rec["retained"] = False
        rec["finished_utc"] = _now()
        return redact(rec)
    try:
        gates = run_gates(plan, cells, run_id, out_dir, evaluation_date, cases_path, owned=True, plan_error=plan_error)
    except Exception as e:  # noqa: BLE001 - a preflight crash is retained as a refusal, never an empty owned directory
        gates = [_gate("PREFLIGHT_ERROR", False, f"{type(e).__name__}: {str(e)[:300]}")]
    if cells is None and plan is not None and _first_refusal(gates) is None:
        cells = [c["name"] for c in plan["consumer_cells"]]
    rec["gates"] = gates
    refusal = _first_refusal(gates)
    if refusal is None:
        version = plan["facts"]["selected_version"]
        rec["plan"] = {"version": plan["version"], "facts_state": plan["facts"]["state"],
                       "selected_version": {k: version[k] for k in ("kind", "synthetic", "dataset", "location", "tables", "sdk_pin", "fixture_sha256",
                                                                    "content_manifest_sha256", "row_counts", "expected_gross_margin_usd_2026_01",
                                                                    "valid_for_runs_on_or_after", "materialization_expires_utc",
                                                                    "live_materialization", "historical_chain_equivalence")}}
        rec["row_oracle"] = row_oracle_check(version, json.loads((FACTS_DIR / "content.json").read_text()), evaluation_date)
        expires = expiry_date(version)
        rec["expiry"] = {"expires_about": expires.isoformat() if expires else None, "evaluation_date": evaluation_date.isoformat(),
                         "live_admission_would_refuse": bool(expires and evaluation_date >= expires),
                         "note": "hermetic mode reads no live table, so it does not refuse on expiry; a live admission on this date would"}
        rec["live_admission"] = {"status": "NOT_RUN", "reason": "hermetic mode reads no live table; admit_live is exercised by tests against the vendored manifest only"}
        rec["budget"] = {"consumer_sampling": plan["budget"].get("consumer_sampling"), "spent": "nothing",
                         "note": "hermetic: no job, no bytes, no USD; the block is declared for FS-2 and not drawn on"}
        # SDK provenance (subprocess-free: data files + git)
        try:
            sdk_pub = sdk_publication(sdk_root)
        except (OSError, ValueError, KeyError) as e:
            sdk_pub = None
            gates.append(_gate("SDK_UNAVAILABLE", False, f"{type(e).__name__}: {str(e)[:200]} at {sdk_root}"))
        if sdk_pub is not None:
            rec["sdk"] = {"root": sdk_root, "head": sdk_pub["sdk_head"], "pin": SDK_PIN, "head_matches_pin": sdk_pub["sdk_head_matches_pin"],
                          "repo_dirty": sdk_pub["sdk_repo_dirty"], "publication_id": sdk_pub["manifest"]["publication_id"],
                          "computation_digest": sdk_pub["computation_digest"], "synthetic_fixture": bool(sdk_pub["manifest"].get("synthetic")),
                          "invocation": "subprocess run.py --case approved (hermetic), one invocation per bound attempt"}
            clean = sdk_pub["sdk_head_matches_pin"] and sdk_pub["sdk_repo_dirty"] is False
            gates.append(_gate("SDK_PROVENANCE", clean, f"head {sdk_pub['sdk_head']} vs pin {SDK_PIN}; repo_dirty {sdk_pub['sdk_repo_dirty']}"))
        refusal = _first_refusal(gates)
    projection = None
    if refusal is None:
        try:
            projection = compile_bundle(acme_root, BUNDLE_ID, SOURCE_PIN)
            gates.append(_gate("PUBLICATION_PIN", projection["publication_id"] == PUBLICATION_PIN,
                               f"compiled projection {projection['publication_id']} vs pin {PUBLICATION_PIN}"))
        except Exception as e:  # noqa: BLE001
            gates.append(_gate("PUBLICATION_PIN", False, f"compile failed: {type(e).__name__}: {str(e)[:200]}"))
        refusal = _first_refusal(gates)
    if refusal is not None:
        rec["verdict"] = REFUSED
        rec["refusal"] = refusal
        rec["retained"] = True
        rec["finished_utc"] = _now()
        return _write(rec, out_dir, run_dir, redact)
    receipt_dir = run_dir / "receipt"
    jsonl = run_dir / "attempts.jsonl"
    lock = threading.Lock()
    clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection}
    ctx = {"clients": clients, "pub": projection["publication_id"], "requester": operator(), "as_of": as_of, "sdk_pub": sdk_pub,
           "sdk_root": sdk_root, "receipt_dir": str(receipt_dir), "runner": runner,
           "digest": plan["facts"]["selected_version"]["content_manifest_sha256"], "evaluation_date": evaluation_date.isoformat()}
    rec["evidence"] = {"run_dir": str(run_dir), "attempts_jsonl": str(jsonl), "receipt_dir": str(receipt_dir),
                       "note": "attempts.jsonl is appended as each attempt finishes; a crash retains everything before it"}
    by_name = {c["name"]: c for c in plan["consumer_cells"]}
    for name in cells:
        cell = by_name[name]
        n_warm, n_meas, conc = cell["warmups"], cell["measured"], cell["concurrency"]
        in_flight, peak = 0, 0
        attempts: list[dict] = []

        def one(index: int, kind: str) -> dict:
            nonlocal in_flight, peak
            with lock:
                in_flight += 1
                peak = max(peak, in_flight)
            try:
                a = _attempt(name, index, kind, ctx)
            finally:
                with lock:
                    in_flight -= 1
            with lock:
                with jsonl.open("a", encoding="utf-8") as fh:
                    fh.write(json.dumps(redact(a), sort_keys=True, default=str) + "\n")
            return a

        plan_kinds = [(i, "warmup" if i < n_warm else "measured") for i in range(n_warm + n_meas)]
        with ThreadPoolExecutor(max_workers=conc) as ex:
            attempts = [f.result() for f in [ex.submit(one, i, k) for i, k in plan_kinds]]
        attempts.append(one(n_warm + n_meas, "probe"))
        attempts.sort(key=lambda a: a["index"])
        measured = [a for a in attempts if a["kind"] == "measured"]
        probe = attempts[-1]
        statuses = [a["acceptance"]["status"] for a in attempts]
        ms = [a["request_to_consumer_ms"] for a in measured]
        summary = {"cell": name, "concurrency": conc, "concurrency_achieved": peak, "attempts_total": len(attempts), "warmups": n_warm,
                   "measured_n": len(measured), "measured_target": n_meas,
                   "released": sum(1 for a in attempts if a["consume"]["decision"] == "RELEASED"),
                   "refused": sum(1 for a in attempts if a["consume"]["decision"] == REFUSED),
                   "errors": sum(1 for a in attempts if a["error"]),
                   "acceptance": {s: statuses.count(s) for s in ("MET", "WRONG", "NOT_REACHED")},
                   "hermetic_orchestration_ms": {"n": len(ms), "p50": _nearest_rank(ms, 0.5), "p95": _nearest_rank(ms, 0.95),
                                                 "max": max(ms) if ms else None, "sdk_elapsed_ms_median": _nearest_rank([a["receipt"]["elapsed_ms"] for a in measured
                                                                                         if isinstance(a["receipt"].get("elapsed_ms"), (int, float))], 0.5),
                                                 "note": "not request_to_consumer_ms: in-process oracle retrieval plus a subprocess emulation on one machine; "
                                                         "nearest-rank over measured attempts, warmups and the probe excluded; never shown on the card"},
                   "probe": {"decision": probe["consume"]["decision"], "bind": probe["bind"]["status"], "failed_checks": probe["bind"]["failed_checks"],
                             "sdk_invoked": probe["receipt"]["invoked"], "acceptance": probe["acceptance"]["status"]},
                   "state": "HERMETIC_COMPLETE" if all(s == "MET" for s in statuses) else "HERMETIC_INCOMPLETE",
                   "fills_cell": False,
                   "note": "a hermetic cell never fills the plan's cell: stopped_reason stays RUNNER_HERMETIC_ONLY on the card"}
        rec["cells"].append(summary)
        rec["attempts"].extend(attempts)
    statuses = [a["acceptance"]["status"] for a in rec["attempts"]]
    if any(s == "WRONG" for s in statuses):
        rec["verdict"] = RUNNER_BROKEN
    elif any(s == "NOT_REACHED" for s in statuses):
        rec["verdict"] = RUNNER_INCOMPLETE
    else:
        rec["verdict"] = RUNNER_OK
    rec["verdict_rule"] = (f"{RUNNER_OK} when every gate passed, every attempt was retained, every measured attempt is MET and the probe is MET; "
                           f"{RUNNER_INCOMPLETE} when any attempt is NOT_REACHED (a child that died, a stage exception); "
                           f"{RUNNER_BROKEN} when any is WRONG (a probe released, a measured attempt refused or released without its bindings)")
    rec["retained"] = True
    rec["finished_utc"] = _now()
    return _write(rec, out_dir, run_dir, redact)


def _claim(run_dir: Path) -> bool:
    """Atomic ownership of a run id: create its directory, fail if anyone already has."""
    try:
        run_dir.parent.mkdir(parents=True, exist_ok=True)
        run_dir.mkdir(exist_ok=False)
        return True
    except FileExistsError:
        return False


def _write(rec: dict, out_dir: Path, run_dir: Path, redact: Callable) -> dict:
    """Publish the record without ever overwriting: the bytes are staged inside the owned run directory and linked
    into place, which fails if a record with this id already exists (no other invocation can be finalised over)."""
    rec = redact(rec)
    final = out_dir / f"run_{rec['run_id']}.json"
    staged = run_dir / "run.json"
    staged.write_text(json.dumps(rec, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    os.link(staged, final)          # atomic create-or-fail; never os.replace onto another invocation's record
    return rec


# ----------------------------------------------------------------------------- command line
def describe(plan: dict, cells: list[str], run_id: str, gates: list[dict], evaluation_date: _dt.date) -> str:
    version = plan["facts"]["selected_version"]
    lines = [f"{RUNNER_VERSION}  run_id {run_id}  evaluation date {evaluation_date.isoformat()}",
             f"fact version: {plan['facts']['state']} {version['kind']}, content digest {version['content_manifest_sha256'][:12]}…, "
             f"valid on/after {version['valid_for_runs_on_or_after']}, expires {version['materialization_expires_utc'].split(' (')[0]}",
             f"question: {QUESTION_ID} = {SEED} -> {COMPUTATION_PATH}, parameters {JAN}, expected RELEASED",
             f"probe:    {PROBE_ID} = {MISMATCH_SEED} -> {MISMATCH_PATH}, expected REFUSED at bind, SDK never invoked",
             "cells:"]
    by_name = {c["name"]: c for c in plan["consumer_cells"]}
    for name in cells:
        c = by_name[name]
        lines.append(f"  {name}: C={c['concurrency']}, {c['warmups']} warmups + {c['measured']} measured + 1 probe, timeout {c['timeout_s']}s")
    lines.append("gates:")
    lines += [f"  {g['code']}: {g['status']} — {g['detail']}" for g in gates]
    budget = plan["budget"].get("consumer_sampling") or {}
    lines.append(f"consumer budget: {budget.get('state')} — {budget.get('consumer_max_bytes_billed_gib')} GiB / ${budget.get('consumer_max_usd')} / "
                 f"{budget.get('consumer_max_wall_seconds_per_cell')} s per cell / {budget.get('consumer_max_wall_seconds_total')} s total; hermetic spends nothing")
    lines.append("modes: --dry-run (nothing launched) | --hermetic (oracle graph + SDK emulation; no job, no cell filled). There is no live mode in this driver.")
    return "\n".join(lines)


def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(prog="python3 -m okf_bq_graph.consumer_run",
                                 description="Hermetic sampled request-to-consumer runner (FS-1). Dry-run and hermetic only; no live mode.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--dry-run", action="store_true", help="validate, run the subprocess-free gates, print the campaign; launch nothing")
    mode.add_argument("--hermetic", action="store_true", help="run the campaign with the oracle graph and the SDK example's hermetic runner")
    ap.add_argument("--cells", nargs="+", metavar="CELL", help="consumer cells (default: both); retrieval cells are refused")
    ap.add_argument("--plan", default=str(sb.PLAN), help="sql-baseline plan JSON (default: fixtures/sql_baseline.json)")
    ap.add_argument("--cases", default=str(CASES), help="pinned question set (default: fixtures/cases.json)")
    ap.add_argument("--out-dir", default=str(OUT_DIR), help="where run_<run_id>.json and <run_id>/ are retained")
    ap.add_argument("--run-id", help="run id (default: fresh consumer-hermetic-<utc>-<hex>); must be unused")
    ap.add_argument("--sdk-root", default=None, help="SDK receipt-spike checkout (default: OKF_SDK_ROOT or the pinned path)")
    ap.add_argument("--acme-root", default=None, help="pinned acme_retail bundle checkout")
    ap.add_argument("--as-of", default=None, help="as-of timestamp (UTC, ISO); its date is the evaluation date")
    return ap


def main(argv: Optional[list[str]] = None, stdout=None) -> int:
    out = stdout or sys.stdout
    args = build_parser().parse_args(argv)
    plan, plan_error = None, None
    try:
        plan = sb.load_plan(args.plan)
        if not isinstance(plan, dict):
            raise ValueError(f"the plan is not a JSON object ({type(plan).__name__})")
    except (OSError, ValueError) as e:
        plan_error = f"{type(e).__name__}: {str(e)[:300]} ({args.plan})"
    cells = args.cells or None       # None: the plan's consumer cells, derived after the plan validates
    as_of = args.as_of or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    evaluation_date = _dt.date.fromisoformat(as_of[:10])
    run_id = args.run_id or fresh_run_id()
    if args.dry_run:      # write-free: the gates run, nothing is claimed, nothing is retained
        try:
            gates = run_gates(plan, cells, run_id, args.out_dir, evaluation_date, args.cases, plan_error=plan_error)
        except Exception as e:  # noqa: BLE001
            gates = [_gate("PREFLIGHT_ERROR", False, f"{type(e).__name__}: {str(e)[:300]}")]
        refusal = _first_refusal(gates)
        if refusal is not None:
            print(f"REFUSED: {refusal['code']}: {refusal['detail']}", file=out)
            return 2
        cells = cells or [c["name"] for c in plan["consumer_cells"]]
        print(describe(plan, cells, run_id, gates, evaluation_date), file=out)
        print("dry run: nothing launched, no record retained", file=out)
        return 0
    # hermetic: every gate refusal is retained under a fresh owned record (Astra #5), except an id this invocation
    # cannot own, which retains nothing and leaves the owner's files alone
    rec = run_hermetic(plan, cells, out_dir=args.out_dir, sdk_root=args.sdk_root, acme_root=args.acme_root, as_of=as_of, run_id=run_id,
                       cases_path=args.cases, plan_error=plan_error)
    if rec["verdict"] == REFUSED:
        where = f" (retained {Path(args.out_dir) / ('run_' + rec['run_id'] + '.json')})" if rec.get("retained") else " (nothing retained: the id is not this invocation's)"
        print(f"REFUSED: {rec['refusal']['code']}: {rec['refusal']['detail']}{where}", file=out)
        return 2
    print(describe(plan, [c["cell"] for c in rec["cells"]], run_id, rec["gates"], evaluation_date), file=out)
    for c in rec["cells"]:
        print(f"  {c['cell']}: {c['state']} attempts={c['attempts_total']} released={c['released']} refused={c['refused']} "
              f"probe={c['probe']['decision']}@{c['probe']['bind']} concurrency_achieved={c['concurrency_achieved']}", file=out)
    print(f"{rec['verdict']}: retained {Path(args.out_dir) / ('run_' + rec['run_id'] + '.json')} (hermetic: no job, no cell filled)", file=out)
    return 0 if rec["verdict"] == RUNNER_OK else 1


if __name__ == "__main__":
    sys.exit(main())
