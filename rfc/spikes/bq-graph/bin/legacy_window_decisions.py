"""Generate the explicit ownership decisions for the legacy window reconciliation.

`reconcile_window.classify` refuses to guess: a listed job with no positive signal tying it to the window is AMBIGUOUS
and blocks. What it leaves over on this project is not noise - it is three identifiable bodies of concurrent work plus
four operator probes - so each one is resolved here BY ID, with the reason and the platform evidence that settles it.
The output is committed as `legacy_window_decisions.json` so a reviewer reads the decisions themselves rather than
trusting this rule; re-run it against the same listing to reproduce the file.

    python3 bin/legacy_window_decisions.py <episode_listing.json> bin/legacy_window_decisions.json

The listing is a drained read-only `jobs.list` of the episode span. Either form works: a bare array of job resources,
or the committed `evidence/legacy-reconcile/episode_listing_index.json` envelope (an object whose `jobs` array holds
them). Nothing here submits, cancels or deletes.

    python3 bin/legacy_window_decisions.py evidence/legacy-reconcile/episode_listing_index.json \
        bin/legacy_window_decisions.json
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
# The retained pre-open publication-pointer lookups. `run.py@b6e4f09` resolves this pointer at L252, BEFORE it stamps
# `started_at` (L254) and before `open_window` (L265), so an invocation's first job precedes its own recorded opening.
# Both of these are the identical `active_publication` lookup landing under a second before an opening, and both come
# long after the PREVIOUS invocation stamped `finished_at`. They are the following window's setup, and HEAD dropped
# them (Astra PR50 P1). Assigned by id, to one window each.
PRE_OPEN_SETUP = {
    "fccaf7f9-eae1-4be1-9738-f304aa1933bb": (
        "integration-0009",
        "the invocation's publication-pointer lookup (`SELECT publication_id FROM …active_publication`) at "
        "00:09:56.310Z, 0.69s before integration-0009's recorded opening at 00:09:57Z. `run.py@b6e4f09:252` resolves "
        "this pointer before `started_at` (L254) and `open_window` (L265), so it precedes the window it belongs to; "
        "the previous invocation (integration-0007) had already stamped finished_at at 00:09:09.727Z, 46s earlier"),
    "8526efa6-c55c-4488-a050-421d3eb580b4": (
        "all-0017",
        "the same publication-pointer lookup at 00:17:55.499Z, 0.50s before all-0017's recorded opening at "
        "00:17:56Z and 0.73s before its retained started_at of 00:17:56.230721Z. `run.py@b6e4f09:252` resolves the "
        "pointer before `started_at`/`open_window`; the previous invocation (all-0012) stamped finished_at at "
        "00:15:55.901Z, 120s earlier"),
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


def listing_jobs(raw):
    """Accept either a bare list of job resources or the committed `episode_listing_index.json` envelope.

    The committed index is an object - completeness verdict, span, `full_listing_sha256`, then `jobs` - so pointing
    this script at the retained evidence used to die with `AttributeError: 'str' object has no attribute 'get'`
    (Astra PR50 P2). The retained format is the one a reviewer actually has, so it is the one that must work."""
    if isinstance(raw, dict):
        jobs = raw.get("jobs")
        if not isinstance(jobs, list):
            raise SystemExit(f"listing object has no `jobs` array (keys: {sorted(raw)})")
        return jobs
    if isinstance(raw, list):
        return raw
    raise SystemExit(f"listing must be a job array or an object containing one, not {type(raw).__name__}")


def main(listing_path, out_path):
    jobs = listing_jobs(json.loads(Path(listing_path).read_text(encoding="utf-8")))
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
        elif jid in PRE_OPEN_SETUP:
            owner, why = PRE_OPEN_SETUP[jid]
            for w in WINDOWS:
                decisions[w][jid] = ({"ownership": "OWNED", "reason": why, "evidence": evidence} if w == owner else
                                     {"ownership": "EXCLUDED", "evidence": evidence,
                                      "reason": f"setup of the {owner} invocation, which owns it: " + why})
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
