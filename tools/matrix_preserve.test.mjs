// node --test tools/matrix_preserve.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import crypto from "node:crypto";
import os from "node:os";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");
const BUILDER = path.join(REPO, "tools/build_mcp_apps_matrix.mjs");

function sha256(t) {
  return crypto.createHash("sha256").update(t, "utf8").digest("hex");
}

function extract(html, re) {
  const m = html.match(re);
  assert.ok(m, String(re));
  return m[0];
}

function extractFold(html) {
  return extract(html, /<details class="evidence" id="full-evidence">[\s\S]*?<\/details>/);
}

/** Layer-D block extractors; matrix_region keeps the baseline's trailing indent. */
function layerDBlocks(foldInnerOrHtml) {
  const h = foldInnerOrHtml;
  return {
    html_intro: extract(h, /<section class="intro prose"[\s\S]*?<\/section>/),
    html_matrix_region: extract(h, /<h2 id="matrix">[\s\S]*?<div class="callout prose"[\s\S]*?<\/div>\n\n {4}/),
    html_callout: extract(h, /<div class="callout prose"[\s\S]*?<\/div>/),
    html_notes: extract(h, /<h2 id="notes">[\s\S]*?(?=<h2 id="takeaways")/),
    html_takeaways: extract(h, /<h2 id="takeaways">[\s\S]*?(?=<hr)/),
    html_rendered_from: extract(h, /<p class="source prose">[\s\S]*?<\/p>/),
  };
}

function orderedFoldHrefs(fold) {
  return [...fold.matchAll(/<a href="([^"]+)"/g)].map((m) => m[1]);
}

function htmlToBaselineLinkText(inner) {
  return inner
    .replace(/<code>(.*?)<\/code>/g, (_, c) => "`" + c + "`")
    .replace(/<[^>]+>/g, "")
    .replace(/&quot;/g, '"')
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">");
}

function orderedFoldEntries(fold) {
  return [...fold.matchAll(/<a href="([^"]+)"[^>]*>(.*?)<\/a>/g)].map((m, i) => ({
    i: i + 1,
    text: htmlToBaselineLinkText(m[2]),
    href: m[1],
  }));
}

function privatePathLeak(text) {
  return (
    /\/Users\//.test(text) ||
    /links to a receipt/i.test(text) ||
    /\/private\/tmp\/[A-Za-z0-9._/-]+/i.test(text) ||
    /(?:^|[\s"'`(>]|<\/?code>)\/tmp\/[A-Za-z0-9._/-]+/m.test(text) ||
    /(?:^|[\s"'`(>]|<\/?p>)\/tmp\/[A-Za-z0-9._/-]+/m.test(text)
  );
}

test("builder --check in sync over source+brief+judgments", () => {
  const r = spawnSync(process.execPath, [BUILDER, "--check"], { cwd: REPO, encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
});

test("layer D keeps matrix/notes/takeaways ids and ordered 81-link inventory", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const fold = extractFold(html);
  assert.match(fold, /id="matrix"/);
  assert.match(fold, /id="notes"/);
  assert.match(fold, /id="takeaways"/);
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  assert.equal(sha256(src), baseline.source_md_sha256);
  const hrefs = orderedFoldHrefs(fold);
  assert.equal(hrefs.length, 81);
  assert.deepEqual(hrefs, baseline.link_inventory.ordered_hrefs);
  const entries = orderedFoldEntries(fold);
  assert.equal(entries.length, 81);
  assert.deepEqual(
    entries.map((e) => ({ i: e.i, text: e.text, href: e.href })),
    baseline.link_inventory.ordered_entries.map((e) => ({ i: e.i, text: e.text, href: e.href })),
  );
});

test("layer D rendered blocks match pinned baseline hashes", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const fold = extractFold(html);
  const blocks = layerDBlocks(fold);
  for (const name of [
    "html_intro",
    "html_matrix_region",
    "html_callout",
    "html_notes",
    "html_takeaways",
    "html_rendered_from",
  ]) {
    const got = blocks[name];
    const pin = baseline.blocks[name];
    assert.equal(sha256(got), pin.sha256, `${name} sha256 mismatch`);
    assert.equal(Buffer.byteLength(got, "utf8"), pin.bytes, `${name} byte length mismatch`);
  }
});

test("reader front carries S3 tokens; no private paths; Unknown defined", () => {
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
  assert.ok(!privatePathLeak(html), "private path leak in published HTML");
  assert.ok(!/\bYes\b[^<]{0,40}\bsupported\b/i.test(front.replace(/unsupported/gi, "X")));
});

test("shipping action links Apps spec exactly once", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const action = extract(html, /<p class="action" id="shipping-action">[\s\S]*?<\/p>/);
  const hrefs = [...action.matchAll(/<a href="([^"]+)"/g)].map((m) => m[1]);
  assert.equal(hrefs.length, 1);
  assert.equal(
    hrefs[0],
    "https://github.com/modelcontextprotocol/ext-apps/blob/6d9bdc7babf275b759225aa722cbf5510c4c6021/specification/2026-01-26/apps.mdx",
  );
  assert.match(action, /app-only tool visibility/);
  assert.match(action, /portable path/);
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

test("negative: deleting a takeaway fails block parity", () => {
  const tmpRoot = fs.realpathSync(fs.mkdtempSync(path.join(os.tmpdir(), "matrix-preserve-neg-")));
  try {
    for (const rel of [
      "tools/build_mcp_apps_matrix.mjs",
      "tools/matrix_compact.mjs",
      "tools/matrix_judgments_schema.mjs",
      "tools/site_nav.mjs",
      "assets/site-nav.css",
      "assets/site-nav.js",
      "research/builds/mcp-apps-feature-matrix/source.md",
      "research/builds/mcp-apps-feature-matrix/brief.md",
      "research/builds/mcp-apps-feature-matrix/judgments.json",
      "research/builds/mcp-apps-feature-matrix/v7-preservation-baseline.json",
      "research/builds/mcp-apps-feature-matrix/index.html",
    ]) {
      const dest = path.join(tmpRoot, rel);
      fs.mkdirSync(path.dirname(dest), { recursive: true });
      fs.copyFileSync(path.join(REPO, rel), dest);
    }
    // Drop the first takeaway bullet (Version split) from source.md and rebuild via realpath
    // so the builder's import.meta.url main-gate matches argv on macOS (/var vs /private/var).
    const srcPath = path.join(tmpRoot, "research/builds/mcp-apps-feature-matrix/source.md");
    const srcLines = fs.readFileSync(srcPath, "utf8").split("\n");
    const kept = [];
    let skipped = false;
    for (const line of srcLines) {
      if (!skipped && line.startsWith("- **Version split:**")) { skipped = true; continue; }
      kept.push(line);
    }
    assert.equal(skipped, true, "expected Version split takeaway removal");
    fs.writeFileSync(srcPath, kept.join("\n"));
    const builderPath = fs.realpathSync(path.join(tmpRoot, "tools/build_mcp_apps_matrix.mjs"));
    const gen = spawnSync(process.execPath, [builderPath], { cwd: tmpRoot, encoding: "utf8" });
    assert.equal(gen.status, 0, gen.stdout + gen.stderr);
    assert.match(gen.stdout, /wrote |nothing to do/);
    const html = fs.readFileSync(path.join(tmpRoot, "research/builds/mcp-apps-feature-matrix/index.html"), "utf8");
    const baseline = JSON.parse(
      fs.readFileSync(path.join(tmpRoot, "research/builds/mcp-apps-feature-matrix/v7-preservation-baseline.json"), "utf8"),
    );
    const fold = extractFold(html);
    const got = layerDBlocks(fold).html_takeaways;
    assert.notEqual(sha256(got), baseline.blocks.html_takeaways.sha256);
    assert.ok(!/Version split/.test(got), "Version split takeaway should be absent after mutation");
  } finally {
    fs.rmSync(tmpRoot, { recursive: true, force: true });
  }
});

test("negative: ordinary /tmp inspection path in brief is rejected by private-path guard", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  const poisoned = html.replace(
    "receipts are private",
    "receipts are private; see /tmp/matrix-inspection/result.json",
  );
  assert.ok(privatePathLeak(poisoned));
  assert.ok(!privatePathLeak(html));
});
