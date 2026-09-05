# Plan — three-point comparison in the VP brief

## Scope and approved framing

Start from main at `50faaec` on `feat/rfc-bq-vp-3pts`, including merged PR 21. Follow Haiyuan's locked three-point brief in `/tmp/okf-vp-3pts-page/THREE_POINTS.md`: replayable context, explainable access and verifiable execution. Preserve the accepted Alder story and arithmetic.

| File | Change |
| --- | --- |
| `index.html` | Replace role cards with three paired comparisons; colocate guardrails; extend punchline; retain first-workload line; add access to pilot and proposal footer |
| `styles.css` | Equal comparison columns, labeled stacked pairs on mobile, print grouping |
| `STORY.md` | Preserve narrative; document why the three advantages are distinct and what each changes for Maya |
| `intent.md` | Comparison goal, guardrails, single pilot and delivery scope |
| `spec.md` | Comparison, honesty, usability and delivery acceptance criteria |
| `plan.md` | Execution and observed validation for this revision |

Keep the RFC entry blurb accurate. Leave full-demo, shared styles, dependencies and deployment configuration unchanged.

## Implementation and checks

1. Confirm branch/base, locked framing and existing evidence boundaries.
2. Keep the hero untouched. Build one runtime section with three numbered paired rows, each labeled KC + OKF and + BQ runtime, plus a short story takeaway.
3. Keep vector determinism and access/enforcement qualifiers visible beside their respective claims. Preserve the separate computation-receipt check for substituted queries and missing evidence.
4. Update the four page documents. Keep the empty-project case and extend the punchline without creating another essay.
5. Verify the static page in Chromium at 1280, 768, 375 and 320 px. Inspect screenshots, document height/word count, pair geometry, headings, keyboard access, local links, console errors and print. Check hero preservation and the locked content boundaries against source.
6. Run `git diff --check` and the existing `python3 rfc/full-demo/tools/check_full_demo.py` regression checker. Review only the six intended file changes. This verifies the page and existing evidence, not an implemented graph or authorization runtime.
7. Commit named files, push the branch, and create a PR against main. Save the actual session/model, validation, PR and HEAD under `/tmp/okf-vp-3pts-page/sessions.json`. Do not merge.

## Validation record

- Chromium: 526 visible words; 1,769 px tall at 1280 × 720. The hero and arithmetic match main at `50faaec` byte-for-byte; the hero still ends at y=626 before architecture.
- Desktop 1280 and tablet 768 px keep all three comparisons side by side. Mobile 375 and narrow 320 px stack each labeled pair together. No document/element horizontal overflow, invalid heading labels, authored scripts or external assets. Screenshots inspected.
- Visible keyboard focus and skip-to-main behavior pass. Page, stylesheet, RFC index and full-demo return HTTP 200; actual RFC and evidence-link navigation works. No console errors. New text/background combinations measure at least 5.91:1 contrast.
- Two-page A4 print inspected; each comparison pair stays together and remains legible without dark backgrounds.
- Targeted source checks confirm the three paired labels, locked guardrails, extended punchline and proposal/stub boundaries. Full-demo and the RFC index are unchanged.
- `python3 rfc/full-demo/tools/check_full_demo.py`: exit 0, all checks passed, including mutation fixtures and the clean-copy control. `git diff --check` passes.
- Session metadata confirms `gpt-6-astra` and resumed session `01a06e87-a6fd-7993-88b5-9c489219e68c`. QA artifacts and session record are under `/tmp/okf-vp-3pts-page/`. This is static-page verification, not evidence of an implemented graph, authorization or receipt service.
