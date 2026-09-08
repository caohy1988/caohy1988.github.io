"""Generate the explicit ownership decisions for the legacy window reconciliation.

`reconcile_window.classify` refuses to guess: a listed job with no positive signal tying it to the window is AMBIGUOUS
and blocks. What it leaves over on this project is not noise - it is three identifiable bodies of concurrent work plus
four operator probes - so each one is resolved here BY ID, with the reason and the platform evidence that settles it.
The output is committed as `legacy_window_decisions.json` so a reviewer reads the decisions themselves rather than
trusting this rule; re-run it against the same listing to reproduce the file.

    python3 bin/legacy_window_decisions.py <episode_listing.json> bin/legacy_window_decisions.json

`episode_listing.json` is a drained read-only `jobs.list` of the episode span (evidence/legacy-reconcile/ has the one
these decisions were derived from). Nothing here submits, cancels or deletes.
"""
import json
import sys
from pathlib import Path

WINDOWS = ["smoke-1", "integration-0007", "integration-0009", "all-0012", "all-0017"]
RECEIPT_DATASET = "okf_receipt_spike_20260905"
GRAPH_RESERVATION = "okf-graph-spike-20260905"

# The three operator probes that ran inside all-0017's recorded interval on the campaign reservation, carrying no
# campaign label and referencing no campaign dataset. They are that window's own assignment/capacity checks: they
# consumed its Enterprise capacity and belong in its inventory. For every OTHER window they are simply another
# window's job. `afbe7061` is the same capacity read taken at 00:01:16, when no window was open at all.
ALL_0017_PROBES = {
    "0de731e0-637a-4cb5-b764-9c7d2e82c08a":
        "the driver's own capacity read (`region-us`.INFORMATION_SCHEMA.RESERVATIONS_TIMELINE WHERE reservation_name "
        "= @r), created 00:21:17Z inside all-0017's recorded interval and routed to its Enterprise reservation",
    "bqjob_r74ce8f5679562b1c_000001a074165929_1":
        "`SELECT 1 AS x` submitted through the bq CLI at 00:20:17Z, inside all-0017's recorded interval and routed to "
        "its Enterprise reservation: the operator's assignment-readiness probe for that window",
    "bqjob_r79062b4a27c75a24_000001a07416d20d_1":
        "`SELECT 1` submitted through the bq CLI at 00:20:48Z, inside all-0017's recorded interval and routed to its "
        "Enterprise reservation: the operator's assignment-readiness probe for that window",
}
OUTSIDE_EVERY_INTERVAL = {
    "afbe7061-813a-439d-afb7-2c9efe06d2e7":
        "the same INFORMATION_SCHEMA.RESERVATIONS_TIMELINE capacity read, created 00:01:16Z when no window was open "
        "and routed to no reservation: a between-windows check, not a job of any paid opening",
}


def receipt_reason(job_id, reservation):
    base = (f"concurrent attested-computation receipt work, not graph-window work: the id is an `okf_rcpt_` "
            f"deterministic receipt reference, the job carries the `okf_request`/`requester` label namespace, and it "
            f"queries `{RECEIPT_DATASET}.orders` - a different spike's dataset on the same project")
    if reservation:
        base += (f". It reports the graph reservation because capacity deletion had not finished propagating: its "
                 f"immediate siblings in the same burst carry NO reservation, so the attribution is propagation lag "
                 f"rather than membership")
    return base


TRANSFER_REASON = (
    "a recurring BigQuery Data Transfer scheduled query owned by bqaa-otlp-consumer@, merging into "
    "`bqaa_hero_demo_20260708.agent_events_otlp`: a different principal, a different dataset and a schedule that runs "
    "before and after this episode. Where it reports the graph reservation, that is the window's own "
    "assignee_type=PROJECT job_type=QUERY assignment routing unrelated project traffic onto its Enterprise capacity - "
    "the transfer service owns the job, the window does not")


def main(listing_path, out_path):
    jobs = json.loads(Path(listing_path).read_text(encoding="utf-8"))
    decisions = {w: {} for w in WINDOWS}
    for job in jobs:
        ref = job.get("jobReference") or {}
        jid = ref.get("jobId") or ""
        cfg = job.get("configuration") or {}
        stats = job.get("statistics") or {}
        text = (cfg.get("query") or {}).get("query") or ""
        reservation = str(stats.get("reservation_id") or stats.get("reservationId") or "")
        evidence = {"created_ms": stats.get("creationTime"), "user_email": job.get("user_email"),
                    "labels": cfg.get("labels") or {}, "reservation_id": reservation or None}
        if jid.startswith("okf_rcpt_") or (RECEIPT_DATASET in text and not jid.startswith("okf_graph_")):
            for w in WINDOWS:
                decisions[w][jid] = {"ownership": "EXCLUDED",
                                     "reason": receipt_reason(jid, reservation.endswith(GRAPH_RESERVATION)),
                                     "evidence": evidence}
        elif jid.startswith("scheduled_query_"):
            for w in WINDOWS:
                decisions[w][jid] = {"ownership": "EXCLUDED", "reason": TRANSFER_REASON, "evidence": evidence}
        elif jid in ALL_0017_PROBES:
            for w in WINDOWS:
                decisions[w][jid] = ({"ownership": "OWNED", "reason": ALL_0017_PROBES[jid], "evidence": evidence}
                                     if w == "all-0017" else
                                     {"ownership": "EXCLUDED", "evidence": evidence,
                                      "reason": "created inside the recorded capacity interval of all-0017, which "
                                                "owns it: " + ALL_0017_PROBES[jid]})
        elif jid in OUTSIDE_EVERY_INTERVAL:
            for w in WINDOWS:
                decisions[w][jid] = {"ownership": "EXCLUDED", "reason": OUTSIDE_EVERY_INTERVAL[jid],
                                     "evidence": evidence}
    Path(out_path).write_text(json.dumps(decisions, indent=1, sort_keys=True) + "\n", encoding="utf-8")
    for w in WINDOWS:
        owned = sum(1 for d in decisions[w].values() if d["ownership"] == "OWNED")
        print(f"{w:20s} decisions={len(decisions[w]):3d} owned={owned} excluded={len(decisions[w]) - owned}")


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else "bin/legacy_window_decisions.json")
