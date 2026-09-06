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
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any

from google.cloud import bigquery

from . import PROJECT, LOCATION, DATASET
from .retrieve import retrieve

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
        rec.update({"status": "ERROR", "error": f"{type(e).__name__}: {e}"[:500], "ok": False, "timeout": False,
                    "total_ms": round((time.monotonic() - rec["t0_monotonic"]) * 1000, 1)})
    rec["end"] = _now()
    _record(rec)
    return rec


def run_cell(cell: dict, queries: list[dict], clients_factory, budget: dict) -> dict:
    """cell: name, engine, corpus, publication_id, concurrency, warmups, measured, as_of, seed."""
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
    with ThreadPoolExecutor(max_workers=cell["concurrency"]) as ex:
        futures = {}
        i = 0
        while i < len(order) or futures:
            while i < len(order) and len(futures) < cell["concurrency"]:
                if time.monotonic() - started > budget["cell_seconds"]:
                    stopped_reason = "CELL_TIME_BUDGET"; i = len(order); break
                if budget.get("deadline_monotonic") and time.monotonic() > budget["deadline_monotonic"]:
                    stopped_reason = "WINDOW_DEADLINE"; i = len(order); break
                f = ex.submit(one_request, cell, i, order[i], clients_factory(), timeout_s)
                futures[f] = i; i += 1
            if not futures:
                break
            for f in as_completed(list(futures)):
                recs.append(f.result()); futures.pop(f); break
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
    complete = len(measured) >= n_target
    out = {"cell": cell["name"], "engine": cell["engine"], "corpus": cell["corpus"], "concurrency": cell["concurrency"],
           "publication_id": cell["publication_id"], "warmups_done": sum(1 for r in recs if r["warmup"]),
           "measured_n": len(measured), "measured_target": n_target,
           "state": "COMPLETE" if complete else ("INCOMPLETE" if measured else "NOT_RUN_BUDGET"),
           "stopped_reason": stopped_reason,
           "success_rate": (len(ok) / len(measured)) if measured else None,
           "errors": sum(1 for r in measured if r["status"] == "ERROR"), "timeouts": sum(1 for r in measured if r["timeout"]),
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
    for cell in config["cells"]:
        if config["budget"].get("deadline_monotonic") and time.monotonic() > config["budget"]["deadline_monotonic"]:
            results.append({"cell": cell["name"], "state": "NOT_RUN_BUDGET", "stopped_reason": "WINDOW_DEADLINE"})
            continue
        results.append(run_cell(cell, config["queries"], retrieval_client, config["budget"]))
        with open(SUMMARY, "w") as fh:
            json.dump({"updated_at": _now(), "cells": results}, fh, indent=2, default=str)
    return {"cells": results}
