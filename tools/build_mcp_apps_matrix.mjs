#!/usr/bin/env node
// Renders research/builds/mcp-apps-feature-matrix/source.md (the MATRIX_TLDR publish Markdown) into the
// Field Brief page research/builds/mcp-apps-feature-matrix/index.html.
//
//   node tools/build_mcp_apps_matrix.mjs          rewrite index.html from source.md
//   node tools/build_mcp_apps_matrix.mjs --check  exit 1 if index.html differs from the generated form
//
// The Markdown is one `##` heading, prose paragraphs, one pipe table, `**Label:**` paragraphs and a bullet
// list. Inline syntax handled: links, code spans, bold. Nothing else is interpreted. The site nav block and
// head tags come from tools/site_nav.mjs so the page never drifts from the shared chrome.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render as renderNav, headTags } from "./site_nav.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = "research/builds/mcp-apps-feature-matrix";
const PAGE_PATH = `/${DIR}/`;
const SRC = path.join(REPO, DIR, "source.md");
const OUT = path.join(REPO, DIR, "index.html");
const CANONICAL = `https://caohy1988.github.io${PAGE_PATH}`;

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// Inline Markdown → HTML. Code spans are lifted out first so their contents are never re-interpreted.
function inline(md) {
  const codes = [];
  let s = md.replace(/`([^`]+)`/g, (_, c) => { codes.push(`<code>${esc(c)}</code>`); return `@@CODE${codes.length - 1}@@`; });
  s = esc(s);
  s = s.replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, (_, text, href) => {
    if (!/^https?:\/\//.test(href)) throw new Error(`non-http link in source: ${href}`);
    return `<a href="${href}" rel="noopener">${text}</a>`;
  });
  s = s.replace(/\*\*([^*]+)\*\*/g, "<strong>$1</strong>");
  return s.replace(/@@CODE(\d+)@@/g, (_, i) => codes[Number(i)]);
}

const SEPARATOR = "separator";
function splitRow(line) {
  const t = line.trim();
  if (!t.startsWith("|") || !t.endsWith("|")) throw new Error(`bad table row: ${t.slice(0, 60)}`);
  if (/^[|:\-\s]+$/.test(t)) return SEPARATOR; // `|---|---|` carries no cells
  return t.slice(1, -1).split(" | ").map((c) => c.trim());
}

// Status token at the start of a cell drives a small colour cue. Everything else is neutral.
function cellClass(md) {
  const head = md.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").trim();
  if (/^REC\b/.test(head)) return "st-rec";
  if (/^unk\b/.test(head)) return "st-unk";
  if (/^unpub\b/.test(head)) return "st-unpub";
  return "";
}

export function build(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  let title = "", intro = [], table = null, labelled = [], bullets = [];
  let i = 0;
  const para = () => { const buf = []; while (i < lines.length && lines[i].trim() !== "") buf.push(lines[i++]); return buf.join(" "); };
  while (i < lines.length) {
    const l = lines[i];
    if (l.trim() === "") { i++; continue; }
    if (l.startsWith("## ")) { title = l.slice(3).trim(); i++; continue; }
    if (l.startsWith("|")) {
      const rows = [];
      while (i < lines.length && lines[i].startsWith("|")) rows.push(splitRow(lines[i++]));
      const [head, sep, ...body] = rows;
      if (sep !== SEPARATOR) throw new Error("table separator row missing");
      for (const r of body) if (r.length !== head.length) throw new Error(`row has ${r.length} cells, header has ${head.length}: ${r[0]}`);
      table = { head, body };
      continue;
    }
    if (l.startsWith("- ")) {
      while (i < lines.length && lines[i].startsWith("- ")) bullets.push(lines[i++].slice(2));
      continue;
    }
    const p = para();
    if (/^\*\*[^*]+:\*\*/.test(p)) labelled.push(p); else intro.push(p);
  }
  if (!title || !table || !labelled.length || !bullets.length) throw new Error("source.md is not in the expected shape");

  const m = title.match(/\(v(\d+),\s*(\d{4}-\d{2}-\d{2})\)/);
  const version = m ? `v${m[1]}` : "", date = m ? m[2] : "";
  const heading = title.replace(/^TLDR\s*—\s*/, "").replace(/\s*\(v\d+.*$/, "");
  const legend = labelled.find((p) => p.startsWith("**Legend:**"));
  const columns = labelled.find((p) => p.startsWith("**Columns:**"));
  const notes = labelled.filter((p) => p !== legend && p !== columns);

  const th = table.head.map((h, k) => `<th scope="col"${k === 0 ? ' class="feature"' : ""}>${inline(h)}</th>`).join("");
  const trs = table.body.map((r) => {
    const cells = r.map((c, k) => k === 0 ? `<th scope="row" class="feature">${inline(c)}</th>` : `<td class="${cellClass(c)}">${inline(c)}</td>`);
    return `        <tr>${cells.join("")}</tr>`;
  }).join("\n");

  const [linkTag, scriptTag] = headTags(`${DIR}/index.html`);
  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MCP Apps feature matrix (${version}) — The Field Brief</title>
  <meta name="description" content="MCP Apps (SEP-1865) feature support by product, ${version} ${date}: what vendor documentation, historical reports, pinned source and local inspection show for nine host surfaces. No cell is an observed UI run.">
  <meta name="theme-color" content="#101828">
  <link rel="canonical" href="${CANONICAL}">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {
      --navy: #101828; --paper: #f4efe6; --paper-2: #ebe4d8; --cream: #fbf7f0; --ink: #161410;
      --ink-soft: #5c564c; --ink-faint: #8a8378; --line: #d9d0c3;
      --accent: #e87324; --accent-dark: #b7480d; --mint: #0f766e;
      --serif: "Fraunces", Iowan Old Style, Charter, Georgia, serif;
      --sans: "IBM Plex Sans", Inter, ui-sans-serif, sans-serif;
      --mono: "IBM Plex Mono", ui-monospace, monospace;
    }
    * { box-sizing: border-box; }
    body { margin: 0; background: var(--paper); color: var(--ink); font-family: var(--sans); font-size: 17px; line-height: 1.58; -webkit-font-smoothing: antialiased; }
    a { color: var(--accent-dark); font-weight: 650; text-decoration: none; box-shadow: inset 0 -1px 0 rgba(183,72,13,.35); overflow-wrap: anywhere; }
    a:hover, a:focus-visible { color: var(--accent); }
    code { font-family: var(--mono); font-size: 0.86em; background: var(--paper-2); padding: 0.08em 0.32em; border-radius: 4px; overflow-wrap: anywhere; }
    p { overflow-wrap: break-word; }
    .shell { width: min(1180px, calc(100% - 40px)); margin: 0 auto; }
    .prose { max-width: 76ch; }
    .kicker { padding: 36px 0 8px; margin: 0; font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.14em; text-transform: uppercase; color: var(--mint); }
    h1 { font-family: var(--serif); font-size: clamp(1.9rem, 4vw, 2.6rem); font-weight: 600; letter-spacing: -0.03em; line-height: 1.15; margin: 0 0 12px; max-width: 24ch; }
    .meta { color: var(--ink-soft); margin: 0 0 28px; padding-bottom: 22px; border-bottom: 1px solid var(--line); font-size: 0.95rem; }
    .meta .mono { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); }
    h2 { font-family: var(--serif); font-size: 1.55rem; font-weight: 600; letter-spacing: -0.02em; margin: 40px 0 12px; }
    .intro p { margin: 0 0 14px; color: var(--ink-soft); }
    .intro strong, .notes strong, .takeaways strong { color: var(--ink); }
    .rule { border: 0; border-top: 1px solid var(--line); margin: 28px 0; }

    /* The nine-column matrix: the wrapper scrolls sideways; the feature column stays put while it does. */
    .matrix-hint { display: flex; justify-content: space-between; gap: 16px; margin: 0 0 8px; font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); }
    .matrix-scroll { overflow-x: auto; overscroll-behavior-x: contain; -webkit-overflow-scrolling: touch; margin: 0 0 6px; border: 1px solid var(--line); border-radius: 10px; background: var(--cream); }
    .matrix-scroll:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    table.matrix { border-collapse: separate; border-spacing: 0; min-width: 2360px; width: max-content; font-size: 0.84rem; line-height: 1.5; }
    table.matrix th, table.matrix td { padding: 10px 12px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; color: var(--ink-soft); width: 250px; min-width: 250px; max-width: 250px; }
    table.matrix thead th { font-family: var(--mono); font-size: 0.66rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink); font-weight: 600; background: var(--paper-2); white-space: nowrap; }
    table.matrix th.feature { position: sticky; left: 0; z-index: 2; width: 180px; min-width: 180px; max-width: 180px; background: var(--paper-2); color: var(--ink); font-weight: 600; box-shadow: inset -1px 0 0 var(--line); }
    table.matrix tbody th.feature { font-family: var(--sans); font-size: 0.86rem; }
    table.matrix tbody tr:last-child th, table.matrix tbody tr:last-child td { border-bottom: 0; }
    table.matrix td strong { color: var(--ink); }
    table.matrix td code { font-size: 0.8em; }
    table.matrix td.st-unk::before, table.matrix td.st-unpub::before, table.matrix td.st-rec::before {
      content: ""; display: inline-block; width: 8px; height: 8px; margin: 0 6px 1px 0; border-radius: 50%; vertical-align: baseline;
    }
    table.matrix td.st-unk::before { background: var(--ink-faint); }
    table.matrix td.st-unpub::before { background: var(--accent); }
    table.matrix td.st-rec::before { background: var(--mint); }

    .callout { background: var(--cream); border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 8px; padding: 14px 18px; margin: 18px 0; font-size: 0.92rem; color: var(--ink-soft); }
    .callout p { margin: 0 0 10px; }
    .callout p:last-child { margin-bottom: 0; }
    .notes p { margin: 0 0 14px; font-size: 0.88rem; color: var(--ink-soft); }
    .takeaways { margin: 0 0 16px; padding-left: 1.3em; color: var(--ink-soft); }
    .takeaways li { margin: 0 0 10px; }
    .source { font-size: 0.88rem; color: var(--ink-faint); margin: 0 0 8px; }
    footer { border-top: 3px solid var(--ink); padding: 22px 0 36px; color: var(--ink-soft); font-size: 0.9rem; background: var(--cream); margin-top: 48px; }
    footer .shell { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
    @media (max-width: 860px) {
      body { font-size: 16px; }
      table.matrix th, table.matrix td { width: 220px; min-width: 220px; max-width: 220px; }
      table.matrix th.feature { width: 140px; min-width: 140px; max-width: 140px; }
      table.matrix { min-width: 2120px; }
    }
    @media print { .matrix-scroll { overflow: visible; border: 0; } table.matrix { min-width: 0; width: 100%; font-size: 7pt; } table.matrix th, table.matrix td { width: auto; min-width: 0; max-width: none; } }
  </style>
  ${linkTag}
  ${scriptTag}
</head>
<body>
${renderNav(PAGE_PATH)}
  <main class="shell" id="main">
    <p class="kicker">Builds · MCP Apps · ${version}</p>
    <h1>${inline(heading)}</h1>
    <p class="meta"><span class="mono">${version} · ${date}</span> · MCP Apps (SEP-1865) support across nine host surfaces, read from vendor documentation, dated historical reports, one pinned source snapshot and footnoted local inspection. Public references are linked; prior local inspection is summarized in the footnotes. No cell is an observed UI or fallback run.</p>

    <section class="intro prose" aria-label="Summary">
${intro.map((p) => `      <p>${inline(p)}</p>`).join("\n")}
    </section>

    <h2 id="matrix">Feature support by product</h2>
    <p class="matrix-hint"><span>Scroll sideways for all nine products</span><span>Feature column stays fixed</span></p>
    <div class="matrix-scroll" tabindex="0" role="region" aria-labelledby="matrix">
      <table class="matrix">
        <thead><tr>${th}</tr></thead>
        <tbody>
${trs}
        </tbody>
      </table>
    </div>

    <div class="callout prose" role="note">
      <p>${inline(legend)}</p>
      <p>${inline(columns)}</p>
    </div>

    <h2 id="notes">Inspection footnotes</h2>
    <section class="notes prose">
${notes.map((p) => `      <p>${inline(p)}</p>`).join("\n")}
    </section>

    <h2 id="takeaways">Takeaways</h2>
    <ul class="takeaways prose">
${bullets.map((b) => `      <li>${inline(b)}</li>`).join("\n")}
    </ul>

    <hr class="rule">
    <p class="source prose">Rendered from <code>source.md</code> in this folder by <code>tools/build_mcp_apps_matrix.mjs</code>. The Markdown is the publish copy of MATRIX_TLDR ${version}; local inspection receipts referenced in the footnotes are not hosted here.</p>
  </main>

  <footer>
    <div class="shell"><span>The Field Brief · Builds · MCP Apps feature matrix ${version}</span><span>Haiyuan Cao</span></div>
  </footer>
</body>
</html>
`;
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const next = build(fs.readFileSync(SRC, "utf8"));
  const check = process.argv.includes("--check");
  const cur = fs.existsSync(OUT) ? fs.readFileSync(OUT, "utf8") : null;
  if (check) { const ok = cur === next; console.log(ok ? `${DIR}/index.html in sync` : `DRIFT ${DIR}/index.html; run node tools/build_mcp_apps_matrix.mjs`); process.exit(ok ? 0 : 1); }
  if (cur === next) console.log("nothing to do"); else { fs.writeFileSync(OUT, next); console.log(`wrote ${DIR}/index.html`); }
}
