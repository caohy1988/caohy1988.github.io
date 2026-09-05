# Plan — deterministic OKF-graph retrieval in the VP brief

## Scope

Start from main at `bf92ee8` on `feat/rfc-bq-vp-det-retrieval`, using the resumed gpt-6-astra session. Preserve the accepted Alder story and arithmetic; change the explanation of BigQuery's value from primarily computation beside revenue data to replayable retrieval over an OKF graph projection.

| File | Change |
| --- | --- |
| `rfc/bq-vp/index.html` | Retrieval heading, three graph roles, determinism boundary, separate receipt types, empty-project case, locked punchline and pilot ask |
| `rfc/bq-vp/styles.css` | Only if the longer retrieval copy needs responsive adjustments |
| `rfc/bq-vp/STORY.md` | Story-to-graph connection, retrieval contract, receipt distinction and empty-BigQuery rationale |
| `rfc/bq-vp/intent.md` | Replayable-context goal and scope |
| `rfc/bq-vp/spec.md` | Retrieval, honesty and usability acceptance criteria |
| `rfc/bq-vp/plan.md` | Implementation and observed validation |

Keep the illustrative RFC masthead link accurate. Do not edit `/rfc/full-demo/`, shared styles, dependencies or deployment configuration.

## Implementation

1. Inspect the current page and evidence boundaries. Confirm branch/base and session model.
2. Preserve the hero and arithmetic. Reframe the runtime section around Catalog discovery, OKF authorship, and BigQuery graph projection plus deterministic retrieval. Follow retrieval with the separate computation-evidence boundary.
3. Update the four local Markdown documents. Keep proposal/stub labels and record determinism preconditions precisely.
4. Verify the static page in Chromium at desktop, tablet and narrow mobile widths. Inspect screenshots, word count, page length, heading order, keyboard access, links and print. Review the context/number distinction manually; do not claim an implemented retrieval test.
5. Run the existing full-demo checker and `git diff --check`. Confirm the hero and full demo are unchanged and the diff stays within the intended page/docs.
6. Commit, push this branch, and use `gh pr create --base main`. Record session ID, new HEAD and PR URL in `/tmp/okf-vp-det/sessions.json`. Do not merge.

## Acceptance checks

- Hero still conveys Maya/Alder, the deadline, $4 million decision and 118% → 96% before architecture.
- A skim of the runtime explains why discovering the concept is different from deterministically selecting linked context. BigQuery is useful as the host of the graph projection, including an initially empty project.
- Same-context guarantee is scoped to fixed query/publication/parameters/fact versions/access scope/order. It is not a promise of identical model answers.
- Retrieval receipts describe selected context; computation receipts describe metric execution. Missing execution evidence leaves the number unproven.
- Graph-over-OKF and retrieval receipts are explicitly proposed. No new execution/attestation or Phase A completion is implied.
- Around two desktop viewports and 400–500 visible words; no mobile horizontal overflow, script dependency or external asset loading.
- Existing evidence checker and whitespace check pass. QA artifacts stay outside the repository. No new test suite for a static editorial change.

## Validation record

- Chromium: 437 visible words; 1,404 px tall at 1280 × 720. The full arithmetic figure ends at y=540; the hero ends at y=626, before architecture.
- The hero matches main at `bf92ee8` byte-for-byte. Both arithmetic results and the exact locked punchline pass targeted checks.
- Desktop 1280, tablet 768, mobile 375 and narrow 320 px: no document/element horizontal overflow or authored scripts; only the local stylesheet loads. Screenshots inspected. Text contrast pairs exceed 4.5:1.
- HTTP 200 for page, stylesheet, RFC and deep dive. Actual navigation through both links works. Keyboard focus is visible, the skip link focuses `main`, heading order and labels are valid, and the page has no console errors.
- A4 print inspected across two pages; corrected the BigQuery column's print padding. Screen styling is unchanged.
- `python3 rfc/full-demo/tools/check_full_demo.py`: exit 0, all checks passed, including mutation fixtures and the clean-copy control. Full demo and RFC entry page are unchanged.
- Manual review confirms fixed-input retrieval semantics, the empty-project projection requirement, separate receipt types and explicit unbuilt Graph/retrieval-receipt labels. This is page verification, not a test of an implemented graph runtime.
- `git diff --check` passed. Session metadata confirms `gpt-6-astra` and session `01a06e87-a6fd-7993-88b5-9c489219e68c`; artifacts are under `/tmp/okf-vp-det/`.

## Opus r1 fix (post a3daa3c)

- Runtime opener: similarity search as candidate finder (not a VECTOR_SEARCH own-goal); replayability payoff tied to Maya’s 118% (same definition/cohort/declared computation — no total-ARR substitute).
- Empty-BQ line: “facts that retrieval needs.”
