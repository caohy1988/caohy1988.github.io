#!/usr/bin/env python3
"""Lightweight checks for the Grok 36h STALE rule + box collector schema.

    python3 test_grok_stale.py

Uses temp caches / a fake box tree; never touches the real grok_box_activity.json.
"""
import copy
import json
import sys
import tempfile
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402
import collect_grok_box_activity as box  # noqa: E402

cab.sync_manage_bot_transcript_from_client = lambda: None  # no client-replica side effects
cab.collect_box_bots = lambda: None  # force the cache path even when run on the box

FMT = "%Y-%m-%dT%H:%M:%SZ"
NOW = datetime.now(timezone.utc)
TMP = Path(tempfile.mkdtemp())
BOT_KEYS = {
    "id", "name", "title", "role", "messages", "transcript_bytes", "transcript_mb",
    "last_transcript_activity_pt", "automation_runs", "last_automation_started_pt",
    "share_assistant_tool_pct",
}
TOP_KEYS = {
    "ok", "source", "note", "collected_at_pt", "collected_at_utc", "bots",
    "fleet_messages_total", "fleet_assistant_tool_total", "links",
}
BASE = box.build_payload(
    box.normalize_bots([dict(box.empty_bot("Medium Bot"), last_transcript_activity_pt="2026-09-07 10:00 PDT")]),
    "test",
)
SNAP = {
    "generated_at_pt": "test", "claude": {}, "codex": {}, "kimi": {}, "agy": {}, "muse": {}, "dsh": {},
    "routine_proxy": {},
}


def run(mut):
    d = copy.deepcopy(BASE)
    keep = mut(d) is not False
    cab.GROK_CACHE = TMP / "cache.json"
    if keep:
        cab.GROK_CACHE.write_text(json.dumps(d))
    elif cab.GROK_CACHE.exists():
        cab.GROK_CACHE.unlink()
    g = cab.collect_grok()
    return g, cab.render_grok_body(g)


def ago(**kw):
    return (NOW - timedelta(**kw)).strftime(FMT)


def week_old(d):
    d["collected_at_utc"] = ago(days=7)
    d["collected_at_pt"] = "2026-09-13 09:00:00 PDT"


def no_stamp(d):
    d.pop("collected_at_utc")
    d.pop("collected_at_pt")


def pt_only(d):
    d.pop("collected_at_utc")
    d["collected_at_pt"] = (NOW - timedelta(hours=2)).astimezone(box.PT).strftime("%Y-%m-%d %H:%M:%S %Z")


g, h = run(week_old)
assert g["stale"] is True and g["ok"] is True and "168h" in g["stale_reason"], g
assert ">STALE<" in h and 'class="stale-banner"' in h and "2026-09-13" in h
assert "<table" in h  # table still renders under the banner

g, h = run(lambda d: d.update(collected_at_utc=ago(hours=35)))
assert g["stale"] is False and g["stale_reason"] is None and ">STALE<" not in h
assert "box activity collected" in h  # collected_at shown in the pill

g, h = run(lambda d: d.update(collected_at_utc=ago(hours=37)))
assert g["stale"] is True and ">STALE<" in h

g, h = run(no_stamp)
assert g["stale"] is True and ">STALE<" in h and "no collected_at timestamp" in h

g, h = run(lambda d: d.update(collected_at_utc="garbage", collected_at_pt="nope"))
assert g["stale"] is True and "unparseable" in g["stale_reason"]

g, h = run(pt_only)
assert g["stale"] is False

g, h = run(lambda d: False)  # cache file missing
assert g["stale"] is True and g["ok"] is True and ">STALE<" in h

(TMP / "cache.json").write_text("{bad")
g = cab.collect_grok()
assert g["stale"] is True and g["ok"] is False and ">STALE<" in cab.render_grok_body(g)

# box collector against a fake box tree
a = TMP / "agents" / "id-1"
a.mkdir(parents=True)
(a / "profile.json").write_text(json.dumps({"name": "Medium Bot", "title": "Marketing"}))
t = TMP / "tr" / "id-1"
t.mkdir(parents=True)
(t / "id-1.jsonl").write_text('{"role":"user"}\n{"role":"assistant"}\n{"role":"tool"}\nnot json\n')
r = TMP / "agents" / "room"
r.mkdir()
(r / "profile.json").write_text(json.dumps({"name": "Jev"}))
out = TMP / "out.json"
argv = ["--agents-dir", str(TMP / "agents"), "--transcripts-dir", str(TMP / "tr")]
assert box.main(["-o", str(out)] + argv) == 0
p = json.loads(out.read_text())
assert TOP_KEYS <= set(p), TOP_KEYS - set(p)
assert all(BOT_KEYS <= set(b) for b in p["bots"])
mb = next(b for b in p["bots"] if b["name"] == "Medium Bot")
assert mb["messages"] == {"user": 1, "assistant": 1, "tool": 1, "total": 3, "assistant_tool": 2}
assert mb["share_assistant_tool_pct"] == 100.0 and mb["missing_transcript"] is False
jev = next(b for b in p["bots"] if b["name"] == "Jev")
assert jev["messages"]["total"] == 0 and jev["last_transcript_activity_pt"] is None
assert jev["missing_transcript"] is True  # listed empty, nothing invented
assert box.staleness(p) == (False, None)
assert box.main(["--agents-dir", str(TMP / "nope")]) == 2  # off-box → clear error, no output

print("ALL CHECKS PASSED")
