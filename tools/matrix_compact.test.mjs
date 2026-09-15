// node --test tools/matrix_compact.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import { assertCompactFresh } from "./matrix_compact.mjs";
import { loadJudgments } from "./matrix_judgments_schema.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");

test("compact freshness passes at HEAD", () => {
  const j = loadJudgments();
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  assert.doesNotThrow(() => assertCompactFresh(j, src));
});

test("stale cell_sha256 fails freshness", () => {
  const j = structuredClone(loadJudgments());
  j.compact_rows[0].cell_sha256 = "0".repeat(64);
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  assert.throws(() => assertCompactFresh(j, src), /cell_sha256 stale/);
});

test("builder embeds compact grid with 36 disclosures and unique ids", () => {
  const html = fs.readFileSync(path.join(DIR, "index.html"), "utf8");
  assert.match(html, /id="status-by-product"/);
  assert.match(html, /table class="compact-matrix"/);
  assert.match(html, /class="compact-cards"/);
  const triggers = [...html.matchAll(/class="compact-trigger"/g)];
  // 9 products × 4 questions × 2 presentations (table + cards)
  assert.equal(triggers.length, 72);
  const ids = [...html.matchAll(/id="(compact-[^"]+-btn)"/g)].map((m) => m[1]);
  assert.equal(ids.length, 72);
  assert.equal(new Set(ids).size, 72);
  assert.ok(html.includes("GitHub Copilot in VS Code"));
  assert.ok(!/\bYes\b[^<]{0,40}\bsupported\b/i.test(html.split('id="full-evidence"')[0]));
});

test("builder --check still in sync", () => {
  const r = spawnSync(process.execPath, ["tools/build_mcp_apps_matrix.mjs", "--check"], {
    cwd: REPO,
    encoding: "utf8",
  });
  assert.equal(r.status, 0, r.stdout + r.stderr);
});
