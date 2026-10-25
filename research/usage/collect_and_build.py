#!/usr/bin/env python3
"""Collect Mac CLI model-usage snapshots and build a Field Brief–styled dashboard."""

from __future__ import annotations

import colorsys
import json
import math
import os
import re
import shutil
import sqlite3
import ssl
import subprocess
import tempfile
import time
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

try:
    import tomllib  # Python 3.11+
except ImportError:  # /usr/bin/python3 on the Mac is 3.9 — parse_kimi_config() falls back to a line scan
    tomllib = None

HERE = Path(__file__).resolve().parent
PT = ZoneInfo("America/Los_Angeles")
HUB_USAGE = Path.home() / "caohy1988.github.io/research/usage"
PACKS = Path.home() / "Documents/agent-analytics-research/packs"
WIKI_DAILY = Path.home() / "Documents/agent-context/Wiki/Daily"
HUNT = Path.home() / "Documents/agent-context/Hunt/agent-analytics"
CODEX_AUTH = Path.home() / ".codex/auth.json"
CLAUDE_BIN = Path.home() / ".local/bin/claude"
MUSE_BIN = Path.home() / ".local/bin/muse"
MUSE_AUTH = Path.home() / ".config/muse/auth.json"
MUSE_SHARE = Path.home() / ".local/share/muse"
MUSE_SETTINGS = Path.home() / ".config/muse/settings.json"
MUSE_PLAN = "Max"  # user-stated 2026-10-12; Muse exposes no plan API
MUSE_USAGE_DAYS = 7
MUSE_USAGE_MAX_COUNTER = 2 ** 64 - 1  # support unsigned 64-bit producer counters
MUSE_USAGE_MAX_FILE_BYTES = 200 * 1024 * 1024  # skip + flag session logs larger than this
MUSE_USAGE_TIME_BUDGET_S = 20.0  # on exceed, the usage scan stops and marks partial (deadline checked on every scanned line/parse and between files)
DSH_BIN = Path.home() / ".local/bin/dsh"
DSH_DIR = Path.home() / ".dsh"
QWEN_BIN = Path("/usr/local/bin/qwen")
OPENCODE_BIN = Path("/usr/local/bin/opencode")
GROK_CACHE = HERE / "grok_box_activity.json"

# Pacing (report-only): each quota window's published used % next to the share of the window
# elapsed at the reading. Nothing reads these to hold or throttle a launch. The two marks are
# the token-weather Lab card's author defaults, not measured.
PACE_AHEAD_POINTS = 15.0  # marked when used % runs more than this many points ahead of elapsed %
PACE_USED_MARK_PCT = 90.0  # marked when used % is past this
PACE_SKEW_S = 300  # a reset up to this far past one full window still reads as "window just started"
FIVE_HOURS_S = 5 * 3600
SEVEN_DAYS_S = 7 * 86400

# Box collection + freshness logic is shared with the box-side collector script.
from collect_grok_box_activity import (  # noqa: E402
    BOX_TRANS,
    GROK_LINKS,
    GROK_NOTE,
    GROK_ORDER,
    GROK_ROLES,
    GROK_SKIP_NAMES,
    SOURCE_STALE_AFTER_HOURS,
    STALE_AFTER_HOURS,
    apply_manage_receipts,
    apply_source_freshness,
    build_payload,
    collect_box_bots,
    empty_bot as _empty_bot,
    finite_tree,
    ms_to_pt,
    normalize_bots,
    overlay_client_replicas,
    staleness,
)

GROK_COLORS = ["#0f766e", "#e87324", "#2563eb", "#7c3aed", "#db2777"]


def now_pt() -> datetime:
    return datetime.now(PT)


def iso_pt(dt: datetime | None = None) -> str:
    d = dt or now_pt()
    if d.tzinfo is None:
        d = d.replace(tzinfo=PT)
    return d.astimezone(PT).strftime("%Y-%m-%d %H:%M:%S %Z")


def bar_class(pct: float | None, blocked: bool = False) -> str:
    if blocked:
        return "bad"
    if pct is None:
        return "unk"
    if pct >= 90:
        return "bad"
    if pct >= 70:
        return "warn"
    return "ok"


def redact(obj):
    if isinstance(obj, dict):
        out = {}
        for k, v in obj.items():
            lk = k.lower()
            if any(x in lk for x in ("email", "user_id", "account_id", "access_token", "refresh_token", "id_token")):
                out[k] = "[REDACTED]"
            else:
                out[k] = redact(v)
        return out
    if isinstance(obj, list):
        return [redact(x) for x in obj]
    return obj


# Error strings end up in the public snapshot.json / index.html. subprocess.TimeoutExpired and
# CalledProcessError stringify their full argv, and the curl calls carry "Authorization: Bearer …"
# there — so exceptions go through safe_error(), and main() scrubs the whole tree once more.
_SECRET_PATTERNS = (
    (re.compile(r"(?i)(authorization['\"]?\s*[:=]\s*['\"]?)(?!(?:(?:bearer|basic|token)\s+)?\[REDACTED\])(?:(bearer|basic|token)\s+)?[^\s'\",\]\)}]+"), r"\1\2 [REDACTED]"),
    (re.compile(r"(?i)\b(bearer)\s+(?!\[REDACTED\])[^\s'\",\]\)}]+"), r"\1 [REDACTED]"),
    (re.compile(r"eyJ[\w-]{5,}\.[\w-]{5,}\.[\w-]{5,}"), "[REDACTED]"),  # JWT, including inside identifiers
    (re.compile(r"(?i)sk-[\w-]{12,}"), "[REDACTED]"),
    (re.compile(r"(?i)\b((?:api[_-]?key|access[_-]?token|refresh[_-]?token|id[_-]?token)['\"]?\s*[:=]\s*['\"]?)(?!\[REDACTED\])[^\s'\",\]\)}]+"), r"\1[REDACTED]"),
)


def scrub_secrets(text, secrets=()) -> str:
    """Strip credentials from free text (known literal values first, then Bearer/JWT/key patterns)."""
    text = str(text)
    for sec in secrets:
        if sec and len(str(sec)) >= 6:
            text = text.replace(str(sec), "[REDACTED]")
    for pat, repl in _SECRET_PATTERNS:
        text = pat.sub(repl, text)
    return text.replace("  [REDACTED]", " [REDACTED]")


def safe_error(e: BaseException, secrets=(), limit: int = 300) -> str:
    """Publishable description of an exception — never the command line."""
    if isinstance(e, (subprocess.TimeoutExpired, subprocess.CalledProcessError)):
        cmd = e.cmd[0] if isinstance(e.cmd, (list, tuple)) and e.cmd else "command"
        name = Path(str(cmd).split()[0]).name if str(cmd).strip() else "command"
        if isinstance(e, subprocess.TimeoutExpired):
            return f"{name} timeout after {e.timeout:g}s"
        return f"{name} failed (exit {e.returncode})"
    return scrub_secrets(e, secrets)[:limit]


def scrub_tree(obj, secrets=()):
    """Scrub public values and dynamic dictionary keys before serialization/rendering."""
    if isinstance(obj, dict):
        return {scrub_secrets(k, secrets) if isinstance(k, str) else k: scrub_tree(v, secrets)
                for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [scrub_tree(x, secrets) for x in obj]
    if isinstance(obj, str):
        return scrub_secrets(obj, secrets)
    return obj


def ts_to_pt(ts: int | float | None) -> str | None:
    if ts is None:
        return None
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc).astimezone(PT).strftime(
            "%Y-%m-%d %H:%M %Z"
        )
    except Exception:
        return None


def short_mtime(s: str | None) -> str:
    if not s:
        return "—"
    # "2026-09-07 08:55:09 PDT" -> "Sep 7, 08:55 PT"
    m = re.match(r"(\d{4})-(\d{2})-(\d{2}) (\d{2}):(\d{2})", s)
    if not m:
        return s
    y, mo, d, hh, mm = m.groups()
    months = "Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split()
    return f"{months[int(mo)-1]} {int(d)}, {hh}:{mm} PT"


def first_clause(text: str | None, limit: int = 120) -> str:
    if not text:
        return "—"
    t = text.strip()
    # Prefer first semicolon-separated clause if short enough
    if ";" in t:
        head = t.split(";", 1)[0].strip()
        if len(head) <= limit:
            return head
    if len(t) <= limit:
        return t
    return t[: limit - 1] + "…"


# ── pacing (report-only) ────────────────────────────────────────────────────


def _iso_utc(dt: datetime | None) -> str | None:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ") if dt else None


def _parse_iso(s) -> datetime | None:
    """Aware datetime from an ISO-8601 string; None when naive or unparseable."""
    if not s:
        return None
    # Seconds are enough here, and Python 3.9 only parses 3- or 6-digit fractions.
    t = re.sub(r"(\d{2}:\d{2}:\d{2})\.\d+", r"\1", str(s).strip()).replace("Z", "+00:00")
    try:
        dt = datetime.fromisoformat(t)
    except ValueError:
        return None
    return dt if dt.tzinfo else None


def _epoch_utc(ts) -> datetime | None:
    try:
        return datetime.fromtimestamp(float(ts), tz=timezone.utc)
    except (TypeError, ValueError, OverflowError, OSError):
        return None


def window_seconds_from_name(name) -> int | None:
    """Window length implied by a quota label ('Current session', 'Weekly Limit Remaining', …)."""
    n = str(name or "").lower()
    if re.search(r"\bsession\b|\bfive[ -]?hours?\b|\b5[ -]?h(?:ours?|r)?\b", n):
        return FIVE_HOURS_S
    if re.search(r"\bweek(?:ly)?\b|\b7[ -]?days?\b", n):
        return SEVEN_DAYS_S
    return None


_UNIT_S = {"SECOND": 1, "MINUTE": 60, "HOUR": 3600, "DAY": 86400}


def window_seconds_from_unit(duration, time_unit) -> int | None:
    """Window length from an API {duration, timeUnit} pair, e.g. (300, 'TIME_UNIT_MINUTE')."""
    unit = _UNIT_S.get(str(time_unit or "").upper().rsplit("_", 1)[-1].rstrip("S"))
    try:
        secs = int(float(duration) * unit) if unit else 0
    except (TypeError, ValueError, OverflowError):
        return None
    return secs if secs > 0 else None


_RESET_TEXT = re.compile(
    r"^(?:(?P<mon>[A-Za-z]{3})[a-z]*\.?\s+(?P<day>\d{1,2})(?:\s*,\s*|\s+at\s+|\s+))?"
    r"(?P<h>\d{1,2})(?::(?P<m>\d{2}))?\s*(?P<ap>[ap]m)\s*(?:\((?P<tz>[^()]+)\))?$",
    re.I,
)
_MONTHS = "jan feb mar apr may jun jul aug sep oct nov dec".split()


def parse_reset_text(text, now: datetime) -> datetime | None:
    """Reset time from `/usage` text such as 'Oct 13 at 2:59pm (America/Los_Angeles)'.

    The text carries no year: take the one that puts the reset nearest `now`. Time-only
    text means the next such time. No zone in parentheses means PT.
    """
    m = _RESET_TEXT.match(str(text or "").strip())
    if not m:
        return None
    hour, minute = int(m["h"]), int(m["m"] or 0)
    if not (1 <= hour <= 12 and minute < 60):
        return None
    hour = hour % 12 + (12 if m["ap"].lower() == "pm" else 0)
    try:
        tz = ZoneInfo(m["tz"].strip()) if m["tz"] else PT
    except Exception:
        return None
    local_now = now.astimezone(tz)
    if not m["mon"]:
        at = local_now.replace(hour=hour, minute=minute, second=0, microsecond=0)
        return at if at > local_now else at + timedelta(days=1)
    mon = m["mon"].lower()
    if mon not in _MONTHS:
        return None
    candidates = []
    for year in (local_now.year - 1, local_now.year, local_now.year + 1):
        try:
            candidates.append(datetime(year, _MONTHS.index(mon) + 1, int(m["day"]), hour, minute, tzinfo=tz))
        except ValueError:
            pass
    return min(candidates, key=lambda c: abs(c - now), default=None)


def _pace_na(reason: str) -> dict:
    return {"status": "n/a", "reason": reason, "marked": False}


def pacing(used_percent, reset_at: datetime | None, window_seconds, now: datetime) -> dict:
    """Share of a rolling window used vs share of it elapsed at `now` (report-only).

    Marked when used % runs more than PACE_AHEAD_POINTS ahead of elapsed %, or is past
    PACE_USED_MARK_PCT. Values stay unrounded, so the comparisons and the ratio see the exact
    figures; pacing_html rounds for display only. A window without a reset time, a length or
    a reading is 'n/a'.
    """
    if reset_at is None or reset_at.tzinfo is None:
        return _pace_na("no window time")
    try:
        window = float(window_seconds)
    except (TypeError, ValueError, OverflowError):
        window = math.nan
    if not (math.isfinite(window) and window > 0):
        return _pace_na("unknown window length")
    try:
        used = float(used_percent)
    except (TypeError, ValueError, OverflowError):
        used = math.nan
    if not math.isfinite(used):  # NaN/inf would also leak into snapshot.json as non-JSON tokens
        return _pace_na("no usage reading")
    left = (reset_at - now).total_seconds()
    if left <= 0:
        return _pace_na("window already reset")
    if left > window + PACE_SKEW_S:
        return _pace_na("reset time outside window")
    elapsed = (max(0.0, window - left) / window) * 100.0
    ahead = used - elapsed
    if not all(math.isfinite(v) for v in (elapsed, ahead)):
        return _pace_na("invalid derived reading")
    ratio = used / elapsed if elapsed > 0 else None  # a huge reading over a sliver of elapsed time overflows
    reasons = []
    if ahead > PACE_AHEAD_POINTS:
        reasons.append(f"more than {PACE_AHEAD_POINTS:g} pts ahead of the clock")
    if used > PACE_USED_MARK_PCT:
        reasons.append(f"past {PACE_USED_MARK_PCT:g}% used")
    return {
        "status": "ok",
        "used_pct": used,
        "elapsed_pct": elapsed,
        "ahead_points": ahead,
        "ratio": ratio if ratio is not None and math.isfinite(ratio) else None,
        "marked": bool(reasons),
        "mark_reasons": reasons,
    }


def add_pacing(seat: dict, now: datetime | None = None) -> dict:
    """Attach a report-only `pacing` dict to each quota bar of one Mac CLI seat, as of `now`.

    A bar whose shown `used_percent` was rounded by its collector also carries
    `used_percent_unrounded`; pacing compares that one."""
    if not isinstance(seat, dict):
        return seat
    now = now or datetime.now(timezone.utc)
    for key in ("bars", "additional_rate_limits"):
        for b in seat.get(key) or []:
            if isinstance(b, dict):
                used = b.get("used_percent_unrounded")
                b["pacing"] = pacing(
                    b.get("used_percent") if used is None else used,
                    _parse_iso(b.get("reset_at")), b.get("window_seconds"), now,
                )
    return seat


# ── collectors ──────────────────────────────────────────────────────────────


def collect_claude() -> dict:
    out: dict = {"ok": False, "source": "claude -p /usage", "bars": [], "raw_excerpt": ""}
    try:
        proc = subprocess.run(
            [
                str(CLAUDE_BIN),
                "-p",
                "/usage",
                "--permission-mode",
                "bypassPermissions",
                "--output-format",
                "text",
            ],
            capture_output=True,
            text=True,
            timeout=90,
            stdin=subprocess.DEVNULL,
        )
        text = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        lines = [ln for ln in text.splitlines() if ln.strip()]
        body = "\n".join(lines)
        out["raw_excerpt"] = body[:2500]
        pat = re.compile(
            r"^(Current session|Current week \(all models\)|Current week \(Fable\)):\s*"
            r"(\d+(?:\.\d+)?)%\s*used\s*·\s*resets\s*(.+)$",
            re.I,
        )
        now = now_pt()
        for ln in lines:
            m = pat.match(ln.strip())
            if not m:
                continue
            label, pct_s, reset = m.group(1), float(m.group(2)), m.group(3).strip()
            out["bars"].append(
                {
                    "label": label,
                    "used_percent": pct_s,
                    "reset": reset,
                    "tone": bar_class(pct_s),
                    "reset_at": _iso_utc(parse_reset_text(reset, now)),
                    "window_seconds": window_seconds_from_name(label),
                }
            )
        out["ok"] = bool(out["bars"])
        out["fable_blocked"] = any(
            b["label"].lower().startswith("current week (fable)") and b["used_percent"] >= 100
            for b in out["bars"]
        )
    except Exception as e:
        out["error"] = safe_error(e)
    return out


def _codex_window(win: dict) -> dict:
    """reset_at (ISO UTC) + window_seconds from one wham/usage window object."""
    reset = _epoch_utc(win.get("reset_at"))
    if reset is None:
        try:
            reset = datetime.now(timezone.utc) + timedelta(seconds=float(win["reset_after_seconds"]))
        except (KeyError, TypeError, ValueError, OverflowError):
            reset = None
    try:
        length = int(win.get("limit_window_seconds") or 0)
    except (TypeError, ValueError, OverflowError):
        length = 0
    return {"reset_at": _iso_utc(reset), "window_seconds": length if length > 0 else None}


def _codex_bar(label: str, win, blocked: bool = False, **extra) -> dict:
    """One quota bar from a wham/usage window object (primary or secondary)."""
    win = win if isinstance(win, dict) else {}
    fields = _codex_window(win)
    reset = _parse_iso(fields["reset_at"])
    pct = win.get("used_percent")
    return {
        "label": label,
        "used_percent": pct,
        "reset": reset.astimezone(PT).strftime("%Y-%m-%d %H:%M %Z") if reset else None,
        "tone": bar_class(pct, blocked=blocked),
        **extra,
        **fields,
    }


def codex_windows(data: dict) -> tuple:
    """(bars, additional) for every window in a wham/usage payload: the main limit's primary
    and secondary window, then each additional limit's. A secondary window only when sent."""
    rl = data.get("rate_limit") or {}
    bars = [
        _codex_bar(
            "Primary window", rl.get("primary_window"), blocked=bool(rl.get("limit_reached")),
            allowed=rl.get("allowed"), limit_reached=rl.get("limit_reached"),
        )
    ]
    if isinstance(rl.get("secondary_window"), dict) and rl["secondary_window"]:
        bars.append(_codex_bar("Secondary window", rl["secondary_window"]))
    addl = []
    for item in data.get("additional_rate_limits") or []:
        if not isinstance(item, dict):
            continue
        arl, name = item.get("rate_limit") or {}, item.get("limit_name")
        addl.append(_codex_bar(f"{name} · primary window", arl.get("primary_window"), limit_name=name))
        if isinstance(arl.get("secondary_window"), dict) and arl["secondary_window"]:
            addl.append(_codex_bar(f"{name} · secondary window", arl["secondary_window"], limit_name=name))
    return bars, addl


def collect_codex() -> dict:
    out: dict = {"ok": False, "source": "chatgpt.com/backend-api/wham/usage", "bars": []}
    try:
        auth = json.loads(CODEX_AUTH.read_text())
        token = auth.get("tokens", {}).get("access_token")
        if not token:
            out["error"] = "no access_token in ~/.codex/auth.json"
            return out
        # Prefer curl: macOS Python often fails SSL verify on chatgpt.com (no certifi).
        raw = None
        curl_err = None
        try:
            proc = subprocess.run(
                [
                    "curl",
                    "-sS",
                    "--max-time",
                    "30",
                    "-H",
                    f"Authorization: Bearer {token}",
                    "-H",
                    "User-Agent: usage-dashboard/1.0",
                    "https://chatgpt.com/backend-api/wham/usage",
                ],
                capture_output=True,
                text=True,
                timeout=45,
            )
            if proc.returncode == 0 and (proc.stdout or "").strip().startswith("{"):
                raw = json.loads(proc.stdout)
            else:
                curl_err = scrub_secrets(proc.stderr or proc.stdout or f"curl exit {proc.returncode}", (token,))[:400]
        except Exception as e:
            curl_err = safe_error(e, (token,))
        if raw is None:
            req = urllib.request.Request(
                "https://chatgpt.com/backend-api/wham/usage",
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": "usage-dashboard/1.0",
                },
            )
            try:
                with urllib.request.urlopen(req, timeout=30) as resp:
                    raw = json.loads(resp.read().decode())
            except Exception as e:
                out["error"] = f"curl: {curl_err}; urllib: {safe_error(e, (token,))}"
                # fall back to last good cache if present
                cache = HERE / "codex-usage.json"
                if cache.exists():
                    try:
                        cached = json.loads(cache.read_text())
                        out["ok"] = False
                        out["cached"] = True
                        out["cache_note"] = "serving last cached codex-usage.json after live fetch fail"
                        data = cached
                        # reuse parse path below by setting raw
                        raw = cached
                        out["error"] = out.get("error")
                    except Exception:
                        return out
                else:
                    return out
        data = redact(raw)
        out["plan_type"] = data.get("plan_type")
        out["bars"], addl = codex_windows(data)
        model_usage = data.get("model_usage") or {}
        astra = model_usage.get("gpt-6-astra") or {}
        out["gpt6_astra"] = {
            "available": astra.get("available"),
            "available_at": astra.get("available_at"),
            "credits_would_enable": astra.get("credits_would_enable"),
        }
        credits = data.get("credits") or {}
        out["credits"] = {
            "has_credits": credits.get("has_credits"),
            "balance": credits.get("balance"),
            "unlimited": credits.get("unlimited"),
            "overage_limit_reached": credits.get("overage_limit_reached"),
        }
        out["additional_rate_limits"] = addl
        out["snapshot_redacted"] = {
            "plan_type": out["plan_type"],
            "rate_limit": data.get("rate_limit"),
            "model_usage": model_usage,
            "credits": out["credits"],
            "additional_rate_limits": data.get("additional_rate_limits"),
        }
        # Live fetch success clears prior error; cached fallback stays ok=False
        if out.get("cached"):
            out["ok"] = False
        else:
            out["ok"] = True
            out.pop("error", None)
    except Exception as e:
        out["error"] = safe_error(e)
    return out


_KIMI_MODEL_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,95}")
_KIMI_EFFORT = re.compile(r"[a-z][a-z0-9_-]{0,15}")
_TOML_BARE_KEY = re.compile(r"[A-Za-z0-9_-]+")
_TOML_SCALAR = re.compile(r"\d{4}-\d{2}-\d{2} \d{2}:\d{2}[^\s,\]}#]*|[^\s,\]}#]+")  # "date time" or one token
_TOML_ESCAPES = {"b": "\b", "t": "\t", "n": "\n", "f": "\f", "r": "\r", '"': '"', "\\": "\\"}
_TOML_HEX = frozenset("0123456789abcdefABCDEF")


def _toml_escape(s: str, i: int) -> tuple:
    """The basic-string escape at s[i] (a backslash) -> (text, end). Like tomllib, raises on an unknown
    escape, on a \\u / \\U without exactly 4 / 8 hex digits, and on a code point that is not a Unicode
    scalar value."""
    e = s[i + 1:i + 2]
    if e in ("u", "U"):
        k = 4 if e == "u" else 8
        digits = s[i + 2:i + 2 + k]
        if len(digits) != k or not _TOML_HEX.issuperset(digits):
            raise ValueError("bad unicode escape")
        cp = int(digits, 16)
        if 0xD800 <= cp <= 0xDFFF or cp > 0x10FFFF:
            raise ValueError("escape is not a Unicode scalar value")
        return chr(cp), i + 2 + k
    if e not in _TOML_ESCAPES:
        raise ValueError("bad escape")
    return _TOML_ESCAPES[e], i + 2


def _toml_multiline_basic(body: str) -> str:
    """Decode a multi-line basic string body (first newline already trimmed, CRLF already LF): escapes,
    plus the line-ending backslash, which drops itself and every space, tab and newline after it."""
    out, i, n = [], 0, len(body)
    while i < n:
        if body[i] != "\\":
            out.append(body[i])
            i += 1
            continue
        j = i + 1
        while j < n and body[j] in " \t":
            j += 1
        if j < n and body[j] == "\n":  # line-ending backslash
            while j < n and body[j] in " \t\n":
                j += 1
            i = j
        else:
            s, i = _toml_escape(body, i)
            out.append(s)
    return "".join(out)


def _toml_strings(text: str) -> dict:
    """{key path tuple: str} for every string value of a TOML document — the tomllib fallback for
    Python 3.9. Strings are decoded as tomllib does, multi-line ones included (escapes, line-ending
    backslash, first newline trimmed, CRLF read as LF), so callers validate the decoded value.

    A scanner, not a full validator: it follows [table] headers and bare / quoted / dotted keys, and
    walks every value (multi-line strings, arrays, inline tables) and comment to its end, so nothing
    inside one can be read as a key or a header. Keys under [[array]] headers or inside arrays are not
    collected. Raises on anything it cannot follow, on a bad escape, and on TOML's redefinition errors: a
    key or table defined twice, a table defined both by a header and by keys or a value, a bare CR
    between lines. Not checked (so a broken file may still be read): keys inside [[array]] entries,
    control characters inside strings and comments, an implicit super-table later declared as [[array]].
    """
    found: dict = {}
    assigned: set = set()  # key paths given a value (inline tables included)
    implied: set = set()  # tables created by dotted keys
    tables: set = set()  # [table] headers
    arrays: set = set()  # [[array]] headers
    n, i = len(text), 0

    def newline(i):  # length of the LF / CRLF at i, else 0
        return 1 if text.startswith("\n", i) else 2 if text.startswith("\r\n", i) else 0

    def ws(i, newlines=False):
        while i < n:
            if text[i] in " \t":
                i += 1
            elif newlines and newline(i):
                i += newline(i)
            else:
                break
        return i

    def blank(i):  # spaces, newlines and comments
        i = ws(i, True)
        while text.startswith("#", i):
            i = text.find("\n", i)
            i = n if i < 0 else ws(i, True)
        return i

    def string(i):  # one-line "basic" or 'literal' string at i -> (value, end)
        q, out, i = text[i], [], i + 1
        while i < n and text[i] not in (q, "\n"):
            if q == '"' and text[i] == "\\":
                s, i = _toml_escape(text, i)
                out.append(s)
                continue
            out.append(text[i])
            i += 1
        if not text.startswith(q, i):
            raise ValueError("unterminated string")
        return "".join(out), i + 1

    def multiline(i):  # """...""" or '''...''' at i -> (decoded text, end)
        q, j = text[i], i + 3
        while True:
            j = text.find(q * 3, j)
            if j < 0:
                raise ValueError("unterminated multi-line string")
            k = j
            while q == '"' and text[k - 1] == "\\":
                k -= 1
            if (j - k) % 2 == 0:  # not escaped; up to two more quotes still belong to the string
                end = j + 3
                while end < j + 5 and text.startswith(q, end):
                    end += 1
                body = text[i + 3:end - 3]
                body = body[2:] if body.startswith("\r\n") else body[1:] if body.startswith("\n") else body
                body = body.replace("\r\n", "\n")
                return (_toml_multiline_basic(body) if q == '"' else body), end
            j += 1

    def key(i):  # dotted key at i -> (parts, end after trailing spaces)
        parts = []
        while True:
            i = ws(i)
            if text.startswith(('"', "'"), i):
                part, i = string(i)
            else:
                m = _TOML_BARE_KEY.match(text, i)
                if not m:
                    raise ValueError("bad key")
                part, i = m.group(), m.end()
            parts.append(part)
            i = ws(i)
            if not text.startswith(".", i):
                return tuple(parts), i
            i += 1

    def assign(path, base):  # base: length of the enclosing table's path; path None: not tracked
        if path is None:
            return
        for k in range(base + 1, len(path) + 1):
            p = path[:k]
            if p in assigned or p in tables or p in arrays or k == len(path) and p in implied:
                raise ValueError("key or table defined twice")
        assigned.add(path)
        implied.update(path[:k] for k in range(base + 1, len(path)))

    def value(i, path):  # walk one value at i -> end; a one-line string is collected under path
        if text.startswith(('"', "'"), i):
            s, i = multiline(i) if text.startswith(('"""', "'''"), i) else string(i)
            if path is not None:
                found[path] = s
            return i
        if text.startswith(("[", "{"), i):  # array (nothing collected) or inline table (keys extend path)
            close = "]" if text[i] == "[" else "}"
            i = blank(i + 1)
            while not text.startswith(close, i):
                if close == "]":
                    i = value(i, None)
                else:
                    sub, i = key(i)
                    if not text.startswith("=", i):
                        raise ValueError("bad inline table")
                    full = None if path is None else path + sub
                    assign(full, len(path or ()))
                    i = value(ws(i + 1), full)
                i = blank(i)
                if text.startswith(",", i):
                    i = blank(i + 1)
                elif not text.startswith(close, i):
                    raise ValueError("bad array / inline table")
            return i + 1
        m = _TOML_SCALAR.match(text, i)
        if not m:
            raise ValueError("bad value")
        return m.end()

    scope = ()  # key path of the current [table]; None inside an [[array]] entry
    while True:
        i = blank(i)
        if i >= n:
            return found
        if text.startswith("[", i):
            array = text.startswith("[[", i)
            width = 2 if array else 1
            path, i = key(i + width)
            if not text.startswith("]" * width, i):
                raise ValueError("bad header")
            i += width
            if path in implied or any(path[:k] in assigned for k in range(1, len(path) + 1)):
                raise ValueError("table defined twice")
            if array:
                if path in tables:
                    raise ValueError("table defined twice")
                arrays.add(path)
                scope = None
            elif any(path[:k] in arrays for k in range(1, len(path))):
                scope = None  # a sub-table of an [[array]] entry: neither collected nor tracked
            elif path in tables or path in arrays:
                raise ValueError("table defined twice")
            else:
                tables.add(path)
                scope = path
        else:
            sub, i = key(i)
            if not text.startswith("=", i):
                raise ValueError("expected =")
            full = None if scope is None else scope + sub
            assign(full, len(scope or ()))
            i = value(ws(i + 1), full)
        i = ws(i)
        if text.startswith("#", i):
            i = text.find("\n", i)
            i = n if i < 0 else i
        if i < n and not newline(i):
            raise ValueError("text after a statement")


def parse_kimi_config(text: str, use_tomllib: bool = True) -> dict:
    """Top-level default_model and the [thinking] table's effort from kimi-code's config.toml; a value
    that fails the id / effort regex comes back as None. tomllib when available, else _toml_strings();
    a file either one cannot read sets config_error instead.
    """
    out = {"default_model": None, "effort": None}
    if use_tomllib and tomllib is not None:
        try:
            cfg = tomllib.loads(text)
        except Exception:
            return dict(out, config_error="config.toml is not valid TOML")
        thinking = cfg.get("thinking")
        model = cfg.get("default_model")
        effort = thinking.get("effort") if isinstance(thinking, dict) else None
    else:
        try:
            found = _toml_strings(text)
        except Exception:
            return dict(out, config_error="config.toml could not be parsed")
        model, effort = found.get(("default_model",)), found.get(("thinking", "effort"))
    if isinstance(model, str) and _KIMI_MODEL_ID.fullmatch(model):
        out["default_model"] = model
    if isinstance(effort, str) and _KIMI_EFFORT.fullmatch(effort):
        out["effort"] = effort
    return out


def read_kimi_config() -> dict:
    """Kimi default model + effort from ~/.kimi-code/config.toml (~ resolved per call, like collect_kimi)."""
    out = {"default_model": None, "effort": None, "config_source": "~/.kimi-code/config.toml"}
    try:
        text = (Path.home() / ".kimi-code" / "config.toml").read_text(encoding="utf-8")
    except FileNotFoundError:
        return dict(out, config_error="~/.kimi-code/config.toml not found")
    except Exception:
        return dict(out, config_error="~/.kimi-code/config.toml unreadable")
    out.update(parse_kimi_config(text))
    return out


def collect_kimi() -> dict:
    """Prefer live Kimi Code /usages API; fall back to vault DONE_BLOCKED markers."""
    out: dict = {
        "ok": True,
        "source": "api.kimi.com/coding/v1/usages",
        "status": "unknown",
        "chip": "Unknown",
        "detail": "",
        "reset": None,
        "last_checked": None,
        "used_percent": None,
        "bars": [],
        "evidence": [],
    }
    out.update(read_kimi_config())  # default model + effort ride along on every status path below

    # --- Live API (Bearer from ~/.kimi-code/credentials/kimi-code.json) ---
    cred_path = Path.home() / ".kimi-code" / "credentials" / "kimi-code.json"

    def _fetch_usages(token: str):
        # Prefer curl: Python urllib on this Mac often fails SSL issuer verify for api.kimi.com.
        # Do NOT use curl -f: HTTP 401 must surface so we can refresh the short-lived token.
        try:
            proc = subprocess.run(
                [
                    "curl", "-sS", "--max-time", "20",
                    "-w", "\n__HTTP__%{http_code}",
                    "-H", f"Authorization: Bearer {token}",
                    "-H", "Accept: application/json",
                    "-H", "User-Agent: usage-dashboard",
                    "https://api.kimi.com/coding/v1/usages",
                ],
                capture_output=True,
                text=True,
                timeout=25,
            )
            body = proc.stdout or ""
            http_code = 0
            if "__HTTP__" in body:
                body, code_s = body.rsplit("__HTTP__", 1)
                body = body.rstrip("\n")
                try:
                    http_code = int(code_s.strip())
                except ValueError:
                    http_code = 0
            if proc.returncode == 0 and http_code == 401:
                raise urllib.error.HTTPError(
                    "https://api.kimi.com/coding/v1/usages",
                    401,
                    "Unauthorized",
                    hdrs=None,
                    fp=None,
                )
            if proc.returncode == 0 and 200 <= http_code < 300 and body.strip():
                return json.loads(body)
            err = scrub_secrets(proc.stderr or body or f"curl exit {proc.returncode} http={http_code}", (token,))[:300]
            # Fall through to urllib if curl missing/failed oddly
            if "curl:" in err or proc.returncode == 127:
                pass
            else:
                raise RuntimeError(err)
        except FileNotFoundError:
            pass
        req = urllib.request.Request(
            "https://api.kimi.com/coding/v1/usages",
            headers={
                "Authorization": f"Bearer {token}",
                "Accept": "application/json",
                "User-Agent": "usage-dashboard",
            },
        )
        # Last resort: unverified context only for this endpoint (Mac CA store quirk).
        import ssl
        ctx = ssl.create_default_context()
        try:
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                return json.loads(resp.read().decode())
        except ssl.SSLCertVerificationError:
            ctx = ssl._create_unverified_context()
            with urllib.request.urlopen(req, timeout=20, context=ctx) as resp:
                return json.loads(resp.read().decode())

    def _refresh_kimi_session() -> str | None:
        """Expired access_token: nudge CLI once so it rewrites credentials."""
        kimi_bin = Path.home() / ".kimi-code" / "bin" / "kimi"
        if not kimi_bin.exists():
            return None
        try:
            subprocess.run(
                [str(kimi_bin), "-p", "Reply with exactly: OK", "--output-format", "text"],
                cwd="/tmp",
                capture_output=True,
                text=True,
                timeout=90,
            )
        except Exception:
            return None
        if not cred_path.exists():
            return None
        try:
            return json.loads(cred_path.read_text()).get("access_token")
        except Exception:
            return None

    try:
        if cred_path.exists():
            cred = json.loads(cred_path.read_text())
            token = cred.get("access_token")
            # Access tokens are ~15m (expires_in=900). Refresh proactively if expired.
            exp = cred.get("expires_at")
            try:
                if exp is not None and float(exp) <= datetime.now(timezone.utc).timestamp():
                    token = _refresh_kimi_session() or token
            except (TypeError, ValueError):
                pass
            if token:
                try:
                    payload = _fetch_usages(token)
                except urllib.error.HTTPError as he:
                    if he.code == 401:
                        token2 = _refresh_kimi_session()
                        if not token2:
                            raise
                        payload = _fetch_usages(token2)
                    else:
                        raise
                usage = payload.get("usage") or {}
                limits = payload.get("limits") or []
                # API reports remaining; dashboard bars are used %
                def pct_used(limit_s, remaining_s, ndigits=1):
                    try:
                        lim = float(limit_s)
                        rem = float(remaining_s)
                        if not (math.isfinite(lim) and math.isfinite(rem)) or lim <= 0:
                            return None  # "Infinity" / "NaN" strings parse as floats but are no reading
                        pct = max(0.0, min(100.0, 100.0 * (lim - rem) / lim))
                        return pct if ndigits is None else round(pct, ndigits)
                    except (TypeError, ValueError):
                        return None

                def tone_for(used):
                    if used is None:
                        return "unk"
                    if used >= 90:
                        return "bad"
                    if used >= 70:
                        return "warn"
                    return "ok"

                def fmt_reset(iso_s):
                    if not iso_s:
                        return None
                    try:
                        # e.g. 2026-09-15T05:29:21.831115Z
                        dt = datetime.fromisoformat(iso_s.replace("Z", "+00:00")).astimezone(PT)
                        return dt.strftime("%Y-%m-%d %H:%M %Z")
                    except Exception:
                        return iso_s

                weekly_used = pct_used(usage.get("limit"), usage.get("remaining"))
                # display, tone and status keep the 1-decimal share; pacing reads the unrounded one
                weekly_exact = pct_used(usage.get("limit"), usage.get("remaining"), None)
                weekly_reset = fmt_reset(usage.get("resetTime"))
                bars = []
                if weekly_used is not None:
                    bars.append(
                        {
                            "label": "Weekly (7-day) usage",
                            "used_percent": weekly_used,
                            "reset": weekly_reset,
                            "tone": tone_for(weekly_used),
                            "reset_at": _iso_utc(_parse_iso(usage.get("resetTime"))),
                            "window_seconds": SEVEN_DAYS_S,
                            "used_percent_unrounded": weekly_exact,
                        }
                    )
                for lim in limits:
                    detail = (lim or {}).get("detail") or {}
                    window = (lim or {}).get("window") or {}
                    used = pct_used(detail.get("limit"), detail.get("remaining"))
                    if used is None:
                        continue
                    dur = window.get("duration")
                    unit = (window.get("timeUnit") or "").upper()
                    label = "5-hour window"
                    if dur == 300 and "MINUTE" in unit:
                        label = "5-hour window"
                    bars.append(
                        {
                            "label": label,
                            "used_percent": used,
                            "reset": fmt_reset(detail.get("resetTime")),
                            "tone": tone_for(used),
                            "reset_at": _iso_utc(_parse_iso(detail.get("resetTime"))),
                            "window_seconds": window_seconds_from_unit(dur, unit),
                            "used_percent_unrounded": pct_used(detail.get("limit"), detail.get("remaining"), None),
                        }
                    )

                blocked = weekly_used is not None and weekly_used >= 99.5
                out.update(
                    {
                        "ok": True,
                        "source": "GET https://api.kimi.com/coding/v1/usages (token redacted)",
                        "status": "blocked_quota" if blocked else "ok",
                        "chip": "Limit reached" if blocked else "OK",
                        "detail": (
                            "You've reached your weekly (7-day) usage limit"
                            if blocked
                            else f"Weekly remaining {usage.get('remaining')}/{usage.get('limit')}"
                        ),
                        "reset": weekly_reset,
                        "last_checked": iso_pt(now_pt()),
                        "used_percent": weekly_used,
                        "tone": tone_for(weekly_used) if weekly_used is not None else "ok",
                        "bars": bars,
                        "evidence": [
                            {
                                "path": str(cred_path),
                                "mtime": iso_pt(
                                    datetime.fromtimestamp(cred_path.stat().st_mtime, tz=PT)
                                ),
                                "excerpt": "Live /usages payload consumed; access_token not stored in snapshot.",
                            }
                        ],
                    }
                )
                return out
    except Exception as e:
        out["api_error"] = safe_error(e)
        # fall through to vault markers

    # --- Fallback: vault markers ---
    out["source"] = "Wiki/Daily + Hunt DONE_BLOCKED markers + kimi.out (API unavailable)"
    today = now_pt().strftime("%Y-%m-%d")
    daily = WIKI_DAILY / f"{today}-kimi.md"
    evidence = []
    blocked = False
    ok_signal = False
    detail_from_log = None
    reset_from_log = None

    def add_ev(path: Path, excerpt: str):
        evidence.append(
            {
                "path": str(path),
                "mtime": iso_pt(datetime.fromtimestamp(path.stat().st_mtime, tz=PT)),
                "excerpt": excerpt[:500],
            }
        )

    if daily.exists():
        text = daily.read_text(errors="replace")
        add_ev(daily, text[:500])
        if re.search(r"quota|403|DONE_BLOCKED|blocked", text, re.I):
            blocked = True
        elif re.search(r"DONE\b|ok|success", text, re.I):
            ok_signal = True

    if HUNT.exists():
        markers = sorted(HUNT.glob("*kimi*"), key=lambda p: p.stat().st_mtime, reverse=True)[:5]
        now_ts = datetime.now().timestamp()
        for p in markers:
            text = p.read_text(errors="replace")[:800]
            add_ev(p, text[:300])
            age_h = (now_ts - p.stat().st_mtime) / 3600.0
            # Only a FRESH DONE_BLOCKED/quota signal may set blocked.
            # Stale Sep-7-style notes must not OR into a false 100% when API is down.
            if age_h <= 18.0 and (
                "DONE_BLOCKED" in text or re.search(r"quota|403|weekly \(7-day\) usage limit", text, re.I)
            ):
                blocked = True

    for log in (
        Path("/tmp/vault-update-mac-20260907/kimi.out"),
        Path("/tmp/vault-update-kimi-2153.out"),
    ):
        if log.exists():
            t = log.read_text(errors="replace")[-2000:]
            add_ev(log, t[-500:])
            if re.search(r"403|quota|rate.?limit|weekly", t, re.I):
                blocked = True
            m = re.search(
                r"You've reached your weekly \(7-day\) usage limit[^.]*\.?",
                t,
                re.I,
            )
            if m:
                detail_from_log = m.group(0).rstrip(".")
            rm = re.search(
                r"[Yy]our quota will reset when the current 7-day window ends",
                t,
            )
            if rm:
                reset_from_log = "when current 7-day window ends"

    last_checked = None
    if evidence:
        # newest evidence mtime string for sort: parse from evidence
        last_checked = max((e["mtime"] for e in evidence), default=None)

    # Stale DONE_BLOCKED notes must not override a live API outage forever.
    newest_mtime = None
    for e in evidence:
        try:
            # e["mtime"] like "2026-09-08 21:15:36 PDT"
            newest_mtime = max(filter(None, [newest_mtime, e.get("mtime")]))
        except Exception:
            pass
    evidence_fresh = False
    if evidence:
        try:
            newest_path_mtime = max(
                Path(e["path"]).stat().st_mtime
                if Path(e["path"]).exists()
                else 0
                for e in evidence
            )
            # Prefer absolute path ages; Hunt filenames are relative — also check mtime strings via files we opened
            ages = []
            for e in evidence:
                p = Path(e["path"])
                if not p.is_absolute():
                    # try Hunt / Wiki
                    for root in (HUNT, WIKI_DAILY, Path("/tmp")):
                        cand = root / p.name
                        if cand.exists():
                            ages.append(cand.stat().st_mtime)
                            break
                elif p.exists():
                    ages.append(p.stat().st_mtime)
            if ages:
                age_h = (datetime.now().timestamp() - max(ages)) / 3600.0
                evidence_fresh = age_h <= 18.0
                out["evidence_age_hours"] = round(age_h, 1)
        except Exception:
            evidence_fresh = False

    if blocked and evidence_fresh:
        out["status"] = "blocked_quota"
        out["chip"] = "Limit reached"
        out["detail"] = detail_from_log or "You've reached your weekly (7-day) usage limit"
        out["reset"] = reset_from_log or "when current 7-day window ends"
        out["used_percent"] = 100.0
        out["tone"] = "bad"
        out["bars"] = [
            {
                "label": "Weekly (7-day) usage",
                "used_percent": 100.0,
                "reset": out["reset"],
                "tone": "bad",
            }
        ]
    elif blocked and not evidence_fresh:
        out["status"] = "unknown"
        out["chip"] = "API unavailable"
        out["detail"] = (
            (out.get("api_error") and f"Live /usages failed ({out['api_error']}); ")
            or ""
        ) + "stale vault DONE_BLOCKED markers ignored (>18h). Re-run after kimi login."
        out["reset"] = None
        out["used_percent"] = None
        out["tone"] = "unk"
        out["bars"] = [
            {
                "label": "Weekly (7-day) usage",
                "used_percent": None,
                "reset": "unknown — refresh kimi session",
                "tone": "unk",
            }
        ]
    elif ok_signal:
        out["status"] = "ok"
        out["chip"] = "OK"
        out["detail"] = "Recent vault markers look healthy (no quota block)."
        out["reset"] = None
        out["used_percent"] = None
        out["tone"] = "ok"
        out["bars"] = [
            {
                "label": "Weekly (7-day) usage",
                "used_percent": None,
                "reset": "N/A — numeric % API not available",
                "tone": "unk",
            }
        ]
    else:
        out["status"] = "unknown"
        out["chip"] = "Unknown"
        out["detail"] = "No reliable public usage API; status inferred from vault markers."
        out["reset"] = None
        out["used_percent"] = None
        out["tone"] = "unk"
        out["bars"] = [
            {
                "label": "Weekly (7-day) usage",
                "used_percent": None,
                "reset": "N/A — numeric % API not available",
                "tone": "unk",
            }
        ]

    out["last_checked"] = last_checked
    out["evidence"] = evidence[:6]
    return out


def parse_agy_usage_tsv(text: str) -> list[dict]:
    """Parse `agy -p /usage` rows: Label\\tWindow Remaining\\tNN%\\tISO-Z."""
    bars: list[dict] = []
    for ln in text.splitlines():
        ln = ln.strip()
        if not ln or ln.startswith("Usage of"):
            continue
        parts = re.split(r"\t+", ln)
        if len(parts) < 3:
            parts = re.split(r"\s{2,}", ln)
        if len(parts) < 3:
            continue
        family = parts[0].strip()
        window = parts[1].strip()
        pct_m = re.search(r"(\d+(?:\.\d+)?)\s*%", parts[2])
        if not pct_m:
            continue
        remaining = float(pct_m.group(1))
        used = max(0.0, min(100.0, 100.0 - remaining))
        reset_raw = parts[3].strip() if len(parts) > 3 else ""
        reset_pt = None
        if reset_raw:
            try:
                iso = reset_raw.replace("Z", "+00:00")
                reset_pt = datetime.fromisoformat(iso).astimezone(PT).strftime("%Y-%m-%d %H:%M %Z")
            except Exception:
                reset_pt = reset_raw
        remaining_word = "remaining" in window.lower()
        label = f"{family} · {window.replace(' Remaining', '').replace(' remaining', '')}"
        bars.append(
            {
                "label": label,
                "used_percent": used,
                "remaining_percent": remaining,
                "reset": reset_pt,
                "tone": bar_class(used),
                "raw_window": window,
                "reports_remaining": remaining_word,
                "reset_at": _iso_utc(_parse_iso(reset_raw)),
                "window_seconds": window_seconds_from_name(window),
            }
        )
    return bars


def collect_agy() -> dict:
    out: dict = {
        "ok": False,
        "source": "agy -p /usage + packs/agy-pack-*.md",
        "cli_version": None,
        "bars": [],
        "pack": None,
        "social_superpowers": None,
        "collect_health": None,
    }
    agy_bin = str(Path.home() / ".local/bin/agy")
    if not Path(agy_bin).exists():
        agy_bin = "agy"
    try:
        ver = subprocess.run(
            [agy_bin, "--version"],
            capture_output=True,
            text=True,
            timeout=20,
        )
        out["cli_version"] = (
            (ver.stdout or ver.stderr or "").strip().splitlines()[0]
            if (ver.stdout or ver.stderr)
            else None
        )
    except Exception as e:
        out["cli_version_error"] = safe_error(e)

    try:
        proc = subprocess.run(
            [
                agy_bin,
                "--dangerously-skip-permissions",
                "-p",
                "/usage",
                "--print-timeout",
                "90s",
            ],
            capture_output=True,
            text=True,
            timeout=120,
            stdin=subprocess.DEVNULL,
        )
        utext = (proc.stdout or "") + ("\n" + proc.stderr if proc.stderr else "")
        out["usage_raw_excerpt"] = utext.strip()[:2000]
        out["bars"] = parse_agy_usage_tsv(utext)
        if out["bars"]:
            out["ok"] = True
        elif proc.returncode != 0:
            out["usage_error"] = (proc.stderr or proc.stdout or f"exit {proc.returncode}")[:500]
    except Exception as e:
        out["usage_error"] = safe_error(e)

    packs = sorted(PACKS.glob("agy-pack-*.md"), key=lambda p: p.stat().st_mtime, reverse=True)
    if packs:
        p = packs[0]
        text = p.read_text(errors="replace")
        status_m = re.search(r"\*\*Status:\*\*\s*(.+)", text)
        status = status_m.group(1).strip() if status_m else None
        status_short = first_clause(status, 120)
        mtime = datetime.fromtimestamp(p.stat().st_mtime, tz=PT)
        out["pack"] = {
            "path": str(p),
            "name": p.name,
            "mtime": iso_pt(mtime),
            "mtime_short": short_mtime(iso_pt(mtime)),
            "status": status_short,
            "status_full_len": len(status or ""),
        }

        # Hourly collect health chip
        st_upper = (status or "").upper()
        if st_upper.startswith("PACK_DONE") or st_upper.startswith("PASS"):
            health_chip = "PACK_DONE" if "PACK_DONE" in st_upper[:20] else "PASS"
            health_tone = "ok"
        elif re.search(r"\bFAIL|ERROR|BLOCKED\b", status or "", re.I):
            health_chip = "FAIL"
            health_tone = "bad"
        else:
            health_chip = "UNKNOWN"
            health_tone = "unk"
        out["collect_health"] = {
            "chip": health_chip,
            "tone": health_tone,
            "pack_name": p.name,
            "mtime_short": short_mtime(iso_pt(mtime)),
            "status_short": status_short,
        }

        ssp: dict = {
            "daily_limit": 120,
            "reset_note": "17:00 PT (midnight UTC)",
            "state": "unknown",
            "used_percent": None,
            "label": "—",
            "tone": "unk",
        }
        if re.search(r"daily limit of 120|120 calls was reached|quota.*reached", text, re.I):
            ssp["state"] = "blocked_quota"
            ssp["tone"] = "bad"
            ssp["used_percent"] = 100.0
            ssp["label"] = "120/120 calls"
            reached = re.search(r"reached at\s*~?([0-9: ]+PT)", text, re.I)
            if reached:
                ssp["reached_at"] = reached.group(1).strip()
            elif re.search(r"~08:27 PT", text):
                ssp["reached_at"] = "~08:27 PT"
        elif re.search(r"social-superpowers", text, re.I):
            ssp["state"] = "mentioned"
            ssp["tone"] = "unk"
            ssp["label"] = "—"
            ssp["used_percent"] = None
        if re.search(r"resets? at midnight UTC|17:00 PT", text, re.I):
            ssp["reset_note"] = "17:00 PT (midnight UTC)"
        out["social_superpowers"] = ssp
        out["ok"] = True if out.get("bars") or out.get("pack") else out.get("ok", False)
        if out.get("bars") or out.get("pack"):
            out["ok"] = True
    else:
        out["error"] = "no agy-pack-*.md found"
        out["social_superpowers"] = {
            "daily_limit": 120,
            "reset_note": "17:00 PT (midnight UTC)",
            "state": "unknown",
            "used_percent": None,
            "label": "—",
            "tone": "unk",
        }
        out["collect_health"] = {"chip": "UNKNOWN", "tone": "unk", "pack_name": "—", "mtime_short": "—", "status_short": "—"}
    return out


def sync_manage_bot_transcript_from_client() -> Path | None:
    """Mirror Agent Manage Bot UI transcript replica into a countable jsonl.

    Temporal-harness agents often lack box agent-transcripts/*.jsonl. The Mac
    Grok Bot app keeps a client-side replica under Application Support.
    Always write HERE/_manage_bot_transcript.jsonl; also write the box path
    when that mount is present and writable.
    """
    import base64

    aid = "6a85c81a-8c66-4169-ae76-60d743932802"
    root = Path.home() / "Library/Application Support/Grok Bot/sand-client-persistence"
    local = HERE / "_manage_bot_transcript.jsonl"
    if not root.exists():
        return local if local.exists() else None

    def _b32(name: str) -> bytes | None:
        s = name.replace(".blob", "").upper()
        pad = (-len(s)) % 8
        try:
            return base64.b32decode(s + "=" * pad)
        except Exception:
            return None

    target = None
    for blob in root.glob("*.blob"):
        dec = _b32(blob.name)
        if dec and f"transcript.replicas.{aid}".encode() in dec:
            target = blob
            break
    if not target:
        return local if local.exists() else None
    try:
        data = json.loads(target.read_text())
        entries = (data.get("value") or {}).get("entries") or []
    except Exception:
        return local if local.exists() else None

    lines: list[str] = []
    for e in entries:
        kind = e.get("kind")
        if kind == "message" and e.get("role") == "user":
            lines.append(
                json.dumps(
                    {
                        "role": "user",
                        "message": {"content": [{"type": "text", "text": e.get("content") or ""}]},
                    },
                    ensure_ascii=False,
                )
            )
        elif kind == "send-message" or (kind == "message" and e.get("role") == "assistant"):
            msg = e.get("message") if kind == "send-message" else None
            if isinstance(msg, dict):
                content = msg.get("content")
                text = content if isinstance(content, str) else json.dumps(content, ensure_ascii=False)[:2000]
            else:
                text = e.get("content") or ""
            lines.append(
                json.dumps(
                    {"role": "assistant", "message": {"content": [{"type": "text", "text": text}]}},
                    ensure_ascii=False,
                )
            )
    body = ("\n".join(lines) + ("\n" if lines else "")).encode()
    local.write_bytes(body)
    # Best-effort box mirror (mount is intermittent on the Mac builder)
    try:
        if BOX_TRANS.exists():
            out_dir = BOX_TRANS / aid
            out_dir.mkdir(parents=True, exist_ok=True)
            (out_dir / f"{aid}.jsonl").write_bytes(body)
    except Exception:
        pass
    return local


def _counts_from_role_jsonl(path: Path) -> tuple[Counter, int, str | None]:
    counts: Counter = Counter()
    size = 0
    mtime = None
    if not path.exists():
        return counts, size, mtime
    st = path.stat()
    size = st.st_size
    mtime = datetime.fromtimestamp(st.st_mtime, tz=timezone.utc).astimezone(PT).strftime("%Y-%m-%d %H:%M %Z")
    with path.open() as f:
        for line in f:
            try:
                o = json.loads(line)
            except Exception:
                continue
            r = o.get("role")
            if r in ("user", "assistant", "tool"):
                counts[r] += 1
    return counts, size, mtime


def _apply_manage_bot_client_counts(bots: list[dict]) -> list[dict]:
    """Fill Agent Manage Bot zeros from the synced client replica jsonl."""
    sync_manage_bot_transcript_from_client()
    local = HERE / "_manage_bot_transcript.jsonl"
    counts, size, mtime = _counts_from_role_jsonl(local)
    if not sum(counts.values()):
        return bots
    at = counts["assistant"] + counts["tool"]
    patched = False
    for b in bots:
        if b.get("name") != "Agent Manage Bot":
            continue
        cur = (b.get("messages") or {}).get("assistant_tool") or 0
        # Always refresh last-activity from the client replica mtime when present.
        if mtime:
            b["last_transcript_activity_pt"] = mtime
            b["activity_source"] = "mac-client-replica:6a85c81a-8c66-4169-ae76-60d743932802"
            try:
                # mtime string is PT display; keep epoch from file
                b["source_mtime_epoch"] = local.stat().st_mtime
            except Exception:
                pass
        if cur > 0:
            patched = True
            break
        b["id"] = b.get("id") or "6a85c81a-8c66-4169-ae76-60d743932802"
        b["role"] = GROK_ROLES.get("Agent Manage Bot", b.get("role") or "")
        b["messages"] = {
            "user": counts["user"],
            "assistant": counts["assistant"],
            "tool": counts["tool"],
            "total": counts["user"] + counts["assistant"] + counts["tool"],
            "assistant_tool": at,
        }
        b["transcript_bytes"] = size
        b["transcript_mb"] = round(size / (1024 * 1024), 2)
        b["last_transcript_activity_pt"] = mtime
        b["source_note"] = "client transcript replica (UI turns; tool calls undercounted)"
        patched = True
        break
    if not patched:
        bots.append(
            {
                "id": "6a85c81a-8c66-4169-ae76-60d743932802",
                "name": "Agent Manage Bot",
                "title": "Admin",
                "role": GROK_ROLES.get("Agent Manage Bot", ""),
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
                "automation_runs": 0,
                "last_automation_started_pt": None,
                "source_note": "client transcript replica (UI turns; tool calls undercounted)",
            }
        )
    # recompute shares
    fleet_at = sum(b["messages"]["assistant_tool"] for b in bots) or 0
    for b in bots:
        b["share_assistant_tool_pct"] = (
            round(100.0 * b["messages"]["assistant_tool"] / fleet_at, 1) if fleet_at else 0.0
        )
    return bots


def _collect_grok_from_box() -> dict | None:
    bots = collect_box_bots()
    if bots is None:
        return None
    bots = _apply_manage_bot_client_counts(bots)
    bots = apply_manage_receipts(bots)  # Manage: max(chat signals, routine receipts)
    bots = overlay_client_replicas(bots)
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
    return build_payload(
        bots,
        "box agents/<id>/ live + Mac client replicas",
        problems=problems,
    )



def _muse_runtime_record(obj):
    """Validate the durable session-record envelope, never payload/example content."""
    if not isinstance(obj, dict):
        return False
    stream = obj.get("stream")
    return (
        type(obj.get("schema_version")) is int and obj["schema_version"] == 1
        and obj.get("record_type") == "event"
        and isinstance(obj.get("id"), str) and bool(obj["id"])
        and isinstance(stream, dict) and stream.get("kind") == "session"
        and isinstance(stream.get("id"), str) and bool(stream["id"])
        and isinstance(obj.get("payload"), dict)
    )


def _muse_runtime_records(obj, marker, depth=0, malformed=None, deadline=None, expired=None,
                          rejected=None):
    """Yield runtime records only at the log root or in retained-frame children.

    No arbitrary dictionaries, lists, event fields or tool results are traversed.
    record_json is decoded only in the supported retained-frame envelope.
    """
    if depth > 8 or (expired is not None and expired[0]):
        return
    if deadline is not None and time.monotonic() > deadline:
        if expired is not None:
            expired[0] = True
        return
    if _muse_runtime_record(obj):
        yield obj
        return  # the record's payload cannot contain another runtime record
    if not isinstance(obj, dict):
        return
    payload = obj.get("payload")
    if isinstance(payload, dict):
        event = payload.get("event")
        recognizable = (
            obj.get("payload_type") == "runtime.user_intent.accepted"
            or (obj.get("payload_type") == "runtime.session" and payload.get("kind") == "run"
                and isinstance(event, dict) and event.get("kind") == "model_completed")
        )
        if recognizable:
            if rejected is not None:
                rejected.add(id(obj))
            return  # flag the envelope without descending into its payload
    if obj.get("retained_frame") != "session_permission_transaction":
        return
    children = obj.get("children")
    if not isinstance(children, list):
        return
    for child in children:
        if deadline is not None and time.monotonic() > deadline:
            if expired is not None:
                expired[0] = True
            return
        if not isinstance(child, dict):
            continue
        encoded = child.get("record_json")
        if not isinstance(encoded, str) or marker not in encoded:
            continue
        if type(child.get("child_index")) is not int or child["child_index"] < 0:
            if malformed is not None:
                malformed.add(id(encoded))
            continue
        try:
            record = json.loads(encoded)
        except ValueError:
            if malformed is not None:
                malformed.add(id(encoded))
            continue
        if not _muse_runtime_record(record) and not (
            isinstance(record, dict) and record.get("retained_frame") == "session_permission_transaction"
        ):
            if malformed is not None:
                malformed.add(id(encoded))
            continue
        yield from _muse_runtime_records(record, marker, depth + 1, malformed, deadline, expired, rejected)


def _muse_find_model_completed(obj, hits, ctx=None, depth=0, malformed=None,
                               deadline=None, expired=None, rejected=None):
    """Read only runtime.session -> run -> model_completed in validated records."""
    for record in _muse_runtime_records(
        obj, "model_completed", depth, malformed, deadline, expired, rejected
    ):
        payload = record["payload"]
        if record.get("payload_type") != "runtime.session" or payload.get("kind") != "run":
            continue
        event = payload.get("event")
        if isinstance(event, dict) and event.get("kind") == "model_completed":
            hits.append(((record["id"], record.get("recorded_at")), event))


def _muse_find_user_prompts(obj, hits, depth=0, malformed=None, deadline=None,
                            expired=None, rejected=None):
    """Read accepted user intents only from validated runtime-record envelopes."""
    for record in _muse_runtime_records(
        obj, "user_intent.accepted", depth, malformed, deadline, expired, rejected
    ):
        if record.get("payload_type") == "runtime.user_intent.accepted":
            hits.append((record["id"], record.get("recorded_at"), record["payload"].get("intent_id")))


def _muse_model_id(value) -> str | None:
    """Accept bounded model identifiers, rejecting credentials before dictionary insertion."""
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,159}", value):
        return None
    if any(part.lower().startswith("sk-") for part in value.split("/")):
        return None
    return value if scrub_secrets(value) == value else None


def _muse_event_day(recorded_us, days, fallback_day, start_key):
    """Map an event timestamp to its PT window day: (day_key|None, valid_ts, pre_window).

    A valid timestamp outside the window yields day None (exclude the event —
    never dump it on the session's updated day). Only events with no usable
    timestamp fall back to fallback_day (the session's updated day).
    """
    if isinstance(recorded_us, (int, float)) and not isinstance(recorded_us, bool):
        try:
            day = datetime.fromtimestamp(recorded_us / 1_000_000, PT).date().isoformat()
        except (OverflowError, OSError, ValueError):
            return fallback_day, False, False
        if day in days:
            return day, True, False
        return None, True, day < start_key
    return fallback_day, False, False


def _muse_int(x) -> int | None:
    """Missing counters are zero; only integral unsigned 64-bit counts are supported."""
    if x is None:
        return 0
    if isinstance(x, bool) or not isinstance(x, (int, float)) or x < 0 or x > MUSE_USAGE_MAX_COUNTER:
        return None
    if isinstance(x, float) and (not math.isfinite(x) or not x.is_integer()):
        return None
    return int(x)


def _muse_query_sessions(target, start_us, uri):
    """Session rows updated at/after start_us; tolerates an index without created_at_us."""
    con = sqlite3.connect(target, uri=uri, timeout=1)
    try:
        try:
            return con.execute(
                "SELECT session_id, session_log_path, model_id, prompt_count, updated_at_us, created_at_us"
                " FROM sessions WHERE updated_at_us >= ? ORDER BY updated_at_us DESC",
                (start_us,),
            ).fetchall()
        except sqlite3.OperationalError as e:
            if "no such column" not in str(e).lower():
                raise
            return [
                (*r, None)
                for r in con.execute(
                    "SELECT session_id, session_log_path, model_id, prompt_count, updated_at_us"
                    " FROM sessions WHERE updated_at_us >= ? ORDER BY updated_at_us DESC",
                    (start_us,),
                ).fetchall()
            ]
    finally:
        con.close()


def _muse_query_sessions_via_copy(db: Path, start_us):
    """Query a temp copy of the index (db + -wal + -shm). Never writes to the original.

    Fallback for runtimes whose read-only WAL open fails ("unable to open
    database file") on the live index. The copy may be opened read-write
    (WAL recovery writes only inside the temp dir); always cleaned up.
    """
    with tempfile.TemporaryDirectory(prefix="muse-index-") as tmp:
        dst = Path(tmp) / db.name
        shutil.copyfile(db, dst)
        for suffix in ("-wal", "-shm"):
            src = Path(f"{db}{suffix}")
            if src.exists():
                shutil.copyfile(src, Path(f"{dst}{suffix}"))
        return _muse_query_sessions(str(dst), start_us, uri=False)


def _collect_muse_usage(share_dir: Path, now: datetime | None = None) -> dict:
    """Last-7-days (PT) Muse token usage from session-index.db + per-session JSONL logs.

    Tokens count model_completed events only (goal_usage_attribution re-reports
    the same numbers). Per-day attribution is by each event's own timestamp:
    events with valid timestamps outside the window are excluded, never moved
    to the session's updated day; only untimestamped events fall back to that
    day. A session counts on each day it had counted model/prompt activity
    (totals count distinct sessions). Prompts count timestamped
    runtime.user_intent.accepted records; sessions whose logs have none fall
    back to the index lifetime prompt_count only when the session provably
    started inside the window (a valid created_at_us inside the window, no
    pre-window events, log fully read), spread pro rata over its
    model-activity days and flagged prompts_approximate — pre-window
    lifetimes are never attributed, and a missing/invalid created_at_us
    contributes zero fallback prompts flagged approximate. Missing or
    oversized logs, malformed model_completed / user_intent /
    retained-frame record lines, invalid model identifiers or counters,
    and time-budget overruns (deadline checked
    on every line/parse and between files) set partial + usage_note. The
    WAL index is opened read-only with a brief locked-retry; if that open
    or first query fails, a temp copy is queried instead (see
    _muse_query_sessions_via_copy). Any remaining DB failure degrades into
    usage_error + partial + usage_note — this never raises.
    """
    zero = {
        "sessions": 0,
        "prompts": 0,
        "input_tokens": 0,
        "output_tokens": 0,
        "cached_tokens": 0,
        "reasoning_tokens": 0,
    }
    usage: dict = {
        "window_days": MUSE_USAGE_DAYS,
        "plan": MUSE_PLAN,
        "limit": None,  # not exposed by Muse CLI
        "reset": None,  # not exposed by Muse CLI
        "limit_note": "not exposed by Muse CLI",
        "days": [],
        "totals": dict(zero),
        "today": dict(zero),
        "by_model": {},
        "sessions_in_window": 0,
        "logs_scanned": 0,
        "logs_missing": 0,
        "logs_skipped_large": 0,
        "malformed_lines": 0,
        "malformed_usage_lines": 0,
        "malformed_prompt_lines": 0,
        "malformed_frame_records": 0,
        "rejected_runtime_records": 0,
        "invalid_model_events": 0,
        "invalid_counter_events": 0,
        "events_out_of_window": 0,
        "partial": False,
        "usage_note": "",
        "prompts_approximate": False,
        "prompts_note": "",
    }
    day_sessions = {}
    try:
        now = now or now_pt()
        today = now.date()
        start_day = today - timedelta(days=MUSE_USAGE_DAYS - 1)
        start_us = int(datetime.combine(start_day, datetime.min.time(), PT).timestamp() * 1_000_000)
        day_keys = [(start_day + timedelta(days=i)).isoformat() for i in range(MUSE_USAGE_DAYS)]
        days = {k: {"date": k, **zero, "models": {}} for k in day_keys}
        usage["days"] = [days[k] for k in day_keys]
        db = share_dir / "session-index.db"
        if not db.exists():
            usage["usage_error"] = "session-index.db not found"
            usage["partial"] = True
            usage["usage_note"] = "session-index.db not found — totals may undercount"
            return usage
        rows = None
        ro_err: Exception | None = None
        locked_exhausted = False
        for _attempt in range(4):  # WAL db is actively written; tolerate transient locks
            try:
                rows = _muse_query_sessions(f"file:{db}?mode=ro", start_us, uri=True)
                break
            except sqlite3.OperationalError as e:
                ro_err = e
                if "locked" not in str(e).lower():
                    break  # read-only open/query failed: try the copy fallback
                if _attempt == 3:
                    locked_exhausted = True
                else:
                    time.sleep(0.25)
            except sqlite3.Error as e:
                ro_err = e
                break  # try the copy fallback (a corrupt copy fails too)
        if rows is None and not locked_exhausted:
            try:
                rows = _muse_query_sessions_via_copy(db, start_us)
            except Exception:
                rows = None  # degrade below with the read-only error
        if rows is None:
            err = safe_error(ro_err) if ro_err is not None else "database is locked"
            usage["usage_error"] = err
            usage["partial"] = True
            usage["usage_note"] = (
                f"session-index.db could not be read ({err}) — totals may undercount"
            )
            return usage
        usage["sessions_in_window"] = len(rows)
        deadline = time.monotonic() + MUSE_USAGE_TIME_BUDGET_S
        budget_hit = False
        start_key = day_keys[0]
        day_sessions = {k: set() for k in day_keys}
        for session_id, log_path, model_id, prompt_count, updated_us, created_us in rows:
            if time.monotonic() > deadline:
                budget_hit = True
                break
            try:
                up_day = datetime.fromtimestamp((updated_us or 0) / 1_000_000, PT).date().isoformat()
            except (OverflowError, OSError, ValueError):
                up_day = None
            fallback_day = up_day if up_day in days else None
            try:
                size = os.path.getsize(log_path or "")
            except OSError:
                usage["logs_missing"] += 1
                continue
            if size > MUSE_USAGE_MAX_FILE_BYTES:
                usage["logs_skipped_large"] += 1
                continue
            sess_model_days: Counter = Counter()
            sess_prompt_days: Counter = Counter()
            saw_prompt_record = False
            saw_pre_window = False
            truncated = False
            read_ok = True
            try:
                with open(log_path, "r", encoding="utf-8", errors="replace") as fh:
                    seen_models = set()
                    seen_prompts = set()
                    for line in fh:
                        if time.monotonic() > deadline:
                            budget_hit = True
                            truncated = True
                            break
                        if "model_completed" not in line and "user_intent.accepted" not in line:
                            continue
                        try:
                            obj = json.loads(line)
                        except ValueError:
                            usage["malformed_lines"] += 1
                            if "model_completed" in line:
                                usage["malformed_usage_lines"] += 1
                            if "user_intent.accepted" in line:
                                usage["malformed_prompt_lines"] += 1
                            continue
                        if time.monotonic() > deadline:
                            budget_hit = True
                            truncated = True
                            break
                        frame_malformed: set = set()
                        runtime_rejected: set = set()
                        expired = [False]
                        hits: list = []
                        _muse_find_model_completed(
                            obj, hits, malformed=frame_malformed,
                            deadline=deadline, expired=expired, rejected=runtime_rejected,
                        )
                        for ctx, ev in hits:
                            if expired[0] or time.monotonic() > deadline:
                                budget_hit = True
                                truncated = True
                                break
                            key = ctx[0]
                            if key in seen_models:
                                continue
                            seen_models.add(key)
                            ev_day, valid_ts, pre_window = _muse_event_day(
                                ctx[1] if ctx else None, days, fallback_day, start_key
                            )
                            saw_pre_window = saw_pre_window or pre_window
                            if ev_day is None:
                                if valid_ts:
                                    usage["events_out_of_window"] += 1
                                continue
                            model = _muse_model_id(ev.get("model") or model_id or "unknown")
                            if model is None:
                                usage["invalid_model_events"] += 1
                                continue
                            u = ev.get("usage")
                            counters = [_muse_int(u.get(f)) for f in (
                                "input_tokens", "output_tokens", "cached_tokens",
                                "cache_read_tokens", "reasoning_tokens",
                            )] if isinstance(u, dict) else [None]
                            if any(v is None for v in counters):
                                usage["invalid_counter_events"] += 1
                                continue
                            inp, out_t, cache_tokens, cache_read, reas = counters
                            cached = cache_tokens + cache_read
                            drow = days[ev_day]
                            drow["input_tokens"] += inp
                            drow["output_tokens"] += out_t
                            drow["cached_tokens"] += cached
                            drow["reasoning_tokens"] += reas
                            drow["models"][model] = drow["models"].get(model, 0) + inp + out_t
                            sess_model_days[ev_day] += 1
                            day_sessions[ev_day].add(session_id)
                        if truncated:
                            usage["malformed_frame_records"] += len(frame_malformed)
                            usage["rejected_runtime_records"] += len(runtime_rejected)
                            break
                        phits: list = []
                        _muse_find_user_prompts(
                            obj, phits, malformed=frame_malformed,
                            deadline=deadline, expired=expired, rejected=runtime_rejected,
                        )
                        usage["malformed_frame_records"] += len(frame_malformed)
                        usage["rejected_runtime_records"] += len(runtime_rejected)
                        for rec_id, rec_at, intent_id in phits:
                            if expired[0] or time.monotonic() > deadline:
                                budget_hit = True
                                truncated = True
                                break
                            pkey = rec_id or intent_id
                            if pkey is not None:
                                if pkey in seen_prompts:
                                    continue
                                seen_prompts.add(pkey)
                            saw_prompt_record = True
                            p_day, valid_ts, pre_window = _muse_event_day(
                                rec_at, days, fallback_day, start_key
                            )
                            saw_pre_window = saw_pre_window or pre_window
                            if p_day is None:
                                if valid_ts:
                                    usage["events_out_of_window"] += 1
                                continue
                            sess_prompt_days[p_day] += 1
                        if expired[0]:
                            budget_hit = True
                            truncated = True
                        if truncated:
                            break
            except OSError:
                read_ok = False
                usage["logs_missing"] += 1
            if saw_prompt_record:
                for dkey, n in sess_prompt_days.items():
                    days[dkey]["prompts"] += n
                    day_sessions[dkey].add(session_id)
            elif read_ok and not truncated and sess_model_days and not saw_pre_window:
                # No timestamped prompt events in this log: the lifetime index
                # prompt_count is an in-window total only if a valid
                # created_at_us proves the session started inside the window;
                # spread it over the session's model-activity days pro rata
                # (largest-remainder rounding). A missing/invalid creation
                # timestamp proves nothing: contribute zero and flag the
                # prompt totals approximate instead of attributing a lifetime.
                created_ok = False
                created_unknown = True
                if isinstance(created_us, (int, float)) and not isinstance(created_us, bool) and created_us > 0:
                    try:
                        created_day = datetime.fromtimestamp(
                            created_us / 1_000_000, PT
                        ).date().isoformat()
                    except (OverflowError, OSError, ValueError):
                        created_day = None
                    if created_day in days:
                        created_ok = True
                        created_unknown = False
                    elif created_day is not None and created_day < start_key:
                        created_unknown = False  # provably pre-window
                total_pc = _muse_int(prompt_count)
                if total_pc is None:
                    usage["invalid_counter_events"] += 1
                    total_pc = 0
                    usage["prompts_approximate"] = True
                if created_unknown and total_pc > 0:
                    usage["prompts_approximate"] = True
                if created_ok and total_pc > 0:
                    total_w = sum(sess_model_days.values())
                    shares = {k: [total_pc * w // total_w, total_pc * w % total_w]
                              for k, w in sess_model_days.items()}
                    assigned = sum(v[0] for v in shares.values())
                    for dkey in sorted(shares, key=lambda k: (-shares[k][1], k)):
                        if assigned >= total_pc:
                            break
                        shares[dkey][0] += 1
                        assigned += 1
                    for dkey, (n, _rem) in shares.items():
                        days[dkey]["prompts"] += n
                    usage["prompts_approximate"] = True
            if read_ok:
                usage["logs_scanned"] += 1
            if truncated:
                break
        else:
            if time.monotonic() > deadline:
                budget_hit = True
        note_parts = []
        if usage["logs_missing"]:
            note_parts.append(f"{usage['logs_missing']} session log(s) missing/unreadable")
        if usage["logs_skipped_large"]:
            limit = MUSE_USAGE_MAX_FILE_BYTES
            limit_s = f"{limit / (1024 * 1024):g} MB" if limit >= 1024 * 1024 else f"{limit} bytes"
            note_parts.append(f"{usage['logs_skipped_large']} session log(s) over {limit_s} skipped")
        if usage.get("malformed_usage_lines"):
            note_parts.append(
                f"{usage['malformed_usage_lines']} malformed model_completed line(s) skipped"
            )
        if usage.get("malformed_prompt_lines"):
            note_parts.append(
                f"{usage['malformed_prompt_lines']} malformed user_intent line(s) skipped"
            )
        if usage.get("malformed_frame_records"):
            note_parts.append(
                f"{usage['malformed_frame_records']} malformed retained-frame record(s) skipped"
            )
        if usage["rejected_runtime_records"]:
            note_parts.append(f"{usage['rejected_runtime_records']} rejected runtime record(s) skipped")
        if usage["invalid_model_events"]:
            note_parts.append(f"{usage['invalid_model_events']} invalid model identifier event(s) skipped")
        if usage["invalid_counter_events"]:
            note_parts.append(f"{usage['invalid_counter_events']} invalid usage counter record(s) skipped")
        if budget_hit:
            note_parts.append("time budget exceeded")
        if note_parts:
            usage["partial"] = True
            usage["usage_note"] = "; ".join(note_parts) + " — totals may undercount"
        if usage["prompts_approximate"]:
            usage["prompts_note"] = (
                "Some sessions have no timestamped prompt events; their index prompt_count "
                "is spread over their model-activity days only when a valid created_at_us "
                "proves the session started inside the window. Sessions created before the "
                "window, or with a missing/invalid created_at_us, contribute zero fallback "
                "prompts."
            )
    except Exception as e:
        usage["usage_error"] = safe_error(e)
        usage["partial"] = True
        if not usage.get("usage_note"):
            usage["usage_note"] = (
                f"usage scan failed ({usage['usage_error']}) — totals may undercount"
            )
    # Finalize even if a later record failed after valid activity was accumulated.
    active_sessions: set = set()
    by_model: dict = {}
    for d in usage["days"]:
        sessions = day_sessions.get(d["date"], set())
        d["sessions"] = len(sessions)
        active_sessions.update(sessions)
        for f in zero:
            if f != "sessions":
                usage["totals"][f] += d[f]
        for model, tokens in d["models"].items():
            by_model[model] = by_model.get(model, 0) + tokens
    usage["totals"]["sessions"] = len(active_sessions)
    if usage["days"]:
        usage["today"] = {f: usage["days"][-1][f] for f in zero}
    usage["by_model"] = dict(sorted(by_model.items(), key=lambda kv: -kv[1]))
    return usage


def collect_muse(share_dir=None, settings_path=None, muse_bin=None, auth_path=None) -> dict:
    """Muse Code / Muse Spark — version + auth + local 7-day token usage.

    Muse exposes no plan/quota API; plan is user-stated Max, limits render as null.
    Paths are injectable for tests (defaults = the real ~/.local / ~/.config paths).
    """
    import shutil

    share_dir = Path(share_dir) if share_dir else MUSE_SHARE
    settings_path = Path(settings_path) if settings_path else MUSE_SETTINGS
    auth_path = Path(auth_path) if auth_path else MUSE_AUTH

    out: dict = {
        "ok": False,
        "source": "muse --version + ~/.config/muse/auth.json + session-index.db (7d local usage)",
        "bars": [],
        "model": "muse-spark-1.3-contributor",
        "product": "Muse Code",
        "model_family": "Muse Spark",
    }
    try:
        if muse_bin is not None:
            muse = Path(muse_bin)
        else:
            muse = MUSE_BIN if MUSE_BIN.exists() else Path(shutil.which("muse") or "")
        if not muse or not Path(muse).exists():
            out["error"] = "muse binary not found"
            return out
        out["binary"] = str(muse)
        proc = subprocess.run(
            [str(muse), "--version"],
            capture_output=True,
            text=True,
            timeout=15,
            stdin=subprocess.DEVNULL,
        )
        ver = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        out["cli_version"] = ver[0] if ver else "unknown"
        auth_ok = False
        mechanism = None
        if auth_path.exists():
            auth = json.loads(auth_path.read_text())
            meta = (auth.get("providers") or {}).get("meta") or {}
            mechanism = meta.get("mechanism") or meta.get("obtained_via") or meta.get("storage")
            auth_ok = bool(meta)
        out["auth_ok"] = auth_ok
        out["auth_mechanism"] = mechanism
        cfg_model = None
        try:
            if settings_path.exists():
                cfg = json.loads(settings_path.read_text())
                if isinstance(cfg, dict):
                    m = cfg.get("model")
                    cfg_model = m.strip() if isinstance(m, str) and m.strip() else None
                    if cfg.get("reasoning_effort"):
                        out["reasoning_effort"] = cfg.get("reasoning_effort")
        except Exception:
            cfg_model = None
        usage = _collect_muse_usage(share_dir)
        out["usage"] = usage
        if usage.get("usage_error"):
            out["usage_error"] = usage["usage_error"]
        top_model = next(iter(usage.get("by_model") or {}), None)
        out["model"] = cfg_model or top_model or out["model"]
        out["model_source"] = (
            "settings.json" if cfg_model else ("session logs (7d most-used)" if top_model else "fallback default")
        )
        out["ok"] = bool(out.get("cli_version")) and auth_ok
        out["detail"] = (
            "Usage = local session-index.db (read-only, temp-copy fallback) + session logs, last 7 days PT by event "
            "timestamp: tokens from model_completed only (goal_usage_attribution "
            "excluded), prompts from user_intent events. Plan Max is user-stated "
            "(2026-10-12): the Muse CLI exposes no plan/limit/reset API, so quota stays null."
        )
        if not auth_ok:
            out["error"] = "muse auth missing — run muse login"
    except Exception as e:
        out["error"] = safe_error(e)
    return out


_DSH_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._:/@+-]{0,79}")  # OpenRouter-style provider/model ids
# One "key: value" line of the overlay subset. The value is empty (null), a '…' / "…" closed on the same
# line (no escapes) or a plain ASCII token, then an optional " # comment". Flow collections, block
# scalars, tags, anchors, open quotes and plain values with spaces or quote/bracket chars never match.
_DSH_KV = re.compile(r"""([A-Za-z_][A-Za-z0-9_-]*):(?: +('[^']*'|"[^"\\]*"|[A-Za-z0-9~][A-Za-z0-9_.:/@+~-]*(?<!:)))?(?: +#.*)? *""")
# Plain tokens that dsh's js-yaml (JSON schema) loads as null / bool / int / float instead of a string.
_DSH_NONSTR = re.compile(r"~|null|Null|NULL|true|True|TRUE|false|False|FALSE|0b[01]+|0x[0-9a-fA-F]+|0o[0-7]+|[0-9]+(?:\.[0-9]*)?(?:[eE][-+]?[0-9]+)?")


def _dsh_str(tok: str | None) -> str | None:
    """_DSH_KV value token -> its string; None for null and for non-string plain scalars."""
    if tok and tok[0] in "'\"":
        return tok[1:-1]
    return None if not tok or _DSH_NONSTR.fullmatch(tok) else tok


def _dsh_overlay_model(path: Path) -> tuple:
    """(provider, model) of the agent-default-model entry in a dsh --patch overlay, else (None, None).

    Strict line parser for exactly the overlay's shape: a top-level YAML list of flat "key: scalar"
    entries where only a bare `config:` opens a flat mapping. Anything else (tabs, control chars, other
    indents, flow/block collections, block or multi-line scalars, open quotes, duplicate keys) rejects
    the whole file, as does an entry dsh would skip or not apply as written: duplicate id, disabled
    (any value js-yaml + Boolean() treat as true), other name, extra keys, config not a mapping. Each
    returned value must pass _DSH_ID. Never raises.
    """
    try:
        text = path.read_bytes().decode("utf-8")
    except Exception:  # missing, unreadable, not UTF-8
        return None, None
    if re.search(r"[\x00-\x09\x0b-\x1f\x7f-\x9f\u2028\u2029\ufeff]", text):  # tab, CR, NUL, BOM, ...
        return None, None
    entries, cfg = [], None  # cfg: the open `config:` mapping of the current entry, else None
    for line in text.split("\n"):
        if not line.strip(" ") or line.lstrip(" ").startswith("#"):
            continue  # blank or comment line
        if line.startswith("- "):  # a new list entry; its first key sits at indent 2
            entries.append({})
            ind = 2
        else:
            ind = len(line) - len(line.lstrip(" "))
        mapping = entries[-1] if ind == 2 and entries else cfg if ind == 4 else None
        kv = _DSH_KV.fullmatch(line[ind:])
        if mapping is None or not kv or kv.group(1) in mapping:
            return None, None  # outside the subset, or a duplicate key
        key, tok = kv.groups()
        if ind == 4:
            cfg[key] = tok
        elif key == "config" and tok is None:  # a bare `config:` opens the entry's nested mapping
            cfg = mapping[key] = {}
        else:
            cfg, mapping[key] = None, tok
    hits = [e for e in entries if _dsh_str(e.get("id")) == "agent-default-model"]
    if len(hits) != 1:
        return None, None
    entry, conf = hits[0], hits[0].get("config")
    if (
        not isinstance(conf, dict)
        or set(entry) - {"id", "name", "config", "disabled"}
        or ("name" in entry and _dsh_str(entry["name"]) != "@deepseek-ai/dsh-agent-default-model")
        or entry.get("disabled") not in (None, "false", "False", "FALSE", "null", "~", "0", "''", '""')
    ):
        return None, None
    vals = (_dsh_str(conf.get("provider")), _dsh_str(conf.get("model")))
    return tuple(v if v and _DSH_ID.fullmatch(v) else None for v in vals)


# Default small model seats (Haiyuan 2026-10-24): OpenCode GLM-5.3 first, DSH DeepSeek v4.1 Flash the
# alternate + fallback; advisory jobs only. Both cards carry this label.
SMALL_SEAT = "default small"
SMALL_TRIAL = "two-week trial from 10/28"


def collect_dsh() -> dict:
    """DSH (DeepSeek Harness) — version + OpenRouter auth health; credits PAYG (no Coding Plan bars)."""
    import shutil
    import re

    out: dict = {
        "ok": False,
        "source": "dsh --version + ~/.dsh/collect-model.patch.yml + credential presence",
        "bars": [],
        "product": "DeepSeek Harness",
        "seat": SMALL_SEAT,
        "seat_role": "alternate + fallback",
        "model": None,
        "provider": None,
        "model_source": None,
    }
    try:
        dsh = DSH_BIN if DSH_BIN.exists() else Path(shutil.which("dsh") or "")
        if not dsh or not Path(dsh).exists():
            out["error"] = "dsh binary not found"
            return out
        out["binary"] = str(dsh)
        proc = subprocess.run(
            [str(dsh), "--version"],
            capture_output=True,
            text=True,
            timeout=20,
            stdin=subprocess.DEVNULL,
            env={**os.environ, "PATH": str(Path.home() / ".local/share/pnpm/bin") + ":" + os.environ.get("PATH", "")},
        )
        ver_blob = ((proc.stdout or "") + (proc.stderr or "")).strip().splitlines()
        out["cli_version"] = ver_blob[0].strip() if ver_blob else "unknown"

        # dsh 0.2.0 has no settings.yaml: model/provider come only from the per-run --patch overlay
        # (None when it cannot supply them; a leftover settings.yaml is never read).
        out["provider"], out["model"] = _dsh_overlay_model(DSH_DIR / "collect-model.patch.yml")
        if out["provider"] or out["model"]:
            out["model_source"] = "~/.dsh/collect-model.patch.yml (dsh --patch collect overlay)"

        # Auth health: key present but never expose value
        auth_ok = False
        mechanism = None
        cred = DSH_DIR / ".credentials.yaml"
        envf = DSH_DIR / ".env"
        for path, label in ((cred, "credentials.yaml"), (envf, ".env")):
            if not path.exists():
                continue
            blob = path.read_text()
            if "OPENROUTER_API_KEY" in blob or "openrouter" in blob.lower():
                # treat as configured if a non-empty assignment-like value exists
                if re.search(r"OPENROUTER_API_KEY\s*[=:]\s*\S+", blob) or re.search(
                    r"api[_-]?key\s*[:=]\s*\S+", blob, re.I
                ):
                    auth_ok = True
                    mechanism = label
                    break
        # also check process env (refresh may inherit)
        if not auth_ok and os.environ.get("OPENROUTER_API_KEY"):
            auth_ok = True
            mechanism = "env"

        out["auth_ok"] = auth_ok
        out["auth_mechanism"] = mechanism
        out["ok"] = bool(out.get("cli_version")) and auth_ok and out["cli_version"] != "unknown"
        out["detail"] = (
            "OpenRouter prepaid credits / PAYG (no Coding Plan quota bars). "
            "Card shows install + OpenRouter key presence + the collect model, read from the "
            "dsh --patch overlay ~/.dsh/collect-model.patch.yml (dsh 0.2.0 has no settings.yaml)."
        )
        if not auth_ok:
            out["error"] = "OpenRouter key missing — set OPENROUTER_API_KEY in ~/.dsh/.env"
    except Exception as e:
        out["error"] = safe_error(e)
    return out


# OpenRouter list prices, USD per 1M tokens — estimates only; models not listed show tokens, no cost.
QWEN_PRICES = {"qwen/qwen3.8-max-0902": {"input": 2.00, "cached_input": 0.25, "output": 6.00}}
QWEN_TRIAL_START = datetime(2026, 10, 25, tzinfo=PT)  # first PT day of the nightly-audit trial; earlier = setup tests
QWEN_TRIAL_END = datetime(2026, 10, 28, tzinfo=PT)  # exclusive: the trial is the PT days 10/25, 10/26 and 10/27
QWEN_TRIAL_RUNS = 3
QWEN_NOTE = "Qwen Code system prompt adds ~25k input tokens per request"
_QWEN_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}(?:/[A-Za-z0-9][A-Za-z0-9._:-]{0,95})?")
_QWEN_VERSION = re.compile(r"v?(\d{1,4}\.\d{1,4}\.\d{1,6}(?:-[0-9A-Za-z.]{1,32})?)")
_QWEN_COUNTERS = ("requests", "inputTokens", "outputTokens", "cachedTokens")
_QWEN_MAX_COUNTER = 2 ** 53 - 1  # Number.MAX_SAFE_INTEGER: qwen (Node.js) cannot write a larger count exactly
_OPENROUTER_KEY_LINE = re.compile(rb"""\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*['"]?[^\s'"#]""")


def _qwen_model_id(v) -> str | None:
    """A publishable provider/model id, else None (also refuses anything shaped like an API key)."""
    if isinstance(v, str) and _QWEN_ID.fullmatch(v) and not v.lower().startswith("sk-"):
        return v
    return None


def qwen_settings_model(path: Path) -> str | None:
    """model.name from ~/.qwen/settings.json (or a bare string `model`, the older layout)."""
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None
    model = data.get("model") if isinstance(data, dict) else None
    if isinstance(model, dict):
        model = model.get("name")
    return _qwen_model_id(model)


def openrouter_key_present(path: Path) -> bool:
    """True if the dotenv file gives OPENROUTER_API_KEY a non-empty value. Only this bool leaves here."""
    try:
        with path.open("rb") as fh:
            return any(_OPENROUTER_KEY_LINE.match(line) for line in fh)
    except OSError:
        return False


def _qwen_record(line: str):
    """One usage_record.jsonl line -> (sessionId, end-time ms, {model: counters}), or None if unusable."""
    try:
        o = json.loads(line)
    except Exception:
        return None
    if not isinstance(o, dict) or o.get("version") != 1:
        return None
    sid, ts, models = o.get("sessionId"), o.get("timestamp"), o.get("models")
    if not (isinstance(sid, str) and sid and isinstance(ts, int) and not isinstance(ts, bool) and ts > 0):
        return None
    if not isinstance(models, dict):
        return None
    try:
        datetime.fromtimestamp(ts / 1000, tz=timezone.utc)
    except (OverflowError, OSError, ValueError):
        return None
    per_model = {}
    for name, m in models.items():
        if not isinstance(m, dict):
            return None
        counts = {k: m.get(k, 0) for k in _QWEN_COUNTERS}  # a missing counter is 0
        if not all(isinstance(v, int) and not isinstance(v, bool) and 0 <= v <= _QWEN_MAX_COUNTER
                   for v in counts.values()):
            return None
        per_model[name] = counts
    return sid, ts, per_model


def _qwen_cost(model: str, c: dict) -> float | None:
    """Estimated USD at list price; None when the model has no price. thoughtsTokens are not added:
    qwen's records have totalTokens == inputTokens + outputTokens, so thoughts sit inside outputTokens."""
    p = QWEN_PRICES.get(model)
    if p is None:
        return None
    uncached = max(0, c["inputTokens"] - c["cachedTokens"])
    return (uncached * p["input"] + c["cachedTokens"] * p["cached_input"] + c["outputTokens"] * p["output"]) / 1e6


def _qwen_window(sessions: list) -> dict:
    w = {"sessions": len(sessions), "requests": 0, "input_tokens": 0, "cached_tokens": 0, "output_tokens": 0}
    cost, priced, unpriced, unpriced_tokens = 0.0, False, set(), 0
    for _ts, per_model in sessions:
        for name, c in per_model.items():
            w["requests"] += c["requests"]
            w["input_tokens"] += c["inputTokens"]
            w["cached_tokens"] += c["cachedTokens"]
            w["output_tokens"] += c["outputTokens"]
            usd = _qwen_cost(name, c)
            if usd is None:
                unpriced.add(name)
                unpriced_tokens += c["inputTokens"] + c["outputTokens"]
            else:
                cost, priced = cost + usd, True
    w["unpriced_models"] = len(unpriced)
    w["unpriced_tokens"] = unpriced_tokens
    # Cost covers priced models only: with any unpriced model (even at zero tokens) it is null, or just the
    # priced part when priced models are there too (unpriced_models says so). An overflowed sum is null too.
    w["est_cost_usd"] = round(cost, 6) if (priced or not unpriced) and math.isfinite(cost) else None
    return w


def _qwen_trial_days() -> tuple:
    """('2026-10-25', '2026-10-27'): the first and last PT day of the trial window."""
    return QWEN_TRIAL_START.strftime("%Y-%m-%d"), (QWEN_TRIAL_END - timedelta(days=1)).strftime("%Y-%m-%d")


def _qwen_excluded(bad: int, future: int) -> str:
    """'1 unreadable line, 2 future-dated records' — what summarize_qwen_usage left out ('' if nothing)."""
    parts = [f"{n} {label}{'' if n == 1 else 's'}" for n, label in
             ((bad, "unreadable line"), (future, "future-dated record")) if n]
    return ", ".join(parts)


def summarize_qwen_usage(text: str, now: datetime) -> dict:
    """Aggregate ~/.qwen/usage_record.jsonl text (one line per finished session).

    Mirrors qwen's own reader: version-1 records only, and the last record wins per sessionId. Other
    non-blank lines are counted in bad_lines; records dated after `now` (the collection time) in
    future_records. Neither counts toward usage or trial runs. state: "ok" (readable sessions),
    "no_runs" (no records at all) or "unreadable" (records, none usable), which is never shown as zero
    usage. sessionId is the de-dup key only; neither it nor the project path is returned.
    """
    sessions: dict = {}
    bad = dups = 0
    for line in text.splitlines():
        if not line.strip():
            continue
        rec = _qwen_record(line)
        if rec is None:
            bad += 1
            continue
        dups += rec[0] in sessions
        sessions[rec[0]] = rec[1:]
    now_ms = int(now.timestamp() * 1000)
    picked = [s for s in sessions.values() if s[0] <= now_ms]
    future = len(sessions) - len(picked)
    excluded = _qwen_excluded(bad, future)
    state = "ok" if picked else "unreadable" if excluded else "no_runs"
    windows = {
        "last_24h": _qwen_window([s for s in picked if s[0] >= now_ms - 86_400_000]),
        "last_7d": _qwen_window([s for s in picked if s[0] >= now_ms - 7 * 86_400_000]),
        "all_time": _qwen_window(picked),
    }
    models: dict = {}
    for ts, per_model in picked:
        for name, c in per_model.items():
            models.setdefault(name, []).append((ts, {name: c}))
    by_model = []
    for name, rows in sorted(models.items()):
        w = _qwen_window(rows)
        w["model"] = _qwen_model_id(name) or "unrecognized model id"
        w["priced"] = name in QWEN_PRICES
        by_model.append(w)
    # Rendered from dates at each refresh, with absolute days only: "starts", then "until", then "ended".
    first, last = _qwen_trial_days()
    phase = "not_started" if now < QWEN_TRIAL_START else "running" if now < QWEN_TRIAL_END else "ended"
    trial = {"seat": "trial", "window": f"nightly audits {first} to {last}", "first_day": first, "last_day": last,
             "starts_pt": iso_pt(QWEN_TRIAL_START), "ends_pt": iso_pt(QWEN_TRIAL_END), "phase": phase}
    if state == "unreadable":
        trial.update(runs=None, runs_display=None, setup_test_sessions=None, later_sessions=None,
                     status=f"trial status unavailable: no readable records ({excluded})")
    else:
        start_ms, end_ms = (int(t.timestamp() * 1000) for t in (QWEN_TRIAL_START, QWEN_TRIAL_END))
        runs = sum(1 for ts, _ in picked if start_ms <= ts < end_ms)
        later = sum(1 for ts, _ in picked if ts >= end_ms)
        shown = f"{min(runs, QWEN_TRIAL_RUNS)}/{QWEN_TRIAL_RUNS}"
        if phase == "not_started":
            status = f"starts {first} (nightly ~3 AM PT, until {last}); {shown} runs"
        elif phase == "running":
            status = f"{shown} runs since {first}; trial until {last}"
        else:
            status = f"ended {last}; {shown} runs"
        if runs > QWEN_TRIAL_RUNS:
            status += f"; {runs} sessions"
        if later:
            status += f"; {later} later session{'' if later == 1 else 's'} not counted"
        if excluded:
            status += f" (not counted: {excluded})"
        trial.update(runs=runs, runs_display=shown, setup_test_sessions=sum(1 for ts, _ in picked if ts < start_ms),
                     later_sessions=later, status=status)
    return {
        "state": state,
        "sessions": len(picked),
        "bad_lines": bad,
        "future_records": future,
        "duplicate_records": dups,
        "last_session_pt": ts_to_pt(max(s[0] for s in picked) / 1000) if picked else None,
        "windows": windows,
        "models": by_model,
        "trial": trial,
    }


def collect_qwen() -> dict:
    """Qwen Code trial seat — version, model, OpenRouter key presence, and usage + estimated cost from
    ~/.qwen/usage_record.jsonl. OpenRouter PAYG: no plan bars."""
    out: dict = {
        "ok": False,
        "source": "qwen --version + ~/.qwen/settings.json + ~/.qwen/usage_record.jsonl + key presence",
        "bars": [],
        "product": "Qwen Code",
        "seat": "trial",
        "provider": "OpenRouter",
        "model": None,
        "cli_version": None,
        "auth_ok": False,
        "auth_mechanism": None,
        "note": QWEN_NOTE,
        "pricing": {
            "label": "estimated, list price",
            "usd_per_million_tokens": QWEN_PRICES,
            "uncached_input": "inputTokens - cachedTokens (floor 0)",
        },
    }
    errors = []
    try:
        home = Path.home()  # resolved per call, like collect_kimi (tests run with a temp HOME)
        if not QWEN_BIN.exists():
            errors.append("qwen binary not found")
        else:
            out["binary"] = str(QWEN_BIN)
            try:
                proc = subprocess.run(
                    [str(QWEN_BIN), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    stdin=subprocess.DEVNULL,
                    env={**os.environ, "PATH": "/usr/local/bin:" + os.environ.get("PATH", "")},  # env node
                )
                lines = (proc.stdout or "").strip().splitlines()
                m = _QWEN_VERSION.fullmatch(lines[0].strip()) if lines else None
                if m:
                    out["cli_version"] = m.group(1)
                else:  # never echo unexpected output into the public page
                    errors.append(f"qwen --version printed no version (exit {proc.returncode})")
            except Exception as e:
                errors.append(safe_error(e))
        out["model"] = qwen_settings_model(home / ".qwen" / "settings.json")
        # ~/.local/bin/qwen-or sources ~/.dsh/.env at launch; presence check only, the value is never read out.
        out["auth_ok"] = openrouter_key_present(home / ".dsh" / ".env")
        if out["auth_ok"]:
            out["auth_mechanism"] = "~/.dsh/.env via qwen-or"
        else:
            errors.append("OpenRouter key missing — qwen-or sources OPENROUTER_API_KEY from ~/.dsh/.env")
        try:
            text = (home / ".qwen" / "usage_record.jsonl").read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            text = ""  # no finished session yet
        except Exception as e:
            text = None  # unreadable is not "no runs": leave usage/trial unset so the card says so
            errors.append(f"usage_record.jsonl unreadable: {safe_error(e)}")
        if text is not None:
            out["usage"] = summarize_qwen_usage(text, now_pt())
            out["trial"] = out["usage"].pop("trial")
        out["ok"] = bool(out["cli_version"]) and out["auth_ok"]
    except Exception as e:
        errors.append(safe_error(e))
    if errors:
        out["error"] = "; ".join(errors)
    return out


_OPENCODE_COUNTERS = ("input_tokens", "cached_tokens", "cache_write_tokens", "output_tokens", "reasoning_tokens", "cost_usd")


def opencode_config(path: Path) -> dict:
    """provider, model and reasoning effort from opencode.json ("model": "<provider>/<model id>", effort under
    provider.<provider>.models.<model id>.options.reasoning). None for anything missing or unpublishable."""
    out = {"provider": None, "model": None, "effort": None}
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return out
    ref = data.get("model") if isinstance(data, dict) else None
    provider, _, model = ref.partition("/") if isinstance(ref, str) else ("", "", "")
    if not (_qwen_model_id(provider) and _qwen_model_id(model)):
        return out
    out["provider"], out["model"] = provider, model
    try:
        effort = data["provider"][provider]["models"][model]["options"]["reasoning"]["effort"]
    except (KeyError, TypeError):
        effort = None
    out["effort"] = effort if isinstance(effort, str) and _KIMI_EFFORT.fullmatch(effort) else None
    return out


def _opencode_connect(db: Path) -> sqlite3.Connection:
    """Open mode=ro; decode TEXT per row so malformed UTF-8 cannot enter an exception message.
    SQLite may still update WAL sidecars; mode=ro prevents writes to the database itself."""
    con = sqlite3.connect(db.as_uri() + "?mode=ro", uri=True, timeout=5)
    con.text_factory = bytes
    return con


def _opencode_text(value) -> str:
    if isinstance(value, bytes):
        return value.decode("utf-8", errors="strict")
    if isinstance(value, str):
        return value
    raise ValueError("invalid text field")


def _opencode_request(o: dict):
    """Counters of one assistant message (one model request in OpenCode 1.19.4), or None if unusable.
    input_tokens = all prompt tokens (OpenCode's uncached input + cache read + cache write), as on the Qwen
    card; reasoning is its own count (OpenCode's total = input + output + reasoning + cache)."""
    tok, cost = o.get("tokens"), o.get("cost")
    cache = tok.get("cache") if isinstance(tok, dict) else None
    if not isinstance(cache, dict):
        return None
    counts = [tok.get(k) for k in ("input", "output", "reasoning")] + [cache.get(k) for k in ("read", "write")]
    if not all(isinstance(v, int) and not isinstance(v, bool) and v >= 0 for v in counts):
        return None
    if isinstance(cost, bool) or not isinstance(cost, (int, float)):
        return None
    try:
        cost = float(cost)
    except (OverflowError, ValueError, TypeError):
        return None
    if not math.isfinite(cost) or cost < 0:
        return None
    inp, out, reasoning, read, write = counts
    return {"model": _qwen_model_id(o.get("modelID")) or "unrecognized model id",
            "input_tokens": inp + read + write, "cached_tokens": read, "cache_write_tokens": write,
            "output_tokens": out, "reasoning_tokens": reasoning, "cost_usd": cost}


def _opencode_root(sid, parents: dict):
    """A subagent's child session counts toward its top-level session; a parent cycle maps to its lowest id."""
    seen = []
    while sid not in seen:
        seen.append(sid)
        if parents.get(sid) is None:
            return sid
        sid = parents[sid]
    return min(seen[seen.index(sid):])


def _opencode_execution(o: dict):
    """Private fork-stable identity from immutable execution metadata, never settlement fields.
    Completion time, finish status, errors, tokens and cost may change after history is copied.
    Without a valid execution clock, keep rows separate rather than guess from equal counters."""
    clock = o.get("time")
    if not isinstance(clock, dict):
        return None
    created = clock.get("created")
    if not isinstance(created, int) or isinstance(created, bool) or created <= 0:
        return None
    try:
        identity = {k: o.get(k) for k in ("providerID", "modelID", "mode", "agent", "variant", "path")}
        identity["created"] = created
        return json.dumps(identity,
                          sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return None


def _opencode_compaction_history(parent_id: str, sid: str, messages: dict, input_parts: dict, compactions: dict):
    """Immutable compaction flags plus corroborating preceding history, with references normalized.
    tail_start_id is assigned after model processing and rewritten by forks: validate its target but
    do not make this mutable selection field part of execution identity."""
    positions, history, corroborated = {}, [], False
    for mid, (session, data) in messages.items():
        if session != sid:
            continue
        position = len(history)
        positions[mid] = position
        role, clock = data.get("role"), data.get("time")
        created = clock.get("created") if isinstance(clock, dict) else None
        if not isinstance(created, int) or isinstance(created, bool) or created <= 0:
            return None
        if role == "user":
            entry = {k: data.get(k) for k in ("agent", "model", "format", "system", "tools")}
            parts = input_parts.get((sid, mid)) or []
            corroborated = corroborated or bool(parts)
            entry.update(role=role, created=created, parts=parts, compactions=[])
            for part in compactions.get((sid, mid), []):
                if not isinstance(part.get("auto"), bool) or ("overflow" in part and not isinstance(part["overflow"], bool)):
                    return None
                tail_id = part.get("tail_start_id")
                if tail_id is not None:
                    tail = positions.get(tail_id) if isinstance(tail_id, str) else None
                    if tail is None:
                        return None
                entry["compactions"].append({"auto": part["auto"], "overflow": part.get("overflow")})
        elif role == "assistant":
            execution = _opencode_execution(data)
            reference = data.get("parentID")
            parent = positions.get(reference) if isinstance(reference, str) else None
            if execution is None or parent is None or parent >= position:
                return None
            entry = {"role": role, "execution": execution, "parent": parent}
        else:
            return None
        history.append(entry)
        if mid == parent_id:
            return history if corroborated else None
    return None


def _opencode_history(o: dict, messages: dict, input_parts: dict, compactions: dict):
    """Corroborate copied history using the referenced user message and its ordered input parts.
    Forks remap ids but retain this preceding history. Matching execution clocks alone is not proof."""
    parent_id = o.get("parentID")
    parent = messages.get(parent_id) if isinstance(parent_id, str) else None
    if parent is None:
        return None
    sid, user = parent
    clock = user.get("time")
    created = clock.get("created") if isinstance(clock, dict) else None
    parts = input_parts.get((sid, parent_id))
    if not parts and compactions.get((sid, parent_id)):
        parts = _opencode_compaction_history(parent_id, sid, messages, input_parts, compactions)
    if user.get("role") != "user" or not parts or not isinstance(created, int) or isinstance(created, bool) or created <= 0:
        return None
    try:
        history = {k: user.get(k) for k in ("agent", "model", "format", "system", "tools")}
        history.update(created=created, parts=parts)
        return json.dumps(history, sort_keys=True, separators=(",", ":"), allow_nan=False)
    except (TypeError, ValueError, OverflowError):
        return None


def _opencode_window(reqs: list) -> dict:
    w = {"sessions": len({r["session"] for r in reqs}), "requests": len(reqs)}
    for k in _OPENCODE_COUNTERS:
        w[k] = sum(r[k] for r in reqs)
    if math.isfinite(w["cost_usd"]):
        w["cost_usd"] = round(w["cost_usd"], 6)
    else:
        w["cost_usd"] = None
        w["cost_overflow"] = True
    return w


def _opencode_excluded(bad: int, future: int) -> str:
    """'1 unreadable row, 2 future-dated rows' — what summarize_opencode_usage left out ('' if nothing)."""
    parts = [f"{n} {label}{'' if n == 1 else 's'}" for n, label in
             ((bad, "unreadable row"), (future, "future-dated row")) if n]
    return ", ".join(parts)


def summarize_opencode_usage(db: Path, now: datetime) -> dict:
    """Aggregate model requests from OpenCode's opencode.db, opened read-only.

    Only assistant messages with persisted step-start/step-finish evidence represent model requests.
    Merge matching immutable execution metadata only with corroborating copied parent/input history.
    Reconcile counters separately from the canonical origin session, using the earliest session creation.
    Repeated executions within a session retain their multiplicity.
    state: "ok", "no_requests" (readable, no model executions), "missing" (no
    opencode.db, so no lookup ran: never shown as zero) or "unreadable" (a database error, or rows but none
    usable). Rows that do not parse are counted in bad_rows, rows dated after `now` (the collection time)
    in future_records; neither counts. Session ids are grouping keys only; paths, titles and prompts (the
    part table) are never published. Parts are read only to identify model-execution evidence.
    """
    if not db.is_file():
        return {"state": "missing"}
    parents, session_created, input_parts, compactions, evidence, bad = {}, {}, {}, {}, set(), 0
    try:
        con = _opencode_connect(db)
        try:
            con.execute("BEGIN")  # one consistent read of messages and their execution evidence
            for sid, parent, created in con.execute("SELECT id, parent_id, time_created FROM session"):
                try:
                    sid = _opencode_text(sid)
                    parents[sid] = _opencode_text(parent) if parent is not None else None
                    session_created[sid] = created if isinstance(created, int) and not isinstance(created, bool) and created > 0 else None
                except (UnicodeError, ValueError, TypeError):
                    bad += 1
            for sid, mid, data in con.execute("SELECT session_id, message_id, data FROM part ORDER BY id"):
                try:
                    sid, mid = _opencode_text(sid), _opencode_text(mid)
                    part = json.loads(_opencode_text(data))
                    if not isinstance(part, dict):
                        raise ValueError("invalid part")
                    if part.get("type") in ("step-start", "step-finish"):
                        evidence.add((sid, mid))
                    elif part.get("type") == "compaction":
                        compactions.setdefault((sid, mid), []).append(
                            {k: part[k] for k in ("auto", "overflow", "tail_start_id") if k in part})
                    elif (part.get("type") == "text" and isinstance(part.get("text"), str) and part["text"].strip()
                          or part.get("type") == "file" and isinstance(part.get("url"), str) and part["url"]):
                        payload = {k: v for k, v in part.items() if k not in ("id", "messageID", "sessionID")}
                        input_parts.setdefault((sid, mid), []).append(
                            json.dumps(payload, sort_keys=True, separators=(",", ":"), allow_nan=False))
                except (UnicodeError, ValueError, TypeError):
                    bad += 1
            rows = con.execute("SELECT id, session_id, time_created, time_updated, data FROM message"
                               " ORDER BY time_created, id").fetchall()
        finally:
            con.close()
    except Exception:  # fixed category only: database exceptions can contain private row text
        return {"state": "unreadable", "error": "opencode.db unreadable: database read failed"}
    now_ms = int(now.timestamp() * 1000)
    messages, decoded = {}, []
    for mid, sid, ts, updated, data in rows:
        try:
            mid, sid = _opencode_text(mid), _opencode_text(sid)
            o = json.loads(_opencode_text(data))
            if not isinstance(o, dict):
                raise ValueError("invalid message")
            messages[mid] = (sid, o)
            decoded.append((mid, sid, ts, updated, o))
        except Exception:
            bad += 1
    future, deduplicated, ignored = 0, 0, 0
    executions, occurrences = {}, {}
    for mid, sid, ts, updated, o in decoded:
        role = o.get("role") if isinstance(o, dict) else None
        if role == "user":
            continue  # the prompt side of a turn, not a model request
        req = _opencode_request(o) if role == "assistant" else None
        if req is None or not (isinstance(ts, int) and not isinstance(ts, bool) and ts > 0):
            bad += 1
            continue
        if (sid, mid) not in evidence:
            ignored += 1  # native shell/subtask wrappers do not execute a model
            continue
        execution = _opencode_execution(o)
        if execution is not None:
            ts = o["time"]["created"]  # fork insertion time is not a new model execution
        if ts > now_ms:
            future += 1
            continue
        history = _opencode_history(o, messages, input_parts, compactions) if execution is not None else None
        if history is not None:
            slot = (sid, execution, history)
            occurrences[slot] = occurrences.get(slot, 0) + 1
            identity = (execution, history, occurrences[slot])
        else:
            identity = (sid, mid)
        req["ts"], req["session"] = ts, _opencode_root(sid, parents)
        completed = (o.get("time") or {}).get("completed") if isinstance(o.get("time"), dict) else None
        completed = completed if isinstance(completed, int) and not isinstance(completed, bool) and completed >= ts else 0
        updated = updated if isinstance(updated, int) and not isinstance(updated, bool) else 0
        rank = (completed, sum(req[k] for k in _OPENCODE_COUNTERS if k != "cost_usd"), req["cost_usd"], updated)
        created = session_created.get(sid)
        origin = (created is None, created or 0, mid, sid)
        previous = executions.get(identity)
        if previous is None:
            executions[identity] = (rank, req, origin)
        else:
            deduplicated += 1
            canonical_session = req["session"] if origin < previous[2] else previous[1]["session"]
            counters = req if rank > previous[0] else previous[1]
            counters["session"] = canonical_session
            executions[identity] = (max(rank, previous[0]), counters, min(origin, previous[2]))
    reqs = [req for _, req, _ in executions.values()]
    excluded = _opencode_excluded(bad, future)
    windows = {
        "last_24h": _opencode_window([r for r in reqs if r["ts"] >= now_ms - 86_400_000]),
        "last_7d": _opencode_window([r for r in reqs if r["ts"] >= now_ms - 7 * 86_400_000]),
        "all_time": _opencode_window(reqs),
    }
    models = []
    for name in sorted({r["model"] for r in reqs}):
        w = _opencode_window([r for r in reqs if r["model"] == name])
        w["model"] = name
        models.append(w)
    return {
        "state": "ok" if reqs else "unreadable" if excluded else "no_requests",
        "requests": len(reqs),
        "sessions": windows["all_time"]["sessions"],
        "bad_rows": bad,
        "future_records": future,
        "deduplicated_requests": deduplicated,
        "ignored_assistant_rows": ignored,
        "last_run_pt": ts_to_pt(max(r["ts"] for r in reqs) / 1000) if reqs else None,
        "windows": windows,
        "models": models,
    }


def collect_opencode() -> dict:
    """OpenCode · GLM-5.3, the first-choice default small model seat — CLI version, configured model,
    OpenRouter key presence, and usage + recorded cost from opencode.db (read-only). OpenRouter PAYG: no
    plan bars. Publishes no paths, session ids or prompts."""
    out: dict = {
        "ok": False,
        "source": "opencode --version + opencode.json + opencode.db (read-only) + key presence",
        "bars": [],
        "product": "OpenCode",
        "seat": SMALL_SEAT,
        "seat_role": "first choice",
        "provider": None,
        "model": None,
        "effort": None,
        "cli_version": None,
        "auth_ok": False,
        "auth_mechanism": None,
        "cost_note": "cost as OpenCode recorded it per request; not an OpenRouter invoice",
    }
    errors = []
    try:
        home = Path.home()  # resolved per call, like collect_qwen (tests run with a temp HOME)
        if not OPENCODE_BIN.exists():
            errors.append("opencode binary not found")
        else:
            try:
                proc = subprocess.run(
                    [str(OPENCODE_BIN), "--version"],
                    capture_output=True,
                    text=True,
                    timeout=20,
                    stdin=subprocess.DEVNULL,
                    env={**os.environ, "OPENCODE_DISABLE_AUTOUPDATE": "1"},  # a refresh never updates the CLI
                )
                lines = (proc.stdout or "").strip().splitlines()
                m = _QWEN_VERSION.fullmatch(lines[0].strip()) if lines else None  # same x.y.z shape
                if m:
                    out["cli_version"] = m.group(1)
                else:  # never echo unexpected output into the public page
                    errors.append(f"opencode --version printed no version (exit {proc.returncode})")
            except subprocess.TimeoutExpired:
                errors.append("opencode version check timed out")
            except Exception:
                errors.append("opencode version check failed")
        out.update(opencode_config(home / ".config" / "opencode" / "opencode.json"))
        # ~/.local/bin/opencode-or sources ~/.dsh/.env at launch; presence check only, the value is never read out.
        out["auth_ok"] = openrouter_key_present(home / ".dsh" / ".env")
        if out["auth_ok"]:
            out["auth_mechanism"] = "DSH .env via opencode-or"
        else:
            errors.append("OpenRouter key missing — opencode-or sources OPENROUTER_API_KEY from the DSH .env")
        usage = summarize_opencode_usage(home / ".local" / "share" / "opencode" / "opencode.db", now_pt())
        if usage.get("error"):
            errors.append(usage.pop("error"))
        out["usage"] = usage
        out["ok"] = bool(out["cli_version"]) and out["auth_ok"]
    except Exception:
        errors.append("opencode collection failed")
    if errors:
        out["error"] = "; ".join(errors)
    return out


# ── OpenRouter spend (one key, shared by DSH and Qwen Code) ────────────────

OPENROUTER_KEY_URL = "https://openrouter.ai/api/v1/key"
OPENROUTER_SEATS = ["DSH", "Qwen Code"]
# (published name, /api/v1/key field): OpenRouter counts UTC days and UTC weeks starting Monday
_OPENROUTER_WINDOWS = (("today_utc", "usage_daily"), ("week_utc", "usage_weekly"), ("month_utc", "usage_monthly"),
                       ("all_time", "usage"))
_OPENROUTER_KEY_ASSIGN = re.compile(r"""\s*(?:export\s+)?OPENROUTER_API_KEY\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s#]*))""")
_OPENROUTER_KEY_SHAPE = re.compile(r"[A-Za-z0-9._-]{8,256}")


def read_openrouter_key(path: Path) -> str | None:
    """OPENROUTER_API_KEY from a dotenv file (the last assignment wins, as when a shell sources it), or None
    when it is missing, empty or not a plain value. The key stays in memory: never published, logged or
    written anywhere."""
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except (OSError, UnicodeDecodeError):
        return None
    key = None
    for line in lines:
        m = _OPENROUTER_KEY_ASSIGN.match(line)
        if m:
            key = next(g for g in m.groups() if g is not None)
    return key if key and _OPENROUTER_KEY_SHAPE.fullmatch(key) else None


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects, so the key is only ever sent to the URL asked for."""

    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _https_context() -> ssl.SSLContext:
    """Default verifying TLS context. A python.org build that ships no CA certificates gets the macOS
    system bundle /etc/ssl/cert.pem instead; verification is never turned off."""
    ctx = ssl.create_default_context()
    if not ctx.cert_store_stats().get("x509_ca") and Path("/etc/ssl/cert.pem").is_file():
        ctx.load_verify_locations(cafile="/etc/ssl/cert.pem")
    return ctx


def _openrouter_get(url: str, api_key: str, timeout: float = 15):
    """GET one OpenRouter API URL -> parsed JSON body; raises on HTTP, network and JSON errors. The key goes
    only in an unredirected Authorization header: never in argv (no curl), never to a redirect target."""
    req = urllib.request.Request(url, headers={"Accept": "application/json", "User-Agent": "usage-dashboard"})
    req.add_unredirected_header("Authorization", "Bearer " + api_key)
    opener = urllib.request.build_opener(_NoRedirect, urllib.request.HTTPSHandler(context=_https_context()))
    with opener.open(req, timeout=timeout) as resp:
        return json.loads(resp.read(1_000_000).decode("utf-8"))


def _usd_amount(v, allow_negative=False):
    """A finite number (not a bool), non-negative unless allowed, else None."""
    if isinstance(v, bool) or not isinstance(v, (int, float)):
        return None
    try:
        f = float(v)
    except OverflowError:
        return None
    return v if math.isfinite(f) and (allow_negative or f >= 0) else None


def _openrouter_window_labels(now_utc: datetime) -> dict:
    """Dated labels for the key's UTC windows as of the fetch, so a static page never says "today"."""
    day = now_utc.astimezone(timezone.utc).date()
    monday = day - timedelta(days=day.weekday())
    return {"today_utc": f"Day {day.isoformat()} (UTC)", "week_utc": f"Week from Mon {monday.isoformat()} (UTC)",
            "month_utc": f"Month {day.strftime('%Y-%m')} (UTC)", "all_time": "All time"}


def collect_openrouter(now: datetime | None = None, *, clock=None) -> dict:
    """OpenRouter spend of the one key DSH and Qwen Code both use (GET /api/v1/key), in USD. The key's own
    counters cover both seats, so the figures are combined, not split per seat. On any failure every figure
    stays None, which the card shows as "unavailable" (never $0); errors are fixed phrases, never exception
    text."""
    # An injected fixed time keeps historical fixture calls deterministic; production
    # samples both sides of the request and retries a UTC reset boundary once.
    clock = clock or ((lambda: now) if now is not None else (lambda: datetime.now(timezone.utc)))
    out: dict = {
        "ok": False,
        "source": "GET https://openrouter.ai/api/v1/key with OPENROUTER_API_KEY from ~/.dsh/.env (read per build, never stored)",
        "scope": "one shared key: DSH + Qwen Code combined, not split per seat",
        "seats": list(OPENROUTER_SEATS),
        "unit": "USD (OpenRouter credits are US dollars)",
        "windows": {"today_utc": "Day (UTC)", "week_utc": "Week from Monday (UTC)", "month_utc": "Month (UTC)",
                    "all_time": "All time"},  # dated once a fetch succeeds
        "spend_usd": dict.fromkeys(name for name, _ in _OPENROUTER_WINDOWS),
        "limit_usd": None,
        "limit_remaining_usd": None,
        "limit_reset": None,
        "fetched_at": None,
    }
    key = read_openrouter_key(Path.home() / ".dsh" / ".env")  # ~ resolved per call (tests use a temp HOME)
    if not key:
        out["error"] = "OPENROUTER_API_KEY not found in ~/.dsh/.env"
        return out
    try:
        for _attempt in range(2):
            started_at = clock()
            body = _openrouter_get(OPENROUTER_KEY_URL, key)
            fetched_at = clock()
            if started_at.astimezone(timezone.utc).date() == fetched_at.astimezone(timezone.utc).date():
                break
        else:
            out["error"] = "OpenRouter /api/v1/key request crossed a UTC reset boundary twice"
            return out
    except urllib.error.HTTPError as e:
        out["error"] = f"OpenRouter /api/v1/key returned HTTP {int(e.code)}"
        return out
    except (urllib.error.URLError, OSError):
        out["error"] = "OpenRouter /api/v1/key request failed (network or timeout)"
        return out
    except ValueError:
        out["error"] = "OpenRouter /api/v1/key response unreadable (not JSON)"
        return out
    except Exception:
        out["error"] = "OpenRouter /api/v1/key request failed"
        return out
    data = body.get("data") if isinstance(body, dict) else None
    spend = {name: _usd_amount(data.get(field)) for name, field in _OPENROUTER_WINDOWS} if isinstance(data, dict) else {}
    if len(spend) != len(_OPENROUTER_WINDOWS) or any(v is None for v in spend.values()):
        out["error"] = "OpenRouter /api/v1/key response unreadable (usage counters missing or invalid)"
        return out
    out["spend_usd"] = spend
    out["limit_usd"] = _usd_amount(data.get("limit"))
    out["limit_remaining_usd"] = _usd_amount(data.get("limit_remaining"), allow_negative=True)
    reset = data.get("limit_reset")
    out["limit_reset"] = reset if isinstance(reset, str) and re.fullmatch(r"[a-z]{1,16}", reset) else None
    out["windows"] = _openrouter_window_labels(fetched_at)
    out["fetched_at"] = iso_pt(fetched_at)
    out["ok"] = True
    return out




def _cron_fires_per_week(cron: str):
    """Coarse weekly fire estimate from a 5-field cron. Not billing."""
    parts = cron.split()
    if len(parts) != 5:
        return None
    minute, hour, dom, month, dow = parts

    def field_count(field: str, span: int) -> float:
        if field == "*":
            return float(span)
        if field.startswith("*/"):
            try:
                step = int(field[2:])
                return max(1.0, span / step)
            except (ValueError, ZeroDivisionError):
                return 1.0
        n = 0
        for piece in field.split(","):
            if "-" in piece and "/" not in piece:
                a, b = piece.split("-", 1)
                try:
                    n += int(b) - int(a) + 1
                except ValueError:
                    n += 1
            else:
                n += 1
        return float(max(1, n))

    if "-" in hour and "," not in hour and hour[0].isdigit():
        try:
            a, b = hour.split("-", 1)
            hours_per_day = float(int(b) - int(a) + 1)
        except ValueError:
            hours_per_day = field_count(hour, 24)
    else:
        hours_per_day = field_count(hour, 24)

    if dow == "*":
        days = 7.0
    elif dow == "1-5":
        days = 5.0
    else:
        days = field_count(dow, 7)

    if minute.startswith("*/"):
        try:
            step = int(minute[2:])
            fires_per_hour = 60.0 / step
        except (ValueError, ZeroDivisionError):
            fires_per_hour = 1.0
        return round(fires_per_hour * hours_per_day * days, 1)

    if "," in minute:
        # Explicit minute list, e.g. Github EM heartbeat "4,19,34,49 * * * *".
        per_hour = float(len([p for p in minute.split(",") if p.strip()]))
        return round(per_hour * hours_per_day * days, 1)

    if "," in hour:
        return round(field_count(hour, 24) * days, 1)

    return round(hours_per_day * days, 1)


def _normalize_cron_cell(raw: str) -> tuple:
    """Return (cron_5field_or_None, kind, display). kind is cron|event|unknown."""
    cell = raw.strip().strip("`").strip()
    # strip CRON_TZ=Zone prefix
    cell = re.sub(r"^CRON_TZ=\S+\s+", "", cell)
    # if parenthetical cadence after cron, keep leading 5 fields
    lower = cell.lower()
    if "github listener" in lower or "listener" in lower and "cron" not in lower.split()[:1]:
        return None, "event", cell[:120]
    # extract first 5 cron-ish tokens
    tokens = cell.replace("`", " ").split()
    # drop trailing prose after 5 fields
    if len(tokens) >= 5:
        five = " ".join(tokens[:5])
        # validate roughly
        if all(re.match(r"^[0-9*,/\\-]+$", t) or t in ("*",) for t in tokens[:5]):
            return five, "cron", five
        # still try
        if re.match(r"^[\\d*/,-]+", tokens[0]):
            return five, "cron", five
    return None, "unknown", cell[:120]


def _parse_active_routine_table(blob: str, owner: str) -> list:
    """Parse Active markdown table (## Active or first table)."""
    rows = []
    lines = blob.splitlines()
    # Prefer ## Active section; else first markdown table in file
    start_i = None
    for i, line in enumerate(lines):
        if line.startswith("## Active"):
            start_i = i + 1
            break
    if start_i is None:
        for i, line in enumerate(lines):
            if line.startswith("|") and "Name" in line:
                start_i = i
                break
    if start_i is None:
        return rows

    for line in lines[start_i:]:
        if line.startswith("## "):
            break
        if not line.startswith("|"):
            # blank after table ends it
            if rows and line.strip() == "":
                # allow blank inside; only stop on non-table content after we started data rows
                continue
            if rows and line.strip() and not line.startswith("|"):
                break
            continue
        cols = [c.strip() for c in line.strip("|").split("|")]
        if len(cols) < 2 or cols[0] in ("Name",) or cols[0].startswith("-"):
            continue
        name = cols[0]
        cron_raw = cols[1]
        notes = cols[-1] if len(cols) > 2 else ""
        if notes in ("Notes",) or set(notes.replace(" ", "")) <= {"-"}:
            notes = ""
        cron, kind, display = _normalize_cron_cell(cron_raw)
        if kind == "event":
            rows.append({
                "owner": owner,
                "name": name,
                "cron": "(event listener)",
                "fires_per_week": None,
                "notes": (notes + " · event-driven").strip(" ·"),
                "status": "enabled",
            })
            continue
        if not cron:
            rows.append({
                "owner": owner,
                "name": name,
                "cron": display,
                "fires_per_week": None,
                "notes": notes or "unparsed schedule",
                "status": "enabled",
            })
            continue
        rows.append({
            "owner": owner,
            "name": name,
            "cron": cron,
            "fires_per_week": _cron_fires_per_week(cron),
            "notes": notes,
            "status": "enabled",
        })
    return rows


def _newest_dump(hunt: Path, glob_pat: str):
    matches = sorted(hunt.glob(glob_pat), key=lambda p: p.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def collect_routine_proxy() -> dict:
    """Fleet routine fire-count proxy — NOT dollars. Newest Collection dump + hardcoded Manage/Github."""
    vault = Path.home() / "Documents/agent-context"
    hunt = vault / "Hunt/agent-manage"
    rows = []
    sources = []

    # Live vault card Agents/agent-manage-bot.md Standing routines (refreshed 2026-10-05).
    manage = [
        ("Agent Manage Bot", "Monday specialist ops nudge", "11 8 * * 1", "paused — merged into weekly playbook↔card sync 2026-09-28", "paused"),
        ("Agent Manage Bot", "Daily harness-lab collect kick", "55 8 * * *", "Agy/Muse/DSH Lab scout", "enabled"),
        ("Agent Manage Bot", "Weekday usage dashboard refresh", "5 9 * * 1-5", "weekday integrity check", "enabled"),
        ("Agent Manage Bot", "PR board sweep daily", "9 9 * * *", "CI/conflict/stall → Coding EM; never merge", "enabled"),
        ("Agent Manage Bot", "Weekly playbook ↔ card sync", "47 10 * * 1", "playbook→card + kill review + ops nudge", "enabled"),
        ("Agent Manage Bot", "Daily harness-lab curate publish", "45 16 * * *", "KEEP-only Lab publish", "enabled"),
        ("Agent Manage Bot", "Nightly Mac harness audit", "59 2 * * *", "rotate one Mac CLI; dual-LGTM; no merge", "enabled"),
        ("Agent Manage Bot", "Coding EM kick pickup check", "6 4,8 * * *", "ledger vs tmux/PRs", "enabled"),
        ("Agent Manage Bot", "Jev shadow savings tally", "Monday via weekly sync", "paused / folded into Monday weekly sync (Haiyuan kick 2026-10-05); prior 4 8 * * 1-5", "paused"),
        ("Agent Manage Bot", "Daily Mac CLI update", "53 7 * * *", "bump Mac CLIs + verify defaults", "enabled"),
        ("Agent Manage Bot", "Field Brief 6h orchestration watch", "50 0,6,12,18 * * *", "paused — Collection :44 sole miss detector", "paused"),
    ]
    # Github Bot durable routines, hardcoded (2026-10-05): the on-disk
    # *github-bot-active-routines.md dumps went stale (*/5 heartbeat), so the
    # proxy no longer reads Github rows from dumps — refresh cannot revert.
    github = [
        ("Github Bot", "EM heartbeat (all agent tasks)", "4,19,34,49 * * * *", "durable; was */5, token-save */15", "enabled"),
        ("Github Bot", "Daily vault consolidation 20:57", "57 20 * * *", "durable", "enabled"),
    ]
    for owner, name, cron, notes, status in manage + github:
        rows.append({
            "owner": owner,
            "name": name,
            "cron": cron,
            "fires_per_week": _cron_fires_per_week(cron) if status == "enabled" else 0,
            "notes": notes,
            "status": status,
        })
    sources.append("Manage Bot live vault card 2026-10-05 (%d)" % len(manage))
    sources.append("Github Bot hardcoded */15 (4,19,34,49) + vault consolidation (%d)" % len(github))

    dump_specs = [
        ("*collection-bot-active-routines.md", "Collection Bot"),
    ]
    dump_paths = []
    for pat, owner in dump_specs:
        dump = _newest_dump(hunt, pat) if hunt.is_dir() else None
        if not dump:
            sources.append("%s dump missing" % owner)
            continue
        parsed = _parse_active_routine_table(dump.read_text(), owner)
        rows.extend(parsed)
        sources.append("%s %s (%d)" % (owner, dump.name, len(parsed)))
        dump_paths.append(str(dump))

    # fires/week total excludes None (event listeners)
    total = sum(r["fires_per_week"] or 0 for r in rows)
    rows.sort(key=lambda r: (-(r["fires_per_week"] if r["fires_per_week"] is not None else -1), r["owner"], r["name"]))
    return {
        "ok": True,
        "proxy": True,
        "label": "fires/week estimate — NOT dollars",
        "source": "; ".join(sources),
        "dump_paths": dump_paths,
        "rows": rows,
        "total_fires_per_week": round(total, 1),
        "detail": (
            "Coarse cron math only. Manage Bot live vault card 2026-10-05 + hardcoded "
            "Github Bot rows (heartbeat */15 at 4,19,34,49; Github dump not read) + "
            "newest *collection-bot-active-routines.md under Hunt/agent-manage/ (may "
            "still be stale — no Collection rows invented). Event listeners show as "
            "(event listener) with no fires/week. Not tokens or plan spend."
        ),
    }



def _mark_stale(data: dict, cache: dict | None) -> dict:
    """Set stale / stale_reason from collected_at_*; never let an old cache pass as current."""
    stale, reason = staleness(cache)
    data["stale"] = stale
    data["stale_reason"] = reason
    return data


def collect_grok() -> dict:
    live = _collect_grok_from_box()
    if live:
        return _mark_stale(live, live)
    if GROK_CACHE.exists():
        try:
            data = json.loads(GROK_CACHE.read_text())
            data["ok"] = True
            data.setdefault("source", "grok_box_activity.json (cached from box)")
            data.setdefault("note", GROK_NOTE)
            data["links"] = dict(GROK_LINKS)
            bots = _apply_manage_bot_client_counts(normalize_bots(data.get("bots") or []))
            bots = apply_manage_receipts(bots)  # Manage: max(chat signals, routine receipts)
            bots = overlay_client_replicas(bots)
            data["bots"] = bots
            data["freshness"] = {
                "stale_after_hours": SOURCE_STALE_AFTER_HOURS,
                "stale_or_missing": [
                    (
                        f"{b.get('name')}(missing_dir)" if b.get("missing_agent_dir")
                        else f"{b.get('name')}(no_source)" if b.get("source_mtime_epoch") is None
                        else f"{b.get('name')}({b.get('source_age_hours')}h)"
                    )
                    for b in bots if b.get("stale")
                ],
            }
            data["bots"] = bots
            data["fleet_assistant_tool_total"] = sum(b["messages"]["assistant_tool"] for b in bots)
            data["fleet_messages_total"] = sum(b["messages"]["total"] for b in bots)
            return _mark_stale(data, data)
        except Exception as e:
            return {
                "ok": False,
                "source": "grok_box_activity.json",
                "error": safe_error(e),
                "stale": True,
                "stale_reason": f"grok_box_activity.json unreadable ({safe_error(e)})",
                "bots": [_empty_bot(n) for n in GROK_ORDER],
                "fleet_messages_total": 0,
                "fleet_assistant_tool_total": 0,
                "note": GROK_NOTE,
                "links": dict(GROK_LINKS),
            }
    bots = _apply_manage_bot_client_counts([_empty_bot(n) for n in GROK_ORDER])
    return _mark_stale(
        {
            "ok": True,
            "source": "static roster + client replica (no box activity cache)",
            "note": GROK_NOTE + " Open Usage & Billing for included/on-demand spend.",
            "bots": bots,
            "fleet_messages_total": sum(b["messages"]["total"] for b in bots),
            "fleet_assistant_tool_total": sum(b["messages"]["assistant_tool"] for b in bots),
            "links": dict(GROK_LINKS),
        },
        None,
    )


# ── HTML ────────────────────────────────────────────────────────────────────


def esc(s: object) -> str:
    return (
        str(s)
        .replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
        .replace('"', "&quot;")
    )


def progress_bar(pct: float | None, tone: str, label: str | None = None) -> str:
    width = 0 if pct is None else max(0, min(100, float(pct)))
    if label is not None:
        shown = label
    else:
        shown = "—" if pct is None else f"{pct:g}%"
    return f"""
    <div class="bar-row">
      <div class="bar-track"><div class="bar-fill {tone}" style="width:{width}%"></div></div>
      <div class="bar-pct {tone}">{esc(shown)}</div>
    </div>"""


PACE_TITLE = (
    "Share of the rolling window used (the published %) vs share of the window's time elapsed at this "
    "reading; × = used ÷ elapsed. Not dollars or tokens. Report only: nothing is held or throttled."
)


def _num(x: float, nd: int) -> str:
    return f"{x:.{nd}f}".rstrip("0").rstrip(".")


def _pace_decimals(p: dict) -> int:
    """Fewest decimals (1–4) at which the shown used % and pts ahead sit on the same side of
    their lines as the unrounded values, so a line never reads '15 pts ahead' yet marked."""
    for nd in (1, 2, 3, 4):
        if all(
            (float(_num(v, nd)) > line) == (v > line)
            for v, line in ((p["used_pct"], PACE_USED_MARK_PCT), (p["ahead_points"], PACE_AHEAD_POINTS))
        ):
            return nd
    return 4


def pacing_html(p: dict | None) -> str:
    """One report-only line under a quota bar: used % vs elapsed % of its window."""
    if not p or p.get("status") != "ok":
        return f'<div class="metric-pace na">pacing: n/a ({esc((p or {}).get("reason") or "no window time")})</div>'
    nd = _pace_decimals(p)
    used, elapsed, ahead = (_num(p[k], nd) for k in ("used_pct", "elapsed_pct", "ahead_points"))
    delta = (
        "on the clock" if float(ahead) == 0
        else f"{ahead.lstrip('-')} pts behind" if ahead.startswith("-") else f"{ahead} pts ahead"
    )
    # the ratio only reads sensibly once some of the window has visibly elapsed
    ratio = f" ({_num(p['ratio'], 2)}× the clock)" if p.get("ratio") is not None and float(elapsed) > 0 else ""
    text = f"pacing: {used}% used vs {elapsed}% of window elapsed{ratio} · {delta}"
    if p.get("marked"):
        why = "; ".join(p.get("mark_reasons") or [])
        return f'<div class="metric-pace marked" title="{esc(PACE_TITLE)}">⚑ {esc(text)} · marked: {esc(why)}</div>'
    return f'<div class="metric-pace" title="{esc(PACE_TITLE)}">{esc(text)}</div>'


def pacing_flag_html(*bar_lists) -> str:
    """Card-level mark naming each window whose pacing is marked; '' when none is."""
    marked = [
        b for bars in bar_lists for b in bars or []
        if isinstance(b, dict) and (b.get("pacing") or {}).get("marked")
    ]
    if not marked:
        return ""
    items = "; ".join(
        f"{esc(b.get('label') or b.get('limit_name') or 'window')} — {esc(', '.join(b['pacing'].get('mark_reasons') or []))}"
        for b in marked
    )
    return f'<p class="pace-flag" role="status">⚑ <strong>Pacing mark</strong> (report only): {items}</p>'



def _fmt_last_activity(b: dict) -> str:
    """Render last-activity cell; show visible stale-source badge when flagged."""
    when = esc(b.get("last_transcript_activity_pt") or "—")
    if b.get("stale"):
        reason = esc(b.get("stale_reason") or "source older than 24h while peers are fresh")
        return (
            f'<span class="status-chip warn" title="{reason}">stale source</span> '
            f'<span class="muted">{when}</span>'
        )
    return when


def _render_jev_calls(bots: list[dict]) -> str:
    """Jev router call counts from jev-route logs (Jev is on-demand, not chat)."""
    for b in bots:
        c = b.get("jev_calls")
        if not isinstance(c, dict):
            continue
        gates = " · ".join(
            f"{esc(g)} <strong>{esc(n)}</strong>" for g, n in (c.get("by_gate") or {}).items()
        ) or "—"
        newest = esc(c.get("newest_log_pt") or "—")
        return f"""
      <div class="metric" id="jev-calls">
        <div class="metric-label">Jev router calls <span class="muted">(source: {esc(c.get('source') or 'jev-route logs')})</span></div>
        <p class="pill">Total <strong>{esc(c.get('total', 0))}</strong> · last 24h <strong>{esc(c.get('last_24h', 0))}</strong> · last 7d <strong>{esc(c.get('last_7d', 0))}</strong> · newest call <strong>{newest}</strong></p>
        <p class="muted">By gate: {gates}</p>
      </div>"""
    return ""


def render_grok_body(grok: dict) -> str:
    """Grok section body — STALE banner first when the box activity cache is old/unknown."""
    bots = grok.get("bots") or []
    fleet = grok.get("fleet_messages_total") or 0
    # stacked share bar
    segments = []
    legend = []
    for i, b in enumerate(bots):
        pct = float(b.get("share_assistant_tool_pct") or 0)
        if i < len(GROK_COLORS):
            color = GROK_COLORS[i]
        else:
            # Spread additional bots around the hue wheel instead of reusing roster colours.
            hue = ((i - len(GROK_COLORS)) * 0.61803398875) % 1
            rgb = colorsys.hls_to_rgb(hue, 0.42, 0.65)
            color = "#" + "".join(f"{round(c * 255):02x}" for c in rgb)
        if pct > 0:
            segments.append(
                f'<div class="stack-seg" style="width:{pct}%;background:{color}" title="{esc(b.get("name"))}: {pct}%"></div>'
            )
        legend.append(
            f'<span class="stack-leg"><i style="background:{color}"></i>{esc(b.get("name"))} {pct:g}%</span>'
        )
    stack = "".join(segments) or '<div class="stack-seg empty" style="width:100%"></div>'
    rows = []
    for b in bots:
        msg = b.get("messages") or {}
        rows.append(
            f"""
        <tr>
          <td><strong>{esc(b.get('name'))}</strong><div class="muted">{esc(b.get('role') or '')}</div></td>
          <td class="num">{esc(msg.get('user', 0))} / {esc(msg.get('assistant', 0))} / {esc(msg.get('tool', 0))}</td>
          <td class="num">{esc(b.get('transcript_mb', 0))} MB</td>
          <td class="num">{esc(b.get('automation_runs', 0))}</td>
          <td>{_fmt_last_activity(b)}</td>
          <td class="num">{esc(b.get('share_assistant_tool_pct', 0))}%</td>
        </tr>"""
        )
    links = grok.get("links") or {}
    ub = links.get("usage_billing") or "grokbot://app/v1/settings?id=plan"
    od = links.get("on_demand") or "grokbot://app/v1/settings?id=on-demand"
    collected = grok.get("collected_at_pt") or grok.get("collected_at_utc")
    collected_pill = f" · box activity collected <strong>{esc(collected)}</strong>" if collected else ""
    stale_banner = ""
    if grok.get("stale"):
        when = f"collected {collected}" if collected else "no collected_at timestamp"
        stale_banner = (
            '<p class="stale-banner" role="status"><span class="status-chip warn">STALE</span> '
            f"Grok box activity cache is older than {STALE_AFTER_HOURS}h or of unknown age ({esc(when)}). "
            "Last-activity dates below are <strong>not current</strong>; CLI bars may still be fresh."
            f'<span class="muted"> Reason: {esc(grok.get("stale_reason") or "unknown")}.</span></p>'
        )
    grok_body = f"""
      {stale_banner}
      <p class="pill">Fleet messages <strong>{esc(fleet)}</strong> · share = assistant+tool{collected_pill}</p>
      <div class="metric">
        <div class="metric-label">Share of assistant+tool messages</div>
        <div class="stack-track">{stack}</div>
        <div class="stack-legend">{''.join(legend)}</div>
      </div>
      <div class="table-wrap">
        <table class="bots">
          <thead>
            <tr>
              <th>Bot</th>
              <th>Messages (u/a/t)</th>
              <th>Transcript</th>
              <th>Auto runs</th>
              <th>Last activity (PT)</th>
              <th>Share</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rows)}
          </tbody>
        </table>
      </div>
      {_render_jev_calls(bots)}
      <p class="link-pills">
        <a class="link-pill" href="{esc(ub)}">Usage &amp; Billing</a>
        <a class="link-pill" href="{esc(od)}">On-demand</a>
      </p>
      <p class="muted">Activity share from local Grok Bot transcripts — not Cursor plan dollars. Open Usage &amp; Billing for included/on-demand spend.</p>
    """
    return grok_body


def _fmt_int(n) -> str:
    return f"{n:,}" if isinstance(n, int) and not isinstance(n, bool) else "—"


def _fmt_usd(v) -> str:
    if not isinstance(v, (int, float)) or isinstance(v, bool):
        return "—"
    return f"${v:,.2f}" if v == 0 or v >= 1 else f"${v:.4f}"


def _qwen_cost_cell(w: dict) -> str:
    if w.get("est_cost_usd") is None:
        return "tokens only" if w.get("unpriced_models") else "—"
    return _fmt_usd(w["est_cost_usd"]) + (" + unpriced" if w.get("unpriced_models") else "")


def render_qwen_body(qwen: dict) -> str:
    """Qwen Code card — install/auth chip, data-quality banner, trial runs, and the usage table
    (24h / 7d / all time), "no runs yet" or "usage unavailable"."""
    usage = qwen.get("usage")
    trial = qwen.get("trial") or {}
    tone = "ok" if qwen.get("ok") else "bad"
    chip = "AUTH OK" if qwen.get("ok") else "AUTH / INSTALL"
    err = f'<p class="err">{esc(qwen.get("error"))}</p>' if qwen.get("error") else ""

    first, last = _qwen_trial_days()
    setup_n = trial.get("setup_test_sessions") or 0
    setup = ""
    if setup_n:
        setup = (
            f'<div class="metric-reset">{esc(setup_n)} setup test session{"" if setup_n == 1 else "s"} '
            f"before {first} (not trial runs)</div>"
        )
    ended = trial.get("phase") == "ended"
    trial_tone = "ok" if (trial.get("runs") or 0) >= QWEN_TRIAL_RUNS else "warn" if ended else "unk"
    trial_html = f"""
      <div class="metric">
        <div class="metric-label">Trial seat · nightly audits {first} to {last}</div>
        <div class="status-chip {trial_tone}">TRIAL {'ENDED ' if ended else ''}{esc(trial.get('runs_display') or '—')}</div>
        <div class="metric-reset">{esc(trial.get('status') or 'trial status unavailable')}</div>
        {setup}
      </div>"""

    quality = ""
    excluded = _qwen_excluded(usage.get("bad_lines") or 0, usage.get("future_records") or 0) if isinstance(usage, dict) else ""
    if excluded:  # shown in every state: skipped records may hide usage or trial runs
        quality = (
            '<p class="stale-banner" role="status"><span class="status-chip warn">DATA</span> '
            f"Not counted from usage_record.jsonl: {esc(excluded)} (future-dated = timestamp after this refresh). "
            "Totals may be incomplete.</p>"
        )
    if not isinstance(usage, dict):
        usage_html = '<p class="muted">Usage unavailable (see error above).</p>'
    elif usage.get("state") == "unreadable" or (not usage.get("sessions") and excluded):
        usage_html = '<div class="metric"><div class="metric-label">Usage</div><p class="pill">usage unavailable: no readable records</p></div>'
    elif not usage.get("sessions"):
        usage_html = '<div class="metric"><div class="metric-label">Usage</div><p class="pill">no runs yet</p></div>'
    else:
        wins = usage.get("windows") or {}
        cols = [wins.get(k) or {} for k in ("last_24h", "last_7d", "all_time")]
        rows = []
        for label, cell in (
            ("Sessions", lambda w: _fmt_int(w.get("sessions"))),
            ("Requests", lambda w: _fmt_int(w.get("requests"))),
            ("Input tokens", lambda w: _fmt_int(w.get("input_tokens"))),
            ("Cached input", lambda w: _fmt_int(w.get("cached_tokens"))),
            ("Output tokens", lambda w: _fmt_int(w.get("output_tokens"))),
            ("Est. cost*", _qwen_cost_cell),
        ):
            tds = "".join(f'<td class="num">{esc(cell(w))}</td>' for w in cols)
            rows.append(f"<tr><td>{esc(label)}</td>{tds}</tr>")
        models = usage.get("models") or []
        per_model = ""
        if len(models) > 1 or any(not m.get("priced") for m in models):
            items = " · ".join(
                f"{esc(m.get('model'))} {esc(_fmt_int(m.get('input_tokens')))} in / "
                f"{esc(_fmt_int(m.get('output_tokens')))} out, {esc(_qwen_cost_cell(m))}"
                for m in models
            )
            per_model = f'<p class="muted">All time by model: {items}</p>'
        usage_html = f"""
      <div class="table-wrap">
        <table class="bots">
          <thead><tr><th>Usage</th><th>24h</th><th>7d</th><th>All time</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <div class="metric-reset">Last session {esc(usage.get('last_session_pt') or '—')}</div>
      {per_model}"""

    return f"""
      <p class="pill">CLI <strong>{esc(qwen.get('cli_version') or '—')}</strong> · provider <strong>{esc(qwen.get('provider') or '—')}</strong> · model <strong>{esc(qwen.get('model') or '—')}</strong></p>
      <div class="metric">
        <div class="metric-label">Qwen Code status</div>
        <div class="status-chip {tone}">{esc(chip)}</div>
        <div class="metric-reset">auth {esc(qwen.get('auth_mechanism') or '—')} · OpenRouter PAYG (no plan bars)</div>
      </div>
      {err}
      {quality}
      {trial_html}
      {usage_html}
      <p class="muted">{esc(qwen.get('note') or QWEN_NOTE)}.</p>
      <p class="muted">* Est. cost is estimated, list price: $2/M uncached input, $0.25/M cached input, $6/M output for qwen/qwen3.8-max-0902; other models show tokens only. Source: <code>~/.qwen/usage_record.jsonl</code>, one line per finished session.</p>
    """


def _small_seat_html(card: dict) -> str:
    """The "default small" seat label on the OpenCode and DSH cards ('' for any other card)."""
    if card.get("seat") != SMALL_SEAT:
        return ""
    return f"""
      <div class="metric">
        <div class="metric-label">Default small seat · {esc(card.get('seat_role') or '—')}</div>
        <div class="status-chip unk">DEFAULT SMALL</div>
        <div class="metric-reset">{esc(SMALL_TRIAL)} · advisory only</div>
      </div>"""


def render_opencode_body(oc: dict) -> str:
    """OpenCode · GLM-5.3 card — install/auth chip, default-small seat label, data-quality banner and the
    usage table (24h / 7d / all time), "no requests yet" or "usage unavailable"."""
    usage = oc.get("usage") if isinstance(oc.get("usage"), dict) else {}
    state = usage.get("state")
    tone = "ok" if oc.get("ok") else "bad"
    chip = "AUTH OK" if oc.get("ok") else "AUTH / INSTALL"
    err = f'<p class="err">{esc(oc.get("error"))}</p>' if oc.get("error") else ""

    quality = ""
    excluded = _opencode_excluded(usage.get("bad_rows") or 0, usage.get("future_records") or 0)
    if excluded:  # shown in every state: skipped rows may hide usage
        quality = (
            '<p class="stale-banner" role="status"><span class="status-chip warn">DATA</span> '
            f"Not counted from opencode.db: {esc(excluded)} (future-dated = time after this refresh). "
            "Totals may be incomplete.</p>"
        )

    totals = list((usage.get("windows") or {}).values()) + (usage.get("models") or [])
    if any(w.get("cost_overflow") for w in totals):
        quality += ('<p class="stale-banner" role="status"><span class="status-chip warn">DATA</span> '
                    'Cost unavailable: aggregate overflow; request and token counts remain available.</p>')

    def usage_pill(text: str) -> str:
        return f'<div class="metric"><div class="metric-label">Usage</div><p class="pill">{esc(text)}</p></div>'

    if state == "missing":
        usage_html = usage_pill("usage unavailable: opencode.db not found")
    elif state == "no_requests":
        usage_html = usage_pill("no requests yet")
    elif state != "ok":
        usage_html = usage_pill("usage unavailable: no readable rows" if excluded else "usage unavailable (see error above)")
    else:
        wins = usage.get("windows") or {}
        cols = [wins.get(k) or {} for k in ("last_24h", "last_7d", "all_time")]
        rows = []
        for label, key in (("Sessions", "sessions"), ("Requests", "requests"), ("Input tokens", "input_tokens"),
                           ("Cached input", "cached_tokens"), ("Output tokens", "output_tokens"),
                           ("Reasoning tokens", "reasoning_tokens")):
            tds = "".join(f'<td class="num">{esc(_fmt_int(w.get(key)))}</td>' for w in cols)
            rows.append(f"<tr><td>{esc(label)}</td>{tds}</tr>")
        tds = "".join(f'<td class="num">{esc(_fmt_usd(w.get("cost_usd")))}</td>' for w in cols)
        rows.append(f"<tr><td>Cost*</td>{tds}</tr>")
        models = usage.get("models") or []
        per_model = ""
        if len(models) > 1:
            items = " · ".join(
                f"{esc(m.get('model'))} {esc(_fmt_int(m.get('input_tokens')))} in / "
                f"{esc(_fmt_int(m.get('output_tokens')))} out, {esc(_fmt_usd(m.get('cost_usd')))}"
                for m in models
            )
            per_model = f'<p class="muted">All time by model: {items}</p>'
        usage_html = f"""
      <div class="table-wrap">
        <table class="bots">
          <thead><tr><th>Usage</th><th>24h</th><th>7d</th><th>All time</th></tr></thead>
          <tbody>{''.join(rows)}</tbody>
        </table>
      </div>
      <div class="metric-reset">Last run {esc(usage.get('last_run_pt') or '—')}</div>
      {per_model}"""

    return f"""
      <p class="pill">CLI <strong>{esc(oc.get('cli_version') or '—')}</strong> · provider <strong>{esc(oc.get('provider') or '—')}</strong> · model <strong>{esc(oc.get('model') or '—')}</strong> · effort <strong>{esc(oc.get('effort') or '—')}</strong></p>
      <div class="metric">
        <div class="metric-label">OpenCode status</div>
        <div class="status-chip {tone}">{esc(chip)}</div>
        <div class="metric-reset">auth {esc(oc.get('auth_mechanism') or '—')} · OpenRouter PAYG (no plan bars)</div>
      </div>
      {err}
      {_small_seat_html(oc)}
      {quality}
      {usage_html}
      <p class="muted">* Cost is what OpenCode recorded for each request; it is not an OpenRouter invoice. OpenRouter list price for z-ai/glm-5.3 on 10/24: $0.079/M input, $1.40/M output. Input tokens include cached input; reasoning tokens are counted apart from output. Source: opencode.db, read-only; inherited fork history is counted once using original execution metadata.</p>
    """


OPENROUTER_POINTER = (
    '<p class="muted">OpenRouter spend: DSH and Qwen Code use one key, so their spend is shown combined on the '
    "OpenRouter spend card.</p>"
)


def render_openrouter_body(orr: dict) -> str:
    """Shared-key OpenRouter spend card: one row per window, "unavailable" unless the fetch succeeded."""
    ok = bool(orr.get("ok"))
    spend = orr.get("spend_usd") or {}
    windows = orr.get("windows") or {}
    labels = (("today_utc", "Day (UTC)"), ("week_utc", "Week from Monday (UTC)"), ("month_utc", "Month (UTC)"),
              ("all_time", "All time"))
    rows = "".join(
        f'<tr><td>{esc(windows.get(name) or label)}</td><td class="num">'
        f'{esc(_fmt_usd(spend.get(name)) if ok and spend.get(name) is not None else "unavailable")}</td></tr>'
        for name, label in labels
    )
    err = "" if ok else f'<p class="err">Spend unavailable: {esc(orr.get("error") or "not collected")}</p>'
    limit = ""
    if ok and orr.get("limit_usd") is not None:
        reset = f" · resets {esc(orr['limit_reset'])}" if orr.get("limit_reset") else ""
        limit = (f'<div class="metric-reset">Key limit {esc(_fmt_usd(orr["limit_usd"]))} · remaining '
                 f'{esc(_fmt_usd(orr.get("limit_remaining_usd")))}{reset}</div>')
    fetched = f" Fetched {esc(orr['fetched_at'])}." if ok and orr.get("fetched_at") else ""
    return f"""
      <p class="pill"><strong>DSH + Qwen Code combined</strong> · one shared key · not split per seat</p>
      {err}
      <div class="table-wrap">
        <table class="bots">
          <thead><tr><th>Window</th><th>Spend (USD)</th></tr></thead>
          <tbody>{rows}</tbody>
        </table>
      </div>
      {limit}
      <p class="muted">From OpenRouter's own usage counters for the key in <code>~/.dsh/.env</code> (USD: OpenRouter credits are US dollars).{fetched} Both seats send requests with this key and DSH keeps no per-request ids, so its share cannot be split out: this is their combined spend. The Qwen card's est. cost is a separate list-price estimate from its local usage log.</p>
    """


def render_html(snap: dict) -> str:
    refreshed = snap["refreshed_at"]
    claude = snap["claude"]
    codex = snap["codex"]
    kimi = snap["kimi"]
    agy = snap["agy"]
    muse = snap.get("muse") or {}
    dsh = snap.get("dsh") or {}
    qwen = snap.get("qwen") or {}
    opencode = snap.get("opencode") or {}
    openrouter = snap.get("openrouter") or {}
    routine_proxy = snap.get("routine_proxy") or {}
    grok = snap["grok"]

    def bars_html(bars):
        parts = []
        for b in bars:
            parts.append(
                f"""
        <div class="metric">
          <div class="metric-label">{esc(b.get('label'))}</div>
          {progress_bar(b.get('used_percent'), b.get('tone') or bar_class(b.get('used_percent')))}
          <div class="metric-reset">Resets {esc(b.get('reset') or '—')}</div>
          {pacing_html(b.get('pacing'))}
        </div>"""
            )
        return "\n".join(parts) if parts else '<p class="muted">No bar data.</p>\n' + pacing_html(None)

    claude_body = bars_html(claude.get("bars") or [])
    if not claude.get("ok"):
        claude_body = f'<p class="err">Claude collect failed: {esc(claude.get("error") or "unknown")}</p>' + claude_body

    if codex.get("ok"):
        astra = codex.get("gpt6_astra") or {}
        av = "available" if astra.get("available") else "unavailable"
        credits = codex.get("credits") or {}
        addl = ""
        for a in codex.get("additional_rate_limits") or []:
            addl += f"""
        <div class="metric">
          <div class="metric-label">{esc(a.get('label') or a.get('limit_name'))}</div>
          {progress_bar(a.get('used_percent'), a.get('tone') or 'ok')}
          <div class="metric-reset">Resets {esc(a.get('reset') or '—')}</div>
          {pacing_html(a.get('pacing'))}
        </div>"""
        codex_body = f"""
        <p class="pill">plan: <strong>{esc(codex.get('plan_type'))}</strong> · gpt-6-astra: <strong>{esc(av)}</strong></p>
        {bars_html(codex.get('bars') or [])}
        {addl}
        <p class="muted">Credits: has={esc(credits.get('has_credits'))} balance={esc(credits.get('balance'))} unlimited={esc(credits.get('unlimited'))}</p>
        """
    else:
        codex_body = f'<p class="err">Codex collect failed: {esc(codex.get("error") or "unknown")}</p>'

    # Kimi — Claude-like bars, no vault path wall
    tone = kimi.get("tone") or "unk"
    chip = kimi.get("chip") or kimi.get("status") or "unknown"
    kimi_bars = bars_html(kimi.get("bars") or [])
    kimi_extra = ""
    if kimi.get("last_checked"):
        kimi_extra += f'<div class="metric-reset">Last checked {esc(kimi.get("last_checked"))}</div>'
    kimi_body = f"""
      <p class="pill">model <strong>{esc(kimi.get('default_model') or '—')}</strong> · effort <strong>{esc(kimi.get('effort') or '—')}</strong></p>
      <div class="status-chip {tone}">{esc(chip)}</div>
      <p class="kimi-detail">{esc(kimi.get('detail') or '')}</p>
      {kimi_bars}
      {kimi_extra}
      <p class="muted">Bars from live <code>/usages</code> API (used % = 100 − remaining). Vault markers are fallback only. Model + effort from <code>~/.kimi-code/config.toml</code>.</p>
    """

    # Agy
    ssp = agy.get("social_superpowers") or {}
    health = agy.get("collect_health") or {}
    ssp_tone = ssp.get("tone") or "unk"
    health_tone = health.get("tone") or "unk"
    reached = ""
    if ssp.get("reached_at"):
        reached = f'<div class="metric-reset">Reached {esc(ssp.get("reached_at"))}</div>'
    agy_cli_bars = bars_html(agy.get("bars") or [])
    if agy.get("usage_error") and not (agy.get("bars") or []):
        agy_cli_bars = f'<p class="err">agy -p /usage failed: {esc(agy.get("usage_error"))}</p>' + agy_cli_bars
    agy_body = f"""
      <p class="pill">CLI <strong>{esc(agy.get('cli_version') or '—')}</strong> · <code>agy -p /usage</code></p>
      {agy_cli_bars}
      <div class="metric">
        <div class="metric-label">social-superpowers MCP daily</div>
        {progress_bar(ssp.get('used_percent'), ssp_tone, label=ssp.get('label'))}
        <div class="metric-reset">Daily limit {esc(ssp.get('daily_limit', 120))} · resets {esc(ssp.get('reset_note') or '17:00 PT (midnight UTC)')}</div>
        {reached}
      </div>
      <div class="metric">
        <div class="metric-label">Hourly collect health</div>
        <div class="status-chip {health_tone}">{esc(health.get('chip') or 'UNKNOWN')}</div>
        <div class="mono">{esc(health.get('pack_name') or '—')}</div>
        <div class="metric-reset">{esc(health.get('mtime_short') or '—')} · {esc(health.get('status_short') or '—')}</div>
      </div>
      <p class="muted">CLI bars show used % (100 − remaining from /usage). MCP daily is separate from Gemini quota.</p>
    """


    # Muse / Muse Spark
    muse_tone = "ok" if muse.get("ok") else "bad"
    mu = muse.get("usage") or {}
    mu_plan = mu.get("plan")
    muse_chip = str(mu_plan).upper() if mu_plan else ("AUTH OK" if muse.get("ok") else "AUTH / INSTALL")
    muse_bars = bars_html(muse.get("bars") or [])
    muse_err = ""
    if muse.get("error"):
        muse_err = f'<p class="err">{esc(muse.get("error"))}</p>'
    mu_usage_err = ""
    if mu.get("usage_error") or muse.get("usage_error"):
        mu_usage_err = f'<p class="err">Usage scan: {esc(mu.get("usage_error") or muse.get("usage_error"))}</p>'
    mu_usage_note = ""
    if mu.get("usage_note"):
        mu_usage_note = f'<p class="err">Usage incomplete: {esc(mu.get("usage_note"))}</p>'
    mu_prompts_note = ""
    if mu.get("prompts_note"):
        mu_prompts_note = f'<p class="muted">{esc(mu.get("prompts_note"))}</p>'
    mu_rows = []
    for d in mu.get("days") or []:
        day_models = ", ".join(f"{m} {t:,}" for m, t in (d.get("models") or {}).items()) or "—"
        mu_rows.append(
            f"""
        <tr>
          <td class="mono">{esc(d.get('date') or '—')}</td>
          <td class="num">{esc(d.get('sessions', 0))}</td>
          <td class="num">{esc(d.get('prompts', 0))}</td>
          <td class="num">{d.get('input_tokens', 0):,}</td>
          <td class="num">{d.get('output_tokens', 0):,}</td>
          <td class="num">{d.get('cached_tokens', 0):,}</td>
          <td class="num">{d.get('reasoning_tokens', 0):,}</td>
          <td class="mono">{esc(day_models)}</td>
        </tr>"""
        )
    mu_table = ""
    if mu_rows:
        mu_table = f"""
      <div class="table-wrap">
        <table class="bots">
          <thead>
            <tr>
              <th>Day (PT)</th>
              <th>Sess</th>
              <th>Prompts</th>
              <th>In tok</th>
              <th>Out tok</th>
              <th>Cached tok</th>
              <th>Reas tok</th>
              <th>Models (in+out)</th>
            </tr>
          </thead>
          <tbody>
            {''.join(mu_rows)}
          </tbody>
        </table>
      </div>"""
    mu_summary = ""
    if mu:
        mu_tot = mu.get("totals") or {}
        mu_today = mu.get("today") or {}
        mu_partial = ' <span class="status-chip warn">PARTIAL</span>' if mu.get("partial") or mu.get("usage_error") else ""
        mu_bymodel = " · ".join(
            f"{esc(m)} <strong>{t:,}</strong>" for m, t in (mu.get("by_model") or {}).items()
        )
        mu_summary = f"""
      <p class="pill">7d tokens <strong>{mu_tot.get('input_tokens', 0):,}</strong> in / <strong>{mu_tot.get('output_tokens', 0):,}</strong> out · today <strong>{mu_today.get('input_tokens', 0):,}</strong> / <strong>{mu_today.get('output_tokens', 0):,}</strong>{mu_partial}</p>
      <p class="muted">By model (7d, in+out): {mu_bymodel or '—'}</p>"""
    muse_body = f"""
      <p class="pill">CLI <strong>{esc(muse.get('cli_version') or '—')}</strong> · plan <strong>{esc(mu_plan or '—')}</strong> · model <strong>{esc(muse.get('model') or 'muse-spark-1.3-contributor')}</strong></p>
      <div class="metric">
        <div class="metric-label">Muse Spark status</div>
        <div class="status-chip {muse_tone}">{esc(muse_chip)}</div>
        <div class="metric-reset">auth {esc(muse.get('auth_mechanism') or '—')} · limit/reset {esc(mu.get('limit_note') or 'not exposed by Muse CLI')}</div>
      </div>
      {muse_err}
      {mu_usage_err}
      {mu_usage_note}
      {mu_summary}
      {mu_table}
      {mu_prompts_note}
      {muse_bars}
      <p class="muted">{esc(muse.get('detail') or 'Muse Code powered by Muse Spark.')}</p>
    """

    # DSH / DeepSeek Harness
    dsh_tone = "ok" if dsh.get("ok") else "bad"
    dsh_chip = "AUTH OK" if dsh.get("ok") else "AUTH / INSTALL"
    dsh_bars = bars_html(dsh.get("bars") or [])
    dsh_err = ""
    if dsh.get("error"):
        dsh_err = f'<p class="err">{esc(dsh.get("error"))}</p>'
    dsh_body = f"""
      <p class="pill">CLI <strong>{esc(dsh.get('cli_version') or '—')}</strong> · provider <strong>{esc(dsh.get('provider') or '—')}</strong> · model <strong>{esc(dsh.get('model') or '—')}</strong></p>
      <div class="metric">
        <div class="metric-label">DSH status</div>
        <div class="status-chip {dsh_tone}">{esc(dsh_chip)}</div>
        <div class="metric-reset">auth {esc(dsh.get('auth_mechanism') or '—')} · OpenRouter credits (no plan bars)</div>
      </div>
      {_small_seat_html(dsh)}
      {dsh_err}
      {dsh_bars}
      <p class="muted">{esc(dsh.get('detail') or 'DeepSeek Harness via OpenRouter.')}</p>
      {OPENROUTER_POINTER}
    """

    opencode_body = render_opencode_body(opencode)
    # Report-only pacing mark per Mac CLI card (Codex only when its bars are shown)
    flags = {
        "claude": pacing_flag_html(claude.get("bars")),
        "codex": pacing_flag_html(codex.get("bars"), codex.get("additional_rate_limits")) if codex.get("ok") else "",
        "kimi": pacing_flag_html(kimi.get("bars")),
        "agy": pacing_flag_html(agy.get("bars")),
        "muse": pacing_flag_html(muse.get("bars")),
        "dsh": pacing_flag_html(dsh.get("bars")),
    }
    card_cls = {k: "card pace-marked" if v else "card" for k, v in flags.items()}

    qwen_body = render_qwen_body(qwen) + OPENROUTER_POINTER
    openrouter_body = render_openrouter_body(openrouter)

    grok_body = render_grok_body(grok)

    # Routine fire proxy (NOT $)
    rp_rows = []
    for r in routine_proxy.get("rows") or []:
        fpw = r.get("fires_per_week")
        fpw_s = "—" if fpw is None else esc(fpw)
        rp_rows.append(
            f"""
        <tr>
          <td>{esc(r.get('owner') or '—')}</td>
          <td><strong>{esc(r.get('name') or '—')}</strong><div class="muted">{esc(r.get('notes') or '')}</div></td>
          <td class="mono">{esc(r.get('cron') or '')}</td>
          <td class="num">{fpw_s}</td>
        </tr>"""
        )
    rp_total = routine_proxy.get("total_fires_per_week") or 0
    routine_proxy_body = f"""
      <p class="pill"><strong>PROXY</strong> · estimated fires/week <strong>{esc(rp_total)}</strong> · not dollars · not tokens</p>
      <div class="table-wrap">
        <table class="bots">
          <thead>
            <tr>
              <th>Owner</th>
              <th>Routine</th>
              <th>Cron (PT)</th>
              <th>Fires/wk ≈</th>
            </tr>
          </thead>
          <tbody>
            {''.join(rp_rows) or '<tr><td colspan="4">No routine dump yet</td></tr>'}
          </tbody>
        </table>
      </div>
      <p class="muted">{esc(routine_proxy.get('detail') or '')} Source: {esc(routine_proxy.get('source') or '—')}.</p>
    """

    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <meta name="description" content="At-a-glance Mac CLI + Grok agent model usage quotas for Haiyuan Cao.">
  <meta name="theme-color" content="#101828">
  <title>Agent Model Usage — Field Brief</title>
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Fraunces:opsz,wght@9..144,500;9..144,600;9..144,700&family=IBM+Plex+Mono:wght@500;600&family=IBM+Plex+Sans:wght@400;500;600;700&display=swap" rel="stylesheet">
  <style>
    :root {{
      --navy: #101828;
      --navy-2: #17233a;
      --paper: #f4efe6;
      --paper-2: #ebe4d8;
      --cream: #fbf7f0;
      --ink: #161410;
      --ink-soft: #5c564c;
      --ink-faint: #8a8378;
      --line: #d9d0c3;
      --accent: #e87324;
      --accent-dark: #b7480d;
      --mint: #0f766e;
      --warn: #b45309;
      --bad: #b91c1c;
      --ok: #0f766e;
      --serif: "Fraunces", Iowan Old Style, Charter, Georgia, serif;
      --sans: "IBM Plex Sans", Inter, ui-sans-serif, sans-serif;
      --mono: "IBM Plex Mono", ui-monospace, monospace;
    }}
    * {{ box-sizing: border-box; }}
    body {{
      margin: 0;
      background: var(--paper);
      color: var(--ink);
      font-family: var(--sans);
      font-size: 16px;
      line-height: 1.55;
      -webkit-font-smoothing: antialiased;
    }}
    a {{ color: inherit; text-decoration: none; }}
    .shell {{ width: min(1100px, calc(100% - 40px)); margin: 0 auto; }}
    header.hero {{
      padding: 36px 0 8px;
    }}
    .kicker {{
      font-family: var(--mono);
      font-size: 0.78rem;
      font-weight: 600;
      letter-spacing: 0.06em;
      text-transform: uppercase;
      color: var(--accent-dark);
      margin: 0 0 8px;
    }}
    h1 {{
      font-family: var(--serif);
      font-size: clamp(1.8rem, 3vw, 2.4rem);
      font-weight: 600;
      margin: 0 0 10px;
      letter-spacing: -0.02em;
    }}
    .lede {{
      color: var(--ink-soft);
      max-width: 62ch;
      margin: 0 0 18px;
    }}
    .meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px 18px;
      font-size: 0.9rem;
      color: var(--ink-soft);
      margin-bottom: 28px;
    }}
    .meta strong {{ color: var(--ink); font-weight: 600; }}
    .grid {{
      display: grid;
      grid-template-columns: repeat(auto-fit, minmax(300px, 1fr));
      gap: 18px;
      padding-bottom: 18px;
    }}
    .card {{
      background: var(--cream);
      border: 1px solid var(--line);
      border-radius: 14px;
      padding: 18px 18px 16px;
      box-shadow: 0 1px 0 rgba(16,24,40,0.03);
    }}
    .card.wide {{
      grid-column: 1 / -1;
    }}
    .card h2 {{
      font-family: var(--serif);
      font-size: 1.25rem;
      margin: 0 0 4px;
      font-weight: 600;
    }}
    .card .sub {{
      font-size: 0.82rem;
      color: var(--ink-faint);
      margin: 0 0 14px;
    }}
    .metric {{ margin-bottom: 14px; }}
    .metric-label {{
      font-weight: 600;
      font-size: 0.92rem;
      margin-bottom: 6px;
    }}
    .metric-reset {{
      font-size: 0.82rem;
      color: var(--ink-soft);
      margin-top: 4px;
    }}
    .metric-pace {{
      font-size: 0.8rem;
      color: var(--ink-soft);
      margin-top: 2px;
    }}
    .metric-pace.na {{ color: var(--ink-faint); }}
    .metric-pace.marked {{ color: var(--bad); font-weight: 600; }}
    .card.pace-marked {{ border-color: #fecaca; box-shadow: inset 4px 0 0 var(--bad); }}
    .pace-flag {{
      margin: 0 0 12px;
      padding: 8px 10px;
      border: 1px solid #fecaca;
      border-left: 4px solid var(--bad);
      border-radius: 8px;
      background: #fef2f2;
      color: #991b1b;
      font-size: 0.86rem;
    }}
    .kimi-detail {{ margin: 0 0 10px; font-size: 0.95rem; }}
    .bar-row {{
      display: grid;
      grid-template-columns: 1fr auto;
      gap: 10px;
      align-items: center;
    }}
    .bar-track {{
      height: 10px;
      background: var(--paper-2);
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--line);
    }}
    .bar-fill {{
      height: 100%;
      border-radius: 999px;
      background: var(--ok);
    }}
    .bar-fill.warn {{ background: var(--warn); }}
    .bar-fill.bad {{ background: var(--bad); }}
    .bar-fill.unk {{ background: var(--ink-faint); width: 8% !important; opacity: 0.45; }}
    .bar-pct {{
      font-family: var(--mono);
      font-size: 0.82rem;
      font-weight: 600;
      min-width: 3.2rem;
      text-align: right;
      color: var(--ok);
    }}
    .bar-pct.warn {{ color: var(--warn); }}
    .bar-pct.bad {{ color: var(--bad); }}
    .bar-pct.unk {{ color: var(--ink-faint); }}
    .status-chip {{
      display: inline-block;
      font-family: var(--mono);
      font-size: 0.78rem;
      font-weight: 600;
      padding: 4px 10px;
      border-radius: 999px;
      border: 1px solid var(--line);
      background: var(--paper-2);
      margin-bottom: 8px;
    }}
    .status-chip.ok {{ background: #d1fae5; color: #065f46; border-color: #a7f3d0; }}
    .status-chip.warn {{ background: #ffedd5; color: #9a3412; border-color: #fed7aa; }}
    .status-chip.bad {{ background: #fee2e2; color: #991b1b; border-color: #fecaca; }}
    .stale-banner {{
      margin: 0 0 12px;
      padding: 10px 12px;
      border: 1px solid #fed7aa;
      border-left: 4px solid var(--warn);
      border-radius: 8px;
      background: #fff7ed;
      color: #9a3412;
      font-size: 0.9rem;
    }}
    .stale-banner .status-chip {{ margin-right: 6px; }}
    .status-chip.unk {{ background: var(--paper-2); color: var(--ink-soft); }}
    .pill {{
      display: inline-block;
      font-size: 0.84rem;
      background: var(--paper-2);
      border: 1px solid var(--line);
      border-radius: 999px;
      padding: 4px 10px;
      margin: 0 0 12px;
    }}
    .muted {{ color: var(--ink-faint); font-size: 0.84rem; }}
    .err {{ color: var(--bad); font-size: 0.9rem; }}
    .mono {{ font-family: var(--mono); font-size: 0.82rem; word-break: break-all; }}
    .stack-track {{
      display: flex;
      height: 14px;
      border-radius: 999px;
      overflow: hidden;
      border: 1px solid var(--line);
      background: var(--paper-2);
    }}
    .stack-seg {{ height: 100%; min-width: 0; }}
    .stack-seg.empty {{ background: var(--paper-2); opacity: 0.6; }}
    .stack-legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 8px 14px;
      margin-top: 8px;
      font-size: 0.8rem;
      color: var(--ink-soft);
    }}
    .stack-leg i {{
      display: inline-block;
      width: 10px; height: 10px;
      border-radius: 2px;
      margin-right: 6px;
      vertical-align: middle;
    }}
    .table-wrap {{ overflow-x: auto; margin: 8px 0 12px; }}
    table.bots {{
      width: 100%;
      border-collapse: collapse;
      font-size: 0.88rem;
    }}
    table.bots th, table.bots td {{
      text-align: left;
      padding: 8px 10px;
      border-bottom: 1px solid var(--line);
      vertical-align: top;
    }}
    table.bots th {{
      font-size: 0.75rem;
      text-transform: uppercase;
      letter-spacing: 0.04em;
      color: var(--ink-faint);
      font-weight: 600;
    }}
    table.bots td.num {{ font-family: var(--mono); font-size: 0.82rem; white-space: nowrap; }}
    .link-pills {{ display: flex; flex-wrap: wrap; gap: 8px; margin: 8px 0; }}
    .link-pill {{
      display: inline-block;
      font-size: 0.82rem;
      font-weight: 600;
      padding: 6px 12px;
      border-radius: 999px;
      background: var(--navy);
      color: #f5c39a !important;
      border: 1px solid #2a3a55;
    }}
    .link-pill:hover {{ background: var(--navy-2); }}
    .note {{
      background: var(--navy);
      color: #e8edf4;
      border-radius: 14px;
      padding: 16px 18px;
      margin: 0 0 36px;
    }}
    .note h3 {{
      font-family: var(--serif);
      margin: 0 0 6px;
      font-size: 1.05rem;
    }}
    .note code {{
      font-family: var(--mono);
      font-size: 0.82rem;
      background: rgba(255,255,255,0.08);
      padding: 2px 6px;
      border-radius: 4px;
    }}
    .note a {{ color: #f5c39a; text-decoration: underline; }}
    footer {{
      border-top: 1px solid var(--line);
      padding: 18px 0 32px;
      color: var(--ink-faint);
      font-size: 0.82rem;
    }}
    .legend {{
      display: flex;
      flex-wrap: wrap;
      gap: 12px 18px;
      font-size: 0.82rem;
      color: var(--ink-soft);
      margin: -8px 0 22px;
    }}
    .legend i {{
      display: inline-block;
      width: 10px; height: 10px;
      border-radius: 50%;
      margin-right: 6px;
    }}
    .legend .ok {{ background: var(--ok); }}
    .legend .warn {{ background: var(--warn); }}
    .legend .bad {{ background: var(--bad); }}
  </style>
  <link rel="stylesheet" href="../../assets/site-nav.css" data-site-nav>
  <script defer src="../../assets/site-nav.js" data-site-nav></script>
</head>
<body>
<!-- site-nav:start -->
<div class="site-topbar" data-site-nav>
  <div class="site-topbar-inner">
    <a class="site-brand" href="/research/"><span>HC</span> / FIELD BRIEF</a>
    <button class="site-nav-toggle" type="button" aria-expanded="false" aria-controls="site-nav">Menu</button>
    <nav class="nav-links site-nav" id="site-nav" aria-label="Primary">
      <a href="/research/">Research</a>
      <a href="/research/stories/">BQAA</a>
      <div class="site-nav-folder">
        <button type="button" class="site-nav-folder-button" aria-haspopup="true" aria-expanded="false" aria-controls="site-nav-menu-bigquery">BigQuery</button>
        <div class="site-nav-menu" id="site-nav-menu-bigquery">
          <a href="/research/conversational-analytics/">Conversational Analytics</a>
          <a href="/research/bqml-ai-operators/">BQ ML / AI Ops</a>
          <a href="/research/bigquery-graph/">BQ Graph</a>
          <a href="/research/bigquery-lakehouse/">BQ Lakehouse</a>
          <a href="/research/bigquery-search/">BQ Search</a>
        </div>
      </div>
      <a href="/research/usage/" aria-current="page">Usage</a>
      <a href="/research/harness/">Harness</a>
      <div class="site-nav-folder">
        <button type="button" class="site-nav-folder-button" aria-haspopup="true" aria-expanded="false" aria-controls="site-nav-menu-builds">Builds</button>
        <div class="site-nav-menu" id="site-nav-menu-builds">
          <a href="/rfc/">RFC</a>
          <a href="/rfc/detailed-rfc/">Detailed RFC</a>
          <a href="/evalbench/">EvalBench</a>
        </div>
      </div>
    </nav>
  </div>
</div>
<!-- site-nav:end -->
  <main class="shell">
    <header class="hero">
      <p class="kicker">Mac CLIs · Grok activity</p>
      <h1>Agent model usage</h1>
      <p class="lede">At-a-glance quotas for the Opus 5.5 seat, Codex/Astra, Kimi, Agy, Muse Spark, DSH (default small), OpenCode · GLM-5.3 (default small), Qwen Code (trial), OpenRouter spend (DSH + Qwen combined), Grok activity share, plus a routine fires/week proxy (not dollars).</p>
      <div class="meta">
        <span>Last refreshed <strong>{esc(refreshed)}</strong></span>
        <span>Timezone <strong>America/Los_Angeles</strong></span>
      </div>
      <div class="legend">
        <span><i class="ok"></i>&lt;70% green</span>
        <span><i class="warn"></i>70–89% amber</span>
        <span><i class="bad"></i>≥90% / blocked red</span>
        <span>pacing = published used % vs share of the window elapsed (not dollars or tokens)</span>
        <span>⚑ pacing mark: usage &gt;{PACE_AHEAD_POINTS:g} pts ahead of the window clock or past {PACE_USED_MARK_PCT:g}% used · report only</span>
      </div>
    </header>

    <div class="grid">
      <section class="{card_cls['claude']}" id="claude">
        <h2>Claude / Fable</h2>
        <p class="sub">claude -p /usage</p>
        {flags['claude']}
        {claude_body}
      </section>

      <section class="{card_cls['codex']}" id="codex">
        <h2>Codex / Astra</h2>
        <p class="sub">wham/usage · plan + primary / secondary windows</p>
        {flags['codex']}
        {codex_body}
      </section>

      <section class="{card_cls['kimi']}" id="kimi">
        <h2>Kimi</h2>
        <p class="sub">weekly (7-day) quota · derived status</p>
        {flags['kimi']}
        {kimi_body}
      </section>

      <section class="{card_cls['agy']}" id="agy">
        <h2>Agy</h2>
        <p class="sub">agy -p /usage · pack · social-superpowers MCP</p>
        {flags['agy']}
        {agy_body}
      </section>

      <section class="{card_cls['muse']}" id="muse">
        <h2>Muse / Muse Spark</h2>
        <p class="sub">muse --version · Meta Muse Code · 7d local usage (model_completed)</p>
        {flags['muse']}
        {muse_body}
      </section>

      <section class="{card_cls['dsh']}" id="dsh">
        <h2>DSH / DeepSeek Harness</h2>
        <p class="sub">dsh --version · OpenRouter DeepSeek</p>
        {flags['dsh']}
        {dsh_body}
      </section>

      <section class="card" id="opencode">
        <h2>OpenCode · GLM-5.3</h2>
        <p class="sub">opencode --version · OpenRouter GLM-5.3</p>
        {opencode_body}
      </section>

      <section class="card" id="qwen">
        <h2>Qwen Code</h2>
        <p class="sub">qwen --version · OpenRouter Qwen3.8-Max</p>
        {qwen_body}
      </section>

      <section class="card" id="openrouter">
        <h2>OpenRouter spend</h2>
        <p class="sub">GET /api/v1/key · one key shared by DSH + Qwen Code</p>
        {openrouter_body}
      </section>

      <section class="card wide" id="grok">
        <h2>Overall Grok Bots</h2>
        <p class="sub">activity from local transcripts · not plan dollars</p>
        {grok_body}
      </section>

      <section class="card wide" id="routine-proxy">
        <h2>Routine fire proxy</h2>
        <p class="sub">cron fires/week estimate · NOT billing</p>
        {routine_proxy_body}
      </section>
    </div>

    <aside class="note">
      <h3>How to refresh</h3>
      <p>On the Mac, run <code>usage-dashboard/refresh.sh</code> (full path:
      <code>/Users/haiyuancao/Documents/agent-analytics-research/usage-dashboard/refresh.sh</code>),
      then commit/push the hub — or wait for the routine that does it. Grok activity uses live box data when available, else <code>grok_box_activity.json</code>.</p>
    </aside>
  </main>
  <footer>
    <div class="shell">Public research hub · secrets redacted from snapshot · Haiyuan Cao</div>
  </footer>
</body>
</html>
"""


def main() -> None:
    snap = {
        "refreshed_at": iso_pt(),
        "refreshed_at_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        # pacing is stamped as each seat's reading lands, so elapsed % matches that reading
        "claude": add_pacing(collect_claude()),
        "codex": add_pacing(collect_codex()),
        "kimi": add_pacing(collect_kimi()),
        "agy": add_pacing(collect_agy()),
        "muse": add_pacing(collect_muse()),
        "dsh": add_pacing(collect_dsh()),
        "opencode": collect_opencode(),
        "qwen": collect_qwen(),
        "openrouter": collect_openrouter(),
        "routine_proxy": collect_routine_proxy(),
        "grok": collect_grok(),
    }
    snap = scrub_tree(snap)  # last line of defense; collectors already use safe_error()
    snap = finite_tree(snap)  # NaN / ±inf from any collector or API value -> null, for the JSON and the page

    publish = json.loads(json.dumps(snap, allow_nan=False))
    if "evidence" in publish.get("kimi", {}):
        publish["kimi"]["evidence"] = [
            {"path": Path(e["path"]).name, "mtime": e.get("mtime"), "excerpt": (e.get("excerpt") or "")[:180]}
            for e in publish["kimi"].get("evidence") or []
        ]
    if publish.get("agy", {}).get("pack", {}) and "path" in publish["agy"]["pack"]:
        publish["agy"]["pack"]["path"] = publish["agy"]["pack"]["name"]
    if publish.get("claude", {}).get("raw_excerpt"):
        publish["claude"]["raw_excerpt"] = publish["claude"]["raw_excerpt"][:800]
    if publish.get("agy", {}).get("usage_raw_excerpt"):
        publish["agy"]["usage_raw_excerpt"] = publish["agy"]["usage_raw_excerpt"][:800]

    # Publish structured metrics only; raw CLI diagnostic excerpts can include private text.
    for card in publish.values():
        if isinstance(card, dict):
            for key in ("raw_excerpt", "usage_raw_excerpt"):
                card.pop(key, None)

    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "snapshot.json").write_text(json.dumps(publish, indent=2, allow_nan=False) + "\n")
    html = "\n".join(line.rstrip() for line in render_html(snap).splitlines()) + "\n"
    (HERE / "index.html").write_text(html)
    print(f"Wrote {HERE / 'snapshot.json'}")
    print(f"Wrote {HERE / 'index.html'}")
    print(f"Refreshed at {snap['refreshed_at']}")
    k = snap["kimi"]
    print(f"Kimi: {k.get('status')} chip={k.get('chip')} pct={k.get('used_percent')} model={k.get('default_model')} effort={k.get('effort')}")
    a = snap["agy"]
    print(f"Agy: ssp={ (a.get('social_superpowers') or {}).get('state') } health={ (a.get('collect_health') or {}).get('chip') }")
    m = snap.get("muse") or {}
    mu = m.get("usage") or {}
    mut = mu.get("totals") or {}
    print(
        f"Muse: ok={m.get('ok')} ver={m.get('cli_version')} model={m.get('model')} plan={mu.get('plan')}"
        f" 7d_in={mut.get('input_tokens')} 7d_out={mut.get('output_tokens')} partial={mu.get('partial')}"
    )
    d = snap.get("dsh") or {}
    print(f"DSH: ok={d.get('ok')} ver={d.get('cli_version')} model={d.get('model')} provider={d.get('provider')}")
    o = snap.get("opencode") or {}
    ou = o.get("usage") or {}
    print(
        f"OpenCode: ok={o.get('ok')} ver={o.get('cli_version')} model={o.get('model')} effort={o.get('effort')} "
        f"state={ou.get('state')} requests={ou.get('requests')} "
        f"cost_all={((ou.get('windows') or {}).get('all_time') or {}).get('cost_usd')}"
    )
    q = snap.get("qwen") or {}
    qu = q.get("usage") or {}
    print(
        f"Qwen: ok={q.get('ok')} ver={q.get('cli_version')} model={q.get('model')} state={qu.get('state')} sessions={qu.get('sessions')} "
        f"cost_all={((qu.get('windows') or {}).get('all_time') or {}).get('est_cost_usd')} trial={(q.get('trial') or {}).get('status')}"
    )
    o = snap.get("openrouter") or {}
    osp = o.get("spend_usd") or {}
    print(
        f"OpenRouter: ok={o.get('ok')} (DSH + Qwen combined) today={osp.get('today_utc')} week={osp.get('week_utc')} "
        f"month={osp.get('month_utc')} all_time={osp.get('all_time')} error={o.get('error')}"
    )
    g = snap["grok"]
    print(f"Grok: bots={len(g.get('bots') or [])} fleet={g.get('fleet_messages_total')} source={g.get('source')} stale={g.get('stale')}")
    rp = snap.get("routine_proxy") or {}
    print(
        "RoutineProxy: rows=%s fires_per_week≈%s source=%s"
        % (len(rp.get("rows") or []), rp.get("total_fires_per_week"), rp.get("source"))
    )


if __name__ == "__main__":
    main()
