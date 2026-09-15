// Shared schema checks for research/builds/mcp-apps-feature-matrix/judgments.json
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath } from "node:url";
import crypto from "node:crypto";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const DIR = path.join(REPO, "research/builds/mcp-apps-feature-matrix");
const JUDGMENTS = path.join(DIR, "judgments.json");
const SOURCE = path.join(DIR, "source.md");
const BASELINE = path.join(DIR, "v7-preservation-baseline.json");

export function loadJudgments() {
  return JSON.parse(fs.readFileSync(JUDGMENTS, "utf8"));
}

export function parseSourceCells(src) {
  const lines = src.split(/\n/).filter((l) => l.startsWith("|"));
  const header = lines[0].split("|").slice(1, -1).map((c) => c.trim());
  const out = {};
  for (const line of lines.slice(2)) {
    const cells = line.split("|").slice(1, -1).map((c) => c.trim());
    const feature = cells[0];
    out[feature] = {};
    for (let i = 1; i < header.length; i++) {
      out[feature][header[i]] = cells[i];
    }
  }
  return { header, cells: out };
}

export function sha256(text) {
  return crypto.createHash("sha256").update(text, "utf8").digest("hex");
}

export function validateJudgments(j, sourceText, baseline) {
  const errors = [];
  if (j.schema_version !== 1) errors.push("schema_version must be 1");
  if (!Array.isArray(j.compact_rows) || j.compact_rows.length !== 36) {
    errors.push(`expected 36 compact_rows, got ${j.compact_rows?.length}`);
  }
  if (!Array.isArray(j.product_sentences) || j.product_sentences.length !== 9) {
    errors.push(`expected 9 product_sentences, got ${j.product_sentences?.length}`);
  }
  const { cells } = parseSourceCells(sourceText);
  const forbidden = new Set(j.honesty?.forbidden_status_words || []);
  const seen = new Set();
  for (const row of j.compact_rows || []) {
    const key = `${row.product}::${row.question}`;
    if (seen.has(key)) errors.push(`duplicate row ${key}`);
    seen.add(key);
    const permitted = j.field_definitions?.[row.question]?.answers_permitted || [];
    if (!permitted.includes(row.evidence_kind)) {
      errors.push(`${key}: evidence_kind ${row.evidence_kind} not in ${permitted}`);
    }
    if (!row.phrase || !row.cell_sha256 || !row.source_row) {
      errors.push(`${key}: missing phrase/cell_sha256/source_row`);
    }
    // phrase must not be a bare forbidden status chip
    const firstWord = String(row.phrase).split(/[\s·]/)[0];
    if (forbidden.has(firstWord)) errors.push(`${key}: forbidden status word ${firstWord}`);
    if (/\bYes\b|\bNo\b/.test(row.phrase) && /supported/i.test(row.phrase)) {
      errors.push(`${key}: looks like Yes/No supported chip`);
    }
    const srcCol = row.product_source_column;
    const cellText = cells[row.source_row]?.[srcCol];
    if (cellText == null) {
      errors.push(`${key}: missing source cell ${row.source_row} / ${srcCol}`);
    } else if (sha256(cellText) !== row.cell_sha256) {
      errors.push(`${key}: cell_sha256 stale for ${row.source_row}`);
    }
  }
  // product label rule
  for (const row of j.compact_rows || []) {
    if (row.product === "GitHub Copilot") errors.push("must spell GitHub Copilot in VS Code");
  }
  for (const s of j.product_sentences || []) {
    if (s.product === "GitHub Copilot") errors.push("sentence product must spell GitHub Copilot in VS Code");
  }
  // fixtures
  const by = Object.fromEntries((j.compact_rows || []).map((r) => [`${r.product}::${r.question}`, r]));
  const fx = j.counterexample_fixtures || {};
  const c1 = by["Cursor::without_apps"];
  const cursorCell = cells["Fallback: Apps absent/failing"]?.["Cursor"] || "";
  if (!cursorCell.startsWith("[VD generic]")) errors.push("fixture setup: Cursor fallback cell should start [VD generic]");
  if (!c1 || c1.evidence_kind !== "Reported" || !c1.phrase.includes("plain text (3.10.20, Jul 2026)")) {
    errors.push("counterexample Cursor without_apps failed");
  }
  const c2 = by["GitHub Copilot in VS Code::rendering_evidence"];
  const vsCell = cells["Iframe / UI mount"]?.["GitHub Copilot"] || "";
  if (!vsCell.startsWith("[VD inline]")) errors.push("fixture setup: VS Code mount cell should start [VD inline]");
  if (!c2 || c2.evidence_kind !== "Source pinned" || !c2.phrase.includes("not a release run")) {
    errors.push("counterexample VS Code rendering_evidence failed");
  }
  if (fx.cursor_fallback_starts_vd_generic_answer_reported?.expected_evidence_kind !== "Reported") {
    errors.push("fixture record Cursor missing");
  }
  if (fx.vscode_mount_starts_vd_inline_rendering_is_source_pinned?.expected_evidence_kind !== "Source pinned") {
    errors.push("fixture record VS Code missing");
  }
  // baseline link count
  if (baseline?.link_inventory?.count !== 81) errors.push("baseline link count must be 81");
  const srcSha = sha256(sourceText);
  if (j.v7_source_sha256 && j.v7_source_sha256 !== srcSha) errors.push("judgments v7_source_sha256 mismatch");
  if (baseline?.source_md_sha256 && baseline.source_md_sha256 !== srcSha) errors.push("baseline source_md_sha256 mismatch");
  // private path sniff on judgments phrases
  const blob = JSON.stringify(j);
  if (/\/Users\/|\/private\/tmp\/.*receipt|links to a receipt/i.test(blob)) {
    errors.push("private receipt path or forbidden receipt phrasing in judgments");
  }
  return errors;
}

export function main() {
  const j = loadJudgments();
  const src = fs.readFileSync(SOURCE, "utf8");
  const baseline = JSON.parse(fs.readFileSync(BASELINE, "utf8"));
  const errors = validateJudgments(j, src, baseline);
  if (errors.length) {
    console.error("JUDGMENTS_SCHEMA_FAIL");
    for (const e of errors) console.error(" -", e);
    process.exit(1);
  }
  console.log("judgments.json schema OK (36 rows, 9 sentences, fixtures, hashes)");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) main();
