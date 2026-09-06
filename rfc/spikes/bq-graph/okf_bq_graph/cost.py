"""Cost reconciliation (spec §6).

(1) slot_ms attribution per job, partitioned by the EXACT named Enterprise reservation vs other pools
    (e.g. default-pipeline) vs on-demand;
(2) charged autoscale slot-seconds from INFORMATION_SCHEMA.RESERVATIONS_TIMELINE.period_autoscale_slot_seconds
    (per-minute rows; the platform's charged quantity), plus baseline slot-seconds;
(3) on-demand bytes billed at list rate (free tier not applied).
Writes evidence/cost.json. Billing-export reconciliation is pending; everything here is provisional."""
from __future__ import annotations

import os
import subprocess
import sys
import json

from google.cloud import bigquery

from . import PROJECT, LOCATION, RESERVATION

RATE_ENTERPRISE_US = 0.06      # USD per slot-hour, SKU C0F6-38AB-6629 (evidence/sku_receipt.json)
RATE_ONDEMAND_TIB = 6.25       # USD per TiB, SKU 1DF5-1F98-1DD1 (list rate; 1 TiB/month free tier not applied)
NAMED = f"{PROJECT}:{LOCATION}.{RESERVATION}"


def operator_email() -> str:
    return os.environ.get("OKF_OPERATOR_EMAIL") or subprocess.run(
        ["gcloud", "config", "get-value", "account"], capture_output=True, text=True).stdout.strip()


def reconcile(client: bigquery.Client, since: str, until: str) -> dict:
    P = lambda k, t, v: bigquery.ScalarQueryParameter(k, t, v)
    jobs = [dict(r) for r in client.query(f"""
      SELECT job_id, creation_time, start_time, end_time, state, statement_type, reservation_id, edition,
             total_slot_ms, total_bytes_processed, total_bytes_billed, cache_hit, error_result.reason AS error_reason, labels
      FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
      WHERE creation_time BETWEEN @since AND @until AND user_email = @u
        AND (job_id LIKE 'okf_graph_%' OR EXISTS (SELECT 1 FROM UNNEST(labels) l WHERE l.key = 'okf_spike')
             OR reservation_id IS NOT NULL OR query LIKE '%okf_graph_spike_20260905%')
      ORDER BY creation_time""", job_config=bigquery.QueryJobConfig(query_parameters=[
          P("since", "TIMESTAMP", since), P("until", "TIMESTAMP", until), P("u", "STRING", operator_email())]),
      location=LOCATION).result()]
    timeline = [dict(r) for r in client.query(f"""
      SELECT period_start, reservation_name, slot_capacity, autoscale.current_slots AS autoscale_current_slots,
             autoscale.max_slots AS autoscale_max_slots, period_autoscale_slot_seconds, edition
      FROM `region-us`.INFORMATION_SCHEMA.RESERVATIONS_TIMELINE
      WHERE period_start BETWEEN @since AND @until AND reservation_name = @r
      ORDER BY period_start""", job_config=bigquery.QueryJobConfig(query_parameters=[
          P("since", "TIMESTAMP", since), P("until", "TIMESTAMP", until), P("r", "STRING", RESERVATION)]),
      location=LOCATION).result()]
    named = [j for j in jobs if j["reservation_id"] == NAMED]
    other_pool = [j for j in jobs if j["reservation_id"] and j["reservation_id"] != NAMED]
    od_jobs = [j for j in jobs if not j["reservation_id"]]
    slot_ms_named = sum(j["total_slot_ms"] or 0 for j in named)
    slot_ms_other = sum(j["total_slot_ms"] or 0 for j in other_pool)
    autoscale_slot_s = sum(r["period_autoscale_slot_seconds"] or 0 for r in timeline)
    baseline_slot_s = sum((r["slot_capacity"] or 0) * 60 for r in timeline)
    snapshot_slot_min = sum((r["autoscale_current_slots"] or 0) for r in timeline)
    od_bytes = sum(j["total_bytes_billed"] or 0 for j in od_jobs)
    last_tl = str(timeline[-1]["period_start"]) if timeline else None
    return {
        "window": {"since": since, "until": until}, "rate_usd_per_slot_hour": RATE_ENTERPRISE_US, "named_reservation": NAMED,
        "named_reservation_jobs": len(named), "other_pool_jobs": len(other_pool),
        "other_pools": sorted({j["reservation_id"] for j in other_pool}), "ondemand_jobs": len(od_jobs),
        "slot_ms_named": slot_ms_named, "slot_attribution_named_usd": round(slot_ms_named / 3_600_000 * RATE_ENTERPRISE_US, 4),
        "slot_ms_other_pool": slot_ms_other,
        "other_pool_note": "jobs routed to a non-Enterprise pool (e.g. default-pipeline DDL/load jobs); not billed at the Enterprise rate here",
        "timeline_minutes": len(timeline), "timeline_last_period_start": last_tl,
        "charged_autoscale_slot_seconds": autoscale_slot_s,
        "charged_autoscale_usd": round(autoscale_slot_s / 3600 * RATE_ENTERPRISE_US, 4),
        "baseline_slot_seconds": baseline_slot_s,
        "snapshot_slot_minutes_legacy": snapshot_slot_min,
        "ondemand_bytes_billed": od_bytes, "ondemand_list_usd": round(od_bytes / 2**40 * RATE_ONDEMAND_TIB, 4),
        "ondemand_note": "list rate; the 1 TiB/month on-demand free tier is not applied, so the invoice line is likely $0.00",
        "coverage_note": "timeline rows are per minute and may lag; compare timeline_last_period_start with window.until and with the "
                         "deletion time in evidence/reservation_changes.json before calling the window fully covered",
        "note": "slot attribution is a resource-use estimate, not the invoice; charged_autoscale_usd uses the platform's charged "
                "autoscale slot-seconds (1-minute minimum, multiples of 50); the two are not added; billing export reconciliation pending",
        "timeline": timeline, "jobs": jobs,
    }


if __name__ == "__main__":
    since, until = sys.argv[1], sys.argv[2]
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    o = reconcile(client, since, until)
    with open("evidence/cost.json", "w") as fh:
        json.dump(o, fh, indent=1, default=str)
    print(json.dumps({k: v for k, v in o.items() if k not in ("timeline", "jobs")}, indent=1))
    for r in o["timeline"]:
        print(r["period_start"], "baseline", r["slot_capacity"], "autoscale_cur", r["autoscale_current_slots"], "charged_autoscale_s", r["period_autoscale_slot_seconds"])
