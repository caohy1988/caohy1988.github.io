"""Aggregate cells from evidence/requests.jsonl that never reached a summary row (driver interrupted).
They are written to evidence/summary.json with state INCOMPLETE and their actual sample size; never as COMPLETE."""
import json, os
from .benchmark import nearest_rank

recs = [json.loads(l) for l in open("evidence/requests.jsonl")]
summary = json.load(open("evidence/summary.json")) if os.path.exists("evidence/summary.json") else {"cells": []}
done = {c["cell"] for c in summary["cells"]}
spec = {c["name"]: c for c in json.load(open("fixtures/scale.json"))["cells"]}
for name in sorted({r["cell"] for r in recs} - done):
    rs = [r for r in recs if r["cell"] == name]
    measured = [r for r in rs if not r["warmup"]]
    allv = [r["total_ms"] for r in measured]
    ok = [r["total_ms"] for r in measured if r.get("ok")]
    stages = {}
    for r in measured:
        for k, v in (r.get("timing", {}).get("stages_ms") or {}).items():
            stages.setdefault(k, []).append(v)
    slot_ms = sum(j.get("slot_ms") or 0 for r in measured for j in (r.get("timing", {}).get("jobs") or []))
    summary["cells"].append({
        "cell": name, "engine": rs[0]["engine"], "corpus": rs[0]["corpus"], "concurrency": rs[0]["concurrency"],
        "publication_id": rs[0]["publication_id"], "warmups_done": sum(1 for r in rs if r["warmup"]),
        "measured_n": len(measured), "measured_target": spec.get(name, {}).get("measured", 100),
        "state": "INCOMPLETE" if measured else "NOT_RUN_BUDGET", "stopped_reason": "DRIVER_INTERRUPTED_COST_CONTROL",
        "success_rate": (len(ok) / len(measured)) if measured else None,
        "errors": sum(1 for r in measured if r["status"] == "ERROR"), "timeouts": sum(1 for r in measured if r.get("timeout")),
        "p50_ms_all": nearest_rank(allv, 50), "p95_ms_all": nearest_rank(allv, 95), "max_ms_all": max(allv) if allv else None,
        "p50_ms_ok": nearest_rank(ok, 50), "p95_ms_ok": nearest_rank(ok, 95),
        "stage_p50_ms": {k: nearest_rank(v, 50) for k, v in stages.items()},
        "stage_p95_ms": {k: nearest_rank(v, 95) for k, v in stages.items()},
        "slot_ms_total": slot_ms, "jobs_total": sum(len(r.get("timing", {}).get("jobs") or []) for r in measured),
        "slot_attribution_usd": round(slot_ms / 3_600_000 * 0.06, 6),
        "note": "INCOMPLETE: small sample, percentiles are nearest-rank over the attempts that ran; not a completed cell"})
for name, c in spec.items():
    if name not in {x["cell"] for x in summary["cells"]}:
        summary["cells"].append({"cell": name, "state": "NOT_RUN_BUDGET", "stopped_reason": "WINDOW_ENDED_BEFORE_CELL"})
json.dump(summary, open("evidence/summary.json", "w"), indent=2)
for c in summary["cells"]:
    print(c["cell"], c["state"], c.get("measured_n"), "p50", c.get("p50_ms_all"), "p95", c.get("p95_ms_all"), "ok", c.get("success_rate"))
