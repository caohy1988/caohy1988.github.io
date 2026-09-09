# Plan — Sep 19 ordinary-SQL baseline Slice B

## Pass 1 — hermetic (commit + push before any live)
1. Add `okf_bq_graph/sql_baseline_run.py` (or equivalent CLI) that builds per-cell configs for `benchmark.measure` from the sql-baseline plan.
2. Wire `python -m okf_bq_graph.sql_baseline_run --dry-run` (print cells/queries/budget, open no client) and `--live` (real measure).
3. Hermetic tests: plan→cell mapping, shape isolation, run_id uniqueness gate, refuse consumer cells, dry-run opens no client.
4. README + baseline card command lines updated to name the new driver.
5. Commit + push branch; open PR. **Do not wait on live to push Pass 1.**

## Pass 2 — live (same PR, foreground)
6. Run the four retrieval cells foreground under the plan budget; retain attempts + cell summaries.
7. Regenerate/update `evidence/sql-baseline/` so measured cells show real n / p50 / p95 / state; unrun/stopped stay INCOMPLETE with why.
8. Full pytest still green; vault note under Ship/builds.
9. Push evidence + card update on the same PR. No merge (Haiyuan gate). Astra review after PR URL exists.

## Anti exit-while-waiting
Never end a turn waiting on background live. Either foreground wait to `exit=`, or push hermetic Pass 1 first then a follow-up for Pass 2.
