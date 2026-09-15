// node --test rfc/tools/build_e2e_visual_evidence.test.mjs
// Parser and projection checks for the /rfc/e2e/ evidence builder (VISUAL_PLAN.md U1). Mutations are applied to
// in-memory or temporary copies of the committed inputs only; they are never presented as live evidence.
import test from "node:test";
import assert from "node:assert/strict";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { spawnSync } from "node:child_process";
import {
  REPO, INPUTS, OUT_JSON, OUT_HTML, STAGE_ORDER, EvidenceError,
  loadInputs, project, parseJsonl, resolveLifecycle, renderWalkthrough, renderRecord,
} from "./build_e2e_visual_evidence.mjs";

const BUILDER = path.join(REPO, "rfc/tools/build_e2e_visual_evidence.mjs");
const base = loadInputs();
const mutateJson = (key, fn) => { const o = JSON.parse(base[key].toString("utf8")); fn(o); return { ...base, [key]: Buffer.from(JSON.stringify(o)) }; };
const caseOf = (C, name) => C.cases.find((c) => c.case === name);
const rejects = (raw, pattern) => assert.throws(() => project(raw), (e) => e instanceof EvidenceError && pattern.test(e.message));

test("retained files produce six stages whose every fact has a resolvable source", () => {
  const ev = project(base);
  assert.deepEqual(ev.stages.map((s) => s.id), STAGE_ORDER);
  assert.deepEqual(STAGE_ORDER, ["publish", "catalog", "discover", "retrieve", "receipt", "revoke"]);
  const docs = { P: JSON.parse(base.P), C: JSON.parse(base.C) };
  const lines = { PJ: base.PJ.toString("utf8").split("\n"), CJ: base.CJ.toString("utf8").split("\n") };
  for (const [key, fact] of Object.entries(ev.facts)) {
    assert.ok(fact.src.length > 0, key);
    for (const s of fact.src) {
      assert.ok(s.file in INPUTS, `${key}: unknown file ${s.file}`);
      if (s.pointer !== undefined) {
        let cur = docs[s.file];
        for (const part of s.pointer.split("/").slice(1)) { assert.ok(cur && Object.hasOwn(cur, part), `${key}: ${s.file}${s.pointer}`); cur = cur[part]; }
      } else if (s.line !== undefined) {
        assert.equal(JSON.parse(lines[s.file][s.line - 1]).event, s.event, `${key}: ${s.file} line ${s.line}`);
      }
    }
  }
  assert.equal(ev.facts.amount.display, "$400.00 USD");
  assert.equal(ev.facts.publication_id.value, "pub_190192147fd7fd78");
  assert.equal(ev.facts.dataset.value, "okf_kp_publish_kp_20260915t082018z_0387");
});

test("full job references agree with the plan's identity anchors", () => {
  const ev = project(base);
  const jobs = ev.stages.flatMap((s) => s.jobs || []);
  const find = (id) => jobs.find((j) => j.job_id === id);
  for (const id of ["okf_cc_kp_20260915t082018z_0387_merge_head_b402d3731b67", "okf_cc_e2e-20260915t082049z-34e6ed72_retrieval_walk_7f2f49791577", "okf_rcpt_a783c736b3ac936351bef069_22e00a1dd6cb4fc8", "okf_rcpt_d2472cd6fef3b214eb39c20d_2a2706019e808fcb"]) {
    const j = find(id);
    assert.ok(j, id);
    assert.equal(j.project, "test-project-0728-467323");
    assert.equal(j.location, "US");
  }
  assert.equal(find("okf_rcpt_d2472cd6fef3b214eb39c20d_2a2706019e808fcb").output_job, null, "substitution output.job stays null");
  const ops = ev.stages.find((s) => s.id === "catalog").operations;
  assert.deepEqual(ops.map((o) => [o.role, o.job_backed, o.job_id]), [["create_entry", false, null], ["readback_entry", false, null]]);
  assert.deepEqual(ops.map((o) => o.src.seq), [22, 23]);
});

test("removing a required READY readback check prevents generation", () => {
  rejects(mutateJson("P", (P) => { delete P.publish.ready.readback.section_hashes; }), /readback/);
  rejects(mutateJson("P", (P) => { P.publish.ready.readback.dangling = false; }), /readback|dangling/);
});

test("changing the pin dataset prevents generation", () => {
  rejects(mutateJson("C", (C) => { caseOf(C, "connected-approved").catalog.pin.runtime_dataset = "okf_other_dataset"; }), /dataset join/);
});

test("changing a verdict prevents the $400 release", () => {
  rejects(mutateJson("C", (C) => { caseOf(C, "connected-approved").receipt.output.verdict = "REJECTED"; }), /VERIFIED/);
  rejects(mutateJson("C", (C) => { caseOf(C, "connected-approved").consume.decision = "REFUSED"; C.decisions["connected-approved"] = "REFUSED"; }), /RELEASED|decision/);
  rejects(mutateJson("P", (P) => { P.verdict = "E2E_BROKEN"; }), /E2E_PUBLISH_CONNECTED/);
});

test("duplicate or missing case names fail", () => {
  rejects(mutateJson("C", (C) => { C.cases.push(structuredClone(C.cases[1])); }), /duplicate/);
  rejects(mutateJson("C", (C) => { C.cases = C.cases.filter((c) => c.case !== "connected-revocation"); }), /exactly/);
});

test("UNKNOWN later reconciled to ERROR stays refusal evidence", () => {
  const ops = resolveLifecycle(parseJsonl(base.CJ.toString("utf8"), "CJ"), "CJ");
  const late = ops.filter((o) => o.seq === 45 || o.seq === 46);
  assert.deepEqual(late.map((o) => [o.state, o.observed, o.final_event]), [["ERROR", "DONE", "reconciled"], ["ERROR", "DONE", "reconciled"]]);
  assert.equal(ops.length, 46, "each job counted once, not once per lifecycle event");
  const ev = project(base);
  assert.deepEqual(ev.stages.find((s) => s.id === "revoke").jobs.map((j) => [j.state, j.src.line]), [["ERROR", 154], ["ERROR", 158]]);
  // Dropping the reconciliation leaves UNKNOWN unresolved: generation must stop, not treat it as success.
  const lines = base.CJ.toString("utf8").split("\n");
  const noReconcile = lines.filter((l) => !l.includes('"event": "reconciled"')).join("\n");
  assert.throws(() => project({ ...base, CJ: Buffer.from(noReconcile) }), /unresolved/);
  // Turning the server's observed DONE into the final state contradicts the recorded summary.
  const flipped = lines.map((l) => l.includes('"event": "reconciled"') ? l.replace('"state": "ERROR"', '"state": "DONE"') : l).join("\n");
  assert.throws(() => project({ ...base, CJ: Buffer.from(flipped) }), /disagree/);
});

test("the missing substitution output job is not filled with the approved job", () => {
  rejects(mutateJson("C", (C) => { const S = caseOf(C, "connected-sql-substitution"); S.receipt.output.job = caseOf(C, "connected-approved").receipt.output.job; }), /output\.job/);
});

test("HTML-looking evidence text is escaped in generated markup", () => {
  const raw = mutateJson("C", (C) => { caseOf(C, "connected-approved").bind.sdk_publication_id = "<img src=x onerror=alert(1)>"; });
  const ev = project(raw);
  const html = renderWalkthrough(ev).html + renderRecord(ev);
  assert.ok(!html.includes("<img src=x"), "raw tag leaked");
  assert.ok(html.includes("&lt;img src=x onerror=alert(1)&gt;"));
});

test("Catalog entry must be run-owned and written after the head switch", () => {
  rejects(mutateJson("P", (P) => { P.state_trace.find((t) => t.state === "KC_APPLIED").at = "2026-09-15T08:20:40.000000+00:00"; }), /timestamps|precedes/);
});

test("outputs expose no local machine paths", () => {
  const json = fs.readFileSync(path.join(REPO, OUT_JSON), "utf8");
  const html = fs.readFileSync(path.join(REPO, OUT_HTML), "utf8");
  for (const text of [json, html]) assert.ok(!/\/Users\/|~\/|argv|GOOGLE_APPLICATION_CREDENTIALS/.test(text));
});

test("--check passes at HEAD and fails on stale source bytes or edited outputs", () => {
  const ok = spawnSync(process.execPath, [BUILDER, "--check"], { cwd: REPO, encoding: "utf8" });
  assert.equal(ok.status, 0, ok.stdout + ok.stderr);
  const tmp = fs.mkdtempSync(path.join(os.tmpdir(), "e2e-visual-"));
  try {
    for (const rel of [...Object.values(INPUTS), OUT_JSON, OUT_HTML]) {
      fs.mkdirSync(path.dirname(path.join(tmp, rel)), { recursive: true });
      fs.copyFileSync(path.join(REPO, rel), path.join(tmp, rel));
    }
    const run = () => spawnSync(process.execPath, [BUILDER, "--check", "--root", tmp], { encoding: "utf8" });
    assert.equal(run().status, 0, "copy starts in sync");
    fs.appendFileSync(path.join(tmp, INPUTS.P), "\n");
    const stale = run();
    assert.equal(stale.status, 1, stale.stdout);
    assert.match(stale.stdout, /STALE rfc\/e2e\/visual-evidence\.json/);
    fs.copyFileSync(path.join(REPO, INPUTS.P), path.join(tmp, INPUTS.P));
    const htmlPath = path.join(tmp, OUT_HTML);
    fs.writeFileSync(htmlPath, fs.readFileSync(htmlPath, "utf8").replace(">$400.00 USD<", ">$500.00 USD<"));
    assert.equal(run().status, 1, "edited generated value is stale");
    fs.copyFileSync(path.join(REPO, OUT_HTML), htmlPath);
    fs.writeFileSync(path.join(tmp, INPUTS.C), "{}");
    assert.equal(run().status, 2, "contradictory source stops generation");
  } finally {
    fs.rmSync(tmp, { recursive: true, force: true });
  }
});
