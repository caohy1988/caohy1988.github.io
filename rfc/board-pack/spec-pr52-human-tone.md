# Spec — whole-pack human tone

- Files: `rfc/board-pack/{index.html,STORY.md}`, and the skim sentences in `rfc/index.html` that mirror the pack.
- Voice: leadership brief. Point first, then its limit. One idea per paragraph. Short sentences by default.

## Rules

- **T1 — no claim regression.** Every factual claim, limit, number, date and link that exists before this pass exists
  after it. This is a rewrite of sentences, not of the evidence. If a rewrite cannot carry a limit, the rewrite is
  wrong, not the limit.
- **T2 — the limit stays with the claim.** R27 from the honesty pass still binds: every independently readable
  surface stating the 8 September graph-query chain carries all three limits locally — a seed chosen by hand rather
  than a catalog read, one operator on both legs, and only the case that should succeed, so a swapped query and a
  mismatched declaration have never been put through graph queries. Shortening must never separate a claim from its
  qualification.
- **T3 — the three chains stay distinct.** The 7 September catalog chains (live catalog read, one operator, plain
  SQL), the 7 September restricted chain (restricted identity, plain SQL, hand-chosen seed) and the 8 September graph
  chain (graph queries, hand-chosen seed, one operator, success case only) are different runs. No sentence may let a
  reader merge them, and no pronoun may quietly include one in a claim about another.
- **T4 — inventory moves, it does not vanish.** Job counts, entry-group mechanics, dataset names, fixture layout and
  cleanup bookkeeping come off the skim surfaces and stay in the linked evidence, which the prose still points at
  with friendly text. What each run does *not* show stays on the page in words.
- **T5 — no new metric, no upgraded metric.** G8 remains 0 of 9 cells. Partial samples stay described as partial: the
  5.4 seconds from twenty-eight of a hundred attempts one at a time, the single 21-second publish. Proposed
  thresholds stay proposed and unaccepted. One chain is not a sample.
- **T6 — the bar does not move.** The combined bar — catalog discovery, a restricted identity and graph queries, in
  one chain, on real cohort data — and the 2026-09-19 decision wording are unchanged.
- **T7 — human tone.** No verdict labels, gate codes, case names, pull-request numbers or commit hashes in visible
  prose; hashes live only inside link targets. Say "the number was released only after the check passed", not the
  verdict word.
- **T8 — structure may change, anchors may not.** Paragraphs may split or reorder within a section. Element ids,
  same-document fragments and link targets stay valid.

## Method

Rewrite the blocks that read worst first: the opening assessment, the design intro, the diagram plot note, the
retrieval and access paragraphs, the three chain paragraphs, and the "where the evidence stands" pair. Verify
afterwards with a claim checklist rather than by eye.
