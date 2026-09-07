"""Follow-up job-identity audit for a retained B2 run (Astra PR42 P1).

Read-only. Rebuilds the EXACT job set from the committed evidence (driver journal + every child chain record,
including the early-refusal chains whose jobs appear only in their own journal), reads each one back from BigQuery
under its own (project, location, job id), and applies the same `identity_gate` the driver applies in-run.
`jobs.get` submits no job, so this cannot change the set it audits.
"""
import json, sys
from pathlib import Path

sys.path.insert(0, "/Users/haiyuancao/caohy1988.github.io-catalog-live/rfc/spikes/bq-graph")
from google.cloud import bigquery
from okf_bq_graph import LOCATION, PROJECT
from okf_bq_graph.authz import redact
from okf_bq_graph.catalog_live import B2Experiment, LiveCloud, identity_gate, _jsonable, _now

root = Path(sys.argv[1])
rows = [{"source": "lifecycle", "leg": "lifecycle", "role": e.get("role"), "job_id": e["job_id"],
         "project": e.get("project"), "location": e.get("location"), "journal_state": e.get("state"),
         "dispatched": e.get("state") != "NOT_SUBMITTED"}
        for e in (json.loads(l) for l in (root / "journal.jsonl").read_text().splitlines())
        if e.get("job_id") and e.get("event") == "terminal"]
unresolved = []
for d in sorted((root / "chains").iterdir()):
    rec = json.loads((d / "chain_live.json").read_text())
    rows.extend(B2Experiment._chain_job_refs(d.name, rec))
    unresolved.extend((rec.get("job_inventory") or {}).get("unresolved") or [])

cloud = LiveCloud(bigquery.Client(project=PROJECT, location=LOCATION))
out = []
for r in rows:
    rec = dict(r)
    try:
        st = cloud.job_state(r["job_id"], timeout=30.0, project=r.get("project"), location=r.get("location"))
        rec.update(read="OK", state=st.get("state"), user_email=st.get("user_email"), error=_jsonable(st.get("error"))) if st \
            else rec.update(read="NOT_FOUND", state=None, user_email=None, error=None)
    except Exception as e:                                        # noqa: BLE001 - unreadable leaves the gate incomplete
        rec.update(read="ERROR", state=None, user_email=None, error=f"{type(e).__name__}: {str(e)[:200]}")
    out.append(rec)

by_chain = {d.name: identity_gate([j for j in out if j["source"] == f"chain:{d.name}"], []) for d in sorted((root / "chains").iterdir())}
audit = {"kind": "follow-up job-identity audit (read-only jobs.get over the exact retained job set)",
         "run_id": root.name, "at": _now(), "audited_by": "okf_bq_graph.catalog_live/0.2.0 identity_gate",
         "overall": identity_gate(out, unresolved), "lifecycle": identity_gate([j for j in out if j["source"] == "lifecycle"], []),
         "by_chain": by_chain,
         "counts": {"lifecycle_bigquery_jobs": len([j for j in out if j["source"] == "lifecycle"]),
                    "chain_jobs": len([j for j in out if j["source"] != "lifecycle"]), "total_jobs": len(out)},
         "jobs": out}
(root / "job_identity_followup.json").write_text(json.dumps(redact(_jsonable(audit)), indent=1, sort_keys=True, default=str) + "\n")
print(json.dumps({"total": len(out), "overall": audit["overall"]["status"], "principals": audit["overall"]["principals"],
                  "reasons": audit["overall"]["reasons"], "counts": audit["counts"],
                  "by_chain": {k: (v["status"], v["jobs"]) for k, v in by_chain.items()}}, indent=1))
