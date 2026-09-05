# Plan — optional runtime design at the board-pack address

## Scope

Start from main at `de43648` on `feat/rfc-retention-runtime-details`. Move the brief and its local documents/styles to `/rfc/board-pack/`. Preserve the Alder hero, arithmetic, three comparisons, first-workload line, punchline, pilot ask and honesty labels. Keep the page static and the footer removed.

## Implementation

1. Add one native Technical design disclosure after the comparisons and first-workload line. Keep it closed by default, with an RFC proposal label. Explain the proposed retrieval, current-access and computation-receipt mechanisms from STORY, intent and spec.
2. Style the disclosure to match the dark runtime section. Keep native keyboard semantics, visible focus and a decorative open/closed indicator. Use print CSS to expose the body regardless of screen state and keep each design subsection readable across page breaks.
3. Move all six brief files to `rfc/board-pack/`; update the canonical and RFC index href. Leave an immediate meta-refresh redirect with a canonical and fallback link at `rfc/bq-vp/index.html`.
4. Update the local docs for the disclosure and new address. Search repository references; change any full-demo href only if it points to the old brief. Do not change full-demo content.

## Verification

- Source comparison: removing the new disclosure and reversing the canonical change should reproduce the previous brief exactly. The hero, arithmetic, comparisons and notes must be unchanged.
- Verify redirect markup and actual browser navigation from both the RFC index and the old URL. Scan local references and labels; legacy-path mentions should only explain the redirect.
- Chromium at 1280, 768, 375 and 320 px, both collapsed and expanded: check horizontal overflow, readable wrapping, accessible labels and absence of console errors.
- Test Tab focus and Enter/Space open/close; inspect the focus ring. Print from closed and open states, confirm all three design sections appear, and inspect page breaks.
- Run `git diff --check` and confirm the full-demo tree is unchanged. Use targeted source/browser checks for this static page; no new test suite or unrelated runtime tests.

## Delivery

Commit named files, push the branch and create a PR against main. Save the session/model, validation, PR URL and HEAD under `/tmp/okf-vp-details/`. Do not merge. Opus + Kimi are the requested review gate; do not claim those reviews have run.

## Validation record

- Source comparison confirms the prior brief is unchanged outside the new disclosure and canonical URL. The RFC index changes only its href. Full-demo is unchanged; remaining legacy-path references document the redirect.
- Chromium at 1280, 768, 375 and 320 px passes in both states: no horizontal overflow, invalid heading references or authored scripts; no console errors. Collapsed: 532 visible words and 1,795 px tall at 1280 × 720. Expanded: 771 words. Desktop/mobile and focus screenshots inspected.
- Tab reaches the native summary; Enter and Space both open and close it. The focus ring is visible; the skip link focuses main. Both the RFC index link and old URL reach `/rfc/board-pack/`, with the updated canonical.
- Closed/open A4 print text is identical and includes all three design sections and the pilot. The expanded content fits two pages; print layout inspected. Initial print verification used Chromium 145; the P2 follow-up below removes the reliance on `::details-content`.
- `git diff --check` passes. Session and QA artifacts: `/tmp/okf-vp-details/`. This validates the static page, not implementation of the proposed runtime.

## P2 — print independently of the native disclosure slot

Keep one content block adjacent to the native details toggle, inside a shared visual frame. The summary identifies that body with `aria-controls`; `[open] + .design-body` controls screen visibility. Print explicitly resets the real body's display, height, max-height, visibility, content-visibility and overflow. The native pseudo-element remains a progressive enhancement, not the print fallback. No JavaScript or duplicated content is introduced; all page text is unchanged.

Verified closed-state Chromium 145 PDF and Firefox 146.0.1 / WebKit 26.0 print-media layouts: Retrieve, Evaluate, Validate and the pilot render, including with native pseudo-element visibility disabled. Chromium PDF text matches the previous two-page output. Safari itself was not automated; WebKit is the tested engine. Native Enter/Space, focus, the control relationship and desktop/mobile open/closed states pass in all three engines. Evidence is under `/tmp/okf-vp-details/p2/`. Push to PR 25 and stop; no merge or re-review wait.
