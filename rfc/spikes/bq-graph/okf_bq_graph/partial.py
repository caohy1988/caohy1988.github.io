"""Refresh unfinished benchmark summaries from immutable requests, separated by run.

Recovery never promotes a cell to COMPLETE: that requires the driver summary. Old
records without run_id form one legacy run; ambiguous repeated request IDs fail
before writing anything instead of silently pooling independent runs.
"""
from __future__ import annotations

from collections import defaultdict
import json
from pathlib import Path

from .benchmark import nearest_rank

LEGACY_RUN_ID = "legacy-unlabeled"


def _key(row):
    return row["cell"], row.get("run_id") or LEGACY_RUN_ID


def _unfinished(name, run_id, records, previous, spec):
    measured = [r for r in records if not r["warmup"]]
    if len(measured) < previous.get("measured_n", 0):
        raise ValueError(f"{name}/{run_id}: raw records do not cover the unfinished summary")
    allv = [r["total_ms"] for r in measured]
    ok = [r["total_ms"] for r in measured if r.get("ok")]
    stages = defaultdict(list)
    jobs = [j for r in measured for j in (r.get("timing", {}).get("jobs") or [])]
    for r in measured:
        for stage, value in (r.get("timing", {}).get("stages_ms") or {}).items():
            stages[stage].append(value)
    slot_ms = sum(j.get("slot_ms") or 0 for j in jobs)
    metadata = dict(spec, **previous)
    if records:
        for field in ("engine", "corpus", "concurrency", "publication_id"):
            if metadata.get(field) is None:
                metadata[field] = records[0].get(field)
    reason = previous.get("stopped_reason")
    if records and reason in (None, "WINDOW_ENDED_BEFORE_CELL"):
        reason = "DRIVER_INTERRUPTED_COST_CONTROL"
    row = dict(previous)
    # A refreshed partial has no trustworthy wall-clock completion boundary.
    row.pop("wall_seconds", None)
    row.pop("throughput_rps", None)
    row.update({
        "cell": name, "run_id": run_id, "engine": metadata.get("engine", "gql"),
        "corpus": metadata.get("corpus"), "concurrency": metadata.get("concurrency"),
        "publication_id": metadata.get("publication_id"),
        "warmups_done": sum(1 for r in records if r["warmup"]),
        "warmups_target": metadata.get("warmups_target", spec.get("warmups", 20)),
        "measured_n": len(measured), "measured_target": metadata.get("measured_target", spec.get("measured", 100)),
        "state": "INCOMPLETE" if measured else "NOT_RUN_BUDGET",
        "stopped_reason": reason or "WINDOW_ENDED_BEFORE_CELL",
        "success_rate": len(ok) / len(measured) if measured else None,
        "errors": sum(1 for r in measured if r["status"] == "ERROR"),
        "timeouts": sum(1 for r in measured if r.get("timeout")),
        "p50_ms_all": nearest_rank(allv, 50), "p95_ms_all": nearest_rank(allv, 95), "max_ms_all": max(allv) if allv else None,
        "p50_ms_ok": nearest_rank(ok, 50), "p95_ms_ok": nearest_rank(ok, 95),
        "stage_p50_ms": {k: nearest_rank(v, 50) for k, v in stages.items()},
        "stage_p95_ms": {k: nearest_rank(v, 95) for k, v in stages.items()},
        "slot_ms_total": slot_ms, "jobs_total": len(jobs),
        "slot_attribution_usd": round(slot_ms / 3_600_000 * 0.06, 6),
        "note": ("INCOMPLETE: percentiles are nearest-rank over retained attempts; no completed driver summary"
                 if measured else "No measured attempts; percentiles unavailable; retained warmups are counted separately"),
    })
    return row


def aggregate(recs: list[dict], summary: dict, spec: dict) -> dict:
    """Return a refreshed summary; spec maps configured cell names to metadata."""
    grouped = defaultdict(list)
    seen = set()
    for r in recs:
        key = _key(r)
        request_id = r.get("request_id")
        if not request_id or (*key, request_id) in seen:
            raise ValueError(f"{key}: missing/duplicate request_id; repeated runs require distinct run_id values")
        seen.add((*key, request_id))
        grouped[key].append(r)
    existing = {}
    for row in summary.get("cells", []):
        key = _key(row)
        if key in existing:
            raise ValueError(f"{key}: duplicate summary; repeated cells require distinct run_id values")
        existing[key] = row
    keys = dict.fromkeys([*existing, *grouped])
    run_ids = dict.fromkeys(run_id for _, run_id in keys) or {LEGACY_RUN_ID: None}
    for run_id in run_ids:
        for name in spec:
            keys.setdefault((name, run_id), None)
    cells = []
    for name, run_id in keys:
        previous = existing.get((name, run_id), {})
        if previous.get("state") == "COMPLETE":
            cells.append(dict(previous))
        else:
            cells.append(_unfinished(name, run_id, grouped[(name, run_id)], previous, spec.get(name, {})))
    return dict(summary, cells=cells)


def main():
    requests = Path("evidence/requests.jsonl")
    recs = [json.loads(line) for line in requests.read_text().splitlines() if line.strip()] if requests.exists() else []
    path = Path("evidence/summary.json")
    summary = json.loads(path.read_text()) if path.exists() else {"cells": []}
    spec = {c["name"]: c for c in json.loads(Path("fixtures/scale.json").read_text())["cells"]}
    summary = aggregate(recs, summary, spec)
    path.write_text(json.dumps(summary, indent=2) + "\n")
    for c in summary["cells"]:
        print(c["cell"], c.get("run_id", LEGACY_RUN_ID), c["state"], c.get("measured_n"),
              "p50", c.get("p50_ms_all"), "p95", c.get("p95_ms_all"), "ok", c.get("success_rate"))


if __name__ == "__main__":
    main()
