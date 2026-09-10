# Spec — shorten both RFC surfaces

## Measurement

Words are counted in headless Chromium as `document.body.innerText` split on whitespace, once as rendered and once with every `<details>` opened (the count a reader can reach). `node rfc/tools/rfc_word_count.mjs rfc/index.html rfc/detailed-rfc/index.html` prints both numbers per page as JSON. The all-open number is the gated one.

| Page | Baseline (all open / closed) | Ceiling (all open) |
|---|---|---|
| `rfc/index.html` | 3,281 / 2,172 | 1,800 |
| `rfc/detailed-rfc/index.html` | 14,102 / 10,132 | 7,500 |

## Rules for every cut

1. **Honesty is invariant.** A shortened sentence may drop detail, never a limit. Where a run was single-identity, hand-seeded, success-only, plain-SQL, unmeasured, synthetic or proposed, the shortened sentence still says so or points to the one place on the page that does.
2. **Say each thing once per page.** The recorded runs' limits live in one block on each page: the technical-design fold on the landing page, the recorded-examples note on the detailed page. Other sections point there instead of restating.
3. **No lab calendar, no people.** Dates of individual test runs, reviewer and author names, the invented VP's name, and "as of" notes go. Decision dates that a reader acts on stay (the 2026-09-19 checkpoint, the 2026-08-26 Catalog post that the baseline is defined by).
4. **No digests, job ids or pull-request numbers in prose.** Pinned GitHub links keep their revisions in the `href` only. OKF convention thread numbers stay only inside the one decision that adopts them, because they are the conventions' names.
5. **Structure survives.** Every `id` attribute on both pages stays, so the legacy-forwarder list, the browser route check and bookmarks are unchanged. Every `href` that a test asserts stays. Both diagrams, all `<pre><code>` contracts and all tables stay (cells may be shortened).

## Landing page (`rfc/index.html`)

| Block | Action |
|---|---|
| Masthead, skip link, head script | keep |
| Hero: title, opening, reconciliation figure, near-miss | keep, opening trimmed |
| Runtime heading: five assessment paragraphs | shrink to three: the proposal, when it is strong, what is shown and what is open |
| Three comparison points | keep cells; comparison notes shortened to the claim, the pinned link and the one limit |
| Later questions | shrink to three one-line questions and one caveat |
| Enterprise-capacity rule | shrink to one sentence |
| Decision envelope (`#sep19-envelope`) | keep every row; each row states the proposed number and the one measured fact, without measurement history. The fact-data row keeps the wording the fact-selection tests assert |
| Technical-design fold: figure, intro, four parts, what is still open | keep figure; intro shrinks; each part keeps its Shown and Limits lists with shorter items; the benchmark bullet drops the numbers that the envelope already carries |
| Punchline, two asks | keep, asks trimmed |

## Detailed RFC (`rfc/detailed-rfc/index.html`)

| Block | Action |
|---|---|
| Header: thesis, subtitle, status note, badges, credo | status note shrinks to one paragraph with two pinned links; the rest stays |
| 01 Summary | lede stays; the examples paragraph becomes a pointer to the recorded-examples note; guarantee table stays with shorter notes; closing paragraphs merge |
| 02 Motivation | one short scenario paragraph without the VP's name, the arithmetic table, one paragraph on the three questions, the fixture note as one sentence |
| 03 System design | plane table and diagram stay; the three prose paragraphs shrink; the status paragraph becomes two sentences pointing to the evidence note |
| 04 Decisions | six decisions stay as positions; implementation and source-convention detail shrink to what a maintainer needs to review the position |
| 04 Baseline fold | naming, shipped baseline, what the profile adds and package mechanics shrink to one short paragraph each; author names removed |
| 05 Consistency protocol | intro and diagram stay; four bullets shortened, capture links kept |
| 06 Proposed model | every fold stays; every `<pre><code>` block and the keys table stay; prose is compressed; the Alder consequence paragraphs and the "where the evidence stands" paragraphs are replaced by one sentence each pointing to the evidence note; non-goals list stays as the single such list |
| 07 Reproducibility | ladder and auditor table stay with shorter cells |
| 08 Acceptance | every check stays, each shortened |
| 09 Phases | intro shrinks to two paragraphs; at-a-glance table keeps five rows with shorter gate cells and no test dates; the Phase 0 report note and earlier-demos note shrink; the recorded-examples note (`#current-evidence`) stays as the one evidence block with all its pinned links; phase cards keep Outcome, Gate, Added and Out rows, shortened; risks table stays |
| 10 Closing and footer | closing stays shortened; the footer keeps one dated line without agent names |

## Checks that must stay green (offline)

- `rfc/spikes/bq-graph/tests/test_board_pack_links.py` (relative links, pinned blob links, canonical, forwarder list, both stubs, browser routes).
- `rfc/spikes/bq-graph/tests/test_fact_select_surfaces.py` (the asserted sentences on both pages, no digest or PR number on the landing page).
- New `rfc/spikes/bq-graph/tests/test_rfc_word_ceilings.py`: runs the counter and asserts the two ceilings; skips when node or Playwright is unavailable.
- `python3 rfc/full-demo/tools/check_full_demo.py` exit 0; `python3 rfc/demo/tools/check_cli_viewer.py` at its three baseline FAILs, no more.
- Full spike suite.

## Acceptance

1. Both ceilings hold in the counter's output, and the PR body quotes before and after numbers from it.
2. `git diff` shows no removed `id="…"` and no removed `href` among the ones the tests assert.
3. No personal name, job id, digest or pull-request number in either page's prose (OKF thread numbers only inside the source-conventions decision).
