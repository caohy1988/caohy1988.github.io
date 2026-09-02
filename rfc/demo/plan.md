# Plan — live GCP full demo page

Implement from this file. Branch `feat/rfc-okf-live-gcp`, worktree `/Users/haiyuancao/caohy1988.github.io-okf-e2e`. PR against `main`, do not merge.

## Files

```
rfc/demo/intent.md, spec.md, plan.md      this slice
rfc/demo/live/live.json                  commit as-is
rfc/demo/live/agent_events.json          commit as-is (14 rows, no secrets)
rfc/demo/live/run_okf_agent.py           commit as-is
rfc/demo/tools/check_live_trace.py       new stdlib check
rfc/demo/index.html                      masthead, badges, live strip, walkthrough, what-is-real, footer
rfc/demo/app.js                          load live files; beats 1–4 rewritten around the live run
rfc/demo/styles.css                      small additions: .live strip, .badge.live, .live-card, .ev .ty.live
rfc/demo/README.md                       rewrite honesty table + commands
rfc/index.html                           one-sentence update of the demo callout (was "no live GCP")
```

## Order

1. Write `tools/check_live_trace.py` first; run it against the untracked live files. It must pass before the page changes.
2. `app.js`: add `fetchJson("live/live.json")` and `fetchJson("live/agent_events.json")` to the load; parse `attributes`/`content` strings once into `D.live.rows`; derive `D.live.tool`, `D.live.answer`, `D.live.usage`, `D.live.checks`.
3. Beat 1: live list + facts + scan; fixture trace moved into a collapsed details.
4. Beat 2: copy update + two live checklist rows.
5. Beat 3: live entry card and live table card ahead of the in-browser views; relabel views.
6. Beat 4: live transcript, live tiles, no-receipt tile; fixture replay collapsed.
7. `index.html`: kicker, subtitle, badges, live strip markup, walkthrough order, what-is-real, run-locally, footer, meta/og.
8. `styles.css` additions.
9. `README.md` rewrite. `rfc/index.html` callout sentence.
10. Run all checks. Serve locally and smoke the page with a headless fetch of each static file (no console errors expected; JS-only).
11. Commit, push, `gh pr create`.

## Guardrails

- No `fetch()` to any non-same-origin URL. Console links are plain `<a target=_blank rel=noopener>`.
- Never render `concept_version_id` inside the beat 4 transcript or live payloads. It stays on the beat 2 inspector as source metadata only, as before.
- Keep `gemini-3.8-flash` everywhere; grep for `2.5` before commit.
- Do not modify `fixture/`, `derived/`, `hash.js`, `adapter.js`.

## Recording (Haiyuan 4:41 PM PT: also add the recording of the demo into the page)

Primary walkthrough on the page must be a recording of THIS live-GCP full demo, not only the prior 24s fixture clip.
- File: `rfc/demo/okf-bqaa-live-e2e.mp4` (or replace `okf-bqaa-e2e.mp4` if you record after the page rewrite).
- Walkthrough section: live recording first, labelled "live GCP run · 2026-09-02". Prior fixture mp4 only if clearly labelled "prior fixture clip, not live-GCP proof".
- If you cannot capture a new mp4 in this pass, leave a labelled `<video>` slot and `WALKTHROUGH.md` with the exact beats to record; do not ship the page without a video element.
