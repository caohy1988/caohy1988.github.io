#!/usr/bin/env python3
"""Check the static CLI viewer of the BQAA → OKF path (stdlib only, read-only).

Asserts that /rfc/demo/ is a viewer of the SDK CLI run on record:

* live/observe/live.json is the okf_rfc_observe_agent session
  f21ee192-d989-4c38-894f-66b6b82eaf18 with event_count 180, context_ref
  okf:env-observe#674153c572f6, model gemini-3.8-flash;
* live/observe/live_identities.json pins publication sha256:53bd1651…;
* live/observe/mapping.json binds that context_ref to that publication;
* live/observe/snapshot.json is the TRIMMED viewer snapshot (histogram sums
  to 180, samples carry the session, the 494KB export is not on disk);
* cli/okf-bqaa-cli-transcript.txt carries SESSION / PUBLICATION_ID /
  FAIL_CLOSED and agrees with the JSON;
* index.html presents okf_rfc_observe_agent + okf:env-observe#674153c572f6
  on the hero / live strip, and never presents the prior consume session
  (okf_rfc_consume_agent / 04fa3d56-… / okf:env-demo#a25e1c0ccbca) or the
  germany fixture (sess-4c1f9a2e7b3d) as Observe / Adapt source of truth;
* no "computed in-browser" claim anywhere in index.html / app.js;
* no gemini-2.5 anywhere in the viewer files.

Usage: python3 rfc/demo/tools/check_cli_viewer.py   (exit 0 on pass)
"""
import json
import re
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

# Strings that may appear only as the labelled prior consume experiment / synthetic fixture.
PRIOR_CONSUME = ["okf_rfc_consume_agent", "04fa3d56-f2f1-413e-8c2b-ec116835af84", "okf:env-demo#a25e1c0ccbca"]
GERMANY = ["sess-4c1f9a2e7b3d"]
PRIOR_LABEL = re.compile(r"prior|synthetic|not this|leftover", re.I)

failures = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


def load(p):
    return json.loads(p.read_text("utf-8"))


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
check(any(e.get("event_type") == "TOOL_COMPLETED" and ((e.get("content") or {}).get("result") or {}).get("context_ref") == CONTEXT_REF for e in samples),
      "a sample TOOL_COMPLETED result carries " + CONTEXT_REF)
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

# ---- CLI transcript ---------------------------------------------------------
tx = (CLI / "okf-bqaa-cli-transcript.txt").read_text("utf-8")
for line in ("SESSION " + SESSION, "TRACE " + TRACE, "TABLE " + TABLE, "MODEL " + MODEL, "ADAPTER " + ADAPTER,
             "CONTEXT_REF " + CONTEXT_REF, "OBSERVATION_ID " + OBSERVATION, "SNAPSHOT_ID " + SNAPSHOT,
             "PUBLICATION_ID " + PUBLICATION, "FILES 8", "RECEIPT UNVERIFIABLE rcpt-observe-noexec"):
    check(line in tx, "transcript has: " + line[:60] + ("…" if len(line) > 60 else ""))
check("run.py --lookup 'okf:env-observe#674153c572f6'" in tx, "transcript shows the lookup command for " + CONTEXT_REF)
check("FAIL_CLOSED" in tx and "okf:env-junk#deadbeef" in tx and "exit 2" in tx, "transcript shows FAIL_CLOSED for the junk ref with exit 2")
check("expected FAIL_CLOSED exit 2" in tx and "not a crashed demo" in tx, "transcript labels junk-ref exit 2 as expected fail-closed, not a crash")
check("180 events" in tx and "useful OKF" in tx and "Active-customer revenue" in tx, "transcript is pedagogical: 180 events + useful OKF titles, not a hash dump")
check("an agent later resolves context_ref" in tx, "transcript comments the LOOKUP beat")
check("476d37dc9d4210a335c2f77e78003f6a5ebe2878" in tx and "do not merge" in tx, "transcript pins PR 474 HEAD and says do not merge")
for name in ("okf-bqaa-cli.cast", "okf-bqaa-cli.gif"):
    check((CLI / name).exists(), "cli/%s present" % name)
check((DEMO / "okf-bqaa-cli.mp4").exists(), "okf-bqaa-cli.mp4 present (live-adapter proof)")
check((DEMO / "okf-bqaa-cli-poster.png").exists(), "okf-bqaa-cli-poster.png present (successful lookup JSON frame)")
cast_head = (CLI / "okf-bqaa-cli.cast").read_text("utf-8").splitlines()[0]
check(('"version": 2' in cast_head or '"version":2' in cast_head) and "live-adapter proof" in cast_head, "cast is asciinema v2 titled live-adapter proof")

# ---- page ----------------------------------------------------------------------
html = (DEMO / "index.html").read_text("utf-8")
app = (DEMO / "app.js").read_text("utf-8")
hero = html.split("<main", 1)[0]
walk = html.split('id="walkthrough"', 1)[1].split('class="extras"', 1)[0] if 'id="walkthrough"' in html else ""

for s in (AGENT, SESSION, CONTEXT_REF, PUBLICATION, TABLE, MODEL, ADAPTER, "180"):
    check(s in hero, "hero / live strip shows " + s)
check(PR_URL in hero, "hero / live strip links SDK PR 474")
for s in (AGENT, SESSION, CONTEXT_REF):
    check(s in walk, "walkthrough live snapshot card shows " + s)
for s in PRIOR_CONSUME + GERMANY:
    check(s not in hero, "hero / live strip does not show " + s)
    check(s not in walk, "walkthrough live snapshot card does not show " + s)
check("computed in-browser" not in html and "computed in-browser" not in app, 'no "computed in-browser" claim in index.html / app.js')
check("pinned from CLI" in html, "derived identity row is labelled pinned from CLI")
check('src="okf-bqaa-cli.mp4"' in html, "walkthrough embeds okf-bqaa-cli.mp4")
check('poster="okf-bqaa-cli-poster.png"' in html, "video poster is the successful lookup PNG, not an empty first frame")
check('preload="metadata"' in html, "video preload=metadata")
check("180 live BQAA" in html and "derived OKF bundle" in html, "caption has OBSERVE + ADAPT sentences")
check("resolves" in html and "context_ref" in html, "caption has LOOKUP sentence")
check("fail-closed proof" in html or "junk-ref exit 2" in html, "caption says junk-ref exit 2 is fail-closed proof")
m = re.search(r"okf-bqaa-e2e\.mp4", html)
check(m is not None and PRIOR_LABEL.search(html[max(0, m.start() - 600):m.start()]) is not None,
      "okf-bqaa-e2e.mp4 is labelled prior fixture clip")


def prior_lines_labelled(text, name, needles):
    bad = []
    for i, ln in enumerate(text.splitlines(), 1):
        if any(n in ln for n in needles) and not PRIOR_LABEL.search(ln):
            bad.append(i)
    check(not bad, "%s: every line naming the prior consume session / germany fixture is labelled prior or synthetic%s"
          % (name, "" if not bad else " (lines %s)" % ", ".join(map(str, bad[:8]))))


prior_lines_labelled(html, "index.html", PRIOR_CONSUME + GERMANY)
prior_lines_labelled(app, "app.js", PRIOR_CONSUME + GERMANY)

for s in ("live/observe/live.json", "live/observe/live_identities.json", "live/observe/snapshot.json", "live/observe/mapping.json", "cli/okf-bqaa-cli-transcript.txt"):
    check(s in app, "app.js loads " + s)
check(re.search(r"fetch\(\s*[\"']https?://", app) is None, "app.js makes no cross-origin fetch()")
check("FAIL_CLOSED" in app and "okf:env-junk#deadbeef" in app, "app.js shows the fail-closed junk-ref tape")
check("Object.hasOwn(" in app, "app.js localLookup uses Object.hasOwn (own-key fail-closed)")
check("ref in map" not in app, "app.js does not use `ref in map` (would accept constructor/toString/__proto__)")

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

for p in (DEMO / "index.html", DEMO / "app.js", DEMO / "README.md", DEMO / "WALKTHROUGH.md", OBS / "snapshot.json", CLI / "okf-bqaa-cli-transcript.txt"):
    check("gemini-2.5" not in p.read_text("utf-8"), "no gemini-2.5 in " + str(p.relative_to(DEMO)))

readme = (DEMO / "README.md").read_text("utf-8")
check(SESSION in readme and CONTEXT_REF in readme and PUBLICATION in readme and "PR 474" in readme, "README names the observe session, context_ref, publication and PR 474")
rfc_index = (DEMO.parent / "index.html").read_text("utf-8")
check(AGENT in rfc_index and "okf-bqaa-adapter:v0" in rfc_index, "rfc/index.html Prototype callout names the observe agent and the CLI adapter")

print()
if failures:
    print("cli viewer check: %d failure(s)" % len(failures))
    sys.exit(1)
print("cli viewer check: session %s, %d events, %s → %s" % (SESSION, EVENTS, CONTEXT_REF, PUBLICATION[:20] + "…"))
