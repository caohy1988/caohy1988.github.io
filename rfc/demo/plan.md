# Plan — why-slice rewrite of `/rfc/demo/`

Implement from this file. Branch `feat/okf-why-demo`, worktree
`/Users/haiyuancao/caohy1988.github.io-okf-why-demo` (from `origin/main` @
`47575a4`, PR 11 already merged). PR against `main`. Do not merge. Do not
touch SDK PR 474 (historical: it has since merged, 2026-09-03). Do not re-run the live ADK agent. Off #435.

SDK read-only: `/Users/haiyuancao/BigQuery-Agent-Analytics-SDK-okf-adapter`
@ `476d37dc9d4210a335c2f77e78003f6a5ebe2878`.

## Order

1. Recut the CLI tape to match Ask → Observe → Publish → Next agent
   (script at `/tmp/okf-why-demo/record_why.sh`). Real `python3
   examples/okf_bqaa_adapter/run.py`. 20–40s, 1280×720 H.264, last-frame
   poster = lookup JSON + payoff comment. Write
   `rfc/demo/cli/okf-bqaa-cli-transcript.txt`, `.cast`, `.gif`,
   `rfc/demo/okf-bqaa-cli.mp4`, `rfc/demo/okf-bqaa-cli-poster.png`.
2. Rewrite `index.html`: locked hero title + subtitle; drop the SHA live
   strip from above the fold; retitle stepper Ask / Observe / Publish /
   Next agent; walkthrough captions = one sentence per beat; collapsed
   **How this was built / IDs** carries CLI, SHA triple, histogram, PR 474,
   `Object.hasOwn`; honesty card kept; meta/og match the question + payoff.
3. Rewrite `app.js` beat bodies per spec.md. Beat 1 = trap vs current
   metric. Beat 2 = observer-visible titles (rank 1, exclusion, unproven
   receipt), not a 180-row dump. Beat 3 = 8 stubs + “handle a KC entry
   would expose” + leftover Dataplex labelled prior. Beat 4 = lookup
   payoff first, fail-closed second. Keep `#beat=1..4`, keys, try-a-ref
   `Object.hasOwn`. Do **not** run `adapter.js` for live identities.
4. Small `styles.css` only if the hero/beats need it. Keep RFC visual
   language. Do not turn the page into a spec sheet.
5. Rewrite `README.md` and `WALKTHROUGH.md` in why-language. Update
   `rfc/index.html` Prototype callout (question + payoff, 2–4 sentences).
6. Update `rfc/demo/tools/check_cli_viewer.py` per spec.md and make it pass.
   Grep for forbidden hero SHA-wall / consume-as-Observe / germany-as-SoT /
   `computed in-browser` / `gemini-2.5`.
7. Serve `python3 -m http.server 8000` from the worktree root and spot-check
   beats 1–4 (no console errors). Do not re-run `--live`.
8. Commit as Haiyuan Cao `<raincoatrun@gmail.com>` (already git config).
   Do not amend `47575a4`. Message:

   `feat(rfc): retell /rfc/demo/ as why BQAA→OKF helps the next agent`

   Push `feat/okf-why-demo`, `gh pr create` against
   `caohy1988/caohy1988.github.io` `main`. Print DONE, HEAD SHA, PR URL.
   **Do not merge.** Do not start Codex/Kimi.

## Guardrails

- No `fetch()` to any non-same-origin URL (Google Fonts stylesheet link is
  already there; do not add GCP calls).
- Never dump `live_observe_agent_events.json` (494KB) onto Pages.
- Never `--live` the observe agent. Never pad events. Off #435.
- Keep `gemini-3.8-flash`; grep for `2.5` before commit.
- Do not invent a different finance story.
- Do not claim a Knowledge Catalog write for this CLI path.
- Do not touch SDK PR 474 (historical guardrail; it merged 2026-09-03 independently of this repo).
