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
for name, text in (("index.html", index), ("stories.json", (DEMO / "stories.json").read_text("utf-8")), ("app.js", app)):
    check("twelve times" not in text, "%s does not claim the verbatim sentence was said twelve times" % name)
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
shown = {}
for f in LIVE.glob("bq_job_*.json"):   # `bq show -j` snapshots for jobs INFORMATION_SCHEMA had not surfaced yet
    d = json.loads(f.read_text("utf-8"))
    shown[d["jobReference"]["jobId"]] = d["user_email"]
known = {j["job_id"] for j in jobs} | set(shown)
check(jobids <= known, "every *.jobid is in bq_jobs_identity.json or a bq_job_*.json show snapshot: missing %s" % sorted(jobids - known))
check(all(u == jobs[0]["user_email"] for u in shown.values()), "every bq show -j snapshot carries the same operator user_email")

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
