#!/usr/bin/env python3
"""Collect Grok Bot activity on the box → schema-compatible grok_box_activity.json.

Run on the **box** (the Mac cannot see /home/box/agent-data):

    python3 collect_grok_box_activity.py -o /tmp/grok_box_activity.json

then copy the output to the Mac at
``Documents/agent-analytics-research/usage-dashboard/grok_box_activity.json``.
``collect_and_build.py`` imports this module too, so the live-box path and the
cached path share one implementation. Stdlib only; output carries counts,
sizes and timestamps — never transcript text, tokens or secrets.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

PT = ZoneInfo("America/Los_Angeles")
BOX_AGENTS = Path("/home/box/agent-data/agents")
BOX_TRANS = Path("/home/box/agent-data/agent-transcripts")

GROK_ORDER = [
    "Agent Analytics Collection Bot",
    "Github Bot CHY1988",
    "Medium Bot",
    "Agent Manage Bot",
]
GROK_ROLES = {
    "Agent Analytics Collection Bot": "Collection / vault ops",
    "Github Bot CHY1988": "GitHub / hub publish",
    "Medium Bot": "Medium (id was Linkedin)",
    "Agent Manage Bot": "Chief of staff — dual-layer harness (rooms, Lab, Field Brief watch)",
}
# Dead / placeholder agents still on disk — never show in usage roster
GROK_SKIP_NAMES = {"New Bot", "Field Brief", "Coding EM"}  # rooms = channels, not usage rows
GROK_NOTE = "Activity share from local Grok Bot transcripts — not Cursor plan dollars."
GROK_LINKS = {
    "usage_billing": "grokbot://app/v1/settings?id=plan",
    "on_demand": "grokbot://app/v1/settings?id=on-demand",
}
# Cache older than this (or with no parseable collected_at_*) renders a STALE banner.
STALE_AFTER_HOURS = 36


def _mtime_pt(ts: float) -> str:
    return datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(PT).strftime("%Y-%m-%d %H:%M %Z")


def ms_to_pt(ms: int | float | None) -> str | None:
    if ms is None:
        return None
    try:
        return _mtime_pt(float(ms) / 1000.0)
    except Exception:
        return None


def empty_bot(name: str) -> dict:
    return {
        "id": None,
        "name": name,
        "title": "",
        "role": GROK_ROLES.get(name, ""),
        "messages": {"user": 0, "assistant": 0, "tool": 0, "total": 0, "assistant_tool": 0},
        "transcript_bytes": 0,
        "transcript_mb": 0.0,
        "last_transcript_activity_pt": None,
        "automation_runs": 0,
        "last_automation_started_pt": None,
        "share_assistant_tool_pct": 0.0,
        "missing_transcript": True,
    }


def _collect_one(d: Path, trans_dir: Path) -> dict:
    prof = json.loads((d / "profile.json").read_text())
    aid = d.name
    name = prof.get("name") or aid
    tp = trans_dir / aid / f"{aid}.jsonl"
    counts: Counter = Counter()
    size = 0
    mtime = None
    if tp.exists():
        st = tp.stat()
        size = st.st_size
        mtime = _mtime_pt(st.st_mtime)
        with tp.open() as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                r = o.get("role") if isinstance(o, dict) else None
                if r in ("user", "assistant", "tool"):
                    counts[r] += 1
    # Fallback: local store.db when jsonl not mirrored yet (e.g. new / temporal agents)
    store = d / "store.db"
    if sum(counts.values()) == 0 and store.exists():
        try:
            import sqlite3

            con = sqlite3.connect(f"file:{store}?mode=ro", uri=True)
            rows = con.execute("SELECT entry FROM transcript_entries").fetchall()
            con.close()
            for (entry,) in rows:
                try:
                    o = json.loads(entry) if isinstance(entry, str) else {}
                except Exception:
                    continue
                kind = (o.get("kind") or "").lower()
                if kind in ("user-message", "user", "receive-message"):
                    counts["user"] += 1
                elif kind in ("send-message", "assistant"):
                    counts["assistant"] += 1
                elif "tool" in kind:
                    counts["tool"] += 1
                elif kind:
                    # unknown store kinds still count as assistant activity
                    counts["assistant"] += 1
            if rows:
                st = store.stat()
                size = max(size, st.st_size)
                mtime = _mtime_pt(st.st_mtime)
        except Exception:
            pass
    auto_runs = 0
    last_started = None
    autod = d / "automations"
    if autod.exists():
        for runs_path in autod.glob("*/runs.json"):
            try:
                raw = json.loads(runs_path.read_text())
            except Exception:
                continue
            entries = raw if isinstance(raw, list) else (raw.get("runs") or raw.get("entries") or [])
            if not isinstance(entries, list):
                continue
            auto_runs += len(entries)
            for e in entries:
                sa = e.get("startedAt") or e.get("started_at") if isinstance(e, dict) else None
                if sa is None:
                    continue
                try:
                    if last_started is None or float(sa) > float(last_started):
                        last_started = sa
                except (TypeError, ValueError):
                    continue
    at = counts["assistant"] + counts["tool"]
    return {
        "id": aid,
        "name": name,
        "title": prof.get("title") or "",
        "role": GROK_ROLES.get(name, prof.get("title") or ""),
        "messages": {
            "user": counts["user"],
            "assistant": counts["assistant"],
            "tool": counts["tool"],
            "total": counts["user"] + counts["assistant"] + counts["tool"],
            "assistant_tool": at,
        },
        "transcript_bytes": size,
        "transcript_mb": round(size / (1024 * 1024), 2),
        "last_transcript_activity_pt": mtime,
        "automation_runs": auto_runs,
        "last_automation_started_pt": ms_to_pt(last_started),
        # no jsonl and no store.db rows → honest empty row, never an invented transcript
        "missing_transcript": mtime is None,
    }


def normalize_bots(bots: list[dict]) -> list[dict]:
    """Roster order, skip placeholders, add zero rows for missing named bots, recompute shares.

    Entries without a transcript dir (e.g. Jev) stay as zero rows — nothing is
    invented for them; names in GROK_SKIP_NAMES (placeholders, rooms) are dropped.
    """
    bots = list(bots)
    have = {b.get("name") for b in bots}
    for name in GROK_ORDER:
        if name not in have:
            bots.append(empty_bot(name))
    bots = [b for b in bots if b.get("name") not in GROK_SKIP_NAMES]
    rank = {n: i for i, n in enumerate(GROK_ORDER)}
    bots.sort(key=lambda b: (rank.get(b.get("name"), 99), b.get("name") or ""))
    fleet_at = sum((b.get("messages") or {}).get("assistant_tool") or 0 for b in bots)
    for b in bots:
        at = (b.get("messages") or {}).get("assistant_tool") or 0
        b["share_assistant_tool_pct"] = round(100.0 * at / fleet_at, 1) if fleet_at else 0.0
    return bots


def build_payload(bots: list[dict], source: str, now: datetime | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    return {
        "ok": True,
        "source": source,
        "note": GROK_NOTE,
        "collected_at_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "collected_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bots": bots,
        "fleet_messages_total": sum(b["messages"]["total"] for b in bots),
        "fleet_assistant_tool_total": sum(b["messages"]["assistant_tool"] for b in bots),
        "links": dict(GROK_LINKS),
    }


def collect_box_bots(agents_dir: Path = BOX_AGENTS, trans_dir: Path = BOX_TRANS) -> list[dict] | None:
    """Per-bot rows from box agent-data, or None when the box path is not visible."""
    if not agents_dir.exists():
        return None
    bots = []
    for d in sorted(agents_dir.iterdir()):
        if not d.is_dir() or not (d / "profile.json").exists():
            continue
        try:
            bots.append(_collect_one(d, trans_dir))
        except Exception as e:  # one unreadable profile must not sink the fleet
            print(f"collect_grok_box_activity: skip {d.name}: {e}", file=sys.stderr)
    return normalize_bots(bots)


# ── freshness ───────────────────────────────────────────────────────────────

def parse_collected_at(data: dict) -> datetime | None:
    """Aware UTC datetime from collected_at_utc (preferred) or collected_at_pt."""
    raw = data.get("collected_at_utc")
    if isinstance(raw, str) and raw.strip():
        try:
            dt = datetime.fromisoformat(raw.strip().replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt.astimezone(timezone.utc)
        except ValueError:
            pass
    raw = data.get("collected_at_pt")
    if isinstance(raw, str) and raw.strip():
        # "2026-09-20 16:43:57 PDT" — drop the zone abbreviation, interpret as PT
        parts = raw.strip().split()
        base = " ".join(parts[:2])
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(base, fmt).replace(tzinfo=PT).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def staleness(data: dict | None, now: datetime | None = None) -> tuple[bool, str | None]:
    """(stale, reason). Stale = no cache, no parseable collected_at_*, or older than 36h."""
    if data is None:
        return True, "no grok_box_activity.json cache — box activity was never synced to this Mac"
    dt = parse_collected_at(data)
    if dt is None:
        return True, "collected_at_utc / collected_at_pt missing or unparseable — cache age unknown"
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    age_h = (now - dt).total_seconds() / 3600.0
    if age_h > STALE_AFTER_HOURS:
        shown = data.get("collected_at_pt") or data.get("collected_at_utc")
        return True, f"cache is {age_h:.0f}h old (> {STALE_AFTER_HOURS}h; collected {shown})"
    return False, None


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("-o", "--output", default="-", help="output path (default: stdout)")
    ap.add_argument("--agents-dir", type=Path, default=BOX_AGENTS)
    ap.add_argument("--transcripts-dir", type=Path, default=BOX_TRANS)
    args = ap.parse_args(argv)
    bots = collect_box_bots(args.agents_dir, args.transcripts_dir)
    if bots is None:
        print(
            f"collect_grok_box_activity: {args.agents_dir} not found — run this on the box",
            file=sys.stderr,
        )
        return 2
    payload = build_payload(
        bots, "box /home/box/agent-data agents + transcripts + automations/*/runs.json"
    )
    text = json.dumps(payload, indent=2, ensure_ascii=False) + "\n"
    if args.output == "-":
        sys.stdout.write(text)
    else:
        out = Path(args.output)
        tmp = out.with_name(out.name + ".tmp")
        tmp.write_text(text)
        tmp.replace(out)
        print(f"wrote {out} ({len(bots)} bots)", file=sys.stderr)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
