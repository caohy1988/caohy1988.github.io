# Plan — a system diagram for the retention story

## Scope

Start from main at `c370007` on `feat/rfc-board-pack-diagram`. Add one figure at the top of the existing Technical design body at `/rfc/board-pack/`. Preserve all existing story, comparison and design prose, the native disclosure, the print visibility fix, the redirect and full-demo. Keep the footer removed.

## Implementation

1. Draw three numbered flows with inline SVG: replayable context, explainable access, and verifiable execution. Tie the source graph, requesting agent and declared calculation to Maya’s illustrative 118%/96% near-miss. Show current policy gating retrieval and missing/substituted execution staying unproven.
2. Use shared SVG node definitions so labels stay consistent between the wide and stacked mobile layouts. Match the green/cream brief palette, give each visible SVG an accessible title/description, and label the figure proposed/illustrative.
3. Preserve the adjacent-body disclosure mechanism and its explicit print visibility override. Print the diagram in monochrome, keeping it together and retaining the three prose design sections as the deeper read.
4. Update intent/spec to capture the diagram's role and current delivery scope.

## Verification

- Removing the inserted figure must reproduce the original page byte-for-byte. No changes to the redirect, RFC index, full-demo or authored scripts.
- Check 1280, 768, 375 and 320 px, open and closed: readable labels, unclipped SVG text/arrows, no horizontal overflow, one visible diagram layout, valid SVG references and accessible labels.
- Check native keyboard toggling and focus. Inspect desktop/mobile diagrams and closed-state Chromium PDF; check Firefox/WebKit print-media visibility to preserve the prior print fix.
- Run `git diff --check`. No new test suite or unrelated runtime tests for this static illustration.

## Delivery

Commit named files, push the branch and create a new PR against main. Record session/model, validation, PR URL and HEAD under `/tmp/okf-vp-diagram/`. Do not merge. Opus + Kimi are the requested review gate; do not claim those reviews have run.

## Validation record

- Removing the figure reproduces the prior HTML byte-for-byte. Redirect, RFC index and full-demo are untouched. The collapsed page remains 532 visible words and 1,795 px tall at 1280 × 720; no authored scripts or console errors.
- Chromium 145, Firefox 146.0.1 and WebKit 26.0 pass at 1280, 768, 375 and 320 px in both disclosure states. SVG references/IDs resolve, text fits node bounds, exactly one diagram layout is visible, accessible titles/descriptions resolve, and no horizontal overflow occurs. Desktop/mobile diagrams inspected; node body text is approximately 15 px at 375 px viewport width.
- Native Enter/Space toggling and visible focus pass. Closed-state print-media checks in all three engines show the wide diagram in monochrome along with the prose and pilot. Chromium closed/open PDF text is identical; the figure stays together in the three-page A4 output, which was visually inspected. WebKit was tested, not the Safari app.
- `git diff --check` passes. Screenshots, PDFs and the engine/viewport record are under `/tmp/okf-vp-diagram/`. These checks cover the static illustration, not the proposed runtime implementation.
