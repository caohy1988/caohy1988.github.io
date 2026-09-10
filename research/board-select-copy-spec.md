# Spec — `board-select-copy`

Boards: `research/{conversational-analytics,bigquery-search,bigquery-graph,bigquery-lakehouse,bqml-ai-operators}/index.html`, each rendering `entries.json` (`updatedAt`, `title`, `blurb`, `entries[]` of `id, kind, source, date, displayDate, title, href, why, tags`). No test in the repository reads these pages today; `tools/site_nav.mjs` owns their nav block and must stay in sync.

## 1. Shared renderer

- `assets/board.js` (plain script, `defer`) mounts on `main[data-board][data-entries]`, fetches the entries file with `cache: "no-store"`, and fills `#lede`, `#meta`, `#filters`, `#list` exactly as the inline script did: same `channelOf` rules, same four filters with counts, same `?type=` URL sync, newest-first sort by `date` then `id`.
- `assets/board.css` holds the card, filter, list, tag and selection styles; pages keep their own root variables, hero and footer styles.
- `assets/board-format.js` is a dependency-free module (browser global `BoardFormat`, CommonJS export for node) that turns `{ board: { title, url, preparedDate }, entries }` into `{ html, text }`.
- Each page keeps its static hero and footer, gains `data-board="<slug>" data-entries="/research/<slug>/entries.json"` on `<main>`, and includes the two assets with page-relative hrefs (`../../assets/…`), like the nav assets. No inline `<script>` renderer remains.

## 2. Card DOM contract

```html
<article class="card" data-id="…" data-channel="video|medium|google-cloud|community">
  <label class="card-select"><input type="checkbox" aria-label="Select: <title>"><span class="box" aria-hidden="true"></span></label>
  <div class="card-body">
    <div class="src"><span class="kind">Google Cloud</span><span>source</span><span>displayDate</span></div>
    <h2><a href="…" rel="noopener noreferrer" target="_blank">title</a></h2>
    <p>why</p>
    <div class="tags">…</div>
  </div>
</article>
```

The checkbox is a sibling of the linked content, never inside an anchor. The title anchor is stretched over `.card-body` with a pseudo-element so a click anywhere on the body still opens the source in a new tab, as before; the checkbox column is outside that area. Selected cards get `data-selected="true"`, a check mark and a stronger border (not colour alone). Only `http(s)` hrefs are rendered as links; anything else renders the title as text.

## 3. Selection

- State: a `Set` of entry ids for the current board, mirrored to `sessionStorage["board-select:<slug>"]` as a JSON array; memory-only when storage throws. On load the stored ids are intersected with the current entries; if any were dropped the status region says "N previously selected cards are no longer on this board" once.
- Filters never change the selection. The tray shows `N selected · M hidden by filter` where M counts selected cards not in the active filter.
- Tray (`#board-tray`, `role="region"`, `aria-label="Selection"`): appears when N > 0, sticky at the bottom of the viewport with safe-area padding, never covering the nav; contains a **Select visible** checkbox (checked when every visible card is selected, indeterminate when some are), **Review**, **Copy for Google Docs**, **Copy plain text**, **Clear**. Copy buttons are disabled at N = 0. A status line (`aria-live="polite"`) reports selection and copy results without re-reading the list.
- Keyboard: checkboxes are native inputs labelled "Select: <title>"; Space toggles; every tray control is a button or input.

## 4. Copy format (`BoardFormat.format`)

Selected entries are emitted in board order (newest first), independent of click order.

HTML flavor: generated and escaped from data only, never card `innerHTML`.

```html
<h3>Conversational Analytics in BigQuery</h3>
<p>Selected product updates · Prepared September 10, 2026 · 2 selected sources</p>
<ol>
  <li><b><a href="https://…">Title</a></b><br>why, verbatim<br>Source: Gunnar Griese · Feb 2026 · updated Sep 6, 2026<br>https://…</li>
  …
</ol>
<p>Board: <a href="https://caohy1988.github.io/research/conversational-analytics/">https://caohy1988.github.io/research/conversational-analytics/</a></p>
```

Plain flavor:

```
Conversational Analytics in BigQuery
Selected product updates
Prepared September 10, 2026 · 2 selected sources

1. Title
   why, verbatim
   Source: Gunnar Griese · Feb 2026 · updated Sep 6, 2026
   https://…

Board: https://caohy1988.github.io/research/conversational-analytics/
```

Rules: heading + one numbered list, no tables, fonts, images or nested lists (Docs keeps headings, lists, bold and links on normal paste; plain-text paste uses the text flavor); `title` and `why` verbatim; `displayDate` as written, `date` when absent; the URL line is always present so sources survive plain paste and export; no tags, filter labels, `kind` or ids.

## 5. Clipboard behaviour

- On click, synchronously (no awaited fetch first) build both flavors and call `navigator.clipboard.write([new ClipboardItem({ "text/html": Blob, "text/plain": Blob })])` when `navigator.clipboard`, `navigator.clipboard.write` and `window.ClipboardItem` exist and `window.isSecureContext` is true.
- Success → status "Copied N cards for Google Docs." Selection is preserved.
- Failure or unsupported → status "Rich copy was blocked here. Use Copy plain text, or copy from the review panel." and the review panel opens. **Copy plain text** calls `navigator.clipboard.writeText(text)` on its own click; if that fails the panel's textarea is focused and selected with the instruction to press ⌘C / Ctrl+C. No `execCommand`.
- "Copied" is never shown before the promise resolves.

## 6. Review panel

`<dialog>`-free inline panel under the tray (`#board-review`, hidden by default): the plain-text output in a read-only `<textarea>`, a per-card list with "Remove" buttons, and Close. Removing a card updates the selection and both outputs.

## 7. Acceptance gates (hermetic)

| Gate | Tool | Threshold |
|---|---|---|
| G1 formatter | `node --test tools/board_format.test.mjs` | golden HTML and text for two entries; escaping of `<`, `&`, quotes; non-http href renders as text; board order independent of selection order; `displayDate` fallback to `date` |
| G2 boards in a browser | `node tools/check_boards.mjs [--shots]` over a loopback server, all five boards, 1280 and 375 px | entries load and count equals `entries.json`; the four filter labels with counts; card title href equals the entry href with `target="_blank"`; clicking a checkbox opens no page; clicking the card body opens the source (popup observed); Select visible under a filter selects only visible cards; changing filter keeps selection and reports hidden count; reload restores selection; Copy for Google Docs writes both flavors (clipboard permissions granted) and the status says Copied; with clipboard write failing (stubbed) the review panel opens and Copy plain text works; no inline renderer script in the page source; the `?type=` param still filters |
| G3 nav | `node tools/site_nav.mjs --check`; `node tools/check_site_nav.mjs` | in sync; all pass |
| G4 static | grep | no `execCommand`; no `innerHTML` assignment from entry fields without escaping (formatter and renderer escape every field); no secrets |
| G5 Docs paste | manual, recorded in the vault note and `research/board-select-copy-plan.md` | paste into a Google Doc from Chrome on macOS keeps heading, numbered list, bold titles and links; paste without formatting shows the plain flavor |

## 8. Out of scope

Subscribe/email; cross-board basket; Markdown export; `?sel=` links; `executiveSummary` editorial fields (Astra's proposal, deferred to an editorial pass); changing `why` text.
