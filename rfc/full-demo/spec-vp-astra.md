# Spec — Astra full VP show optimization

## Goal
Make `/rfc/full-demo/` a VP-ready demo show: one retellable story, clear value, scannable beats, talk-track friendly. Optimize end-to-end (strip + masthead + beat framing + stories/matrix intros + optional talk notes), not just one card.

## Must keep
- Live session ids and verdict quotes already on page
- Honesty labels (live / seeded / stub / RFC text only)
- Six-beat player; checker exit 0; SQL/live pins untouched unless copy-only

## Optimize for
1. **Story arc** a VP can retell in 30s: ask → Catalog failure mode → BQ runtime value → what to do next
2. **Value first**, mechanism as citation
3. **Demo choreography**: what to click/say per beat for a VP show (short on-page “Show notes” or beat kicker lines)
4. **Cut density**: long technical digressions demoted; punchlines sharpened
5. **Visual hierarchy**: strip → beats → matrix/stories as backup, not the cold open

## Deliverables
- Edits under `rfc/full-demo/` (html/css/js/md/json as needed)
- Optional `rfc/full-demo/VP_SHOW_NOTES.md` — 5–8 min talk track
- Commit, push, `gh pr create` vs main; print PR URL + NEW_SHA. Do not merge.
