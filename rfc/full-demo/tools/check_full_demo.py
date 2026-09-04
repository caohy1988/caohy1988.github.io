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
import json
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

# ---- executed-language scan (Codex rounds 3–5): deferred Phase A must read as future / not done / RFC text only ----
# Block → sentence → clause. Markdown structure is preserved: a heading, list item, table row, blockquote line or blank
# line starts a new block, and only indented/plain continuation lines join the block above, so a qualifier in a later
# list item or paragraph never covers an earlier clause. Inside a sentence a qualifier governs its own clause and the
# clauses that FOLLOW it (a modal such as "must" scopes forward over coordination); a trailing qualifier does not reach
# back over an earlier executed clause ("… was recorded on tape, while future work is planned" fails). The bare words
# "Phase A" qualify nothing. Markdown emphasis and backticks are stripped before matching so "**not** created" reads as
# "not created".
PHASE_A_OBJECT = r"\b(service accounts?|SAs?|bindings?|binding calls?|grants?|roles?|okf-setup|okf-sync-writer(-okf-rfc-demo)?|okf-runtime-reader|okfCatalogSearch|custom role|Token Creator|boundary(-probe)?|denials?|negative checks?|checks? [1-7]|PERMISSION_DENIED|(the|Phase A|on) tape|impersonation|user_email)\b"
# A past-tense / perfect verb counts as executed language only when the same clause names a Phase A object
# (either side of the verb): "the operator created the three service accounts", "the service accounts were created",
# "has revoked every okf-setup role". "Runtime tables were created by the operator" names no Phase A object and passes.
PAST_VERB = r"\b(created|revoked|granted|installed|recorded|exercised|proved|demonstrated|deleted|executed|ran|denied)\b"
EXECUTED = [r"recorded on tape", r"on tape under", r"\bon tape\b", r"\bthe tape shows\b", r"\bthe tape demonstrates\b",
            r"\bdemonstrated, not asserted\b", r"\b(is|was|were|are|been) demonstrated\b", r"\bprove[sd]? (the|that|it)\b", r"\bdenial checks prove\b",
            r"\bmakes every binding\b", r"\bevery binding call is made\b", r"\bcreates? the (three )?service accounts\b", r"\b(are|were|was|is|been) revoked\b",
            r"\beach (binding )?command (is |was )?recorded\b", r"\b(is|are|was|were|been) recorded (on|in) the tape\b", r"returned `?PERMISSION_DENIED",
            r"\bran as `?okf-(setup|sync-writer|runtime-reader)", r"\bexercised once on tape\b", r"\bimpersonated `?user_email`? (from|after)\b",
            r"\bidentity is demonstrated\b", r"\bshows? the impersonated\b",
            r"\b(was|were|is|are) denied\b", r"\bPERMISSION_DENIED\b[^.;]*\bon tape\b",
            r"\bPhase A (was|has been|is) (executed|done|complete|completed|run|recorded)\b"]

def executed_clause(cl):
    return any(re.search(rx, cl) for rx in EXECUTED) or (re.search(PAST_VERB, cl) and re.search(PHASE_A_OBJECT, cl))
QUALIFIER = [r"\bmust\b", r"\bwill\b", r"\bwould\b", r"\bshall\b", r"\bto be (recorded|run|exercised|made|created|revoked|deleted|granted)\b", r"\bexpected\b",
             r"\bnot yet\b", r"\bNOT yet\b", r"\bnot done\b", r"\bNot done\b", r"\bnot run\b", r"\bnot started\b", r"\bnot created\b", r"\bnot built\b", r"\bNot built\b",
             r"\bnone (of|was|were|has|have)\b", r"\bno (such )?tape\b", r"\b[Nn]othing\b", r"RFC text only", r"\bfuture\b", r"\bdeferred\b", r"\bplanned\b",
             r"\bhas not run\b", r"\bnone happened\b", r"\bneither happened\b", r"\bprior\b", r"\bnever\b", r"\bdoes not exist\b", r"\brequirement\b",
             r"\bacceptance criterion\b", r"\bnot (been )?executed\b", r"\bnot met\b", r"\b[Nn]ot\b", r"\b[Nn]o\b", r"\bcannot\b", r"\bwithout\b", r"\brequires?\b"]
SCAN_FILES = ["spec.md", "ARCHITECTURE.md", "plan.md", "intent.md", "CUSTOMER_STORIES.md", "README.md", "live/README.md", "index.html", "app.js", "stories.json", "matrix.json"]
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

def clauses(sentence):
    """Split one sentence into clauses at commas and subordinating/coordinating connectors."""
    return [c for c in re.split(r",\s+|\s+\b(?:while|whereas|but|although|though|however|yet|and then|then)\b\s+", sentence) if c and c.strip()]

def scan_executed(text, fname="<text>"):
    """Return offending clauses: executed-language whose clause (or an earlier clause of the same sentence) carries no qualifier."""
    out = []
    plain = re.sub(r"[*_`]", "", text)
    for start_line, block in md_blocks(plain):
        for sent in re.split(r"(?<=[.;:])\s+", block):
            qualified_so_far = False
            for cl in clauses(sent):
                if any(re.search(rx, cl) for rx in QUALIFIER):
                    qualified_so_far = True
                if executed_clause(cl) and not qualified_so_far:
                    out.append("%s:%d: %s" % (fname, start_line, cl.strip()[:130]))
    return out

offenders = []
for fname in SCAN_FILES:
    offenders += scan_executed((DEMO / fname).read_text("utf-8"), fname)
check(not offenders, "no clause narrates deferred Phase A (SA create/revoke, bindings on tape, denials proved, outcomes demonstrated, PERMISSION_DENIED returned) as executed without a future / not-done / RFC-text-only qualifier in that clause or an earlier clause of the same sentence:\n      " + "\n      ".join(offenders[:12]))
# in-memory negative fixtures: the scan itself must catch each of these
NEG = ["Phase A was executed; every binding call is made and recorded on tape.",
       "The operator created the service accounts and every binding was recorded on tape under the okf-setup identity.",
       "Check 6 returned PERMISSION_DENIED on tape.",
       "Phase A: the tape shows the impersonated user_email after each step.",
       "The operator created the three Phase A service accounts.",                      # active past, bare Phase A
       "Every binding was recorded on tape, while future documentation is planned.",     # trailing qualifier must not reach back
       "The operator has revoked every okf-setup role and has proved the denials on tape.",  # perfect forms
       "- Every binding was recorded on tape.\n- Future work: the rest is planned.",       # list boundary
       "Every binding was recorded on tape.\n\nThe rest is future work.",                 # paragraph boundary
       "## Status\nAll seven negative checks returned PERMISSION_DENIED on tape.\n\nPhase A is future work."]
POS = ["In Phase A the operator must make every binding on tape (not yet run).",
       "Each call is expected to return PERMISSION_DENIED; none has been run.",
       "The legacy handle was bound to two publications before Phase A.",
       "The operator must create the service accounts, bind every role on tape, and revoke them afterwards.",  # modal scopes forward
       "No service account was created for this capture; the three SAs are the Phase A follow-up.",
       "The three service accounts were **not** created; they are deferred."]
check(all(scan_executed(t) for t in NEG), "scan flags every negative fixture (active past, perfect, trailing qualifier, list and paragraph boundaries, bare 'Phase A')")
check(not any(scan_executed(t) for t in POS), "scan accepts forward-scoped modals, negations and legacy data facts")
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
