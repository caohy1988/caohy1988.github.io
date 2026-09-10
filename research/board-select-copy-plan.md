# Plan — `board-select-copy`

1. **Formatter first** (`assets/board-format.js`) with `tools/board_format.test.mjs` golden tests (G1).
2. **Shared renderer** (`assets/board.js`, `assets/board.css`): port the inline renderer unchanged in behaviour, new card DOM, selection state + tray + review panel + clipboard.
3. **Migrate the five pages**: remove the inline script and the card/filter/list CSS, add `data-board` / `data-entries`, include the assets. Keep hero, footer, nav block and root variables. `node tools/site_nav.mjs --check` must still pass.
4. **Browser check** `tools/check_boards.mjs` (G2) with `--shots`.
5. **Verify** G1–G4; screenshots at 1280 and 375; Docs paste by hand (G5) recorded below and in the vault note.
6. **Ship**: push `feat/board-select-copy`, PR against `main`, vault note under `Ship/rfc/`. No merge.

## Result (filled in at delivery)

| Check | Result |
|---|---|
| `node --test tools/board_format.test.mjs` | 5 passed |
| `node tools/check_boards.mjs` | all board checks pass over 5 boards (desktop, blocked-clipboard, mobile) |
| `node tools/site_nav.mjs --check` / `node tools/check_site_nav.mjs` | 13 pages in sync / all pass |
| Docs paste (manual) | **not yet verified** — no Google account in the build environment. Procedure: open any board, select two cards, Copy for Google Docs, paste into a Google Doc in Chrome on macOS; expected: a heading, one numbered list with bold linked titles, the why sentence, a Source line and a visible URL line per item, and a Board link; ⌘⇧V should paste the plain flavor. Record the outcome in the vault note before merge. |

Notes: a Japanese card title with no break opportunities widened the BQ ML board to 407px at 375px viewport (pre-existing content); `overflow-wrap: anywhere` on card text fixes it. The old whole-card link is replaced by a stretched title link over the body, so Playwright must click the body by position.
