#!/usr/bin/env python3
"""Collect Grok Bot activity → schema-compatible grok_box_activity.json.

On the box: last-activity from live agents/<id>/ files + store.db (NOT the
frozen agent-transcripts mirror). On the Mac: prefer a synced
grok_box_activity.json, and overlay last-activity from Grok Bot client
transcript replicas under Application Support when those are newer.

Freshness: any roster bot whose source is >24h old while peers are fresh gets
stale:true. Missing agent dirs fail loudly. Collector prints STALE_SOURCES and
exits 1 when any roster bot is stale or missing.
"""

from __future__ import annotations

import argparse
import base64
import json
import re
import sqlite3
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
    "Jev",
]
GROK_ROLES = {
    "Agent Analytics Collection Bot": "Collection / vault ops",
    "Github Bot CHY1988": "GitHub / hub publish",
    "Medium Bot": "Medium (id was Linkedin)",
    "Agent Manage Bot": "Chief of staff — dual-layer harness (rooms, Lab, Field Brief watch)",
    "Jev": "Intake / routing (company-in-a-box)",
}
ROSTER_IDS = {
    "6a85c81a-8c66-4169-ae76-60d743932802": "Agent Manage Bot",
    "a70a646f-fe6c-4fdf-8fb1-75a73cbccc4b": "Github Bot CHY1988",
    "a81d2a9a-c28e-4a7b-942d-8ffba226b0cc": "Agent Analytics Collection Bot",
    "5c4c5dd4-6a97-476f-b7fa-9f70f629bc51": "Medium Bot",
    "2ef4d2bc-4750-4633-9ea7-20b3b5015689": "Jev",
}
NAME_TO_ID = {v: k for k, v in ROSTER_IDS.items()}
GROK_SKIP_NAMES = {"New Bot", "Field Brief", "Coding EM"}
GROK_NOTE = (
    "Activity share from local Grok Bot transcripts — not Cursor plan dollars. "
    "Last-activity from agents/<id>/ (live) + Mac client replicas when newer; "
    "stale:true when source >24h while peers are fresh."
)
GROK_LINKS = {
    "usage_billing": "grokbot://app/v1/settings?id=plan",
    "on_demand": "grokbot://app/v1/settings?id=on-demand",
}
STALE_AFTER_HOURS = 36  # cache-level banner (collected_at age)
SOURCE_STALE_AFTER_HOURS = 24.0  # per-bot relative source staleness
# Jev is called on demand via /home/box/bin/jev-route; real usage = router logs.
JEV_ID = "2ef4d2bc-4750-4633-9ea7-20b3b5015689"
JEV_LOG_DIR = Path("/home/box/agent-data/jev/logs")
JEV_SOURCE_LABEL = "jev-route logs"
JEV_STALE_AFTER_HOURS = 24.0 * 7  # stale only if BOTH logs + chat folder >7d
_JEV_LOG_RE = re.compile(r"^(\d{8}T\d{6})(\d{3})?Z(?:-(.+))?\.json$")
SKIP_BASENAMES = {
    "store.db-shm",
    "conversation-blobs.db-shm",
    "settings.json",
}


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
        "id": NAME_TO_ID.get(name),
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
        "missing_agent_dir": False,
        "activity_source": None,
        "source_mtime_epoch": None,
        "stale": False,
        "stale_reason": None,
    }


def _consider(ts, path, best):
    if ts is None:
        return best
    if best is None or ts > best[0]:
        return (float(ts), path)
    return best


def newest_agent_dir_activity(agent_dir: Path):
    best = None
    if not agent_dir.is_dir():
        return None
    for p in agent_dir.rglob("*"):
        if not p.is_file():
            continue
        if p.name in SKIP_BASENAMES or p.name.endswith(".bak"):
            continue
        try:
            st = p.stat()
        except OSError:
            continue
        if p.name.endswith("-wal") and st.st_size == 0:
            continue
        rel = str(p.relative_to(agent_dir))
        best = _consider(st.st_mtime, f"agents/{agent_dir.name}/{rel}", best)
    return best


def store_db_latest_ts(agent_dir: Path):
    db = agent_dir / "store.db"
    if not db.exists():
        return None
    best = None
    try:
        con = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    except Exception:
        return None
    try:
        try:
            for (entry,) in con.execute("SELECT entry FROM transcript_entries"):
                try:
                    obj = json.loads(entry) if isinstance(entry, str) else None
                except Exception:
                    continue
                if not isinstance(obj, dict):
                    continue
                ts = obj.get("timestampMs")
                if isinstance(ts, (int, float)) and ts > 1e11:
                    best = _consider(ts / 1000.0, f"agents/{agent_dir.name}/store.db#transcript_entries", best)
        except Exception:
            pass
        try:
            row = con.execute("SELECT value FROM kv WHERE key='unreadState'").fetchone()
            if row:
                obj = json.loads(row[0])
                for kk in ("lastActivityAt", "lastUnreadActivityAt", "lastViewedAt"):
                    ts = obj.get(kk) or 0
                    if isinstance(ts, (int, float)) and ts > 1e11:
                        best = _consider(ts / 1000.0, f"agents/{agent_dir.name}/store.db#unreadState.{kk}", best)
        except Exception:
            pass
        try:
            row = con.execute("SELECT value FROM kv WHERE key='lastTurnSettlement'").fetchone()
            if row:
                obj = json.loads(row[0])
                ts = obj.get("settledAtMs")
                if isinstance(ts, (int, float)) and ts > 1e11:
                    best = _consider(ts / 1000.0, f"agents/{agent_dir.name}/store.db#lastTurnSettlement", best)
        except Exception:
            pass
    finally:
        con.close()
    return best


def automation_latest(agent_dir: Path):
    autod = agent_dir / "automations"
    best = None
    runs = 0
    if not autod.is_dir():
        return None, 0
    for auto_json in autod.glob("*/automation.json"):
        try:
            data = json.loads(auto_json.read_text())
        except Exception:
            continue
        lr = data.get("lastRunAt")
        if isinstance(lr, (int, float)) and lr > 1e11:
            best = _consider(lr / 1000.0, f"agents/{agent_dir.name}/automations/{auto_json.parent.name}/automation.json#lastRunAt", best)
    for runs_path in autod.glob("*/runs.json"):
        try:
            raw = json.loads(runs_path.read_text())
        except Exception:
            continue
        entries = raw if isinstance(raw, list) else (raw.get("runs") or raw.get("entries") or [])
        if not isinstance(entries, list):
            continue
        runs += len(entries)
        for e in entries:
            if not isinstance(e, dict):
                continue
            sa = e.get("startedAt") or e.get("started_at") or e.get("endedAt")
            if isinstance(sa, (int, float)) and sa > 1e11:
                best = _consider(sa / 1000.0, f"agents/{agent_dir.name}/automations/{runs_path.parent.name}/runs.json", best)
            elif isinstance(sa, (int, float)) and sa > 1e9:
                best = _consider(float(sa), f"agents/{agent_dir.name}/automations/{runs_path.parent.name}/runs.json", best)
    return best, runs


def _collect_one(d: Path, trans_dir: Path) -> dict:
    prof = json.loads((d / "profile.json").read_text())
    aid = d.name
    name = prof.get("name") or aid
    counts: Counter = Counter()
    size = 0
    tp = trans_dir / aid / f"{aid}.jsonl"
    if tp.exists():
        st = tp.stat()
        size = st.st_size
        with tp.open() as f:
            for line in f:
                try:
                    o = json.loads(line)
                except Exception:
                    continue
                r = o.get("role") if isinstance(o, dict) else None
                if r in ("user", "assistant", "tool"):
                    counts[r] += 1
    store = d / "store.db"
    if sum(counts.values()) == 0 and store.exists():
        try:
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
                elif kind and kind != "event":
                    counts["assistant"] += 1
            if rows:
                size = max(size, store.stat().st_size)
        except Exception:
            pass

    best = None
    nd = newest_agent_dir_activity(d)
    if nd:
        best = _consider(nd[0], nd[1], best)
    sd = store_db_latest_ts(d)
    if sd:
        best = _consider(sd[0], sd[1], best)
    ad, auto_runs = automation_latest(d)
    if ad:
        best = _consider(ad[0], ad[1], best)

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
        "last_transcript_activity_pt": _mtime_pt(best[0]) if best else None,
        "activity_source": best[1] if best else None,
        "source_mtime_epoch": best[0] if best else None,
        "automation_runs": auto_runs,
        "last_automation_started_pt": _mtime_pt(ad[0]) if ad else None,
        "missing_transcript": best is None and sum(counts.values()) == 0,
        "missing_agent_dir": False,
        "stale": False,
        "stale_reason": None,
    }


def jev_route_stats(now: datetime | None = None, log_dir: Path = JEV_LOG_DIR) -> dict | None:
    """Count jev-route calls from log filenames (UTC stamp + gate). None if dir absent."""
    if not log_dir.is_dir():
        return None
    now_ts = (now or datetime.now(timezone.utc)).timestamp()
    total = last_24h = last_7d = 0
    by_gate: dict[str, int] = {}
    newest = None
    for p in log_dir.iterdir():
        m = _JEV_LOG_RE.match(p.name)
        if not m or not p.is_file():
            continue
        try:
            dt = datetime.strptime(m.group(1), "%Y%m%dT%H%M%S").replace(tzinfo=timezone.utc)
        except ValueError:
            continue
        ts = dt.timestamp() + (int(m.group(2)) / 1000.0 if m.group(2) else 0.0)
        gate = m.group(3) or "untagged"
        total += 1
        by_gate[gate] = by_gate.get(gate, 0) + 1
        age_h = (now_ts - ts) / 3600.0
        last_24h += age_h <= 24.0
        last_7d += age_h <= 24.0 * 7
        newest = _consider(ts, f"jev/logs/{p.name}", newest)
    return {
        "source": JEV_SOURCE_LABEL,
        "log_dir": str(log_dir),
        "total": total,
        "last_24h": int(last_24h),
        "last_7d": int(last_7d),
        "by_gate": dict(sorted(by_gate.items(), key=lambda kv: (-kv[1], kv[0]))),
        "newest_log": newest[1] if newest else None,
        "newest_log_epoch": newest[0] if newest else None,
        "newest_log_pt": _mtime_pt(newest[0]) if newest else None,
    }


def apply_jev_route_logs(bots: list[dict], now: datetime | None = None) -> list[dict]:
    """Jev last-activity = newer of jev-route logs / chat folder; label 'jev-route logs'."""
    calls = jev_route_stats(now)
    if calls is None:
        return bots
    for b in bots:
        if (b.get("id") or NAME_TO_ID.get(b.get("name") or "")) != JEV_ID:
            continue
        chat_ts, chat_src = b.get("source_mtime_epoch"), b.get("activity_source")
        log_ts = calls.get("newest_log_epoch")
        if log_ts is not None and (chat_ts is None or log_ts > float(chat_ts)):
            win_ts, win_src = log_ts, calls.get("newest_log")
        else:
            win_ts, win_src = chat_ts, chat_src
        b["chat_folder_last_pt"] = _mtime_pt(float(chat_ts)) if chat_ts is not None else None
        b["chat_folder_source"] = chat_src
        b["source_mtime_epoch"] = win_ts
        b["last_transcript_activity_pt"] = _mtime_pt(float(win_ts)) if win_ts is not None else None
        b["activity_source"] = JEV_SOURCE_LABEL
        b["activity_source_detail"] = win_src
        b["jev_calls"] = calls
    return bots


def _is_jev(b: dict) -> bool:
    return (b.get("id") or NAME_TO_ID.get(b.get("name") or "")) == JEV_ID


def apply_source_freshness(bots: list[dict], now: datetime | None = None) -> list[str]:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    now_ts = now.timestamp()
    fresh_exists = any(
        isinstance(b.get("source_mtime_epoch"), (int, float))
        and (now_ts - float(b["source_mtime_epoch"])) / 3600.0 <= SOURCE_STALE_AFTER_HOURS
        for b in bots
    )
    problems = []
    for b in bots:
        if b.get("missing_agent_dir"):
            b["stale"] = True
            b["stale_reason"] = f"roster agent dir missing: agents/{b.get('id')}"
            problems.append(f"{b.get('name')}(missing_dir)")
            continue
        age = b.get("source_mtime_epoch")
        if age is None:
            b["stale"] = True
            b["stale_reason"] = "no activity source under agents/<id>/ (or client replica)"
            problems.append(f"{b.get('name')}(no_source)")
            continue
        age_h = (now_ts - float(age)) / 3600.0
        b["source_age_hours"] = round(age_h, 1)
        if _is_jev(b):
            # On-demand: source_mtime_epoch = max(jev-route log, chat folder) → both >7d.
            if age_h > JEV_STALE_AFTER_HOURS:
                b["stale"] = True
                b["stale_reason"] = (
                    f"jev-route logs and chat folder both >{JEV_STALE_AFTER_HOURS:.0f}h old "
                    f"(newest {age_h:.0f}h)"
                )
                problems.append(f"{b.get('name')}({age_h:.0f}h)")
            else:
                b["stale"] = False
                b["stale_reason"] = None
            continue
        if fresh_exists and age_h > SOURCE_STALE_AFTER_HOURS:
            b["stale"] = True
            b["stale_reason"] = (
                f"source {b.get('activity_source')} is {age_h:.0f}h old "
                f"(>{SOURCE_STALE_AFTER_HOURS:.0f}h) while other bots are fresh"
            )
            problems.append(f"{b.get('name')}({age_h:.0f}h)")
        else:
            b["stale"] = False
            b["stale_reason"] = None
    return problems


def normalize_bots(bots: list[dict]) -> list[dict]:
    bots = list(bots)
    have = {b.get("name") for b in bots}
    for name in GROK_ORDER:
        if name not in have:
            bots.append(empty_bot(name))
    bots = [b for b in bots if b.get("name") not in GROK_SKIP_NAMES]
    # Drop unknown non-roster agents (keep roster + any already named in ORDER)
    bots = [b for b in bots if b.get("name") in set(GROK_ORDER)]
    rank = {n: i for i, n in enumerate(GROK_ORDER)}
    bots.sort(key=lambda b: (rank.get(b.get("name"), 99), b.get("name") or ""))
    fleet_at = sum((b.get("messages") or {}).get("assistant_tool") or 0 for b in bots)
    for b in bots:
        at = (b.get("messages") or {}).get("assistant_tool") or 0
        b["share_assistant_tool_pct"] = round(100.0 * at / fleet_at, 1) if fleet_at else 0.0
        b.setdefault("stale", False)
        b.setdefault("stale_reason", None)
        b.setdefault("activity_source", None)
        b.setdefault("source_mtime_epoch", None)
        b.setdefault("missing_agent_dir", False)
    return bots


def build_payload(bots: list[dict], source: str, now: datetime | None = None, problems: list[str] | None = None) -> dict:
    now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    problems = list(problems or [])
    return {
        "ok": len(problems) == 0,
        "source": source,
        "note": GROK_NOTE,
        "collected_at_pt": now.astimezone(PT).strftime("%Y-%m-%d %H:%M:%S %Z"),
        "collected_at_utc": now.strftime("%Y-%m-%dT%H:%M:%SZ"),
        "bots": bots,
        "fleet_messages_total": sum(b["messages"]["total"] for b in bots),
        "fleet_assistant_tool_total": sum(b["messages"]["assistant_tool"] for b in bots),
        "links": dict(GROK_LINKS),
        "freshness": {
            "stale_after_hours": SOURCE_STALE_AFTER_HOURS,
            "stale_or_missing": problems,
        },
    }


def collect_box_bots(agents_dir: Path = BOX_AGENTS, trans_dir: Path = BOX_TRANS) -> list[dict] | None:
    if not agents_dir.exists():
        return None
    bots = []
    seen = set()
    for d in sorted(agents_dir.iterdir()):
        if not d.is_dir() or not (d / "profile.json").exists():
            continue
        try:
            b = _collect_one(d, trans_dir)
        except Exception as e:
            print(f"collect_grok_box_activity: skip {d.name}: {e}", file=sys.stderr)
            continue
        if b.get("name") in GROK_SKIP_NAMES:
            continue
        bots.append(b)
        seen.add(d.name)
    for rid, rname in ROSTER_IDS.items():
        if rid not in seen:
            bots.append({**empty_bot(rname), "id": rid, "missing_agent_dir": not (agents_dir / rid).is_dir()})
    bots = normalize_bots(bots)
    apply_jev_route_logs(bots)
    apply_source_freshness(bots)
    return bots


# ── Mac client transcript replicas (live UI clocks) ─────────────────────────

def _b32_decode_name(name: str) -> bytes | None:
    s = name.replace(".blob", "").upper()
    pad = (-len(s)) % 8
    try:
        return base64.b32decode(s + "=" * pad)
    except Exception:
        return None


def client_persistence_root() -> Path:
    return Path.home() / "Library/Application Support/Grok Bot/sand-client-persistence"


def read_client_replica_activity(agent_id: str) -> tuple[float | None, str | None]:
    """Return (epoch_seconds, source_label) from Mac Grok Bot transcript replica."""
    root = client_persistence_root()
    if not root.exists():
        return None, None
    needle = f"transcript.replicas.{agent_id}".encode()
    best_ts = None
    best_label = None
    for blob in root.glob("*.blob"):
        dec = _b32_decode_name(blob.name)
        if not dec or needle not in dec:
            continue
        try:
            data = json.loads(blob.read_text())
            val = data.get("value") or {}
            entries = val.get("entries") or []
        except Exception:
            continue
        ts = None
        if isinstance(entries, list):
            for e in reversed(entries):
                if not isinstance(e, dict):
                    continue
                for kk in ("timestampMs", "createdAt", "at", "persistedAt"):
                    v = e.get(kk)
                    if isinstance(v, (int, float)) and v > 1e11:
                        ts = v / 1000.0
                        break
                    if isinstance(v, (int, float)) and v > 1e9:
                        ts = float(v)
                        break
                if ts:
                    break
        if ts is None:
            # fall back to blob mtime
            ts = blob.stat().st_mtime
        label = f"mac-client-replica:{agent_id}"
        if best_ts is None or ts > best_ts:
            best_ts, best_label = ts, label
    return best_ts, best_label


def overlay_client_replicas(bots: list[dict]) -> list[dict]:
    """Prefer Mac client replica last-activity when newer than box source."""
    for b in bots:
        aid = b.get("id") or NAME_TO_ID.get(b.get("name") or "")
        if not aid:
            continue
        ts, label = read_client_replica_activity(aid)
        if ts is None:
            continue
        cur = b.get("source_mtime_epoch")
        if cur is None or float(ts) > float(cur):
            b["source_mtime_epoch"] = float(ts)
            b["last_transcript_activity_pt"] = _mtime_pt(float(ts))
            if _is_jev(b) and b.get("jev_calls"):
                b["activity_source_detail"] = label  # keep "jev-route logs" label
            else:
                b["activity_source"] = label
            b["missing_transcript"] = False
    apply_source_freshness(bots)
    return bots


def parse_collected_at(data: dict) -> datetime | None:
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
        parts = raw.strip().split()
        base = " ".join(parts[:2])
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
            try:
                return datetime.strptime(base, fmt).replace(tzinfo=PT).astimezone(timezone.utc)
            except ValueError:
                continue
    return None


def staleness(data: dict | None, now: datetime | None = None) -> tuple[bool, str | None]:
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
    ap.add_argument("-o", "--output", default="-")
    ap.add_argument("--agents-dir", type=Path, default=BOX_AGENTS)
    ap.add_argument("--transcripts-dir", type=Path, default=BOX_TRANS)
    args = ap.parse_args(argv)
    bots = collect_box_bots(args.agents_dir, args.transcripts_dir)
    if bots is None:
        print(f"collect_grok_box_activity: {args.agents_dir} not found — run this on the box", file=sys.stderr)
        return 2
    bots = overlay_client_replicas(bots)
    problems = [f"{b.get('name')}({b.get('stale_reason')})" for b in bots if b.get("stale")]
    # compact labels like box collector
    problems = []
    for b in bots:
        if not b.get("stale"):
            continue
        if b.get("missing_agent_dir"):
            problems.append(f"{b.get('name')}(missing_dir)")
        elif b.get("source_mtime_epoch") is None:
            problems.append(f"{b.get('name')}(no_source)")
        else:
            problems.append(f"{b.get('name')}({b.get('source_age_hours')}h)")
    payload = build_payload(
        bots,
        "box agents/<id>/ live mtimes + store.db (+ Mac client replicas when newer)",
        problems=problems,
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
    if problems:
        print("STALE_SOURCES: " + ", ".join(problems))
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
