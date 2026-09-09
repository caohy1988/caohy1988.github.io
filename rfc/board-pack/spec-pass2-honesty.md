# Spec — Pass 2 honesty (ordinary-SQL retrieval cells measured)

- Files: `rfc/board-pack/{index.html,STORY.md}`; `rfc/index.html` (current-evidence box, Phase 5 gate cell and
  card, footer provenance); `spec.md` (dated addendum and one copy-map note); `intent.md` and `plan.md` (dated
  addenda). No change to `styles.css`, SVG geometry or text, `.hero`, `#later-questions`, the capacity line,
  `.punchline`, `.ask`, either "call it proven" bar sentence, the Knowledge Publications callout, the access
  paragraphs, `rfc/bq-vp/`, `rfc/full-demo/`, or any spike artifact.
- Evidence pin **E12** = `16d20ababb997a9e140281773bcdebabd2f45c5c` (PR 57 merge, `origin/main` at kick). Artifacts:
  `rfc/spikes/bq-graph/evidence/sql-baseline/baseline.md` (card, `RETRIEVAL_MEASURED`, linked by relative published
  path as PR 46 P2 requires), `evidence/sql-baseline/run_sqlbase-20260909-065734-c50d0411.json` (the completing
  campaign), `evidence/requests.jsonl` (retained attempts). The board pack keeps its existing relative link to the
  card; the full RFC gains the same relative link. No new pinned URL is required.

## What is now true (E12)

Campaign `sqlbase-20260909-065734-c50d0411`, 2026-09-09, on-demand by job-level override on every one of its 1,678
jobs, 28.1 GiB charged at $0.17 list inside the declared 64 GiB / $0.50 ceiling, filled all four retrieval cells:

| Cell | Shape | C | Measured | p50 ms | p95 ms | ok |
|---|---|---|---|---|---|---|
| `sqlbase_forced_c1` | forced | 1 | 100/100 | 2,564 | 3,171 | 100% |
| `sqlbase_forced_c5` | forced | 5 | 100/100 | 8,700 | 10,770 | 100% |
| `sqlbase_natural_c1` | natural | 1 | 100/100 | 3,724 | 4,459 | 100% |
| `sqlbase_natural_c5` | natural | 5 | 100/100 | 13,799 | 15,892 | 99% |

Percentiles are nearest-rank over every measured attempt, failures included. Three earlier campaigns measured nothing
and are retained on the card. The per-request slowdown at C=5 (about 3.4× forced, 3.7× natural) has no established
cause; per-job creation-to-start and server execution medians are roughly unchanged from C=1, so queueing is a
hypothesis, not a finding.

Still not measured: `sqlchain_forced_c1` / `sqlchain_forced_c5` (`NOT_IMPLEMENTED` + `FACTS_UNSELECTED`); the five
cost cells (`UNMEASURED`); the GQL comparison (`OPTIONAL_LATER`; the recorded GQL C=1 sample is 28 of 100 attempts and
not a comparator); the graph benchmark's own nine cells (0 of 9). Every threshold is `PROPOSED`; the owner has
accepted none.

## Rules (numbered after R33 in `spec-pr51-honesty.md`)

- **R34 — the comparison has numbers.** Every sentence saying the ordinary-SQL comparison is a declared plan with no
  numbers, predeclared and empty, or unmeasured *as a whole*, is now false and must state what was measured: the four
  retrieval cells, a hundred measured attempts each, one at a time and five at once, on on-demand capacity, every
  attempt retained. Do not replace one overstatement with another: it is retrieval time only.
- **R35 — "nine cells" belongs to the graph benchmark.** A sentence that says none of the nine planned cells is
  complete must name the graph benchmark as the owner of those nine, and wherever it shares a surface with the
  ordinary-SQL claim the two must sit together so the reader cannot carry away zero retrieval fill. The 0 of 9 count
  itself is unchanged and stays.
- **R36 — measured is not accepted, and not a verdict.** Numbers appear as retrieval times at a stated shape,
  concurrency and capacity. No sentence says the threshold was met or missed, that five at once is now a planning
  default, or names a cause for the slowdown at five at once. Where the numbers stand beside the proposed five-second
  threshold, the same sentence or the next says a measurement against a proposed threshold is not an acceptance of it.
- **R37 — what stays unmeasured is named beside the new fact.** Every independently readable surface that states the
  new fact also states, in the same or the next sentence, that the full question-to-number path has no runner and no
  selected fact-data version, and that cost is unmeasured. A caveat in the main body does not qualify a bullet. The evaluation card's concurrency, latency and cost notes read together as one surface: the latency note carries the unsampled question-to-number clause for all three.
- **R38 — no engine winner and no bar movement.** The measured SQL cells are not compared against the graph sample in
  any sentence: different capacity, different sample size, not a matched run. The "call it proven" bar text, the
  access story (denials on the SQL path only, not inside graph queries), and the Knowledge Publications callout do not
  move. This is not 2026-09-19 acceptance, not pilot validation and not promotion.
- **R39 — human tone.** No campaign identifiers, cell names, state labels, pull-request numbers, commit hashes or
  personal names in visible prose on either page. Numbers in the closed skim are written in words or as plain figures
  with "about"; the technical-design bullet may carry one-decimal figures. Links carry friendly text.
- **R40 — history is not rewritten.** Dated slice documents (`intent-sep19-pack.md`, `spec-pr51-honesty.md` R30,
  `spec.md` R25 as dated) keep their wording as history; the addendum supersedes rather than edits them. No spike
  artifact is touched.

## Acceptance

- No "declared plan with no numbers", "predeclared and empty", or unqualified "none of the nine planned cells" survives
  in the board-pack pages or the touched full-RFC sentences.
- Every new measured-value sentence carries the shape, the concurrency and "on-demand", and is followed within one
  sentence by the unmeasured list (R37) and the proposed-not-accepted qualification where a threshold is nearby (R36).
- Banned-token scan over visible prose in `index.html` and the touched `rfc/index.html` sentences: no `sqlbase`,
  `RETRIEVAL_MEASURED`, `COMPLETE`, `NOT_IMPLEMENTED`, `FACTS_UNSELECTED`, `UNMEASURED`, `PR 5`, commit hash.
- The relative card link resolves on disk from both pages; `tests/test_board_pack_links.py` passes.
- Protected regions hash identically to E12 on both pages; `styles.css` and both SVGs are byte-identical.
- Chromium, Firefox and WebKit at 1280 and 320 px, closed and open: overflow 0, no duplicate IDs, no dangling
  anchors, no console errors; closed-state word count recorded in `plan-pass2-honesty.md` with the delta from E12
  (1,948 words at E12 in all three engines; no closed-state ceiling has been maintained since the 940 recorded on
  2026-09-07, so this slice records the delta rather than asserting a ceiling).
