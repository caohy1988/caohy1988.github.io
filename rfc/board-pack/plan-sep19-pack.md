# Plan — September 19 2026 decision pack (Slice A)

1. Read the vault contract, `forbidden.md`, Astra R1 §3 and `/tmp/okf-sep19-pack/OWNER.md`; confirm `origin/main` = `ad18b07` and branch from it.
2. Add `fixtures/sql_baseline.json` (predeclared cells, samples, budget, stop rule) and `okf_bq_graph/sql_baseline.py` (validate → read recorded priors → project budget → build card → render). The module opens no client.
3. Generate `evidence/sql-baseline/{plan.json,baseline.md}` with `python3 -m okf_bq_graph.sql_baseline`.
4. Add `tests/test_sql_baseline.py`: plan validation gates, the edition-from-jobs correction, no prior fills a cell, a tampered cell fails the build, both latencies stay separate cells, cost cells stay listed and unmeasured, budget projection fits and a tighter ceiling does not, and the committed artifacts match their generator.
5. Add the `#sep19-envelope` card to `rfc/board-pack/index.html` using the existing `#later-questions` markup pattern; mirror it in `STORY.md` as a table.
6. Correct the three PR 45 sentences in `index.html` and their `STORY.md` mirrors; add the restricted-chain bullet to `STORY.md`.
7. Add the intent / spec / plan slice documents and a README pointer in `rfc/spikes/bq-graph/README.md`.
8. Verification, all offline: the full spike suite (`python3 -m pytest -q`), a regeneration diff on the committed card, and HTML/anchor checks on the board pack.
9. Push `feat/sep19-pack-envelope` and open a PR against `main`. No merge. Haiyuan holds the gate.

## Owner-proxy review round 1 (PR 46, `88d379b`, 0 P0 / 1 P1 / 2 P2)

10. **P1 — fact version.** The card labelled one field "corpus and fact versions / fixed, not proposed" while pinning
    only the authored bundle and the graph publication. Split it: the definitions row keeps its pin and now says it
    identifies no fact data; a new row records the fact fixture the retained chain does name (7 tables, the receipt
    example's own publication, SDK pin `6719eb5`) and marks the **version** `UNSELECTED / INCOMPLETE`, a prerequisite
    for the request-to-consumer comparison. Mirrored in `STORY.md` and `spec-sep19-pack.md`; carried into the baseline
    as a `facts` block that blocks the two consumer cells with a stated reason. No new live run.
11. **P2 — cost-per-success denominator.** `fixtures/sql_baseline.json` said failed and refused attempts were
    "included in the denominator"; the module said the opposite. One formula now lives in the fixture — total cost of
    all attempts ÷ released, receipt-verified answers — the module renders it, and `validate_plan` refuses a
    `cost_per_success` spec without it. Both artifacts regenerated.
12. **P2 — baseline link.** The card pinned the new file at `ad18b07`, which predates it (HTTP 404). Now a relative
    published path. `tests/test_board_pack_links.py` asserts every relative and site-absolute `href` on the page
    resolves on disk, and that every pinned GitHub blob URL into this repository names a path that exists at that
    revision in the local object store.

## Verification results

- `python3 -m pytest -q` in `rfc/spikes/bq-graph`: **498 passed** (448 before this slice, 50 new — 28 at `88d379b`, 22 added by the review round).
- `python3 -m okf_bq_graph.sql_baseline` regenerated into a temporary directory is byte-identical to the committed `evidence/sql-baseline/plan.json` and `baseline.md` (asserted by `test_committed_card_matches_its_generator`).
- Board pack: `#sep19-envelope` is present and unique, every internal anchor resolves, every relative link resolves to a file on disk, the document parses, and no `<details>` wrapping is required for the card to be visible.

## Out of scope

`rfc/index.html`; any live SQL run; any GQL comparison; any reservation; the request-to-consumer sampling runner; the 10,000/day cost model; rewriting the dated `report.md` / `comparison.md` records. Thresholds stay PROPOSED until Haiyuan accepts specific numbers.
