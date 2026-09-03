#!/usr/bin/env python3
"""Check the committed live BQAA snapshot (stdlib only, read-only).

Asserts that live/agent_events.json is the real okf_rfc_demo.agent_events
export for session 04fa3d56-f2f1-413e-8c2b-ec116835af84: every row carries
that session_id and trace_id, a TOOL_COMPLETED row carries the derived
context_ref, the tool payloads contain nothing from the never-emit list,
the tool result's publication_id equals the pinned derived publication, and
live/live.json agrees with the rows.

Usage: python3 tools/check_live_trace.py   (exit 0 on pass)
"""
import json, sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
LIVE = DEMO / "live"

SESSION = "04fa3d56-f2f1-413e-8c2b-ec116835af84"
TRACE = "0294f653a4f141ae960865e438538d2e"
CONTEXT_REF = "okf:env-demo#a25e1c0ccbca"
MODEL = "gemini-3.8-flash"
TOOL = "lookup_okf_context"
NEVER_EMIT = ["concept_version_id", "bundle_path", "source_path", "principal", "user_id",
              "query_text", "sql", "parameter_values", "destination_table"]

failures = []


def check(cond, msg):
    print(("OK   " if cond else "FAIL ") + msg)
    if not cond:
        failures.append(msg)


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


rows = json.loads((LIVE / "agent_events.json").read_text("utf-8"))
meta = json.loads((LIVE / "live.json").read_text("utf-8"))
pinned = json.loads((DEMO / "derived" / "identities.json").read_text("utf-8"))

check(isinstance(rows, list) and len(rows) == 14, "14 rows in live/agent_events.json (got %s)" % (len(rows) if isinstance(rows, list) else "?"))
check(all(r.get("session_id") == SESSION for r in rows), "every row session_id == " + SESSION)
check(all(r.get("trace_id") == TRACE for r in rows), "every row trace_id == " + TRACE)
check(all(r.get("agent") == "okf_rfc_consume_agent" for r in rows), "every row agent == okf_rfc_consume_agent")

for r in rows:
    r["_attributes"] = parse(r.get("attributes"))
    r["_content"] = parse(r.get("content"))

types = [r["event_type"] for r in rows]
starting = [r for r in rows if r["event_type"] == "TOOL_STARTING"]
completed = [r for r in rows if r["event_type"] == "TOOL_COMPLETED"]
responses = [r for r in rows if r["event_type"] == "AGENT_RESPONSE"]
llm_req = [r for r in rows if r["event_type"] == "LLM_REQUEST"]
llm_res = [r for r in rows if r["event_type"] == "LLM_RESPONSE"]

check(len(completed) >= 1, "at least one TOOL_COMPLETED row")
check(any((c["_content"] or {}).get("result", {}).get("context_ref") == CONTEXT_REF for c in completed),
      "TOOL_COMPLETED result.context_ref == " + CONTEXT_REF)
check(all((c["_content"] or {}).get("tool") == TOOL for c in completed), "TOOL_COMPLETED tool == " + TOOL)
check(len(starting) >= 1 and all((s["_content"] or {}).get("args", {}).get("context_ref") == CONTEXT_REF for s in starting),
      "TOOL_STARTING args.context_ref == " + CONTEXT_REF)
check(all(set((s["_content"] or {}).get("args", {}).keys()) == {"context_ref"} for s in starting),
      "TOOL_STARTING args carry context_ref only")
check(len(responses) == 1 and isinstance((responses[0]["_content"] or {}).get("response"), str)
      and CONTEXT_REF in responses[0]["_content"]["response"], "one AGENT_RESPONSE that cites " + CONTEXT_REF)
check(all((r["_attributes"] or {}).get("model") == MODEL for r in llm_req) and len(llm_req) >= 1, "LLM_REQUEST attributes.model == " + MODEL)
check(all((r["_attributes"] or {}).get("model_version") == MODEL for r in llm_res) and len(llm_res) >= 1, "LLM_RESPONSE attributes.model_version == " + MODEL)
check(all((r["_attributes"] or {}).get("tools") == [TOOL] for r in llm_req), "LLM_REQUEST declares only " + TOOL)

payloads = [s["_content"].get("args") for s in starting] + [c["_content"].get("result") for c in completed]
seen = keys_deep(payloads)
viol = sorted(k for k in NEVER_EMIT if k in seen)
check(not viol, "tool payload keys ∩ never-emit = ∅" + ("" if not viol else " (violations: %s)" % ", ".join(viol)))

pub = completed[0]["_content"]["result"].get("publication_id") if completed else None
check(pub == pinned["publication_id"], "tool result publication_id == derived/identities.json publication_id")
check(pub is not None and CONTEXT_REF == "okf:env-demo#" + pub.split(":")[1][:12], "context_ref == okf:env-demo# + prefix12(derived publication)")

texts = json.dumps([r["_content"] for r in rows]) + json.dumps([r["_attributes"] for r in rows])
check("SELECT" not in texts.upper().replace("SELECTED", ""), "no SQL text in any row")
check("gemini-2.5" not in texts, "no gemini-2.5 anywhere")

for k, want in (("session_id", SESSION), ("trace_id", TRACE), ("context_ref", CONTEXT_REF), ("model", MODEL),
                ("agent", "okf_rfc_consume_agent"), ("dataset", "okf_rfc_demo"), ("table", "agent_events"),
                ("project", "test-project-0728-467323"), ("publication_id", pinned["publication_id"])):
    check(meta.get(k) == want, "live.json %s == %s" % (k, want))
check(meta.get("kc_entry", "").endswith("/entryGroups/okf-rfc-demo/entries/okf-derived-germany"), "live.json kc_entry is the okf-derived-germany entry")
check(meta.get("bq_console", "").startswith("https://console.cloud.google.com/bigquery?") and meta.get("kc_console", "").startswith("https://console.cloud.google.com/dataplex/search?"),
      "live.json console links are console.cloud.google.com deep links")

print()
if failures:
    print("live trace check: %d failure(s)" % len(failures))
    sys.exit(1)
print("live trace check: session %s, %d rows, %s on tool payloads" % (SESSION, len(rows), CONTEXT_REF))
