# Plan — BigQuery VP one-pager

## Files

| File | Purpose |
| --- | --- |
| `rfc/bq-vp/intent.md` | Audience, problem, thesis, separation from full demo |
| `rfc/bq-vp/spec.md` | Simplicity rules and evidence boundaries |
| `rfc/bq-vp/plan.md` | Implementation scope and acceptance checks |
| `rfc/bq-vp/index.html` | Complete static story, metadata, source links, and deep-dive CTA |
| `rfc/bq-vp/styles.css` (if needed) | Page-local responsive styling; no JavaScript |
| `rfc/index.html` | Clear link near the masthead to the new VP page |

No full-demo edits, shared CSS changes, dependencies, or deployment changes.

## Implementation

1. Inspect the full demo's validated copy and linked captures. Preserve qualifiers alongside the observations and proposals.
2. Have `gpt-6-astra` implement the new HTML/CSS within the supplied scope. Keep documentation, RFC navigation, integration, and shipping with the primary session.
3. Verify the integrated page with a local static server and real browser. Capture desktop and mobile screenshots outside the repository.
4. Commit only the listed files, push `feat/rfc-bq-vp`, and use `gh pr create --base main`. Stop once the PR exists; report its URL and HEAD SHA.

## Acceptance checks

- `/rfc/bq-vp/` returns HTTP 200 from a repository-root static server. Directory `index.html` routing matches the existing Pages structure.
- Desktop 1280 × 720: question, thesis, and three takeaways appear above the fold. Mobile 375 × 812 and narrow 320 px: readable layout, no horizontal overflow or overlapping persistent notice.
- Three or four short sections; story stands alone without clicking. Aim for at most 400 visible words (under 90 seconds at 270 words/minute; a comprehension proxy, not a user-study result).
- No stepper, disclosure controls, matrix, backup stories, script, or external page-load requests.
- All local source links and the deep-dive CTA resolve. The new RFC masthead link reaches the VP page. Keyboard focus and heading order are usable.
- Confirm quotations against committed sessions; label different prompts/tools, stub/no execution, RFC proposal, and unbuilt IAM honestly.
- Run `python3 rfc/full-demo/tools/check_full_demo.py` unchanged and `git diff --check`. Confirm no diff under `rfc/full-demo/`.
- No new unit-test suite: this is static editorial HTML/CSS. Browser inspection, link checks, source verification, and the existing evidence checker provide the relevant proof.
- Save actual Codex session identifiers to `/tmp/okf-vp-onepager/sessions.json`; keep screenshots and other QA artifacts in that directory, out of the commit.
- Verify the PR targets `main`, uses `feat/rfc-bq-vp`, and exists on GitHub. Pages deployment remains after merge; this task does not merge or claim a live deployment.
