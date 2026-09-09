# Intent — the board pack becomes `/rfc/`; the full RFC moves to `/rfc/detailed-rfc/`

Prepared 2026-09-09. Haiyuan's ask, verbatim: "move the board pack into RFC and move RFC into a subpage called detailed RFC".

## Why

- `/rfc/` is the address every research page's nav points at. Today it opens the long technical RFC; leadership readers land on hashing specs before they see the story.
- The board-pack near-miss (`rfc/board-pack/index.html`) is the 3–4 minute leadership page. It should be the first thing a reader sees under RFC.
- The long RFC stays a first-class page, one click away, as "Detailed RFC".

## Outcome

1. `/rfc/` renders the board-pack story unchanged in content; only links, canonical and chrome move.
2. `/rfc/detailed-rfc/` renders the previous `/rfc/` page unchanged in content; relative links are rewritten one level up.
3. `/rfc/board-pack/` and `/rfc/bq-vp/` stay as redirect stubs to `/rfc/`, so every published link keeps working.
4. Site nav gains a `Detailed RFC` item next to `RFC`.
5. The board-pack markdown history (`rfc/board-pack/*.md`) stays where it is.

## Not in scope

- No change to leadership story wording, evidence claims or the full RFC's technical text beyond link paths.
- No live GCP, no merge, no edits to PR 61's content (PR 61 touches both moved pages; see plan for the re-apply recipe).
