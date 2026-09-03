# Plan — ask-clarify copy slice

Worktree `/Users/haiyuancao/caohy1988.github.io-okf-ask-clarify`, branch
`feat/rfc-demo-ask-clarify` off `main` `ea60db5`. PR against
`caohy1988/caohy1988.github.io` `main`. Do not merge this PR. SDK PR 474 has
merged (2026-09-03); do not touch it, and do not re-record the tape.

## Order

1. Commit `ask-clarify-intent.md`, `ask-clarify-spec.md`, `ask-clarify-plan.md`.
2. `rfc/demo/index.html`: add the ask callout under `.badges` (pre-`<main>`);
   extend walkthrough caption 1 with one clause after the locked sentence.
3. `rfc/demo/app.js` `renderAsk()`: insert the "What this demo is asking" block
   before `.traps`. Keep `must(...)` line and both traps.
4. `rfc/demo/README.md`: extend "1. **Ask.**" and add "## What this demo is
   asking" after "## The question".
5. `rfc/demo/WALKTHROUGH.md`: extend "### 1 · ASK" with the framing.
6. `rfc/index.html` Prototype callout: merge one clause into an existing
   sentence; sentence count must stay ≤ 6.
7. `python3 rfc/demo/tools/check_cli_viewer.py` → exit 0; `node --check`.
8. Commit, `git push -u origin HEAD`, `gh pr create` against `main`.

## Guardrails

- No mp4 / poster / cast / transcript changes.
- No HITL or sentiment feature, not even as a stub.
- No "Catalog was written" claim; keep "did not write Knowledge Catalog".
- Hero `<h1>` and `.subtitle` untouched.
