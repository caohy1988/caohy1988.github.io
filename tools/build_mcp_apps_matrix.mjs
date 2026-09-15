#!/usr/bin/env node
// Renders research/builds/mcp-apps-feature-matrix/ from source.md + brief.md + judgments.json
// into index.html (PM/UTL-readable front; full v7 evidence in a details fold).
//
//   node tools/build_mcp_apps_matrix.mjs          rewrite index.html
//   node tools/build_mcp_apps_matrix.mjs --check  exit 1 on drift
//
// Layer D (matrix, legend, columns, footnotes, takeaways, version history, rendered-from)
// is preserved from source.md. brief.md owns banner/judgment/action/next-steps/headings.
// judgments.json owns product sentences and compact rows (PR3 grid).
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { render as renderNav, headTags } from "./site_nav.mjs";
import { renderCompact, COMPACT_DISCLOSURE_SCRIPT, assertCompactFresh } from "./matrix_compact.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = "research/builds/mcp-apps-feature-matrix";
const PAGE_PATH = `/${DIR}/`;
const SRC = path.join(REPO, DIR, "source.md");
const BRIEF = path.join(REPO, DIR, "brief.md");
const JUDGMENTS = path.join(REPO, DIR, "judgments.json");
const OUT = path.join(REPO, DIR, "index.html");
const CANONICAL = `https://caohy1988.github.io${PAGE_PATH}`;

const esc = (s) => s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

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
  if (/^[|:\-\s]+$/.test(t)) return SEPARATOR;
  return t.slice(1, -1).split(" | ").map((c) => c.trim());
}

function cellClass(md) {
  const head = md.replace(/\[([^\]]+)\]\([^)]+\)/g, "$1").trim();
  if (/^REC\b/.test(head)) return "st-rec";
  if (/^unk\b/.test(head)) return "st-unk";
  if (/^unpub\b/.test(head)) return "st-unpub";
  return "";
}

function parseSource(md) {
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
  const m = title.match(/\(v(\d+)[^,]*,\s*([^)]+)\)/);
  const version = m ? `v${m[1]}` : "", date = m ? m[2] : "";
  const heading = title.replace(/^TLDR\s*—\s*/, "").replace(/\s*\(v\d+.*$/, "");
  const legend = labelled.find((p) => p.startsWith("**Legend:**"));
  const columns = labelled.find((p) => p.startsWith("**Columns:**"));
  const notes = labelled.filter((p) => p !== legend && p !== columns);
  return { title, heading, version, date, intro, table, legend, columns, notes, bullets };
}

function parseBrief(md) {
  const lines = md.replace(/\r\n/g, "\n").split("\n");
  const out = { title: "", sections: {} };
  let cur = null, buf = [];
  const flush = () => {
    if (!cur) return;
    const text = buf.join("\n").trim();
    out.sections[cur] = text;
    buf = [];
  };
  for (const l of lines) {
    if (l.startsWith("# ")) { flush(); out.title = l.slice(2).trim(); cur = null; continue; }
    if (l.startsWith("## ")) { flush(); cur = l.slice(3).trim(); continue; }
    if (cur) buf.push(l);
  }
  flush();
  for (const need of ["Banner", "Aggregate judgment", "Shipping action", "Next steps heading", "Next steps", "Next steps owner", "Evidence fold summary", "Kicker", "Meta"]) {
    if (!out.sections[need]) throw new Error(`brief.md missing section: ${need}`);
  }
  if (!out.title) throw new Error("brief.md missing H1");
  return out;
}

function renderLayerD(parsed) {
  const { heading, version, date, intro, table, legend, columns, notes, bullets } = parsed;
  const th = table.head.map((h, k) => `<th scope="col"${k === 0 ? ' class="feature"' : ""}>${inline(h)}</th>`).join("");
  const trs = table.body.map((r) => {
    const cells = r.map((c, k) => k === 0 ? `<th scope="row" class="feature">${inline(c)}</th>` : `<td class="${cellClass(c)}">${inline(c)}</td>`);
    return `        <tr>${cells.join("")}</tr>`;
  }).join("\n");
  return `
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
    <p class="source prose">Rendered from <code>source.md</code> in this folder by <code>tools/build_mcp_apps_matrix.mjs</code>. The Markdown is the publish copy of MATRIX_TLDR v7; local inspection receipts referenced in the footnotes are not hosted here.</p>
`.replace(/^\n/, "");
}

function renderSentences(judgments) {
  const order = [
    "Documented by the vendor",
    "Reported only",
    "Code found, undocumented",
    "Unknown",
  ];
  const byGroup = new Map(order.map((g) => [g, []]));
  for (const s of judgments.product_sentences) {
    if (!byGroup.has(s.group)) byGroup.set(s.group, []);
    byGroup.get(s.group).push(s);
  }
  const blocks = [];
  for (const [group, items] of byGroup) {
    if (!items.length) continue;
    const lis = items.map((s) => {
      const name = esc(s.product);
      let linkedName;
      if (s.first_claim_link) {
        linkedName = `<a href="${esc(s.first_claim_link)}" rel="noopener">${name}</a>`;
      } else if (s.links_footnote) {
        linkedName = `<a href="#notes">${name}</a>`;
      } else {
        linkedName = name;
      }
      return `        <li>${linkedName} — ${esc(s.sentence)}</li>`;
    }).join("\n");
    blocks.push(`      <h3 class="group">${esc(group)}</h3>\n      <ul class="products">\n${lis}\n      </ul>`);
  }
  return blocks.join("\n");
}

function renderNextSteps(brief) {
  const raw = brief.sections["Next steps"];
  const items = raw.split("\n").map((l) => l.replace(/^- /, "").trim()).filter(Boolean);
  return items.map((it) => `      <li>${inline(it)}</li>`).join("\n");
}

export function build(sourceMd, briefMd, judgments) {
  const parsed = parseSource(sourceMd);
  const brief = parseBrief(briefMd);
  const { version, date } = parsed;
  assertCompactFresh(judgments, sourceMd);
  const layerD = renderLayerD(parsed);
  const compact = renderCompact(judgments, sourceMd, parsed.notes, inline, esc);
  const [linkTag, scriptTag] = headTags(`${DIR}/index.html`);

  const banner = brief.sections["Banner"];
  const judgment = brief.sections["Aggregate judgment"];
  const action = brief.sections["Shipping action"];
  const nextHeading = brief.sections["Next steps heading"];
  const owner = brief.sections["Next steps owner"];
  const foldSummary = brief.sections["Evidence fold summary"];
  const kicker = brief.sections["Kicker"];
  const meta = brief.sections["Meta"];

  return `<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>MCP Apps feature matrix (${version}, readable) — The Field Brief</title>
  <meta name="description" content="MCP Apps (SEP-1865) feature support by product, ${version} ${date}: which hosts document Apps rendering, what to ship anyway, and the full v7 evidence on demand. No cell is an observed UI run.">
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
    h1 { font-family: var(--serif); font-size: clamp(1.9rem, 4vw, 2.6rem); font-weight: 600; letter-spacing: -0.03em; line-height: 1.15; margin: 0 0 12px; max-width: 28ch; }
    .meta { color: var(--ink-soft); margin: 0 0 28px; padding-bottom: 22px; border-bottom: 1px solid var(--line); font-size: 0.95rem; }
    .meta .mono { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); }
    h2 { font-family: var(--serif); font-size: 1.55rem; font-weight: 600; letter-spacing: -0.02em; margin: 40px 0 12px; }
    h3.group { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.1em; text-transform: uppercase; color: var(--ink-faint); margin: 22px 0 8px; font-weight: 600; }
    .banner { background: var(--cream); border: 1px solid var(--line); border-left: 4px solid var(--mint); border-radius: 8px; padding: 14px 18px; margin: 0 0 22px; font-size: 0.92rem; color: var(--ink-soft); }
    .banner p { margin: 0; }
    .judgment, .action { margin: 0 0 14px; }
    .action { font-weight: 550; }
    .products, .next-steps { margin: 0 0 16px; padding-left: 1.3em; color: var(--ink-soft); }
    .products li, .next-steps li { margin: 0 0 10px; }
    .compact { margin: 28px 0 24px; }
    .compact-hint, .compact-key, .compact-portable { color: var(--ink-soft); font-size: 0.92rem; }
    .compact-table-wrap { overflow-x: auto; margin: 12px 0 16px; border: 1px solid var(--line); border-radius: 10px; }
    table.compact-matrix { border-collapse: collapse; width: 100%; min-width: 920px; font-size: 0.9rem; }
    table.compact-matrix th, table.compact-matrix td { border-bottom: 1px solid var(--line); padding: 10px 12px; vertical-align: top; text-align: left; }
    table.compact-matrix th.product { min-width: 160px; }
    table.compact-matrix thead th { background: var(--cream); font-size: 0.8rem; letter-spacing: 0.01em; }
    .compact-cards { display: none; gap: 12px; }
    .compact-card { border: 1px solid var(--line); border-radius: 10px; padding: 12px 14px; background: #fff; }
    .compact-card h3 { margin: 0 0 10px; font-size: 1.05rem; }
    .compact-card-row { margin: 0 0 10px; }
    .compact-card-q { display: block; font-size: 0.75rem; text-transform: uppercase; letter-spacing: 0.04em; color: var(--ink-faint); margin-bottom: 4px; }
    .compact-trigger { display: block; width: 100%; text-align: left; border: 1px solid var(--line); border-radius: 8px; background: var(--cream); padding: 8px 10px; cursor: pointer; font: inherit; color: inherit; }
    .compact-trigger:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .compact-trigger[aria-expanded="true"] { border-color: var(--accent); background: #fff; }
    .compact-word { font-weight: 650; }
    .compact-phrase { color: var(--ink-soft); }
    .compact-panel { margin-top: 8px; padding: 10px 12px; border-left: 3px solid var(--accent); background: #fff; font-size: 0.88rem; color: var(--ink-soft); }
    .compact-panel[hidden] { display: none !important; }
    .visually-hidden { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; border: 0; }
    @media (max-width: 700px) {
      .compact-table-wrap { display: none; }
      .compact-cards { display: grid; }
    }
    @media print {
      .compact-panel[hidden] { display: block !important; }
      .compact-trigger { border: 0; background: transparent; padding: 0; }
    }
    .owner { font-size: 0.9rem; color: var(--ink-faint); margin: 0 0 28px; }
    .rule { border: 0; border-top: 1px solid var(--line); margin: 28px 0; }
    details.evidence { border: 1px solid var(--line); border-radius: 10px; background: var(--cream); padding: 0 18px 18px; margin: 28px 0 8px; }
    details.evidence > summary { cursor: pointer; list-style: none; font-family: var(--mono); font-size: 0.78rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--mint); padding: 16px 0; font-weight: 600; }
    details.evidence > summary::-webkit-details-marker { display: none; }
    details.evidence > summary::before { content: "▸ "; }
    details.evidence[open] > summary::before { content: "▾ "; }
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
    .callout { background: var(--paper); border: 1px solid var(--line); border-left: 4px solid var(--accent); border-radius: 8px; padding: 14px 18px; margin: 18px 0; font-size: 0.92rem; color: var(--ink-soft); }
    .callout p { margin: 0 0 10px; }
    .callout p:last-child { margin-bottom: 0; }
    .notes p { margin: 0 0 14px; font-size: 0.88rem; color: var(--ink-soft); }
    .takeaways { margin: 0 0 16px; padding-left: 1.3em; color: var(--ink-soft); }
    .takeaways li { margin: 0 0 10px; }
    .source { font-size: 0.88rem; color: var(--ink-faint); margin: 0 0 8px; }
    footer { border-top: 3px solid var(--ink); padding: 22px 0 36px; color: var(--ink-soft); font-size: 0.9rem; background: var(--cream); margin-top: 48px; }
    footer .shell { display: flex; justify-content: space-between; gap: 16px; flex-wrap: wrap; }
    .kicker { padding: 28px 0 6px; }
    h1 { font-size: clamp(1.55rem, 3.6vw, 2.35rem); margin: 0 0 8px; }
    .meta { margin: 0 0 16px; padding-bottom: 14px; font-size: 0.9rem; }
    .banner { padding: 12px 14px; margin: 0 0 14px; font-size: 0.88rem; line-height: 1.45; }
    #short-version h2 { margin: 18px 0 8px; font-size: 1.25rem; }
    .judgment, .action { margin: 0 0 10px; font-size: 0.98rem; line-height: 1.45; }
    @media (max-width: 860px) {
      body { font-size: 15px; }
      .kicker { padding: 14px 0 4px; font-size: 0.62rem; letter-spacing: 0.08em; white-space: nowrap; overflow: hidden; text-overflow: ellipsis; }
      h1 { font-size: 1.35rem; line-height: 1.2; max-width: none; margin: 0 0 6px; }
      .meta { margin: 0 0 10px; padding-bottom: 10px; font-size: 0.78rem; line-height: 1.35; }
      .meta .desk-only { display: none; }
      .banner { padding: 8px 10px; margin: 0 0 8px; font-size: 0.78rem; line-height: 1.35; }
      #short-version h2 { position: absolute; width: 1px; height: 1px; padding: 0; margin: -1px; overflow: hidden; clip: rect(0,0,0,0); border: 0; }
      .judgment, .action { margin: 0 0 8px; font-size: 0.9rem; line-height: 1.35; }
      table.matrix th, table.matrix td { width: 220px; min-width: 220px; max-width: 220px; }
      table.matrix th.feature { width: 140px; min-width: 140px; max-width: 140px; }
      table.matrix { min-width: 2120px; }
    }
    @media print {
      .matrix-scroll { overflow: visible; border: 0; }
      table.matrix { min-width: 0; width: 100%; font-size: 7pt; }
      table.matrix th, table.matrix td { width: auto; min-width: 0; max-width: none; }
      details.evidence { border: 0; padding: 0; }
      details.evidence > summary { display: none; }
      details.evidence[open], details.evidence { display: block; }
    }
  </style>
  ${linkTag}
  ${scriptTag}
</head>
<body>
${renderNav(PAGE_PATH)}
  <main class="shell" id="main">
    <p class="kicker">${esc(kicker)}</p>
    <h1>${esc(brief.title)}</h1>
    <p class="meta"><span class="mono">${esc(meta.split(" · ").slice(0, 2).join(" · "))}</span><span class="desk-only"> · ${esc(meta.split(" · ").slice(2).join(" · "))}</span></p>

    <section class="short prose" id="short-version" aria-label="The short version">
      <h2>The short version</h2>
      <p class="judgment" id="aggregate-judgment">${esc(judgment)}</p>
      <p class="action" id="shipping-action">${inline(action)}</p>
    </section>

    <div class="banner prose" role="note" id="banner">
      <p>${esc(banner)}</p>
    </div>

    <section class="by-product prose" id="by-product" aria-label="By product">
      <h2>By product</h2>
${renderSentences(judgments)}
    </section>

${compact}

    <section class="next prose" id="what-would-change" aria-label="${esc(nextHeading)}">
      <h2>${esc(nextHeading)}</h2>
      <ul class="next-steps">
${renderNextSteps(brief)}
      </ul>
      <p class="owner">${esc(owner)}</p>
    </section>

    <p class="generator-inputs prose" id="generator-inputs">Page inputs: <code>brief.md</code> (banner, judgment, action, next steps), <code>judgments.json</code> (product sentences and compact rows), and <code>source.md</code> (full evidence below).</p>

    <details class="evidence" id="full-evidence">
      <summary>${esc(foldSummary)}</summary>
${layerD}
    </details>
  </main>

  <footer>
    <div class="shell"><span>The Field Brief · Builds · MCP Apps feature matrix ${version} (readable)</span><span>Haiyuan Cao</span></div>
  </footer>
  <script>
    (function () {
      function openEvidenceForHash() {
        var id = (location.hash || "").replace(/^#/, "");
        if (!id) return;
        var el = document.getElementById(id);
        if (!el) return;
        var fold = document.getElementById("full-evidence");
        if (fold && fold.contains(el)) fold.open = true;
        // print: ensure open
        el.scrollIntoView({ block: "start" });
      }
      window.addEventListener("DOMContentLoaded", openEvidenceForHash);
      window.addEventListener("hashchange", openEvidenceForHash);
      if (window.matchMedia) {
        window.matchMedia("print").addEventListener("change", function (e) {
          var fold = document.getElementById("full-evidence");
          if (fold && e.matches) fold.open = true;
        });
      }
    })();
${COMPACT_DISCLOSURE_SCRIPT}
  </script>
</body>
</html>
`;
}

function loadInputs() {
  const sourceMd = fs.readFileSync(SRC, "utf8");
  const briefMd = fs.readFileSync(BRIEF, "utf8");
  const judgments = JSON.parse(fs.readFileSync(JUDGMENTS, "utf8"));
  return { sourceMd, briefMd, judgments };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { sourceMd, briefMd, judgments } = loadInputs();
  const next = build(sourceMd, briefMd, judgments);
  const check = process.argv.includes("--check");
  const cur = fs.existsSync(OUT) ? fs.readFileSync(OUT, "utf8") : null;
  if (check) {
    const ok = cur === next;
    console.log(ok ? `${DIR}/index.html in sync` : `DRIFT ${DIR}/index.html; run node tools/build_mcp_apps_matrix.mjs`);
    process.exit(ok ? 0 : 1);
  }
  if (cur === next) console.log("nothing to do");
  else { fs.writeFileSync(OUT, next); console.log(`wrote ${DIR}/index.html`); }
}
