// node --test tools/matrix_judgments.test.mjs
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import { spawnSync } from "node:child_process";
import {
  loadJudgments,
  validateJudgments,
  parseSourceCells,
  sha256,
  EXPECTED_PRODUCTS,
  EXPECTED_QUESTIONS,
} from "./matrix_judgments_schema.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");

test("judgments schema + counterexample fixtures + sentence derivations pass", () => {
  const j = loadJudgments();
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const errors = validateJudgments(j, src, baseline);
  assert.deepEqual(errors, []);
  for (const s of j.product_sentences) {
    assert.ok(s.derivation?.cited_cells?.length >= 1, s.product);
    assert.ok(s.derivation?.compact_row_refs?.length >= 1, s.product);
  }
  const agy = j.product_sentences.find((s) => s.product === "Antigravity Desktop");
  assert.equal(agy.first_claim_link, null);
  assert.equal(agy.links_footnote, "⁶");
  assert.ok(agy.derivation.cited_blocks.some((b) => b.marker === "⁶"));
});

test("schema rejects missing sentence derivation and empty/duplicate coverage", () => {
  const j = loadJudgments();
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const bad = structuredClone(j);
  delete bad.product_sentences[0].derivation;
  assert.ok(validateJudgments(bad, src, baseline).some((e) => /derivation\.supporting_clauses/.test(e)));
  const empty = structuredClone(j);
  empty.product_sentences = EXPECTED_PRODUCTS.map((p) => ({ product: p, group: "x", sentence: "" }));
  assert.ok(validateJudgments(empty, src, baseline).length > 0);
  const dup = structuredClone(j);
  dup.product_sentences[1] = structuredClone(dup.product_sentences[0]);
  assert.ok(validateJudgments(dup, src, baseline).some((e) => /duplicate sentence|missing product sentence/.test(e)));
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

test("source.md parses to eight feature rows; builder --check reports in sync", () => {
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const { header, cells } = parseSourceCells(src);
  assert.equal(header[0], "Feature");
  assert.equal(Object.keys(cells).length, 8);
  assert.ok(cells["Iframe / UI mount"]["Cursor"].includes("cursor.com"));
  const r = spawnSync(process.execPath, ["tools/build_mcp_apps_matrix.mjs", "--check"], { cwd: REPO, encoding: "utf8" });
  assert.equal(r.status, 0, r.stdout + r.stderr);
  assert.match(r.stdout, /in sync/);
});

test("pm-readable contract trio exists", () => {
  for (const f of ["pm-readable-intent.md", "pm-readable-spec.md", "pm-readable-plan.md"]) {
    assert.ok(fs.existsSync(path.join(DIR, f)), f);
  }
});

test("exact 9x4 compact coverage constants match artifact", () => {
  const j = loadJudgments();
  assert.deepEqual(j.products, EXPECTED_PRODUCTS);
  const keys = new Set(j.compact_rows.map((r) => `${r.product}::${r.question}`));
  for (const p of EXPECTED_PRODUCTS) for (const q of EXPECTED_QUESTIONS) assert.ok(keys.has(`${p}::${q}`));
});

test("schema rejects stale cited_blocks hashes and wrong product_source_column", () => {
  const j = loadJudgments();
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const badHash = structuredClone(j);
  const agy = badHash.product_sentences.find((s) => s.product === "Antigravity Desktop");
  agy.derivation.cited_blocks[0].block_sha256 = "0".repeat(64);
  assert.ok(validateJudgments(badHash, src, baseline).some((e) => /block_sha256 stale/.test(e)));
  const badCol = structuredClone(j);
  for (const row of badCol.compact_rows.filter((r) => r.product === "Claude Desktop")) {
    row.product_source_column = "Claude Cowork";
    // keep hash pointing at Cowork cell so only mapping fails
    const { cells } = parseSourceCells(src);
    row.cell_sha256 = sha256(cells[row.source_row]["Claude Cowork"]);
  }
  assert.ok(validateJudgments(badCol, src, baseline).some((e) => /product_source_column must be/.test(e)));
});

test("schema rejects Yes/No supported chip and private tmp receipt path", () => {
  const j = loadJudgments();
  const src = fs.readFileSync(path.join(DIR, "source.md"), "utf8");
  const baseline = JSON.parse(fs.readFileSync(path.join(DIR, "v7-preservation-baseline.json"), "utf8"));
  const bad = structuredClone(j);
  bad.compact_rows[0].phrase = "Documented · Yes supported";
  assert.ok(validateJudgments(bad, src, baseline).some((e) => /Yes\/No supported/.test(e)));
  const bad2 = structuredClone(j);
  bad2.compact_rows[0].phrase += " /private/tmp/matrix-receipt/inspection.json";
  assert.ok(validateJudgments(bad2, src, baseline).some((e) => /private receipt/.test(e)));
});
