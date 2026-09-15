// node --test tools/matrix_preserve.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import crypto from "node:crypto";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");

function sha256(t) { return crypto.createHash("sha256").update(t, "utf8").digest("hex"); }

function extract(html, re) {
  const m = html.match(re);
  assert.ok(m, String(re));
  return m[0];
}

test("builder --check in sync over source+brief+judgments", () => {
  const r = spawnSync(process.execPath, ["tools/build_mcp_apps_matrix.mjs", "--check"], { cwd: REPO, encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
});

test("layer D keeps matrix/notes/takeaways ids and 81 source links", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const fold = extract(html, /<details class="evidence" id="full-evidence">[\s\S]*?<\/details>/);
  assert.match(fold, /id="matrix"/);
  assert.match(fold, /id="notes"/);
  assert.match(fold, /id="takeaways"/);
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const mdLinks = [...src.matchAll(/\]\(([^)]+)\)/g)].map((m) => m[1]);
  assert.equal(mdLinks.length, 81);
  assert.equal(baseline.link_inventory.count, 81);
  for (const href of mdLinks) {
    assert.ok(fold.includes(href), `missing link in layer D: ${href.slice(0, 80)}`);
  }
  // source.md hash still matches baseline pin
  assert.equal(sha256(src), baseline.source_md_sha256);
});

test("reader front carries S3 tokens; no private receipt paths; Unknown defined", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const front = html.split('id="full-evidence"')[0];
  for (const t of [
    "No cell is an observed UI or fallback run",
    "does not establish the answer",
    "receipts are private",
    "portable",
  ]) assert.ok(front.includes(t), t);
  assert.ok(front.includes('id="aggregate-judgment"'));
  assert.ok(front.includes('id="shipping-action"'));
  assert.ok(!/\/Users\//.test(html));
  assert.ok(!/links to a receipt/i.test(html));
  assert.ok(!/\/private\/tmp\/.*receipt/i.test(html));
  // capability chips
  assert.ok(!/\bYes\b[^<]{0,40}\bsupported\b/i.test(front.replace(/unsupported/gi, "X")));
});

test("site_nav check still lists MCP Apps matrix route", () => {
  const nav = fs.readFileSync(path.join(REPO, "tools/site_nav.mjs"), "utf8");
  assert.ok(nav.includes("/research/builds/mcp-apps-feature-matrix/"));
});

test("fragment-open script present for hash targets inside fold", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert.ok(html.includes("openEvidenceForHash"));
  assert.ok(html.includes('getElementById("full-evidence")'));
});
