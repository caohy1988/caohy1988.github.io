# Intent — September 19 2026 decision pack (Slice A)

Implemented by Claude Opus 5 on `feat/sep19-pack-envelope` from `origin/main` `ad18b07` (PR 45 merged), 2026-09-07 PT. Source: Astra R1 post-PR-39, priority P1 — "make September 19 a workload decision."

## The problem this slice fixes

The 2026-09-19 checkpoint appears on the board pack and in the full RFC as a date with a narrowing rule attached, and nothing else. There is no stated workload, no stated envelope and no owner, so "reassess at the checkpoint" cannot resolve to continue, narrow or stop. Meanwhile 0 of 9 benchmark cells are complete and the only ordinary-SQL measurements are three single observations from integration runs. A more complete synthetic chain would not fix either gap.

## What this slice does

1. Puts a visible, deep-linkable evaluation card on the board pack (`#sep19-envelope`) recording the chosen task, corpus and fact versions, concurrency, request volume, tolerated latency, freshness, retention, success definition, total-cost ceiling and owner.
2. Predeclares a bounded ordinary-SQL baseline under `rfc/spikes/bq-graph/` — cells, samples, budget and stop rule — with every cell empty and every unmeasured cost named.
3. Corrects the three board-pack sentences that PR 45 made stale.

## The owner, and what naming one does not do

Haiyuan Cao (`caohy1988`) is the owner of this decision, named 2026-09-07 on his own direction ("You can make me as owner"). He has accepted no threshold. No Finance or data owner outside this project has been asked for one, and this agent may not invent a customer owner.

Naming an owner is not agreeing an envelope. Every threshold on the card is labelled **PROPOSED**, including the p95 ≤ 5 s at C=5 that has been carried in the graph report since 2026-09-05: that number is a proposal against which a partial C=1 GQL sample was compared, not an agreement with anyone. The card says so in those words.

## Boundaries

No live SQL was run and no number was invented. The baseline is a scaffold: it declares what would be measured and how each cell would be filled, and its own tests fail if a cell acquires a value. Recorded prior observations are carried beside the cells and fill none of them. Any GQL comparison stays optional and later, and must match seed shape, corpus, authorization and workload with its reservation cost accounted separately. No score moves; the hero, arithmetic, three comparisons, later-questions panel, punchline and pilot ask are unchanged.
