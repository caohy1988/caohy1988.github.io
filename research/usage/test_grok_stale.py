#!/usr/bin/env python3
"""Lightweight checks for the Grok 36h STALE rule + box collector schema.

    python3 test_grok_stale.py

Uses temp caches / a fake box tree; never touches the real grok_box_activity.json.
"""
import contextlib
import copy
import io
import json
import os
import shutil
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
box.client_persistence_root = lambda: TMP / "no-client-replicas"  # never read this Mac's Grok client data
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

# a cached bot outside the five-name roster is kept (it used to be dropped), after the roster rows
EXTRA = dict(box.empty_bot("Extra Bot"), id="extra-1", title="Side project", role="Side project",
             missing_transcript=False, last_transcript_activity_pt="2026-09-01 10:00 PDT",
             source_mtime_epoch=(NOW - timedelta(days=30)).timestamp())
g, h = run(lambda d: d["bots"].append(copy.deepcopy(EXTRA)))
assert [b["name"] for b in g["bots"]] == box.GROK_ORDER + ["Extra Bot"], [b["name"] for b in g["bots"]]
extra = g["bots"][-1]
assert extra["stale"] is False and extra["stale_reason"] is None  # idle, not a broken roster source
assert not any(s.startswith("Extra Bot") for s in g["freshness"]["stale_or_missing"])
assert "<strong>Extra Bot</strong>" in h and "Side project" in h
g, h = run(lambda d: d["bots"].append(dict(box.empty_bot("Field Brief"), id="room-1")))
assert "Field Brief" not in [b["name"] for b in g["bots"]]  # rooms stay out

# box collector against a fake box tree: every roster dir, two rooms, the New Bot placeholder and one
# idle bot outside the roster
agents, tr = TMP / "agents", TMP / "tr"


def agent(aid, name, title=""):
    d = agents / aid
    d.mkdir(parents=True)
    (d / "profile.json").write_text(json.dumps({"name": name, "title": title}))
    return d


for rid, rname in box.ROSTER_IDS.items():
    agent(rid, rname, "Marketing" if rname == "Medium Bot" else "")
mid = box.NAME_TO_ID["Medium Bot"]
(tr / mid).mkdir(parents=True)
(tr / mid / f"{mid}.jsonl").write_text('{"role":"user"}\n{"role":"assistant"}\n{"role":"tool"}\nnot json\n')
for i, room in enumerate(sorted(box.GROK_SKIP_NAMES)):
    agent(f"room-{i}", room)
idle = agent("extra-1", "Extra Bot", "Side project")
old = (NOW - timedelta(days=10)).timestamp()
os.utime(idle / "profile.json", (old, old))
out = TMP / "out.json"
argv = ["--agents-dir", str(agents), "--transcripts-dir", str(tr)]
with contextlib.redirect_stdout(io.StringIO()) as said:
    rc = box.main(["-o", str(out)] + argv)
assert rc == 0, said.getvalue()  # an idle bot outside the roster is not a stale source
p = json.loads(out.read_text())
assert TOP_KEYS <= set(p), TOP_KEYS - set(p)
assert all(BOT_KEYS <= set(b) for b in p["bots"])
assert [b["name"] for b in p["bots"]] == box.GROK_ORDER + ["Extra Bot"], [b["name"] for b in p["bots"]]
assert p["ok"] is True and p["freshness"]["stale_or_missing"] == []
extra = p["bots"][-1]
assert extra["id"] == "extra-1" and extra["role"] == "Side project" and extra["stale"] is False
assert extra["last_transcript_activity_pt"] is not None and extra["source_age_hours"] >= 239
mb = next(b for b in p["bots"] if b["name"] == "Medium Bot")
assert mb["messages"] == {"user": 1, "assistant": 1, "tool": 1, "total": 3, "assistant_tool": 2}
assert mb["share_assistant_tool_pct"] == 100.0 and mb["missing_transcript"] is False
jev = next(b for b in p["bots"] if b["name"] == "Jev")
assert jev["messages"]["total"] == 0  # no transcript: no counts invented
assert box.staleness(p) == (False, None)
# a missing roster dir still fails loudly
shutil.rmtree(agents / box.NAME_TO_ID["Github Bot CHY1988"])
with contextlib.redirect_stdout(io.StringIO()) as said:
    assert box.main(["-o", str(out)] + argv) == 1
assert "Github Bot CHY1988(missing_dir)" in said.getvalue()
p = json.loads(out.read_text())
gh = next(b for b in p["bots"] if b["name"] == "Github Bot CHY1988")
assert gh["missing_agent_dir"] is True and gh["stale"] is True and p["ok"] is False
assert box.main(["--agents-dir", str(TMP / "nope")]) == 2  # off-box → clear error, no output

print("ALL CHECKS PASSED")
