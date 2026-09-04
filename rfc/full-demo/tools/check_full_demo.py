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
# Past / perfect verbs count as executed language only when the same clause names a Phase A object (either side).
# ---- executed predicates: an audited form table, not a generator (Codex round 10) ---------------------------------
# lemma -> (past/participle forms, simple-present 3sg form). Written out and audited: a generator produced "denyed" /
# "denys" and dropped the "run" participle. Adding a verb means adding one audited row here.
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
LEMMAS = set(VERB_FORMS)
PAST_FORMS = sorted({f for past, _ in VERB_FORMS.values() for f in past if f not in AMBIGUOUS_PARTICIPLE})
PRESENT_FORMS = sorted({pres for _, pres in VERB_FORMS.values()})
# An object head: a determiner / quantifier / possessive, a Titlecase word ("Phase"), or a Phase A object. ALL-CAPS
# identifiers (IAM, PERMISSION_DENIED) are not object heads, so "BigQuery grants use table-level IAM" reads as a noun.
AUX_WORDS = r"was|were|is|are|be|been|being|has|have|had|having|does|do|did"
AUX = r"(?:" + AUX_WORDS + r")"
# ---- noun / verb disambiguation for our own action lemmas (Codex round 12) ---------------------------------------
# "grant(s)" is both an action and a noun in this corpus. The signals are structural, in this order:
#   * immediately preceded by a determiner, quantifier, possessive or a hyphenated / compound modifier → noun
#     ("Every grant below …", "the table-level grants", "nine dataEditor grants");
#   * immediately followed by another verb → the candidate was the subject noun ("BigQuery grants use …",
#     "The table grant named …"). RELATIONAL lists the ordinary verbs that show up in this position; it disambiguates
#     a noun reading only, so a miss here can only make the scanner more permissive on one ambiguous word, never on
#     the past-tense forms that carry the actual execution claims;
#   * followed by nothing (clause end / punctuation) → noun, since these verbs are transitive here.
# Otherwise the candidate is a verb, with no vocabulary list of allowed objects or modifiers.
DETERMINER = r"(?:the|a|an|this|that|these|those|every|each|all|its|their|our|his|her|my|your|any|some|no|one|two|three|nine|both|such|many|few)"
PREPOSITION = r"at|in|on|of|for|by|with|from|into|per|via|under|over|during|through|across|between|within|without|about|as|than|below|above|beside|beyond|behind|beneath"
RELATIONAL = (r"use[sd]?|appl(?:y|ies|ied)|cover(?:s|ed)?|includ(?:e|es|ed)|name[sd]?|hold[s]?|held|need(?:s|ed)?|remain(?:s|ed)?|govern(?:s|ed)?|"
              r"describ(?:e|es|ed)|explain(?:s|ed)?|report(?:s|ed)?|say[s]?|said|show[s]?|showed|mean[s]?|meant|allow(?:s|ed)?|"
              r"give[s]?|gave|take[s]?|took|keep[s]?|kept|work(?:s|ed)?|stay(?:s|ed)?|answer(?:s|ed)?|succeed(?:s|ed)?|"
              r"fail(?:s|ed)?|happen(?:s|ed)?|exist(?:s|ed)?|carr(?:y|ies|ied)|sit[s]?|live[s]?|come[s]?|go(?:es)?|went")
MODAL_WORDS = r"must|will|would|shall|should|can|could|may|might"
# A finite verb of ANY kind, used to decide whether a subordinating word opens a clause or is a determiner /
# preposition. Deliberately broad (auxiliaries, modals, our own forms, ordinary verbs, any -ed word): a false hit here
# only makes the scanner stricter.
GENERAL_FINITE = re.compile(r"\b(?:" + AUX_WORDS + r"|" + MODAL_WORDS + r"|" + "|".join(PAST_FORMS + PRESENT_FORMS) + r"|" + RELATIONAL + r")\b", re.I)
# ---- token-level embedded-clause detection (Codex / Kimi round 15) ------------------------------------------------
# The question "does this span contain a claim of its own?" is answered from token adjacency, not from a list of verbs.
# A clause needs a SUBJECT next to its verb, so the signal is a noun immediately followed by a verb slot. A verb slot is
#   * an auxiliary ("operators were …", "the operator was …"), or
#   * the token right before a new determiner-headed noun phrase ("the operator audited THE bindings",
#     "reviewers audit THE service accounts") — the new determiner closes the previous phrase, so what precedes it is a
#     verb, whatever its spelling; unlisted, irregular and simple-present verbs are all caught, or
#   * the last token of the span when it is verb-shaped ("and record the operator succeeded" + predicate).
# A determiner that follows a preposition opens that preposition's object, not a new clause, so "service account in the
# Phase A project" is not one. A verb preceded by a coordinator shares the earlier subject ("… and record the binding"),
# so it is not a clause either. Noun compounds ("the Phase A binding") never reach a verb slot.
TOKEN = re.compile(r"[A-Za-z][\w'’./-]*|[^\sA-Za-z]")
def _word_set(pattern):
    """The alternatives of a plain alternation pattern, without its (?: … ) wrapper."""
    return {w for w in re.split(r"\|", pattern.strip()) if re.fullmatch(r"[a-z]+", w.strip("(?:)"))} | \
           {w.strip("(?:)") for w in re.split(r"\|", pattern.strip()) if re.fullmatch(r"[a-z]+", w.strip("(?:)"))}
DET_SET = _word_set(DETERMINER)
PREP_SET = _word_set(PREPOSITION) | {"to"}
CONJ_SET = {"and", "or", "but", "then", "nor", "plus"}
AUX_SET = _word_set(AUX_WORDS) | _word_set(MODAL_WORDS)
VERB_SHAPED = re.compile(r"(?-i:[a-z]+ed)$|^(?:" + "|".join(PAST_FORMS + PRESENT_FORMS) + r")$", re.I)

def _kind(tok):
    low = tok.lower()
    if not tok[0].isalpha():
        return "PUNCT"
    if len(tok) == 1 and tok.isupper():
        return "WORD"                                 # "Phase A binding": a lone capital is part of a name, not "a"
    if low in DET_SET:
        return "DET"
    if low in PREP_SET:
        return "PREP"
    if low in CONJ_SET:
        return "CONJ"
    if low in AUX_SET:
        return "AUX"
    if re.fullmatch(r"(?-i:[a-z]+ly)", tok):
        return "ADV"
    return "WORD"

def contains_finite_clause(span):
    """True when the span holds a subject-predicate structure of its own."""
    toks = [(t, _kind(t)) for t in TOKEN.findall(span)]
    for i, (tok, kind) in enumerate(toks):
        prev = toks[i - 1] if i else None
        if not prev or prev[1] not in ("WORD", "DET"):
            continue                                  # a verb needs a subject noun or quantifier before it
        if prev[1] == "DET" and kind != "WORD":
            continue
        if kind == "AUX":
            return True                               # "operators were …", "the operator was …"
        if kind == "WORD":
            nxt = toks[i + 1] if i + 1 < len(toks) else None
            if nxt and nxt[1] == "DET":
                return True                           # "… audited THE bindings", "… audit THE service accounts"
            if nxt is None and VERB_SHAPED.search(tok):
                return True                           # "… the operator succeeded" | predicate
            # noun verb noun: "reviewer knew okf-setup", where the third noun is the next clause's subject. The verb
            # must be lowercase, so a name compound ("Phase A project", "the Phase A binding") is not one.
            before_subject = toks[i - 2] if i >= 2 else None
            if (nxt and nxt[1] == "WORD" and tok[:1].islower()
                    and (before_subject is None or before_subject[1] != "WORD")):
                return True                           # the subject starts its phrase, so this is not a name compound
    return False
NOUN_BEFORE = re.compile(r"(?:" + DETERMINER + r"|[a-z]+-[a-z-]+|[A-Za-z]+)\s*$", re.I)
# A preposition takes a noun-phrase complement, so a bare form right after one is a noun ("at run time", "on record").
PREP_BEFORE = re.compile(r"\b(?:" + PREPOSITION + r")\s+$", re.I)
# What follows decides transitivity: a finite verb needs an object noun phrase after it. A preposition, an -ly adverb,
# a modal, an auxiliary, another verb or punctuation means the candidate was the head of a noun phrase instead
# ("the project grant to one permission", "the wider grant honestly", "its impersonation grant must be revoked").
NONOBJECT_AFTER = re.compile(r"^\s+(?:(?:to|" + PREPOSITION + r"|" + MODAL_WORDS + r"|" + AUX_WORDS + r"|" + RELATIONAL + r"|" +
                             "|".join(PAST_FORMS + PRESENT_FORMS) + r")\b)|^\s*[)\],.;:|]", re.I)

ADVERB = r"(?-i:[a-z]+ly)|very|more|most|quite|fairly|only|just|even|also|then|now|still|already|first|again"
OBJECT_HEAD_TOKEN = re.compile(r"^\s+(?:" + DETERMINER + r"\b|(?-i:[A-Z][a-z]+)\b|" + PHASE_A_OBJECT.pattern + r")", re.I)
ADJECTIVE_TOKEN = re.compile(r"^\s+(?!(?:" + PREPOSITION + r"|to|" + MODAL_WORDS + r"|" + AUX_WORDS + r"|" + RELATIONAL + r"|" +
                             "|".join(PAST_FORMS + PRESENT_FORMS) + r")\b)(?-i:[a-z][\w-]*)", re.I)

# A subject noun phrase before the candidate, in three ordinary shapes. A bare Titlecase noun with nothing between it
# and the candidate is NOT one: "Project grants" and "BigQuery grants" are compound nouns, while "The operator grants",
# "Check 6 returns" and clause-initial "Both grant" are subject + verb.
PRONOUN = r"it|they|we|he|she|one|someone|everyone|nobody|somebody"
DET_PLUS_WORD = re.compile(r"\b(?:" + DETERMINER + r")\b(?:\s+[\w'’-]+)+\s*$", re.I)
TITLE_PLUS_WORD = re.compile(r"(?-i:\b[A-Z][a-z]+\b)(?:\s+[\w'’-]+)+\s*$")
BARE_PRONOUN_SUBJECT = re.compile(r"^\W*(?:" + DETERMINER + r"|" + PRONOUN + r")\s*$", re.I)

def has_subject(before):
    """Any content word before the candidate can be its subject — a determiner-headed phrase, a bare plural
    ("Operators grant …"), an identifier ("okf-setup returns …") or a pronoun. A clause-initial candidate shares the
    subject of the clause it continues. What separates a noun reading from a verb reading is therefore what FOLLOWS,
    not the shape of the subject."""
    return True
ADVERB_THEN_END = re.compile(r"^(?:\s+(?:" + ADVERB + r"))+\s*(?:[)\],.;:|]|$)", re.I)

def reads_as_noun(cl, m):
    """True when an ambiguous base / 3sg form heads a noun phrase rather than being a finite verb. The decision is
    about the shape of the subject and of what follows, with no scan ceiling and no list of allowed objects:
      * a preposition before it ("at run time") → noun;
      * nothing after it, a verb / modal / preposition / punctuation after it, or only an adverb then the end
        ("Every grant below names …", "the wider grant honestly.") → nothing for a transitive verb to take → noun;
      * no subject noun phrase before it ("Project grants govern …", "BigQuery grants use …") → the candidate is part
        of a bare compound noun phrase → noun.
    Otherwise it is a verb, so "The operator grants access to the custom role" and "Both grant temporary Phase A roles"
    are claims."""
    before, after = cl[:m.start()], cl[m.end():]
    if PREP_BEFORE.search(before):
        return True
    if not re.match(r"^\s+\S", after):             # nothing follows: these verbs are transitive here
        return True
    if NONOBJECT_AFTER.match(after) or ADVERB_THEN_END.match(after):
        return True
    return not has_subject(before)

PAST_VERB = re.compile(r"\b(" + "|".join(PAST_FORMS) + r")\b|\b(?:was|were|is|are|been|be|has|have|had)\s+(?:not\s+|already\s+)?(?:" + "|".join(AMBIGUOUS_PARTICIPLE) + r")\b", re.I)
PRESENT_VERB = re.compile(r"\b(" + "|".join(PRESENT_FORMS) + r")\b", re.I)
BASE_VERB = re.compile(r"\b(" + "|".join(sorted(LEMMAS)) + r")\b")   # lowercase only: "Run"/"Create" are proper nouns or imperatives
FINITE_FORM = re.compile(r"\b(" + "|".join(PAST_FORMS + PRESENT_FORMS) + r")\b", re.I)

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
# LIGHT tokens may stand between a governor and the predicate it governs without breaking the government: auxiliaries,
# our own participles, coordinators, "to", and adverbs. Anything else is a content word — typically a new subject or an
# embedded verb — and ends the modal's / status marker's reach over a finite verb.
LIGHT = re.compile(r"^(?:\W|\b(?:" + AUX_WORDS + r"|" + "|".join(PAST_FORMS + PRESENT_FORMS + AMBIGUOUS_PARTICIPLE) +
                   r"|and|or|to|not|never|also|already|then|still|now|only|just|even|afterwards|again|always)\b|\b(?-i:[a-z]+ly)\b)*$", re.I)
# Factive complementizers assert the content of the clause they open, so they end a qualifier's reach; whether / if are
# non-factive and leave the embedded claim unasserted, so they license the binding instead of breaking it.
FACTIVE_OPENER = re.compile(r"\b(that|which|who|whom|whose|where|how|why|what|when)\b", re.I)
NONFACTIVE_OPENER = re.compile(r"\b(whether|if)\b", re.I)
RESET_ALWAYS = re.compile(r"^(but|while|whereas|although|though|however|because|so|\|)$", re.I)
RESET_IF_FINITE = re.compile(r"^(then|and then|after|before|until|when|once)$", re.I)

def governed_by(cl, start):
    """True when a modal or infinitive "to" immediately governs the form at `start` (only LIGHT tokens in between):
    "must create", "to be exercised". "must report the operators grant" does NOT govern "grant"."""
    for rx in (MODAL, re.compile(r"\bto\b", re.I)):
        for m in rx.finditer(cl[:start]):
            if LIGHT.match(cl[m.end():start]):
                return True
    return False

def base_is_finite(cl, start):
    """A bare lemma is a finite base-present verb when nothing governs it as an infinitive and a subject stands before
    it in the clause. No allowlist of subject words: any preceding content token counts."""
    if governed_by(cl, start):
        return False
    return bool(re.search(r"[A-Za-z]", cl[:start]))

def executed_preds(cl):
    """Return (offset, kind) for EVERY executed predicate. kind "verb" is a finite past / present / base form (it takes a
    subject, so an intervening subject means a different clause); kind "phrase" is a fixed phrase such as "on tape"."""
    found = {}
    for rx in EXECUTED:
        for m in rx.finditer(cl):
            found.setdefault(m.start(), "phrase")
    if PHASE_A_OBJECT.search(cl):
        for m in PAST_VERB.finditer(cl):
            found[m.start()] = "verb"
        for m in PRESENT_VERB.finditer(cl):
            if not reads_as_noun(cl, m):
                found[m.start()] = "verb"
        for m in BASE_VERB.finditer(cl):
            if not reads_as_noun(cl, m) and base_is_finite(cl, m.start()):
                found[m.start()] = "verb"
    return sorted(found.items())

# ---- structural binding (Codex rounds 9–12), fail-closed ---------------------------------------------------------
# One token that can head a subject noun phrase: a determiner, pronoun, possessive or Titlecase word. ALL-CAPS and
# snake_case identifiers are not subject heads.
SUBJECT_TOKEN = re.compile(r"\b(the|a|an|this|that|these|those|every|each|all|its|their|our|his|her|my|your|it|they|we|he|she|one|someone|everyone|nobody|somebody)\b|(?-i:\b[A-Z][a-z]+\b)")
SUBJECT_OPENER = re.compile(r"(the|a|an|this|that|these|those|every|each|all|its|their|our|his|her|my|your|it|they|we|he|she|one|someone|everyone|nobody|somebody|who|which)|[A-Z][a-z]+")
LEADING_FUNCTION = re.compile(r"^(?:\W+|\b(?:as|so|then|also|already|now|still|indeed|only|just|even)\b\s*)*", re.I)
VERB_PHRASE_TAIL = r"(?:\s*(?:,|\band\b|\bor\b)?\s+(?:" + AUX_WORDS + r"|" + "|".join(PAST_FORMS + PRESENT_FORMS + AMBIGUOUS_PARTICIPLE) + r"|not|already|then|also))+\s*(?:,|\band\b|\bor\b)?\s*$"
TRAILING_AUX = re.compile(VERB_PHRASE_TAIL, re.I)

def opens_finite_clause(span):
    """True when a factive complementizer in the span is followed by a clause of its own, so it is a complementizer
    rather than a determiner: "say that the operator created …", "explain why an operator audited …" break the
    binding, while "record that scoped Phase A binding on tape" does not."""
    m = FACTIVE_OPENER.search(span)
    return bool(m and contains_finite_clause(span[m.end():]))

def phrase_bound(cl, qual_end, pred_start, kind="phrase"):
    """True when the qualifier governs this predicate. Fail-closed:
      * a non-factive complement (whether / if) leaves the embedded claim unasserted, so the qualifier does govern it;
      * a factive complementizer introducing a finite clause always ends the reach;
      * a VERB predicate takes a subject, so ONLY LIGHT tokens may stand between a modal / status marker and it —
        any content word is a new subject or an embedded verb ("must report okf-setup created …");
      * a NEGATION may sit on the subject of a passive ("no service account was created"), so it only requires that no
        other finite predicate intervene;
      * a PHRASE predicate has no subject, so content words are fine as long as the span does not start a new subject."""
    if qual_end > pred_start:
        return False
    span = cl[qual_end:pred_start]
    if NONFACTIVE_OPENER.search(span):
        return True
    if opens_finite_clause(span):
        return False
    # A verb predicate owns the auxiliary chain that leads into it ("no service account WAS created"), so that chain is
    # stripped before the span is judged. A phrase predicate ("on tape") owns no auxiliary, so "report operators WERE
    # on tape" keeps its "were" and reads as the embedded claim it is.
    core = TRAILING_AUX.sub(" ", span) if kind == "verb" else span
    if FINITE_FORM.search(TRAILING_AUX.sub(" ", span)):
        return False
    if contains_finite_clause(core):
        return False
    if kind == "verb":
        return bool(LIGHT.match(TRAILING_AUX.sub(" ", span)))
    rest = LEADING_FUNCTION.sub("", span, count=1)
    first = re.match(r"^(\S+)", rest)
    return not (first and SUBJECT_OPENER.fullmatch(first.group(1).strip(",.;:()\"'")))

def phrase_bound_negation(cl, qual_end, pred_start, kind="phrase"):
    """A negation may sit on the subject of the predicate it negates ("no service account was created"), so unlike a
    modal it tolerates that one noun phrase. It does NOT reach across a further subject: in "No one realizes the
    operator created …", "the operator" is a second subject, so the negation governs "realizes", not "created"."""
    if qual_end > pred_start:
        return False
    span = cl[qual_end:pred_start]
    if NONFACTIVE_OPENER.search(span):
        return True
    if opens_finite_clause(span):
        return False
    core = TRAILING_AUX.sub(" ", span)
    if FINITE_FORM.search(core):
        return False
    return not contains_finite_clause(core)     # a clause of its own between them means the negation governs that one

def nearest_before(rx, cl, pred_start):
    """The governing qualifier is the NEAREST one before the predicate; a farther one cannot reach over a nearer one
    that fails to bind ("As a future requirement it is true that the operator created …")."""
    ms = [m for m in rx.finditer(cl) if m.start() < pred_start]
    return ms[-1] if ms else None

def negation_bound(cl, pred_start, kind):
    m = nearest_before(NEGATION, cl, pred_start)
    return bool(m and phrase_bound_negation(cl, m.end(), pred_start, kind))

def modal_before(cl, pred_start, kind):
    """A modal governs the predicate when the predicate sits inside the modal span ("to be revoked") or when the modal
    heads the predicate's phrase."""
    if any(m.start() <= pred_start < m.end() for m in MODAL.finditer(cl)):
        return True
    m = nearest_before(MODAL, cl, pred_start)
    return bool(m and phrase_bound(cl, m.end(), pred_start, kind))

def status_before(cl, pred_start, kind):
    m = nearest_before(STATUS, cl, pred_start)
    return bool(m and phrase_bound(cl, m.end(), pred_start, kind))

PASSIVE_FRAME = re.compile(r"\b(be|been|being)\b", re.I)

def participle_continuation(cl):
    """A clause headed by a past participle continues a passive modal frame ("must be created and granted on tape")."""
    m = re.match(r"^\W*([\w'’\-]+)", cl)
    return bool(m and m.group(1).strip(",.;:()\"'").lower() in {f.lower() for f in PAST_FORMS})

ADVERBIAL_SKIP = re.compile(r"^\W*(?:(?-i:[a-z][\w'’-]*)\s+)?", re.I)

def bare_verb_continuation(cl):
    """POSITIVE recognition, fail-closed: a coordinated clause inherits an earlier modal only when it is a shared-subject
    continuation headed by a bare lemma ("… and revoke the custom role"). A clause with its own subject, an adjunct, or a
    finite verb inherits nothing. "run" is both lemma and participle, so it is treated as finite."""
    for tok in _head_candidates(cl):
        if tok in {f.lower() for f in PAST_FORMS} or tok in {f.lower() for f in PRESENT_FORMS}:
            return False                              # "and revoked …" / "and commits …" is a claim, not a continuation
        if tok in DET_SET or tok in PREP_SET or tok in CONJ_SET or tok in AUX_SET:
            return False                              # "and the operator …" opens its own subject
        if tok in LEMMAS:
            return True
    return False

def _head_candidates(cl, limit=3):
    """The first few word tokens of a clause. A continuation may be introduced by any adverbial ("always record …",
    "carefully record …"), so the head verb is looked for among the first tokens rather than after a list of adverbs."""
    return [t.lower().strip(",.;:()\"'") for t in TOKEN.findall(cl) if t[0].isalpha()][:limit]

PAST_SET = {f.lower() for f in PAST_FORMS}

def continuation_head_end(cl):
    """Offset just past the verb that heads an inherited continuation: a bare lemma ("… and always revoke the role") or,
    under a passive modal frame, a participle ("must be created and granted on tape")."""
    for m in re.finditer(r"[A-Za-z][\w'’-]*", cl):
        if m.group(0).lower() in LEMMAS or m.group(0).lower() in PAST_SET:
            return m.end()
    return 0

def inherit_bound(cl, pred_start, kind):
    """An inherited modal governs the continuation's own head verb and whatever that head verb takes as its complement,
    but not a predicate belonging to an embedded clause. The head verb is part of the inherited verb phrase, so the span
    is measured after it: "and record every binding on tape" inherits over "on tape"; "and record that the operator
    created …" does not inherit over "created", because a new subject stands before it."""
    head_end = continuation_head_end(cl)
    if pred_start < head_end:
        return True
    span = cl[head_end:pred_start]
    if opens_finite_clause(span):
        return False
    core = TRAILING_AUX.sub(" ", span)
    if FINITE_FORM.search(core):
        return False
    if kind == "verb":
        return bool(LIGHT.match(core))
    return not contains_finite_clause(core)     # "and record the operator succeeded on tape" is not inherited

def opens_own_claim(cl):
    """A clause introduced by a temporal / sequential connector resets an earlier modal only when it makes a claim of its
    own — it has a finite verb or an executed predicate. "create one service account after another" does not."""
    return bool(GENERAL_FINITE.search(cl) or executed_preds(cl))

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

REGEX_PRECEDER = re.compile(r"(?:^|[(,=:\[!&|?{};+\-*%~^]|\b(?:return|typeof|instanceof|in|of|new|delete|void|case|do|else)\b)\s*$")

def _js_pieces(src):
    """Walk a JavaScript source and yield (line, kind, text) for every string literal and comment. Handles escapes,
    template literals and regular-expression literals, so a regex containing a quote (app.js has several) can no longer
    shift the quoting state and spill executable code into the scanned prose."""
    i, n, line = 0, len(src), 1
    while i < n:
        ch = src[i]
        if ch == "\n":
            line += 1
            i += 1
            continue
        if ch in "'\"`":
            quote, start_line, buf = ch, line, []
            i += 1
            while i < n and src[i] != quote:
                if src[i] == "\\":
                    i += 2
                    continue
                if src[i] == "\n":
                    line += 1
                buf.append(src[i])
                i += 1
            i += 1
            yield start_line, "lit", "".join(buf)
            continue
        if src.startswith("//", i):
            j = src.find("\n", i)
            j = n if j < 0 else j
            yield line, "com", src[i + 2:j]
            i = j
            continue
        if src.startswith("/*", i):
            j = src.find("*/", i)
            j = n if j < 0 else j + 2
            body = src[i + 2:max(i + 2, j - 2)]
            yield line, "com", body.replace("\n", " ")
            line += body.count("\n")
            i = j
            continue
        if ch == "/" and REGEX_PRECEDER.search(src[max(0, i - 40):i]):
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
            continue
        i += 1

def extract_js_prose(src):
    """Return only the prose of a JavaScript source: string-literal text and comment text. Executable code never
    appears, so `function current() { return roles; }` is not read as a sentence. Every piece is emitted as its own
    Markdown block (leading "|"), so a comment can never qualify a claim in a neighbouring literal. Consecutive
    literals within two source lines are joined, because the page renders them as one run of text — a claim split
    across concatenated literals is still a claim."""
    lines = [""] * (src.count("\n") + 2)
    run_start, run_end = None, None
    for line, kind, text in _js_pieces(src):
        text = html_runs(text).strip()
        if not text or (kind == "lit" and not re.search(r"\s", text)):
            continue                                  # one-word literals are keys, class names and labels, not prose
        if kind == "lit" and run_start is not None and line - run_end <= 2:
            lines[run_start] = (lines[run_start] + " " + text).strip()
            run_end = line
            continue
        target = min(line, len(lines) - 1)
        lines[target] = (lines[target] + " | " + text).strip() if lines[target] else "| " + text
        if kind == "lit":
            run_start, run_end = target, line
        else:
            run_start, run_end = None, None
    return "\n".join(lines)

# An HTML tag ends a text run: the words on either side of it belong to different elements, so they are different
# clauses. "|" is already the hard clause boundary the scanner uses for Markdown table cells.
BLOCK_TAG = re.compile(r"</?(?:div|p|li|ul|ol|tr|td|th|table|section|article|header|footer|nav|details|summary|pre|blockquote|h[1-6]|br|dl|dt|dd|form|figure)\b[^>]*>", re.I)
INLINE_TAG = re.compile(r"</?[a-zA-Z][^>]*>")

def html_runs(text):
    """Block-level tags separate text runs; inline tags are removed so a phrase the reader sees as one
    ("The service <strong>accounts</strong> were created") stays one clause."""
    return INLINE_TAG.sub("", BLOCK_TAG.sub(" | ", text))

def strip_markdown(text):
    """Collapse inline code to one opaque token, then remove emphasis markers (*, stray backticks, and _ at word
    edges). Identifier underscores survive, so PERMISSION_DENIED and agent_events stay intact."""
    text = INLINE_CODE.sub(lambda m: _code_span(m.group(0).strip("`")), text)
    text = re.sub(r"[*`]", "", text)
    return re.sub(r"(?<![A-Za-z0-9])_+|_+(?![A-Za-z0-9])", "", text)

CONNECTOR_WORDS = r"and then|while|whereas|but|although|though|however|and|or|then|after|before|until|when|because|so|once"
CONNECTOR = re.compile(r"\s*\|\s*|,\s*(?:\b(" + CONNECTOR_WORDS + r")\b\s+)?|\s+\b(" + CONNECTOR_WORDS + r")\b\s+", re.I)

def clauses(sentence):
    """Split one sentence into (connector, clause) pairs; connector is the token that introduced the clause ('' for the first)."""
    out, pos, conn = [], 0, ""
    for m in CONNECTOR.finditer(sentence):
        piece = sentence[pos:m.start()]
        if piece.strip():
            out.append((conn, piece))
        tok = (m.group(1) or m.group(2) or "").strip()
        conn = tok.lower() if tok else ("|" if "|" in m.group(0) else ",")
        pos = m.end()
    tail = sentence[pos:]
    if tail.strip():
        out.append((conn, tail))
    return out

def scan_executed(text, fname="<text>"):
    """Return offending predicates: every executed predicate must be governed by a preceding modal (own clause or latched
    from a coordinated earlier clause), a status marker in its own clause, or a negation bound to that predicate."""
    out = []
    for start_line, block in md_blocks(strip_markdown(text)):
        for sent in re.split(r"(?<=[.;:])\s+", block):
            latch = passive = False
            for conn, cl in clauses(sent):
                preds = executed_preds(cl)
                continues = bare_verb_continuation(cl) or (passive and participle_continuation(cl))
                if RESET_ALWAYS.match(conn) or (RESET_IF_FINITE.match(conn) and not continues and opens_own_claim(cl)):
                    latch = passive = False
                    continues = False
                continued = latch and conn != "" and continues
                for pred, kind in preds:
                    # An inherited modal governs only the predicates it actually reaches from the head of this clause:
                    # "… and record that the operator created …" inherits over "record", never over the embedded "created".
                    inherits = continued and inherit_bound(cl, pred, kind)
                    ok = (inherits or modal_before(cl, pred, kind) or status_before(cl, pred, kind)
                          or negation_bound(cl, pred, kind))
                    if not ok:
                        out.append("%s:%d: %s" % (fname, start_line, cl.strip()[:130]))
                        break
                if MODAL.search(cl):
                    latch = True
                    passive = bool(PASSIVE_FRAME.search(cl[MODAL.search(cl).end():]))
    return out

offenders = []
for fname in SCAN_FILES:
    raw = (DEMO / fname).read_text("utf-8")
    if fname.endswith(".js"):
        raw = extract_js_prose(raw)
    elif fname.endswith(".html"):
        raw = html_runs(raw)
    offenders += scan_executed(raw, fname)
check("def extract_js_prose(" in open(str(HERE / "check_full_demo.py"), encoding="utf-8").read() and not extract_js_prose("function current() { return roles; }").strip(),
      "app.js is scanned through its string literals and comments only: executable code carries no prose")
check(not offenders, "no clause narrates deferred Phase A (SA create/revoke, bindings on tape, denials proved, outcomes demonstrated, PERMISSION_DENIED returned) as executed without a future / not-done / RFC-text-only qualifier in that clause or an earlier clause of the same sentence:\n      " + "\n      ".join(offenders[:12]))
# in-memory negative fixtures: the scan itself must catch each of these
def scan_fixture(t):
    """JavaScript fixtures go through the same extractor the scan uses for app.js."""
    return scan_executed(extract_js_prose(t) if t.lstrip().startswith(("function ", "var ", "//")) else t)
NEG = ["Phase A was executed; every binding call is made and recorded on tape.",
       "The operator created the service accounts and every binding was recorded on tape under the okf-setup identity.",
       "Check 6 returned PERMISSION_DENIED on tape.",
       "Phase A: the tape shows the impersonated user_email after each step.",
       "The operator created the three Phase A service accounts.",
       "Every binding was recorded on tape, while future documentation is planned.",
       "The operator has revoked every okf-setup role and has proved the denials on tape.",
       "- Every binding was recorded on tape.\n- Future work: the rest is planned.",
       "Every binding was recorded on tape.\n\nThe rest is future work.",
       "## Status\nAll seven negative checks returned PERMISSION_DENIED on tape.\n\nPhase A is future work.",
       "No DML touched agent_events, and the three Phase A service accounts were created.",
       "The operator made every Phase A binding.",
       "Check 6 returned PERMISSION_DENIED.",
       "It is not a secret that the denials were proved on tape.",
       "Without a tape, the operator created the service accounts.",
       "THE OPERATOR CREATED THE SERVICE ACCOUNTS.",
       "Phase A is not blocked; the custom role okfCatalogSearch was granted at project level.",
       "The operator created the service accounts as expected.",                                    # r7: modal after the verb
       "Future documentation is planned, then the operator created the three service accounts.",   # r7: 'then' resets scope
       "The service account was not created after the operator granted the custom role.",          # r7: negation bound to its own predicate
       "The operator granted the custom role, as planned.",                                         # r7 cousin: trailing status in another clause
       "The SAs will be created; the operator revoked the setup roles.",                            # r7 cousin: semicolon boundary
       "Nothing was executed before the operator created the service accounts.",                    # r7 cousin: 'before' resets
       "The operator must create the SAs, but the denials were proved on tape.",                    # r7 cousin: 'but' resets the modal
       "The operator will record the tape after the service accounts were created.",                 # r7 cousin: 'after' resets
       "The operator granted the custom role as planned.",                                           # r8: status after the predicate, no comma
       "The documentation will explain the RFC, and the operator created the Phase A service accounts.",  # r8: finite new claim after ', and'
       "The operator will record the tape once the service accounts were created.",                  # r8: 'once' resets
       "The operator must document the RFC and the service accounts were created by the operator.",  # r8 cousin: finite passive after 'and'
       "The operator granted the custom role (RFC text only).",                                      # r8 cousin: trailing status label
       "Deferred documentation aside, the operator created the service accounts.",                   # r8 cousin: status in an earlier clause
       "The docs must describe the workflow, and the operator creates the three Phase A service accounts.",  # r9: simple present after ', and'
       "The plan must document the workflow, and the operator makes every binding.",                 # r9: simple present 'makes'
       "As planned the operator created the Phase A service accounts.",                              # r9: status describes manner, subject intervenes
       "The docs must describe the workflow, and the operator responsible for the Phase A bootstrap in the demo project on 2026-09-03 created the three service accounts.",  # r9: long subject, no ceiling
       "The tape will be recorded, and Codex verified that the operator granted the custom role.",   # r9 cousin: proper-noun subject
       "Not yet documented, the operator created the service accounts.",                             # r9 cousin: status in a fronted clause
       "As a future requirement it is true that the operator created the service accounts.",         # r9 cousin: status then new subject
       "The docs must say that the operator created the three Phase A service accounts.",             # r10 Codex: subordinate clause after the modal
       "The docs must be updated after service accounts were created.",                               # r10 Codex: temporal adjunct clause
       "Check 6 denied the request with PERMISSION_DENIED.",                                          # r10 Codex: past inflection (denied, not denyed)
       "The operator grants temporary Phase A roles.",                                                # r10 Codex: present with a modifier before the object
       "The operator will create the service accounts and revoked the custom role.",                  # r10 Kimi: verb-initial finite past inherits nothing
       "The sync writer must validate the bundle and committed it on tape.",                          # r10 Kimi: verb-initial finite past, on tape
       "The plan must document the workflow, and okf-setup created the service accounts.",            # r10 cousin: identifier subject
       "In the demo project the operator created the service accounts.",                              # r10 cousin: leading adjunct
       "The tape must show the switch, and the denials were proved.",                                 # r10 cousin: finite passive after coordination
       "The okf-setup roles have been revoked.",                                                      # r10 cousin: perfect passive
       "The operator will document the plan and denies every Phase A grant.",                         # r10 cousin: present form after coordination
       "The setup job has run on tape.",                                                              # r10 cousin: ambiguous participle after an auxiliary
       "The docs must be updated because service accounts were created.",                             # r10 cousin: causal reset
       "The docs must explain how the operator created the Phase A service accounts.",                # r11 Codex: wh-complement
       "The docs must report the operator created the Phase A service accounts.",                     # r11 Codex: null complement
       "The operator will record the tape once Phase A has been executed.",                           # r11 Codex: unconditional temporal boundary
       "The operators grant temporary Phase A roles.",                                                # r11 Codex: finite base-present, plural subject
       "The operator grants very narrowly scoped temporary Phase A roles.",                           # r11 Codex: no modifier ceiling
       "The tape will show how the operator created the service accounts.",                           # r11 Kimi: how
       "The docs must explain why the operator granted the custom role.",                             # r11 cousin: why
       "The tape will show the operator granted the custom role.",                                    # r11 cousin: null complement after show
       "The report must record what the operator revoked on tape.",                                   # r11 cousin: what
       "The docs must report okf-setup created the service accounts.",                                # r12 Codex: identifier subject, null complement
       "The docs must report service accounts were created.",                                         # r12 Codex: bare plural subject
       "The docs must explain why all IAM calls succeeded on tape.",                                   # r12 Codex: factive why over a phrase predicate
       "The planned service account was created.",                                                    # r12 Codex: status modifies the subject, not the predicate
       "The operator grants narrow Phase A roles.",                                                   # r12 Codex: plain adjective, no modifier vocabulary
       "The operators grant new Phase A roles.",                                                      # r12 Codex: base-present, plain adjective
       "The docs must report the operators grant temporary Phase A roles.",                           # r12 Codex: embedded base-present under an earlier modal
       "The docs must report `okf-setup` created the service accounts.",                              # r12 cousin: subject written as inline code
       "The docs must explain the RFC and record that the operator created the service accounts.",    # r13 Codex: inheritance must be per predicate
       "No one realizes the operator created the service accounts.",                                  # r13 Codex: negation must not cross a second subject
       "Check 6 returns PERMISSION_DENIED.",                                                          # r13 Codex: "return" is an audited action lemma
       "All seven positive checks returned OK.",                                                      # r13 Codex: past "returned"
       "The operator grants narrowly scoped temporary Phase A roles.",                                # r13 Codex: -ly adverb is not proof of a noun
       "Both grant temporary Phase A roles.",                                                         # r13 Codex: a quantifier subject is not proof of a noun
       "The operator granted the `custom role` at project scope.",                                    # r13 Codex: multiword inline code
       "The docs must explain why an operator audited the Phase A service accounts on tape.",         # r14 Codex: unlisted finite in a complement
       "The docs must explain the RFC and record the operator succeeded on tape.",                    # r14 Codex: embedded clause under an inherited modal
       "No reviewer realized okf-setup created the service accounts.",                                # r14 Codex: negation across an embedded clause
       "The operator grants access to the custom role.",                                              # r14 Codex: bare-noun object
       "All positive checks return success.",                                                         # r14 Codex: base-present with a bare object
       "The operator grants alpha beta gamma delta epsilon zeta eta theta iota kappa lambda mu Phase A roles.",                                                       # r14 Codex: no modifier ceiling
       "The operator granted the `custom role (okfCatalogSearch)` at project scope.",                 # r14 Codex: inline code with punctuation
       "The docs must explain the operator audited the bindings on tape.",                            # r15 Kimi: null complement, unlisted -ed verb
       "The docs must report operators were on tape.",                                                # r15 Codex: null-complement phrase claim
       "The planned operator was on tape.",                                                           # r15 Codex: status modifies the subject of a phrase claim
       "The docs must explain why reviewers audit the service accounts on tape.",                     # r15 Codex: unlisted present verb
       "No reviewer knew okf-setup created the service accounts.",                                    # r15 Codex: irregular past in the span
       "Operators grant temporary Phase A roles.",                                                    # r15 Codex: bare plural subject
       "okf-setup returns PERMISSION_DENIED.",                                                        # r15 Codex: identifier subject
       "The operator granted the `custom role = okfCatalogSearch` at project scope."]                 # r15 Codex: inline code with an equals sign keeps the object
POS = ["In Phase A the operator must make every binding on tape (not yet run).",
       "Each call is expected to return PERMISSION_DENIED; none has been run.",
       "The legacy handle was bound to two publications before Phase A.",
       "The operator must create the service accounts, record every binding on tape, and revoke them afterwards.",
       "No service account was created for this capture; the three SAs are the Phase A follow-up.",
       "The three service accounts were **not** created; they are deferred.",
       "Nothing in §1.3 has been executed on PR 16.",
       "No `PERMISSION_DENIED` check was recorded; the three service accounts were not created.",
       "The operator must create the service accounts and record every binding on tape.",
       "Each check is expected to return PERMISSION_DENIED (not yet run).",
       "Runtime tables were created and seeded by the operator, not yet by the Phase A service accounts.",
       "Phase A requirement, not yet run: the operator must create the SAs and record every binding on tape.",
       "The operator must create the SAs, then record every binding on tape, and revoke the roles afterwards.",
       "RFC text only: the sync writer stamped every entry after BQ_COMMITTED.",
       "The operator must create the SAs and revoke every role on tape afterwards.",
       "Not yet run: the operator must create EntryGroup okf-rfc-demo-boundary, then record every binding on tape.",
       "No PERMISSION_DENIED check was recorded and no service account was created.",
       "The Cloud Run Job will run as the sync writer.",
       "The operator must run the DDL jobs and record every binding on tape.",
       "Every grant below names the resource it is bound to.",
       "BigQuery grants use table-level IAM so the sync writer never touches agent_events.",
       "Every Phase A role must be created and granted on tape.",
       "The operator must record that Phase A binding on tape.",
       "BigQuery grants use the table-level IAM policy for the custom role.",
       "The table grant named the custom role.",
       "The operator must verify whether the service accounts were created.",
       "The operator must create one service account after another and record every binding on tape.",
       "The custom role limits the project grant to one permission.",
       "At run time the operator keeps only the impersonation grant.",
       "The operator must eventually create the Phase A service accounts.",
       "Project grants govern access to the custom role.",
       "The operator must record that scoped Phase A binding on tape.",
       "The docs must explain the RFC and record every binding on tape.",
       "No Phase A service account was created.",
       "Project grants govern Phase A access to the custom role.",
       "The operator must create the service accounts and carefully record every binding on tape.",
       "function current() { return roles; }",
       "The operator must be recorded on tape.",
       "The docs must explain the RFC and record the Phase A binding on tape.",
       "The docs must explain the RFC and record the previously scoped Phase A binding on tape.",
       "No service account in the Phase A project was created.",
       "The project grants govern Phase A access to the custom role.",
       "The operator must create the service accounts and always record every binding on tape."]
check(all(scan_fixture(t) for t in NEG), "scan flags every negative fixture (active past, perfect, after-verb status/modal, finite claims after coordination, once/then/after resets, block boundaries, bare Phase A, unbound negation, case, identifiers): %s" % [t[:50] for t in NEG if not scan_executed(t)])
check(not any(scan_fixture(t) for t in POS), "scan accepts preceding modals latched over nonfinite coordination, preceding status markers, bound negations and legacy data facts: %s" % [scan_fixture(t) for t in POS if scan_fixture(t)])
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
