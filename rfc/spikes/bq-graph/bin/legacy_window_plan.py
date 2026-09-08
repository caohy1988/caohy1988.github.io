"""Build the read-only reconciliation plan for the five legacy openings (post-PR47).

Read-only and offline: this only reads committed evidence and writes a plan file. The plan is then executed with

    python3 -m okf_bq_graph.reconcile_window --plan <plan> --stage-dir <dir> --live

which issues `jobs.list` / `jobs.get` and nothing else. Every constant below is evidence, not preference:

  * CAMPAIGN is how the 2026-09-05 spike driver marks its own work - `configuration.labels.okf_spike` and its dataset.
    It establishes CAMPAIGN membership only; which window a job belongs to is decided by the recorded capacity
    interval in `reconcile_window.classify`, with every other declared opening checked for exclusivity.
  * LOCAL_RECORDS name the retained artifact that shows each submitter stopped. Two of the five retained no stop
    timestamp; those say so (`stopped_at: None`) and the gap is carried into the receipt rather than filled in.
  * DECISIONS resolve, one job at a time and with its reason, the references the automatic signals leave AMBIGUOUS.

    python3 bin/legacy_window_plan.py /tmp/stage/plan.json
"""
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
from okf_bq_graph.reconcile_window import build_plan                              # noqa: E402

EVIDENCE = ROOT / "evidence"

# All six datasets the 2026-09-05 spike created, not just the base one: the scale harness loads into `_x100`/`_x1000`
# and a LOAD job carries no query text, so a base-dataset-only campaign silently left every seed load unattributable.
CAMPAIGN = {"label_key": "okf_spike", "label_value": "bq_graph_20260905",
            "datasets": ["okf_graph_spike_20260905", "okf_graph_spike_20260905_rls", "okf_graph_spike_20260905_meta",
                         "okf_graph_spike_20260905_av", "okf_graph_spike_20260905_x100",
                         "okf_graph_spike_20260905_x1000"]}

# The retained per-run driver evidence, per opening. `integration-0009` has none: its driver was killed by session
# teardown before it wrote one, which is exactly why that window has no job ids to recover.
RECOVER_FROM = {
    "smoke-1": ["smoke_enterprise.job.json", "smoke_enterprise.jobids"],
    "integration-0007": ["integration_integration-0007.json"],
    "integration-0009": [],
    "all-0012": ["all_all-0012.json"],
    "all-0017": ["all_all-0017.json"],
}

# Frozen (hashed) alongside every window: the shared record the reconstruction rests on.
EXTRA_SOURCES = ["cost.json", "reservation_changes.json", "capacity-gate.md", "safety_teardown.log",
                 "integration_run.log", "integration_run_attempt2_killed.log", "window_all.log"]

LOCAL_RECORDS = {
    "smoke-1": {
        "source": "evidence/smoke_enterprise.out + cleanup_manifest.json[smoke-1].steps",
        "stopped_at": "2026-09-05T23:46:30Z",
        "note": "the only submitter was one foreground `bq query`; its retained output waits to DONE and returns, and "
                "the same session's next recorded manifest step (ls --reservation_assignment) is stamped 23:46:30Z, "
                "so the submitting process had returned by then"},
    "integration-0007": {
        "source": "evidence/integration_integration-0007.json#/finished_at",
        "stopped_at": "2026-09-06T00:09:09.727229+00:00",
        "note": "the driver wrote its own run record and exited"},
    "integration-0009": {
        "source": "cleanup_manifest.json[integration-0009].note + evidence/integration_run_attempt2_killed.log",
        "stopped_at": None,
        "note": "RETAINED GAP: the driver was killed by session teardown and no kill timestamp was recorded. No run "
                "record was written. The independent safety watcher deleted the reservation at 00:11:10Z. The stop "
                "moment therefore rests on the platform probe, not on a local stamp"},
    "all-0012": {
        "source": "evidence/all_all-0012.json#/finished_at",
        "stopped_at": "2026-09-06T00:15:55.901536+00:00",
        "note": "the driver wrote its own run record and exited"},
    "all-0017": {
        "source": "cleanup_manifest.json[all-0017].note + evidence/window_all.log + evidence/safety_teardown.log",
        "stopped_at": None,
        "note": "RETAINED GAP: the driver was interrupted (SIGINT 00:24:54Z) and its run record has finished_at: null, "
                "so it never stamped its own exit. SIGINT is when the signal was sent, not when submission stopped, "
                "and is deliberately not used as the stop moment"},
}

DECISIONS = json.loads((Path(__file__).resolve().parent / "legacy_window_decisions.json").read_text(encoding="utf-8"))

if __name__ == "__main__":
    out = Path(sys.argv[1] if len(sys.argv) > 1 else "/tmp/okf-post47/stage/plan.json")
    out.parent.mkdir(parents=True, exist_ok=True)
    plan = build_plan(EVIDENCE / "cleanup_manifest.json", evidence_dir=EVIDENCE, campaign=CAMPAIGN,
                      recover_from=RECOVER_FROM, decisions=DECISIONS, local_records=LOCAL_RECORDS,
                      extra_sources=EXTRA_SOURCES, min_silence_s=3600)
    out.write_text(json.dumps(plan, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for w in plan["windows"]:
        print(f"{w['label']:20s} recovered={len(w['recovered']):3d} sources={len(w['sources'])} "
              f"decisions={len(w['decisions'])}")
    print(f"declared: {[d['label'] for d in plan['declared']]}\nwrote {out}")
