// node --test tools/matrix_host_tldr.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { parseHostTldr, HOST_TLDR_STATUSES } from "./build_mcp_apps_matrix.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");
const HOSTS = [
  "Claude Desktop",
  "Claude Cowork",
  "Claude Code",
  "OpenAI Codex CLI",
  "OpenAI Codex Desktop",
  "GitHub Copilot",
  "Cursor",
  "Antigravity CLI",
  "Antigravity Desktop",
];

const html = () => fs.readFileSync(path.join(DIR, "index.html"), "utf8");
const tldrMd = () => fs.readFileSync(path.join(DIR, "host-tldr.md"), "utf8");
const section = (h) => h.match(/<section class="host-tldr" id="host-tldr"[\s\S]*?<\/section>/)[0];

test("host TLDR sits above the fold: after banner, before by-product, compact grid and evidence", () => {
  const h = html();
  const at = (s) => { const i = h.indexOf(s); assert.ok(i > 0, s); return i; };
  const tldr = at('id="host-tldr"');
  assert.ok(at('id="shipping-action"') < tldr);
  assert.ok(at('id="banner"') < tldr);
  assert.ok(tldr < at('id="by-product"'));
  assert.ok(tldr < at('id="status-by-product"'));
  assert.ok(tldr < at('id="full-evidence"'));
});

test("host TLDR table has 9 hosts, allowed chips only, and a linked Why per row", () => {
  const s = section(html());
  const rows = [...s.matchAll(/<tr><th scope="row">([^<]+)<\/th><td class="tldr-status">([\s\S]*?)<\/td><td class="tldr-why">([\s\S]*?)<\/td><\/tr>/g)];
  assert.deepEqual(rows.map((r) => r[1]), HOSTS);
  const chips = [...s.matchAll(/<span class="chip chip-([a-z]+)">([^<]+)<\/span>/g)];
  assert.equal(chips.length, 9);
  for (const [, cls, word] of chips) {
    assert.ok(HOST_TLDR_STATUSES.includes(word), word);
    assert.equal(cls, word.toLowerCase());
  }
  assert.deepEqual(chips.map((c) => c[2]), ["Partial", "Partial", "Unknown", "Unknown", "Partial", "Full", "Full", "Unknown", "Unknown"]);
  assert.ok(!/chip-documented|>Documented</.test(s), "host TLDR chips rate feature parity, never Documented");
  assert.match(s, /Chips rate <strong>feature parity<\/strong> \([^)]*mount, fallback[^)]*\), not documentation/);
  assert.match(s, /<strong>Full<\/strong>: GitHub Copilot in VS Code and Cursor\. <strong>Partial<\/strong>: Claude Desktop, Claude Cowork, OpenAI Codex Desktop\. The other four are <strong>Unknown<\/strong>/);
  for (const [, host, , why] of rows) {
    const links = [...why.matchAll(/<a href="(https:\/\/[^"]+)" rel="noopener">([^<]+)<\/a>/g)];
    assert.ok(links.length >= 1, `${host} Why has no https link`);
    for (const [, href, label] of links) assert.notEqual(label, href, `${host} uses a bare URL label`);
  }
});

test("host TLDR carries summary + a “Yes, this differs” official-vs-ours comparison with both official links", () => {
  const s = section(html());
  assert.match(s, /No row below is an observed UI or fallback run/);
  assert.match(s, /not<\/strong> the same as unsupported/);
  const cmp = s.match(/<div class="tldr-official prose" id="official-vs-ours">[\s\S]*?<\/div>/)[0];
  assert.match(cmp, /<p class="tldr-differs"><strong>Yes — this differs from the official MCP Apps matrix, intentionally\.<\/strong>/);
  assert.match(cmp, /<a href="https:\/\/modelcontextprotocol\.io\/extensions\/apps\/overview" rel="noopener">MCP Apps overview<\/a>/);
  assert.match(cmp, /<a href="https:\/\/modelcontextprotocol\.io\/extensions\/client-matrix" rel="noopener">client extension matrix<\/a>/);
  const rows = Object.fromEntries([...cmp.matchAll(/<tr><th scope="row">([^<]+)<\/th><td class="compare-official">([\s\S]*?)<\/td><td class="compare-ours">([\s\S]*?)<\/td><\/tr>/g)].map((m) => [m[1], [m[2], m[3]]]));
  assert.deepEqual(Object.keys(rows), ["Question", "Grain"]);
  assert.match(rows.Question[0], /Does the client implement <code>io\.modelcontextprotocol\/ui<\/code>/);
  assert.match(rows.Question[1], /capability \/ registration-path \/ fallback gap for shipping Glance-style UI on these nine hosts/);
  assert.match(rows.Grain[0], /CHECK/);
  assert.match(rows.Grain[1], /Full \/ Partial \/ Unknown feature parity per host, with evidence links/);
  // the comparison table, the Agreement table, and the Host | Status | Why table
  assert.equal([...s.matchAll(/<table/g)].length, 3);
});

test("host TLDR answers per-product agreement: 3 overlaps (2 Agree, 1 Disagree), 16 no overlap, naming traps", () => {
  const s = section(html());
  const at = (x) => { const i = s.indexOf(x); assert.ok(i > 0, x); return i; };
  assert.ok(at('id="official-vs-ours"') < at('id="official-agreement"'));
  assert.ok(at('id="official-agreement"') < at('class="host-tldr-table"'));
  const agree = s.match(/<div class="tldr-agreement prose" id="official-agreement">[\s\S]*?<\/div>/)[0];
  const rows = [...agree.matchAll(/<tr><th scope="row">([^<]+)<\/th><td>([^<]+)<\/td><td>([^<]+)<\/td><td class="agree-([a-z]+)"><strong>([^<]+)<\/strong><\/td><\/tr>/g)].map((m) => m.slice(1));
  assert.deepEqual(rows, [
    ["Claude Desktop", "CHECK", "Partial", "disagree", "Disagree"],
    ["GitHub Copilot", "CHECK", "Full", "agree", "Agree"],
    ["Cursor", "CHECK", "Full", "agree", "Agree"],
  ]);
  assert.ok(!/class="chip/.test(agree), "agreement words are not feature-parity chips");
  assert.match(agree, /Other 16 products: <strong>no overlap<\/strong>/);
  assert.match(agree, /ChatGPT ≠ Codex Desktop/);
  assert.match(agree, /Claude web ≠ Desktop\/Cowork\/Code/);
  assert.match(agree, /CHECK is a claim, not a verified Glance UI journey/);
});

test("parser ties Agreement to the Table chips and the CHECK mapping rule", () => {
  const md = tldrMd();
  assert.throws(() => parseHostTldr(md.replace("| Cursor | CHECK | Full | Agree |", "| Cursor | CHECK | Full | Disagree |")), /must be Agree/);
  assert.throws(() => parseHostTldr(md.replace("| Claude Desktop | CHECK | Partial | Disagree |", "| Claude Desktop | CHECK | Partial | Agree |")), /must be Disagree/);
  assert.throws(() => parseHostTldr(md.replace("| GitHub Copilot | CHECK | Full | Agree |", "| GitHub Copilot | CHECK | Partial | Disagree |")), /does not match Table status/);
  assert.throws(() => parseHostTldr(md.replace("| Cursor | CHECK | Full | Agree |\n", "")), /Agreement rows must be/);
  assert.throws(() => parseHostTldr(md.replace("**no overlap**", "**elsewhere**")), /no-overlap/);
  assert.throws(() => parseHostTldr(md.replace("## Agreement\n", "## Agreements\n")), /missing section: Agreement/);
});

test("parser rejects an Official matrix block without the differs lead, a required row, or an official link", () => {
  const md = tldrMd();
  assert.throws(() => parseHostTldr(md.replace("this differs", "this compares")), /must say this differs/);
  assert.throws(() => parseHostTldr(md.replace(/^\| Grain \|.*\n/m, "")), /missing row: Grain/);
  assert.throws(() => parseHostTldr(md.replace("(https://modelcontextprotocol.io/extensions/apps/overview)", "(https://example.com/)")), /must link/);
  assert.throws(() => parseHostTldr(md.replace(/^\| \| Official.*\n\|---\|---\|---\|\n/m, "")), /header must be|comparison table/);
});

test("reader front never shows an Unsupported chip, unqualified unsupported, or private paths", () => {
  const front = html().split('id="full-evidence"')[0];
  assert.ok(!/chip[^>]*>\s*Unsupported/i.test(front));
  const unsupported = [...section(front).matchAll(/(.{0,16})unsupported/gi)].map((m) => m[1]);
  for (const lead of unsupported) assert.match(lead, /(≠ | the same as )$/, lead);
  assert.ok(!/\/Users\/|\/private\/tmp\/|(?:^|[\s"'`(>])\/tmp\/|links to a receipt/m.test(section(front)));
});

test("parser rejects Unsupported status, a link-free Why, and a missing row", () => {
  const md = tldrMd();
  assert.doesNotThrow(() => parseHostTldr(md));
  assert.throws(() => parseHostTldr(md.replace("| Claude Code | Unknown |", "| Claude Code | Unsupported |")), /status must be/);
  const noLink = md.replace(/\| Antigravity CLI \| Unknown \| .*\|\n/, "| Antigravity CLI | Unknown | Silent on Apps. |\n");
  assert.throws(() => parseHostTldr(noLink), /https evidence link/);
  const short = md.replace(/\| Cursor \| Full \| .*\|\n/, "");
  assert.throws(() => parseHostTldr(short), /expected 9/);
});

test("builder --check in sync with host-tldr.md", () => {
  const r = spawnSync(process.execPath, ["tools/build_mcp_apps_matrix.mjs", "--check"], { cwd: REPO, encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
});
