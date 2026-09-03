# Plan — static viewer of the SDK CLI path

Implement from this file. Branch `feat/okf-cli-viewer`, worktree
`/Users/haiyuancao/caohy1988.github.io-okf-cli-viewer`. PR against `main`.
Do not merge. Do not touch SDK PR 474.

Assets already in the worktree (do not re-record unless broken):

- `rfc/demo/cli/okf-bqaa-cli-transcript.txt`
- `rfc/demo/cli/okf-bqaa-cli.cast`
- `rfc/demo/cli/okf-bqaa-cli.gif`
- `rfc/demo/okf-bqaa-cli.mp4` (live-adapter proof)
- `rfc/demo/live/observe/{live.json,live_identities.json,mapping.json,snapshot.json}`
- `rfc/demo/okf-bqaa-e2e.mp4` (keep, relabel prior fixture)

## Order

1. Write `rfc/demo/tools/check_cli_viewer.py` against the committed snapshot +
   transcript + index/app (will fail until the page rewrite).
2. Rewrite `index.html`: masthead, badges, live observe strip (agent
   `okf_rfc_observe_agent`, session `f21ee192-…`, context_ref
   `okf:env-observe#674153c572f6`), identity strip derived label, walkthrough
   (CLI mp4 first), honesty card, meta/og. Relabel old consume IDs.
3. Rewrite `app.js` load path: fetch `live/observe/live.json`,
   `live_identities.json`, `snapshot.json`, `mapping.json`, and the CLI
   transcript (as text). Do **not** run `adapter.js` to produce the live
   derived triple. Beats 1–4 per spec.md.
4. Small `styles.css` additions if needed (CLI transcript `<pre>`, observe
   histogram). Keep RFC visual language.
5. Rewrite `README.md` and `WALKTHROUGH.md`. Update `rfc/index.html`
   Prototype callout (observe agent + CLI adapt; 2–4 sentences max).
6. Keep `adapter.js` / germany trace only behind SYNTHETIC labels.
7. Run `python3 rfc/demo/tools/check_cli_viewer.py`. Grep for the forbidden
   hero strings. Existing germany hashing checks may still be run as
   labelled extras.
8. Commit as Haiyuan Cao `<raincoatrun@gmail.com>`, push
   `feat/okf-cli-viewer`, `gh pr create` against `caohy1988/caohy1988.github.io`
   `main`. Print DONE, HEAD SHA, PR URL. Do not merge. Do not start Codex/Kimi.

## Guardrails

- No `fetch()` to any non-same-origin URL.
- Never dump `live_observe_agent_events.json` (494KB) onto Pages.
- Never `--live` the observe agent. Never pad events. Off #435.
- Keep `gemini-3.8-flash`; grep for `2.5` before commit.
- Commit message: `feat(rfc): static CLI viewer of BQAA → OKF (observe 180)`
