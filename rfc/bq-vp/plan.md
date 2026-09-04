# Plan — a concrete story with a clear BigQuery case

## Scope

| File | Change |
| --- | --- |
| `rfc/bq-vp/index.html` | Both numbers in the hero, one arithmetic comparison, three named roles with BigQuery emphasized, punchline, ask and honesty footer |
| `rfc/bq-vp/styles.css` | Compact editorial layout; responsive figure, keyboard focus and print styling |
| `rfc/bq-vp/STORY.md` | Invented scenario, arithmetic, rationale and counterfactual boundaries |
| `rfc/bq-vp/intent.md` | Customer-first goal and pilot ask |
| `rfc/bq-vp/spec.md` | Story, honesty, scope and usability requirements |
| `rfc/bq-vp/plan.md` | Execution and validation record |
| `rfc/index.html` | Existing link remains accurate; unchanged in the follow-up |

Keep `/rfc/full-demo/`, dependencies and deployment configuration unchanged. Use gpt-6-astra only.

## Implementation

1. Keep Alder, Maya, the deadline, $4 million decision and the 118% / 96% arithmetic. Put all of them in the hero, with both percentages in the headline.
2. Replace the input ledger with one comparison showing the mistaken addition of new-customer ARR. Name Catalog, OKF and BigQuery directly in the technical section, and explain execution, job/context/result receipts, attribution and access grants.
3. Update `STORY.md`, intent and spec to capture the sharper framing. Keep the unbuilt RFC label and compact evidence footer.
4. Verify desktop, tablet and narrow mobile layout, arithmetic, 30-second skim content, keyboard access, links, contrast and print. Run the existing full-demo checker and `git diff --check`.
5. Commit and push the six changed files to existing PR 20 on `feat/rfc-bq-vp-story`. Refresh the PR description to match the final framing and measured page. Save follow-up session/validation metadata under `/tmp/okf-vp-story/`. Print the new HEAD; do not create another PR or merge.

## Acceptance checks

- A skim answers: who is Maya, why does 9 a.m. matter, why is 118% wrong, what is 96%, and what would the proposed runtime add?
- Arithmetic: `(9.6 + 2.2) / 10 = 1.18`; `9.6 / 10 = .96`. All figures use ARR consistently.
- The illustrative label appears before the story; proposal labeling precedes all runtime promises; the footer separates the unrelated recorded demo from this invented scenario.
- Main page is roughly 400–500 visible words, around two desktop screens, with three named roles and one ask. No real or invented execution IDs appear in the story.
- HTTP 200, correct navigation, no horizontal overflow at desktop/768/375/320 widths, no script requirement, usable heading order and keyboard focus.
- Relevant existing checker passes. No new test suite for this reversible editorial change; browser inspection and targeted checks provide the relevant validation.

## Initial validation — HEAD 691ad08

- Chromium: 416 visible words; page height 1,345 px at 1280 × 720. The complete correction figure ends at y=665, within the first viewport.
- Responsive checks at 1280, 768, 375 and 320 px: no document or element horizontal overflow. Desktop, tablet and mobile screenshots inspected; fixed a hidden-line-break spacing issue and the narrow-screen headline wrap.
- Keyboard: visible focus on links; skip link moves focus to `main`; RFC entry and evidence deep-dive navigation work. Every page/stylesheet link returns HTTP 200. Heading IDs and labels are valid.
- No authored scripts or external assets. Browser network shows only local HTML/CSS, with no console errors. Checked text color pairs exceed 4.5:1 contrast. A4 print output inspected across two pages with no clipping.
- Decimal arithmetic checks pass for both 118% and 96%. All fictional and proposal labels reviewed against `STORY.md` and the full-demo status table.
- `python3 rfc/full-demo/tools/check_full_demo.py`: exit 0, all checks passed, including the negative mutation fixtures and the clean-copy control. `/rfc/full-demo/` has no diff.
- `git diff --check`: passed. Only the seven scoped files are staged for the delivery commit.
- QA artifacts and the actual Codex session ID are saved in `/tmp/okf-vp-story/`; session metadata confirms `gpt-6-astra`.

## Sharpening validation — follow-up (HEAD 7c5c243)

- Chromium (independent re-review): ~420 visible words; page height ~1,312 px at 1280 × 720 (~1.8 viewports). Hero carries Maya / Alder / five-minute deadline / \$4M / 118% / 96% before architecture language; arithmetic figure teaches the new-customer trap on a 30-second skim.
- Responsive checks at 1280, 768, 375 and 320 px: no document or element horizontal overflow (headless Chromium).
- HTTP 200 on page + stylesheet; zero console errors; heading order valid (h1→h2→h3).
- Decimal arithmetic: `(9.6 + 2.2) / 10 = 1.18`; `9.6 / 10 = 0.96`.
- `python3 rfc/full-demo/tools/check_full_demo.py`: exit 0 (including mutation fixtures). `/rfc/full-demo/` untouched.
- `git diff --check`: clean for the polish commit.
- Artifacts under `/tmp/okf-vp-story/sharpen/`; Codex session `01a06e87-a6fd-7993-88b5-9c489219e68c` (`gpt-6-astra`).
