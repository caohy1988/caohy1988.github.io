#!/usr/bin/env node
// Evidence builder for the /rfc/e2e/ human walkthrough (rfc/e2e/VISUAL_PLAN.md, U1 / KTD3).
//
//   node rfc/tools/build_e2e_visual_evidence.mjs          write rfc/e2e/visual-evidence.json and the generated regions of rfc/e2e/index.html
//   node rfc/tools/build_e2e_visual_evidence.mjs --check  exit 1 if either differs from what the committed run files produce
//   --root DIR                                            read inputs and write outputs under DIR instead of the repository (tests)
//
// Reads only the pinned, committed records of publish run kp-20260915t082018z-0387 and consume run
// e2e-20260915t082049z-34e6ed72, validates the joins in the plan's evidence-binding table and projects an allowlisted
// shape. Every observed value carries its source: file plus JSON Pointer, or journal line plus event. Missing or
// contradictory evidence throws, so there is no fallback success record. Editorial copy (step titles, plain-English
// meaning, tape offsets) lives under `editorial` and is never a recorded value. No network, no cloud calls.
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { isDeepStrictEqual } from "node:util";
import { fileURLToPath } from "node:url";

export const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
export const PUBLISH_RUN = "kp-20260915t082018z-0387";
export const CONSUME_RUN = "e2e-20260915t082049z-34e6ed72";
export const PROJECT = "test-project-0728-467323";
const RUN_DIR = `rfc/spikes/bq-graph/evidence/publish-connected/${PUBLISH_RUN}`;
const CON_DIR = `${RUN_DIR}/connected/${CONSUME_RUN}`;
// Canonical inputs. The shorter connected/connected_live.json alias is deliberately not read.
export const INPUTS = {
  P: `${RUN_DIR}/publish_connected_live.json`,
  PJ: `${RUN_DIR}/publish/journal.jsonl`,
  C: `${CON_DIR}/connected_live.json`,
  CJ: `${CON_DIR}/journal.jsonl`,
  CAT_LIST: `${CON_DIR}/catalog/connected-approved__catalog_list_0.json`,
  CAT_ENTRY: `${CON_DIR}/catalog/connected-approved__catalog_entry.json`,
  REPORT: "rfc/spikes/bq-graph/evidence/report-publish-connected.md",
};
const LABELS = {
  P: "publish_connected_live.json", PJ: "publish/journal.jsonl", C: "connected_live.json", CJ: "connected journal.jsonl",
  CAT_LIST: "retained Catalog list", CAT_ENTRY: "retained Catalog entry", REPORT: "report-publish-connected.md",
};
export const OUT_JSON = "rfc/e2e/visual-evidence.json";
export const OUT_HTML = "rfc/e2e/index.html";
export const SCHEMA = "rfc-e2e-visual-evidence/1";
export const CASES = ["connected-approved", "connected-sql-substitution", "connected-denied-intermediate", "connected-unauthorized-output", "connected-revocation"];
export const REGIONS = ["walkthrough", "record"];

export class EvidenceError extends Error {}
const need = (ok, msg) => { if (!ok) throw new EvidenceError(msg); };
const sha256 = (buf) => crypto.createHash("sha256").update(buf).digest("hex");
const href = (rel) => "../" + rel.replace(/^rfc\//, ""); // page lives at rfc/e2e/
const esc = (v) => String(v).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

// ---------------------------------------------------------------- parsing

export function parseJsonl(text, file) {
  const out = [];
  String(text).split("\n").forEach((line, i) => {
    if (!line.trim()) return;
    let rec;
    try { rec = JSON.parse(line); } catch (e) { throw new EvidenceError(`${file} line ${i + 1}: invalid JSON`); }
    out.push({ line: i + 1, rec });
  });
  return out;
}

const LIFECYCLE = new Set(["intended", "submitted", "terminal", "unknown", "reconciled"]);

// One operation per journal sequence, in append order. Final state is the last lifecycle event (so UNKNOWN later
// reconciled to ERROR stays ERROR). A job reference is the complete (project, location, job_id) triple.
export function resolveLifecycle(entries, file) {
  const bySeq = new Map();
  for (const e of entries) {
    if (!LIFECYCLE.has(e.rec.event)) continue;
    need(Number.isInteger(e.rec.seq), `${file} line ${e.line}: lifecycle event without integer seq`);
    if (!bySeq.has(e.rec.seq)) bySeq.set(e.rec.seq, []);
    bySeq.get(e.rec.seq).push(e);
  }
  const ops = [];
  const seenJobs = new Set();
  for (const [seq, evs] of bySeq) {
    const refs = new Set(evs.filter((e) => e.rec.job_id).map((e) => `${e.rec.project}|${e.rec.location}|${e.rec.job_id}`));
    need(refs.size <= 1, `${file} seq ${seq}: conflicting job references`);
    const roles = new Set(evs.map((e) => e.rec.role));
    need(roles.size === 1, `${file} seq ${seq}: conflicting roles`);
    const last = evs[evs.length - 1];
    const r = last.rec;
    const jobBacked = r.job_backed === true || (r.job_backed === undefined && r.engine === "bigquery");
    let job = null;
    if (r.job_id) {
      need(r.project && r.location, `${file} seq ${seq}: incomplete job reference`);
      job = { project: r.project, location: r.location, job_id: r.job_id };
      const key = `${r.project}|${r.location}|${r.job_id}`;
      need(!seenJobs.has(key), `${file}: job ${r.job_id} appears under two sequences`);
      seenJobs.add(key);
    }
    ops.push({
      seq, role: r.role, job_backed: jobBacked, job, state: r.state, terminal: r.terminal === true, final_event: r.event,
      line: last.line, lines: evs.map((e) => e.line), error: r.error ?? null, observed: r.observed ?? null,
      at: r.terminal_at ?? r.reconciled_at ?? null,
    });
  }
  return ops;
}

function reader(file, doc) {
  const get = (pointer) => {
    let cur = doc;
    for (const part of pointer.split("/").slice(1).map((p) => p.replace(/~1/g, "/").replace(/~0/g, "~"))) {
      need(cur !== null && typeof cur === "object" && Object.prototype.hasOwnProperty.call(cur, part), `${file}${pointer}: missing`);
      cur = cur[part];
    }
    return cur;
  };
  return { get, ref: (pointer) => ({ file, pointer }) };
}

const exactTrue = (obj, keys, what) => {
  need(obj && typeof obj === "object" && !Array.isArray(obj), `${what}: not an object`);
  need(isDeepStrictEqual(Object.keys(obj).sort(), [...keys].sort()), `${what}: expected exactly ${keys.join(", ")}`);
  for (const k of keys) need(obj[k] === true, `${what}.${k} is not true`);
};
const utcTime = (iso) => { need(/^\d{4}-\d\d-\d\dT\d\d:\d\d:\d\d/.test(String(iso)), `bad timestamp ${iso}`); return `${String(iso).slice(11, 19)} UTC`; };
const utcDateTime = (iso) => `${String(iso).slice(0, 10)} ${utcTime(iso)}`;

// ---------------------------------------------------------------- projection

export function loadInputs(root = REPO) {
  const raw = {};
  for (const [k, rel] of Object.entries(INPUTS)) {
    const abs = path.join(root, rel);
    need(fs.existsSync(abs), `missing input ${k}: ${rel}`);
    raw[k] = fs.readFileSync(abs);
  }
  return raw;
}

const EDITORIAL = {
  publish: {
    plane: "b", tags: ["BigQuery Knowledge Publish"], rail: ["Publish", "BigQuery fixes one version"],
    title: "Publish one fixed version in BigQuery",
    meaning: "Finance’s Open Knowledge Format files define Gross Margin, its rules and the approved calculation. BigQuery stores them as a fixed version, checks it, then makes it current.",
    highlight: ["okf", "publication"], links: ["okf-publication"], tape: 11.7,
  },
  catalog: {
    plane: "a", tags: ["Knowledge Catalog"], rail: ["Catalog", "a pointer, not the authority"],
    title: "Write the Knowledge Catalog pointer",
    meaning: "After the switch, Knowledge Catalog gets an entry naming the version BigQuery published. Catalog is the directory; BigQuery stays the serving authority.",
    highlight: ["publication", "catalog"], links: ["publication-catalog"], tape: 27.4,
  },
  discover: {
    plane: "a", tags: ["Knowledge Catalog", "Requester"], rail: ["Discover", "the requester finds that version"],
    title: "Discover it as the requester",
    meaning: "The agent’s tool reads Knowledge Catalog as the restricted requester and pins the version named there. Finding an entry grants no access to its contents.",
    highlight: ["catalog", "requester"], links: ["catalog-requester"], tape: 39.8,
  },
  retrieve: {
    plane: "b", tags: ["BigQuery Knowledge Publish", "Requester"], rail: ["Retrieve", "fixed context, requester’s access"],
    title: "Retrieve the pinned context",
    meaning: "BigQuery returns the pinned definition, rule and approved calculation under the requester’s access. The current pointer is observed, not silently followed.",
    highlight: ["publication", "requester"], links: [], tape: 39.8,
  },
  receipt: {
    plane: "c", tags: ["Receipt"], rail: ["Receipt", "checked before release"],
    title: "Check the receipt, then release",
    meaning: "A receipt ties the BigQuery job, the calculation and the result. The consumer checks it before releasing any number.",
    highlight: ["requester", "receipt"], links: ["requester-receipt"], tape: 48.8,
  },
  revoke: {
    plane: "c", tags: ["Requester"], rail: ["Revoke", "later requests refused"],
    title: "Remove access, then recheck",
    meaning: "Access was removed and denial observed repeatedly. Three routes were then retried; the earlier release authorizes nothing new.",
    highlight: ["requester", "receipt"], links: [], tape: 69.8, stop: true,
  },
};
export const STAGE_ORDER = Object.keys(EDITORIAL);

export function project(raw) {
  const sources = {};
  for (const [k, rel] of Object.entries(INPUTS)) sources[k] = { path: rel, sha256: sha256(raw[k]), bytes: raw[k].length };
  let P, C;
  try { P = JSON.parse(raw.P.toString("utf8")); } catch (e) { throw new EvidenceError("P: invalid JSON"); }
  try { C = JSON.parse(raw.C.toString("utf8")); } catch (e) { throw new EvidenceError("C: invalid JSON"); }
  const PJ = parseJsonl(raw.PJ.toString("utf8"), "PJ");
  const CJ = parseJsonl(raw.CJ.toString("utf8"), "CJ");
  const p = reader("P", P), c = reader("C", C);

  const facts = {};
  const F = (key, value, display, src) => {
    need(!(key in facts), `duplicate fact ${key}`);
    need(Array.isArray(src) && src.length > 0, `fact ${key} has no source`);
    facts[key] = { value, display: String(display), src };
    return facts[key].display;
  };
  const jref = (file, e) => ({ file, line: e.line, event: e.rec.event, ...(Number.isInteger(e.rec.seq) ? { seq: e.rec.seq } : {}) });
  const oneEvent = (entries, file, event) => {
    const hits = entries.filter((e) => e.rec.event === event);
    need(hits.length === 1, `${file}: expected exactly one ${event} event, found ${hits.length}`);
    return hits[0];
  };

  // ---- identity (plan: Global identity)
  need(p.get("/run_id") === PUBLISH_RUN, `P.run_id is not ${PUBLISH_RUN}`);
  need(p.get("/mode") === "live", "P.mode is not live");
  need(p.get("/verdict") === "E2E_PUBLISH_CONNECTED", "P.verdict is not E2E_PUBLISH_CONNECTED");
  need(c.get("/run_id") === CONSUME_RUN, `C.run_id is not ${CONSUME_RUN}`);
  need(p.get("/connected/run_id") === c.get("/run_id"), "P.connected.run_id does not match C.run_id");
  need(c.get("/mode") === "live", "C.mode is not live");
  need(c.get("/verdict") === "E2E_CONNECTED" && p.get("/connected/verdict") === "E2E_CONNECTED", "connected verdict is not E2E_CONNECTED in both records");
  exactTrue(p.get("/checks"), ["author", "author_identity", "catalog_pin", "cleanup", "connected", "consumed", "head_switched", "originals", "publish_journal_resolved", "ready"], "P.checks");
  need(oneEvent(PJ, "PJ", "opened").rec.run_id === PUBLISH_RUN, "PJ opened for another run");
  need(oneEvent(CJ, "CJ", "opened").rec.run_id === CONSUME_RUN, "CJ opened for another run");

  const cases = c.get("/cases");
  need(Array.isArray(cases), "C.cases is not an array");
  const names = cases.map((x) => x && x.case);
  need(new Set(names).size === names.length, "C.cases has duplicate case names");
  need(isDeepStrictEqual([...names].sort(), [...CASES].sort()), `C.cases is not exactly ${CASES.join(", ")}`);
  need(isDeepStrictEqual([...c.get("/selected_cases")].sort(), [...CASES].sort()), "C.selected_cases disagrees with C.cases");
  const caseIdx = (name) => names.indexOf(name);
  const cp = (name, rest) => `/cases/${caseIdx(name)}${rest}`;
  const A = "connected-approved", S = "connected-sql-substitution", D = "connected-denied-intermediate", U = "connected-unauthorized-output", V = "connected-revocation";
  for (const name of CASES) {
    need(c.get(`/acceptance/${name}`) === "MET" && c.get(cp(name, "/acceptance/status")) === "MET", `${name}: acceptance not MET`);
    need(c.get(`/decisions/${name}`) === c.get(cp(name, "/consume/decision")), `${name}: C.decisions disagrees with the case record`);
    need(p.get(`/connected/summary/cases/${name}/decision`) === c.get(`/decisions/${name}`), `${name}: P summary decision disagrees`);
  }

  const project_ = c.get(cp(A, "/catalog/pin/runtime_project"));
  need(project_ === PROJECT, "approved pin runtime_project is not the recorded project");
  F("run_publish_id", PUBLISH_RUN, PUBLISH_RUN, [p.ref("/run_id"), jref("PJ", oneEvent(PJ, "PJ", "opened"))]);
  F("run_consume_id", CONSUME_RUN, CONSUME_RUN, [c.ref("/run_id"), p.ref("/connected/run_id")]);
  F("run_verdict", p.get("/verdict"), p.get("/verdict"), [p.ref("/verdict")]);
  F("run_mode", "live", "live (the recorded invocation, not this page)", [p.ref("/mode"), c.ref("/mode")]);
  F("run_project", project_, project_, [c.ref(cp(A, "/catalog/pin/runtime_project"))]);
  F("run_started", p.get("/started_at"), utcDateTime(p.get("/started_at")), [p.ref("/started_at")]);
  F("run_finished", p.get("/finished_at"), utcTime(p.get("/finished_at")), [p.ref("/finished_at")]);

  // ---- publication id and dataset joins
  const pub = p.get("/author/publication_id");
  const pubJoins = ["/author/publication_id", "/publish/ready/row/publication_id", "/publish/ready/publication_id", "/publish/head/to", "/publish/head/observed", "/publish/catalog_pin/publication_id", "/consumed/publication_id"].map((x) => [p, x])
    .concat([cp(A, "/catalog/pin/publication_id"), cp(A, "/publication/publication_id"), cp(A, "/retrieval/scope/publication_id")].map((x) => [c, x]));
  for (const [r, x] of pubJoins) need(r.get(x) === pub, `publication join: ${x} is not ${pub}`);
  const dataset = p.get("/owned/dataset");
  for (const [r, x] of [[p, "/publish/dataset"], [p, "/consumed/dataset"], [p, "/consumed/observed/pin_runtime_dataset"], [c, cp(A, "/catalog/pin/runtime_dataset")]]) need(r.get(x) === dataset, `dataset join: ${x} is not ${dataset}`);
  F("publication_id", pub, pub, pubJoins.map(([r, x]) => r.ref(x)));
  F("dataset", dataset, dataset, [p.ref("/owned/dataset"), p.ref("/publish/dataset"), p.ref("/consumed/dataset"), c.ref(cp(A, "/catalog/pin/runtime_dataset"))]);

  // ---- journals: resolved operations
  const pOps = resolveLifecycle(PJ, "PJ");
  const cOps = resolveLifecycle(CJ, "CJ");
  for (const op of [...pOps, ...cOps]) need(op.terminal, `journal seq ${op.seq} (${op.role}) is unresolved`);
  const pJobs = pOps.filter((o) => o.job_backed);
  const pubJobs = p.get("/publish/jobs");
  need(pubJobs.length === pJobs.length, `P.publish.jobs has ${pubJobs.length} jobs, PJ resolves ${pJobs.length}`);
  for (const j of pubJobs) {
    const op = pOps.find((o) => o.seq === j.seq);
    need(op && op.job && op.job.job_id === j.job_id && op.job.project === j.project && op.job.location === j.location && op.state === j.state && op.role === j.role, `P.publish.jobs seq ${j.seq} disagrees with PJ`);
  }
  const cjJobs = c.get("/journal/jobs");
  need(cOps.length === cjJobs.length && cOps.length === c.get("/journal/summary/actual_jobs"), "C.journal job count disagrees with CJ");
  for (const j of cjJobs) {
    const op = cOps.find((o) => o.seq === j.seq);
    need(op && op.job && op.job.job_id === j.job_id && op.job.project === j.project && op.job.location === j.location && op.state === j.state, `C.journal.jobs seq ${j.seq} disagrees with CJ`);
  }
  const byState = {};
  for (const op of cOps) byState[op.state] = (byState[op.state] || 0) + 1;
  need(isDeepStrictEqual(byState, c.get("/journal/summary/by_state")), "CJ final states disagree with C.journal.summary.by_state");
  const jobChip = (file, op, label) => ({ label, role: op.role, ...op.job, state: op.state, src: { file, line: op.line, event: op.final_event, seq: op.seq } });

  // ---- stage 1: publish
  const author = p.get("/author");
  for (const k of ["ok", "bundle_clean", "checkout_head_matches_pin", "projection_valid"]) need(author[k] === true, `P.author.${k} is not true`);
  const trace = p.get("/state_trace");
  const traceAt = (state) => { const i = trace.findIndex((t) => t.state === state); need(i >= 0 && trace.filter((t) => t.state === state).length === 1, `state_trace ${state} missing or repeated`); return i; };
  const order = ["PLANNED", "PREPARING", "BQ_STAGED", "BQ_COMMITTED", "KC_APPLIED", "COMPLETE"];
  need(isDeepStrictEqual(trace.map((t) => t.state), order), "state_trace order is not PLANNED → … → COMPLETE");
  for (let i = 1; i < trace.length; i++) need(trace[i].at > trace[i - 1].at, "state_trace timestamps are not increasing");
  const row = p.get("/publish/ready/row");
  need(p.get("/publish/ready/state") === "READY" && row.validation_status === "READY", "publication is not READY");
  exactTrue(p.get("/publish/ready/readback"), ["dangling", "distinct", "edge_rows", "edges_sha256", "node_rows", "nodes_sha256", "section_hashes"], "P.publish.ready.readback");
  need(row.node_count === author.nodes && row.edge_count === author.edges && row.source_pin === author.source_pin, "READY row counts or pin disagree with author");
  const pjPublish = oneEvent(PJ, "PJ", "publish");
  need(pjPublish.rec.state === p.get("/publish/ready/state") && isDeepStrictEqual(pjPublish.rec.readback, p.get("/publish/ready/readback")), "PJ publish event disagrees with P.publish.ready");
  for (const k of ["publication_id", "validation_status", "ready_at", "node_count", "edge_count", "section_count", "source_pin"]) need(pjPublish.rec.row[k] === row[k], `PJ publish row.${k} disagrees`);
  const rb = F("readback_checks", 7, "7 of 7", [p.ref("/publish/ready/readback"), jref("PJ", pjPublish)]);
  F("nodes", author.nodes, author.nodes, [p.ref("/author/nodes"), p.ref("/publish/ready/row/node_count")]);
  F("edges", author.edges, author.edges, [p.ref("/author/edges"), p.ref("/publish/ready/row/edge_count")]);
  F("sections", row.section_count, row.section_count, [p.ref("/publish/ready/row/section_count"), jref("PJ", pjPublish)]);
  F("ready_state", "READY", "READY", [p.ref("/publish/ready/state"), p.ref("/publish/ready/row/validation_status"), jref("PJ", pjPublish)]);
  F("ready_at", row.ready_at, utcTime(row.ready_at), [p.ref("/publish/ready/row/ready_at")]);
  F("source_pin", author.source_pin, author.source_pin.slice(0, 7), [p.ref("/author/source_pin"), p.ref("/publish/ready/row/source_pin")]);

  const head = p.get("/publish/head");
  need(head.from === null && head.to === pub && head.observed === pub && head.state === "SWITCHED" && head.merge_state === "DONE", "head is not null → published, SWITCHED, merge DONE");
  const committed = trace[traceAt("BQ_COMMITTED")];
  need(committed.head_from === null && committed.head_to === pub && committed.merge_job_id === head.merge_job_id && committed.jobs.includes(head.merge_job_id), "BQ_COMMITTED trace disagrees with head");
  const pjHead = oneEvent(PJ, "PJ", "head_switch");
  need(pjHead.rec.from === null && pjHead.rec.to === pub && pjHead.rec.observed === pub && pjHead.rec.state === "SWITCHED", "PJ head_switch disagrees");
  const mergeOp = pOps.find((o) => o.role === "merge_head");
  need(mergeOp && mergeOp.job && mergeOp.job.job_id === head.merge_job_id && mergeOp.state === "DONE" && mergeOp.job.project === PROJECT, "merge_head job missing, not DONE or not in the recorded project");
  const postRead = pOps.find((o) => o.role === "read_head" && o.seq > mergeOp.seq);
  need(postRead && postRead.state === "DONE" && committed.jobs.includes(postRead.job.job_id), "no post-merge read_head in BQ_COMMITTED");
  need(pjPublish.line < pjHead.line, "head switched before the READY publish event");
  F("head_from", null, "none", [p.ref("/publish/head/from"), p.ref(`/state_trace/${traceAt("BQ_COMMITTED")}/head_from`), jref("PJ", pjHead)]);
  F("head_state", "SWITCHED", "SWITCHED", [p.ref("/publish/head/state"), jref("PJ", pjHead)]);
  F("head_at", committed.at, utcTime(committed.at), [p.ref(`/state_trace/${traceAt("BQ_COMMITTED")}/at`)]);
  const identity = p.get("/publish/author_identity");
  need(identity.status === "BOUND" && identity.jobs_compared === pJobs.length && Object.keys(identity.jobs).length === pJobs.length, "author identity is not BOUND over every publish job");
  F("author_jobs", pJobs.length, pJobs.length, [p.ref("/publish/author_identity/jobs_compared"), p.ref("/publish/jobs")]);
  F("author_identity", "BOUND", "BOUND", [p.ref("/publish/author_identity/status")]);
  const publishJobs = ["load_nodes", "load_edges", "readback_nodes", "readback_edges", "insert_publication", "publication_status", "merge_head"]
    .map((role) => { const op = pOps.find((o) => o.role === role); need(op && op.state === "DONE", `publish job ${role} missing or not DONE`); return jobChip("PJ", op, role); })
    .concat([jobChip("PJ", postRead, "read_head after merge")]);

  // ---- stage 2: catalog pointer
  const pin = p.get("/publish/catalog_pin");
  need(pin.readback_status === "OK" && pin.publication_id === pub && pin.authored_aspects_present === true, "Catalog pin readback is not OK for the publication");
  const kc = trace[traceAt("KC_APPLIED")];
  need(kc.entry === pin.entry && kc.at > committed.at, "KC_APPLIED trace disagrees with pin or precedes the head switch");
  const pjPin = oneEvent(PJ, "PJ", "write_pin");
  need(pjPin.rec.entry === pin.entry && pjPin.rec.publication_id === pub && pjPin.rec.readback_status === "OK" && pjPin.line > pjHead.line, "PJ write_pin disagrees or precedes the head switch");
  need(pin.entry.startsWith(p.get("/owned/entry_prefix")) && p.get("/consumed/checks/entry_is_owned") === true, "Catalog entry is not run-owned");
  const catOps = ["create_entry", "readback_entry"].map((role) => {
    const op = pOps.find((o) => o.role === role);
    need(op && op.job_backed === false && op.job === null && op.state === "DONE" && op.error === null && op.terminal, `Catalog ${role} is not a DONE non-job operation`);
    return { label: role, role, job_backed: false, job_id: null, state: op.state, target: pin.entry, src: { file: "PJ", line: op.line, event: op.final_event, seq: op.seq } };
  });
  F("pin_entry", pin.entry, pin.entry, [p.ref("/publish/catalog_pin/entry"), p.ref(`/state_trace/${traceAt("KC_APPLIED")}/entry`), jref("PJ", pjPin)]);
  F("pin_readback", "OK", "OK", [p.ref("/publish/catalog_pin/readback_status"), jref("PJ", pjPin)]);
  F("pin_at", kc.at, utcTime(kc.at), [p.ref(`/state_trace/${traceAt("KC_APPLIED")}/at`)]);

  // ---- stage 3: discover
  need(c.get("/caller/caller_is_requester") === true && c.get("/caller/status") === "REQUESTER", "Catalog caller is not the requester");
  need(c.get("/grant/catalog_before/status") === "DENIED", "Catalog was not denied before the grant");
  need(c.get("/grant/catalog_wait/status") === "ALLOWED" && c.get("/grant/catalog_wait/observed") === true, "Catalog grant not observed");
  need(c.get("/grant/stable/stable") === true, "grant not stable");
  need(c.get(cp(A, "/catalog/status")) === "OK" && c.get(cp(A, "/catalog/mode")) === "catalog", "approved Catalog discovery is not OK");
  const consumed = p.get("/consumed");
  need(consumed.status === "MATCH", "consumed publication is not MATCH");
  exactTrue(consumed.checks, ["catalog_ok", "entry_is_owned", "head_is_published", "pin_dataset", "pin_publication", "publication_ok", "store_dataset"], "P.consumed.checks");
  const rawEvent = (name) => { const hits = CJ.filter((e) => e.rec.event === "catalog_raw" && e.rec.name === name); need(hits.length === 1, `CJ catalog_raw ${name} missing or repeated`); return hits[0]; };
  const rawList = rawEvent(`${A}__catalog_list_0`), rawEntry = rawEvent(`${A}__catalog_entry`);
  need(rawEntry.rec.raw_sha256 === c.get(cp(A, "/catalog/raw_entry_sha256")), "approved raw entry hash disagrees with CJ");
  need(isDeepStrictEqual(c.get(cp(A, "/catalog/discovery/list_sha256")), [rawList.rec.raw_sha256]), "approved raw list hash disagrees with CJ");
  // The retained copies are redacted: their bytes are checked against retained_sha256 only, never against raw_sha256.
  need(sha256(raw.CAT_LIST) === rawList.rec.retained_sha256, "retained Catalog list bytes do not match retained_sha256");
  need(sha256(raw.CAT_ENTRY) === rawEntry.rec.retained_sha256, "retained Catalog entry bytes do not match retained_sha256");
  const catalogReads = [rawList, rawEntry].map((e) => ({ name: e.rec.name, at: e.rec.at, raw_sha256: e.rec.raw_sha256, retained_sha256: e.rec.retained_sha256, retained_file: e === rawList ? INPUTS.CAT_LIST : INPUTS.CAT_ENTRY, src: jref("CJ", e) }));
  F("catalog_before", "DENIED", "DENIED", [c.ref("/grant/catalog_before/status")]);
  F("catalog_before_http", c.get("/grant/catalog_before/http_status"), `HTTP ${c.get("/grant/catalog_before/http_status")}`, [c.ref("/grant/catalog_before/http_status")]);
  F("catalog_after", "ALLOWED", "ALLOWED", [c.ref("/grant/catalog_wait/status"), c.ref("/grant/catalog_wait/observed")]);
  F("catalog_wait_s", c.get("/grant/catalog_wait/waited_s"), `${c.get("/grant/catalog_wait/waited_s")} s`, [c.ref("/grant/catalog_wait/waited_s")]);
  F("caller_is_requester", true, "true", [c.ref("/caller/caller_is_requester")]);
  F("discovery_status", "OK", "OK", [c.ref(cp(A, "/catalog/status")), jref("CJ", rawList), jref("CJ", rawEntry)]);
  F("consumed_status", "MATCH", "MATCH", [p.ref("/consumed/status")]);
  F("consumed_checks", 7, "7 of 7", [p.ref("/consumed/checks")]);

  // ---- stage 4: retrieve
  need(c.get(cp(A, "/publication/status")) === "OK" && c.get(cp(A, "/publication/head/matches_pin")) === true, "approved publication not OK or head does not match pin");
  exactTrue(c.get(cp(A, "/publication/checks")), ["compiler_version", "seed_file_sha256", "seed_kind", "seed_path", "seed_scope", "source_manifest_sha256", "source_pin"], "approved publication.checks");
  need(c.get(cp(A, "/retrieval/status")) === "OK" && c.get(cp(A, "/retrieval/reached")) === true, "approved retrieval not OK/reached");
  need(c.get(cp(A, "/payload/status")) === "CONSISTENT", "approved payload not CONSISTENT");
  need(c.get(cp(A, "/bind/status")) === "BOUND", "approved bind not BOUND");
  need(c.get(cp(A, "/authorization/status")) === "ALLOWED" && c.get(cp(A, "/authorization/denied")) === 0, "approved authorization not ALLOWED");
  const engine = c.get(cp(A, "/retrieval/scope/engine"));
  need(engine === "fallback" && c.get("/engine") === "fallback", "retrieval engine is not the recorded relational fallback");
  const tables = c.get(cp(A, "/authorization/tables"));
  const retrievalJobs = c.get(cp(A, "/retrieval/timing/jobs")).map((j, i) => {
    const op = cOps.find((o) => o.job && o.job.job_id === j.job_id && o.job.project === j.project && o.job.location === j.location);
    need(op && op.state === "DONE" && j.state === "DONE", `approved retrieval job ${j.job_id} not DONE in CJ`);
    return { ...jobChip("CJ", op, `retrieval ${j.stage}`), case_src: { file: "C", pointer: cp(A, `/retrieval/timing/jobs/${i}/job_id`) } };
  });
  need(retrievalJobs.some((j) => j.label === "retrieval walk"), "approved retrieval has no walk job");
  F("publication_status", "OK", "OK", [c.ref(cp(A, "/publication/status"))]);
  F("head_matches_pin", true, "matches the pin", [c.ref(cp(A, "/publication/head/matches_pin"))]);
  F("retrieval_status", "OK", "OK", [c.ref(cp(A, "/retrieval/status")), c.ref(cp(A, "/retrieval/reached"))]);
  F("payload_status", "CONSISTENT", "CONSISTENT", [c.ref(cp(A, "/payload/status"))]);
  F("bind_status", "BOUND", "BOUND", [c.ref(cp(A, "/bind/status"))]);
  F("authorization_status", "ALLOWED", "ALLOWED", [c.ref(cp(A, "/authorization/status"))]);
  F("authorization_denied", 0, `0 of ${tables.length}`, [c.ref(cp(A, "/authorization/denied")), c.ref(cp(A, "/authorization/tables"))]);
  F("retrieval_engine", engine, engine, [c.ref(cp(A, "/retrieval/scope/engine")), c.ref("/engine")]);
  F("sdk_publication_id", c.get(cp(A, "/bind/sdk_publication_id")), c.get(cp(A, "/bind/sdk_publication_id")), [c.ref(cp(A, "/bind/sdk_publication_id"))]);
  need(c.get(cp(A, "/bind/sdk_publication_id")) !== pub, "SDK receipt publication id unexpectedly equals the graph publication id");

  // ---- stage 5: receipt and release
  const rc = (x) => c.get(cp(A, `/receipt${x}`));
  need(rc("/invoked") === true && rc("/live") === true && rc("/exit_code") === 0 && rc("/released") === true, "approved receipt was not a live released invocation");
  need(rc("/output/verdict") === "VERIFIED" && rc("/receipt/verdict") === "VERIFIED", "approved receipt is not VERIFIED");
  need(rc("/output/execution_match") === "MATCH" && rc("/receipt/execution_match") === "MATCH", "approved receipt execution is not MATCH");
  need(isDeepStrictEqual(rc("/output/job"), rc("/receipt/job")) && rc("/receipt/job/job_id") && rc("/receipt/job/project") === PROJECT, "approved receipt job reference incomplete or inconsistent");
  const display = c.get(cp(A, "/consume/display"));
  need(c.get(cp(A, "/consume/decision")) === "RELEASED" && c.get(`/decisions/${A}`) === "RELEASED", "approved case was not RELEASED");
  need(p.get("/connected/summary/answer") === display && p.get("/connected/summary/receipt_verdict") === "VERIFIED", "P summary answer or receipt verdict disagrees");
  const amount = /^\[LIVE\] Gross margin: (\$\d+\.\d\d USD) · VERIFIED$/.exec(display);
  need(amount, "approved display is not a recorded VERIFIED live release line");
  need(c.get(`/job_inventory/receipt`).includes(rc("/receipt/job/job_id")), "approved receipt job not in the receipt inventory");
  F("amount", amount[1], amount[1], [c.ref(cp(A, "/consume/display")), p.ref("/connected/summary/answer")]);
  F("answer_display", display, display, [c.ref(cp(A, "/consume/display"))]);
  F("approved_decision", "RELEASED", "RELEASED", [c.ref(cp(A, "/consume/decision")), c.ref(`/decisions/${A}`)]);
  F("receipt_verdict", "VERIFIED", "VERIFIED", [c.ref(cp(A, "/receipt/receipt/verdict")), c.ref(cp(A, "/receipt/output/verdict")), p.ref("/connected/summary/receipt_verdict")]);
  F("execution_match", "MATCH", "MATCH", [c.ref(cp(A, "/receipt/receipt/execution_match"))]);
  const issued = new Date(rc("/receipt/issued_at") * 1000).toISOString();
  F("receipt_issued", issued, utcTime(issued), [c.ref(cp(A, "/receipt/receipt/issued_at"))]);
  const receiptJob = { label: "approved receipt", ...rc("/receipt/job"), state: "VERIFIED", src: { file: "C", pointer: cp(A, "/receipt/receipt/job") } };

  const sc = (x) => c.get(cp(S, x));
  need(sc("/receipt/invoked") === true && sc("/receipt/output/verdict") === "REJECTED" && sc("/receipt/output/execution_match") === "MISMATCH", "substitution receipt is not REJECTED / MISMATCH");
  need(isDeepStrictEqual(sc("/receipt/output/reason_codes"), ["sql_mismatch"]), "substitution reason codes are not [sql_mismatch]");
  need(sc("/receipt/output/job") === null, "substitution output.job is not null");
  need(sc("/receipt/receipt/job/job_id") && sc("/receipt/receipt/job/job_id") !== rc("/receipt/job/job_id"), "substitution receipt job missing or equals the approved job");
  need(sc("/consume/decision") === "REFUSED" && sc("/receipt/released") === false, "substitution was not refused");
  F("sub_verdict", "REJECTED", "REJECTED", [c.ref(cp(S, "/receipt/output/verdict"))]);
  F("sub_match", "MISMATCH", "MISMATCH", [c.ref(cp(S, "/receipt/output/execution_match"))]);
  F("sub_reason", "sql_mismatch", "sql_mismatch", [c.ref(cp(S, "/receipt/output/reason_codes"))]);
  F("sub_decision", "REFUSED", "Refused", [c.ref(cp(S, "/consume/decision"))]);
  const subJob = { label: "substitution receipt", ...sc("/receipt/receipt/job"), state: "REJECTED", output_job: null, src: { file: "C", pointer: cp(S, "/receipt/receipt/job") } };

  const dc = (x) => c.get(cp(D, x));
  need(dc("/retrieval/status") === "OK" && dc("/retrieval/reached") === false, "hidden-rule retrieval is not OK / not reached");
  need(dc("/bind/status") === "NOT_REACHED" && dc("/authorization/status") === "NOT_RUN" && dc("/receipt/invoked") === false, "hidden-rule case ran further than recorded");
  need(dc("/consume/decision") === "REFUSED" && dc("/seed_origin") === "injected-fixture-seed", "hidden-rule case not refused or not the injected seed");
  F("hidden_bind", "NOT_REACHED", "NOT_REACHED", [c.ref(cp(D, "/bind/status"))]);
  F("hidden_receipt_invoked", false, "not invoked", [c.ref(cp(D, "/receipt/invoked"))]);
  F("hidden_decision", "REFUSED", "Refused", [c.ref(cp(D, "/consume/decision"))]);
  F("hidden_seed", "injected-fixture-seed", "injected-fixture-seed", [c.ref(cp(D, "/seed_origin"))]);

  const uc = (x) => c.get(cp(U, x));
  need(uc("/authorization/status") === "DENIED" && uc("/receipt/invoked") === false && uc("/consume/decision") === "REFUSED", "unreadable-dependency case not DENIED / not invoked / not refused");
  F("unread_denied", uc("/authorization/denied"), `${uc("/authorization/denied")} tables DENIED`, [c.ref(cp(U, "/authorization/denied")), c.ref(cp(U, "/authorization/status"))]);
  F("unread_receipt_invoked", false, "not invoked", [c.ref(cp(U, "/receipt/invoked"))]);
  F("unread_decision", "REFUSED", "Refused", [c.ref(cp(U, "/consume/decision"))]);

  // ---- stage 6: revoke
  const vc = (x) => c.get(cp(V, x));
  need(vc("/revocation/observed") === true && vc("/revocation/stable/stable") === true, "revocation not observed / not stable");
  need(vc("/fresh_request/catalog/status") === "CATALOG_ERROR" && vc("/fresh_request/downstream_ran") === false, "fresh request did not stop at Catalog");
  need(vc("/bypass/publication/status") === "ERROR", "retained-pin bypass publication is not ERROR");
  need(vc("/bypass/retrieval/status") === "DENIED" && vc("/bypass/retrieval/disclosed_anything") === false, "retained-pin bypass retrieval not DENIED or disclosed something");
  need(vc("/authorization/status") === "DENIED" && vc("/consume/decision") === "REFUSED", "post-revocation authorization/decision not DENIED/REFUSED");
  need(vc("/receipt_invocations_after_revocation") === 0, "receipt ran after revocation");
  need(/^not exercised/.test(vc("/cache")), "revocation cache note no longer says not exercised");
  const reconciled = cOps.filter((o) => o.final_event === "reconciled");
  need(reconciled.length === 2 && reconciled.every((o) => o.state === "ERROR" && o.observed === "DONE" && o.lines.some((l) => CJ.find((e) => e.line === l).rec.event === "unknown")), "expected two UNKNOWN → reconciled ERROR operations");
  need(reconciled.every((o) => o.at > vc("/revocation/requester/at")), "reconciled errors precede the revocation");
  F("revoked_stable", true, `${vc("/revocation/stable/consecutive")} consecutive checks`, [c.ref(cp(V, "/revocation/stable/stable")), c.ref(cp(V, "/revocation/stable/consecutive"))]);
  F("fresh_status", "CATALOG_ERROR", "CATALOG_ERROR", [c.ref(cp(V, "/fresh_request/catalog/status"))]);
  F("fresh_http", vc("/fresh_request/catalog/http_status"), `HTTP ${vc("/fresh_request/catalog/http_status")}`, [c.ref(cp(V, "/fresh_request/catalog/http_status"))]);
  F("fresh_downstream", false, "nothing downstream ran", [c.ref(cp(V, "/fresh_request/downstream_ran")), c.ref(cp(V, "/fresh_request/stopped_at"))]);
  F("bypass_publication", "ERROR", "ERROR", [c.ref(cp(V, "/bypass/publication/status")), ...reconciled.map((o) => ({ file: "CJ", line: o.line, event: o.final_event, seq: o.seq }))]);
  F("bypass_retrieval", "DENIED", "DENIED", [c.ref(cp(V, "/bypass/retrieval/status"))]);
  F("bypass_disclosed", false, "nothing disclosed", [c.ref(cp(V, "/bypass/retrieval/disclosed_anything"))]);
  F("revoked_authorization", "DENIED", "DENIED", [c.ref(cp(V, "/authorization/status"))]);
  F("revoked_decision", "REFUSED", "Refused", [c.ref(cp(V, "/consume/decision")), c.ref(`/decisions/${V}`)]);
  F("revoked_receipts", 0, "0", [c.ref(cp(V, "/receipt_invocations_after_revocation"))]);
  F("cache_replay", vc("/cache"), "not exercised", [c.ref(cp(V, "/cache"))]);
  F("fresh_refused", "CATALOG_ERROR", "Refused", [c.ref(cp(V, "/fresh_request/catalog/status")), c.ref(cp(V, "/fresh_request/downstream_ran"))]);
  F("bypass_refused", "ERROR/DENIED", "Refused", [c.ref(cp(V, "/bypass/publication/status")), c.ref(cp(V, "/bypass/retrieval/status"))]);
  F("revoked_outcome", "REFUSED", "Later release refused", [c.ref(cp(V, "/consume/decision")), c.ref(cp(V, "/receipt_invocations_after_revocation"))]);
  const revokedOps = reconciled.map((o) => ({ ...jobChip("CJ", o, `after revocation: ${o.role}`), observed: o.observed }));

  // ---- closing evidence (not a seventh stage)
  const cleanup = p.get("/publish/cleanup");
  need(cleanup.status === "COMPLETE" && cleanup.pending === 0 && cleanup.unresolved_jobs === 0 && cleanup.steps.length === 2 && cleanup.steps.every((s) => s.deleted === true && s.absent_verified === true), "cleanup not COMPLETE with verified absence");
  need(p.get("/publish/originals_recheck/status") === "UNCHANGED", "originals changed");
  need(c.get("/teardown/broker/status") === "VERIFIED" && c.get("/teardown/catalog/status") === "VERIFIED", "consumer teardown not VERIFIED");
  const complete = trace[traceAt("COMPLETE")];
  F("cleanup_status", "COMPLETE", "COMPLETE", [p.ref("/publish/cleanup/status"), jref("PJ", oneEvent(PJ, "PJ", "cleanup"))]);
  F("originals", "UNCHANGED", "UNCHANGED", [p.ref("/publish/originals_recheck/status"), jref("PJ", oneEvent(PJ, "PJ", "originals_recheck"))]);
  F("teardown", "VERIFIED", "VERIFIED", [c.ref("/teardown/broker/status"), c.ref("/teardown/catalog/status")]);
  F("publish_phase_complete_at", complete.at, utcTime(complete.at), [p.ref(`/state_trace/${traceAt("COMPLETE")}/at`)]);

  const roles = c.get("/identity/roles");
  need(c.get("/identity/status") === "BOUND" && c.get("/job_inventory/unresolved").length === 0, "consumer identity not BOUND or jobs unresolved");
  const inventory = {
    author: { jobs: pJobs.length, status: "BOUND", src: [p.ref("/publish/author_identity")] },
    consumer_roles: Object.fromEntries(Object.entries(roles).map(([k, v]) => [k, v.jobs])),
    consumer_roles_src: [c.ref("/identity/roles")],
    journal_by_state: byState, journal_src: [c.ref("/journal/summary/by_state"), { file: "CJ", lines: `1-${CJ[CJ.length - 1].line}` }],
    graph_and_store: c.get("/job_inventory/graph_and_store").length, receipt: c.get("/job_inventory/receipt").length, unresolved: 0,
    note: "Policy-admin jobs ran as the operator; not every consumer-side job ran as the requester, and ERROR/EMPTY states are recorded as such.",
  };

  const caseRows = CASES.map((name) => ({ case: name, decision: c.get(`/decisions/${name}`), acceptance: c.get(`/acceptance/${name}`), src: [c.ref(`/decisions/${name}`), c.ref(`/acceptance/${name}`)] }));

  const stages = STAGE_ORDER.map((id, i) => ({ id, anchor: `stage-${id}`, n: i + 1, editorial: EDITORIAL[id] }));
  stages[0].jobs = publishJobs;
  stages[1].operations = catOps;
  stages[2].catalog_reads = catalogReads;
  stages[3].jobs = retrievalJobs;
  stages[4].jobs = [receiptJob, subJob];
  stages[5].jobs = revokedOps;

  return {
    schema: SCHEMA,
    generated_by: "rfc/tools/build_e2e_visual_evidence.mjs",
    note: "Deterministic projection of committed run files. `facts` are recorded values with sources; `editorial` is page copy. Selecting a stage on the page replays nothing.",
    sources, facts, stages, cases: caseRows, inventory,
    residuals: [
      "relational SQL on the published tables, not BigQuery Graph / GQL",
      "the SDK example's own verifier with a requester-held key; no independent attester",
      "a fresh deployment of the same content-addressed publication, not a new knowledge revision",
      "simplified RFC §05: no sync_id staging, deployment_heads, *_current views or Catalog lag SLO",
      "access granted and removed by the harness; the hidden-rule case is an injected legacy seed on the _rls copy",
      "retrieval-cache replay not exercised",
      "n = 1 on synthetic data; no cost or latency benchmark",
    ],
  };
}

// ---------------------------------------------------------------- markup

function srcHtml(s) {
  const link = `<a href="${esc(href(INPUTS[s.file]))}">${esc(LABELS[s.file])}</a>`;
  if (s.pointer !== undefined) return `${link} <code>${esc(s.pointer)}</code>`;
  if (s.lines !== undefined) return `${link} lines ${esc(s.lines)}`;
  return `${link} line ${esc(s.line)} <code>${esc(s.event)}</code>${s.seq !== undefined ? ` seq ${esc(s.seq)}` : ""}`;
}
const jobHtml = (j) => `<li>${esc(j.label)} · <code>${esc(j.project)}</code> / <code>${esc(j.location)}</code> / <code>${esc(j.job_id)}</code> · ${esc(j.state)}${j.observed ? ` (server observed ${esc(j.observed)})` : ""}${j.output_job === null ? " · <code>output.job</code> null" : ""} — ${srcHtml(j.src)}</li>`;

export function renderWalkthrough(ev) {
  const f = (key) => { need(ev.facts[key], `markup references unknown fact ${key}`); return `<span class="obs" data-fact="${esc(key)}">${esc(ev.facts[key].display)}</span>`; };
  const facts = (keys) => `<details class="vw-src"><summary>Source details</summary><ul>${keys.map((k) => `<li><b>${esc(k)}</b> = <code>${esc(JSON.stringify(ev.facts[k].value))}</code> — ${ev.facts[k].src.map(srcHtml).join("; ")}</li>`).join("")}`;
  const tape = (s) => `<a class="seek" href="#tape" data-t="${esc(s.editorial.tape)}" aria-label="Watch this step in the original CLI recording at ${esc(fmtT(s.editorial.tape))}">▶ ${esc(fmtT(s.editorial.tape))}</a>`;
  const tagClass = { "BigQuery Knowledge Publish": "t-b", "Knowledge Catalog": "t-a", Requester: "t-c", Receipt: "t-c" };
  const S = Object.fromEntries(ev.stages.map((s) => [s.id, s]));
  const body = {
    publish: `<ol class="vw-checks">
            <li><b>Written</b> ${f("nodes")} nodes, ${f("edges")} edges, ${f("sections")} sections</li>
            <li><b>Read back</b> ${f("readback_checks")} checks true</li>
            <li><b>${f("ready_state")}</b> at ${f("ready_at")}</li>
            <li><b>Current version</b> ${f("head_from")} → ${f("publication_id")}, ${f("head_state")} ${f("head_at")}</li>
          </ol>`,
    catalog: `<ul class="vw-rec">
            <li>Entry written ${f("pin_at")}, pointing to ${f("publication_id")}; readback ${f("pin_readback")}.</li>
            <li>Catalog API operations, not BigQuery jobs: no job ID.</li>
          </ul>`,
    discover: `<ul class="vw-rec">
            <li>Before access: ${f("catalog_before")} (${f("catalog_before_http")}); after grant: ${f("catalog_after")}.</li>
            <li>Pin versus BigQuery’s publication and dataset: ${f("consumed_status")}, ${f("consumed_checks")} checks.</li>
          </ul>`,
    retrieve: `<ul class="vw-rec">
            <li>Publication ${f("publication_status")}, binding ${f("bind_status")}, payload ${f("payload_status")}.</li>
            <li>Access ${f("authorization_status")}: ${f("authorization_denied")} tables denied.</li>
            <li>Plain SQL (${f("retrieval_engine")}), not a graph query.</li>
          </ul>`,
    receipt: `<p class="vw-result"><span class="k">Recorded live result</span><b>${f("amount")}</b><span>receipt ${f("receipt_verdict")} · ${f("approved_decision")}</span></p>
          <ul class="vw-neg" aria-label="Recorded negative checks">
            <li><b>Swapped query</b> <span class="stop">${f("sub_decision")}</span> receipt ${f("sub_verdict")} (${f("sub_reason")}); a receipt job ran.</li>
            <li><b>Hidden rule</b> <span class="stop">${f("hidden_decision")}</span> separate injected legacy-seed test on the governance copy; receipt ${f("hidden_receipt_invoked")}.</li>
            <li><b>Unreadable dependencies</b> <span class="stop">${f("unread_decision")}</span> ${f("unread_denied")}; receipt ${f("unread_receipt_invoked")}.</li>
          </ul>`,
    revoke: `<ul class="vw-neg" aria-label="Recorded checks after revocation">
            <li><b>Fresh request</b> <span class="stop">${f("fresh_refused")}</span> at Catalog (${f("fresh_http")}); ${f("fresh_downstream")}.</li>
            <li><b>Retained pin</b> <span class="stop">${f("bypass_refused")}</span> publication ${f("bypass_publication")}, retrieval ${f("bypass_retrieval")}, ${f("bypass_disclosed")}.</li>
            <li><b>Stored receipt</b> <span class="stop">${f("revoked_decision")}</span> access ${f("revoked_authorization")}; ${f("revoked_receipts")} new receipt runs.</li>
          </ul>
          <p class="vw-foot">Denial held ${f("revoked_stable")}; cache replay ${f("cache_replay")}.</p>`,
  };
  const keysIn = (html) => [...new Set([...html.matchAll(/data-fact="([^"]+)"/g)].map((m) => m[1]))];
  const extra = {
    publish: `<li><b>jobs</b> (full references):<ul>${S.publish.jobs.map(jobHtml).join("")}</ul></li><li><b>author identity</b> ${f("author_jobs")} jobs ${f("author_identity")}; source pin ${f("source_pin")}</li>`,
    catalog: `<li><b>operations</b> (no BigQuery job):<ul>${S.catalog.operations.map((o) => `<li>${esc(o.role)} · <code>job_backed=false</code>, <code>job_id=null</code> · ${esc(o.state)} — ${srcHtml(o.src)}</li>`).join("")}</ul></li><li><b>entry</b> <code>${esc(ev.facts.pin_entry.display)}</code></li>`,
    discover: `<li><b>requester Catalog reads</b>:<ul>${S.discover.catalog_reads.map((r) => `<li>${esc(r.name)} at ${esc(utcTime(r.at))} · response hash <code>${esc(r.raw_sha256)}</code>; redacted retained copy <a href="${esc(href(r.retained_file))}">hash</a> <code>${esc(r.retained_sha256)}</code> — ${srcHtml(r.src)}</li>`).join("")}</ul></li><li>Access observed after ${f("catalog_wait_s")} of polling (a diagnostic interval, not a propagation bound); caller is requester ${f("caller_is_requester")}. Consumer records mask part of the entry name; ownership is corroborated by <code>entry_is_owned</code>.</li>`,
    retrieve: `<li><b>approved-case jobs</b>:<ul>${S.retrieve.jobs.map(jobHtml).join("")}</ul></li><li>Other store, declaration and payload jobs stay in the run inventory under Evidence; role names alone do not assign them to this case.</li>`,
    receipt: `<li><b>receipt jobs</b>:<ul>${S.receipt.jobs.map(jobHtml).join("")}</ul></li><li>Recorded line <code>${esc(ev.facts.answer_display.display)}</code>; receipt issued ${f("receipt_issued")}, execution ${f("execution_match")}. The receipt’s publication ID <code>${esc(ev.facts.sdk_publication_id.display)}</code> is the SDK’s label, not the BigQuery publication ID. Hidden-rule seed: ${f("hidden_seed")}.</li>`,
    revoke: `<li><b>post-revocation BigQuery calls</b> (UNKNOWN, then reconciled to ERROR: refusal evidence, not successful queries):<ul>${S.revoke.jobs.map(jobHtml).join("")}</ul></li>`,
  };
  const articles = ev.stages.map((s) => {
    const e = s.editorial;
    const keys = keysIn(body[s.id]);
    const src = facts(keys) + extra[s.id] + "</ul></details>";
    return `        <article class="vw-stage p-${e.plane}${e.stop ? " is-stop" : ""}" id="${s.anchor}" data-stage="${s.id}" tabindex="-1" aria-labelledby="${s.anchor}-h">
          <p class="vw-kicker">${e.tags.map((t) => `<span class="tag ${tagClass[t]}">${esc(t)}</span>`).join("")}</p>
          <h3 id="${s.anchor}-h">${esc(e.title)}</h3>
          <div class="vw-cols">
            <div class="vw-mean"><h4>What this means</h4><p>${esc(e.meaning)}</p></div>
            <div class="vw-obs"><h4>Recorded</h4>
          ${body[s.id]}
            </div>
          </div>
          <div class="vw-more">${src} ${tape(s)}</div>
        </article>`;
  }).join("\n");
  const rail = ev.stages.map((s) => `          <li><a href="#${s.anchor}" data-stage="${s.id}" class="p-${s.editorial.plane}"><span class="vw-n" aria-hidden="true">${s.n}</span><span><b>${esc(s.editorial.rail[0])}</b> ${esc(s.editorial.rail[1])}</span></a></li>`).join("\n");
  const obj = (id, cls, title, sub) => `<li class="vw-obj ${cls}" data-obj="${id}"><b>${esc(title)}</b><span>${sub}</span></li>`;
  const link = (id) => `<li class="vw-link" data-link="${id}" aria-hidden="true"></li>`;
  const diagram = [obj("okf", "p-a", "Open Knowledge Format files", "definition, rules, calculation"), link("okf-publication"),
    obj("publication", "p-b", "BigQuery publication", "fixed, READY, current"), link("publication-catalog"),
    obj("catalog", "p-a", "Catalog entry", "points to that version"), link("catalog-requester"),
    obj("requester", "p-c", "Requester", "restricted account"), link("requester-receipt"),
    obj("receipt", "p-c", "Receipt check", "before any release")].join("");
  const outcomes = `<ul class="vw-outcomes" aria-label="Recorded outcomes">
      <li class="oc-rel"><span class="k">Recorded approved case</span><b>${f("amount")}</b><span>released, receipt verified</span></li>
      <li class="oc-ref"><span class="k">Swapped query</span><b class="stop">${f("sub_decision")}</b></li>
      <li class="oc-ref"><span class="k">Hidden rule, injected test</span><b class="stop">${f("hidden_decision")}</b></li>
      <li class="oc-ref"><span class="k">Unreadable dependencies</span><b class="stop">${f("unread_decision")}</b></li>
      <li class="oc-rev"><span class="k">Access removed</span><b class="stop">${f("revoked_outcome")}</b></li>
    </ul>`;
  const inner = `
    <p class="vw-unavailable" role="status" hidden>Interactive details unavailable. The six recorded steps below still come from the committed files of the ${esc(String(ev.facts.run_started.value).slice(0, 10))} run; <a href="#evidence">open the raw records</a>.</p>
    <div class="vw-grid">
      <nav class="vw-rail" aria-label="Six steps">
        <ol>
${rail}
        </ol>
      </nav>
      <div class="vw-work">
        <figure class="vw-diagram">
          <ol class="vw-flow" aria-label="Objects in the recorded path">${diagram}</ol>
          <figcaption class="vw-legend"><span class="lg p-a">OKF + Knowledge Catalog: authoring, discovery</span><span class="lg p-b">BigQuery Knowledge Publish: serving authority</span><span class="lg p-c">Requester and receipt</span></figcaption>
        </figure>
        <p class="vw-live" aria-live="polite"></p>
${articles}
        <p class="vw-pager" hidden><button type="button" data-dir="-1">← Previous</button><button type="button" data-dir="1">Next →</button></p>
      </div>
    </div>
    ${outcomes}
`;
  const digest = sha256(inner);
  return { digest, html: `<div class="vw" id="walkthrough" data-evidence="visual-evidence.json" data-markup-sha256="${digest}">${inner}  </div>` };
}

// Recording positions rounded to the nearest second, matching the Evidence chapter list.
function fmtT(t) { const s = Math.round(t); return `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`; }

export function renderRecord(ev) {
  const f = (key) => `<code data-fact="${esc(key)}">${esc(ev.facts[key].display)}</code>`;
  const S = Object.fromEntries(ev.stages.map((s) => [s.id, s]));
  const inv = ev.inventory;
  return `<div class="ev-record" data-generated="rfc/tools/build_e2e_visual_evidence.mjs">
        <h3>Run</h3>
        <dl class="kv">
          <dt>verdict</dt><dd>${f("run_verdict")} · publish run ${f("run_publish_id")} · consume run ${f("run_consume_id")}</dd>
          <dt>window</dt><dd>${f("run_started")} → ${f("run_finished")}</dd>
          <dt>project</dt><dd>${f("run_project")} · mode ${f("run_mode")}</dd>
          <dt>data</dt><dd>synthetic Acme bundle, source pin ${f("source_pin")}; no customer data</dd>
        </dl>
        <h3>Source files</h3>
        <ul class="files">${Object.entries(ev.sources).map(([k, s]) => `<li><a href="${esc(href(s.path))}">${esc(LABELS[k])}</a> · ${esc(s.bytes)} bytes · sha256 <code>${esc(s.sha256)}</code></li>`).join("")}</ul>
        <h3>BigQuery Knowledge Publish (serving authority)</h3>
        <dl class="kv">
          <dt>publication</dt><dd>${f("publication_id")} ${f("ready_state")} at ${f("ready_at")} on full-row readback (${f("readback_checks")}): ${f("nodes")} nodes, ${f("edges")} edges, ${f("sections")} sections</dd>
          <dt>head switch</dt><dd><code>active_publication</code> ${f("head_from")} → ${f("publication_id")} ${f("head_state")} at ${f("head_at")}</dd>
          <dt>dataset</dt><dd>${f("dataset")}, run-owned</dd>
          <dt>jobs</dt><dd><ul>${S.publish.jobs.map(jobHtml).join("")}</ul>${f("author_jobs")} author jobs, identity ${f("author_identity")}; all 19 in the report.</dd>
        </dl>
        <h3>Knowledge Catalog (discovery)</h3>
        <dl class="kv">
          <dt>entry</dt><dd>${f("pin_entry")}: written at ${f("pin_at")}, after the head switch; readback ${f("pin_readback")}</dd>
          <dt>operations</dt><dd><ul>${S.catalog.operations.map((o) => `<li>${esc(o.role)} · no BigQuery job (<code>job_id=null</code>) · ${esc(o.state)} — ${srcHtml(o.src)}</li>`).join("")}</ul></dd>
          <dt>consumed</dt><dd>${f("consumed_status")} (${f("consumed_checks")} checks)</dd>
        </dl>
        <h3>Consumer cases</h3>
        <div class="table-wrap ev-table" role="region" aria-label="Consumer cases" tabindex="0">
          <table class="cases">
            <thead><tr><th scope="col">Case</th><th scope="col">Decision</th><th scope="col">Acceptance</th></tr></thead>
            <tbody>
${ev.cases.map((r) => `              <tr><td><code>${esc(r.case)}</code></td><td>${esc(r.decision)}</td><td>${esc(r.acceptance)}</td></tr>`).join("\n")}
            </tbody>
          </table>
        </div>
        <dl class="kv">
          <dt>receipt jobs</dt><dd><ul>${S.receipt.jobs.map(jobHtml).join("")}</ul></dd>
          <dt>after revocation</dt><dd><ul>${S.revoke.jobs.map(jobHtml).join("")}</ul></dd>
          <dt>job inventory</dt><dd>author ${esc(inv.author.jobs)} (${esc(inv.author.status)}); consumer roles ${Object.entries(inv.consumer_roles).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(", ")}; consumer journal final states ${Object.entries(inv.journal_by_state).map(([k, v]) => `${esc(k)} ${esc(v)}`).join(", ")}; unresolved ${esc(inv.unresolved)}. ${esc(inv.note)}</dd>
          <dt>cleanup</dt><dd>run-owned entry and dataset deleted with absence read back: ${f("cleanup_status")}; originals ${f("originals")}; consumer teardown ${f("teardown")}. The deleted resources no longer serve queries. The trace’s <code>COMPLETE</code> at ${f("publish_phase_complete_at")} ends the publish phase, not the end-to-end run.</dd>
        </dl>
      </div>`;
}

export function splice(html, name, content) {
  const start = `<!-- e2e-visual:${name}:start -->`, end = `<!-- e2e-visual:${name}:end -->`;
  const a = html.indexOf(start), b = html.indexOf(end);
  need(a >= 0 && b > a && html.indexOf(start, a + 1) < 0, `index.html: missing or repeated ${start} … ${end}`);
  return html.slice(0, a + start.length) + "\n" + content + "\n" + html.slice(b);
}

export function build(root = REPO) {
  const ev = project(loadInputs(root));
  const walk = renderWalkthrough(ev);
  const json = JSON.stringify({ ...ev, markup_sha256: walk.digest }, null, 2) + "\n";
  const htmlPath = path.join(root, OUT_HTML);
  let html = fs.readFileSync(htmlPath, "utf8");
  html = splice(html, "walkthrough", walk.html);
  html = splice(html, "record", renderRecord(ev));
  return { json, html };
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const args = process.argv.slice(2);
  const i = args.indexOf("--root");
  const root = i >= 0 ? path.resolve(args[i + 1]) : REPO;
  const check = args.includes("--check");
  let out;
  try { out = build(root); } catch (e) {
    if (e instanceof EvidenceError) { console.error(`evidence invalid: ${e.message}`); process.exit(2); }
    throw e;
  }
  const targets = [[OUT_JSON, out.json], [OUT_HTML, out.html]];
  let drift = 0;
  for (const [rel, next] of targets) {
    const abs = path.join(root, rel);
    const cur = fs.existsSync(abs) ? fs.readFileSync(abs, "utf8") : null;
    if (cur === next) continue;
    drift++;
    if (check) console.log(`STALE ${rel}`);
    else { fs.writeFileSync(abs, next); console.log(`wrote ${rel}`); }
  }
  if (check) { console.log(drift ? `${drift} file(s) stale; run node rfc/tools/build_e2e_visual_evidence.mjs` : "visual evidence in sync"); process.exit(drift ? 1 : 0); }
  else console.log(drift ? `${drift} file(s) updated` : "nothing to do");
}
