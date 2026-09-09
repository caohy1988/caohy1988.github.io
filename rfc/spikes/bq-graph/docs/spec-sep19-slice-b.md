# Spec — Sep 19 ordinary-SQL baseline Slice B

## Driver requirements
1. Read the committed sql-baseline plan (not `fixtures/scale.json`).
2. For each retrieval cell, pass **only that cell's shape** as the query list (forced vs natural never pooled).
3. Engine `fallback`; result cache off; warmups/measured/timeout/concurrency from the plan.
4. On-demand: no Enterprise reservation window. Budget uses `cell_seconds` (and total budget) only.
5. Fresh `run_id` per measurement campaign; must not collide with retained GQL `summary` run_ids (`benchmark.measure` raises).
6. Reuse `okf_bq_graph.benchmark.measure` for sampling + `evidence/requests.jsonl` retention; do not reimplement aggregation.
7. Stop rule: cell stays INCOMPLETE if stopped mid-sample; never invent p50/p95.
8. Consumer cells remain NOT_IMPLEMENTED + FACTS_UNSELECTED; driver must refuse to pretend to fill them.

## Live run
- Project `test-project-0728-467323`, corpus/publication from the plan.
- Respect plan budget: 900 s/cell, 3600 s total, 64 GiB billed, $0.50 list on-demand.
- Foreground wait to durable exit; retain evidence under `evidence/sql-baseline/` (or a dated subdir the card links).
- Do not delete standing Enterprise reservation `US.okf-demo-enterprise` (unrelated to this on-demand run).

## Honesty
- Thresholds on the board-pack `#sep19-envelope` stay PROPOSED.
- Prior n=1 observations still do not fill cells.
- Edition/on-demand labeling: this run is on-demand; do not claim Enterprise for it.
