# Plan — replace the thesis with a customer moment

## Scope

| File | Change |
| --- | --- |
| `rfc/bq-vp/index.html` | Alder board-pack story, arithmetic figure, three proposed beats, punchline, ask, honesty footer |
| `rfc/bq-vp/styles.css` | Compact editorial layout; responsive figure, keyboard focus and print styling |
| `rfc/bq-vp/STORY.md` | Invented scenario, arithmetic, rationale and counterfactual boundaries |
| `rfc/bq-vp/intent.md` | Customer-first goal and pilot ask |
| `rfc/bq-vp/spec.md` | Story, honesty, scope and usability requirements |
| `rfc/bq-vp/plan.md` | Execution and validation record |
| `rfc/index.html` | Update the existing VP link title and blurb |

Keep `/rfc/full-demo/`, dependencies and deployment configuration unchanged. Use gpt-6-astra only.

## Implementation

1. Read the existing RFC and full-demo evidence boundaries. Invent one independent story with checkable arithmetic; record the rationale in `STORY.md`.
2. Write the complete static story and compact responsive design. Put the company, human, deadline and wrong number ahead of the technical thesis.
3. Verify the served page in Chromium at desktop, tablet and narrow mobile widths. Inspect screenshots, page length, calculation labels, keyboard navigation, links, console and network behavior. Check the print view.
4. Run the unchanged full-demo evidence checker and `git diff --check`. Confirm only the seven scoped files changed.
5. Commit the final change, push `feat/rfc-bq-vp-story`, and use `gh pr create --base main`. Save actual session identifiers to `/tmp/okf-vp-story/sessions.json`. Report PR URL and HEAD; do not merge.

## Acceptance checks

- A skim answers: who is Maya, why does 9 a.m. matter, why is 118% wrong, what is 96%, and what would the proposed runtime add?
- Arithmetic: `(9.6 + 2.2) / 10 = 1.18`; `9.6 / 10 = .96`. All figures use ARR consistently.
- The illustrative label appears before the story; proposal labeling precedes all runtime promises; the footer separates the unrelated recorded demo from this invented scenario.
- Main page is 400–550 visible words, around two desktop screens, with three runtime beats and one ask. No real or invented execution IDs appear in the story.
- HTTP 200, correct navigation, no horizontal overflow at desktop/768/375/320 widths, no script requirement, usable heading order and keyboard focus.
- Relevant existing checker passes. No new test suite for this reversible editorial change; browser inspection and targeted checks provide the relevant validation.

## Validation record

- Chromium: 416 visible words; page height 1,345 px at 1280 × 720. The complete correction figure ends at y=665, within the first viewport.
- Responsive checks at 1280, 768, 375 and 320 px: no document or element horizontal overflow. Desktop, tablet and mobile screenshots inspected; fixed a hidden-line-break spacing issue and the narrow-screen headline wrap.
- Keyboard: visible focus on links; skip link moves focus to `main`; RFC entry and evidence deep-dive navigation work. Every page/stylesheet link returns HTTP 200. Heading IDs and labels are valid.
- No authored scripts or external assets. Browser network shows only local HTML/CSS, with no console errors. Checked text color pairs exceed 4.5:1 contrast. A4 print output inspected across two pages with no clipping.
- Decimal arithmetic checks pass for both 118% and 96%. All fictional and proposal labels reviewed against `STORY.md` and the full-demo status table.
- `python3 rfc/full-demo/tools/check_full_demo.py`: exit 0, all checks passed, including the negative mutation fixtures and the clean-copy control. `/rfc/full-demo/` has no diff.
- `git diff --check`: passed. Only the seven scoped files are staged for the delivery commit.
- QA artifacts and the actual Codex session ID are saved in `/tmp/okf-vp-story/`; session metadata confirms `gpt-6-astra`.
