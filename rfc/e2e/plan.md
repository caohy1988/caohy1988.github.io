# Plan — `/rfc/e2e/`

Execute in order. Everything is site-only on branch `rfc/e2e-page`. No live GCP calls.

1. **Docs.** Write `intent.md`, `spec.md` and this plan.
2. **Poster and captions.**
   - Cut the 0:01 frame of `../demo/okf-publish-connected.mp4`.
   - Write `okf-publish-connected.en.vtt` from the cast timeline. Cast deltas capped at 3 s sum to 92.72 s against the 92.75 s mp4, spot-checked on frames at 1, 27.8, 49.3 and 79 s.

   | Tape | Stage |
   |---|---|
   | 0:00 | question |
   | 0:04 | compile |
   | 0:11 | write and read back |
   | 0:22 | `READY` |
   | 0:27 | current version switched |
   | 0:30 | Catalog entry |
   | 0:31–0:40 | access granted, wait compressed |
   | 0:40 | discover → pin → retrieve → receipt |
   | 0:49 | released $400.00 |
   | 0:52–1:10 | refusals |
   | 1:13 | revoke |
   | 1:19 | refused after revocation |
   | 1:22–1:24 | match and cleanup |
   | 1:27 | the agent gets the validated result |
   | 1:30 | model answer and verdict |

3. **Page.** `index.html` + `styles.css` per spec §3, with site-nav markers and head tags.
4. **Nav.** Edit `tools/site_nav.mjs` (`PAGES`, `CURRENT`, `STICKY`), then run `node tools/site_nav.mjs` to write the bar into the new page.
5. **Landing links.**
   - `/rfc/index.html`: three link edits, keeping within the rendered ≤ 950 / open ≤ 1800 word budget.
   - `/rfc/demo/index.html`: a one-line pointer in `#connected-e2e`.
6. **Gates.** Run spec §6. Take screenshots at 1280 px and 375 px with Playwright and read them for layout and overflow. Fix, then rerun.
7. **Commit and push.** Commit on `rfc/e2e-page` and push. If the push stalls, use `git -c http.postBuffer=524288000 push`.
8. **PR.** Open one PR to `caohy1988/caohy1988.github.io` that includes:
   - both planes;
   - the thesis;
   - the 5-minute UX;
   - the retained run `kp-20260915t082018z-0387`;
   - the gate results;
   - the Astra checklist: (a) readability, (b) why-better thesis, (c) quality/realness. Each is P1 if missing.

   The overnight rule is merge on Astra APPROVE; this seat does not merge. The EM kicks Astra and Kimi.
9. **Notes and vault.**
   - Record the PR URL, commits, beats, UX choices and residuals in `/tmp/okf-e2e-page/OPUS_E2E_PAGE_NOTES.md`.
   - Set `STATUS.md` to `WAITING_ASTRA`.
   - File vault notes under `Ship/builds/` and `Ship/rfc/`.
