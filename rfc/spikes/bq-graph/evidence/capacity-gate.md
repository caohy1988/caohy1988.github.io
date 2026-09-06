# G1 capacity gate — measured 2026-09-05 (UTC)

Principal: operator user account (project Owner; address redacted from committed evidence). Project `test-project-0728-467323` (number 201486563047), no parent folder/organization (`gcloud projects get-ancestors` returns only the project), so no inherited assignment is possible. Billing enabled. `bq 2.1.28`, `gcloud 559.0.0`.

## Inventory (read-only) — `capacity.json`

| Location | reservations.list | capacityCommitments.list | searchAssignments(assignee=project) | bq ls --reservation / --reservation_assignment |
|---|---|---|---|---|
| US | `{}` (HTTP 200) | `{}` (200) | `{}` (200) | none / none |
| us-central1 | `{}` (200) | `{}` (200) | `{}` (200) | none / none |
| EU | `{}` (200) | `{}` (200) | `{}` (200) | none / none |

Datasets in the project: 83 in `US`, 9 in `us-central1`. The spike dataset `okf_graph_spike_20260905` was created in `US` (default table expiration 14 days). IAM `testIamPermissions` granted all seven required permissions (reservations create/delete/list, assignments create/delete, datasets.create, jobs.create). State: `READY_TO_PROVISION`.

## Public SKU prices (Cloud Billing Catalog API, read by curl 2026-09-05T23:40Z — receipt `sku_receipt.json`; the later `capacity.py` read got 403 SERVICE_DISABLED, so `capacity.json.skus.rows` is empty)

| SKU | Description | USD |
|---|---|---|
| C0F6-38AB-6629 | BigQuery Enterprise Edition for US (multi-region), pay-as-you-go | 0.06 / slot-hour |
| 85AA-6B65-6D94 | BigQuery Enterprise Edition for Iowa (us-central1) | 0.06 / slot-hour |
| F3BC-D8DD-E9F2 | Enterprise Plus, US | 0.10 / slot-hour |
| 5DE7-AD37-6FAB | Standard, US | 0.04 / slot-hour |
| 1DF5-1F98-1DD1 | Analysis (on-demand), US | 6.25 / TiB after 1 TiB free |
| 947D-3B46-7781 | Active Logical Storage, US | 0.02 / GiB-month after 10 GiB free |

Billing granularity (docs): per second with a one-minute minimum; autoscaled slots are added in multiples of 50 and retained for at least a 60 s scale-down window. Cost proposal per spec §2 stands: 100 slots × 2 h × $0.06 = $12 compute ceiling, plus ≤$5 overhead, within a $20 session budget. Authority: Haiyuan's kickoff prompt for this session explicitly allows option (a), a short-lived Enterprise pay-as-you-go autoscaling reservation.

## On-demand GQL probe (before any reservation) — `smoke_ondemand.*`

Job `okf_graph_smoke_ondemand_20260905234252` on a disposable 3-node/2-edge graph `smoke_graph` failed:

> BigQuery Graph queries require a reservation with Enterprise or Enterprise Plus edition.

`CREATE PROPERTY GRAPH` itself succeeded on-demand. This is the measured product boundary: GQL is closed on on-demand; GRAPH_EXPAND was not used (single-root/acyclic/no many-to-many; unsuitable for OKF links).

## Enterprise smoke window `smoke-1` — `cleanup_manifest.json`, `smoke_enterprise.*`

| Step | UTC | Result |
|---|---|---|
| `bq mk --reservation --edition=ENTERPRISE --slots=0 --autoscale_max_slots=100 --ignore_idle_slots=true okf-graph-spike-20260905` | 23:43:45 | created |
| `bq mk --reservation_assignment … --job_type=QUERY` (assignee project) | 23:43:48 | assignment 6422525903903109563 |
| GQL smoke job `okf_graph_smoke_ent_20260905234528_1` | 23:45:31 → 23:46:12 | DONE, 3 rows (a→b 1 hop, a→c 2 hops, b→c 1 hop) |
| job statistics | | `reservation_id = test-project-0728-467323:US.okf-graph-spike-20260905`, `edition = ENTERPRISE`, `totalSlotMs = 21410`, bytes 29, cacheHit false |
| `bq rm --reservation_assignment okf-graph-spike-20260905.6422525903903109563` | 23:47:12 | deleted (first attempt at 23:46:33 used the wrong id format and failed; fixed in `reservation.py`) |
| `bq rm --reservation okf-graph-spike-20260905` | 23:47:15 | deleted |
| verify (`bq ls`, REST reservations.list, searchAssignments) | 23:47:21 | none / `{}` / `{}` |

Observed: the first GQL job on a cold zero-baseline reservation took ~40.5 s wall (start→end) for a 29-byte scan; 21.4 slot-seconds attributed. Reservation lifetime 3.5 min. Capacity-bill estimate for the window: one autoscale step of 50 slots for ≥1 min ≈ 50 × (1/60) × $0.06 ≈ **$0.05** (provisional until the billing export reconciles; see `cost.json` and `report.md` §G8).

**G1 outcome: PASSED (measured).** GQL executes on the named Enterprise reservation with job reference, reservation id and edition recorded; teardown verified.
