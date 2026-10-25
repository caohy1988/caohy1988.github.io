#!/usr/bin/env python3
"""Tests for the report-only pacing figure on the Mac CLI quota cards: the share of each
rolling window used vs the share of that window elapsed at the reading.

    python3 -m unittest test_pacing

Synthetic readings only: fake `/usage` text and fake API payloads behind a patched
subprocess.run, a temp HOME, a temp output dir. Never touches real credentials, the
network, the real CLIs, or the real snapshot.json / index.html.
"""
import contextlib
import io
import json
import os
import re
import subprocess
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

# test_error_redaction.py replaces collectors with stubs at import time; when both run in
# one unittest process, keep the real ones captured here (list this module before it).
REAL = {
    name: getattr(cab, name)
    for name in ("collect_claude", "collect_codex", "collect_kimi", "parse_agy_usage_tsv", "main")
}

UTC = timezone.utc
PT = cab.PT
NOW = datetime(2026, 10, 13, 20, 55, 50, tzinfo=UTC)  # 13:55:50 PDT
WEEK = 7 * 86400
FIVE_H = 5 * 3600
AHEAD = "more than 15 pts ahead of the clock"
PAST = "past 90% used"


def at_elapsed(pct, window_s, now=NOW):
    """Reset time that puts `now` at `pct` % of a window of `window_s` seconds."""
    return now + timedelta(seconds=window_s * (1 - pct / 100.0))


def iso(dt):
    return dt.astimezone(UTC).strftime("%Y-%m-%dT%H:%M:%SZ")


def bar(label, used, reset_at, window_s, now=NOW):
    """A collector-shaped bar with pacing attached the way main() does it."""
    b = {
        "label": label,
        "used_percent": used,
        "reset": "test",
        "tone": cab.bar_class(used),
        "reset_at": iso(reset_at) if reset_at else None,
        "window_seconds": window_s,
    }
    return cab.add_pacing({"bars": [b]}, now)["bars"][0]


def make_snap(**seats):
    snap = {
        "refreshed_at": "2026-10-13 13:55:50 PDT",
        "claude": {"ok": True, "bars": []},
        "codex": {"ok": False, "error": "offline"},
        "kimi": {},
        "agy": {},
        "muse": {},
        "dsh": {},
        "routine_proxy": {},
        "grok": {"ok": False, "bots": [], "stale": True, "stale_reason": "test"},
    }
    snap.update(seats)
    return snap


def card(html, card_id):
    """(class attribute, inner html) of one dashboard card."""
    m = re.search(r'<section class="([^"]*)" id="%s">(.*?)</section>' % re.escape(card_id), html, re.S)
    assert m, f"card #{card_id} not found"
    return m.group(1), m.group(2)


def completed(stdout):
    return subprocess.CompletedProcess(args=["fake"], returncode=0, stdout=stdout, stderr="")


def codex_win(used, window_s, elapsed_pct):
    """A wham/usage window object whose reset puts NOW at `elapsed_pct` % of the window."""
    return {"used_percent": used, "limit_window_seconds": window_s,
            "reset_at": int(at_elapsed(elapsed_pct, window_s).timestamp())}


def fake_auth():
    """Stands in for ~/.codex/auth.json without touching disk."""
    token = json.dumps({"tokens": {"access_token": "FAKE-codex-token-0123456789"}})
    return mock.Mock(**{"read_text.return_value": token})


class FakeKimiCred:
    """Stands in for Path.home() / ".kimi-code/credentials/kimi-code.json" without touching disk."""

    def __truediv__(self, _part):
        return self

    def exists(self):
        return True

    def read_text(self):
        return json.dumps({"access_token": "FAKE-kimi-token-0123456789"})

    def stat(self):
        return types.SimpleNamespace(st_mtime=NOW.timestamp())

    def __str__(self):
        return "/fake-home/.kimi-code/credentials/kimi-code.json"


def kimi_paced(weekly_remaining, weekly_reset, five_h=None):
    """collect_kimi() on a fake /usages payload (every limit 10000, so 0.01-point steps), then
    pacing as of NOW. five_h = (remaining, reset) adds one 300-minute limit window."""
    payload = {"usage": {"limit": "10000", "remaining": str(weekly_remaining), "resetTime": iso(weekly_reset)},
               "limits": []}
    if five_h:
        payload["limits"].append({"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                                  "detail": {"limit": "10000", "remaining": str(five_h[0]),
                                             "resetTime": iso(five_h[1])}})
    with mock.patch.object(cab.Path, "home", return_value=FakeKimiCred()), \
            mock.patch.object(cab.subprocess, "run", return_value=completed(json.dumps(payload) + "\n__HTTP__200")):
        seat = REAL["collect_kimi"]()
    assert seat["source"].startswith("GET https://api.kimi.com"), seat  # live-API path, not the fallback
    return cab.add_pacing(seat, NOW)


class PacingMathTests(unittest.TestCase):
    def test_ahead_of_clock_is_marked(self):
        p = cab.pacing(62, at_elapsed(40, WEEK), WEEK, NOW)
        self.assertEqual(p["status"], "ok")
        self.assertEqual((p["used_pct"], p["elapsed_pct"], p["ahead_points"]), (62.0, 40.0, 22.0))
        self.assertEqual(p["ratio"], 1.55)
        self.assertTrue(p["marked"])
        self.assertEqual(p["mark_reasons"], [AHEAD])

    def test_behind_clock_is_not_marked(self):
        p = cab.pacing(20, at_elapsed(40, WEEK), WEEK, NOW)
        self.assertEqual((p["ahead_points"], p["ratio"]), (-20.0, 0.5))
        self.assertFalse(p["marked"])
        self.assertEqual(p["mark_reasons"], [])

    def test_on_the_clock_is_not_marked(self):
        p = cab.pacing(40, at_elapsed(40, WEEK), WEEK, NOW)
        self.assertEqual((p["ahead_points"], p["ratio"], p["marked"]), (0.0, 1.0, False))

    def test_exactly_threshold_points_ahead_is_not_marked(self):
        p = cab.pacing(55, at_elapsed(40, WEEK), WEEK, NOW)
        self.assertEqual(p["ahead_points"], 15.0)
        self.assertFalse(p["marked"])

    def test_just_over_threshold_is_marked(self):
        p = cab.pacing(55.5, at_elapsed(40, WEEK), WEEK, NOW)
        self.assertEqual(p["ahead_points"], 15.5)
        self.assertTrue(p["marked"])

    def test_past_used_mark_is_marked_even_on_pace(self):
        p = cab.pacing(95, at_elapsed(94, WEEK), WEEK, NOW)
        self.assertEqual(p["ahead_points"], 1.0)
        self.assertTrue(p["marked"])
        self.assertEqual(p["mark_reasons"], [PAST])

    def test_exactly_used_mark_is_not_marked(self):
        p = cab.pacing(90, at_elapsed(88, WEEK), WEEK, NOW)
        self.assertFalse(p["marked"])

    def test_both_reasons_listed(self):
        p = cab.pacing(99, at_elapsed(50, WEEK), WEEK, NOW)
        self.assertEqual(p["mark_reasons"], [AHEAD, PAST])

    def test_five_hour_window(self):
        p = cab.pacing(34, NOW + timedelta(hours=1), FIVE_H, NOW)
        self.assertEqual((p["elapsed_pct"], p["ahead_points"], p["marked"]), (80.0, -46.0, False))

    def test_window_just_started(self):
        p = cab.pacing(0, NOW + timedelta(seconds=WEEK), WEEK, NOW)
        self.assertEqual((p["status"], p["elapsed_pct"], p["ratio"], p["marked"]), ("ok", 0.0, None, False))
        p = cab.pacing(16, NOW + timedelta(seconds=WEEK), WEEK, NOW)
        self.assertEqual((p["ahead_points"], p["ratio"], p["marked"]), (16.0, None, True))

    def test_small_clock_skew_counts_as_window_start(self):
        p = cab.pacing(5, NOW + timedelta(seconds=WEEK + 120), WEEK, NOW)
        self.assertEqual((p["status"], p["elapsed_pct"]), ("ok", 0.0))

    def test_inputs_are_coerced(self):
        p = cab.pacing("62", at_elapsed(40, WEEK), "604800", NOW)
        self.assertEqual((p["status"], p["ahead_points"]), ("ok", 22.0))

    def test_thresholds_are_module_constants(self):
        self.assertEqual((cab.PACE_AHEAD_POINTS, cab.PACE_USED_MARK_PCT), (15.0, 90.0))
        with mock.patch.object(cab, "PACE_AHEAD_POINTS", 25.0):
            self.assertFalse(cab.pacing(62, at_elapsed(40, WEEK), WEEK, NOW)["marked"])
        with mock.patch.object(cab, "PACE_USED_MARK_PCT", 80.0):
            self.assertEqual(cab.pacing(85, at_elapsed(84, WEEK), WEEK, NOW)["mark_reasons"], ["past 80% used"])


class PacingNotApplicableTests(unittest.TestCase):
    def assertNA(self, p, reason):
        self.assertEqual(p, {"status": "n/a", "reason": reason, "marked": False})

    def test_no_reset_time(self):
        self.assertNA(cab.pacing(62, None, WEEK, NOW), "no window time")

    def test_naive_reset_time_is_not_a_window_time(self):
        self.assertNA(cab.pacing(62, datetime(2026, 10, 15, 12, 0), WEEK, NOW), "no window time")

    def test_no_window_time_wins_over_other_gaps(self):
        self.assertNA(cab.pacing(None, None, None, NOW), "no window time")

    def test_unknown_window_length(self):
        for w in (None, 0, -5, "abc"):
            self.assertNA(cab.pacing(62, at_elapsed(40, WEEK), w, NOW), "unknown window length")

    def test_no_usage_reading(self):
        for used in (None, "n/a"):
            self.assertNA(cab.pacing(used, at_elapsed(40, WEEK), WEEK, NOW), "no usage reading")

    def test_window_already_reset(self):
        self.assertNA(cab.pacing(100, NOW, WEEK, NOW), "window already reset")
        self.assertNA(cab.pacing(100, NOW - timedelta(minutes=5), WEEK, NOW), "window already reset")

    def test_reset_beyond_one_window(self):
        self.assertNA(cab.pacing(5, NOW + timedelta(seconds=FIVE_H + 3600), FIVE_H, NOW), "reset time outside window")

    def test_absurd_numbers_never_raise_or_leak_nan(self):
        """Untrusted API values: no exception (it would stop the build), no NaN/inf in the JSON."""
        reset = at_elapsed(40, WEEK)
        for used in (10 ** 400, float("nan"), float("inf")):
            self.assertNA(cab.pacing(used, reset, WEEK, NOW), "no usage reading")
        for window in (10 ** 400, float("nan"), float("inf")):
            self.assertNA(cab.pacing(62, reset, window, NOW), "unknown window length")
        for duration in (10 ** 400, float("nan"), float("inf")):
            self.assertIsNone(cab.window_seconds_from_unit(duration, "TIME_UNIT_MINUTE"), duration)
        win = cab._codex_window({"limit_window_seconds": float("inf"), "reset_after_seconds": 1e300})
        self.assertEqual(win, {"reset_at": None, "window_seconds": None})


class WindowFieldTests(unittest.TestCase):
    def test_window_seconds_from_name(self):
        cases = {
            "Current session": FIVE_H,
            "Current week (all models)": WEEK,
            "Current week (Fable)": WEEK,
            "Weekly Limit Remaining": WEEK,
            "Five Hour Limit Remaining": FIVE_H,
            "Weekly (7-day) usage": WEEK,
            "5-hour window": FIVE_H,
            "Primary window": None,
            "Daily Limit Remaining": None,
            None: None,
        }
        for name, want in cases.items():
            self.assertEqual(cab.window_seconds_from_name(name), want, name)

    def test_window_seconds_from_unit(self):
        cases = [
            ((300, "TIME_UNIT_MINUTE"), FIVE_H),
            ((5, "TIME_UNIT_HOUR"), FIVE_H),
            ((7, "TIME_UNIT_DAY"), WEEK),
            ((18000, "SECONDS"), FIVE_H),
            ((None, "TIME_UNIT_MINUTE"), None),
            ((300, ""), None),
            ((300, "TIME_UNIT_MILLISECOND"), None),
            ((0, "TIME_UNIT_MINUTE"), None),
        ]
        for args, want in cases:
            self.assertEqual(cab.window_seconds_from_unit(*args), want, args)

    def test_parse_reset_text(self):
        pt_now = NOW.astimezone(PT)
        cases = {
            "Oct 13 at 2:59pm (America/Los_Angeles)": datetime(2026, 10, 13, 14, 59, tzinfo=PT),
            "Oct 20 at 3pm (America/Los_Angeles)": datetime(2026, 10, 20, 15, 0, tzinfo=PT),
            "Oct 14 at 12:59am (America/Los_Angeles)": datetime(2026, 10, 14, 0, 59, tzinfo=PT),
            "Oct 14 at 12pm (America/Los_Angeles)": datetime(2026, 10, 14, 12, 0, tzinfo=PT),
            "Oct 14, 9:05am": datetime(2026, 10, 14, 9, 5, tzinfo=PT),  # no zone → PT
            "7:30pm (America/Los_Angeles)": datetime(2026, 10, 13, 19, 30, tzinfo=PT),  # later today
            "9am (America/Los_Angeles)": datetime(2026, 10, 14, 9, 0, tzinfo=PT),  # already passed → tomorrow
        }
        for text, want in cases.items():
            self.assertEqual(cab.parse_reset_text(text, pt_now), want, text)
        london = cab.parse_reset_text("Oct 13 at 2:59pm (Europe/London)", pt_now)
        self.assertEqual(london.astimezone(UTC), datetime(2026, 10, 13, 13, 59, tzinfo=UTC))

    def test_parse_reset_text_picks_nearest_year(self):
        dec30 = datetime(2026, 12, 30, 10, 0, tzinfo=PT)
        self.assertEqual(cab.parse_reset_text("Jan 2 at 3pm (America/Los_Angeles)", dec30),
                         datetime(2027, 1, 2, 15, 0, tzinfo=PT))
        jan1 = datetime(2027, 1, 1, 0, 30, tzinfo=PT)
        self.assertEqual(cab.parse_reset_text("Dec 31 at 11pm (America/Los_Angeles)", jan1),
                         datetime(2026, 12, 31, 23, 0, tzinfo=PT))  # in the past → pacing says reset

    def test_parse_reset_text_rejects_unknown(self):
        pt_now = NOW.astimezone(PT)
        for text in (None, "", "garbage", "when current 7-day window ends",
                     "Oct 13 at 2:59pm (Mars/Olympus)", "Feb 30 at 3pm (America/Los_Angeles)",
                     "Oct 13 at 13pm (America/Los_Angeles)"):
            self.assertIsNone(cab.parse_reset_text(text, pt_now), text)


class CollectorFieldTests(unittest.TestCase):
    """Collectors attach the reset time + window length they already read (no new sources)."""

    def test_agy_rows_carry_window_fields(self):
        tsv = (
            "Usage of Agy\n"
            "Gemini Models\tWeekly Limit Remaining\t51%\t2026-10-14T02:23:00Z\n"
            "Gemini Models\tFive Hour Limit Remaining\t66%\t2026-10-13T21:55:50.1234567Z\n"
            "Gemini Models\tDaily Limit Remaining\t90%\t2026-10-14T07:00:00Z\n"
            "Other Models\tWeekly Limit Remaining\t100%\n"
        )
        bars = REAL["parse_agy_usage_tsv"](tsv)
        got = [(b["window_seconds"], b["reset_at"]) for b in bars]
        self.assertEqual(got, [
            (WEEK, "2026-10-14T02:23:00Z"),
            (FIVE_H, "2026-10-13T21:55:50Z"),
            (None, "2026-10-14T07:00:00Z"),
            (WEEK, None),
        ])
        paced = cab.add_pacing({"bars": bars}, NOW)["bars"]
        self.assertEqual(paced[1]["pacing"]["elapsed_pct"], 80.0)  # 1h left of 5h
        self.assertEqual(paced[2]["pacing"]["reason"], "unknown window length")
        self.assertEqual(paced[3]["pacing"]["reason"], "no window time")

    def test_usage_text_seat_bars_carry_window_fields(self):
        text = (
            "Current session: 12% used · resets Oct 13 at 4:30pm (America/Los_Angeles)\n"
            "Current week (all models): 62% used · resets Oct 17 at 6:43pm (America/Los_Angeles)\n"
            "Current week (Fable): 95% used · resets Oct 17 at 6:43pm (America/Los_Angeles)\n"
            "Last 7d · 10 requests · 2 sessions\n"
        )
        with mock.patch.object(cab.subprocess, "run", return_value=completed(text)), \
                mock.patch.object(cab, "now_pt", return_value=NOW.astimezone(PT)):
            seat = REAL["collect_claude"]()
        self.assertTrue(seat["ok"])
        got = [(b["label"], b["window_seconds"], b["reset_at"]) for b in seat["bars"]]
        self.assertEqual(got, [
            ("Current session", FIVE_H, "2026-10-13T23:30:00Z"),
            ("Current week (all models)", WEEK, "2026-10-18T01:43:00Z"),
            ("Current week (Fable)", WEEK, "2026-10-18T01:43:00Z"),
        ])
        paced = [b["pacing"] for b in cab.add_pacing(seat, NOW)["bars"]]
        self.assertEqual([(round(p["ahead_points"], 1), p["marked"]) for p in paced],
                         [(-36.6, False), (22.0, True), (55.0, True)])

    def test_codex_payload_carries_window_fields(self):
        payload = {
            "plan_type": "pro",
            "rate_limit": {
                "allowed": True,
                "limit_reached": False,
                "primary_window": {"used_percent": 62, "limit_window_seconds": WEEK,
                                   "reset_after_seconds": 362880,
                                   "reset_at": int(at_elapsed(40, WEEK).timestamp())},
                "secondary_window": None,
            },
            "additional_rate_limits": [
                {"limit_name": "spark", "rate_limit": {"primary_window": {
                    "used_percent": 10, "limit_window_seconds": FIVE_H,
                    "reset_at": int((NOW + timedelta(hours=1)).timestamp())}}},
            ],
        }
        with mock.patch.object(cab, "CODEX_AUTH", fake_auth()), \
                mock.patch.object(cab.subprocess, "run", return_value=completed(json.dumps(payload))):
            seat = REAL["collect_codex"]()
        self.assertTrue(seat["ok"], seat.get("error"))
        b, a = seat["bars"][0], seat["additional_rate_limits"][0]
        self.assertEqual((b["window_seconds"], b["reset_at"]), (WEEK, iso(at_elapsed(40, WEEK))))
        self.assertEqual((a["window_seconds"], a["reset_at"]), (FIVE_H, iso(NOW + timedelta(hours=1))))
        cab.add_pacing(seat, NOW)
        self.assertEqual(seat["bars"][0]["pacing"]["ahead_points"], 22.0)
        self.assertEqual(seat["additional_rate_limits"][0]["pacing"]["ahead_points"], -70.0)

    def test_codex_reset_after_seconds_fallback(self):
        payload = {"rate_limit": {"primary_window": {
            "used_percent": 5, "limit_window_seconds": WEEK, "reset_after_seconds": 3600}}}
        with mock.patch.object(cab, "CODEX_AUTH", fake_auth()), \
                mock.patch.object(cab.subprocess, "run", return_value=completed(json.dumps(payload))):
            seat = REAL["collect_codex"]()
        got = cab._parse_iso(seat["bars"][0]["reset_at"])
        want = datetime.now(UTC) + timedelta(seconds=3600)
        self.assertLess(abs((got - want).total_seconds()), 5)

    def test_kimi_payload_carries_window_fields(self):
        week_reset = at_elapsed(40, WEEK).strftime("%Y-%m-%dT%H:%M:%S") + ".1234567Z"
        payload = {
            "usage": {"limit": "100", "remaining": "38", "resetTime": week_reset},
            "limits": [{"window": {"duration": 300, "timeUnit": "TIME_UNIT_MINUTE"},
                        "detail": {"limit": "100", "remaining": "90",
                                   "resetTime": iso(NOW + timedelta(hours=1))}}],
        }
        with tempfile.TemporaryDirectory() as d:
            cred = Path(d) / ".kimi-code" / "credentials" / "kimi-code.json"
            cred.parent.mkdir(parents=True)
            cred.write_text(json.dumps({"access_token": "FAKE-kimi-token-0123456789"}))
            with mock.patch.dict(os.environ, {"HOME": d}), \
                    mock.patch.object(cab.subprocess, "run",
                                      return_value=completed(json.dumps(payload) + "\n__HTTP__200")):
                seat = REAL["collect_kimi"]()
        self.assertEqual(seat["status"], "ok", seat)
        got = [(b["label"], b["window_seconds"], b["reset_at"]) for b in seat["bars"]]
        self.assertEqual(got, [
            ("Weekly (7-day) usage", WEEK, iso(at_elapsed(40, WEEK))),
            ("5-hour window", FIVE_H, iso(NOW + timedelta(hours=1))),
        ])
        paced = [b["pacing"] for b in cab.add_pacing(seat, NOW)["bars"]]
        self.assertEqual([(p["ahead_points"], p["marked"]) for p in paced], [(22.0, True), (-70.0, False)])

    def test_add_pacing_tolerates_seats_without_bars(self):
        for seat in ({}, {"ok": False, "error": "x"}, {"bars": None}, {"bars": [None, "x"]}):
            self.assertIs(cab.add_pacing(seat, NOW), seat)


class RenderTests(unittest.TestCase):
    def test_marked_card_shows_flag(self):
        snap = make_snap(claude={"ok": True, "bars": [
            bar("Current week (all models)", 62, at_elapsed(40, WEEK), WEEK),
            bar("Current session", 10, NOW + timedelta(hours=1), FIVE_H),
        ]})
        cls, body = card(cab.render_html(snap), "claude")
        self.assertEqual(cls, "card pace-marked")
        self.assertIn('class="pace-flag"', body)
        self.assertIn(f"Current week (all models) — {AHEAD}", body)
        self.assertIn("⚑ pacing: 62% used vs 40% of window elapsed (1.55× the clock) · 22 pts ahead", body)
        self.assertIn("pacing: 10% used vs 80% of window elapsed (0.12× the clock) · 70 pts behind", body)
        self.assertEqual(body.count("metric-pace marked"), 1)

    def test_unmarked_card_has_no_flag(self):
        snap = make_snap(kimi={"ok": True, "bars": [bar("Weekly (7-day) usage", 20, at_elapsed(40, WEEK), WEEK)]})
        cls, body = card(cab.render_html(snap), "kimi")
        self.assertEqual(cls, "card")
        self.assertNotIn("pace-flag", body)
        self.assertIn("20 pts behind", body)

    def test_seats_without_window_time_say_so(self):
        snap = make_snap(
            kimi={"ok": True, "bars": [{"label": "Weekly (7-day) usage", "used_percent": None,
                                        "reset": "N/A — numeric % API not available", "tone": "unk"}]},
        )
        cab.add_pacing(snap["kimi"], NOW)
        html = cab.render_html(snap)
        for card_id in ("muse", "dsh", "kimi"):
            cls, body = card(html, card_id)
            self.assertIn("pacing: n/a (no window time)", body, card_id)
            self.assertEqual(cls, "card", card_id)

    def test_other_na_reasons_render(self):
        snap = make_snap(agy={"bars": [bar("Gemini Models · Weekly Limit", 100, NOW - timedelta(minutes=1), WEEK)]})
        _, body = card(cab.render_html(snap), "agy")
        self.assertIn("pacing: n/a (window already reset)", body)

    def test_codex_additional_limits_render_pacing(self):
        snap = make_snap(codex={
            "ok": True,
            "bars": [bar("Primary window", 5, at_elapsed(10, WEEK), WEEK)],
            "additional_rate_limits": [dict(bar("spark", 95, at_elapsed(50, FIVE_H), FIVE_H), limit_name="spark")],
        })
        cls, body = card(cab.render_html(snap), "codex")
        self.assertEqual(cls, "card pace-marked")
        self.assertIn(f"spark — {AHEAD}, {PAST}", body)
        self.assertIn("pacing: 5% used vs 10% of window elapsed (0.5× the clock) · 5 pts behind", body)

    def test_failed_codex_card_is_not_flagged(self):
        snap = make_snap(codex={"ok": False, "error": "offline",
                                "bars": [bar("Primary window", 99, at_elapsed(10, WEEK), WEEK)]})
        cls, body = card(cab.render_html(snap), "codex")
        self.assertEqual(cls, "card")
        self.assertNotIn("pace-flag", body)

    def test_legend_states_rule_from_constants(self):
        html = cab.render_html(make_snap())
        self.assertIn("&gt;15 pts ahead of the window clock or past 90% used", html)
        with mock.patch.object(cab, "PACE_AHEAD_POINTS", 20.0):
            self.assertIn("&gt;20 pts ahead", cab.render_html(make_snap()))

    def test_main_publishes_pacing(self):
        now = datetime.now(UTC)
        seats = {
            "collect_claude": lambda: {"ok": True, "bars": [{
                "label": "Current week (all models)", "used_percent": 62, "reset": "x", "tone": "ok",
                "reset_at": iso(at_elapsed(40, WEEK, now)), "window_seconds": WEEK}]},
            "collect_codex": lambda: {"ok": False, "error": "offline"},
            "collect_kimi": lambda: {"ok": True, "bars": []},
            "collect_agy": lambda: {},
            "collect_muse": lambda: {"ok": True, "bars": []},
            "collect_dsh": lambda: {"ok": True, "bars": []},
            "collect_qwen": lambda: {},
            "collect_openrouter": lambda: {"ok": False, "error": "offline"},  # never the network from a test
            "collect_routine_proxy": lambda: {},
            "collect_grok": lambda: {"ok": False, "bots": [], "stale": True, "stale_reason": "test"},
        }
        with tempfile.TemporaryDirectory() as d, mock.patch.multiple(cab, HERE=Path(d), **seats), \
                contextlib.redirect_stdout(io.StringIO()):
            REAL["main"]()
            snap = json.loads((Path(d) / "snapshot.json").read_text())
            html = (Path(d) / "index.html").read_text()
        p = snap["claude"]["bars"][0]["pacing"]
        self.assertEqual(p["status"], "ok")
        self.assertAlmostEqual(p["elapsed_pct"], 40.0, delta=0.2)
        self.assertTrue(p["marked"])
        self.assertEqual(card(html, "claude")[0], "card pace-marked")
        self.assertIn("pacing: n/a (no window time)", card(html, "muse")[1])


class SecondaryWindowTests(unittest.TestCase):
    """Codex secondary windows, of the main limit and of each additional limit, get their own
    labelled bar and pacing; a card is marked when only a secondary window crosses a line."""

    def paced(self, payload):
        bars, addl = cab.codex_windows(payload)
        return cab.add_pacing({"ok": True, "bars": bars, "additional_rate_limits": addl}, NOW)

    def test_main_secondary_alone_past_used_mark(self):
        seat = self.paced({"rate_limit": {"primary_window": codex_win(5, FIVE_H, 50),
                                          "secondary_window": codex_win(95, WEEK, 94)}})
        self.assertEqual([b["label"] for b in seat["bars"]], ["Primary window", "Secondary window"])
        self.assertEqual([b["window_seconds"] for b in seat["bars"]], [FIVE_H, WEEK])
        self.assertEqual([b["pacing"]["mark_reasons"] for b in seat["bars"]], [[], [PAST]])
        cls, body = card(cab.render_html(make_snap(codex=seat)), "codex")
        self.assertEqual(cls, "card pace-marked")
        self.assertIn(f"Secondary window — {PAST}", body)
        self.assertNotIn("Primary window —", body)

    def test_main_secondary_alone_ahead_of_clock(self):
        seat = self.paced({"rate_limit": {"primary_window": codex_win(10, FIVE_H, 50),
                                          "secondary_window": codex_win(60, WEEK, 30)}})
        self.assertEqual([b["pacing"]["mark_reasons"] for b in seat["bars"]], [[], [AHEAD]])

    def test_additional_limit_secondary_alone(self):
        seat = self.paced({
            "rate_limit": {"primary_window": codex_win(5, WEEK, 50), "secondary_window": None},
            "additional_rate_limits": [{"limit_name": "spark", "rate_limit": {
                "primary_window": codex_win(10, FIVE_H, 50), "secondary_window": codex_win(70, WEEK, 40)}}],
        })
        self.assertEqual([b["label"] for b in seat["bars"]], ["Primary window"])  # null secondary: no bar
        addl = seat["additional_rate_limits"]
        self.assertEqual([a["label"] for a in addl], ["spark · primary window", "spark · secondary window"])
        self.assertEqual([a["limit_name"] for a in addl], ["spark", "spark"])
        self.assertEqual([a["window_seconds"] for a in addl], [FIVE_H, WEEK])
        self.assertEqual([a["pacing"]["mark_reasons"] for a in addl], [[], [AHEAD]])
        self.assertFalse(seat["bars"][0]["pacing"]["marked"])
        cls, body = card(cab.render_html(make_snap(codex=seat)), "codex")
        self.assertEqual(cls, "card pace-marked")
        self.assertIn(f"spark · secondary window — {AHEAD}", body)
        self.assertIn('<div class="metric-label">spark · secondary window</div>', body)
        self.assertIn('<div class="metric-label">spark · primary window</div>', body)

    def test_null_or_malformed_secondary_adds_nothing(self):
        bars, addl = cab.codex_windows({
            "rate_limit": {"primary_window": codex_win(5, WEEK, 50), "secondary_window": "n/a"},
            "additional_rate_limits": [{"limit_name": "x", "rate_limit": {
                "primary_window": codex_win(1, FIVE_H, 10), "secondary_window": None}}],
        })
        self.assertEqual([b["label"] for b in bars], ["Primary window"])
        self.assertEqual([a["label"] for a in addl], ["x · primary window"])

    def test_collect_codex_wires_secondary_windows(self):
        payload = {
            "rate_limit": {"allowed": True, "limit_reached": False,
                           "primary_window": codex_win(5, FIVE_H, 50),
                           "secondary_window": codex_win(95, WEEK, 94)},
            "additional_rate_limits": [{"limit_name": "spark", "rate_limit": {
                "primary_window": codex_win(10, FIVE_H, 50), "secondary_window": codex_win(70, WEEK, 40)}}],
        }
        with mock.patch.object(cab, "CODEX_AUTH", fake_auth()), \
                mock.patch.object(cab.subprocess, "run", return_value=completed(json.dumps(payload))):
            seat = REAL["collect_codex"]()
        self.assertTrue(seat["ok"], seat.get("error"))
        sec = seat["bars"][1]
        self.assertEqual((sec["label"], sec["used_percent"], sec["reset_at"]),
                         ("Secondary window", 95, iso(at_elapsed(94, WEEK))))
        self.assertEqual(sec["reset"], at_elapsed(94, WEEK).astimezone(PT).strftime("%Y-%m-%d %H:%M %Z"))
        self.assertEqual([a["label"] for a in seat["additional_rate_limits"]],
                         ["spark · primary window", "spark · secondary window"])
        cab.add_pacing(seat, NOW)
        self.assertEqual([b["pacing"]["marked"] for b in seat["bars"]], [False, True])
        self.assertEqual([a["pacing"]["marked"] for a in seat["additional_rate_limits"]], [False, True])


class BoundaryTests(unittest.TestCase):
    """Comparisons use unrounded values; rounding is for display only, and the display keeps
    enough decimals to sit on the same side of each line as the value it shows."""

    def test_used_just_above_and_below_the_mark(self):
        for used, want in ((90.01, True), (90.0001, True), (90.0, False), (89.9999, False), (89.99, False)):
            self.assertEqual(cab.pacing(used, at_elapsed(88, WEEK), WEEK, NOW)["marked"], want, used)

    def test_ahead_just_above_and_below_the_mark(self):
        for elapsed, want in ((39.96, True), (39.9999, True), (40, False), (40.0001, False), (40.04, False)):
            p = cab.pacing(55, at_elapsed(elapsed, WEEK), WEEK, NOW)
            self.assertEqual(p["marked"], want, (elapsed, p))
            self.assertEqual(p["mark_reasons"], [AHEAD] if want else [])

    def test_values_are_kept_unrounded(self):
        p = cab.pacing(55, at_elapsed(39.96, WEEK), WEEK, NOW)
        self.assertAlmostEqual(p["elapsed_pct"], 39.96, places=6)
        self.assertAlmostEqual(p["ahead_points"], 15.04, places=6)
        self.assertAlmostEqual(p["ratio"], 55 / 39.96, places=6)
        self.assertNotEqual(p["elapsed_pct"], round(p["elapsed_pct"], 1))

    def test_display_keeps_each_value_on_its_side_of_the_line(self):
        cases = [
            (55, 39.96, "⚑ pacing: 55% used vs 39.96% of window elapsed (1.38× the clock) · 15.04 pts ahead · marked:"),
            (55, 40.04, "pacing: 55% used vs 40% of window elapsed (1.37× the clock) · 15 pts ahead</div>"),
            (90.01, 88, "⚑ pacing: 90.01% used vs 88% of window elapsed (1.02× the clock) · 2.01 pts ahead · marked:"),
            (89.99, 88, "pacing: 90% used vs 88% of window elapsed (1.02× the clock) · 2 pts ahead</div>"),
        ]
        for used, elapsed, want in cases:
            self.assertIn(want, cab.pacing_html(cab.pacing(used, at_elapsed(elapsed, WEEK), WEEK, NOW)))

    def test_ratio_hidden_while_shown_elapsed_is_zero(self):
        html = cab.pacing_html(cab.pacing(6, NOW + timedelta(seconds=WEEK - 1), WEEK, NOW))
        self.assertIn("pacing: 6% used vs 0% of window elapsed · 6 pts ahead</div>", html)

    def test_display_uses_the_fewest_decimals_that_keep_the_side(self):
        # 15.0388 pts ahead needs 2 decimals (15.04) to read as past the 15-point line, not 4
        html = cab.pacing_html(cab.pacing(55, at_elapsed(39.9612, WEEK), WEEK, NOW))
        self.assertIn("55% used vs 39.96% of window elapsed (1.38× the clock) · 15.04 pts ahead · marked:", html)
        self.assertNotIn("15.0388", html)


class KimiBoundaryTests(unittest.TestCase):
    """Collector to pacing: Kimi bars keep their 1-decimal used % for display, status and tone,
    while pacing reads the unrounded share, on the weekly bar and on each limit window."""

    def test_weekly_just_past_90_is_marked(self):
        seat = kimi_paced(999, at_elapsed(88, WEEK))  # 90.01% used, shown as 90.0
        b = seat["bars"][0]
        self.assertEqual((b["used_percent"], b["tone"]), (90.0, "bad"))
        self.assertEqual((seat["status"], seat["chip"], seat["used_percent"]), ("ok", "OK", 90.0))
        self.assertAlmostEqual(b["pacing"]["used_pct"], 90.01, places=9)
        self.assertEqual(b["pacing"]["mark_reasons"], [PAST])

    def test_weekly_just_under_90_is_not_marked(self):
        seat = kimi_paced(1001, at_elapsed(88, WEEK))  # 89.99% used, also shown as 90.0
        b = seat["bars"][0]
        self.assertEqual((b["used_percent"], b["tone"]), (90.0, "bad"))
        self.assertAlmostEqual(b["pacing"]["used_pct"], 89.99, places=9)
        self.assertFalse(b["pacing"]["marked"], b["pacing"])

    def test_limit_window_just_over_15_points_is_marked(self):
        seat = kimi_paced(9000, at_elapsed(10, WEEK), five_h=(4496, at_elapsed(40, FIVE_H)))
        b = seat["bars"][1]  # 55.04% used at 40% elapsed: 15.04 pts ahead; shown as 55.0
        self.assertEqual((b["label"], b["used_percent"]), ("5-hour window", 55.0))
        self.assertEqual(b["pacing"]["mark_reasons"], [AHEAD])

    def test_limit_window_just_under_15_points_is_not_marked(self):
        seat = kimi_paced(9000, at_elapsed(10, WEEK), five_h=(4494, NOW + timedelta(seconds=10785)))
        b = seat["bars"][1]  # 55.06% used at 40.083% elapsed: 14.98 pts ahead; shown as 55.1
        self.assertEqual(b["used_percent"], 55.1)
        self.assertLess(b["pacing"]["ahead_points"], 15)
        self.assertFalse(b["pacing"]["marked"], b["pacing"])

    def test_blocked_status_still_reads_the_rounded_share(self):
        seat = kimi_paced(54, at_elapsed(95, WEEK))  # 99.46% used, shown as 99.5: blocked as before
        self.assertEqual((seat["status"], seat["chip"]), ("blocked_quota", "Limit reached"))
        self.assertEqual(seat["bars"][0]["used_percent"], 99.5)
        self.assertAlmostEqual(seat["bars"][0]["pacing"]["used_pct"], 99.46, places=9)


class MarkingGuardTest(unittest.TestCase):
    """Must fail if the marking rule breaks: strict > on both thresholds, either reason
    alone marks, the sign of "ahead" is used minus elapsed, and the page shows the mark."""

    def test_mark_rule_guard(self):
        table = [
            # used, elapsed %, window, marked?
            (55.0, 40, WEEK, False),   # exactly 15 pts ahead: not marked
            (55.5, 40, WEEK, True),    # 15.5 pts ahead
            (20.0, 40, WEEK, False),   # behind the clock
            (40.0, 60, FIVE_H, False),  # behind, short window
            (80.0, 60, FIVE_H, True),  # 20 pts ahead, short window
            (90.0, 85, WEEK, False),   # exactly 90% used, near pace: not marked
            (90.5, 85, WEEK, True),    # past 90% used
            (100.0, 99.5, WEEK, True),  # at cap on pace
            (16.0, 0, WEEK, True),     # window just started, 16 pts ahead
            (55.0, 39.96, WEEK, True),  # 15.04 pts ahead: compared unrounded
            (55.0, 40.04, WEEK, False),  # 14.96 pts ahead
            (90.01, 88, WEEK, True),   # just past 90% used: compared unrounded
            (89.99, 88, WEEK, False),  # just under
        ]
        for used, elapsed, window, want in table:
            p = cab.pacing(used, at_elapsed(elapsed, window), window, NOW)
            self.assertEqual(p["marked"], want, (used, elapsed, window, p))
            html = cab.pacing_html(p)
            self.assertEqual("metric-pace marked" in html, want, html)
            self.assertEqual(html.count("⚑"), int(want), html)
        self.assertEqual(cab.pacing_flag_html([bar("w", 20, at_elapsed(40, WEEK), WEEK)]), "")
        self.assertIn("⚑", cab.pacing_flag_html([bar("w", 62, at_elapsed(40, WEEK), WEEK)]))


if __name__ == "__main__":
    unittest.main()
