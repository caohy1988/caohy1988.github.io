#!/usr/bin/env python3
"""Collect Mac CLI model-usage snapshots and build a Field Brief–styled dashboard."""

from __future__ import annotations

import json
import os
import re
import subprocess
import urllib.request
import urllib.error
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

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
DSH_BIN = Path.home() / ".local/bin/dsh"
DSH_DIR = Path.home() / ".dsh"
GROK_CACHE = HERE / "grok_box_activity.json"

# Box collection + freshness logic is shared with the box-side collector script.
from collect_grok_box_activity import (  # noqa: E402
    BOX_TRANS,
    GROK_LINKS,
    GROK_NOTE,
    GROK_ORDER,
    GROK_ROLES,
    GROK_SKIP_NAMES,
    STALE_AFTER_HOURS,
    build_payload,
    collect_box_bots,
    empty_bot as _empty_bot,
    ms_to_pt,
    normalize_bots,
    staleness,
)

GROK_COLORS = ["#0f766e", "#e87324", "#2563eb", "#7c3aed"]


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
                }
            )
        out["ok"] = bool(out["bars"])
        out["fable_blocked"] = any(
            b["label"].lower().startswith("current week (fable)") and b["used_percent"] >= 100
            for b in out["bars"]
        )
    except Exception as e:
        out["error"] = str(e)
    return out


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
                curl_err = (proc.stderr or proc.stdout or f"curl exit {proc.returncode}")[:400]
        except Exception as e:
            curl_err = str(e)
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
                out["error"] = f"curl: {curl_err}; urllib: {e}"
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
        rl = data.get("rate_limit") or {}
        pw = rl.get("primary_window") or {}
        pct = pw.get("used_percent")
        reset = ts_to_pt(pw.get("reset_at"))
        if reset is None and pw.get("reset_after_seconds") is not None:
            reset = ts_to_pt(datetime.now(timezone.utc).timestamp() + float(pw["reset_after_seconds"]))
        out["bars"].append(
            {
                "label": "Primary window",
                "used_percent": pct,
                "reset": reset,
                "tone": bar_class(pct, blocked=bool(rl.get("limit_reached"))),
                "allowed": rl.get("allowed"),
                "limit_reached": rl.get("limit_reached"),
            }
        )
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
        addl = []
        for item in data.get("additional_rate_limits") or []:
            arl = (item.get("rate_limit") or {}).get("primary_window") or {}
            apct = arl.get("used_percent")
            addl.append(
                {
                    "limit_name": item.get("limit_name"),
                    "used_percent": apct,
                    "reset": ts_to_pt(arl.get("reset_at")),
                    "tone": bar_class(apct),
                }
            )
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
        out["error"] = str(e)
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
            err = (proc.stderr or body or f"curl exit {proc.returncode} http={http_code}")[:300]
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
                def pct_used(limit_s, remaining_s):
                    try:
                        lim = float(limit_s)
                        rem = float(remaining_s)
                        if lim <= 0:
                            return None
                        return round(max(0.0, min(100.0, 100.0 * (lim - rem) / lim)), 1)
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
                weekly_reset = fmt_reset(usage.get("resetTime"))
                bars = []
                if weekly_used is not None:
                    bars.append(
                        {
                            "label": "Weekly (7-day) usage",
                            "used_percent": weekly_used,
                            "reset": weekly_reset,
                            "tone": tone_for(weekly_used),
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
        out["api_error"] = str(e)[:300]
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
        out["cli_version_error"] = str(e)

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
        out["usage_error"] = str(e)

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
        if cur > 0:
            return bots
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
    return build_payload(bots, "box /home/box/agent-data (live)")



def collect_muse() -> dict:
    """Muse Code / Muse Spark — version + auth; Meta does not expose CLI quota bars yet."""
    import shutil

    out: dict = {
        "ok": False,
        "source": "muse --version + ~/.config/muse/auth.json",
        "bars": [],
        "model": "muse-spark-1.3-contributor",
        "product": "Muse Code",
        "model_family": "Muse Spark",
    }
    try:
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
        if MUSE_AUTH.exists():
            auth = json.loads(MUSE_AUTH.read_text())
            meta = (auth.get("providers") or {}).get("meta") or {}
            mechanism = meta.get("mechanism") or meta.get("obtained_via") or meta.get("storage")
            auth_ok = bool(meta)
        out["auth_ok"] = auth_ok
        out["auth_mechanism"] = mechanism
        out["ok"] = bool(out.get("cli_version")) and auth_ok
        out["detail"] = (
            "Per Muse itself (2026-09-15): no documented /usage, muse usage, or quota API. "
            "Plan/limits live in Meta Accounts Center (web). Card shows install + auth health only."
        )
        if not auth_ok:
            out["error"] = "muse auth missing — run muse login"
    except Exception as e:
        out["error"] = str(e)
    return out



def collect_dsh() -> dict:
    """DSH (DeepSeek Harness) — version + OpenRouter auth health; credits PAYG (no Coding Plan bars)."""
    import shutil
    import re

    out: dict = {
        "ok": False,
        "source": "dsh --version + ~/.dsh settings/credentials",
        "bars": [],
        "product": "DeepSeek Harness",
        "model": "z-ai/glm-5.3",
        "provider": "openrouter",
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

        settings = DSH_DIR / "settings.yaml"
        if settings.exists():
            raw = settings.read_text()
            m = re.search(r"agent-default-model:\s*\n(?:\s+\w+:.*\n)*?\s+model:\s*([^\n]+)", raw)
            if not m:
                m = re.search(r"agent-default-model:[\s\S]*?model:\s*([^\n]+)", raw)
            if m:
                out["model"] = m.group(1).strip().strip("\"'")
            if re.search(r"provider:\s*openrouter", raw):
                out["provider"] = "openrouter"
            pm = re.search(r"agent-default-model:[\s\S]*?provider:\s*([^\n]+)", raw)
            if pm:
                out["provider"] = pm.group(1).strip().strip("\"'")

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
            "Card shows install + OpenRouter key presence + default model only."
        )
        if not auth_ok:
            out["error"] = "OpenRouter key missing — set OPENROUTER_API_KEY in ~/.dsh/.env"
    except Exception as e:
        out["error"] = str(e)
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
            except ValueError:
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
        except ValueError:
            fires_per_hour = 1.0
        return round(fires_per_hour * hours_per_day * days, 1)

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
    """Fleet routine fire-count proxy — NOT dollars. Newest Collection + Github dumps + Manage."""
    vault = Path.home() / "Documents/agent-context"
    hunt = vault / "Hunt/agent-manage"
    rows = []
    sources = []

    manage = [
        ("Agent Manage Bot", "Weekday usage dashboard refresh", "5 9 * * 1-5", "weekday integrity check"),
        ("Agent Manage Bot", "Field Brief 6h orchestration watch", "50 0,6,12,18 * * *", "detect-only second-line room ping"),
        ("Agent Manage Bot", "Daily harness-lab collect kick", "0 9 * * *", "Agy/Muse/DSH Lab scout"),
        ("Agent Manage Bot", "Daily harness-lab curate publish", "30 16 * * *", "KEEP-only Lab publish"),
    ]
    for owner, name, cron, notes in manage:
        rows.append({
            "owner": owner,
            "name": name,
            "cron": cron,
            "fires_per_week": _cron_fires_per_week(cron),
            "notes": notes,
            "status": "enabled",
        })
    sources.append("Manage Bot (%d)" % len(manage))

    dump_specs = [
        ("*collection-bot-active-routines.md", "Collection Bot"),
        ("*github-bot-active-routines.md", "Github Bot"),
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
            "Coarse cron math only. Newest *collection-bot-active-routines.md + "
            "*github-bot-active-routines.md under Hunt/agent-manage/ plus Manage Bot. "
            "Event listeners show as (event listener) with no fires/week. Not tokens or plan spend."
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
            data["bots"] = bots
            data["fleet_assistant_tool_total"] = sum(b["messages"]["assistant_tool"] for b in bots)
            data["fleet_messages_total"] = sum(b["messages"]["total"] for b in bots)
            return _mark_stale(data, data)
        except Exception as e:
            return {
                "ok": False,
                "source": "grok_box_activity.json",
                "error": str(e),
                "stale": True,
                "stale_reason": f"grok_box_activity.json unreadable ({e})",
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


def render_grok_body(grok: dict) -> str:
    """Grok section body — STALE banner first when the box activity cache is old/unknown."""
    bots = grok.get("bots") or []
    fleet = grok.get("fleet_messages_total") or 0
    # stacked share bar
    segments = []
    legend = []
    for i, b in enumerate(bots):
        pct = float(b.get("share_assistant_tool_pct") or 0)
        color = GROK_COLORS[i % len(GROK_COLORS)]
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
          <td>{esc(b.get('last_transcript_activity_pt') or '—')}</td>
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
      <p class="link-pills">
        <a class="link-pill" href="{esc(ub)}">Usage &amp; Billing</a>
        <a class="link-pill" href="{esc(od)}">On-demand</a>
      </p>
      <p class="muted">Activity share from local Grok Bot transcripts — not Cursor plan dollars. Open Usage &amp; Billing for included/on-demand spend.</p>
    """
    return grok_body


def render_html(snap: dict) -> str:
    refreshed = snap["refreshed_at"]
    claude = snap["claude"]
    codex = snap["codex"]
    kimi = snap["kimi"]
    agy = snap["agy"]
    muse = snap.get("muse") or {}
    dsh = snap.get("dsh") or {}
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
        </div>"""
            )
        return "\n".join(parts) if parts else '<p class="muted">No bar data.</p>'

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
          <div class="metric-label">{esc(a.get('limit_name'))}</div>
          {progress_bar(a.get('used_percent'), a.get('tone') or 'ok')}
          <div class="metric-reset">Resets {esc(a.get('reset') or '—')}</div>
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
      <div class="status-chip {tone}">{esc(chip)}</div>
      <p class="kimi-detail">{esc(kimi.get('detail') or '')}</p>
      {kimi_bars}
      {kimi_extra}
      <p class="muted">Bars from live <code>/usages</code> API (used % = 100 − remaining). Vault markers are fallback only.</p>
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
    muse_chip = "AUTH OK" if muse.get("ok") else "AUTH / INSTALL"
    muse_bars = bars_html(muse.get("bars") or [])
    muse_err = ""
    if muse.get("error"):
        muse_err = f'<p class="err">{esc(muse.get("error"))}</p>'
    muse_body = f"""
      <p class="pill">CLI <strong>{esc(muse.get('cli_version') or '—')}</strong> · model <strong>{esc(muse.get('model') or 'muse-spark-1.3-contributor')}</strong></p>
      <div class="metric">
        <div class="metric-label">Muse Spark status</div>
        <div class="status-chip {muse_tone}">{esc(muse_chip)}</div>
        <div class="metric-reset">auth {esc(muse.get('auth_mechanism') or '—')} · no CLI quota bars yet</div>
      </div>
      {muse_err}
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
      <p class="pill">CLI <strong>{esc(dsh.get('cli_version') or '—')}</strong> · provider <strong>{esc(dsh.get('provider') or 'openrouter')}</strong> · model <strong>{esc(dsh.get('model') or 'z-ai/glm-5.3')}</strong></p>
      <div class="metric">
        <div class="metric-label">DSH status</div>
        <div class="status-chip {dsh_tone}">{esc(dsh_chip)}</div>
        <div class="metric-reset">auth {esc(dsh.get('auth_mechanism') or '—')} · OpenRouter credits (no plan bars)</div>
      </div>
      {dsh_err}
      {dsh_bars}
      <p class="muted">{esc(dsh.get('detail') or 'DeepSeek Harness via OpenRouter.')}</p>
    """

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
      <p class="lede">At-a-glance quotas for Claude/Fable, Codex/Astra, Kimi, Agy, Muse Spark, DSH, Grok activity share, plus a routine fires/week proxy (not dollars).</p>
      <div class="meta">
        <span>Last refreshed <strong>{esc(refreshed)}</strong></span>
        <span>Timezone <strong>America/Los_Angeles</strong></span>
      </div>
      <div class="legend">
        <span><i class="ok"></i>&lt;70% green</span>
        <span><i class="warn"></i>70–89% amber</span>
        <span><i class="bad"></i>≥90% / blocked red</span>
      </div>
    </header>

    <div class="grid">
      <section class="card" id="claude">
        <h2>Claude / Fable</h2>
        <p class="sub">claude -p /usage</p>
        {claude_body}
      </section>

      <section class="card" id="codex">
        <h2>Codex / Astra</h2>
        <p class="sub">wham/usage · plan + primary window</p>
        {codex_body}
      </section>

      <section class="card" id="kimi">
        <h2>Kimi</h2>
        <p class="sub">weekly (7-day) quota · derived status</p>
        {kimi_body}
      </section>

      <section class="card" id="agy">
        <h2>Agy</h2>
        <p class="sub">agy -p /usage · pack · social-superpowers MCP</p>
        {agy_body}
      </section>

      <section class="card" id="muse">
        <h2>Muse / Muse Spark</h2>
        <p class="sub">muse --version · Meta Muse Code</p>
        {muse_body}
      </section>

      <section class="card" id="dsh">
        <h2>DSH / DeepSeek Harness</h2>
        <p class="sub">dsh --version · OpenRouter GLM / DeepSeek</p>
        {dsh_body}
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
        "claude": collect_claude(),
        "codex": collect_codex(),
        "kimi": collect_kimi(),
        "agy": collect_agy(),
        "muse": collect_muse(),
        "dsh": collect_dsh(),
        "routine_proxy": collect_routine_proxy(),
        "grok": collect_grok(),
    }

    publish = json.loads(json.dumps(snap))
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

    HERE.mkdir(parents=True, exist_ok=True)
    (HERE / "snapshot.json").write_text(json.dumps(publish, indent=2) + "\n")
    html = render_html(snap)
    (HERE / "index.html").write_text(html)
    print(f"Wrote {HERE / 'snapshot.json'}")
    print(f"Wrote {HERE / 'index.html'}")
    print(f"Refreshed at {snap['refreshed_at']}")
    k = snap["kimi"]
    print(f"Kimi: {k.get('status')} chip={k.get('chip')} pct={k.get('used_percent')}")
    a = snap["agy"]
    print(f"Agy: ssp={ (a.get('social_superpowers') or {}).get('state') } health={ (a.get('collect_health') or {}).get('chip') }")
    m = snap.get("muse") or {}
    print(f"Muse: ok={m.get('ok')} ver={m.get('cli_version')} model={m.get('model')}")
    d = snap.get("dsh") or {}
    print(f"DSH: ok={d.get('ok')} ver={d.get('cli_version')} model={d.get('model')} provider={d.get('provider')}")
    g = snap["grok"]
    print(f"Grok: bots={len(g.get('bots') or [])} fleet={g.get('fleet_messages_total')} source={g.get('source')} stale={g.get('stale')}")
    rp = snap.get("routine_proxy") or {}
    print(
        "RoutineProxy: rows=%s fires_per_week≈%s source=%s"
        % (len(rp.get("rows") or []), rp.get("total_fires_per_week"), rp.get("source"))
    )


if __name__ == "__main__":
    main()
