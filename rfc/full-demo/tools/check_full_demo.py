#!/usr/bin/env python3
"""Check /rfc/full-demo/ against its checked-in live captures (stdlib only, read-only).

Asserts, per plan.md Phase C:
  - six beats present in index.html and app.js deep-link regex
  - session ids and publication prefixes on the page match the checked-in snapshots
  - ATTESTED appears only inside labelled, non-normative or quoted shapes
  - never-emit list absent from every tool payload (both the live scan result and a key walk)
  - okf-derived-germany is labelled prior wherever it is named
  - every RFC-text-only capability row carries that label; every row has a beat or the label
  - both system prompts are present in the captures and rendered on beat 3
  - attribution bands sum to 14 / 13 with no duplicate row
  - no BQ_COMMITTED / CATALOG_STAMPED / no-op / FAIL_STALE claim without a "not run" qualifier
  - shipped-type captures agree: entries.get shows the okf aspect, lookupContext omits it
  - rfc/index.html links to ./full-demo/
  - node --check on app.js

Usage: python3 rfc/full-demo/tools/check_full_demo.py   (exit 0 on pass)
"""
import html
import json
import posixpath
import re
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
LIVE = DEMO / "live"
RFC = DEMO.parent

S_OBS = "f21ee192-d989-4c38-894f-66b6b82eaf18"
S_CON = "04fa3d56-f2f1-413e-8c2b-ec116835af84"
S_OBS2 = "1e6dfed7-27ce-4c4d-b2e7-c45de7c241d1"
PUBS = {
    "a25e1c0c": "sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5",
    "674153c5": "sha256:674153c572f6be57618a8d769a1a2b21a3e20d98406b3d1e58dd00027bc45905",
    "53bd1651": "sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77",
}
NEVER_EMIT = ["concept_version_id", "bundle_path", "source_path", "principal",
              "query_text", "sql", "parameter_values", "destination_table"]

failures = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def load(name):
    return json.loads((LIVE / name).read_text("utf-8"))


def parse(v):
    if isinstance(v, str):
        try:
            return json.loads(v)
        except ValueError:
            return v
    return v


def keys_deep(obj, out=None):
    out = set() if out is None else out
    if isinstance(obj, dict):
        for k, v in obj.items():
            out.add(k)
            keys_deep(v, out)
    elif isinstance(obj, list):
        for v in obj:
            keys_deep(v, out)
    return out


index = (DEMO / "index.html").read_text("utf-8")
app = (DEMO / "app.js").read_text("utf-8")
app_lines = app.split("\n")

# ---- beats -------------------------------------------------------------------------
beats = sorted(set(int(m) for m in re.findall(r'data-beat="([1-6])"', index)))
check(beats == [1, 2, 3, 4, 5, 6], "index.html has six step buttons data-beat=1..6")
check("([1-6])" in app, "app.js deep-link regex accepts #beat=1..6")
check("var TOTAL = 6;" in app, "app.js TOTAL = 6")
for fn in ["renderAsk", "renderObserve", "renderCatalog", "renderSync", "renderServe", "renderAttribution"]:
    check(("function %s(" % fn) in app, "app.js defines %s" % fn)

# ---- sessions ----------------------------------------------------------------------
obs = load("session_f21ee192.json")
con = load("session_04fa3d56.json")
obs2 = load("session_1e6dfed7.json")
check(len(obs) == 180 and all(r["session_id"] == S_OBS for r in obs), "session_f21ee192.json: 180 rows, all session_id %s" % S_OBS)
check(len(con) == 14 and all(r["session_id"] == S_CON for r in con), "session_04fa3d56.json: 14 rows, all session_id %s" % S_CON)
check(len(obs2) == 15 and all(r["session_id"] == S_OBS2 for r in obs2), "session_1e6dfed7.json: 15 rows, all session_id %s" % S_OBS2)
check(sum(1 for r in obs if r["event_type"] == "USER_MESSAGE_RECEIVED") == 12, "12 USER_MESSAGE_RECEIVED rows in the observe session")
check(sum(1 for r in obs if r["event_type"] == "TOOL_COMPLETED") == 24, "24 TOOL_COMPLETED rows in the observe session")
for sid in (S_OBS, S_CON, S_OBS2):
    check(sid in app, "app.js names session %s" % sid)
summary = load("sessions_summary.json")
summary_ids = {r["session_id"] for r in summary}
check(sum(int(r["rows_in_table"]) for r in summary) == 212 and len(summary) == 4, "sessions_summary.json: 4 sessions, 212 rows in the table (live aggregate)")
by_sid = {r["session_id"]: int(r["rows_in_table"]) for r in summary}
check(by_sid.get(S_OBS) == len(obs) and by_sid.get(S_CON) == len(con) and by_sid.get(S_OBS2) == len(obs2), "the three pulled snapshots match the live per-session counts (180 / 14 / 15 = 209 rows on the page)")
fourth = [r for r in summary if r["session_id"] not in (S_OBS, S_CON, S_OBS2)]
check(len(fourth) == 1 and int(fourth[0]["tool_completed"]) == 0 and not (LIVE / ("session_" + fourth[0]["session_id"][:8] + ".json")).exists(), "exactly one session (a63c3e86…, 0 tool calls) is counted but not pulled, and no snapshot for it is claimed")
page_sessions = set(re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", app + index))
check(page_sessions <= summary_ids, "no session id on the page outside the live per-session summary: %s" % sorted(page_sessions - summary_ids))
check("three of those sessions (209 rows" in index and "counted but not pulled" in index, "index.html states three pulled sessions / 209 rows and names the fourth as counted, not pulled")
check("all four sessions" not in (DEMO / "stories.json").read_text("utf-8") and "all four sessions" not in index and "all four sessions" not in app, "no 'all four sessions' coverage claim remains")

# ---- the twelve answers: semantic 12/12 vs one verbatim sentence -------------------------------
VERBATIM = "No. The number is unproven."
inv = {}
for r in obs:
    inv.setdefault(r["trace_id"], []).append(r)
finals = []
for evs in inv.values():
    texts = [parse(e["content"]).get("response", "") for e in evs if e["event_type"] == "LLM_RESPONSE"]
    texts = [t for t in texts if isinstance(t, str) and not t.startswith("call: ")]
    finals.append(texts[-1] if texts else "")
semantic = sum(1 for t in finals if "unproven" in t.lower())
verbatim = sum(1 for t in finals if VERBATIM in t)
check(len(finals) == 12 and semantic == 12, "12 of 12 final answers contain 'unproven' (semantic count, got %d)" % semantic)
check(verbatim == 1, "exactly 1 of 12 final answers contains the verbatim sentence (got %d); the page must not claim more" % verbatim)
check('var VERBATIM = "%s"' % VERBATIM in app and "D.verbatim" in app and "D.unproven" in app, "app.js computes and renders both counts from the rows")
stories_md = (DEMO / "CUSTOMER_STORIES.md").read_text("utf-8")
for name, text in (("index.html", index), ("stories.json", (DEMO / "stories.json").read_text("utf-8")), ("app.js", app), ("CUSTOMER_STORIES.md", stories_md), ("README.md", (DEMO / "README.md").read_text("utf-8"))):
    check("twelve times" not in text and not re.search(r"unproven\.[”\"*]*\s*\(?12 of 12\)?", text), "%s does not claim the verbatim sentence was said twelve times / 12 of 12" % name)
stories_flat = re.sub(r"\s+", " ", stories_md)
check("12 of 12 final answers contain" in stories_flat and "appears exactly once" in stories_flat, "CUSTOMER_STORIES.md states the semantic 12/12 and the single verbatim occurrence separately")
check("12 of 12 final responses contain “unproven”" in (DEMO / "stories.json").read_text("utf-8"), "stories.json states the semantic count separately from the one verbatim example")
receipts = [parse(r["content"])["result"] for r in obs if r["event_type"] == "TOOL_COMPLETED" and parse(r["content"]).get("tool") == "okf_run_attested_computation"]
check(len(receipts) == 12 and all(json.dumps(x, sort_keys=True) == json.dumps(receipts[0], sort_keys=True) for x in receipts), "the 12 attested-computation receipts are identical (UNVERIFIABLE, no-execution)")

# ---- system prompts on beat 3 ---------------------------------------------------------
prompts_con = {parse(r["content"]).get("system_prompt") for r in con if r["event_type"] == "LLM_REQUEST"}
prompts_obs = {parse(r["content"]).get("system_prompt") for r in obs if r["event_type"] == "LLM_REQUEST"}
check(len(prompts_con) == 1 and any("sanctioned computation" in p for p in prompts_con), "consume session has one system prompt and it leans on 'sanctioned computation'")
check(len(prompts_obs) == 1 and any("say plainly that the number is unproven" in p for p in prompts_obs), "observe session has one system prompt and it requires 'unproven' unless ATTESTED")
cat_fn = app[app.index("function renderCatalog("):app.index("function renderSync(")]
check("C.systemPrompt" in cat_fn and "F.systemPrompt" in cat_fn, "renderCatalog renders both system prompts (C.systemPrompt and F.systemPrompt)")
answer = [parse(r["content"]) for r in con if r["event_type"] == "AGENT_RESPONSE"]
check(bool(answer) and "You can trust the number because it is verified" in answer[0].get("response", ""), "the over-claim sentence is in the consume AGENT_RESPONSE row")
check("You can trust the number because it is verified" in cat_fn, "renderCatalog highlights the over-claim sentence")

# ---- never-emit ----------------------------------------------------------------------
scan = load("never_emit_scan.json")
check(len(scan) == len(NEVER_EMIT) and all(int(r["hits"]) == 0 for r in scan), "never_emit_scan.json: 0 hits for all %d keys" % len(NEVER_EMIT))
check(all(int(r["tool_rows_scanned"]) == 27 and int(r["rows_with_context_ref"]) == 27 for r in scan), "scan covered 27 TOOL_COMPLETED rows, 27 carry context_ref")
tool_keys = set()
for rows in (obs, con, obs2):
    for r in rows:
        if r["event_type"] == "TOOL_COMPLETED":
            keys_deep(parse(r["content"]), tool_keys)
check(not (tool_keys & set(NEVER_EMIT)), "key walk over all checked-in TOOL_COMPLETED payloads: never-emit keys absent")

# ---- publications ---------------------------------------------------------------------
attr = load("beat6_attribution.json")
evid = load("beat6_demo_evidence.json")
pubs = load("beat5_serve_stmt4.json")
seen_pubs = {r.get("publication_id") for r in attr + evid + pubs if r.get("publication_id")}
check(seen_pubs == set(PUBS.values()), "the three publications in the captures are exactly a25e1c0c…, 674153c5…, 53bd1651…")
pinned = json.loads((RFC / "demo" / "live" / "observe" / "live_identities.json").read_text("utf-8"))
allowed_ids = set(PUBS.values()) | {pinned["observation_id"], pinned["snapshot_id"], pinned["publication_id"]}
check(pinned["publication_id"] == PUBS["53bd1651"], "the adapter's pinned publication on /rfc/demo/ is 53bd1651…")
page_ids = set(re.findall(r"sha256:[0-9a-f]{64}", app + index))
check(page_ids <= allowed_ids, "no sha256 identity on the page outside the three publications and the pinned observation/snapshot: %s" % sorted(page_ids - allowed_ids))
page_prefixes = set(re.findall(r"sha256:([0-9a-f]{8})", app + index))
check(page_prefixes <= {i[7:15] for i in allowed_ids}, "no sha256 prefix on the page outside the captured identities: %s" % sorted(page_prefixes - {i[7:15] for i in allowed_ids}))
push_t = (LIVE / "catalog_push_transcript.txt").read_text("utf-8")
check(PUBS["53bd1651"] in push_t and "MATCH" in push_t, "push transcript records the adapter reproducing 53bd1651… (MATCH) before the push")

# ---- attribution bands ----------------------------------------------------------------------
sums = {}
keyset = set()
dup = False
for r in attr:
    sums[r["band"]] = sums.get(r["band"], 0) + int(r["n"])
    k = (r["session_id"], r["tool"], r["context_ref"], r["publication_id"])
    dup = dup or k in keyset
    keyset.add(k)
check(sums.get("attributed") == 14, "band attributed sums to 14 (got %s)" % sums.get("attributed"))
check(sums.get("receipt_only") == 13, "band receipt_only sums to 13 (got %s)" % sums.get("receipt_only"))
check(not dup, "no (session, tool, context_ref, publication) row appears twice")
check(all(r["publication_source"] == "seeded_pre_phase_a" for r in attr if r["band"] == "attributed"), "every attributed row resolves to a seeded_pre_phase_a publication (no sync has committed)")
check(len(evid) == 2 and {r["source"] for r in evid} == {"adapter_tape_pr474_476d37dc", "legacy_catalog_description"}, "demo_evidence has the adapter-tape and legacy-Catalog rows")
v0 = load("sessions_by_context_ref.json")
check(len(v0) == 5 and sum(int(r["n"]) for r in v0) == 27, "v0 query: 5 groups, 27 events")

# ---- serve probes ---------------------------------------------------------------------------
heads = load("beat5_serve_stmt1.json")
hist = load("beat5_serve_stmt2.json")
resol = load("beat5_serve_stmt3.json")
check(heads == [] and hist == [], "deployment_heads and deployment_heads_history are empty (no sync has run) and shown empty")
by_ref = {r["context_ref"]: r["resolution"] for r in resol}
check(by_ref.get("okf:env-junk#deadbeef") == "FAIL_CLOSED", "junk handle resolves FAIL_CLOSED")
check(by_ref.get("okf:env-observe#674153c572f6") == "AMBIGUOUS_LEGACY", "double-bound legacy handle resolves AMBIGUOUS_LEGACY")
check(by_ref.get("okf:env-demo#a25e1c0ccbca") == "NO_HEAD", "bound handle resolves NO_HEAD (no head yet)")
check("OK" not in by_ref.values() and "FAIL_STALE" not in by_ref.values(), "no OK / FAIL_STALE result is claimed while no head exists")
check(all(r["source"] == "seeded_pre_phase_a" and r["committed_at"] is None for r in pubs), "all publications rows are seeded_pre_phase_a with NULL committed_at")

# ---- honesty: words that need a qualifier -------------------------------------------------------
ATTESTED_OK = ["non-normative", "not ATTESTED", "Nothing is ATTESTED", "nothing attested", "never as a claim", "verdict ∈", "is not ATTESTED",
               "ATTESTED requirement", "achieve an `ATTESTED`", "if the verdict is not ATTESTED", "unproven unless ATTESTED"]
for i, ln in enumerate(app_lines + index.split("\n"), 1):
    if re.search(r"(?<![A-Z])ATTESTED(?![A-Z])", ln) and "UNVERIFIABLE" not in ln.replace("ATTESTED", ""):
        pass
bad_attested = [ln.strip()[:120] for ln in app_lines + index.split("\n")
                if re.search(r"(?<![A-Za-z_])ATTESTED(?![A-Za-z_])", ln) and not any(ok in ln for ok in ATTESTED_OK)]
check(not bad_attested, "every ATTESTED on the page sits inside a labelled non-normative / negated / quoted shape: %s" % bad_attested[:3])
for word in ("BQ_COMMITTED", "CATALOG_STAMPED"):
    lines = [ln for ln in app_lines + index.split("\n") if word in ln]
    check(lines and all(re.search(r"would print|neither happened|none happened|not run|no sync|has not run|shows no|CATALOG_PENDING|would|because none", ln) for ln in lines),
          "every %s mention is qualified as not having happened (%d lines)" % (word, len(lines)))
stale_lines = [ln for ln in app_lines + index.split("\n") if "FAIL_STALE" in ln]
check(stale_lines and all(re.search(r"RFC text only|needs a head|only once a head|no head|returns FAIL_STALE\.|not claimed|while no head|no OK / FAIL_STALE", ln) for ln in stale_lines),
      "every FAIL_STALE mention says it needs a head / is RFC text only (%d lines)" % len(stale_lines))
legacy_lines = [ln for ln in app_lines + index.split("\n") if "okf-derived-germany" in ln]
check(legacy_lines and all("prior" in ln.lower() for ln in legacy_lines), "okf-derived-germany is labelled prior on every line that names it (%d lines)" % len(legacy_lines))
check("Dataplex built-in" not in app or "not" in app, "no claim of a Dataplex built-in")
check(not re.search(r"sync --from-catalog[^.]*\b(is|now) (v1|available|shipped)", app), "no claim that sync --from-catalog exists")

# ---- rendered honesty labels on JSON-backed rows -----------------------------------------------
m = re.search(r"var EVID_LABELS = \{(.*?)\};", app, re.S)
evid_labels = dict(re.findall(r"(\w+): \[\"(\w+)\"", m.group(1))) if m else {}
check(set(evid_labels) == {r["source"] for r in evid}, "every demo_evidence.source rendered on beat 6 has an honesty label in EVID_LABELS: %s" % sorted(evid_labels))
check(evid_labels.get("legacy_catalog_description") == "prior" and evid_labels.get("adapter_tape_pr474_476d37dc") == "recorded", "the okf-derived-germany evidence row renders as prior, the adapter-tape row as recorded")
attr_fn = app[app.index("function renderAttribution("):app.index("function renderMatrix(")]
check('render: evidLabel' in attr_fn, "beat 6 evidence table renders the label column")
serve_fn = app[app.index("function renderServe("):app.index("function renderAttribution(")]
receipt_pane = [ln for ln in serve_fn.split("\n") if "The receipt · okf_run_attested_computation" in ln]
check(receipt_pane and 'src("live", "live trace' in receipt_pane[0] and 'src("stub", "stubbed attester' in receipt_pane[0], "beat 5 receipt pane is labelled live trace + stubbed attester")
sync_fn = app[app.index("function renderSync("):app.index("function iamRow(")]
live_iam = [ln for ln in sync_fn.split("\n") if ln.strip().startswith("iamRow(") and '"live"' in ln]
check(live_iam and all("operator" in ln and not re.search(r"time-boxed|Token Creator|okf-setup\b|okf-sync-writer|okf-runtime-reader", ln.split('"live"')[0]) for ln in live_iam), "every IAM row labelled live describes only what the operator ran (no SA grants, no time-boxed roles)")
for fname, must_have, must_not in (
    ("sql/setup_runtime_tables.sql", "Phase A requirement (NOT yet met)", "so the DDL is demonstrably run as okf-setup.\n--\n-- Run once"),
    ("sql/attribution_two_key.sql", "all ran as the operator raincoatrun@gmail.com", "The tape shows user_email = okf-runtime-reader"),
):
    txt = (DEMO / fname).read_text("utf-8")
    check(must_have in txt and must_not not in txt, "%s describes the SA identity as a future Phase A requirement" % fname)
check("Seeded by okf-setup in" not in (DEMO / "sql/attribution_two_key.sql").read_text("utf-8"), "attribution_two_key.sql does not say okf-setup seeded the table")

# ---- matrix ---------------------------------------------------------------------------------
matrix = json.loads((DEMO / "matrix.json").read_text("utf-8"))
rows = matrix["rows"]
check([r["n"] for r in rows] == list(range(1, 10)), "matrix.json has the nine capability rows of spec.md §2")
for r in rows:
    has_beat = bool(r.get("shown"))
    check(has_beat or r.get("rfc_text_only"), "matrix row %d is shown on a beat or labelled RFC text only" % r["n"])
    if re.search(r"Not implemented|RFC|future", r["bq"] + " " + r["kc"], re.I) and r["n"] in (6,):
        check(bool(r.get("rfc_text_only")), "matrix row %d (BigQuery side unimplemented) carries rfc_text_only" % r["n"])
    for b in r.get("shown", []):
        check(1 <= b <= 6, "matrix row %d beat %s in range" % (r["n"], b))
check('class="rfc-only"' in app and "rfc_text_only" in app, "renderMatrix renders the RFC text only label from rfc_text_only")
check(all(r.get("rfc_text_only") for r in rows if r["n"] in (1, 2, 5, 6, 7, 8, 9)), "rows 1, 2, 5, 6, 7, 8, 9 carry an RFC-text-only remainder (sync / attester not built)")

# ---- stories ---------------------------------------------------------------------------------
stories = json.loads((DEMO / "stories.json").read_text("utf-8"))["stories"]
check(len(stories) == 5, "five customer stories")
trace_ids = {r["trace_id"] for r in obs + con + obs2}
for s in stories:
    text = s["session"]
    uuids = re.findall(r"[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", text)
    check(all(u in (S_OBS, S_CON, S_OBS2) or ("e-" + u) in trace_ids for u in uuids), "story %d cites only real session or invocation ids: %s" % (s["n"], uuids))
    rest = re.sub(r"e-[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}|[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}", "", text)
    sids = re.findall(r"\b[0-9a-f]{8}\b", rest)
    check(all(any(sid.startswith(x) for sid in summary_ids) for x in sids), "story %d cites only real session prefixes (live per-session summary): %s" % (s["n"], sids))
    check(all(p in PUBS for p in re.findall(r"[0-9a-f]{8}", s["publication_prefix"])), "story %d cites only captured publication prefixes" % s["n"])
    check(all(1 <= b <= 6 for b in s["beats"]), "story %d beats in range" % s["n"])
check(any("RFC text only" in s["status"] for s in stories if s["n"] == 5), "story 5 BigQuery side is RFC text only")

# ---- catalog captures ----------------------------------------------------------------------------
legacy = load("catalog_entry_okf-derived-germany.json")
check("aspects" not in legacy and legacy["entryType"].endswith("/entryTypes/okf-concept"), "legacy entry has no aspects and type okf-concept")
metric = load("catalog_shipped_entry_metric_viewALL.json")
okf_aspect = [v for k, v in metric.get("aspects", {}).items() if k.endswith(".okf")]
check(bool(okf_aspect) and okf_aspect[0]["data"].get("okf_type") == "Metric" and metric["entryType"].endswith("/entryTypes/okf-bundle"),
      "pushed metric entry is okf-bundle and carries the okf aspect with okf_type Metric")
lc_metric = load("lookup_context_shipped_metric.json").get("context", "")
check(lc_metric and "okf_type" not in lc_metric and "\nsources" not in lc_metric and "overview:" in lc_metric,
      "lookupContext on the same entry returns overview but no okf fields")
lc_comp = load("lookup_context_shipped_computation.json").get("context", "")
check(lc_comp and not re.search(r"\n\s*(runtime|parameters|executor|attester|verdict):", lc_comp), "lookupContext on the computation entry omits runtime/parameters/executor/attester and has no verdict")
lc11 = load("lookup_context_11_resources.json")
check(lc11.get("error", {}).get("code") == 400 and "ten resources" in lc11["error"]["message"].lower(), "eleven resources → 400 'Only ten resources'")
check(load("lookup_context_missing_entry.json") == {}, "missing entry → {}")
aspect_type = load("catalog_aspect_type_okf.json")
fields = [f["name"] for f in aspect_type["metadataTemplate"]["recordFields"]]
check(len(fields) == 13 and "verdict" not in fields, "okf AspectType has 13 fields and none is a verdict")
entries = load("catalog_entries_list_after_push.json")
check(sum(1 for e in entries if e["entryType"].endswith("/okf-bundle")) == 8, "eight okf-bundle entries after the push")
search_dep = load("search_entries_okf_status_deprecated.json")
check(any(r["dataplexEntry"]["entrySource"]["displayName"] == "Customer revenue (legacy)" for r in search_dep.get("results", [])), "searchEntries status=deprecated finds Customer revenue (legacy)")

# ---- jobs / identity -----------------------------------------------------------------------------
jobs = load("bq_jobs_identity.json")
check(jobs and all(j["user_email"] == jobs[0]["user_email"] for j in jobs), "every capture job ran as one identity (%s)" % (jobs[0]["user_email"] if jobs else "none"))
jobids = {p.read_text().strip() for p in LIVE.glob("*.jobid")}
inventory = {j["job_id"]: j for j in jobs}
check(jobids <= set(inventory), "every *.jobid is in bq_jobs_identity.json (no fallback source): missing %s" % sorted(jobids - set(inventory)))
check(not list(LIVE.glob("bq_job_*.json")), "no bq show -j identity-fallback snapshots remain; the inventory file is the only identity source (provenance_*.json binds query text only)")
# the per-session summary job is bound end to end: job id ↔ inventory row (DONE, SELECT, operator) ↔ executed
# query text (bq show -j, kept in provenance_sessions_summary.json) ↔ committed SQL file ↔ result file ↔ app consumer.
# The provenance file is NOT an identity source: user_email comes only from the inventory and is cross-checked.
import hashlib
summary_job = (LIVE / "sessions_summary.jobid").read_text().strip()
srow = inventory.get(summary_job)
check(bool(srow) and srow["state"] == "DONE" and srow["statement_type"] == "SELECT" and srow["user_email"] == jobs[0]["user_email"],
      "inventory row for %s is DONE + SELECT + operator" % summary_job)
prov = load("provenance_sessions_summary.json")
check(prov["job_id"] == summary_job and prov["state"] == "DONE" and prov["statement_type"] == "SELECT", "provenance artifact names the same job id, DONE, SELECT")
check(prov["user_email_as_shown_by_bq_show"] == (srow or {}).get("user_email"), "provenance artifact's user_email agrees with the inventory row (cross-check, not a fallback)")
# True bytes, no universal-newline rewrite: read_bytes() vs executed_query.encode("utf-8"). A CRLF rewrite of the file
# changes its real SHA-256 and must fail here even though read_text() would have hidden it.
sql_bytes = (DEMO / "sql/sessions_summary.sql").read_bytes()
sql_text = sql_bytes.decode("utf-8")
check(b"\r" not in sql_bytes, "sql/sessions_summary.sql has LF line endings only (no CR bytes)")
check(prov["executed_query"].encode("utf-8") == sql_bytes, "executed query bytes are identical to the sql/sessions_summary.sql file bytes (no normalization, no newline rewrite)")
raw_sql_hash = hashlib.sha256(sql_bytes).hexdigest()
check(hashlib.sha256(prov["executed_query"].encode("utf-8")).hexdigest() == prov["executed_query_sha256_raw"] == prov["sql_file_sha256_raw"] == raw_sql_hash,
      "raw SHA-256 of the executed query bytes and of the SQL file bytes agree with both hashes recorded in the artifact")
# Independently verified pin, outside the mutable (SQL file, provenance) pair: the hash of the query the operator ran on
# 2026-09-03 (bq show -j okf_full_demo_sessions_summary_20260903T231025Z). Changing the file and the artifact together
# cannot satisfy this line.
PINNED_SUMMARY_SQL_SHA256 = "59436c24faf964798fe54d9de1b551ea46e776037833f868d1b8b9f92ad7107e"
check(raw_sql_hash == PINNED_SUMMARY_SQL_SHA256, "SQL file bytes match the independently pinned hash of the executed summary query")
check("normalized" not in json.dumps(prov), "provenance artifact carries no normalized hash that a literal collision could satisfy")

def strip_sql_comments(text):
    """Remove -- comments outside single/double/backtick quoted regions (quote-aware; keeps everything executable)."""
    out, i, n, q = [], 0, len(text), None
    while i < n:
        ch = text[i]
        if q:
            out.append(ch)
            if ch == q:
                q = None
            i += 1
            continue
        if ch in ("'", '"', "`"):
            q = ch
            out.append(ch)
            i += 1
            continue
        if text.startswith("--", i):
            while i < n and text[i] != "\n":
                i += 1
            continue
        out.append(ch)
        i += 1
    return "".join(out)

sql_body = strip_sql_comments(sql_text)
check(re.search(r"FROM `test-project-0728-467323\.okf_rfc_demo\.agent_events`", sql_body) and "COUNT(*)" in sql_body and "TOOL_COMPLETED" in sql_body and "GROUP BY 1, 2" in sql_body,
      "the EXECUTABLE body (comments stripped, quote-aware) is the per-session aggregate over agent_events (COUNT(*), TOOL_COMPLETED, GROUP BY 1, 2)")
check(re.search(r"(?is)^\s*SELECT\b.*\bFROM\b.*\bGROUP BY\b", sql_body) and "agent_events" in sql_body.split("FROM", 1)[-1], "the executable body is a single SELECT … FROM agent_events … GROUP BY statement")
check(hashlib.sha256((LIVE / "sessions_summary.json").read_bytes()).hexdigest() == prov["result_sha256"], "sessions_summary.json bytes match the result hash in the artifact")
expected_cols = {"session_id", "agent", "rows_in_table", "tool_completed", "t0", "t1"}
check(set(prov["result_columns"]) == expected_cols and all(set(r) == expected_cols for r in summary) and len(summary) == prov["result_rows"] == 4,
      "result schema (6 columns) and row count (4) bound between the artifact, the result file and the SELECT list")
check(all(re.search(r"\b%s\b" % c, sql_body) for c in ("session_id", "agent", "rows_in_table", "tool_completed", "t0", "t1")), "every result column is named in the executable SELECT list (not in a comment)")
check("summary: \"live/sessions_summary.json\"" in app and "D.summary" in app and "rows_in_table" in app and "tool_completed" in app and "D.fourth" in app and "D.tableRows" in app,
      "app.js consumes sessions_summary.json through D.summary (rows_in_table, tool_completed → D.tableRows, D.fourth)")
check("provenance_sessions_summary.json" in (LIVE / "README.md").read_text("utf-8") and "sessions_summary.json" in (LIVE / "README.md").read_text("utf-8"), "live/README.md lists the summary result and its provenance artifact")

# ---- spec.md status honesty (Codex round 2) -------------------------------------------------------------
spec = (DEMO / "spec.md").read_text("utf-8")
check("| Piece | v1 target | Status on 2026-09-03 (PR 16) |" in spec, "spec.md §1.2 has a status column for what was actually captured")
for piece, marker in (("`okf-context sync` commit into BigQuery runtime tables", "Not built"), ("Catalog stamp on `okf-context-runtime`", "Not done"), ("IAM bootstrap, identities, positive and negative checks", "Not done")):
    row = [ln for ln in spec.split("\n") if ln.startswith("| " + piece)]
    check(bool(row) and marker in row[0] and "RFC text only" in row[0], "spec.md §1.2 row '%s…' is marked %s / RFC text only" % (piece[:40], marker))
check("Source (all recorded; page is static)" not in spec and "| Captured on PR 16 |" in spec, "spec.md §3 beat table no longer says 'all recorded' and carries a Captured-on-PR-16 column")
check("Phase A; not yet met" in spec, "spec.md §4 marks the bootstrap/negative-check criterion as Phase A, not yet met")
arch = (DEMO / "ARCHITECTURE.md").read_text("utf-8")
check("not yet shown" in arch, "ARCHITECTURE.md marks FAIL_STALE / history as not yet shown")

# ---- executed-language scan (Codex rounds 3–7): deferred Phase A must read as future / not done / RFC text only ----
# Block → sentence → clause → predicate. Markdown structure is preserved (heading, list item, table row, blockquote or
# blank line starts a new block; only continuation lines join), so a qualifier in a later item or paragraph never covers
# an earlier clause. Sentences split at . ; : and clauses at commas and connectors (and / or / but / then / while /
# after / before / until / when / because / so …). EVERY executed predicate in a clause is evaluated and must be governed by:
#   MODAL    must / will / shall / expected / to be … heading the predicate's phrase (no new subject opens between the
#            modal and the predicate); latches only into shared-subject NONFINITE continuations, i.e. coordinated clauses
#            that start with the verb ("must create X, bind Y on tape"), never into a clause that opens its own subject
#            ("…, and the operator creates / created / makes …"); reset by then / but / while / because / so and by
#            after / before / until / when / once whenever the clause they open has its own subject.
#   STATUS   not yet / not done / future / deferred / planned / RFC text only / prior / requirement … only when it heads
#            the predicate's phrase; "As planned the operator created …" and a trailing "as planned" qualify nothing.
#   NEGATION not / no / none / nothing / never / cannot / without, only when it heads the predicate's phrase ("were not
#            created", "no service account was created"); "not a secret that the denials were proved" is unbound.
# Binding is structural (a subject opener between qualifier and predicate breaks it), with no token-count ceilings.
# The bare words "Phase A" qualify nothing. Only emphasis is stripped (*, backticks, edge underscores); identifiers such
# as PERMISSION_DENIED, agent_events and user_email survive. Matching is case-insensitive.
PHASE_A_OBJECT = re.compile(r"\b(service accounts?|SAs?|bindings?|binding calls?|grants?|roles?|okf-setup|okf-sync-writer(-okf-rfc-demo)?|okf-runtime-reader|okfCatalogSearch|custom role|Token Creator|boundary(-probe)?|denials?|negative checks?|positive checks?|checks? [1-7]|PERMISSION_DENIED|(the|Phase A|on) tape|impersonation|user_email)\b", re.I)
# ---- the action verbs, as an audited form table (Codex round 10) -------------------------------------------------
# lemma -> (past/participle forms, simple-present 3sg form). Written out and audited: a generator produced "denyed" /
# "denys" and dropped the "run" participle. Only the past forms are load-bearing now: they are the completion
# vocabulary of INV-4, and adding a row can only make more sentences demand a qualifier, never fewer.
VERB_FORMS = {
    "create": (["created"], "creates"), "revoke": (["revoked"], "revokes"), "grant": (["granted"], "grants"),
    "install": (["installed"], "installs"), "record": (["recorded"], "records"), "exercise": (["exercised"], "exercises"),
    "prove": (["proved", "proven"], "proves"), "demonstrate": (["demonstrated"], "demonstrates"),
    "delete": (["deleted"], "deletes"), "execute": (["executed"], "executes"), "run": (["ran", "run"], "runs"),
    "deny": (["denied"], "denies"), "make": (["made"], "makes"), "return": (["returned"], "returns"),
    "complete": (["completed"], "completes"), "perform": (["performed"], "performs"), "show": (["showed", "shown"], "shows"),
    "confirm": (["confirmed"], "confirms"), "impersonate": (["impersonated"], "impersonates"),
    "stamp": (["stamped"], "stamps"), "commit": (["committed"], "commits"),
    "verify": (["verified"], "verifies"), "issue": (["issued"], "issues"), "attach": (["attached"], "attaches"),
}
# Forms identical to their lemma are ambiguous with the infinitive and the noun ("run the DDL jobs", "Cloud Run Job"),
# so they count as a past participle only directly after an auxiliary ("has run", "was run").
AMBIGUOUS_PARTICIPLE = ["run"]
PAST_FORMS = sorted({f for past, _ in VERB_FORMS.values() for f in past if f not in AMBIGUOUS_PARTICIPLE})
# ---- the honesty gate (Codex round 20): an audited claim register, not an English parser -------------------------
# Rounds 3-19 grew a clause parser that tried to decide, for arbitrary English, whether a qualifier bound an executed
# predicate. Every round found a new lexical hole in it - an irregular past that was not listed, a comparative adverb
# that was not listed, a participle shape that was not matched - because that question is open-domain and a regex
# grammar can only ever approximate it. Each patch moved the ceiling; none removed it. The gate is now structural:
#
#   INV-1  COVERAGE.  EVERY sentence of the demo copy must appear, verbatim after whitespace normalisation and under
#          its own source path, in tools/audited_claims.tsv. There is no test deciding which sentences count, so there
#          is nothing to fall outside of: "The IAM bootstrap succeeded.", "sync finished successfully" and any other
#          wording are regulated because all wording is. Coverage costs only rows. New, edited or MOVED prose fails
#          until it is audited, and what a READER sees is what is audited - JSON is read after JSON.parse, HTML after
#          entity decoding, CSS through its generated content.
#   INV-2  EVIDENCE.  Every CAPTURED row cites a file under live/ or sql/ that exists in the tree.
#   INV-3  CONTAINMENT.  A CAPTURED row may name a deferred Phase A artefact only inside a disclaimer frame that sits
#          ON that artefact ("(not okf-setup) ran the DDL"), and a NOT_PHASE_A row may not name one at all. Growing
#          DEFERRED_ARTEFACT only makes both stricter.
#   INV-4  QUALIFIED.  A PENDING row must record a licence FRAME around every completion token in its sentence: one
#          bounded pattern holding the qualifier, its auxiliary chain and the verb, with only verb-phrase material
#          inside. A qualifier that follows its verb, or that belongs to another clause, licenses nothing, so
#          "created … as expected" and "No reviewer knew okf-setup created …" cannot be registered at all. The one
#          exception, stated rather than hidden: a fixed claim PHRASE from the EXECUTED list ("… on tape") is an
#          adjunct with no verb of its own to frame, so it is licensed by the nearest qualifier before it.
#   INV-5  NO STALE ROWS.  A register row whose sentence is no longer in the copy is an error, so the register stays
#          an audit of what ships rather than a graveyard that could pre-license future prose.
#
# Deliberate non-goals, stated so a reviewer can judge the boundary instead of guessing at it:
#   * The register IS the audit. The checker guarantees that no sentence naming a Phase A artefact ships without a
#     recorded verdict, and that the verdict is internally consistent; it does not re-derive the verdict from the
#     sentence's grammar, and it makes no claim to parse English.
#   * A contributor who writes a false sentence AND registers it defeats INV-1 by construction. That is a falsified
#     audit record, visible in the register diff of any pull request, and it is out of scope for a static checker.
#   * Present-tense and imperative contract prose ("create the SAs", "revoke every okf-setup role") asserts nothing
#     about completion, so INV-4 ignores it. INV-1 still covers every such sentence.
#   * What remains load-bearing and lexicon-free is EXTRACTION: text the reader sees must reach the gate. That is why
#     the JavaScript reader is a token scanner with a real paren stack rather than a lookback regex, and why the HTML
#     reader computes an element's effective `display` rather than matching a substring.
MODAL_WORDS = r"must|will|would|shall|should|can|could|may|might"

EXECUTED = [re.compile(rx, re.I) for rx in [
    r"recorded on tape", r"on tape under", r"\bon tape\b", r"\bthe tape shows\b", r"\bthe tape demonstrates\b",
    r"\bdemonstrated, not asserted\b", r"\b(is|was|were|are|been) demonstrated\b", r"\bprove[sd]? (the|that|it)\b", r"\bdenial checks prove\b",
    r"\bmakes every binding\b", r"\bevery binding call is made\b", r"\bcreates? the (three )?service accounts\b", r"\b(are|were|was|is|been) revoked\b",
    r"\beach (binding )?command (is |was )?recorded\b", r"\b(is|are|was|were|been) recorded (on|in) the tape\b", r"returned `?PERMISSION_DENIED",
    r"\bran as `?okf-(setup|sync-writer|runtime-reader)", r"\bexercised once on tape\b", r"\bimpersonated `?user_email`? (from|after)\b",
    r"\bidentity is demonstrated\b", r"\bshows? the impersonated\b", r"\b(was|were|is|are) denied\b", r"\bPERMISSION_DENIED\b[^.;]*\bon tape\b",
    r"\bPhase A (was|has been|is) (executed|done|complete|completed|run|recorded)\b"]]

MODAL = re.compile(r"\b(" + MODAL_WORDS + r"|expected|is to|are to|to be (recorded|run|exercised|made|created|revoked|deleted|granted|stamped|demonstrated|shown))\b", re.I)
STATUS = re.compile(r"\b(not yet|not done|not run|not started|not created|not built|not met|not (been )?executed|has not run|none (has|have|was|were) (been )?run|"
                    r"none happened|neither happened|future|deferred|planned|prior|requirement|acceptance criterion|requires?|does not exist|no (such )?tape)\b|RFC text only", re.I)
NEGATION = re.compile(r"\b(not|no|none|nothing|never|cannot|without)\b", re.I)

# ---- licence frames (Codex round 22) ------------------------------------------------------------------------------
# A licence FRAME binds a qualifier to a completion token inside ONE bounded pattern, instead of accepting any
# qualifier anywhere before it. Only verb-phrase material may stand inside a frame - auxiliaries, our own participles,
# coordinators, "to", adverbs - so a licence cannot reach over a second predicate or into an embedded clause. Three
# constructions, which is what the demo copy actually uses:
#   * a modal or infinitival head over its own verb phrase: "must be recorded", "to be revoked", "must be created and
#     granted on tape";
#   * a negation directly on the verb: "not created", "never recorded", "no stamped pin";
#   * a negation on the SUBJECT of a passive: "No Phase A service account was created". The subject noun phrase may
#     stand between, but no clause boundary and no complementizer may, so "It is not a secret THAT the denials were
#     proved" and "No reviewer KNEW okf-setup created the service accounts" are not frames - the first embeds its
#     claim, the second has no auxiliary at all between the negation and the verb.
PAST_TOKEN = r"(?:" + "|".join(PAST_FORMS) + r")"
# Inside a frame the verb may be ANY regular past participle: a qualifier that reaches its verb licenses that verb
# whatever it is, so "none happened" and "must be deployed" are frames like "must be recorded".
ANY_PAST = r"(?:(?i:[a-z]+ed)|" + PAST_TOKEN + r")"
FRAME_ADVERB = r"(?-i:[a-z]+ly)|yet|ever|already|also|then|still|now|only|just|even|again|duly|once|first|never|not"
VERB_PHRASE_FILL = r"(?:\s+(?:be|been|being|is|are|was|were|has|have|had|and|or|to|" + PAST_TOKEN + r"|" + FRAME_ADVERB + r"))*"
CLAUSE_FILL = r"(?:[^,;:.]|\.(?=\w))"               # one clause: no clause boundary, but "§1.3" is one token
# Determiners and prepositions are closed classes, used here only to bound a frame's fill: inside a negated SUBJECT a
# new determiner opens a NEW noun phrase - and therefore a second predicate - unless a preposition put it there. So
# "No service account IN THE Phase A project was created" is one subject while "No reviewer knew THE Phase A service
# accounts were created" is two clauses, without the checker knowing that "knew" is a verb.
DETERMINER_WORD = (r"the|a|an|this|that|these|those|its|their|our|his|her|my|your|each|every|all|both|either|neither|"
                   r"such|any|some|no|another|own|one|two|three|four|five|six|seven|eight|nine|ten|many|few|several|most")
PREPOSITION_WORD = (r"at|in|on|of|for|by|with|from|into|per|via|under|over|during|through|across|between|within|"
                    r"without|about|as|than|below|above|beside|beyond|behind|beneath|to|onto|upon|among")
# The determiner test is case-sensitive on purpose: a lone capital "A" is a name part ("Phase A"), not the article.
SUBJECT_FILL = (r"(?:\s+(?:(?:" + PREPOSITION_WORD + r")\s+(?-i:" + DETERMINER_WORD + r")\b"
                r"|(?!(?-i:" + DETERMINER_WORD + r")\b)[\w'’.§%$/·—–-]+))*")
COMPLEMENTIZER = r"that|which|who|whom|whose|why|how|when|where|whether|if"
LICENCE_FRAMES = [
    re.compile(r"\b(?:" + MODAL_WORDS + r"|expected)\b" + VERB_PHRASE_FILL + r"\s+" + ANY_PAST + r"\b", re.I),
    re.compile(r"\bto\b" + VERB_PHRASE_FILL + r"\s+" + ANY_PAST + r"\b", re.I),
    re.compile(r"\b(?:not|never|no|none|nothing|neither|without)\b(?:\s+(?:" + FRAME_ADVERB + r"|been|be|being))*\s+"
               + ANY_PAST + r"\b", re.I),
    re.compile(r"\b(?:no|none|nothing|neither|not)\b(?!" + CLAUSE_FILL + r"*\b(?:" + COMPLEMENTIZER + r")\b)"
               + SUBJECT_FILL + r"\s+(?:was|were|is|are|been)\b(?:\s+(?:" + FRAME_ADVERB + r"|been))*\s+"
               + ANY_PAST + r"\b", re.I),
    # A non-factive complement leaves its clause unasserted, so a completion token inside one is a question, not a
    # claim: "must verify WHETHER the service accounts were created". The auxiliary must still be inside the frame,
    # so "report whether the operator created …" is not one.
    re.compile(r"\b(?:whether|if)\b" + CLAUSE_FILL + r"{0,60}?\s(?:was|were|is|are|been|has|have|had)\b"
               + r"(?:\s+(?:" + FRAME_ADVERB + r"|been))*\s+" + ANY_PAST + r"\b", re.I),
]
COMPLETION_VERB = re.compile(r"\b" + PAST_TOKEN + r"\b", re.I)
COMPLETION_PHRASE = re.compile("|".join("(?:%s)" % rx.pattern for rx in EXECUTED), re.I)
# A disclaimer FRAME sits immediately on the artefact it disclaims - "(not okf-setup)", "not yet by the Phase A
# service accounts", "no service account" - so a negation belonging to some other clause cannot stand in for one.
DISCLAIMER_FRAME = re.compile(r"\b(?:not|no|never|nothing|neither|without)\b"
                              r"(?:\s+(?:yet|as|by|from|for|to|of|in|on|the|a|an|any|its|their|each|every|one|"
                              r"(?-i:Phase)|(?-i:A)))*\s*$", re.I)
# A verb PREDICATED of a deferred artefact is a claim about it, whatever the verb is. Round 24 could only see a verb
# closing the artefact's own noun phrase; a browser reader sees the predicate wherever the ordinary machinery of
# English puts it, so the reach now spans the rest of one noun phrase, at most one prepositional phrase, an auxiliary
# chain and an adverbial tail: "The IAM bootstrap has succeeded.", "… in staging succeeded.", "… succeeded yesterday."
# What still ends the reach is structure, not distance: a determiner or a coordinator or a second preposition opens
# something new, punctuation ends the clause, a determiner immediately before the verb makes it attributive ("an
# isolated configuration"), and a following "by" without an auxiliary makes it a reduced relative ("the aspect type
# owned by the setup identity").
AUXILIARY_WORD = r"is|are|was|were|be|been|being|has|have|had|having|does|do|did|" + MODAL_WORDS
SUBORDINATOR_WORD = (r"because|since|so|when|while|if|unless|until|after|before|although|though|whereas|that|which|"
                     r"who|whom|whose|whether|how|why|where")
COORDINATOR_WORD = r"and|or|but|nor|plus|then"
NP_STOP = (r"(?-i:" + DETERMINER_WORD + r")|(?i:" + PREPOSITION_WORD + r"|" + AUXILIARY_WORD + r"|"
           + SUBORDINATOR_WORD + r"|" + COORDINATOR_WORD + r")")
BARE_RUN = r"(?:\s+(?!(?:" + NP_STOP + r")\b)[A-Za-z][\w'’]*){0,3}"
ONE_PP = r"(?:\s+(?i:" + PREPOSITION_WORD + r")(?:\s+(?-i:" + DETERMINER_WORD + r"))?" + BARE_RUN + r")?"
AUX_RUN = r"(?:\s+(?i:" + AUXILIARY_WORD + r"))*"
ADVERB_RUN = r"(?:\s+(?:(?i:[a-z]+ly)|not|never|also|already|then|still|now|only|just|even|yet))*"
ADVERBIAL_TAIL = r"(?:\s+(?:(?i:[a-z]+ly)|(?!(?:" + NP_STOP + r")\b)[A-Za-z][\w'’]*)){0,2}"
POSTPOSED_VERB = re.compile(BARE_RUN + ONE_PP + AUX_RUN + ADVERB_RUN + r"\s+(?<![-\w])(" + ANY_PAST + r")\b"
                            + ADVERBIAL_TAIL + r"\s*(?=[,;:.)\]|]|$)")

def postposed_problems(sent):
    """PENDING says nothing here was executed. A verb predicated of a deferred artefact says otherwise unless a
    licence frame covers it."""
    out = []
    frames = [(m.start(), m.end()) for rx in LICENCE_FRAMES for m in rx.finditer(sent)]
    for a in DEFERRED_ARTEFACT.finditer(sent):
        m = POSTPOSED_VERB.match(sent[a.end():])
        if not m:
            continue
        at, end = a.end() + m.start(1), a.end() + m.end(1)
        before = re.search(r"([\w'’-]+)\s*$", sent[:at])
        before = before.group(1).lower() if before else ""
        if re.fullmatch(DETERMINER_WORD, before, re.I):
            continue                                  # attributive: "an isolated gcloud configuration"
        if sent[end:].lstrip()[:3].lower() == "by " and not re.fullmatch(AUXILIARY_WORD, before, re.I):
            continue                                  # reduced relative: "the aspect type owned by the service"
        if any(x <= at and end <= y for x, y in frames):
            continue
        out.append("%r is predicated of %r with no licence frame" % (m.group(1)[:24], a.group(0)[:24]))
    return out


# The qualifier vocabulary. It is used only to ask "is a qualifier present in this sentence", never to bind one to a
# predicate, so a missing word here can at most demand an audit note - it cannot license an unaudited claim.
QUALIFIER = re.compile("(?:%s)|(?:%s)|(?:%s)" % (MODAL.pattern, STATUS.pattern, NEGATION.pattern), re.I)
# Completion language: any past / participle form of the audited action verbs, or one of the EXECUTED phrases.
COMPLETION = re.compile(r"\b(?:" + "|".join(PAST_FORMS) + r")\b|" + "|".join("(?:%s)" % rx.pattern for rx in EXECUTED), re.I)
# The artefacts that do not exist on this PR. Narrower than PHASE_A_OBJECT on purpose: legacy context_ref bindings,
# BigQuery grants and user_email rows are real, so naming them is not a Phase A claim.
DEFERRED_ARTEFACT = re.compile(r"\b(?<![-\w])(?<!pre-)(?<!post-)(Phase[- ]A|service accounts?|SAs?|okf-setup|okf-sync-writer(-okf-rfc-demo)?|"
                               r"okf-runtime-reader|okf-context[- ](sync|runtime)|okfCatalogSearch|"
                               r"custom (search )?role|table-level grants?|boundary(-| )?probe|boundary EntryGroup|"
                               r"negative checks?|positive checks?|denial checks?|denials?|binding calls?|"
                               r"PERMISSION_DENIED|BQ_COMMITTED|CATALOG_STAMPED|FAIL_STALE|Token Creator|"
                               r"impersonation|(on|the) tape)\b", re.I)
def regulated(sent):
    """Every sentence of the demo copy needs an audited verdict. Rounds 20 and 21 tried to decide which sentences were
    "about the project" - first from an artefact list, then from identifier shapes - and each time a reviewer found an
    ordinary English claim that fell outside ("The IAM bootstrap succeeded."). There is no test here to fall outside
    of now: coverage costs nothing but rows, so it is total, and no vocabulary anywhere can license unaudited prose."""
    return True

# The pieces the demo itself declares undone. Derived from spec.md 1.2's own status table rather than hand-listed
# here, so the artefact vocabulary is the RFC's own declaration: mark a new piece "Not built" / "Not done" / "Partly"
# and the gate widens with it. "IAM bootstrap" is deferred because the spec says so, not because a checker author
# remembered it.
def declared_deferred():
    try:
        spec_text = (DEMO / "spec.md").read_text("utf-8")
    except OSError:
        return []
    out = []
    section = spec_text[spec_text.index("### 1.2"):spec_text.index("### 1.3")] if "### 1.2" in spec_text and "### 1.3" in spec_text else ""
    for row in re.findall(r"(?m)^\|(.+)\|(.+)\|(.+)\|\s*$", section):
        if not re.search(r"\b(Not built|Not done|Not shown|Partly|Not run|Not started)\b", row[2], re.I):
            continue
        piece = re.sub(r"[`*]", "", row[0])
        piece = re.sub(r"\(§[\d.]+\)", " ", piece)
        for frag in re.split(r"[,/]| and ", piece):
            frag = frag.strip(" .")
            # A fragment has to be specific enough to name a piece: two words, or an identifier shape. A bare
            # common noun ("identities") would match everywhere and say nothing.
            if 3 < len(frag) <= 60 and (" " in frag or re.search(r"[A-Z0-9_-]", frag)) and re.search(r"[A-Za-z]", frag):
                out.append(frag)
    return sorted(set(out), key=len, reverse=True)

DECLARED_DEFERRED = declared_deferred()
DEFERRED_ARTEFACT = re.compile(DEFERRED_ARTEFACT.pattern + ("|" + "|".join(re.escape(x) for x in DECLARED_DEFERRED)
                                                           if DECLARED_DEFERRED else ""), re.I)

NOT_DONE = re.compile(r"\b(not|no|none|never|without|nothing|neither|yet|deferred|planned|future|prior|pending|"
                      r"requirements?|acceptance|expected|must|will|would|shall|should)\b|RFC text only", re.I)

SCAN_FILES = ["spec.md", "ARCHITECTURE.md", "plan.md", "intent.md", "CUSTOMER_STORIES.md", "README.md", "live/README.md", "index.html", "app.js", "stories.json", "matrix.json", "styles.css"]

# ---- the dependency graph (Codex rounds 23-25), fail-closed -------------------------------------------------------
# Everything the page can put on the screen is either COPY, audited sentence by sentence in the register, or a
# CAPTURE, pinned byte for byte in tools/live_manifest.tsv. Round 23 scraped app.js's FILES / TEXTS maps; round 24
# widened that to every path literal; both still read a path as a bare string. A browser resolves a URL against the
# document that asked for it, so this reader does too: every reference is resolved from ITS OWN loading file, which
# is what makes fetchText("../index.html") a dependency on rfc/index.html rather than an alias of this directory's.
# The graph is walked from index.html through its stylesheet and script, and through @import, so an unregistered
# stylesheet cannot smuggle generated content in. Anything that resolves to a real file - inside this directory or
# above it - has to be pinned or audited.
HTML_REF = re.compile(r"(?:href|src)\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>=`]+))", re.I)
CSS_REF = re.compile(r"@import\s+(?:url\(\s*)?(?:\"([^\"]*)\"|'([^']*)'|([^\s;)]+))|url\(\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s)]+))", re.I)
PATHY = re.compile(r"^[\w./-]+\.[A-Za-z0-9]{1,6}$")

def _refs(rel):
    """Every URL a source file asks the browser for, as written."""
    try:
        body = (DEMO / rel).read_text("utf-8")
    except OSError:
        return []
    if rel.endswith(".js"):
        return [t for _, kind, t, _, _ in _js_pieces(body) if kind == "lit" and PATHY.match(t.strip())]
    if rel.endswith(".css"):
        return [g for m in CSS_REF.finditer(body) for g in m.groups() if g]
    if rel.endswith((".html", ".htm")):
        return [g for m in HTML_REF.finditer(body) for g in m.groups() if g]
    return []

def dependency_graph():
    """Resolve the graph from index.html outwards, each reference against the directory of the file that made it.
    Returns (paths relative to this directory, including "../" ones, sorted; unresolvable references)."""
    seen, queue, outside = set(), ["index.html"], []
    while queue:
        rel = queue.pop()
        if rel in seen:
            continue
        seen.add(rel)
        base = posixpath.dirname(rel)
        for ref in _refs(rel):
            ref = ref.split("#", 1)[0].split("?", 1)[0].strip()
            if not ref or "://" in ref or ref.startswith(("mailto:", "data:", "//")):
                continue
            target = posixpath.normpath(posixpath.join(base, ref)) if not ref.startswith("/") else ref.lstrip("/")
            if not (DEMO / target).is_file():
                if PATHY.match(ref):
                    outside.append("%s asks for %s, which resolves to no file" % (rel, ref))
                continue
            queue.append(target)
    return sorted(seen), outside

def viewer_files():
    """The inventory: every file under live/ and sql/, whether or not anything fetches it yet, plus every file the
    dependency graph reaches from index.html."""
    out = set()
    for root in ("live", "sql"):
        base = DEMO / root
        if base.is_dir():
            out |= {str(f.relative_to(DEMO)) for f in base.rglob("*") if f.is_file()}
    reached, _ = dependency_graph()
    return sorted(out | set(reached))


# A declaration value ends at the first semicolon or brace OUTSIDE a string, so a quoted value may contain either.
# ---- a stateful CSS tokenizer (Codex round 25) --------------------------------------------------------------------
# Round 24 decoded escapes over the whole sheet before tokenizing, which is not what a browser does: an escaped quote
# inside a string became a real delimiter, and a backslash-newline survived as whitespace instead of vanishing. The
# reader now tokenizes the way the CSS syntax spec does - escapes are decoded IN TOKEN CONTEXT - and assembles each
# `content` declaration into the one string the browser paints, so strings, attr() and counters interleave into a
# single run of copy instead of separate fragments.
CSS_COMMENT = re.compile(r"/\*.*?\*/", re.S)

def _css_escape(src, i):
    """Decode one escape starting at src[i] == '\\'; returns (text, next index). A backslash-newline is a line
    continuation and contributes nothing, and \\6e is 'n' whether or not a space closes it."""
    j = i + 1
    if j >= len(src):
        return "", j
    if src[j] == "\n":
        return "", j + 1                              # line continuation: the browser drops it entirely
    m = re.match(r"[0-9a-fA-F]{1,6}", src[j:j + 6])
    if m:
        j += len(m.group(0))
        if j < len(src) and src[j] in " \t\n":
            j += 1                                    # one whitespace closes a hex escape and is not literal
        try:
            return chr(int(m.group(0), 16)), j
        except (ValueError, OverflowError):
            return "", j
    return src[j], j + 1

def _css_string(src, i):
    """Read a quoted string starting at the quote; returns (text, next index)."""
    quote, out, i = src[i], [], i + 1
    while i < len(src) and src[i] != quote:
        if src[i] == "\\":
            text, i = _css_escape(src, i)
            out.append(text)
            continue
        if src[i] == "\n":
            break                                     # an unterminated string ends at the newline
        out.append(src[i])
        i += 1
    return "".join(out), i + 1

def _css_ident(src, i):
    """Read an identifier, decoding escapes in token context, so `co\\6e tent` reads as `content`."""
    out = []
    while i < len(src):
        if src[i] == "\\":
            text, i = _css_escape(src, i)
            out.append(text)
            continue
        if src[i].isalnum() or src[i] in "-_":
            out.append(src[i])
            i += 1
            continue
        break
    return "".join(out), i

def _attribute_values(name):
    """What `content: attr(x)` prints: the x attribute of any element the page ships - written into index.html, or
    built by app.js and inserted into the DOM. Values are entity-decoded, because that is what the DOM holds and what
    attr() copies onto the screen. Quoted and unquoted forms are both read."""
    out = []
    pattern = re.compile(r"(?<![-\w])" + re.escape(name) + r"\s*=\s*(?:\"([^\"]*)\"|'([^']*)'|([^\s\"'>=`]+))", re.I)
    for src_name in ("index.html", "app.js"):
        try:
            body = (DEMO / src_name).read_text("utf-8")
        except OSError:
            continue
        if src_name.endswith(".js"):
            body = " ".join(t for _, kind, t, _, _ in _js_pieces(body) if kind == "lit")
        out += [html.unescape(a or b or c) for a, b, c in pattern.findall(body)]
    return out

def css_content_values(src):
    """Yield (assembled generated value, unmodelled functions) for every `content` declaration in a stylesheet. The
    value is assembled in source order - "The " attr(data-target) " were created." is ONE run - because that is what
    the browser paints."""
    src = CSS_COMMENT.sub(" ", src)
    i, n = 0, len(src)
    while i < n:
        ch = src[i]
        if ch in "\"'":
            _, i = _css_string(src, i)
            continue
        if ch.isalpha() or ch in "-_\\":
            name, j = _css_ident(src, i)
            k = j
            while k < n and src[k] in " \t\n":
                k += 1
            if name.lower() == "content" and k < n and src[k] == ":":
                pieces, unmodelled, k = [], [], k + 1
                while k < n and src[k] not in ";}":
                    if src[k] in "\"'":
                        text, k = _css_string(src, k)
                        pieces.append(text)
                        continue
                    if src[k].isalpha() or src[k] in "-_\\":
                        fn, k2 = _css_ident(src, k)
                        k3 = k2
                        while k3 < n and src[k3] in " \t":
                            k3 += 1
                        if k3 < n and src[k3] == "(":
                            depth, k4 = 1, k3 + 1
                            while k4 < n and depth:
                                if src[k4] in "\"'":
                                    _, k4 = _css_string(src, k4)
                                    continue
                                depth += (src[k4] == "(") - (src[k4] == ")")
                                k4 += 1
                            args = src[k3 + 1:k4 - 1]
                            if fn.lower() == "attr":
                                attr = _css_ident(args.strip(), 0)[0]
                                values = _attribute_values(attr)
                                if not values:
                                    unmodelled.append("attr(%s) resolves to no attribute this checker can read" % attr)
                                pieces.append(" ".join(values))
                            elif fn.lower() not in ("counter", "counters", "url", "image-set", "linear-gradient"):
                                unmodelled.append("content uses %s(), which this checker does not model" % fn)
                            k = k4
                            continue
                        k = k2
                        continue
                    k += 1
                yield "".join(pieces).strip(), unmodelled
                i = k
                continue
            i = j
            continue
        i += 1

def extract_css_prose(src):
    """The only parts of a stylesheet a reader can see: the value each `content` declaration paints, and comments. A
    generated-content function this reader cannot model is reported for audit rather than dropped."""
    out, unmodelled = [], []
    for m in re.finditer(r"/\*(.*?)\*/", src, re.S):
        out.append(m.group(1).replace("\n", " ").strip())
    for value, problems in css_content_values(src):
        out.append(value)
        unmodelled += problems
    out += ["UNMODELLED GENERATED CONTENT: " + u for u in sorted(set(unmodelled))]
    return "\n".join("| " + t.replace("\n", " ") for t in out if t)
BLOCK_START = re.compile(r"^\s*(#{1,6}\s|[-*+]\s|\d+[.)]\s|>\s?|\|)")

def md_blocks(text):
    """Yield (start_line, block_text). New block at blank line, heading, list item, table row or blockquote line."""
    lines = text.split("\n")
    cur, start = [], None
    for i, ln in enumerate(lines, 1):
        if not ln.strip():
            if cur:
                yield start, " ".join(cur)
            cur, start = [], None
            continue
        if BLOCK_START.match(ln) and cur:
            yield start, " ".join(cur)
            cur, start = [], None
        if not cur:
            start = i
        cur.append(ln.strip())
    if cur:
        yield start, " ".join(cur)

INLINE_CODE = re.compile(r"`{1,3}[^`\n]+`{1,3}")
CLI_SHAPE = re.compile(r"[<>|$*&;{}\[\]]|--|\bSELECT\b|^(?:gcloud|bq|curl|python3?|bun|npm|git|sed|export|unset|aspect-types|entry-types|entry-groups|entries|dataplex)\b", re.I)

def _code_span(inner):
    """Inline code stays readable when it is plain prose (`custom role`, `okf-setup`) so a protected object is still
    visible to the scanner; a shell / SQL fragment collapses to one opaque token so it is not parsed as a sentence."""
    return inner if not CLI_SHAPE.search(inner) else "code"

# Whether a "/" opens a regular expression or divides is decided the way a JavaScript tokenizer decides it: from the
# PREVIOUS significant token, with a real stack for parentheses. A "/" divides after a value - an identifier, a number,
# a string, a regex, "]", or a ")" that closed an ordinary call or grouping - and opens a regex everywhere else,
# including after a ")" that closed an if / for / while / switch / catch head. A word after "." is a property name, not
# a keyword, so "holder.if(ready) / x" and "holder . throw / x" are division however much whitespace sits around the
# dot. There is no lookback window and no nesting limit, so neither a long condition nor a deeply nested one can
# desynchronise the reader.
JS_WORD = re.compile(r"[A-Za-z_$][\w$]*")
JS_NUMBER = re.compile(r"(?:0[xXbBoO])?[\d._]+(?:[eE][+-]?\d+)?n?")
JS_CONTROL = {"if", "for", "while", "switch", "catch", "with"}
JS_VALUE_WORD = {"this", "true", "false", "null", "super"}
JS_KEYWORD = {"return", "throw", "typeof", "instanceof", "in", "of", "new", "delete", "void", "case", "do", "else",
              "yield", "await", "function", "var", "let", "const", "class", "extends", "import", "export", "default",
              "if", "for", "while", "switch", "catch", "with"}

ESCAPES = {"n": " ", "t": " ", "r": " ", "b": "", "f": "", "v": "", "0": "", "\n": ""}

def _decode_escape(src, i):
    """Decode a JavaScript escape so its character survives into the prose: \\u0065 is "e", \\' is an apostrophe."""
    ch = src[i + 1] if i + 1 < len(src) else ""
    if ch == "u" and src[i + 2:i + 3] == "{":
        j = src.find("}", i + 3)
        if j > 0:
            try:
                return chr(int(src[i + 3:j], 16)), j + 1
            except ValueError:
                return "", j + 1
    if ch == "u" and re.fullmatch(r"[0-9a-fA-F]{4}", src[i + 2:i + 6] or ""):
        return chr(int(src[i + 2:i + 6], 16)), i + 6
    if ch == "x" and re.fullmatch(r"[0-9a-fA-F]{2}", src[i + 2:i + 4] or ""):
        return chr(int(src[i + 2:i + 4], 16)), i + 4
    return ESCAPES.get(ch, ch), i + 2

def _js_pieces(src):
    """Walk a JavaScript source and yield (line, kind, text, start_offset, end_offset) for every string literal and
    comment, and nothing else. Escapes are decoded, so "cr\\u0065ated" reads as "created"; regular-expression literals
    are recognised by the token rule above, so a regex containing a quote cannot shift the quoting state and spill
    executable code into the scanned prose."""
    i, n, line = 0, len(src), 1
    prev_value = False                                # can the previous significant token end an expression?
    prev_dot = False                                  # was it "."?
    last_word = None                                  # the last word token, for "if (" style heads
    parens = []                                       # one flag per open "(": True when it heads a control statement
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in " \t\r\f\v":
            i += 1
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            yield line, "com", src[i + 2:j], i, j
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i)
            j = n if j < 0 else j + 2
            body = src[i + 2:max(i + 2, j - 2)]
            yield line, "com", body.replace("\n", " "), i, j
            line += body.count("\n")
            i = j
            continue
        if ch in "'\"`":
            quote, start_line, buf, start_off = ch, line, [], i
            i += 1
            while i < n and src[i] != quote:
                if src[i] == "\\":
                    esc, i = _decode_escape(src, i)   # keep the escaped character, and drop a line continuation
                    buf.append(esc)
                    continue
                if src[i] == "\n":
                    line += 1
                buf.append(src[i])
                i += 1
            i += 1
            yield start_line, "lit", "".join(buf), start_off, i
            prev_value, prev_dot, last_word = True, False, None
            continue
        m = JS_WORD.match(src, i)
        if m:
            word = m.group(0)
            i = m.end()
            if prev_dot:
                prev_value, last_word = True, None     # a property name, never a keyword
            else:
                last_word = word
                prev_value = word in JS_VALUE_WORD or word not in JS_KEYWORD
            prev_dot = False
            continue
        if ch.isdigit():
            i = JS_NUMBER.match(src, i).end()
            prev_value, prev_dot, last_word = True, False, None
            continue
        if ch == "/":
            if prev_value:                            # division, or the /= operator
                i += 2 if src[i + 1:i + 2] == "=" else 1
                prev_value, prev_dot, last_word = False, False, None
                continue
            i += 1                                    # a regular-expression literal: skip it, class-aware
            in_class = False
            while i < n and (in_class or src[i] != "/"):
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "[":
                    in_class = True
                elif src[i] == "]":
                    in_class = False
                elif src[i] == "\n":
                    line += 1
                    break
                i += 1
            i += 1
            while i < n and src[i].isalpha():         # flags
                i += 1
            prev_value, prev_dot, last_word = True, False, None
            continue
        if src.startswith("++", i) or src.startswith("--", i):
            # Postfix after a value leaves a value behind ("x++ / 2" divides); prefix leaves the operand's own state.
            i += 2
            prev_dot, last_word = False, None
            continue
        if ch == "(":
            parens.append(last_word in JS_CONTROL)
            prev_value, prev_dot, last_word = False, False, None
        elif ch == ")":
            prev_value = not (parens.pop() if parens else False)
            prev_dot, last_word = False, None
        elif ch in "]":
            prev_value, prev_dot, last_word = True, False, None
        elif ch == ".":
            prev_dot, prev_value, last_word = True, False, None
        else:                                         # "{", "}", operators, separators: a value cannot precede "/"
            prev_value, prev_dot, last_word = False, False, None
        i += 1

# Two literals belong to one rendered run only when nothing but a concatenation stands between them: whitespace, "+",
# and simple call/member expressions ("… " + esc(D.jobUser) + " …"). A ";" or a new statement ends the run, so two
# unrelated literals on neighbouring lines are never merged.
CONCAT_GAP = re.compile(r"[\s+]*(?:[A-Za-z_$][\w$.]*\s*\([^();{}]*\)|[A-Za-z_$][\w$.\[\]]*)?[\s+]*")

def extract_js_prose(src):
    """Return only the prose of a JavaScript source: string-literal text and comment text. Executable code never
    appears, so `function current() { return roles; }` is not read as a sentence. Every piece is emitted as its own
    Markdown block (leading "|"), so a comment can never qualify a claim in a neighbouring literal. Consecutive
    literals within two source lines are joined, because the page renders them as one run of text — a claim split
    across concatenated literals is still a claim."""
    lines = [""] * (src.count("\n") + 2)
    run_start, prev_end = None, None
    for line, kind, text, start_off, end_off in _js_pieces(src):
        text = html_runs(text).strip()
        joins = (kind == "lit" and run_start is not None and prev_end is not None
                 and CONCAT_GAP.fullmatch(src[prev_end:start_off]))
        if not text:
            if joins:
                prev_end = end_off
            continue
        if not joins and kind == "lit" and not re.search(r"\s", text):
            continue                                  # a lone one-word literal is a key or class name, not prose
        if joins:
            lines[run_start] = (lines[run_start] + " " + text).strip()
            prev_end = end_off
            continue
        target = min(line, len(lines) - 1)
        lines[target] = (lines[target] + " | " + text).strip() if lines[target] else "| " + text
        run_start, prev_end = (target, end_off) if kind == "lit" else (None, None)
    return "\n".join(lines)

# An HTML tag ends a text run: the words on either side of it belong to different elements, so they are different
# clauses. "|" is already the hard clause boundary the scanner uses for Markdown table cells.
BLOCK_TAG = re.compile(r"</?(?:div|p|li|ul|ol|tr|td|th|table|section|article|header|footer|nav|details|summary|pre|blockquote|h[1-6]|br|dl|dt|dd|form|figure)\b[^>]*>", re.I)
INLINE_TAG = re.compile(r"</?[a-zA-Z][^>]*>")

# What the browser renders. Attributes are read as name / value pairs rather than as loose tokens, so title="hidden"
# and data-hidden="false" are visible elements; a style hides its element only when the LAST display declaration is
# none, because that is the one CSS applies; and the element is removed with its nesting balanced, so an inner tag of
# the same name cannot end the removal early and leave hidden text in the reader's view.
HTML_COMMENT = re.compile(r"<!--.*?-->", re.S)
VOID_TAG = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta", "param", "source", "track", "wbr"}
OPEN_TAG = re.compile(r"<([A-Za-z][\w-]*)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*)>")
ATTR = re.compile(r"([A-Za-z_:][-\w:.]*)(?:\s*=\s*(\"[^\"]*\"|'[^']*'|[^\s\"'>=`]+))?")

def _style_display(value):
    """The display a browser computes from a style attribute. An !important declaration beats any normal one in the
    same block whatever the order; otherwise the last declaration wins; and a custom property ("--x: display:none")
    declares a variable, not a display."""
    normal = important = None
    for decl in value.split(";"):
        prop, sep, val = decl.partition(":")
        if not sep:
            continue
        prop = prop.strip()
        if prop.startswith("--") or prop.lower() != "display":
            continue
        val = val.strip()
        bang = re.search(r"!\s*important\s*$", val, re.I)
        word = re.sub(r"!\s*important\s*$", "", val, flags=re.I).strip().lower()
        if bang:
            important = word
        else:
            normal = word
    return important if important is not None else normal

def _is_hidden(attrs):
    """True when the browser does not render the element: a `hidden` attribute or a computed display of none.
    aria-hidden is NOT here: it takes an element out of the accessibility tree while leaving it on the screen, so its
    text is read by a sighted reader and must be audited. Attributes are read as name / value pairs, so title="hidden"
    and data-hidden="false" are visible elements whose text the reader sees."""
    for m in ATTR.finditer(attrs):
        name, val = m.group(1).lower(), (m.group(2) or "").strip("\"'")
        if name == "hidden":
            return True
        if name == "style" and _style_display(val) == "none":
            return True
    return False

def _drop_hidden(text):
    out, i = [], 0
    while True:
        m = OPEN_TAG.search(text, i)
        if not m:
            out.append(text[i:])
            return "".join(out)
        out.append(text[i:m.start()])
        if not _is_hidden(m.group(2)):
            out.append(m.group(0))
            i = m.end()
            continue
        out.append(" ")
        if m.group(1).lower() in VOID_TAG or m.group(2).rstrip().endswith("/"):
            i = m.end()
            continue
        edge = re.compile(r"<(/?)" + re.escape(m.group(1)) + r"(?![\w-])[^>]*>", re.I)
        depth, j = 1, m.end()
        while depth:
            c = edge.search(text, j)
            if not c:
                return "".join(out)                   # an unclosed hidden element hides the rest of the run too
            depth += -1 if c.group(1) else 1
            j = c.end()
        i = j

# Attributes that carry no copy a reader can meet: plumbing, geometry and identifiers. EVERY other attribute value is
# read as copy, because a browser can put one on the screen (`value`, `alt`, `placeholder`, `title`, `aria-label`, a
# `data-` attribute a stylesheet prints with attr()). The list is an EXCLUSION list on purpose: forgetting an entry
# adds rows to audit, it never drops a claim.
NON_TEXT_ATTR = {
    "class", "id", "href", "src", "srcset", "style", "type", "rel", "target", "role", "name", "for", "width",
    "height", "colspan", "rowspan", "xmlns", "viewbox", "d", "fill", "stroke", "stroke-width", "stroke-linecap",
    "stroke-linejoin", "lang", "charset", "http-equiv", "property", "media", "sizes", "integrity", "crossorigin",
    "referrerpolicy", "loading", "decoding", "async", "defer", "hidden", "open", "disabled", "checked", "selected",
    "readonly", "required", "multiple", "novalidate", "autocomplete", "autofocus", "tabindex", "colspan", "scope",
    "aria-hidden", "aria-live", "aria-current", "aria-controls", "aria-expanded", "aria-selected", "data-beat",
    "data-tone", "viewport", "preserveaspectratio", "points", "cx", "cy", "r", "x", "y", "x1", "x2", "y1", "y2",
    "rx", "ry", "transform", "offset", "stop-color", "gradientunits", "patternunits", "clip-path", "version",
}

def attribute_copy(text):
    """The copy a reader can meet through an attribute rather than through element text: a button's `value`, an
    image's `alt`, a tooltip's `title`, a label a stylesheet prints. Each is its own run."""
    out = []
    for m in OPEN_TAG.finditer(text):
        for a in ATTR.finditer(m.group(2)):
            name = a.group(1).lower()
            value = html.unescape((a.group(2) or "").strip("\"'")).strip()
            if name in NON_TEXT_ATTR or not value or not re.search(r"[A-Za-z]", value):
                continue
            out.append(value)
    return out

def html_runs(text):
    """What the reader sees. Hidden elements are dropped whole, so text the browser never renders can neither make a
    claim nor qualify one; block-level tags separate text runs; inline tags are removed so a phrase the reader sees as
    one ("The service <strong>accounts</strong> were created") stays one clause. Copy a browser shows from an
    ATTRIBUTE - a button label, an alt text, a tooltip - is emitted as its own run rather than thrown away with the
    tag that carried it."""
    text = HTML_COMMENT.sub(" ", text)            # a comment is not rendered, and its tags open no element
    text = _drop_hidden(text)
    attrs = attribute_copy(text)
    text = INLINE_TAG.sub("", BLOCK_TAG.sub(" | ", text))
    text = html.unescape(text)                        # &#66;Q_COMMITTED is BQ_COMMITTED on the screen
    text = re.sub(r"[ \t]{2,}", " ", text)            # removing an element must not split "service  accounts"
    return text + ("\n" + "\n".join("| " + a for a in attrs) if attrs else "")

def strip_markdown(text):
    """Collapse inline code to one opaque token, then remove emphasis markers (*, stray backticks, and _ at word
    edges). Identifier underscores survive, so PERMISSION_DENIED and agent_events stay intact."""
    text = INLINE_CODE.sub(lambda m: _code_span(m.group(0).strip("`")), text)
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])", "", text)

# ---- the register: coverage, binding, evidence, containment, qualification, staleness ----------------------------
REGISTER = HERE / "audited_claims.tsv"
VERDICTS = ("PENDING", "CAPTURED", "NOT_PHASE_A")
EVIDENCE_ROOTS = [(DEMO / d).resolve() for d in ("live", "sql")]

def extract_json_prose(src):
    """What the viewer renders: the string VALUES a JSON document carries, after JSON.parse. app.js prints parsed
    values, so "BQ\\u005fCOMMITTED happened." is BQ_COMMITTED happened. on the screen and must be audited as such;
    auditing the source bytes would let any escape hide a claim."""
    try:
        doc = json.loads(src)
    except ValueError:
        return src                                    # not JSON after all: audit the bytes rather than nothing
    out = []

    def walk(node):
        if isinstance(node, dict):
            for v in node.values():
                walk(v)
        elif isinstance(node, list):
            for v in node:
                walk(v)
        elif isinstance(node, str):
            # app.js puts most values through esc() before innerHTML, so "<span hidden>…</span>" is LITERAL text on
            # the screen; a few go in as markup. Both readings are audited, so neither sink can drop a claim.
            literal = node.replace("\n", " ").strip()
            rendered = html_runs(node).replace("\n", " ").strip()
            out.append(literal)
            if rendered and rendered != literal:
                out.append(rendered)
    walk(doc)
    return "\n".join("| " + t for t in out if t)

def read_copy(fname):
    """The demo copy as a READER meets it: JavaScript through its literals and comments, HTML after tags and entities,
    JSON after JSON.parse, CSS through its generated content, Markdown as it is."""
    raw = (DEMO / fname).read_text("utf-8")
    if fname.endswith(".js"):
        return extract_js_prose(raw)
    if fname.endswith(".html"):
        return html_runs(raw)
    if fname.endswith(".json"):
        return extract_json_prose(raw)
    if fname.endswith(".css"):
        return extract_css_prose(raw)
    return raw

def regulated_sentences(text, fname="<text>"):
    """Yield (line, sentence) for every sentence that touches this project. The test is `regulated`: shape, completion
    language or a named artefact. No tense, adverb, participle or clause structure is consulted anywhere here."""
    for start_line, block in md_blocks(strip_markdown(text)):
        for raw in re.split(r"(?<=[.;:])\s+", block):
            sent = " ".join(raw.split())
            if sent and regulated(sent):
                yield start_line, sent

def derive_licences(sent):
    """The licence spans a PENDING row must carry: one frame match per completion token. None when a completion token
    is inside no frame, which is what makes "The operator created the service accounts as expected." and "No reviewer
    knew okf-setup created the service accounts." impossible to register as PENDING rather than merely discouraged."""
    frames = [(m.start(), m.end(), m.group(0)) for rx in LICENCE_FRAMES for m in rx.finditer(sent)]
    spans = []
    for m in COMPLETION_VERB.finditer(sent):
        cover = [f for f in frames if f[0] <= m.start() and m.end() <= f[1]]
        if not cover:
            return None
        span = min(cover, key=lambda f: f[1] - f[0])[2]
        if span not in spans:
            spans.append(span)
    for m in COMPLETION_PHRASE.finditer(sent):
        # A fixed claim phrase ("… on tape", "the tape shows") is an adjunct or a present-tense shape, not a past
        # verb, so no frame can hold it: its licence is the nearest qualifier before it. This is the WEAKER of the two
        # rules and the one place a qualifier still licenses by position; it is bounded by the EXECUTED list, which is
        # hand-written, and every PAST verb in the same sentence must still be framed.
        quals = list(QUALIFIER.finditer(sent[:m.start()]))
        if not quals:
            return None
        span = sent[quals[-1].start():m.end()]
        if span not in spans:
            spans.append(span)
    return spans

def licence_problems(sent, licences):
    """Every completion token must sit inside a recorded span, and every span must be a licence frame the checker
    recognises (or, for a claim phrase, a qualifier reaching it with no complementizer between). A qualifier that
    follows its verb, or one that belongs to another clause, therefore licenses nothing."""
    out, spans = [], []
    for lic in licences:
        at = sent.find(lic)
        if at < 0:
            out.append("licence %r is not a substring of the sentence" % lic[:40])
            continue
        if not any(rx.fullmatch(lic) for rx in LICENCE_FRAMES) and not (
                QUALIFIER.match(lic) and COMPLETION_PHRASE.search(lic)):
            out.append("licence %r is not a licence frame" % lic[:40])
            continue
        spans.append((at, at + len(lic)))
    for rx in (COMPLETION_VERB, COMPLETION_PHRASE):
        for m in rx.finditer(sent):
            if not any(a <= m.start() and m.end() <= b for a, b in spans):
                out.append("completion %r sits outside every licence frame" % m.group(0)[:30])
    return out

def _stems(text):
    """Four-character stems of the words in a piece of text, camelCase and snake_case split apart, so "attributed"
    and "beat6_attribution.json" meet at "attr" and "EntryGroup" meets "catalog_entry_group_iam"."""
    text = re.sub(r"(?<=[a-z0-9])(?=[A-Z])", " ", text)
    return {w[:4] for w in re.findall(r"[a-z0-9]{4,}", text.lower())}

def anchor_problems(sent, paths):
    """A CAPTURED row says THIS capture did it, so the sentence must be tied to the capture: it names the operator, or
    it shares a word with the evidence it cites - the file's name or what is inside it. "The IAM bootstrap succeeded."
    is tied to nothing and cannot take this verdict whatever file it points at."""
    if re.search(r"\boperator\b|raincoatrun|\bcaptured\b|\bon record\b", sent, re.I):
        return []
    here = _stems(sent)
    for rel in paths:
        full = DEMO / rel
        if here & _stems(re.sub(r"\.\w+$", "", rel)):
            return []
        try:
            if here & _stems(full.read_text("utf-8", errors="replace")[:400000]):
                return []
        except OSError:
            continue
    return ["CAPTURED names neither the operator nor anything its evidence is about"]

def evidence_problems(paths):
    out = []
    if not paths:
        out.append("CAPTURED needs at least one evidence file")
    for rel in paths:
        try:
            full = (DEMO / rel).resolve()
        except OSError:
            out.append("evidence %r cannot be resolved" % rel)
            continue
        if not any(full == root or root in full.parents for root in EVIDENCE_ROOTS):
            out.append("evidence %r resolves outside live/ and sql/" % rel)   # live/../../index.html is not evidence
        elif not full.is_file():
            out.append("evidence %r is not a file" % rel)
    return out

def containment_problems(sent):
    """A CAPTURED sentence may name a deferred artefact only inside a disclaimer frame that sits ON that artefact:
    "(not okf-setup) ran the DDL" is captured work, while "No unrelated query ran, and the service accounts were
    created." is not - its negation belongs to another clause, and no window can tell the difference."""
    out = []
    for m in DEFERRED_ARTEFACT.finditer(sent):
        if not DISCLAIMER_FRAME.search(sent[:m.start()]):
            out.append("names %r without a disclaimer on it" % m.group(0)[:30])
    return out

def distance_problems(sent):
    """NOT_PHASE_A says the completion language here is not about deferred Phase A work. The test is naming, not
    distance: a sentence that names a deferred artefact at all cannot take this verdict, so padding between the
    artefact and the verb buys nothing."""
    m = DEFERRED_ARTEFACT.search(sent)
    return ["NOT_PHASE_A names %r" % m.group(0)[:30]] if m else []

def load_register():
    """verdict, source file, evidence, licence spans and sentence per row; malformed rows are errors, never skipped."""
    rows, problems = {}, []
    for i, ln in enumerate(REGISTER.read_text("utf-8").split("\n"), 1):
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) != 5:
            problems.append("line %d: expected verdict/file/evidence/licence/sentence, got %d fields" % (i, len(parts)))
            continue
        verdict, fname, evidence, licence, sentence = (x.strip() for x in parts)
        sentence = " ".join(sentence.split())
        if verdict not in VERDICTS:
            problems.append("line %d: unknown verdict %r (expected one of %s)" % (i, verdict, ", ".join(VERDICTS)))
            continue
        if fname not in SCAN_FILES:
            problems.append("line %d: %r is not a scanned file" % (i, fname))
            continue
        key = (fname, sentence)
        if key in rows:
            problems.append("line %d: duplicate row for %s / %r" % (i, fname, sentence[:50]))
            continue
        rows[key] = (verdict,
                     [x.strip() for x in evidence.split(",") if x.strip() and x.strip() != "-"],
                     [x for x in licence.split("~") if x and x != "-"],
                     i)
    return rows, problems

register, reg_problems = load_register()
check(not reg_problems, "tools/audited_claims.tsv parses: verdict / file / evidence / licence / sentence per row\n      " + "\n      ".join(reg_problems[:8]))

unregistered, seen = [], set()
for fname in SCAN_FILES:
    for line, sent in regulated_sentences(read_copy(fname), fname):
        seen.add((fname, sent))
        if (fname, sent) not in register:
            unregistered.append("%s:%d: %s" % (fname, line, sent[:110]))

check("def extract_js_prose(" in open(str(HERE / "check_full_demo.py"), encoding="utf-8").read() and not extract_js_prose("function current() { return roles; }").strip(),
      "app.js is scanned through its string literals and comments only: executable code carries no prose")
check(not unregistered,
      "INV-1: every sentence touching this project is audited under its own file in tools/audited_claims.tsv; these are not:\n      "
      + "\n      ".join(unregistered[:12]) + ("\n      (+%d more)" % (len(unregistered) - 12) if len(unregistered) > 12 else ""))

bad = []
for (fname, sent), (verdict, evidence, licences, i) in sorted(register.items(), key=lambda kv: kv[1][3]):
    where = "line %d (%s)" % (i, fname)
    if verdict == "CAPTURED":
        bad += ["INV-2 %s: %s" % (where, m) for m in evidence_problems(evidence)]
        bad += ["INV-3 %s: %s" % (where, m) for m in containment_problems(sent)]
        bad += ["INV-2 %s: %s" % (where, m) for m in anchor_problems(sent, evidence)]
        if licences:
            bad.append("INV-3 %s: a CAPTURED row states what happened, so it carries no licence span" % where)
    elif verdict == "NOT_PHASE_A":
        bad += ["INV-3 %s: %s" % (where, m) for m in distance_problems(sent)]
        if evidence or licences:
            bad.append("INV-3 %s: NOT_PHASE_A states nothing about Phase A, so it carries no evidence or licence span" % where)
    else:
        if evidence:
            bad.append("INV-4 %s: a PENDING row cites evidence" % where)
        bad += ["INV-4 %s: %s" % (where, m) for m in licence_problems(sent, licences)]
        bad += ["INV-4 %s: %s" % (where, m) for m in postposed_problems(sent)]
check(not bad, "every register row is bound to its claim (licence spans open with a qualifier and cover every completion token; CAPTURED evidence resolves inside live//sql/ and disclaims what it names):\n      " + "\n      ".join(bad[:12]) + ("\n      (+%d more)" % (len(bad) - 12) if len(bad) > 12 else ""))

# ---- INV-6: every file the viewer loads is either audited copy or a pinned capture --------------------------------
MANIFEST = HERE / "live_manifest.tsv"
viewer = viewer_files()
reached, unresolved = dependency_graph()
check(not unresolved, "every reference in the dependency graph resolves to a file:\n      " + "\n      ".join(unresolved[:8]))
check(len(viewer) >= 40 and all((DEMO / f).is_file() for f in viewer),
      "the inventory is every file under live/ and sql/ plus everything the dependency graph reaches (%d found)" % len(viewer))
copy_like = [f for f in reached if f.endswith((".css", ".html", ".js", ".md")) and f not in SCAN_FILES]
check(not copy_like,
      "every stylesheet, page and script the graph reaches is audited copy - a pin would fix its bytes without ever "
      "reading what it prints. Bring it into this directory and add it to SCAN_FILES, or stop fetching it: %s" % copy_like[:4])
pinned = {}
manifest_problems = []
for i, ln in enumerate(MANIFEST.read_text("utf-8").split("\n"), 1):
    if not ln.strip() or ln.lstrip().startswith("#"):
        continue
    parts = ln.split("\t")
    if len(parts) != 2:
        manifest_problems.append("line %d: expected sha256<TAB>path" % i)
        continue
    pinned[parts[1].strip()] = parts[0].strip()
for f in viewer:
    if f in SCAN_FILES:
        continue                                      # audited sentence by sentence instead
    if f not in pinned:
        manifest_problems.append("%s is fetched by the viewer and is neither audited copy nor a pinned capture" % f)
    elif hashlib.sha256((DEMO / f).read_bytes()).hexdigest() != pinned[f]:
        manifest_problems.append("%s does not match its pinned hash" % f)
for f in sorted(pinned):
    if f not in viewer:
        manifest_problems.append("%s is pinned but the viewer does not fetch it" % f)
check(not manifest_problems,
      "INV-6: every capture the viewer renders is pinned byte for byte in tools/live_manifest.tsv:\n      "
      + "\n      ".join(manifest_problems[:10]))

stale = [k for k in register if k not in seen]
check(not stale, "INV-5: no register row survives the prose it audited, in the file it audited it in (%d stale):\n      " % len(stale) + "\n      ".join("%s: %s" % (f, t[:100]) for f, t in stale[:8]))

# ---- in-memory fixtures ------------------------------------------------------------------------------------------
def regulated_in(text):
    """The sentences the gate would demand an audit for. JavaScript fragments go through the same reader app.js does."""
    src = extract_js_prose(text) if text.lstrip().startswith(("function ", "var ", "const ", "//")) else text
    return [s for _, s in regulated_sentences(src)]

# Prose that must never ship unaudited. Each is a sentence some review round produced as a bypass: an unlisted
# irregular past, a noun / verb homograph, a comparative adverb, an artefact nobody had listed. None of that matters -
# the sentence touches this project, so it is regulated on sight.
NEG = ["Phase A was executed; every binding call is made and recorded on tape.",
       "The operator created the three Phase A service accounts.",
       "Check 6 returned PERMISSION_DENIED on tape.",
       "THE OPERATOR CREATED THE SERVICE ACCOUNTS.",
       "The operator created the service accounts as expected.",
       "The docs must report the operator froze on tape.",
       "The docs must report the Phase A operator quit on tape.",
       "The sync stamped okf-context-runtime and advanced deployment_heads.",                          # r21 Codex 1
       "The IAM bootstrap completed successfully.",                                                    # r21 Codex 1
       "okf-context sync committed successfully.",                                                     # r21 Codex 1
       "BQ_COMMITTED happened.",                                                                       # r21 Codex 1
       "Without a tape, the operator created the service accounts."]
check(all(regulated_in(t) for t in NEG),
      "INV-1 regulates every claim fixture, whatever its verb morphology or artefact: %s" % [t[:50] for t in NEG if not regulated_in(t)])

# Honest prose a reviewer must be able to write and audit. Each was a false positive of the old parser; under INV-4
# they are clean because a qualifier opens the span that covers the completion token.
POS = ["The operator must record the service account binding on tape.",
       "The operator must better record every binding on tape.",
       "The operator must create the service accounts and much better record every binding on tape.",
       "Project grants widely known to reviewers are Phase A requirements.",
       "Project grants narrowly constrained only by policy are Phase A requirements.",
       "The operator must record the Phase A cache hit on tape.",
       "In Phase A the operator must make every binding on tape (not yet run).",
       "No Phase A service account was created.",
       "The three service accounts were not created; they are deferred.",
       "Every Phase A role must be created and granted on tape.",
       "Not yet run: the operator must create EntryGroup okf-rfc-demo-boundary."]
unlicensed = [(s, licence_problems(s, derive_licences(s) or [])) for t in POS for s in regulated_in(t)]
check(not [x for x in unlicensed if x[1]], "INV-4 licenses honest prose from a qualifier that opens before the verb: %s" % [x for x in unlicensed if x[1]][:2])

# A qualifier that follows its verb licenses nothing, so these cannot be registered PENDING at all.
UNLICENSABLE = ["The operator created the service accounts as expected.",
                "The operator granted the custom role as planned.",
                "Phase A was executed; every binding call is made and recorded on tape."]
check(all(derive_licences(t) is None for t in UNLICENSABLE),
      "a sentence whose completion language has no qualifier before it cannot be registered PENDING: %s" % [t[:50] for t in UNLICENSABLE if derive_licences(t) is not None])

# ---- extraction: what the reader sees must reach the gate ---------------------------------------------------------
# These are the load-bearing fixtures. A claim that extraction drops is never regulated, so every one asserts that a
# visible claim survives, and that genuinely hidden text does not surface.
VISIBLE = [
    ("member access is division, not a regex",
     "var q = holder.if(ready) / '/' / 2;\nvar c = 'The operator created the Phase A service accounts.';"),
    ("member access with spaces around the dot",
     "var q = holder . if(ready) / '/' / 2;\nvar c = 'The operator created the Phase A service accounts.';"),
    ("postfix ++ leaves a value, so the next slash divides",
     "var x = 1; x++ / '/' / 2;\nvar c = 'The operator created the Phase A service accounts.';"),
    ("postfix -- likewise",
     "var x = 1; x-- / '/' / 2;\nvar c = 'The operator created the Phase A service accounts.';"),
    ("a regex after a nested condition does not desynchronise",
     "var r = function () { if (((ready))) /'/.test(x); };\nvar c = 'The operator created the Phase A service accounts.';"),
    ("a long condition has no lookback ceiling",
     "var r = function () { if (%s) /'/.test(x); };\nvar c = 'The operator created the Phase A service accounts.';"
     % " && ".join("flag%02d" % i for i in range(1, 26))),
    ("a custom property is not a display declaration",
     'var h = "<span style=\'--x:display:none\'>The operator created the Phase A service accounts.</span>";'),
    ("title=\"hidden\" is an attribute value, not the hidden attribute",
     'var h = "<span title=\'hidden\'>The operator created the Phase A service accounts.</span>";'),
    ("data-hidden=\"false\" is a visible element",
     'var h = "<span data-hidden=\'false\'>The operator created the Phase A service accounts.</span>";'),
    ("aria-hidden hides from the accessibility tree, not from the screen",
     'var h = "<span aria-hidden=\'true\'>The operator created the Phase A service accounts.</span>";'),
    ("the last display declaration wins when neither is important",
     'var h = "<span style=\'display:none; display:inline\'>The operator created the Phase A service accounts.</span>";'),
    ("a tag inside an HTML comment does not open an element",
     'var h = "<span hidden><!-- <span> --></span> The operator created the Phase A service accounts.";'),
]
CLAIM = "created the Phase A service accounts"
missed = [why for why, src in VISIBLE if not any(CLAIM in t for t in regulated_in(src))]
check(not missed, "every visible claim survives extraction and reaches the gate: %s" % missed)
check(any("service accounts were created" in t for t in regulated_in(extract_css_prose('body::after { content: "Note; The Phase A service accounts were created."; }'))),
      "a stylesheet that prints prose is copy, semicolons and all: generated content reaches the gate")
check(any("service accounts were created" in t for t in regulated_in(extract_css_prose('body::after { content/**/: "The Phase A service accounts were created."; }'))),
      "a comment between the property and its colon is removed the way a browser removes it")
check(any("service accounts were created" in t for t in regulated_in(extract_css_prose('body::after { co\\6e tent: "The Phase A service accounts were created."; }'))),
      "a CSS identifier escape spells the same property: co\\6e tent is content")
check(any("service accounts were created" in t for t in regulated_in(extract_css_prose('body::after { content: "The Phase A service " "accounts were created."; }'))),
      "adjacent strings in one content value are concatenated the way a browser concatenates them")
check(any("service accounts were created" in t for t in regulated_in(extract_css_prose(r'body::after { content: "\"The Phase A service accounts were created."; }'))),
      "an escaped quote inside a CSS string is a character, not a delimiter")
check(any("service accounts were created" in t for t in regulated_in(extract_css_prose('body::after { content: "The Phase A service accounts \\\n were created."; }'))),
      "a CSS line continuation vanishes the way a browser drops it, so the claim stays one run")
check(any("service accounts were created" in t for t in regulated_in(html_runs('<input type="button" value="The Phase A service accounts were created.">'))),
      "copy a browser shows from an attribute - a button label, an alt text, a tooltip - is audited like element text")
check(all(postposed_problems(t) and distance_problems(t) and anchor_problems(t, ["live/bq_jobs_identity.json"])
          for t in ("The IAM bootstrap SUCCEEDED.", "The IAM bootstrap effort succeeded.", "The IAM bootstrap succeeded.",
                    "The IAM bootstrap has succeeded.", "The IAM bootstrap in staging succeeded.",
                    "The IAM bootstrap succeeded yesterday.")),
      "a verb predicated of a spec-declared deferred piece is refused by all three verdicts - through an auxiliary chain, a prepositional phrase or an adverbial tail")
check(not postposed_problems("The human operator must impersonate each service account through an isolated gcloud configuration."),
      "an attributive participle inside a prepositional phrase is not a predicate")
check("UNMODELLED" in extract_css_prose('body::after { content: attr(data-nothing-uses-this); }'),
      "generated content this reader cannot resolve is reported for audit, not silently dropped")
check(any("service accounts were created" in t for t in regulated_in(extract_json_prose('{"status": "<span hidden>The Phase A service accounts were created.</span>"}'))),
      "JSON values are audited as esc() renders them - literal text - as well as as markup, so neither sink can drop a claim")
check(any("service accounts were created" in t for t in regulated_in(extract_json_prose('{"status": "BQ\\u005fCOMMITTED: the service accounts were created."}'))),
      "JSON is audited as the viewer renders it, after JSON.parse, so an escape cannot hide a claim")

HIDDEN = [
    ("the hidden attribute", 'var h = "<span hidden>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("an unquoted style attribute", 'var h = "<span style=display:none>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("!important beats a later normal declaration", 'var h = "<span style=\'display:none!important;display:inline\'>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("same-tag nesting is balanced", 'var h = "<span hidden><span>x</span> The operator created the Phase A service accounts.</span> Nothing else here.";'),
]
shown = [why for why, src in HIDDEN if any(CLAIM in t for t in regulated_in(src))]
check(not shown, "text the browser does not render never reaches the gate: %s" % shown)

check("Nothing in §1.3 has been executed on PR 16" in spec, "spec.md §1.3 opens with the not-executed scope note")
check("Status on 2026-09-03 (PR 16): none of this section has run" in arch, "ARCHITECTURE.md sync-leg prose carries the not-run scope note")
plan_md = (DEMO / "plan.md").read_text("utf-8")
check("Status on 2026-09-03 (PR 16)" in plan_md and "Phase A has not started" in plan_md, "plan.md carries a status note that Phase A has not started")

# ---- mutation fixture: a clean copy with a known bad edit must make this checker exit non-zero -----------------
if not __import__("os").environ.get("CHECK_FULL_DEMO_NO_MUTATION"):
    try:
        out = subprocess.run([sys.executable, str(HERE / "mutation_fixture.py")], capture_output=True, text=True, timeout=600)
        check(out.returncode == 0, "tools/mutation_fixture.py: every mutated copy fails and the clean copy passes\n      " + out.stdout.strip().replace("\n", "\n      ") + out.stderr.strip())
    except (subprocess.TimeoutExpired, FileNotFoundError) as e:
        check(False, "tools/mutation_fixture.py could not run: %s" % e)

# ---- wiring ---------------------------------------------------------------------------------------
check('href="./full-demo/"' in (RFC / "index.html").read_text("utf-8"), "rfc/index.html Prototype callout links ./full-demo/")
for f in ["styles.css", "app.js", "matrix.json", "stories.json", "live/README.md"]:
    check((DEMO / f).exists(), "%s exists" % f)
try:
    subprocess.run(["node", "--check", str(DEMO / "app.js")], check=True, capture_output=True)
    check(True, "node --check app.js")
except (subprocess.CalledProcessError, FileNotFoundError) as e:
    check(False, "node --check app.js: %s" % e)

print()
if failures:
    print("%d check(s) failed" % len(failures))
    sys.exit(1)
print("all checks passed")
