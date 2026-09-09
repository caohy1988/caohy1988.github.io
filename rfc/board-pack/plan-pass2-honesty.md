# Plan — Pass 2 honesty (ordinary-SQL retrieval cells measured)

Narrow edit pass. Each location either states a sentence that is now false, or is a skim surface where a reader would
otherwise carry the old picture away. Numbers in the edits come from `baseline.md` at E12 and nowhere else.

## `rfc/board-pack/index.html`

1. **Runtime assessment, "What is still open".** "Speed benchmarks are unfinished" becomes: the graph speed
   benchmark is unfinished; ordinary-SQL retrieval has been timed, one at a time and five at once, but the full
   question-to-number path and its cost have not; nobody has accepted an operating budget. Closed skim.
2. **Retrieval comparison note.** "Speed benchmarks and access checks inside graph queries are still to come" is
   scoped to graph queries so it no longer reads as no benchmark at all. Closed skim.
3. **Evaluation card, concurrency.** "One request at a time is the only concurrency any recorded measurement covers"
   is false: ordinary-SQL retrieval has been timed at five at once. Say so, and that a measurement at five does not
   make five an agreed setting. Closed skim.
4. **Evaluation card, latency.** Beside the 5.4-second partial graph sample, add what ordinary SQL measured on
   on-demand capacity, in words, at both shapes and both concurrencies, then R36's qualification. Closed skim.
5. **Evaluation card, cost.** "Nothing has been measured against it" stays true for cost; the clause that follows now
   says the ordinary-SQL comparison has retrieval times but none of its cost cells, and the graph benchmark's nine
   cells are unfinished. The card link moves onto "ordinary-SQL comparison". Closed skim.
6. **Technical design, "Also unfinished" bullet.** Replace the declared-plan bullet with: graph benchmark 0 of 9;
   the ordinary-SQL comparison's four retrieval cells measured (attempts, shapes, concurrencies, on-demand, retained),
   the four p95 figures, the two unfilled question-to-number cells and why, the five unmeasured cost cells, the
   unexplained slowdown at five, thresholds still proposed. Inside the disclosure; not word-budgeted.

## `rfc/board-pack/STORY.md`

7. **"The bar is unchanged" paragraph.** Same correction as item 1, in the editorial voice.
8. **Envelope table, concurrency row.** Same correction as item 3.
9. **Envelope table, latency row.** Add the four measured p95 values with shape and concurrency, and R36's
   qualification. The request-to-consumer clause stays.
10. **"Matched baseline" paragraph.** "Predeclared and empty" becomes predeclared with its retrieval cells measured;
    keep the cell inventory, add the campaign facts in the editorial voice, keep the unfilled consumer cells, the five
    cost cells, the retained prior observations that fill none, and the optional GQL clause.

## `rfc/index.html`

11. **Current-evidence box.** "Speed benchmarks are not finished yet (0 of 9 cells complete)" keeps its wording and
    its pinned link, gains "on the graph benchmark", and is followed by the ordinary-SQL fact with a relative link to
    the card and the unmeasured list.
12. **Phase 5 gate cell and Phase 5 "Added" card.** Same "on the graph benchmark" scoping plus a short clause that the
    ordinary-SQL retrieval cells are measured and its consumer and cost cells are not.
13. **Footer provenance.** Append a dated clause for the measured retrieval cells with the unmeasured remainder.

## `spec.md`, `intent.md`, `plan.md`

14. Dated addenda pointing at the three slice documents; the copy-map row for G8 gains a dated note; R25's "0/9"
    sentence gains a dated note that the ordinary-SQL retrieval cells are measured. No rule is deleted.

## Verification (offline only)

- Exact-string edit script that fails if any target sentence is missing, so a stale target is caught rather than
  silently skipped.
- Stale-phrase scan across `rfc/**/*.html` and `rfc/board-pack/*.md` (dated slice documents excluded by name).
- Banned-token scan on visible prose (R39).
- Protected-region hashes against E12; `styles.css` and SVG byte checks.
- `tests/test_board_pack_links.py` and `tests/test_sql_baseline.py` under `/tmp/bq-venv/bin/python -m pytest`.
- Three-engine Playwright pass at 1280 and 320 px, closed and open; word count recorded below.
- `git diff --check`; push; open PR against `main`. No merge.

## Validation record

Filled in after implementation (see the bottom of this file).

## Validation record (Claude Fable 5.1, 2026-09-09 PT, `feat/board-pack-pass2-honesty` from `origin/main` `16d20ab`)

- **Edit script.** Sixteen exact-string replacements across `index.html` (6), `STORY.md` (4), `rfc/index.html` (4) and `spec.md` (2), each asserted to occur exactly once before replacement; dated addenda appended to `spec.md` and `intent.md`.
- **Stale-phrase scan** over `rfc/**/*.html` and `rfc/board-pack/*.md` (dated slice documents and `rfc/full-rfc-align-*` excluded): no "declared plan", "no numbers in it", "predeclared and empty" or "only concurrency any recorded" survives in `index.html`, `STORY.md` or `rfc/index.html`. One hit in `intent.md` is this slice's own addendum describing what was false.
- **Banned-token scan** on the board pack's visible prose (tags stripped) and the four touched `rfc/index.html` lines: no campaign identifier, cell name, state label, PR number, commit hash or personal name.
- **Protected regions** byte-identical to `16d20ab`: `.hero`, `#later-questions`, the capacity line, `.punchline`, `.ask`, "The bar." paragraph, all three board-pack SVGs, both full-RFC SVGs, every `<pre>` block, `styles.css`. Every sentence containing "proven" in `rfc/index.html` is unchanged except the footer, where a dated clause was appended.
- **Links.** The relative card link resolves on disk from both pages; `tests/test_board_pack_links.py` + `tests/test_sql_baseline.py`: **58 passed** under `/tmp/bq-venv/bin/python -m pytest` with bytecode writes off.
- **Engines.** Chromium, Firefox and WebKit at 1280 and 320 px, closed and open: closed-state words **2,070** in all three (1,948 at `16d20ab`, +122, all of it in the four closed-skim sentences listed in the plan); open 3,176 / 3,069 / 3,176 at 1280; document overflow 0 throughout; no duplicate IDs, no dangling anchors, no console or page errors. Full RFC at 1280 and 320: overflow 0, `#repro-ask-later` 876/876 and 444-in-276, no dangling anchors.
- **Observed, not fixed.** The board-pack masthead still reads "3–4 MIN READ" while the closed state measured 1,948 words before this slice; the count has not been tracked against a ceiling since the 940 recorded on 2026-09-07. The masthead is outside this slice's scope and inside the `.hero` region every honesty slice has protected; flagged for the owner.
- `git diff --check` clean. Docs only: no cloud run, no spike artifact edited, no merge.
