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
#   INV-1  COVERAGE.  Every sentence of the demo copy that NAMES a Phase A artefact must appear, verbatim after
#          whitespace normalisation, in tools/audited_claims.tsv. No grammar is consulted: a sentence is regulated
#          because it names one of our artefacts, full stop. New, edited or moved prose fails until it is audited,
#          whatever words it uses, so no vocabulary list can make this fail open. There is nothing here to bypass.
#   INV-2  EVIDENCE.  Every CAPTURED row cites a file under live/ or sql/ that exists in the tree.
#   INV-3  CONTAINMENT.  A CAPTURED row may not name a deferred Phase A artefact unless it also carries a not-done
#          marker, so no row can present a thing that does not exist as a thing that was done. Growing
#          DEFERRED_ARTEFACT only makes this stricter.
#   INV-4  QUALIFIED.  A PENDING row whose sentence carries completion language - a past / participle form of one of
#          the audited action verbs, or one of the EXECUTED phrases - must also carry a qualifier token. This asks
#          only that the qualifier be PRESENT in the sentence, never where it sits, so it has no parse to bypass and
#          no adverb, irregular-verb or participle vocabulary on its critical path.
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

# The qualifier vocabulary. It is used only to ask "is a qualifier present in this sentence", never to bind one to a
# predicate, so a missing word here can at most demand an audit note - it cannot license an unaudited claim.
QUALIFIER = re.compile("(?:%s)|(?:%s)|(?:%s)" % (MODAL.pattern, STATUS.pattern, NEGATION.pattern), re.I)
# Completion language: any past / participle form of the audited action verbs, or one of the EXECUTED phrases.
COMPLETION = re.compile(r"\b(?:" + "|".join(PAST_FORMS) + r")\b|" + "|".join("(?:%s)" % rx.pattern for rx in EXECUTED), re.I)
# The artefacts that do not exist on this PR. Narrower than PHASE_A_OBJECT on purpose: legacy context_ref bindings,
# BigQuery grants and user_email rows are real, so naming them is not a Phase A claim.
DEFERRED_ARTEFACT = re.compile(r"\b(service accounts?|SAs?|okf-setup|okf-sync-writer(-okf-rfc-demo)?|okf-runtime-reader|"
                               r"okfCatalogSearch|custom (search )?role|table-level grants?|boundary(-| )?probe|"
                               r"boundary EntryGroup|negative checks?|positive checks?|denial checks?|denials?|"
                               r"binding calls?|PERMISSION_DENIED|BQ_COMMITTED|CATALOG_STAMPED|Token Creator|"
                               r"impersonation|(on|the) tape)\b", re.I)
NOT_DONE = re.compile(r"\b(not|no|none|never|without|nothing|neither|yet|deferred|planned|future|prior|pending|"
                      r"requirements?|acceptance|expected|must|will|would|shall|should)\b|RFC text only", re.I)

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
    """True when the browser does not render the element: a `hidden` attribute, aria-hidden="true", or a computed
    display of none. Attributes are read as name / value pairs, so title="hidden" and data-hidden="false" are visible
    elements whose text the reader sees."""
    for m in ATTR.finditer(attrs):
        name, val = m.group(1).lower(), (m.group(2) or "").strip("\"'")
        if name == "hidden":
            return True
        if name == "aria-hidden" and val.strip().lower() == "true":
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

def html_runs(text):
    """What the reader sees. Hidden elements are dropped whole, so text the browser never renders can neither make a
    claim nor qualify one; block-level tags separate text runs; inline tags are removed so a phrase the reader sees as
    one ("The service <strong>accounts</strong> were created") stays one clause."""
    text = HTML_COMMENT.sub(" ", text)            # a comment is not rendered, and its tags open no element
    text = _drop_hidden(text)
    text = INLINE_TAG.sub("", BLOCK_TAG.sub(" | ", text))
    return re.sub(r"[ \t]{2,}", " ", text)            # removing an element must not split "service  accounts"

def strip_markdown(text):
    """Collapse inline code to one opaque token, then remove emphasis markers (*, stray backticks, and _ at word
    edges). Identifier underscores survive, so PERMISSION_DENIED and agent_events stay intact."""
    text = INLINE_CODE.sub(lambda m: _code_span(m.group(0).strip("`")), text)
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])", "", text)

# ---- the register: coverage, evidence, containment, qualification, staleness -------------------------------------
REGISTER = HERE / "audited_claims.tsv"
VERDICTS = ("PENDING", "CAPTURED")

def regulated_sentences(text, fname="<text>"):
    """Yield (line, sentence) for every sentence of the demo copy that names a Phase A artefact. The test is naming,
    not grammar: no tense, adverb, participle or clause structure is consulted anywhere in this function."""
    for start_line, block in md_blocks(strip_markdown(text)):
        for raw in re.split(r"(?<=[.;:])\s+", block):
            sent = " ".join(raw.split())
            if sent and PHASE_A_OBJECT.search(sent):
                yield start_line, sent

def load_register():
    """verdict, evidence and sentence per row; malformed rows are errors, not silently skipped."""
    rows, problems = {}, []
    for i, ln in enumerate(REGISTER.read_text("utf-8").split("\n"), 1):
        if not ln.strip() or ln.lstrip().startswith("#"):
            continue
        parts = ln.split("\t")
        if len(parts) != 3:
            problems.append("line %d: expected verdict<TAB>evidence<TAB>sentence, got %d fields" % (i, len(parts)))
            continue
        verdict, evidence, sentence = (x.strip() for x in parts)
        sentence = " ".join(sentence.split())
        if verdict not in VERDICTS:
            problems.append("line %d: unknown verdict %r (expected one of %s)" % (i, verdict, ", ".join(VERDICTS)))
            continue
        if sentence in rows:
            problems.append("line %d: duplicate row for %r" % (i, sentence[:60]))
            continue
        rows[sentence] = (verdict, evidence, i)
    return rows, problems

register, reg_problems = load_register()
check(not reg_problems, "tools/audited_claims.tsv parses: one verdict / evidence / sentence per row\n      " + "\n      ".join(reg_problems[:8]))

unregistered, seen = [], set()
for fname in SCAN_FILES:
    raw = (DEMO / fname).read_text("utf-8")
    if fname.endswith(".js"):
        raw = extract_js_prose(raw)
    elif fname.endswith(".html"):
        raw = html_runs(raw)
    for line, sent in regulated_sentences(raw, fname):
        seen.add(sent)
        if sent not in register:
            unregistered.append("%s:%d: %s" % (fname, line, sent[:110]))

check("def extract_js_prose(" in open(str(HERE / "check_full_demo.py"), encoding="utf-8").read() and not extract_js_prose("function current() { return roles; }").strip(),
      "app.js is scanned through its string literals and comments only: executable code carries no prose")
check(not unregistered,
      "INV-1: every sentence naming a Phase A artefact is audited in tools/audited_claims.tsv; these are not:\n      "
      + "\n      ".join(unregistered[:12]) + ("\n      (+%d more)" % (len(unregistered) - 12) if len(unregistered) > 12 else ""))

bad = []
for sent, (verdict, evidence, i) in sorted(register.items(), key=lambda kv: kv[1][2]):
    if verdict == "CAPTURED":
        if not re.match(r"(live|sql)/", evidence) or not (DEMO / evidence).exists():
            bad.append("INV-2 line %d: CAPTURED needs an existing live/ or sql/ file, got %r" % (i, evidence))
        if DEFERRED_ARTEFACT.search(sent) and not NOT_DONE.search(sent):
            bad.append("INV-3 line %d: CAPTURED names a deferred artefact with no not-done marker: %s" % (i, sent[:90]))
    else:
        if COMPLETION.search(sent) and not QUALIFIER.search(sent):
            bad.append("INV-4 line %d: completion language with no qualifier in the sentence: %s" % (i, sent[:90]))
check(not bad, "every register row is internally consistent (evidence exists, nothing deferred is claimed done, completion language carries a qualifier):\n      " + "\n      ".join(bad[:12]))

stale = [sent for sent in register if sent not in seen]
check(not stale, "INV-5: no register row survives the prose it audited (%d stale):\n      " % len(stale) + "\n      ".join(s[:110] for s in stale[:8]))

# ---- in-memory fixtures ------------------------------------------------------------------------------------------
def regulated(text):
    """The sentences the gate would demand an audit for. JavaScript fragments go through the same reader app.js does."""
    src = extract_js_prose(text) if text.lstrip().startswith(("function ", "var ", "const ", "//")) else text
    return [s for _, s in regulated_sentences(src)]

# Prose that must never ship unaudited. Each of these is a sentence a past review round produced as a bypass of the
# old parser: an unlisted irregular past, a subject the old subject-head guard missed, a noun / verb homograph, a
# comparative adverb. None of that matters now - they name a Phase A artefact, so they are regulated on sight.
NEG = ["Phase A was executed; every binding call is made and recorded on tape.",
       "The operator created the three Phase A service accounts.",
       "Check 6 returned PERMISSION_DENIED on tape.",
       "The operator has revoked every okf-setup role and has proved the denials on tape.",
       "THE OPERATOR CREATED THE SERVICE ACCOUNTS.",
       "The operator created the service accounts as expected.",
       "The docs must report the operator froze on tape.",                                            # r20 Codex 1
       "The docs must report the Phase A operator quit on tape.",                                     # r20 Codex 1
       "The docs must report the operator spoke softly on tape.",
       "No reviewer knew okf-setup created the service accounts.",
       "It is not a secret that the denials were proved on tape.",
       "Without a tape, the operator created the service accounts."]
check(all(regulated(t) for t in NEG),
      "INV-1 regulates every claim fixture, whatever its verb morphology: %s" % [t[:50] for t in NEG if not regulated(t)])

# Honest prose that a reviewer must be able to write and audit without the gate arguing about its grammar. Every one
# of these was a false positive of the old parser in some round; under INV-4 they are clean because the qualifier is
# simply present in the sentence.
POS = ["The operator must record the service account binding on tape.",                               # r20 Codex 1
       "The operator must better record every binding on tape.",                                      # r20 Codex 2
       "The operator must create the service accounts and much better record every binding on tape.",  # r20 Codex 2
       "Project grants widely known to reviewers are Phase A requirements.",                          # r20 Codex 3
       "Project grants narrowly constrained only by policy are Phase A requirements.",                # r20 Codex 3
       "The operator must record the Phase A cache hit on tape.",
       "The operator must often record every binding on tape.",
       "In Phase A the operator must make every binding on tape (not yet run).",
       "No Phase A service account was created.",
       "The three service accounts were not created; they are deferred.",
       "Every Phase A role must be created and granted on tape.",
       "Not yet run: the operator must create EntryGroup okf-rfc-demo-boundary."]
unqualified = [s for t in POS for s in regulated(t) if COMPLETION.search(s) and not QUALIFIER.search(s)]
check(not unqualified, "INV-4 accepts honest prose with the qualifier anywhere in the sentence: %s" % unqualified[:3])

# ---- extraction: what the reader sees must reach the gate ---------------------------------------------------------
# These are the load-bearing fixtures. A claim that extraction drops is never regulated, so every one of them asserts
# that a visible claim survives, and that genuinely hidden text does not surface.
VISIBLE = [
    ("member access is division, not a regex",
     "var q = holder.if(ready) / '/' / 2;\nvar c = 'The operator created the Phase A service accounts.';"),
    ("member access with spaces around the dot",
     "var q = holder . if(ready) / '/' / 2;\nvar c = 'The operator created the Phase A service accounts.';"),
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
    ("the last display declaration wins when neither is important",
     'var h = "<span style=\'display:none; display:inline\'>The operator created the Phase A service accounts.</span>";'),
    ("a tag inside an HTML comment does not open an element",
     'var h = "<span hidden><!-- <span> --></span> The operator created the Phase A service accounts.";'),
]
missed = [why for why, src in VISIBLE if not regulated(src)]
check(not missed, "every visible claim survives extraction and reaches the gate: %s" % missed)

HIDDEN = [
    ("the hidden attribute", 'var h = "<span hidden>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("aria-hidden=true", 'var h = "<span aria-hidden=\'true\'>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("an unquoted style attribute", 'var h = "<span style=display:none>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("!important beats a later normal declaration", 'var h = "<span style=\'display:none!important;display:inline\'>The operator created the Phase A service accounts.</span> Nothing else here.";'),
    ("same-tag nesting is balanced", 'var h = "<span hidden><span>x</span> The operator created the Phase A service accounts.</span> Nothing else here.";'),
]
shown = [why for why, src in HIDDEN if regulated(src)]
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
