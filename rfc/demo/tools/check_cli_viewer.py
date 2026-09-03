#!/usr/bin/env python3
"""Check the why-slice viewer of the BQAA → OKF path (stdlib only, read-only).

Asserts that /rfc/demo/ tells the locked story on top of the SDK CLI run on
record, and that the technical proof still holds underneath it:

* live/observe/live.json is the okf_rfc_observe_agent session
  f21ee192-d989-4c38-894f-66b6b82eaf18 with event_count 180, context_ref
  okf:env-observe#674153c572f6, model gemini-3.8-flash;
* live/observe/live_identities.json pins publication sha256:53bd1651…;
* live/observe/mapping.json binds that context_ref to that publication;
* live/observe/snapshot.json is the TRIMMED viewer snapshot (histogram sums
  to 180, samples carry the session, the 494KB export is not on disk) and
  its tool result ranks Active-customer revenue first and excludes
  Customer revenue (legacy);
* cli/okf-bqaa-cli-transcript.txt is the four-beat tape: ASK question,
  OBSERVE rank 1 / excluded legacy / UNVERIFIABLE, PUBLISH run.py +
  PUBLICATION_ID + stub titles, NEXT AGENT lookup JSON + payoff comment,
  labelled FAIL_CLOSED, and the payoff comment comes AFTER the junk ref so
  the tape (and the poster) end on the payoff;
* index.html hero is the locked question + three-sentence payoff and does
  NOT carry the SHA wall (full publication, Object.hasOwn, adapter version,
  180 badge, session id) — those live in the collapsed IDs panel;
* stepper titles are Ask / Observe / Publish / Next agent, data-beat 1..4;
* walkthrough embeds the recut mp4 with the payoff poster and one caption
  sentence per beat; okf-bqaa-e2e.mp4 stays labelled prior fixture clip;
* honesty strings survive; the prior consume session
  (okf_rfc_consume_agent / 04fa3d56-… / okf:env-demo#a25e1c0ccbca) and the
  germany fixture (sess-4c1f9a2e7b3d) are never presented as Observe /
  Publish source of truth; no "computed in-browser"; no gemini-2.5;
* app.js parses the tape the same way (hermetic node run), keeps the
  Object.hasOwn fail-closed lookup (constructor / toString / __proto__).

Usage: python3 rfc/demo/tools/check_cli_viewer.py   (exit 0 on pass)
"""
import json
import re
import shutil
import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
OBS = DEMO / "live" / "observe"
CLI = DEMO / "cli"

AGENT = "okf_rfc_observe_agent"
SESSION = "f21ee192-d989-4c38-894f-66b6b82eaf18"
TRACE = "e-c7214361-4017-43d7-af4e-cddfe51b09a4"
TABLE = "test-project-0728-467323.okf_rfc_demo.agent_events"
MODEL = "gemini-3.8-flash"
CONTEXT_REF = "okf:env-observe#674153c572f6"
OBSERVATION = "sha256:85ea62a96e5076a292572a996f0408865c4c56aac696bbeb79a73bbc5eda8af6"
SNAPSHOT = "sha256:f18befd010ff7e3d1fe140303626a82dc985c986846093f73643e7d0eea92b75"
PUBLICATION = "sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77"
ADAPTER = "okf-bqaa-adapter:v0"
EVENTS = 180
PR_URL = "https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/474"
PR_HEAD = "476d37dc9d4210a335c2f77e78003f6a5ebe2878"

CURRENT_METRIC = "Active-customer revenue"
LEGACY_METRIC = "Customer revenue (legacy)"

# Locked copy (Haiyuan, 2026-09-02).
QUESTION = "What was active-customer revenue in Germany last quarter — and can I trust the number?"
PAYOFF_SENTENCES = [
    "Without this path a finance agent can pick the superseded Customer revenue (legacy) metric, or talk as if the number is verified.",
    "A live BQAA trace ranked Active-customer revenue first, excluded the legacy metric, and recorded the receipt as unproven.",
    "Derived OKF in Knowledge Catalog is how the next agent finds that — uses the current metric, skips legacy, and reports the number as unproven.",
]
CAPTIONS = [
    "The agent is asked for Germany last-quarter revenue — and whether the number can be trusted.",
    "The live trace ranked Active-customer revenue first and excluded the superseded legacy metric; the receipt is unproven.",
    "One command turns that telemetry into derived OKF, the handle a Catalog entry would expose.",
    "The next agent looks up that handle, uses the current metric, skips legacy, and reports the number as unproven.",
]
STEP_TITLES = ["Ask", "Observe", "Publish", "Next agent"]

# Strings that may appear only as the labelled prior consume experiment / synthetic fixture.
PRIOR_CONSUME = ["okf_rfc_consume_agent", "04fa3d56-f2f1-413e-8c2b-ec116835af84", "okf:env-demo#a25e1c0ccbca"]
GERMANY = ["sess-4c1f9a2e7b3d"]
PRIOR_LABEL = re.compile(r"prior|synthetic|not this|leftover", re.I)

failures = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def note(msg):
    print("INFO " + msg)


def load(p):
    return json.loads(p.read_text("utf-8"))


def strip_tags(s):
    return re.sub(r"\s+", " ", re.sub(r"<[^>]+>", "", s)).strip()


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


# ---- committed observe inputs ---------------------------------------------
live = load(OBS / "live.json")
ident = load(OBS / "live_identities.json")
mapping = load(OBS / "mapping.json")
snap = load(OBS / "snapshot.json")

for k, want in (("agent", AGENT), ("session_id", SESSION), ("trace_id", TRACE), ("table", TABLE),
                ("model", MODEL), ("vertex_location", "global"), ("event_count", EVENTS),
                ("context_ref", CONTEXT_REF), ("receipt_context_ref", CONTEXT_REF)):
    check(live.get(k) == want, "live.json %s == %s" % (k, want))
check("nothing attested" in live.get("label", ""), "live.json label says nothing attested")

check(ident.get("observation_id") == OBSERVATION, "live_identities.json observation_id == " + OBSERVATION[:20] + "…")
check(ident.get("snapshot_id") == SNAPSHOT, "live_identities.json snapshot_id == " + SNAPSHOT[:20] + "…")
check(ident.get("publication_id") == PUBLICATION, "live_identities.json publication_id == " + PUBLICATION[:20] + "…")
inp = ident.get("inputs", {})
check(inp.get("adapter_version") == ADAPTER, "live_identities.json adapter_version == " + ADAPTER)
check(inp.get("session_id") == SESSION and inp.get("trace_id") == TRACE, "live_identities.json inputs bind session + trace")
check(inp.get("bundle_key") == "bqaa-derived-cymbal-demo", "live_identities.json bundle_key is the derived key, not cymbal-finance-core")
check(len(ident.get("file_sha256", {})) == 8, "live_identities.json lists 8 derived files")

check(mapping.get("adapter_version") == ADAPTER, "mapping.json adapter_version == " + ADAPTER)
check(mapping.get("mapping", {}).get(CONTEXT_REF) == PUBLICATION, "mapping.json binds %s → publication" % CONTEXT_REF)
check(len(mapping.get("mapping", {})) == 1, "mapping.json binds exactly one context_ref (fail closed on any other)")
check(mapping.get("source", {}).get("session_id") == SESSION, "mapping.json source session == " + SESSION)

hist = snap.get("histogram", {})
check(sum(hist.values()) == EVENTS, "snapshot.json histogram sums to %d (got %d)" % (EVENTS, sum(hist.values())))
check(snap.get("event_count") == EVENTS, "snapshot.json event_count == %d" % EVENTS)
check(snap.get("live", {}) == live, "snapshot.json live block == live.json")
check(snap.get("identities", {}).get("publication_id") == PUBLICATION, "snapshot.json identities.publication_id == pinned publication")
samples = snap.get("sample_events", [])
check(1 <= len(samples) <= 20, "snapshot.json carries a small sample (%d events), not the export" % len(samples))
check(all(e.get("session_id") == SESSION and e.get("agent") == AGENT for e in samples), "every sample event carries session %s and agent %s" % (SESSION[:8], AGENT))
tool_results = [((e.get("content") or {}).get("result") or {}) for e in samples if e.get("event_type") == "TOOL_COMPLETED"]
tool_results = [r for r in tool_results if r.get("context_ref") == CONTEXT_REF]
check(bool(tool_results), "a sample TOOL_COMPLETED result carries " + CONTEXT_REF)
okf = (tool_results[0].get("okf") if tool_results else None) or {}
items = sorted(okf.get("items", []), key=lambda it: it.get("rank", 99))
excluded = okf.get("excluded", [])
question_rows = [((e.get("content") or {}).get("text_summary") or "") for e in samples if e.get("event_type") == "USER_MESSAGE_RECEIVED"]
check(question_rows and question_rows[0] == QUESTION, "snapshot USER_MESSAGE_RECEIVED text is the locked question")
check(bool(items) and items[0].get("title") == CURRENT_METRIC and items[0].get("rank") == 1, "snapshot tool result ranks %s first" % CURRENT_METRIC)
check(any(x.get("title") == LEGACY_METRIC and "superseded" in x.get("reason", "") for x in excluded), "snapshot tool result excludes %s as superseded" % LEGACY_METRIC)
never = snap.get("never_emit", [])
content_keys = keys_deep([e.get("content") for e in samples])
viol = sorted(k for k in never if k in content_keys)
check(never and not viol, "sample content keys ∩ never-emit = ∅" + ("" if not viol else " (violations: %s)" % ", ".join(viol)))
check(snap.get("source_of_truth", {}).get("pr_url") == PR_URL and snap["source_of_truth"].get("do_not_merge_pr_474") is True,
      "snapshot.json names SDK PR 474 as the full export and says do not merge")
check(snap.get("germany_trace", {}).get("not_source_of_truth") is True, "snapshot.json labels germany trace not_source_of_truth")
check("prior" in snap.get("prior_consume_experiment", {}).get("label", "").lower(), "snapshot.json labels the consume session as prior")
check(not (OBS / "live_observe_agent_events.json").exists() and not (DEMO / "live" / "live_observe_agent_events.json").exists(),
      "the 494KB 180-row export is not committed to Pages")
for p in OBS.glob("*.json"):
    check(p.stat().st_size < 60_000, "%s stays small (%d bytes)" % (p.relative_to(DEMO), p.stat().st_size))

# ---- CLI transcript: the four-beat tape -------------------------------------------
tx = (CLI / "okf-bqaa-cli-transcript.txt").read_text("utf-8")
tx_lines = tx.splitlines()
for line in ("SESSION " + SESSION, "TRACE " + TRACE, "TABLE " + TABLE, "MODEL " + MODEL, "ADAPTER " + ADAPTER,
             "CONTEXT_REF " + CONTEXT_REF, "OBSERVATION_ID " + OBSERVATION, "SNAPSHOT_ID " + SNAPSHOT,
             "PUBLICATION_ID " + PUBLICATION, "FILES 8", "RECEIPT UNVERIFIABLE rcpt-observe-noexec"):
    check(line in tx, "transcript has: " + line[:60] + ("…" if len(line) > 60 else ""))
check(QUESTION in tx_lines, "transcript ASK beat prints the locked question as a line")
check("rank 1: " + CURRENT_METRIC in tx, "transcript OBSERVE beat: rank 1 " + CURRENT_METRIC)
check(any(l.startswith("excluded: " + LEGACY_METRIC) and "superseded" in l for l in tx_lines), "transcript OBSERVE beat: excluded %s, superseded" % LEGACY_METRIC)
check("receipt: UNVERIFIABLE" in tx, "transcript OBSERVE beat: receipt UNVERIFIABLE")
check("$ python3 examples/okf_bqaa_adapter/run.py" in tx_lines, "transcript PUBLISH beat runs the real run.py")
for t in (CURRENT_METRIC, LEGACY_METRIC, "Active-customer revenue by region and quarter", "Revenue recognition eligibility"):
    check("title: " + t in tx, "transcript PUBLISH beat lists stub title: " + t)
check("handle a Knowledge Catalog entry would expose" in tx and "did not write Catalog" in tx, "transcript PUBLISH beat says KC handle + no Catalog write")
check("run.py --lookup 'okf:env-observe#674153c572f6'" in tx, "transcript NEXT AGENT beat shows the lookup command for " + CONTEXT_REF)
check('"publication_id": "%s"' % PUBLICATION in tx and '"label": "derived/demo"' in tx, "transcript NEXT AGENT beat prints the three-key lookup JSON")
payoff_idx = [i for i, l in enumerate(tx_lines) if "Payoff:" in l]
fail_idx = [i for i, l in enumerate(tx_lines) if l.startswith("FAIL_CLOSED")]
check(payoff_idx and all(("not legacy" in tx_lines[i] and "unproven" in tx_lines[i]) for i in payoff_idx), "transcript payoff comment: use %s, not legacy; the number is unproven" % CURRENT_METRIC)
check("FAIL_CLOSED" in tx and "okf:env-junk#deadbeef" in tx and "exit 2" in tx, "transcript shows FAIL_CLOSED for the junk ref with exit 2")
check("expected FAIL_CLOSED exit 2" in tx and "not a crashed demo" in tx, "transcript labels junk-ref exit 2 as expected fail-closed, not a crash")
check(bool(payoff_idx) and bool(fail_idx) and max(payoff_idx) > max(fail_idx), "transcript ends on the payoff comment AFTER the junk-ref FAIL_CLOSED (poster = payoff, not FAIL_CLOSED)")
check(PR_HEAD in tx and "do not merge" in tx, "transcript pins PR 474 HEAD and says do not merge")
check("180 events" in tx, "transcript OBSERVE beat names 180 events (secondary fact, not the hero)")
for name in ("okf-bqaa-cli.cast", "okf-bqaa-cli.gif"):
    check((CLI / name).exists(), "cli/%s present" % name)
check((DEMO / "okf-bqaa-cli.mp4").exists(), "okf-bqaa-cli.mp4 present (recut why tape)")
check((DEMO / "okf-bqaa-cli-poster.png").exists(), "okf-bqaa-cli-poster.png present (lookup JSON + payoff frame)")
cast_head = (CLI / "okf-bqaa-cli.cast").read_text("utf-8").splitlines()[0]
check(('"version": 2' in cast_head or '"version":2' in cast_head) and "live-adapter proof" in cast_head and "why the next agent does better" in cast_head,
      "cast is asciinema v2 titled why-the-next-agent-does-better + live-adapter proof")
cast_text = (CLI / "okf-bqaa-cli.cast").read_text("utf-8")
check("Payoff: use Active-customer revenue, not legacy" in cast_text and QUESTION.split(" — ")[0] in cast_text, "cast carries the question and the payoff comment")
if shutil.which("ffprobe"):
    r = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries", "stream=codec_name,width,height:format=duration",
                        "-of", "json", str(DEMO / "okf-bqaa-cli.mp4")], capture_output=True, text=True)
    try:
        j = json.loads(r.stdout)
        st = j["streams"][0]
        dur = float(j["format"]["duration"])
        check(st.get("codec_name") == "h264" and st.get("width") == 1280 and st.get("height") == 720, "mp4 is H.264 1280×720 (got %s %sx%s)" % (st.get("codec_name"), st.get("width"), st.get("height")))
        check(20.0 <= dur <= 40.0, "mp4 runs 20–40s (got %.1fs)" % dur)
    except Exception as e:  # noqa: BLE001
        check(False, "ffprobe could not read okf-bqaa-cli.mp4 (%s)" % e)
else:
    note("ffprobe not on PATH; skipping codec / duration probe of okf-bqaa-cli.mp4")

# ---- page: hero is the why, IDs are collapsed -------------------------------------------
html = (DEMO / "index.html").read_text("utf-8")
app = (DEMO / "app.js").read_text("utf-8")
hero = html.split("<main", 1)[0]
body_main = html.split("<main", 1)[1] if "<main" in html else ""
walk = html.split('id="walkthrough"', 1)[1].split('class="extras"', 1)[0] if 'id="walkthrough"' in html else ""
ids = ""
m_ids = re.search(r"<details id=\"ids\">[\s\S]*?</details>\s*<details>", html)
if m_ids:
    ids = m_ids.group(0)

h1 = re.search(r"<h1[^>]*>([\s\S]*?)</h1>", hero)
check(h1 is not None and strip_tags(h1.group(1)) == QUESTION, "hero <h1> is exactly the locked question")
title = re.search(r"<title>([\s\S]*?)</title>", hero)
check(title is not None and strip_tags(title.group(1)) == QUESTION, "<title> is the locked question")
sub = re.search(r"<p class=\"subtitle\">([\s\S]*?)</p>", hero)
sub_text = strip_tags(sub.group(1)) if sub else ""
for s in PAYOFF_SENTENCES:
    check(s in sub_text, "hero subtitle has the locked sentence: " + s[:60] + "…")
check(sub_text == " ".join(PAYOFF_SENTENCES), "hero subtitle is exactly the three locked sentences")
for s in ("derived / demo", "untouched", "no GCP"):
    check(s in hero, "hero badges keep: " + s)
check("did not write Knowledge Catalog" in hero, "hero banner says this CLI path did not write Knowledge Catalog")

# No SHA wall / feature sheet above the fold.
for s, why in ((PUBLICATION, "full 64-hex publication"), ("sha256:", "any sha256 chip"), ("Object.hasOwn", "Object.hasOwn"),
               (ADAPTER, "adapter version badge"), (SESSION, "session id"), (TRACE, "trace id"), (TABLE, "table name"),
               (OBSERVATION, "observation_id"), (SNAPSHOT, "snapshot_id"), (PR_URL, "PR 474 link"), ("live-strip", "the three-row live SHA strip"),
               ("identity-strip", "the identity strip")):
    check(s not in hero, "hero / pre-<main> does not carry the %s" % why)
check(re.search(r"\b180\b", hero) is None, "hero / pre-<main> does not carry 180 as a badge")
for s in PRIOR_CONSUME + GERMANY:
    check(s not in hero, "hero does not show " + s)
    check(s not in walk, "walkthrough does not show " + s)

# Stepper: human titles, data-beat 1..4 preserved.
for n, t in enumerate(STEP_TITLES, 1):
    pat = r'<button class="step" type="button" data-beat="%d"[^>]*>.*?<span class="t">%s</span>' % (n, re.escape(t))
    check(re.search(pat, body_main, re.S) is not None, "stepper beat %d is titled %s" % (n, t))
check(body_main.count('data-beat="') == 4, "exactly four stepper buttons")

# Collapsed IDs panel carries the proof.
check("How this was built / IDs" in html and ids != "", "collapsed 'How this was built / IDs' panel exists")
for s in (AGENT, SESSION, TRACE, TABLE, MODEL, ADAPTER, CONTEXT_REF, PUBLICATION, OBSERVATION, SNAPSHOT, PR_URL, PR_HEAD, "Object.hasOwn", "180", "cymbal-finance-core", "pinned from CLI", 'id="ids-hist"'):
    check(s in ids, "IDs panel carries " + (s if len(s) < 50 else s[:40] + "…"))
check("prior" in ids and "okf-derived-germany" in ids, "IDs panel labels the Dataplex okf-derived-germany leftover as prior")
check(ids.index("<details") < html.index("What is real here"), "IDs panel precedes the honesty card")

# Walkthrough: recut tape first, poster wired, one caption per beat.
check('src="okf-bqaa-cli.mp4"' in walk, "walkthrough embeds okf-bqaa-cli.mp4")
check('poster="okf-bqaa-cli-poster.png"' in walk, "video poster is okf-bqaa-cli-poster.png")
check('preload="metadata"' in walk, "video preload=metadata")
walk_text = strip_tags(walk)
for i, c in enumerate(CAPTIONS, 1):
    check(c in walk_text, "walkthrough caption %d: %s…" % (i, c[:50]))
check(walk.index("okf-bqaa-cli.mp4") < walk.index("okf-bqaa-e2e.mp4"), "recut tape comes before the prior e2e clip")
check("expected fail-closed" in walk_text, "walkthrough labels junk-ref exit 2 as expected fail-closed")
m = re.search(r"okf-bqaa-e2e\.mp4", html)
check(m is not None and PRIOR_LABEL.search(html[max(0, m.start() - 600):m.start()]) is not None, "okf-bqaa-e2e.mp4 is labelled prior fixture clip")

# Honesty strings survive.
for s in ("observer-only", "nothing attested", "nothing is ATTESTED", "SYNTHETIC", "UNVERIFIABLE", "rcpt-observe-noexec",
          "issued no DML", "same-origin", "no real Catalog pin", "prior fixture clip"):
    check(s in html, "index.html honesty keeps: " + s)
check("computed in-browser" not in html and "computed in-browser" not in app, 'no "computed in-browser" claim in index.html / app.js')


def prior_lines_labelled(text, name, needles):
    bad = []
    for i, ln in enumerate(text.splitlines(), 1):
        if any(n in ln for n in needles) and not PRIOR_LABEL.search(ln):
            bad.append(i)
    check(not bad, "%s: every line naming the prior consume session / germany fixture is labelled prior or synthetic%s"
          % (name, "" if not bad else " (lines %s)" % ", ".join(map(str, bad[:8]))))


prior_lines_labelled(html, "index.html", PRIOR_CONSUME + GERMANY)
prior_lines_labelled(app, "app.js", PRIOR_CONSUME + GERMANY)

# ---- app.js: beat bodies, load path, fail-closed lookup ------------------------------------
for s in ("live/observe/live.json", "live/observe/live_identities.json", "live/observe/snapshot.json", "live/observe/mapping.json", "cli/okf-bqaa-cli-transcript.txt"):
    check(s in app, "app.js loads " + s)
check(re.search(r"fetch\(\s*[\"']https?://", app) is None, "app.js makes no cross-origin fetch()")
for n, tone, name in ((1, "telemetry", "Ask"), (2, "source", "Observe"), (3, "split", "Publish"), (4, "ink", "Next agent")):
    check('beatHead(%d, "%s", "%s"' % (n, tone, name) in app, "app.js beat %d is titled %s" % (n, name))
check("handle a Knowledge Catalog entry would expose" in app and "did not write Catalog" in app, "app.js beat 3 says KC handle + no Catalog write")
check("skips legacy" in app and "unproven" in app and "not legacy" in app, "app.js beat 4 states the payoff (current metric, not legacy, unproven)")
check("FAIL_CLOSED" in app and "okf:env-junk#deadbeef" in app, "app.js shows the fail-closed junk-ref tape")
check("expected fail-closed, not a crash" in app, "app.js labels the junk-ref tape as expected, not a crash")
check("Object.hasOwn(" in app, "app.js localLookup uses Object.hasOwn (own-key fail-closed)")
check("ref in map" not in app, "app.js does not use `ref in map` (would accept constructor/toString/__proto__)")
check("A.adapt(" in app and "traces/bqaa-germany.json" in app and "live_identities" in app and not re.search(r"A\.adapt\([^)]*live", app),
      "app.js runs adapter.js only on the SYNTHETIC germany trace, never on the live export")

# Hermetic: execute the committed localLookup against mapping.json.
# Python dict membership would not catch the JS `in` prototype leak, so this is node.
m_lookup = re.search(r"function localLookup\(ref\) \{[\s\S]*?\n  \}", app)
check(m_lookup is not None, "app.js defines localLookup")
if m_lookup is not None:
    node = (
        "const fs = require('fs');\n"
        "const D = { mapping: JSON.parse(fs.readFileSync(%s, 'utf8')) };\n"
        % json.dumps(str(OBS / "mapping.json"))
        + m_lookup.group(0)
        + """
const proto = ['constructor', 'toString', '__proto__'];
for (const k of proto) {
  const r = localLookup(k);
  if (!r || r.ok || r.exit !== 2) {
    console.error('prototype key did not fail closed:', k, r);
    process.exit(1);
  }
}
const junk = localLookup('okf:env-junk#deadbeef');
if (!junk || junk.ok || junk.exit !== 2) { console.error('junk ref did not fail closed', junk); process.exit(1); }
const ok = localLookup('okf:env-observe#674153c572f6');
if (!ok || !ok.ok || ok.exit !== 0 || !String((ok.result || {}).publication_id).startsWith('sha256:53bd1651')) {
  console.error('bound ref failed', ok); process.exit(1);
}
process.exit(0);
"""
    )
    r = subprocess.run(["node", "-e", node], capture_output=True, text=True)
    check(r.returncode == 0, "node hermetic: constructor/toString/__proto__ fail closed"
          + ("" if r.returncode == 0 else " (%s %s)" % (r.stderr.strip(), r.stdout.strip())))

# Hermetic: the page's transcript parser reads the four beats off the committed tape.
m_parse = re.search(r"function parseTranscript\(text\) \{[\s\S]*?\n  \}", app)
check(m_parse is not None, "app.js defines parseTranscript")
if m_parse is not None:
    node = (
        "const fs = require('fs');\n" + m_parse.group(0) +
        "\nconst r = parseTranscript(fs.readFileSync(%s, 'utf8'));\n" % json.dumps(str(CLI / "okf-bqaa-cli-transcript.txt")) +
        "const want = %s;\n" % json.dumps({"question": QUESTION, "pub": PUBLICATION, "ref": CONTEXT_REF, "current": CURRENT_METRIC, "legacy": LEGACY_METRIC}) +
        """
function die(m) { console.error(m); process.exit(1); }
if (r.askText !== want.question) die('askText ' + r.askText);
if (!r.observeLines.includes('rank 1: ' + want.current)) die('rank1 missing');
if (!r.observeLines.some(l => l.startsWith('excluded: ' + want.legacy))) die('excluded missing');
if (!r.lookup || r.lookup.publication_id !== want.pub || r.lookup.context_ref !== want.ref || r.lookup.label !== 'derived/demo') die('lookup ' + JSON.stringify(r.lookup));
if (r.kv.PUBLICATION_ID !== want.pub || r.kv.FILES !== '8') die('kv ' + JSON.stringify(r.kv));
if (!r.titleLines.includes(want.current) || !r.titleLines.includes(want.legacy)) die('titles ' + r.titleLines);
if (!r.payoffAfterJunk || !/not legacy/.test(r.payoffLine) || !/unproven/.test(r.payoffLine)) die('payoff ' + r.payoffLine + ' ' + r.payoffAfterJunk);
if (!r.junk.some(l => /^FAIL_CLOSED/.test(l)) || !r.junk.some(l => /exit 2/.test(l))) die('junk ' + r.junk);
process.exit(0);
"""
    )
    r = subprocess.run(["node", "-e", node], capture_output=True, text=True)
    check(r.returncode == 0, "node hermetic: app.js parseTranscript reads ASK / OBSERVE / PUBLISH / NEXT AGENT off the tape"
          + ("" if r.returncode == 0 else " (%s %s)" % (r.stderr.strip(), r.stdout.strip())))

r = subprocess.run(["node", "--check", str(DEMO / "app.js")], capture_output=True, text=True)
check(r.returncode == 0, "node --check app.js" + ("" if r.returncode == 0 else " (%s)" % r.stderr.strip()[:200]))

for p in (DEMO / "index.html", DEMO / "app.js", DEMO / "README.md", DEMO / "WALKTHROUGH.md", OBS / "snapshot.json", CLI / "okf-bqaa-cli-transcript.txt", DEMO.parent / "index.html"):
    check("gemini-2.5" not in p.read_text("utf-8"), "no gemini-2.5 in " + str(p.relative_to(DEMO.parent)))

readme = (DEMO / "README.md").read_text("utf-8")
check(QUESTION in readme and SESSION in readme and CONTEXT_REF in readme and PUBLICATION in readme and "PR 474" in readme, "README names the question, the observe session, context_ref, publication and PR 474")
check("did not write" in readme and "Knowledge Catalog" in readme, "README says this CLI path did not write Knowledge Catalog")
walkmd = (DEMO / "WALKTHROUGH.md").read_text("utf-8")
check(all(c in walkmd for c in CAPTIONS), "WALKTHROUGH.md carries the four caption sentences")

rfc_index = (DEMO.parent / "index.html").read_text("utf-8")
m_call = re.search(r"<div class=\"note\"[^>]*>\s*<span class=\"badge rev\"[^>]*><b>Prototype</b>[\s\S]*?</div>", rfc_index)
callout = strip_tags(m_call.group(0)) if m_call else ""
check(m_call is not None and QUESTION in callout, "rfc/index.html Prototype callout leads with the locked question")
check("legacy" in callout and "unproven" in callout and 'href="./demo/"' in (m_call.group(0) if m_call else ""), "rfc/index.html Prototype callout states the payoff and links ./demo/")
check(ADAPTER not in callout and re.search(r"\b180\b", callout) is None and "Object.hasOwn" not in callout, "rfc/index.html Prototype callout is why-language, not a feature list")
sentences = [s for s in re.split(r"(?<=[.!?])\s+", callout) if s.strip()]
check(2 <= len(sentences) <= 6, "rfc/index.html Prototype callout is short (%d sentences)" % len(sentences))

print()
if failures:
    print("cli viewer check: %d failure(s)" % len(failures))
    sys.exit(1)
print("cli viewer check: why-slice OK · session %s, %d events, %s → %s" % (SESSION, EVENTS, CONTEXT_REF, PUBLICATION[:20] + "…"))
