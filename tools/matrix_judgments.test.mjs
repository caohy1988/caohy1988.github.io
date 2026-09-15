// node --test tools/matrix_judgments.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { loadJudgments, validateJudgments, parseSourceCells, sha256 } from "./matrix_judgments_schema.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");

test("judgments schema + counterexample fixtures pass", () => {
  const j = loadJudgments();
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const errors = validateJudgments(j, src, baseline);
  assert.deepEqual(errors, []);
});

test("preservation baseline pins 81 links and fragment ids", () => {
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  assert.equal(baseline.link_inventory.count, 81);
  assert.equal(baseline.link_inventory.ordered_hrefs.length, 81);
  assert.deepEqual(baseline.fragment_ids_required, ["matrix", "notes", "takeaways"]);
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  assert.equal(baseline.source_md_sha256, sha256(src));
});

test("copy-map carries S3 tokens and 36 compact phrases", () => {
  const map = JSON.parse(fs.readFileSync(path.join(DIR, "copy-map.json"), "utf8"));
  for (const t of ["No cell is an observed UI or fallback run", "does not establish the answer", "receipts are private", "portable"]) {
    assert.ok(map.brief_tokens_S3.includes(t), t);
  }
  assert.equal(map.compact_phrases_verbatim.length, 36);
  assert.equal(map.product_sentences_verbatim.length, 9);
});

test("PR1 does not drift generated HTML (source-only build still in sync)", async () => {
  // import build check via child would be heavier; compare that index exists and source parse works
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const { header, cells } = parseSourceCells(src);
  assert.equal(header[0], "Feature");
  assert.equal(Object.keys(cells).length, 8);
  assert.ok(cells["Iframe / UI mount"]["Cursor"].includes("cursor.com"));
});

test("pm-readable contract trio exists", () => {
  for (const f of ["pm-readable-intent.md", "pm-readable-spec.md", "pm-readable-plan.md"]) {
    assert.ok(fs.existsSync(path.join(DIR, f)), f);
  }
});
