# Catalog finds, BigQuery serves — the full-version OKF runtime demo (`/rfc/full-demo/`)

Live at <https://caohy1988.github.io/rfc/full-demo/> once merged. Static files, no build. Plan docs:
`intent.md`, `spec.md`, `plan.md`, `CUSTOMER_STORIES.md`, `ARCHITECTURE.md` (merged in PR 15).

## Six beats

1. **Ask.** The twelve real questions of session `f21ee192…` and the over-claim from session `04fa3d56…`.
2. **Observe.** Histogram Σ 180, 24 tool completions, the live never-emit scan (0 hits on 8 keys over 27 payloads).
3. **Catalog path: where it stops.** Shipped `okf-bundle` + `okf` aspect via `entries.get --view=ALL`;
   `lookupContext` on the same entry omitting every `okf` field; eleven resources → 400; the `04fa3d56`
   transcript with both system prompts; `searchEntries` still finding the deprecated metric; EntryGroup
   IAM; the legacy `okf-derived-germany` entry collapsed and labelled prior.
4. **Sync (CLI).** The `okf-context sync` algorithm and IAM contract as RFC text; what was actually run
   (sample `setup.ts` + `push.ts`, the DDL) under the operator identity; no `BQ_COMMITTED` /
   `CATALOG_STAMPED` shown because the syncer is not built.
5. **Serve (BigQuery).** Five real `SELECT`s: empty `deployment_heads`, empty history, the resolution
   probe (`NO_HEAD`, `AMBIGUOUS_LEGACY`, `FAIL_CLOSED`), seeded `publications`, the view; the
   `UNVERIFIABLE` receipt; 12 of 12 answers contain “unproven” (one verbatim “No. The number is unproven.”); 13 of 13 exclusions of the dead metric.
6. **Attribution.** The two-key query: band `attributed` Σ 14, band `receipt_only` Σ 13, `demo_evidence`,
   and the v0 events-only query.

Below the stepper: the capability matrix from `spec.md` §2 with a **Shown on** column and `RFC text
only` labels, and the five customer stories with real session ids.

## What was done for this page, and what was deferred

Done on 2026-09-03 as the operator (`raincoatrun@gmail.com`, project Owner): every capture in
`live/` (see `live/README.md`); `sql/setup_runtime_tables.sql` run once (11 tables, 1 view, seeds);
the sample `setup.ts` + `push.ts` run against the derived bundle the SDK adapter regenerated from
the committed 180-row export (publication `sha256:53bd1651…` reproduced first).

Deferred to Phase A: the three service accounts, custom role, table-level grants, boundary probe,
negative checks, and the `okf-context sync` CLI. Phase D (a new tape) follows the review of this PR.
`okf-bqaa-cli.mp4` was not re-recorded.

## Files

- `index.html`, `app.js`, `styles.css`: the viewer. `styles.css` is `/rfc/demo/styles.css` plus additions.
- `matrix.json`, `stories.json`: the capability matrix and stories as data, checked by the tool below.
- `live/`: captures, job ids, transcripts. `live/README.md` lists every file and the command behind it.
- `sql/`: `sessions_by_context_ref.sql` (v0), `never_emit_scan.sql`, `serve_probes.sql`,
  `attribution_two_key.sql` (reader, SELECT only), `setup_runtime_tables.sql` (setup, DDL + seeds).
- `tools/check_full_demo.py`: the checker. Exit 0 required.

## Run it locally

```bash
python3 -m http.server 8000          # from the repo root
open http://localhost:8000/rfc/full-demo/
python3 rfc/full-demo/tools/check_full_demo.py
```
