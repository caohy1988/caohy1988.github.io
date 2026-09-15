#!/usr/bin/env node
// Renders research/builds/mcp-apps-feature-matrix/ from source.md + brief.md + host-tldr.md + judgments.json
// into index.html (PM/UTL-readable front; full v7 evidence in a details fold).
//
//   node tools/build_mcp_apps_matrix.mjs          rewrite index.html
//   node tools/build_mcp_apps_matrix.mjs --check  exit 1 on drift
//
// Layer D (matrix, legend, columns, footnotes, takeaways, version history, rendered-from)
// is preserved from source.md. brief.md owns banner/judgment/action/next-steps/headings.
// host-tldr.md owns the above-fold Host | Status | Why table (Full/Partial/Unknown feature parity)
// and the official-vs-ours comparison table.
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
const HOST_TLDR = path.join(REPO, DIR, "host-tldr.md");
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

// Feature parity across the dense-matrix capability rows, not documentation parity (Haiyuan, 2026-09-14).
export const HOST_TLDR_STATUSES = ["Full", "Partial", "Unknown"];

// host-tldr.md owns the above-fold Host | Status | Why table (TLDR_HUMAN contract).
export function parseHostTldr(md) {
  const { sections } = parseSections(md, ["Heading", "Summary", "Official matrix", "Table"], "host-tldr.md");
  const rows = sections["Table"].split("\n").filter((l) => l.startsWith("|")).map(splitRow);
  const [head, sep, ...body] = rows;
  if (head === SEPARATOR || head.join("|") !== "Host|Status|Why") throw new Error("host-tldr.md table header must be Host | Status | Why");
  if (sep !== SEPARATOR) throw new Error("host-tldr.md table separator row missing");
  if (body.length !== 9) throw new Error(`host-tldr.md table has ${body.length} rows, expected 9`);
  for (const r of body) {
    if (r.length !== 3) throw new Error(`host-tldr.md row has ${r.length} cells: ${r[0]}`);
    const [host, status, why] = r;
    if (!HOST_TLDR_STATUSES.includes(status)) throw new Error(`host-tldr.md ${host}: status must be ${HOST_TLDR_STATUSES.join("/")}, got ${status}`);
    if (!/\]\(https:\/\/[^)\s]+\)/.test(why)) throw new Error(`host-tldr.md ${host}: Why needs at least one https evidence link`);
  }
  return { heading: sections["Heading"], summary: sections["Summary"], official: parseOfficial(sections["Official matrix"]), rows: body };
}

export const OFFICIAL_LINKS = ["https://modelcontextprotocol.io/extensions/apps/overview", "https://modelcontextprotocol.io/extensions/client-matrix"];
export const OFFICIAL_COMPARE_ROWS = ["Question", "Grain", "Observed UI runs"];

// "Official matrix" = a lead saying this differs, a | | Official | This page | table, and a closing line.
function parseOfficial(text) {
  const lines = text.split("\n");
  const first = lines.findIndex((l) => l.startsWith("|"));
  if (first < 0) throw new Error("host-tldr.md Official matrix needs a comparison table");
  let end = first;
  while (end < lines.length && lines[end].startsWith("|")) end++;
  const lead = lines.slice(0, first).join(" ").trim();
  const after = lines.slice(end).join(" ").trim();
  const [head, sep, ...body] = lines.slice(first, end).map(splitRow);
  if (head === SEPARATOR || head.length !== 3 || head[0] !== "" || !/^Official\b/.test(head[1]) || head[2] !== "This page") {
    throw new Error("host-tldr.md Official matrix table header must be | | Official … | This page |");
  }
  if (sep !== SEPARATOR) throw new Error("host-tldr.md Official matrix separator row missing");
  for (const r of body) if (r.length !== 3) throw new Error(`host-tldr.md Official matrix row has ${r.length} cells: ${r[0]}`);
  const labels = body.map((r) => r[0]);
  for (const need of OFFICIAL_COMPARE_ROWS) if (!labels.includes(need)) throw new Error(`host-tldr.md Official matrix missing row: ${need}`);
  if (!/\bdiffers\b/.test(lead)) throw new Error("host-tldr.md Official matrix lead must say this differs");
  if (!/`io\.modelcontextprotocol\/ui`/.test(body.find((r) => r[0] === "Question")[1])) throw new Error("host-tldr.md Official question must name io.modelcontextprotocol/ui");
  for (const href of OFFICIAL_LINKS) if (!text.includes(`](${href})`)) throw new Error(`host-tldr.md Official matrix must link ${href}`);
  return { lead, head, body, after };
}

function renderOfficial(o) {
  const [, official, ours] = o.head;
  const trs = o.body.map(([label, a, b]) => `              <tr><th scope="row">${esc(label)}</th><td class="compare-official">${inline(a)}</td><td class="compare-ours">${inline(b)}</td></tr>`).join("\n");
  return `      <div class="tldr-official prose" id="official-vs-ours">
        <p class="tldr-differs">${inline(o.lead)}</p>
        <table class="tldr-compare">
          <thead><tr><td></td><th scope="col">${inline(official)}</th><th scope="col">${inline(ours)}</th></tr></thead>
          <tbody>
${trs}
          </tbody>
        </table>${o.after ? `\n        <p class="tldr-overlap">${inline(o.after)}</p>` : ""}
      </div>`;
}

function renderHostTldr(tldr) {
  const trs = tldr.rows.map(([host, status, why]) => {
    const chip = `<span class="chip chip-${status.toLowerCase()}">${esc(status)}</span>`;
    return `          <tr><th scope="row">${esc(host)}</th><td class="tldr-status">${chip}</td><td class="tldr-why">${inline(why)}</td></tr>`;
  }).join("\n");
  return `    <section class="host-tldr" id="host-tldr" aria-labelledby="host-tldr-heading">
      <h2 id="host-tldr-heading">${esc(tldr.heading)}</h2>
      <p class="tldr-summary prose">${inline(tldr.summary)}</p>
${renderOfficial(tldr.official)}
      <div class="tldr-table-wrap">
        <table class="host-tldr-table">
          <thead><tr><th scope="col">Host</th><th scope="col">Status</th><th scope="col">Why</th></tr></thead>
          <tbody>
${trs}
          </tbody>
        </table>
      </div>
    </section>`;
}

function parseBrief(md) {
  const { title, sections } = parseSections(
    md,
    ["Banner", "Aggregate judgment", "Shipping action", "Next steps heading", "Next steps", "Next steps owner", "Evidence fold summary", "Kicker", "Meta"],
    "brief.md",
  );
  if (!title) throw new Error("brief.md missing H1");
  return { title, sections };
}

function parseSections(md, need, name) {
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
  for (const n of need) {
    if (!out.sections[n]) throw new Error(`${name} missing section: ${n}`);
  }
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

export function build(sourceMd, briefMd, judgments, hostTldrMd) {
  const parsed = parseSource(sourceMd);
  const brief = parseBrief(briefMd);
  const hostTldr = renderHostTldr(parseHostTldr(hostTldrMd));
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
    .host-tldr { margin: 22px 0 8px; }
    .host-tldr h2 { margin: 0 0 8px; }
    .tldr-summary { margin: 0 0 10px; }
    .tldr-official { margin: 0 0 12px; font-size: 0.92rem; color: var(--ink-soft); }
    .tldr-official p { margin: 0 0 8px; }
    .tldr-differs { color: var(--ink); }
    table.tldr-compare { border-collapse: collapse; width: 100%; table-layout: fixed; margin: 0 0 8px; line-height: 1.4; }
    table.tldr-compare th, table.tldr-compare td { padding: 7px 10px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; overflow-wrap: anywhere; }
    table.tldr-compare thead th { font-weight: 600; color: var(--ink); background: var(--paper-2); }
    table.tldr-compare thead td { width: 9.5em; background: var(--paper-2); }
    table.tldr-compare tbody th { font-family: var(--mono); font-size: 0.7rem; letter-spacing: 0.06em; text-transform: uppercase; color: var(--ink-faint); font-weight: 600; }
    @media (max-width: 700px) {
      table.tldr-compare thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
      table.tldr-compare, table.tldr-compare tbody, table.tldr-compare tr, table.tldr-compare th, table.tldr-compare td { display: block; width: auto; }
      table.tldr-compare tr { padding: 6px 0; border-bottom: 1px solid var(--line); }
      table.tldr-compare th, table.tldr-compare td { padding: 2px 0; border: 0; }
      table.tldr-compare td.compare-official::before { content: "Official: "; font-weight: 600; color: var(--ink); }
      table.tldr-compare td.compare-ours::before { content: "This page: "; font-weight: 600; color: var(--ink); }
    }
    details.fold > summary { cursor: pointer; list-style: none; }
    details.fold > summary::-webkit-details-marker { display: none; }
    details.fold > summary h2 { display: inline; margin: 0; }
    details.fold > summary::before { content: "▸ "; color: var(--mint); font-weight: 600; }
    details.fold[open] > summary::before { content: "▾ "; }
    details.fold > summary:focus-visible { outline: 2px solid var(--accent); outline-offset: 2px; }
    .fold-hint { font-family: var(--mono); font-size: 0.72rem; letter-spacing: 0.08em; text-transform: uppercase; color: var(--ink-faint); margin-left: 6px; }
    .tldr-table-wrap { border: 1px solid var(--line); border-radius: 10px; background: var(--cream); overflow: hidden; }
    table.host-tldr-table { border-collapse: collapse; width: 100%; font-size: 0.9rem; line-height: 1.45; }
    table.host-tldr-table th, table.host-tldr-table td { padding: 9px 12px; border-bottom: 1px solid var(--line); vertical-align: top; text-align: left; }
    table.host-tldr-table thead th { font-family: var(--mono); font-size: 0.68rem; letter-spacing: 0.08em; text-transform: uppercase; background: var(--paper-2); }
    table.host-tldr-table tbody tr:last-child th, table.host-tldr-table tbody tr:last-child td { border-bottom: 0; }
    table.host-tldr-table tbody th { white-space: nowrap; font-weight: 600; }
    table.host-tldr-table td.tldr-why { color: var(--ink-soft); }
    .chip { display: inline-block; padding: 1px 8px; border-radius: 999px; font-family: var(--mono); font-size: 0.7rem; font-weight: 600; letter-spacing: 0.04em; border: 1px solid; white-space: nowrap; }
    .chip-full { color: var(--mint); border-color: rgba(15,118,110,.45); background: rgba(15,118,110,.08); }
    .chip-partial { color: var(--accent-dark); border-color: rgba(183,72,13,.4); background: rgba(232,115,36,.1); }
    .chip-unknown { color: var(--ink-soft); border-color: var(--line); background: var(--paper-2); }
    @media (max-width: 700px) {
      table.host-tldr-table thead { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); }
      table.host-tldr-table, table.host-tldr-table tbody, table.host-tldr-table tr { display: block; }
      table.host-tldr-table tr { padding: 9px 12px; border-bottom: 1px solid var(--line); }
      table.host-tldr-table tbody tr:last-child { border-bottom: 0; }
      table.host-tldr-table th, table.host-tldr-table td { display: inline; padding: 0; border: 0; }
      table.host-tldr-table td.tldr-status { margin-left: 6px; }
      table.host-tldr-table td.tldr-why { display: block; margin-top: 4px; }
    }
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
    .compact-trigger { position: relative; display: block; width: 100%; text-align: left; border: 1px solid var(--line); border-radius: 8px; background: var(--cream); padding: 8px 10px; cursor: pointer; font: inherit; color: inherit; }
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

${hostTldr}

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

    <p class="generator-inputs prose" id="generator-inputs">Page inputs: <code>brief.md</code>, <code>host-tldr.md</code>, <code>judgments.json</code> and <code>source.md</code>.</p>

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
        for (var d = el.parentElement; d; d = d.parentElement) if (d.tagName === "DETAILS") d.open = true;
        el.scrollIntoView({ block: "start" });
      }
      window.addEventListener("DOMContentLoaded", openEvidenceForHash);
      window.addEventListener("hashchange", openEvidenceForHash);
      if (window.matchMedia) {
        window.matchMedia("print").addEventListener("change", function (e) {
          var fold = document.getElementById("full-evidence");
          if (fold && e.matches) fold.open = true;
          if (e.matches) document.querySelectorAll("main details").forEach(function (d) { d.open = true; });
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
  const hostTldrMd = fs.readFileSync(HOST_TLDR, "utf8");
  return { sourceMd, briefMd, judgments, hostTldrMd };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const { sourceMd, briefMd, judgments, hostTldrMd } = loadInputs();
  const next = build(sourceMd, briefMd, judgments, hostTldrMd);
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
