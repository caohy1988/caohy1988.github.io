# Intent — select cards and copy a leadership-ready list on the five BigQuery boards

**Ask (Haiyuan, 2026-09-10 ~07:09 PT, GO on Feature 1 only).** On each BigQuery product-update board (Conversational Analytics, BQ Search, BQ Graph, BQ Lakehouse, BQ ML / AI Operators) a director should be able to select specific cards and, with one click, copy a clean list that pastes into Google Docs and reads well in front of leadership. No email or subscribe backend in this slice; the joint EM recommendation of 2026-09-10 07:00 PT is authoritative.

**Why.** The boards are built for directors tracking product impact, but the only way to share cards today is to copy links one by one. The five pages also carry five identical inline renderers, so any change to cards is five hand edits.

**What changes.** One shared renderer (`assets/board.js` + `assets/board.css`) replaces the inline scripts and card styles; each card becomes a container with a native checkbox beside the linked content, so selecting never opens the source and the source link keeps opening in a new tab; a selection tray offers Select visible, Review, Copy for Google Docs, Copy plain text and Clear; the copy writes HTML and plain text to the clipboard from the same data model, with a manual-copy panel when the clipboard is blocked; selection survives filter changes and reloads for the current board.

**What does not change.** The four live filters (Video, Medium, Google Cloud, Community) and their counts; `kind: customer` stays data, never a filter label; card content, order (newest first) and the `why` sentences, which are copied verbatim; the shared site navigation; `entries.json` files and the bots that write them.

**Non-goals.** No subscribe or email; no cross-board copy basket; no Markdown export or `?sel=` links (later); no runtime rewriting of `why`; no third-party clipboard library; no deprecated `execCommand` as the primary path.
