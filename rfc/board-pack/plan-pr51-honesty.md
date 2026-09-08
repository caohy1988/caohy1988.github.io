# Plan — PR 51 honesty

Narrow edit pass. Each location either states a sentence that is now false, or is a skim surface where a reader would
otherwise carry the old picture away.

## `rfc/board-pack/index.html`

1. **Runtime assessment (what works today / what we still need to prove).** Replace the closing clause that says the
   graph-query tooling was built offline but no live chain has used it and the gate stays closed. State the 8
   September chain with R27's three limits. Leave "what we still need to prove" untouched — all of it at once, on
   real cohort data, is still the bar.
2. **Receipt comparison note.** The recorded Acme chains sentence says they used plain SQL rather than graph queries.
   True of those chains; add that a later chain fed the same check from graph-query retrieval, hand-seeded and under
   one operator.
3. **Diagram descriptions, wide and narrow.** Both carry "graph queries are still untested in any live chain. Offline
   graph-query tooling exists but has not run live." Replace with the one chain and its limits. Keep the rest of the
   description as-is; the full design still has not run.
4. **Diagram plot note.** Extend the "connected chains … used plain SQL" line so it does not read as a claim about
   every chain.
5. **Design intro.** Add the graph-query chain beside the three recorded experiments, with its limits.
6. **Retrieval paragraph (the graph walk).** It says the chains ran the sanctioned SQL through the receipt check but
   from plain SQL retrieval rather than from the walk. Note that a later chain did retrieve through graph queries.
7. **Access paragraph.** Keep "the same five checks have not run inside graph queries" (R29). Soften only "this run
   could not open one" so it does not imply no window has ever been opened — while making clear the access checks
   still have not run inside graph queries.
8. **Connected-path bar paragraph.** Replace the closing clause about offline wiring and a closed gate. State the
   chain, its limits, and that the bar is unchanged (R28).

## `rfc/board-pack/STORY.md`

9. **Evidence list.** Add a bullet for the 8 September graph-query chain in the same shape as its neighbours: what
   ran, then what it does not show.
10. **Connected-path bullet.** Replace the closing clause (no live chain through graph queries, gate closed, five
    legacy windows unreconciled) with the chain, its limits, the unchanged bar, and the corrected legacy clause.
11. **Access bullet.** Same softening as item 7.

## `rfc/index.html`

12. **Status note.** Replace the closed-gate clause with the chain and its limits.
13. **What the examples show.** "Still to prove" becomes the combination, not graph queries alone.
14. **Connected-path bar.** Add the chain; the bar does not move.
15. **Current-evidence box, "what remains to prove".** Replace the offline-wiring and closed-gate clause and the
    stale legacy-window clause.
16. **Footer provenance.** "live chains remain plain SQL" is now false; state that one live chain ran through graph
    queries.

## Out of scope

The architecture figure caption and crosswalk table describe the proposed design and the access evidence; they are
accurate and stay. No spike file is edited. No metric is added. No merge.
