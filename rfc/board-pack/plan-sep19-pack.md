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

## Verification results

- `python3 -m pytest -q` in `rfc/spikes/bq-graph`: **476 passed** (448 before this slice, 28 new).
- `python3 -m okf_bq_graph.sql_baseline` regenerated into a temporary directory is byte-identical to the committed `evidence/sql-baseline/plan.json` and `baseline.md` (asserted by `test_committed_card_matches_its_generator`).
- Board pack: `#sep19-envelope` is present and unique, every internal anchor resolves, the document parses, and no `<details>` wrapping is required for the card to be visible.

## Out of scope

`rfc/index.html`; any live SQL run; any GQL comparison; any reservation; the request-to-consumer sampling runner; the 10,000/day cost model; rewriting the dated `report.md` / `comparison.md` records. Thresholds stay PROPOSED until Haiyuan accepts specific numbers.
