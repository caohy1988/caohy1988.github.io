#!/usr/bin/env python3
"""Strict JSON: snapshot.json never carries NaN / Infinity, and the page never shows them.

    python3 test_strict_json.py

Synthetic values only: stub collectors, a temp HOME for Kimi, a temp output dir. Never touches real
credentials, the network, the real CLIs, or the real snapshot.json / index.html.
"""
import contextlib
import copy
import io
import json
import math
import os
import subprocess
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

REAL = {name: getattr(cab, name) for name in ("collect_kimi", "main")}
PT = cab.PT
NOW = datetime(2026, 10, 24, 12, 0, tzinfo=PT)
MODEL = "qwen/qwen3.8-max-0902"
NAN, INF = float("nan"), float("inf")


def strict_loads(text):
    def refuse(token):
        raise ValueError(f"non-finite JSON token {token}")
    return json.loads(text, parse_constant=refuse)


def qwen_line(inp, out=0, cached=0):
    return json.dumps({"version": 1, "sessionId": "s1", "timestamp": int((NOW - timedelta(hours=1)).timestamp() * 1000),
                       "models": {MODEL: {"requests": 1, "inputTokens": inp, "outputTokens": out,
                                          "cachedTokens": cached}}})


def qwen_card(text):
    u = cab.summarize_qwen_usage(text, NOW)
    trial = u.pop("trial")
    return u, cab.render_qwen_body({"usage": u, "trial": trial, "ok": True, "auth_ok": True})


def stub_collectors(**seats):
    """Patch every collect_* function (so a new collector can never reach the network from a test)."""
    names = [n for n in dir(cab) if n.startswith("collect_") and callable(getattr(cab, n))]
    return mock.patch.multiple(cab, **{n: (lambda v=seats.get(n[len("collect_"):], {}): copy.deepcopy(v))
                                       for n in names})


class FiniteTreeTests(unittest.TestCase):
    def test_non_finite_floats_become_null(self):
        tree = {"a": NAN, "b": [1, INF, {"c": -INF}], "d": (2.5, NAN), "e": "Infinity", "f": True, "g": 10 ** 30,
                "h": 0.1, "i": None}
        got = cab.finite_tree(tree)
        self.assertEqual(got, {"a": None, "b": [1, None, {"c": None}], "d": [2.5, None], "e": "Infinity",
                               "f": True, "g": 10 ** 30, "h": 0.1, "i": None})
        strict_loads(json.dumps(got, allow_nan=False))


class QwenCounterTests(unittest.TestCase):
    def test_counter_past_the_producer_range_is_an_unreadable_line(self):
        u, html = qwen_card(qwen_line(10 ** 308))
        self.assertEqual((u["state"], u["bad_lines"], u["sessions"]), ("unreadable", 1, 0))
        strict_loads(json.dumps(u, allow_nan=False))
        self.assertNotIn("$inf", html)
        self.assertIn("1 unreadable line", html)

    def test_largest_exact_javascript_integer_is_accepted(self):
        u, _ = qwen_card(qwen_line(2 ** 53 - 1))
        self.assertEqual((u["state"], u["bad_lines"]), ("ok", 0))
        self.assertTrue(math.isfinite(u["windows"]["all_time"]["est_cost_usd"]))
        u, _ = qwen_card(qwen_line(2 ** 53))
        self.assertEqual((u["state"], u["bad_lines"]), ("unreadable", 1))

    def test_overflowing_estimate_is_null_not_infinity(self):
        huge = {"input": 1e308, "cached_input": 1e308, "output": 1e308}
        with mock.patch.dict(cab.QWEN_PRICES, {MODEL: huge}):
            u, html = qwen_card(qwen_line(10 ** 6, 10 ** 6))
        self.assertIsNone(u["windows"]["all_time"]["est_cost_usd"])
        self.assertIsNone(u["models"][0]["est_cost_usd"])
        strict_loads(json.dumps(u, allow_nan=False))
        self.assertNotIn("$inf", html)


class PacingRatioTests(unittest.TestCase):
    def test_overflowing_ratio_is_null(self):
        week, now = 7 * 86400, datetime(2026, 10, 13, 20, 0, tzinfo=timezone.utc)
        p = cab.pacing(1e308, now + timedelta(seconds=week, microseconds=-1), week, now)
        self.assertEqual(p["status"], "ok")
        self.assertIsNone(p["ratio"])
        strict_loads(json.dumps(p, allow_nan=False))
        self.assertNotIn("inf", cab.pacing_html(p))


class KimiPercentTests(unittest.TestCase):
    def collect(self, limit, remaining):
        payload = {"usage": {"limit": limit, "remaining": remaining, "resetTime": "2026-10-30T00:00:00Z"},
                   "limits": [{"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                               "detail": {"limit": limit, "remaining": remaining,
                                          "resetTime": "2026-10-24T20:00:00Z"}}]}
        done = subprocess.CompletedProcess(["curl"], 0, stdout=json.dumps(payload) + "\n__HTTP__200", stderr="")
        with tempfile.TemporaryDirectory() as d:
            cred = Path(d) / ".kimi-code" / "credentials" / "kimi-code.json"
            cred.parent.mkdir(parents=True)
            cred.write_text(json.dumps({"access_token": "FAKE-kimi-token-0123456789"}))
            with mock.patch.dict(os.environ, {"HOME": d}), mock.patch.object(cab.subprocess, "run", return_value=done):
                return REAL["collect_kimi"]()

    def test_non_finite_limit_or_remaining_is_no_reading(self):
        for limit, remaining in (("Infinity", "5"), ("100", "NaN"), ("1e999", "0"), ("100", "-Infinity")):
            seat = self.collect(limit, remaining)
            self.assertTrue(seat["source"].startswith("GET https://api.kimi.com"), seat)
            self.assertIsNone(seat["used_percent"], (limit, remaining))
            self.assertEqual(seat["bars"], [], (limit, remaining))
            self.assertNotEqual(seat["status"], "blocked_quota", (limit, remaining))

    def test_finite_reading_still_works(self):
        seat = self.collect("100", "38")
        self.assertEqual((seat["used_percent"], [b["used_percent"] for b in seat["bars"]]), (62.0, [62.0, 62.0]))


class CronStepTests(unittest.TestCase):
    def test_zero_step_does_not_raise(self):
        for cron in ("*/0 * * * *", "0 */0 * * *", "5 9 */0 * *"):
            v = cab._cron_fires_per_week(cron)
            self.assertTrue(v is None or math.isfinite(v), (cron, v))


class MainWritesStrictJsonTests(unittest.TestCase):
    def test_non_finite_values_publish_as_null(self):
        seats = {
            "claude": {"ok": True, "bars": [{"label": "Current session", "used_percent": NAN, "reset": "x",
                                             "tone": "unk"}]},
            "kimi": {"ok": True, "status": "ok", "used_percent": INF,
                     "bars": [{"label": "Weekly (7-day) usage", "used_percent": INF, "reset": "x", "tone": "bad"}]},
            "qwen": {"ok": True, "auth_ok": True, "cli_version": "0.26.1",
                     "usage": {"state": "ok", "sessions": 1, "bad_lines": 0, "future_records": 0,
                               "windows": {"all_time": {"sessions": 1, "requests": 1, "input_tokens": 1,
                                                        "cached_tokens": 0, "output_tokens": 1,
                                                        "unpriced_models": 0, "est_cost_usd": INF}},
                               "models": []},
                     "trial": {"runs": 0, "runs_display": "0/3", "status": "x"}},
            "grok": {"ok": True, "bots": [dict(cab._empty_bot("Medium Bot"), share_assistant_tool_pct=NAN)],
                     "fleet_messages_total": 0, "fleet_assistant_tool_total": 0},
        }
        with tempfile.TemporaryDirectory() as d, stub_collectors(**seats), mock.patch.object(cab, "HERE", Path(d)), \
                contextlib.redirect_stdout(io.StringIO()):
            REAL["main"]()
            text = (Path(d) / "snapshot.json").read_text()
            html = (Path(d) / "index.html").read_text()
        snap = strict_loads(text)
        self.assertIsNone(snap["claude"]["bars"][0]["used_percent"])
        self.assertIsNone(snap["kimi"]["used_percent"])
        self.assertIsNone(snap["qwen"]["usage"]["windows"]["all_time"]["est_cost_usd"])
        self.assertIsNone(snap["grok"]["bots"][0]["share_assistant_tool_pct"])
        for token in ("NaN", "Infinity", "$inf", "nan%", "inf%"):
            self.assertNotIn(token, text + html, token)


if __name__ == "__main__":
    unittest.main()
