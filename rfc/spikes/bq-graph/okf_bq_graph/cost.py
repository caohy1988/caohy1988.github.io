"""Cost reconciliation (spec §6): (1) slot_ms attribution per job, (2) allocated-capacity bill over the
reservation window from INFORMATION_SCHEMA.RESERVATIONS_TIMELINE (autoscaled slots per minute), plus
on-demand bytes billed for fallback/publication jobs. Writes evidence/cost.json. Billing export lag noted."""
from __future__ import annotations

import datetime as _dt
import json
import sys

from google.cloud import bigquery

from . import PROJECT, LOCATION, RESERVATION

RATE_ENTERPRISE_US = 0.06      # USD per slot-hour, SKU C0F6-38AB-6629 (read 2026-09-05)
RATE_ONDEMAND_TIB = 6.25       # USD per TiB, SKU 1DF5-1F98-1DD1


def reconcile(client: bigquery.Client, since: str, until: str) -> dict:
    P = lambda k, t, v: bigquery.ScalarQueryParameter(k, t, v)
    jobs = [dict(r) for r in client.query(f"""
      SELECT job_id, creation_time, start_time, end_time, state, statement_type, reservation_id, edition,
             total_slot_ms, total_bytes_processed, total_bytes_billed, cache_hit, error_result.reason AS error_reason,
             labels
      FROM `region-us`.INFORMATION_SCHEMA.JOBS_BY_PROJECT
      WHERE creation_time BETWEEN @since AND @until AND user_email = @u
        AND (job_id LIKE 'okf_graph_%' OR EXISTS (SELECT 1 FROM UNNEST(labels) l WHERE l.key = 'okf_spike')
             OR reservation_id IS NOT NULL OR query LIKE '%okf_graph_spike_20260905%')
      ORDER BY creation_time""", job_config=bigquery.QueryJobConfig(query_parameters=[
          P("since", "TIMESTAMP", since), P("until", "TIMESTAMP", until), P("u", "STRING", "raincoatrun@gmail.com")]),
      location=LOCATION).result()]
    timeline = [dict(r) for r in client.query(f"""
      SELECT period_start, reservation_name, slot_capacity, autoscale.current_slots AS autoscale_current_slots,
             autoscale.max_slots AS autoscale_max_slots, edition, ignore_idle_slots
      FROM `region-us`.INFORMATION_SCHEMA.RESERVATIONS_TIMELINE
      WHERE period_start BETWEEN @since AND @until AND reservation_name = @r
      ORDER BY period_start""", job_config=bigquery.QueryJobConfig(query_parameters=[
          P("since", "TIMESTAMP", since), P("until", "TIMESTAMP", until), P("r", "STRING", RESERVATION)]),
      location=LOCATION).result()]
    resv_jobs = [j for j in jobs if j["reservation_id"]]
    od_jobs = [j for j in jobs if not j["reservation_id"]]
    slot_ms = sum(j["total_slot_ms"] or 0 for j in resv_jobs)
    # allocated bill: per-minute autoscale slots (RESERVATIONS_TIMELINE is per minute) x rate/60
    alloc_slot_minutes = sum((r["autoscale_current_slots"] or 0) + (r["slot_capacity"] or 0) for r in timeline)
    od_bytes = sum(j["total_bytes_billed"] or 0 for j in od_jobs)
    out = {
        "window": {"since": since, "until": until}, "rate_usd_per_slot_hour": RATE_ENTERPRISE_US,
        "reservation_jobs": len(resv_jobs), "ondemand_jobs": len(od_jobs),
        "slot_ms_on_reservation": slot_ms,
        "slot_attribution_usd": round(slot_ms / 3_600_000 * RATE_ENTERPRISE_US, 4),
        "timeline_minutes": len(timeline), "allocated_slot_minutes": alloc_slot_minutes,
        "allocated_capacity_usd": round(alloc_slot_minutes / 60 * RATE_ENTERPRISE_US, 4),
        "ondemand_bytes_billed": od_bytes, "ondemand_usd": round(od_bytes / 2**40 * RATE_ONDEMAND_TIB, 4),
        "note": "slot attribution is a resource-use estimate, not the invoice; allocated_capacity_usd is the capacity bill "
                "estimate from the per-minute autoscale timeline (1-minute minimum granularity); billing export reconciliation pending",
        "timeline": timeline, "jobs": jobs,
    }
    return out


if __name__ == "__main__":
    since, until = sys.argv[1], sys.argv[2]
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    o = reconcile(client, since, until)
    with open("evidence/cost.json", "w") as fh:
        json.dump(o, fh, indent=1, default=str)
    print(json.dumps({k: v for k, v in o.items() if k not in ("timeline", "jobs")}, indent=1))
    for r in o["timeline"]:
        print(r["period_start"], "baseline", r["slot_capacity"], "autoscale", r["autoscale_current_slots"])
