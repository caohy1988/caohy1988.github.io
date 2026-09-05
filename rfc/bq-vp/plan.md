# Plan — connect the customer story to all three runtime comparisons

## Scope

Start from main at `d011a0d` on `feat/rfc-bq-vp-story3`, including merged PR 22. Keep the customer/runtime brief at `/rfc/bq-vp/`. The story should introduce the three gaps answered by the existing comparison, and the page should use neutral audience framing.

| File | Change |
| --- | --- |
| `index.html` | Revise opening and near-miss; connect the access takeaway to the total-ARR asset; neutral title and pilot eyebrow; trim repeated runtime introduction |
| `STORY.md` | Add the three story gaps and distinguish unexplained access from a permissions violation |
| `intent.md` | Customer/runtime audience, story-to-comparison mapping and current delivery scope |
| `spec.md` | Preserve headline/arithmetic; require all three gaps, neutral labels and existing honesty boundaries |
| `plan.md` | Current implementation and observed verification |
| `../index.html` | Rename the page link to Board-pack near-miss |

Leave the arithmetic figure, three comparison pairs, guardrail notes, extended punchline and first-workload case intact. Keep the product masthead and Why BigQuery thesis. Do not edit full-demo or its audience-specific show notes. CSS changes are only needed if text wrapping requires them.

## Implementation and checks

1. Confirm branch/base and scoped instructions. Preserve the headline and arithmetic figure from main.
2. Tell the near-miss through Maya's unanswered questions: no pinned linked context, no clear explanation of this agent's access to the total-ARR asset, and no execution receipt tying the query/result to the declared retention calculation. Keep this in the existing story paragraph.
3. Remove product-executive audience labels from the title, pilot eyebrow, RFC link and local documents. Retain Maya's Finance job title and product terminology.
4. Verify in Chromium at 1280, 768, 375 and 320 px: text wrapping, comparison geometry, accessible headings, keyboard navigation, local links, console errors and two-page print. Check that the new prose does not obscure the arithmetic or become a second essay.
5. Run targeted source checks, `git diff --check` and the existing `python3 rfc/full-demo/tools/check_full_demo.py` regression checker. Confirm the full-demo tree is unchanged. No new test suite for this static editorial change.
6. Commit named files, push the branch and create a PR against main. Save session/model, validation, PR URL and HEAD to `/tmp/okf-vp-story3/sessions.json`. Do not merge. The requested review gate is Opus + Kimi; do not claim reviews have run.

## Validation record

- Chromium: 566 visible words; 1,820 px tall at 1280 × 720. The full hero ends at y=674; the arithmetic figure ends at y=564. The expanded story fits before the technical section in the first desktop viewport.
- The headline and arithmetic figure match main at `d011a0d` byte-for-byte. Targeted checks confirm all three story gaps, preserved comparison notes/decorative-number accessibility, and absence of product-executive audience labels from the page, RFC link and local docs.
- Desktop 1280, tablet 768, mobile 375 and narrow 320 px: no document/element horizontal overflow, invalid heading labels or authored scripts; comparison pairs retain their intended side-by-side/stacked geometry. Desktop/mobile screenshots inspected. CSS is unchanged.
- Keyboard focus and skip-to-main behavior pass. The neutral Board-pack near-miss link navigates from the RFC index to the unchanged URL; the evidence link reaches full-demo. No console errors.
- Two-page A4 print inspected; each comparison pair stays together. Headline, arithmetic, first-workload case, punchline and honesty footer are preserved. The full-demo tree, including show notes, is unchanged.
- `python3 rfc/full-demo/tools/check_full_demo.py`: exit 0, all checks passed, including mutation fixtures and clean-copy control. `git diff --check` passes.
- Session metadata confirms `gpt-6-astra` and resumed session `01a06e87-a6fd-7993-88b5-9c489219e68c`; artifacts are under `/tmp/okf-vp-story3/`. This verifies a static editorial change, not implementation of the proposed runtime.
