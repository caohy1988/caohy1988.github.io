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
| `node --test tools/board_format.test.mjs` | _tbd_ |
| `node tools/check_boards.mjs` | _tbd_ |
| `node tools/site_nav.mjs --check` / `node tools/check_site_nav.mjs` | _tbd_ |
| Docs paste (manual) | _tbd_ |
