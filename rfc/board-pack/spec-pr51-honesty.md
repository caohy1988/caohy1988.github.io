# Spec — PR 51 honesty

- Files: `rfc/board-pack/{index.html,STORY.md}`; `rfc/index.html` (status note, still-to-prove line, connected-path
  bar, current-evidence box, footer provenance).
- Evidence pin: PR 51 merged as `0ab27d679a1e640cc7dcfdbeea465e44788ab133`. Reader-facing links point at
  `rfc/spikes/bq-graph/evidence/chain/SLICE_B_RUN_E_20260908.md` at that commit. The spike README has no live
  graph-query section, so do not link an anchor that does not exist.

## What is now true (E11)

One live chain, 8 September 2026, ran retrieval through graph queries inside an owned Enterprise capacity window on
Acme's invented gross-margin data. The declaration bound to the executed publication, the receipt check ran the job
and verified it, the consumer released the number only after that check passed, and the window closed with capacity
removed, every job it owned finished and accounted for, and nothing left outstanding.

## Rules

- **R26 — the graph-query gate is open, once.** Every sentence saying no live chain has used the graph-query wiring,
  that graph queries are untested in any live chain, or that the live graph-query gate is closed, is now false and
  must be replaced with what actually ran. Do not replace one overstatement with another: it is one chain.
- **R27 — name the three limits beside the new fact, every time.** The chain started from a seed chosen by hand, not
  a catalog read; both legs ran under one operator, so no second identity or policy decision was involved; only the
  approved case ran, and the substituted-query and mismatched-declaration cases were not run in that window. A
  sentence that states the new fact without these is not honest enough to ship.
  Every *independently readable* surface counts separately — comparison notes, diagram captions and plot notes,
  section introductions and footer provenance — because a reader skims one without the others. A caveat in the main
  body does not qualify a caption. Listing which access tests did not run is also not the same statement as which
  cases were attempted: say plainly that only the success case ran. After adding an exception to a group of chains,
  re-read the pronouns that follow it ("those chains") and re-scope them to the group actually meant.
- **R28 — the combined bar is unchanged.** "One chain that does all of it at once — catalog discovery, a restricted
  identity and graph queries — on real cohort data" stays exactly as strong as before. No single chain has done both
  a live catalog read and a second identity, and now none has done all three. The connected-path bar and the
  2026-09-19 checkpoint wording do not move.
- **R29 — the access story is untouched.** The five access-denial checks with a separate restricted identity still
  ran only on the SQL path. They have **not** run inside graph queries. Sentences saying so stay. Where a sentence
  said a capacity window could not be opened, it may note that a window has since been opened for a different chain,
  but must not imply the access checks ran inside it.
- **R30 — no new metrics.** G8 remains 0 of 9 cells; no latency, cost or concurrency number is added or implied. One
  chain is not a sample: no percentiles, no envelope, no throughput. This is not 2026-09-19 acceptance, not pilot
  validation and not promotion.
- **R31 — the legacy-window clause.** The five legacy reconciliation windows were reconciled before this run. Where a
  sentence being rewritten still calls them unreconciled, correct it; do not open a wider sweep for it.
- **R32 — human tone.** No verdict labels, gate codes, case names, pull-request numbers or commit hashes in visible
  prose. Say "the number was released only after the check passed", not the verdict word. Links carry friendly text.
- **R33 — history is not rewritten.** Earlier runs keep their recorded descriptions. The 7 September chains still
  read as catalog-seeded, one operator, plain SQL; the restricted-identity chain still reads as fixture-seeded on
  plain SQL. Nothing in the spike record is edited by this pass.
