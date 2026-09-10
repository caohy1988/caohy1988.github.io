#!/usr/bin/env node
// Single source of truth for the site navigation (research/site-nav-spec.md).
//
//   node tools/site_nav.mjs          rewrite the nav block + asset tags in every page listed below
//   node tools/site_nav.mjs --check  exit 1 if any page's nav block or asset tags differ from the generated form
//
// Each page carries the block between `<!-- site-nav:start -->` and `<!-- site-nav:end -->` plus one
// `<link ... data-site-nav>` and one `<script ... data-site-nav>` in <head>. Edit the IA here, rerun, commit.
// Asset hrefs are relative to the page so file:// previews (and rfc/tools/rfc_word_count.mjs) load the CSS.
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");

export const BRAND = { href: "/research/", html: '<span>HC</span> / FIELD BRIEF' };

// Top level: links and folders. A folder is { label, id, items }.
export const NAV = [
  { label: "Research", href: "/research/" },
  { label: "BQAA", href: "/research/stories/" },
  { label: "BigQuery", id: "bigquery", items: [
    { label: "Conversational Analytics", href: "/research/conversational-analytics/" },
    { label: "BQ ML / AI Ops", href: "/research/bqml-ai-operators/" },
    { label: "BQ Graph", href: "/research/bigquery-graph/" },
    { label: "BQ Lakehouse", href: "/research/bigquery-lakehouse/" },
    { label: "BQ Search", href: "/research/bigquery-search/" },
  ] },
  { label: "Usage", href: "/research/usage/" },
  { label: "Builds", id: "builds", items: [
    { label: "RFC", href: "/rfc/" },
    { label: "Detailed RFC", href: "/rfc/detailed-rfc/" },
    { label: "EvalBench", href: "/evalbench/" },
  ] },
];

// Pages that carry the shared chrome. The key is the page's own site path (used for aria-current).
export const PAGES = {
  "/research/": "research/index.html",
  "/research/stories/": "research/stories/index.html",
  "/research/conversational-analytics/": "research/conversational-analytics/index.html",
  "/research/bqml-ai-operators/": "research/bqml-ai-operators/index.html",
  "/research/bigquery-graph/": "research/bigquery-graph/index.html",
  "/research/bigquery-lakehouse/": "research/bigquery-lakehouse/index.html",
  "/research/bigquery-search/": "research/bigquery-search/index.html",
  "/research/usage/": "research/usage/index.html",
  "/rfc/": "rfc/index.html",
  "/rfc/detailed-rfc/": "rfc/detailed-rfc/index.html",
  "/rfc/demo/": "rfc/demo/index.html",
  "/rfc/full-demo/": "rfc/full-demo/index.html",
  "/evalbench/": "evalbench/index.html",
};

// Which nav entry is "current" for a page. Demos live under the RFC (that is what their old nav said).
export const CURRENT = { "/rfc/demo/": "/rfc/", "/rfc/full-demo/": "/rfc/" };

// Long single-page documents keep the bar pinned (they did before the shared chrome).
export const STICKY = new Set(["/rfc/detailed-rfc/", "/rfc/demo/", "/rfc/full-demo/"]);

const START = "<!-- site-nav:start -->";
const END = "<!-- site-nav:end -->";

export function assetPrefix(file) {
  const depth = file.split("/").length - 1;
  return depth === 0 ? "./" : "../".repeat(depth);
}

export function headTags(file) {
  const p = assetPrefix(file);
  return [
    `<link rel="stylesheet" href="${p}assets/site-nav.css" data-site-nav>`,
    `<script defer src="${p}assets/site-nav.js" data-site-nav></script>`,
  ];
}

export function render(pagePath) {
  const current = CURRENT[pagePath] || pagePath;
  const link = (item, indent) => {
    const cur = item.href === current ? ' aria-current="page"' : "";
    return `${indent}<a href="${item.href}"${cur}>${item.label}</a>`;
  };
  const lines = [START,
    `<div class="site-topbar" data-site-nav${STICKY.has(pagePath) ? ' data-sticky=""' : ""}>`,
    '  <div class="site-topbar-inner">',
    `    <a class="site-brand" href="${BRAND.href}">${BRAND.html}</a>`,
    '    <button class="site-nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>',
    '    <nav class="nav-links site-nav" id="site-nav" aria-label="Primary">'];
  for (const entry of NAV) {
    if (!entry.items) { lines.push(link(entry, "      ")); continue; }
    const active = entry.items.some((i) => i.href === current);
    const id = `site-nav-menu-${entry.id}`;
    lines.push(`      <div class="site-nav-folder"${active ? ' data-active="true"' : ""}>`);
    lines.push(`        <button type="button" class="site-nav-folder-button" aria-haspopup="true" aria-expanded="false" aria-controls="${id}">${entry.label}</button>`);
    lines.push(`        <div class="site-nav-menu" id="${id}">`);
    for (const item of entry.items) lines.push(link(item, "          "));
    lines.push("        </div>");
    lines.push("      </div>");
  }
  lines.push("    </nav>", "  </div>", "</div>", END);
  return lines.join("\n");
}

function splice(html, file, pagePath) {
  const a = html.indexOf(START), b = html.indexOf(END);
  if (a < 0 || b < 0 || b < a) throw new Error(`${file}: missing ${START} … ${END} markers`);
  let out = html.slice(0, a) + render(pagePath) + html.slice(b + END.length);
  const [linkTag, scriptTag] = headTags(file);
  const linkRe = /<link rel="stylesheet" href="[^"]*assets\/site-nav\.css" data-site-nav>/;
  const scriptRe = /<script defer src="[^"]*assets\/site-nav\.js" data-site-nav><\/script>/;
  if (!linkRe.test(out) || !scriptRe.test(out)) throw new Error(`${file}: missing data-site-nav <link>/<script> in <head>`);
  return out.replace(linkRe, linkTag).replace(scriptRe, scriptTag);
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const check = process.argv.includes("--check");
  let drift = 0;
  for (const [pagePath, file] of Object.entries(PAGES)) {
    const abs = path.join(REPO, file);
    const html = fs.readFileSync(abs, "utf8");
    const next = splice(html, file, pagePath);
    if (next === html) continue;
    drift++;
    if (check) console.log(`DRIFT ${file}`);
    else { fs.writeFileSync(abs, next); console.log(`wrote ${file}`); }
  }
  if (check) { console.log(drift ? `${drift} page(s) out of sync; run node tools/site_nav.mjs` : `all ${Object.keys(PAGES).length} pages in sync`); process.exit(drift ? 1 : 0); }
  else console.log(drift ? `${drift} page(s) updated` : "nothing to do");
}
