# Plan — BQAA → derived OKF prototype

Implement from this file. Repo: `caohy1988/caohy1988.github.io`, branch `feat/rfc-okf-bqaa-adapter-demo`, worktree `/Users/haiyuancao/caohy1988.github.io-okf-demo`.

## Layout

```
rfc/intent.md          (already committed)
rfc/spec.md
rfc/plan.md
rfc/index.html         (add Prototype demo callout + link)
rfc/demo/index.html    (clickable four-beat UI)
rfc/demo/app.js
rfc/demo/styles.css    (RFC tokens; keep it small)
rfc/demo/README.md     (how to run locally, honesty labels)
rfc/demo/fixture/      (copy of okf-phase0-mvp/fixture/bundle + golden identities)
rfc/demo/traces/bqaa-germany.json
rfc/demo/derived/      (precomputed derived bundle + derived identities if JS hashing is incomplete)
rfc/demo/okf-bqaa-e2e.mp4  (NOT this PR — record only after Codex+Kimi dual LGTM)
```

## Implementation order

1. Copy Phase 0 fixture + `golden/identities.json` + `golden/receipt.json` into `rfc/demo/fixture/` (and receipts). Do not edit authored markdown except to add a `derived: false` note in README.
2. Write `traces/bqaa-germany.json`: 8–15 observer events. Include `attributes.context_ref` on completed tools. Omit query, principal, paths, `concept_version_id`.
3. Adapter in `app.js`: map traces → derived bundle object. Minimum derived concepts: one metric stub, one policy stub, one computation stub, one log line that says "derived from BQAA observation, not authored." `bundle_key = bqaa-derived-cymbal-demo`.
4. If hashing in JS is too large for this slice, precompute derived identities with a one-off run of `vectors_gen.py` (read-only copy; do not mutate `okf-phase0-mvp/golden/`). Check the precomputed JSON into `rfc/demo/derived/identities.json`. Comment the generator command in README.
5. Four-beat UI. Default beat 1. Buttons: Observe / Adapt / Project / Consume. Project beat splits Catalog vs BigQuery. Consume beat is an **ADK** agent on **`gemini-3.8-flash`**: show model id in chrome, tool JSON + `context_ref` + UNVERIFIABLE receipt. If you add `rfc/demo/adk/` (Python Agent), default `DEMO_MODEL_ID=gemini-3.8-flash`. Never `gemini-2.5-flash`.
6. Callout on `rfc/index.html` near the Phase 0 MVP note: badge "Prototype" linking to `./demo/`. Do not restyle the whole RFC.
7. `rfc/demo/README.md`: derived/demo honesty, no live GCP, never-emit list, local open (`npx serve` or just file:// if it works).
8. Polish the UI to evalbench quality: masthead, stepper, two-column Project, model badge. Not a raw JSON page.
9. Do **not** record in this PR. Haiyuan: wait for Claude + Codex + Kimi to align (dual LGTM) before any mp4. Ship the UI, open the PR, stop.

## Verify

- Open `rfc/demo/index.html` (or a local static server). Click all four beats. No JS exceptions. UI must look like a product (evalbench bar), not a spec dump.
- No mp4 in this PR. Recording is a follow-up after dual LGTM.
- Grep demo JS + traces for `concept_version_id`, `query`, `principal` in **emitted** tool payloads (UI inspector of authored files is allowed).
- `git diff rfc/index.html` is a small callout, not a rewrite.
- No `.env`, no ADC, no `gcloud` from the page.

## Ship

```
git add rfc/
git commit -m "feat(rfc): clickable BQAA→derived OKF prototype demo"
git push -u origin feat/rfc-okf-bqaa-adapter-demo
gh pr create --repo caohy1988/caohy1988.github.io --base main --title "feat(rfc): BQAA → derived OKF prototype demo" --body "..."
```

PR body must link `rfc/intent.md`, `rfc/spec.md`, `rfc/plan.md`, and say Haiyuan merges to publish https://caohy1988.github.io/rfc/demo/. Do not merge. Do not start Codex/Kimi (EM does that after the PR URL exists).

Implementer: Claude Code Fable 5.1.
`claude -p --permission-mode auto --output-format text --model claude-fable-5-1`
