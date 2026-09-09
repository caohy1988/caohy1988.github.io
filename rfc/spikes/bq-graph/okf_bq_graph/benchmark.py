"""Bounded benchmark runner (spec §6, Task 6).

Every attempt is appended to evidence/requests.jsonl BEFORE aggregation. Percentiles are
nearest-rank over ALL attempts (errors/timeouts count as failures, never dropped).
Cells stop at the budget/time threshold; uncompleted cells are NOT_RUN_BUDGET / INCOMPLETE.
"""
from __future__ import annotations

import datetime as _dt
import json
import math
import os
import random
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, wait, FIRST_COMPLETED
from pathlib import Path
from typing import Any

from google.cloud import bigquery

from . import PROJECT, LOCATION, DATASET
from .lifecycle import WindowStopped
from .retrieve import retrieve, BudgetExhausted, RoutingViolation

REQUESTS = "evidence/requests.jsonl"
SUMMARY = "evidence/summary.json"
_lock = threading.Lock()


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def nearest_rank(values: list[float], p: float) -> float | None:
    if not values:
        return None
    s = sorted(values)
    k = max(1, math.ceil(p / 100 * len(s)))
    return s[k - 1]


def _record(rec: dict) -> None:
    with _lock:
        with open(REQUESTS, "a") as fh:
            fh.write(json.dumps(rec, default=str) + "\n")


def one_request(cell: dict, i: int, q: dict, clients: dict, timeout_s: float) -> dict:
    clients = dict(clients, ds=cell.get("ds", DATASET))
    rec: dict[str, Any] = {"cell": cell["name"], "engine": cell["engine"], "corpus": cell["corpus"], "ds": clients["ds"],
                           "run_id": cell["run_id"],
                           "bundle_id": q["bundle_id"], "publication_id": q.get("publication_id", cell["publication_id"]),
                           "concurrency": cell["concurrency"], "request_id": f"{cell['name']}-{i:04d}",
                           "query_id": q["id"], "query": q["text"], "warmup": i < cell["warmups"],
                           "start": _now(), "t0_monotonic": time.monotonic(), "model": cell.get("model"),
                           "cache": clients.get("use_cache", False)}
    try:
        r = retrieve(q["text"], q["bundle_id"], q.get("publication_id", cell["publication_id"]), "benchmark", cell["as_of"], clients,
                     top_k=cell.get("top_k", 5))
        rec.update({"status": r["status"], "timing": r["timing"], "n_concepts": len(r["concepts"]),
                    "n_computations": len(r["computations"]), "hops": [p["concept_hops"] for p in r["paths"]],
                    "error": None})
        rec["total_ms"] = r["timing"]["total_ms"]
        rec["ok"] = r["status"] == "OK" and rec["total_ms"] <= timeout_s * 1000
        rec["timeout"] = rec["total_ms"] > timeout_s * 1000
    except Exception as e:  # noqa: BLE001 - every failure is retained as data
        # A request cut by the caller's own gates is retained under its gate's name, not as an engine error: it is a
        # failure for the percentiles (never dropped) and a stop signal for the cell, not evidence about the engine.
        status = ("STOPPED" if isinstance(e, WindowStopped) else "BUDGET_EXHAUSTED" if isinstance(e, BudgetExhausted)
                  else "ROUTING_VIOLATION" if isinstance(e, RoutingViolation) else "ERROR")
        rec.update({"status": status, "error": f"{type(e).__name__}: {e}"[:500], "ok": False, "timeout": False,
                    "total_ms": round((time.monotonic() - rec["t0_monotonic"]) * 1000, 1)})
        if getattr(e, "okf_timing", None):
            rec["timing"] = e.okf_timing      # the jobs submitted before the cut, with their SUBMITTED / FAILED states
    rec["end"] = _now()
    _record(rec)
    return rec


def run_cell(cell: dict, queries: list[dict], clients_factory, budget: dict) -> dict:
    """cell: name, engine, corpus, publication_id, concurrency, warmups, measured, as_of, seed.

    A cell may carry its own `queries` list (the SQL-baseline driver passes one shape per cell so forced
    seeds and natural questions are never pooled); otherwise the config-wide list is sampled.
    `budget["deadline_reason"]` labels a total-budget stop; it defaults to WINDOW_DEADLINE for the
    reservation-window runner, which is the only caller that existed before the baseline driver.

    Two more optional budget hooks, both added for the on-demand baseline driver and unused by the window runner:

    * `budget["window_for_cell"](cell, started_monotonic)` returns a `lifecycle.WindowJobs` gate for THIS cell,
      with its deadline at the earlier of the cell budget and the total deadline. Every job the cell submits goes
      through that gate, so submission, result polling and row pagination all stop at the deadline instead of
      only the admission of the next request. The gate is sealed (`stop_and_cancel`) when the cell ends.
    * `budget["stop_check"]()` returns a reason string when a caller-side ceiling (billed bytes, USD, routing) is
      reached. It is consulted before every admission and after every completed request; a reason stops the cell.

    A cell that stopped for any reason is INCOMPLETE even when its last retained attempt was the n-th one: the
    stop rule says a cell that reaches a ceiling is recorded INCOMPLETE with its attempts retained.
    """
    cell = dict(cell, run_id=cell.get("run_id") or uuid.uuid4().hex)
    queries = cell.get("queries") or queries
    deadline_reason = budget.get("deadline_reason", "WINDOW_DEADLINE")
    stop_check = budget.get("stop_check")
    rng = random.Random(cell["seed"])
    order = []
    for _ in range(cell["warmups"] + cell["measured"]):
        q = dict(rng.choice(queries))
        if cell.get("bundles"):                      # scale cells: pick a random tenant copy
            b, p = rng.choice(cell["bundles"])
            q["bundle_id"], q["publication_id"] = b, p
        order.append(q)
    timeout_s = cell.get("timeout_s", 60)
    started = time.monotonic()
    recs: list[dict] = []
    stopped_reason = None
    window = budget.get("window")
    owned = None
    if budget.get("window_for_cell"):
        window = owned = budget["window_for_cell"](cell, started)

    def _past_total() -> bool:
        return bool(budget.get("deadline_monotonic")) and time.monotonic() >= budget["deadline_monotonic"]

    def _gate_label() -> str:
        # A per-cell gate stops for the cell budget or the total deadline; the window runner's gate is its window.
        if owned is None:
            return "WINDOW_DEADLINE"
        return deadline_reason if _past_total() else "CELL_TIME_BUDGET"

    ex = ThreadPoolExecutor(max_workers=cell["concurrency"])
    futures = {}
    try:
        i = 0
        while i < len(order) or futures:
            reason = stop_check() if stop_check else None
            if reason and not stopped_reason:
                stopped_reason = reason
                i = len(order)
                if window:
                    window.stop_and_cancel()  # in-flight jobs are past the ceiling too
            if window and (window.stop.is_set() or time.monotonic() >= window.deadline):
                stopped_reason = stopped_reason or _gate_label()
                i = len(order)
                window.stop_and_cancel()  # before waiting for active executor workers
            while i < len(order) and len(futures) < cell["concurrency"]:
                if time.monotonic() - started > budget["cell_seconds"]:
                    stopped_reason = "CELL_TIME_BUDGET"; i = len(order); break
                if _past_total():
                    stopped_reason = deadline_reason; i = len(order); break
                f = ex.submit(one_request, cell, i, order[i], clients_factory(), timeout_s)
                futures[f] = i; i += 1
            if not futures:
                break
            done, _ = wait(futures, timeout=.25, return_when=FIRST_COMPLETED)
            for f in done:
                recs.append(f.result()); futures.pop(f)
    except BaseException:
        if window:
            window.stop_and_cancel()
        raise
    finally:
        ex.shutdown(wait=True, cancel_futures=True)
        # A gate that tripped on the LAST admitted request is seen here, not at the loop top: the loop exits once every
        # request is admitted and collected, so without this check a cell whose final attempt was cut by its deadline
        # or by a ceiling read COMPLETE with stopped_reason null (Astra PR55 #2 repro).
        if stopped_reason is None and owned is not None and (owned.stop.is_set() or time.monotonic() >= owned.deadline):
            stopped_reason = _gate_label()
        if stopped_reason is None and stop_check:
            stopped_reason = stop_check()
        if owned is not None:
            owned.stop_and_cancel()   # seal the cell's gate; with every job finished this cancels nothing
    measured = [r for r in recs if not r["warmup"]]
    ok = [r["total_ms"] for r in measured if r["ok"]]
    allv = [r["total_ms"] for r in measured]
    stages: dict[str, list[float]] = {}
    for r in measured:
        for k, v in (r.get("timing", {}).get("stages_ms") or {}).items():
            stages.setdefault(k, []).append(v)
    slot_ms = sum(j.get("slot_ms") or 0 for r in measured for j in (r.get("timing", {}).get("jobs") or []))
    jobs_n = sum(len(r.get("timing", {}).get("jobs") or []) for r in measured)
    n_target = cell["measured"]
    complete = len(measured) >= n_target and stopped_reason is None
    out = {"cell": cell["name"], "engine": cell["engine"], "corpus": cell["corpus"], "concurrency": cell["concurrency"],
           "run_id": cell["run_id"],
           "publication_id": cell["publication_id"], "warmups_done": sum(1 for r in recs if r["warmup"]),
           "measured_n": len(measured), "measured_target": n_target,
           "state": "COMPLETE" if complete else ("INCOMPLETE" if measured else "NOT_RUN_BUDGET"),
           "stopped_reason": stopped_reason,
           "success_rate": (len(ok) / len(measured)) if measured else None,
           "errors": sum(1 for r in measured if r["status"] == "ERROR"), "timeouts": sum(1 for r in measured if r["timeout"]),
           "gated": sum(1 for r in measured if r["status"] in ("STOPPED", "BUDGET_EXHAUSTED", "ROUTING_VIOLATION")),
           "p50_ms_all": nearest_rank(allv, 50), "p95_ms_all": nearest_rank(allv, 95), "max_ms_all": max(allv) if allv else None,
           "p50_ms_ok": nearest_rank(ok, 50), "p95_ms_ok": nearest_rank(ok, 95),
           "stage_p50_ms": {k: nearest_rank(v, 50) for k, v in stages.items()},
           "stage_p95_ms": {k: nearest_rank(v, 95) for k, v in stages.items()},
           "wall_seconds": round(time.monotonic() - started, 1),
           "throughput_rps": round(len(measured) / max(1e-9, (time.monotonic() - started)), 3) if measured else None,
           "slot_ms_total": slot_ms, "jobs_total": jobs_n,
           "slot_attribution_usd": round(slot_ms / 3_600_000 * 0.06, 6),
           "note": "percentiles are nearest-rank; *_all include failures/timeouts; slot attribution is not the invoice"}
    return out


def measure(config: dict, retrieval_client) -> dict:
    """config: {cells:[...], queries:[...], budget:{cell_seconds, deadline_monotonic}}.
    retrieval_client: callable -> clients dict for one request (thread-local BigQuery client)."""
    results = []
    run_id = config.get("run_id") or uuid.uuid4().hex
    path = Path(SUMMARY)
    try:
        previous = json.loads(path.read_text())
    except FileNotFoundError:
        previous = {"cells": []}
    if any(c.get("run_id") == run_id for c in previous["cells"]):
        raise ValueError(f"run_id {run_id!r} already has a summary; a new measurement requires a new run_id")
    stop_check = config["budget"].get("stop_check")
    for spec in config["cells"]:
        cell = dict(spec, run_id=run_id)
        not_run = None
        if config["budget"].get("deadline_monotonic") and time.monotonic() >= config["budget"]["deadline_monotonic"]:
            not_run = config["budget"].get("deadline_reason", "WINDOW_DEADLINE")
        elif stop_check:
            not_run = stop_check()
        if not_run:
            results.append({"cell": cell["name"], "run_id": run_id, "engine": cell["engine"], "corpus": cell["corpus"],
                            "concurrency": cell["concurrency"], "publication_id": cell["publication_id"],
                            "measured_target": cell["measured"], "measured_n": 0, "warmups_done": 0,
                            "state": "NOT_RUN_BUDGET",
                            "stopped_reason": not_run,
                            "success_rate": None, "errors": 0, "timeouts": 0,
                            "p50_ms_all": None, "p95_ms_all": None, "max_ms_all": None,
                            "p50_ms_ok": None, "p95_ms_ok": None, "stage_p50_ms": {}, "stage_p95_ms": {},
                            "jobs_total": 0, "slot_ms_total": 0, "slot_attribution_usd": 0})
        else:
            results.append(run_cell(cell, config["queries"], retrieval_client, config["budget"]))
        temporary = path.with_suffix(".tmp")
        temporary.write_text(json.dumps(dict(previous, updated_at=_now(), cells=previous["cells"] + results),
                                        indent=2, default=str) + "\n")
        os.replace(temporary, path)
    return {"cells": results}
