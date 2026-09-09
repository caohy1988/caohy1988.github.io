# Spec — `/rfc/` landing restructure

## Files

| Before | After | Change |
|---|---|---|
| `rfc/board-pack/index.html` (story) | `rfc/index.html` | copied; canonical → `https://caohy1988.github.io/rfc/`; `../spikes/…` → `spikes/…`; `intent-knowledge-publications.md` → `board-pack/intent-knowledge-publications.md`; brand → `/research/`; masthead gains `Detailed RFC →` (`detailed-rfc/`) |
| `rfc/board-pack/styles.css` | `rfc/styles.css` | git mv, unchanged bytes |
| `rfc/index.html` (full RFC) | `rfc/detailed-rfc/index.html` | git mv; canonical → `…/rfc/detailed-rfc/`; nav `RFC` → `/rfc/` plus `Detailed RFC` (current); `./board-pack/` → `../`; `./demo/`, `./full-demo/`, `spikes/…` → `../…` |
| `rfc/board-pack/index.html` | redirect stub | meta refresh + canonical to `/rfc/`; names `/rfc/detailed-rfc/` |
| `rfc/bq-vp/index.html` | redirect stub | target `/rfc/board-pack/` → `/rfc/` (one hop instead of two) |
| `rfc/demo/index.html`, `rfc/full-demo/index.html` | kicker link | `../` → `../detailed-rfc/` (the technical RFC these demos belong to); full-demo label stays `RFC` because that sentence is audited copy in `tools/audited_claims.tsv` |
| every page with the primary nav (research, briefs, evalbench, demos) | nav | `<a href="/rfc/detailed-rfc/">Detailed RFC</a>` inserted after `RFC` |

## Checks that must stay green (offline)

- `rfc/spikes/bq-graph/tests/test_board_pack_links.py`: relative links and pinned blob links for both `rfc/index.html` and `rfc/detailed-rfc/index.html`; the two pages link each other; canonical addresses; both redirect stubs target `/rfc/` and never `/rfc/board-pack/`.
- `python3 rfc/full-demo/tools/check_full_demo.py` exit 0 (reads `rfc/detailed-rfc/index.html` for the `../full-demo/` wiring; mutation fixture copies that path).
- `python3 rfc/demo/tools/check_cli_viewer.py`: repointed at `rfc/detailed-rfc/index.html`; its three Prototype-callout checks already fail at baseline `fb8c051` (callout markup drifted before this slice) and are unchanged by it.
- Headless browser over a local static server: `/rfc/`, `/rfc/detailed-rfc/` load with no 4xx responses; `/rfc/board-pack/` and `/rfc/bq-vp/` land on `/rfc/`.

## Acceptance

1. Content of the two moved pages is byte-identical to the source outside the link/canonical/nav lines listed above.
2. No reader-facing link on the site points at `/rfc/board-pack/` except the two redirect stubs' canonical/refresh targets.
3. Markdown under `rfc/board-pack/` untouched.
