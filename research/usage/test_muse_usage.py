#!/usr/bin/env python3
"""Tests for Muse Code 7-day usage collection + rendering (collect_muse / _collect_muse_usage).

    python3 -m unittest test_muse_usage

Builds a temp session-index.db (sessions schema subset) + fake JSONL session logs
and a fake `muse` binary; never touches the real ~/.local/share/muse, ~/.config/muse,
the network, or the real muse binary.
"""
import json
import os
import sqlite3
import sys
import tempfile
import types
import unittest
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

# test_error_redaction.py (imported later in the prescribed unittest command line)
# replaces cab.collect_muse with a stub at import time, so capture the real one now.
REAL_COLLECT_MUSE = cab.collect_muse

PT = cab.PT
M1 = "muse-spark-1.3-contributor"
M2 = "muse-wonder-full"
U1 = {"input_tokens": 1000, "output_tokens": 500, "cached_tokens": 100,
      "cache_write_tokens": 0, "cache_read_tokens": 50, "reasoning_tokens": 25}
U2 = {"input_tokens": 2000, "output_tokens": 1000, "cached_tokens": 0,
      "cache_write_tokens": 0, "cache_read_tokens": 0, "reasoning_tokens": 0}
U3 = {"input_tokens": 4000, "output_tokens": 2000, "cached_tokens": 7,
      "cache_write_tokens": 0, "cache_read_tokens": 3, "reasoning_tokens": 11}

SCHEMA = """
CREATE TABLE sessions (
  session_id TEXT PRIMARY KEY,
  session_log_path TEXT NOT NULL,
  model_id TEXT,
  msp_model_id TEXT,
  provider_id TEXT,
  created_at_us INTEGER,
  updated_at_us INTEGER,
  prompt_count INTEGER NOT NULL DEFAULT 0,
  status TEXT
)
"""


def us(dt: datetime) -> int:
    return int(dt.timestamp() * 1_000_000)


def noon(day) -> datetime:
    return datetime.combine(day, datetime.min.time(), PT) + timedelta(hours=12)


def mc_line(rec_id, recorded_us, model, usage):
    """A durable record line carrying a model_completed event under payload→event.

    recorded_us=None omits recorded_at (untimestamped event: session-day fallback).
    """
    rec = {
        "schema_version": 1, "id": rec_id, "stream": {"kind": "session", "id": "sess"},
        "record_type": "event",
        "payload_type": "runtime.session",
        "payload": {"kind": "run", "run_id": "run-1",
                    "event": {"kind": "model_completed", "usage": usage,
                              "duration_ms": 42, "finish_reason": "stop", "model": model}},
    }
    if recorded_us is not None:
        rec["recorded_at"] = recorded_us
    return json.dumps(rec)


def prompt_line(rec_id, recorded_us):
    """A runtime.user_intent.accepted record = one timestamped user prompt.

    Mirrors the real log shape (top-level record, recorded_at in µs epoch);
    recorded_us=None omits recorded_at.
    """
    rec = {
        "schema_version": 1, "id": rec_id, "stream": {"kind": "session", "id": "sess"},
        "record_type": "event",
        "payload_type": "runtime.user_intent.accepted",
        "payload": {"intent_id": f"intent-{rec_id}", "surface": "main",
                    "semantic_kind": {"kind": "chat"}},
    }
    if recorded_us is not None:
        rec["recorded_at"] = recorded_us
    return json.dumps(rec)


def attribution_line(rec_id, recorded_us, usage):
    """goal_usage_attribution re-reports the same usage — must never be double counted."""
    return json.dumps({
        "schema_version": 1, "id": rec_id, "stream": {"kind": "session", "id": "sess"},
        "recorded_at": recorded_us, "record_type": "event",
        "payload_type": "runtime.session",
        "payload": {"kind": "run", "run_id": "run-1",
                    "event": {"kind": "goal_usage_attribution",
                              "record": {"schema_version": 1, "usage_family": "provider",
                                         "quantity": {"unit": "tokens", "reported": True, **usage}}}},
    })


def frame_line(inner_record_json: str):
    """retained_frame wrapping a whole record as an escaped JSON string in record_json."""
    return json.dumps({"retained_frame": "session_permission_transaction",
                       "children": [{"child_index": 0, "record_json": inner_record_json}]})


class MuseUsageTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.root = root
        self.share = root / "share"
        self.share.mkdir()
        self.cfg = root / "cfg"
        self.cfg.mkdir()
        self.today = cab.now_pt().date()
        self.yesterday = self.today - timedelta(days=1)
        now_us = us(cab.now_pt())

        logs = root / "logs"
        logs.mkdir()
        self.logs = logs
        log_a = logs / "a.jsonl"
        rec_a1 = mc_line("rec-a1", us(noon(self.today)), M1, U1)
        log_a.write_text("\n".join([
            json.dumps({"id": "meta-1", "record_type": "event", "recorded_at": now_us,
                        "payload": {"kind": "metadata", "record": {"model_id": M1}}}),
            prompt_line("prompt-a1", us(noon(self.today))),
            rec_a1,
            attribution_line("attr-1", us(noon(self.today)), U1),  # dup of rec-a1's usage
            '{"id":"bad-1","record_type":"event","event":{"kind":"model_completed", BROKEN',
            prompt_line("prompt-a2", us(noon(self.today))),
            mc_line("rec-a2", us(noon(self.today)), M2, U2),
            frame_line(rec_a1),  # same record embedded in a frame: dedupe by record id
            frame_line(prompt_line("prompt-a1", us(noon(self.today)))),  # prompt dup in a frame
            "",
        ]))
        log_b = logs / "b.jsonl"
        log_b.write_text("\n".join([
            prompt_line("prompt-b1", us(noon(self.yesterday))),
            mc_line("rec-b1", us(noon(self.yesterday)), M2, U3),
            prompt_line("prompt-b2", us(noon(self.yesterday))),
            "",
        ]))
        log_c = logs / "c.jsonl"  # out-of-window session: must never be scanned
        log_c.write_text(mc_line("rec-c1", us(noon(self.today - timedelta(days=8))), M1,
                                 {"input_tokens": 999999, "output_tokens": 999999}) + "\n")
        missing_log = logs / "nope" / "d.jsonl"

        self.db = self.share / "session-index.db"
        con = sqlite3.connect(self.db)
        con.execute(SCHEMA)
        rows = [
            ("sess-a", str(log_a), M1, 2, now_us),
            ("sess-b", str(log_b), M2, 2, us(noon(self.yesterday))),
            ("sess-c", str(log_c), M1, 9, us(noon(self.today - timedelta(days=8)))),
            ("sess-d", str(missing_log), M1, 1, now_us),
        ]
        con.executemany(
            "INSERT INTO sessions (session_id, session_log_path, model_id, msp_model_id,"
            " provider_id, created_at_us, updated_at_us, prompt_count, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [(sid, lp, mid, "", "meta", upd, upd, pc, "valid") for sid, lp, mid, pc, upd in rows],
        )
        con.commit()
        con.close()

        self.muse_bin = root / "bin" / "muse"
        self.muse_bin.parent.mkdir()
        self.muse_bin.write_text('#!/bin/sh\necho "muse 9.9.9-test"\n')
        self.muse_bin.chmod(0o755)
        self.auth = self.cfg / "auth.json"
        self.auth.write_text(json.dumps({"providers": {"meta": {"mechanism": "oauth-test"}}}))
        self.settings = self.cfg / "settings.json"
        self.settings.write_text(json.dumps({"reasoning_effort": "max"}))

    def tearDown(self):
        self.tmp.cleanup()

    def collect(self, **kw):
        args = dict(share_dir=self.share, settings_path=self.settings,
                    muse_bin=self.muse_bin, auth_path=self.auth)
        args.update(kw)
        return REAL_COLLECT_MUSE(**args)

    def write_log(self, name, lines):
        d = self.root / "extra-logs"
        d.mkdir(exist_ok=True)
        p = d / name
        p.write_text("\n".join(lines) + "\n")
        return p

    def make_share(self, name, sessions):
        """Extra share dir with its own index. sessions: (sid, log_path, model, prompts, created_us, updated_us)."""
        share = self.root / name
        share.mkdir(exist_ok=True)
        con = sqlite3.connect(share / "session-index.db")
        con.execute(SCHEMA)
        con.executemany(
            "INSERT INTO sessions (session_id, session_log_path, model_id, msp_model_id,"
            " provider_id, created_at_us, updated_at_us, prompt_count, status)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            [(sid, str(lp), mid, "", "meta", created, updated, pc, "valid")
             for sid, lp, mid, pc, created, updated in sessions],
        )
        con.commit()
        con.close()
        return share

    def test_collect_full_pipeline(self):
        out = self.collect()
        self.assertTrue(out["ok"], out)
        self.assertEqual(out["cli_version"], "muse 9.9.9-test")
        self.assertEqual(out["auth_mechanism"], "oauth-test")
        u = out["usage"]
        self.assertNotIn("usage_error", u, u)
        self.assertEqual(u["plan"], "Max")
        self.assertIsNone(u["limit"])
        self.assertIsNone(u["reset"])
        self.assertEqual(u["limit_note"], "not exposed by Muse CLI")
        self.assertEqual(u["sessions_in_window"], 3)  # sess-c (8d ago) excluded
        self.assertEqual(u["logs_scanned"], 2)
        self.assertEqual(u["logs_missing"], 1)
        self.assertEqual(u["logs_skipped_large"], 0)
        self.assertEqual(u["malformed_lines"], 1)
        # sess-d's log is missing: the scan is incomplete and must say so
        self.assertTrue(u["partial"], u)
        self.assertIn("missing", u.get("usage_note", ""), u)
        self.assertFalse(u.get("prompts_approximate"), u)

        days = {d["date"]: d for d in u["days"]}
        self.assertEqual(len(days), 7)
        self.assertEqual(sorted(days)[0], (self.today - timedelta(days=6)).isoformat())
        t = days[self.today.isoformat()]
        # Only sess-a has observed activity today (sess-d's log is missing, so it
        # contributes no session/prompt counts). Sessions/prompts come from
        # timestamped model_completed / user_intent events; tokens from a's two
        # model_completed events only (attribution + frame dups excluded).
        self.assertEqual((t["sessions"], t["prompts"]), (1, 2))
        self.assertEqual((t["input_tokens"], t["output_tokens"]), (3000, 1500))
        self.assertEqual((t["cached_tokens"], t["reasoning_tokens"]), (150, 25))
        self.assertEqual(t["models"], {M1: 1500, M2: 3000})
        y = days[self.yesterday.isoformat()]
        self.assertEqual((y["sessions"], y["prompts"]), (1, 2))
        self.assertEqual((y["input_tokens"], y["output_tokens"]), (4000, 2000))
        self.assertEqual((y["cached_tokens"], y["reasoning_tokens"]), (10, 11))

        self.assertEqual(u["totals"], {"sessions": 2, "prompts": 4, "input_tokens": 7000,
                                       "output_tokens": 3500, "cached_tokens": 160,
                                       "reasoning_tokens": 36})
        self.assertEqual(u["today"]["input_tokens"], 3000)
        self.assertEqual(u["today"]["output_tokens"], 1500)
        self.assertEqual(u["by_model"], {M2: 9000, M1: 1500})
        self.assertEqual(next(iter(u["by_model"])), M2)  # sorted desc
        # model = most-used in last 7d when settings.json has no "model"
        self.assertEqual(out["model"], M2)
        self.assertEqual(out["model_source"], "session logs (7d most-used)")

    def test_settings_model_override(self):
        self.settings.write_text(json.dumps({"model": "muse-wonder-1.0", "reasoning_effort": "max"}))
        out = self.collect()
        self.assertEqual(out["model"], "muse-wonder-1.0")
        self.assertEqual(out["model_source"], "settings.json")
        self.assertEqual(out["reasoning_effort"], "max")

    def test_missing_db_degrades(self):
        empty = Path(self.tmp.name) / "empty-share"
        empty.mkdir()
        out = self.collect(share_dir=empty)
        u = out["usage"]
        self.assertEqual(u["usage_error"], "session-index.db not found")
        self.assertEqual(out["usage_error"], "session-index.db not found")
        self.assertEqual(len(u["days"]), 7)
        self.assertEqual(u["totals"]["input_tokens"], 0)
        self.assertEqual(u["plan"], "Max")
        # A DB failure must render as incomplete, never as clean zeros.
        self.assertTrue(u["partial"], u)
        self.assertTrue(u.get("usage_note"), u)
        self.assertTrue(out["ok"])  # version + auth still fine

    def test_corrupt_db_degrades(self):
        self.db.write_bytes(b"this is not a sqlite database at all" * 4)
        out = self.collect()
        self.assertIn("usage_error", out["usage"])
        self.assertTrue(out["usage"]["partial"], out["usage"])
        self.assertTrue(out["usage"].get("usage_note"), out["usage"])
        self.assertTrue(out["ok"])

    def test_locked_db_retries_then_degrades(self):
        hold = sqlite3.connect(self.db, isolation_level=None)
        hold.execute("BEGIN EXCLUSIVE")
        try:
            u = cab._collect_muse_usage(self.share)
        finally:
            hold.close()
        self.assertIn("locked", u.get("usage_error", ""), u)
        self.assertTrue(u["partial"], u)
        self.assertTrue(u.get("usage_note"), u)
        self.assertEqual(u["totals"]["input_tokens"], 0)

    def test_time_budget_marks_partial(self):
        orig = cab.MUSE_USAGE_TIME_BUDGET_S
        cab.MUSE_USAGE_TIME_BUDGET_S = 0
        try:
            u = cab._collect_muse_usage(self.share)
        finally:
            cab.MUSE_USAGE_TIME_BUDGET_S = orig
        self.assertTrue(u["partial"], u)
        self.assertIn("time budget", u.get("usage_note", ""), u)
        self.assertNotIn("usage_error", u, u)

    def test_large_files_skipped(self):
        orig = cab.MUSE_USAGE_MAX_FILE_BYTES
        cab.MUSE_USAGE_MAX_FILE_BYTES = 50  # every log is "large"
        try:
            u = cab._collect_muse_usage(self.share)
        finally:
            cab.MUSE_USAGE_MAX_FILE_BYTES = orig
        self.assertEqual(u["logs_skipped_large"], 2)
        self.assertEqual(u["logs_scanned"], 0)
        self.assertEqual(u["totals"]["input_tokens"], 0)
        # No log could be read, so no activity was observed: counts stay 0 and
        # the scan reports itself incomplete instead of looking complete.
        self.assertEqual(u["totals"]["sessions"], 0)
        self.assertEqual(u["totals"]["prompts"], 0)
        self.assertEqual(u["sessions_in_window"], 3)  # index rows still reported
        self.assertTrue(u["partial"], u)
        self.assertIn("skipped", u.get("usage_note", ""), u)

    def test_render_html_includes_muse_usage(self):
        out = self.collect()
        snap = {
            "refreshed_at": "2026-10-12 14:00:00 PDT",
            "claude": {}, "codex": {}, "kimi": {}, "agy": {},
            "muse": out, "dsh": {}, "routine_proxy": {}, "grok": {},
        }
        html = cab.render_html(snap)
        self.assertIn('<section class="card" id="muse">', html)
        self.assertIn(">MAX</div>", html)  # chip shows the plan
        self.assertIn("plan <strong>Max</strong>", html)
        self.assertIn("not exposed by Muse CLI", html)
        self.assertIn(self.today.isoformat(), html)  # per-day table row
        self.assertIn("3,000", html)  # today's input tokens
        self.assertIn(self.yesterday.isoformat(), html)
        self.assertIn("muse-wonder-full <strong>9,000</strong>", html)  # by-model line
        # sess-d's missing log: partial reason is visible in the card
        self.assertIn("PARTIAL", html)
        self.assertIn("Usage incomplete", html)
        self.assertIn("session log(s) missing", html)

    def test_render_html_without_usage(self):
        # old-style payload (no usage key) must still render the card
        snap = {
            "refreshed_at": "2026-10-12 14:00:00 PDT",
            "claude": {}, "codex": {}, "kimi": {}, "agy": {},
            "muse": {"ok": True, "cli_version": "1.4.6", "model": M1}, "dsh": {},
            "routine_proxy": {}, "grok": {},
        }
        html = cab.render_html(snap)
        self.assertIn('<section class="card" id="muse">', html)
        self.assertIn("AUTH OK", html)

    def test_boundary_spanning_session_excludes_old_events(self):
        # P1 regression: a session resumed today must not dump its pre-window
        # tokens/prompts onto today. Events with valid timestamps outside the
        # 7-day window are excluded; untimestamped events fall back to the
        # session's updated day.
        start_day = self.today - timedelta(days=6)
        just_before = self.today - timedelta(days=7)
        tiny = {"input_tokens": 0, "output_tokens": 0}
        log = self.write_log("boundary.jsonl", [
            prompt_line("bp-old", us(noon(just_before))),
            mc_line("bm-old", us(noon(just_before)), M1, {**tiny, "input_tokens": 10000}),
            prompt_line("bp-start", us(noon(start_day))),
            mc_line("bm-start", us(noon(start_day)), M1, {**tiny, "input_tokens": 300}),
            prompt_line("bp-today", us(noon(self.today))),
            mc_line("bm-today", us(noon(self.today)), M1, {**tiny, "input_tokens": 200}),
            mc_line("bm-nots", None, M1, {**tiny, "input_tokens": 50}),  # no timestamp
        ])
        share = self.make_share("boundary-share", [
            ("sess-boundary", log, M1, 99,
             us(noon(self.today - timedelta(days=20))), us(noon(self.today))),
        ])
        u = cab._collect_muse_usage(share)
        self.assertNotIn("usage_error", u, u)
        self.assertFalse(u["partial"], u)
        self.assertEqual(u.get("events_out_of_window"), 2, u)  # old model + old prompt
        days = {d["date"]: d for d in u["days"]}
        first = days[start_day.isoformat()]
        self.assertEqual((first["sessions"], first["prompts"], first["input_tokens"]), (1, 1, 300))
        t = days[self.today.isoformat()]
        self.assertEqual((t["sessions"], t["prompts"], t["input_tokens"]), (1, 1, 250))
        self.assertEqual(u["totals"]["input_tokens"], 550)  # never 10,550
        self.assertEqual(u["totals"]["prompts"], 2)  # never the lifetime 99
        self.assertEqual(u["totals"]["sessions"], 1)

    def test_multi_day_session_counts_each_active_day(self):
        # P2: one session active on two days counts on both days (totals count
        # it once); prompts come from timestamped user_intent events, not the
        # lifetime index prompt_count (99 here).
        d2 = self.today - timedelta(days=2)
        tiny = {"input_tokens": 0, "output_tokens": 0}
        log = self.write_log("multi.jsonl", [
            prompt_line("mp-old", us(noon(self.today - timedelta(days=9)))),
            mc_line("mm-old", us(noon(self.today - timedelta(days=9))), M1,
                    {**tiny, "input_tokens": 9999}),
            prompt_line("mp-1", us(noon(d2))),
            mc_line("mm-1", us(noon(d2)), M1, {**tiny, "input_tokens": 100}),
            prompt_line("mp-2", us(noon(self.today))),
            prompt_line("mp-3", us(noon(self.today))),
            mc_line("mm-2", us(noon(self.today)), M1, {**tiny, "input_tokens": 200}),
            mc_line("mm-3", us(noon(self.today)), M1, {**tiny, "input_tokens": 300}),
        ])
        share = self.make_share("multi-share", [
            ("sess-multi", log, M1, 99,
             us(noon(self.today - timedelta(days=3))), us(noon(self.today))),
        ])
        u = cab._collect_muse_usage(share)
        days = {d["date"]: d for d in u["days"]}
        a = days[d2.isoformat()]
        self.assertEqual((a["sessions"], a["prompts"], a["input_tokens"]), (1, 1, 100))
        t = days[self.today.isoformat()]
        self.assertEqual((t["sessions"], t["prompts"], t["input_tokens"]), (1, 2, 500))
        self.assertEqual(sum(d["sessions"] for d in u["days"]), 2)  # session-days
        self.assertEqual(u["totals"]["sessions"], 1)  # distinct sessions
        self.assertEqual(u["totals"]["prompts"], 3)
        self.assertEqual(u["totals"]["input_tokens"], 600)
        self.assertFalse(u["partial"], u)

    def test_prompt_fallback_without_intent_events(self):
        # Logs with no user_intent events: lifetime prompt_count is used only
        # when the session provably started inside the window, spread over its
        # model-activity days pro rata; pre-window sessions contribute none.
        tiny = {"input_tokens": 10, "output_tokens": 0}
        log_multi = self.write_log("fb-multi.jsonl", [
            mc_line("f1", us(noon(self.yesterday)), M1, tiny),
            mc_line("f2", us(noon(self.yesterday)), M1, tiny),
            mc_line("f3", us(noon(self.yesterday)), M1, tiny),
            mc_line("f4", us(noon(self.today)), M1, tiny),
        ])
        log_single = self.write_log("fb-single.jsonl", [
            mc_line("f5", us(noon(self.today)), M1, {"input_tokens": 20, "output_tokens": 0}),
        ])
        log_old = self.write_log("fb-old.jsonl", [
            mc_line("f6", us(noon(self.today)), M1, {"input_tokens": 30, "output_tokens": 0}),
        ])
        share = self.make_share("fallback-share", [
            ("fb-multi", log_multi, M1, 4, us(noon(self.yesterday)), us(noon(self.today))),
            ("fb-single", log_single, M1, 2, us(noon(self.today)), us(noon(self.today))),
            ("fb-old", log_old, M1, 50,
             us(noon(self.today - timedelta(days=20))), us(noon(self.today))),
        ])
        u = cab._collect_muse_usage(share)
        days = {d["date"]: d for d in u["days"]}
        y = days[self.yesterday.isoformat()]
        self.assertEqual((y["sessions"], y["prompts"]), (1, 3))  # 3/4 of fb-multi's 4
        t = days[self.today.isoformat()]
        self.assertEqual((t["sessions"], t["prompts"]), (3, 3))  # 1 (fb-multi) + 2 + 0 (fb-old)
        self.assertEqual(u["totals"]["prompts"], 6)  # fb-old's 50 never attributed
        self.assertEqual(u["totals"]["input_tokens"], 90)
        self.assertTrue(u.get("prompts_approximate"), u)
        self.assertTrue(u.get("prompts_note"), u)

    def test_slow_clock_between_files_marks_partial(self):
        # P2: a clock racing past the 20s budget across a handful of tiny
        # files must still yield partial:true (between-files deadline checks).
        state = {"t": 0.0}

        def fake_monotonic():
            state["t"] += 10.0
            return state["t"]

        real_time = cab.time
        cab.time = types.SimpleNamespace(monotonic=fake_monotonic, sleep=real_time.sleep)
        try:
            u = cab._collect_muse_usage(self.share)
        finally:
            cab.time = real_time
        self.assertTrue(u["partial"], u)
        self.assertIn("time budget", u.get("usage_note", ""), u)

    def test_slow_clock_within_file_marks_partial(self):
        # P2: inside one file the deadline is checked on every line, so a
        # clock that jumps after the scan starts truncates the file (the
        # model event at the end is never counted).
        filler = [json.dumps({"id": f"fill-{i}", "payload": {"kind": "metadata"}})
                  for i in range(2500)]
        log = self.write_log("long.jsonl", filler + [
            mc_line("late-1", us(noon(self.today)), M1,
                    {"input_tokens": 777, "output_tokens": 0}),
        ])
        share = self.make_share("long-share", [
            ("sess-long", log, M1, 1, us(noon(self.today)), us(noon(self.today))),
        ])
        calls = {"n": 0}

        def fake_monotonic():
            calls["n"] += 1
            return 0.0 if calls["n"] <= 2 else 9999.0  # deadline set + pre-file check pass

        real_time = cab.time
        cab.time = types.SimpleNamespace(monotonic=fake_monotonic, sleep=real_time.sleep)
        try:
            u = cab._collect_muse_usage(share)
        finally:
            cab.time = real_time
        self.assertTrue(u["partial"], u)
        self.assertIn("time budget", u.get("usage_note", ""), u)
        self.assertEqual(u["totals"]["input_tokens"], 0, u)

    def test_missing_log_marks_partial_with_note(self):
        # P2: missing logs make the scan partial with a visible reason, while
        # readable sessions still count.
        log = self.write_log("good.jsonl", [
            prompt_line("gp-1", us(noon(self.today))),
            mc_line("gm-1", us(noon(self.today)), M1,
                    {"input_tokens": 100, "output_tokens": 0}),
        ])
        share = self.make_share("missing-share", [
            ("sess-good", log, M1, 1, us(noon(self.today)), us(noon(self.today))),
            ("sess-gone", self.root / "extra-logs" / "gone.jsonl", M1, 7,
             us(noon(self.today)), us(noon(self.today))),
        ])
        u = cab._collect_muse_usage(share)
        self.assertTrue(u["partial"], u)
        self.assertIn("missing", u.get("usage_note", ""), u)
        self.assertEqual(u["logs_missing"], 1)
        self.assertEqual(u["totals"]["input_tokens"], 100)
        self.assertEqual(u["totals"]["prompts"], 1)  # gone session's 7 not invented
        self.assertEqual(u["totals"]["sessions"], 1)

    def test_quoted_model_completed_in_tool_output_not_counted(self):
        # R2-P2: JSON text quoted inside tool output (or any other string)
        # is not usage. Only retained-frame record_json strings are decoded;
        # a distinct frame-only record must still count.
        noon_today = noon(self.today)
        quoted_mc = mc_line("q-quoted", us(noon_today), M1,
                            {"input_tokens": 9000, "output_tokens": 900})
        quoted_mc2 = mc_line("q-quoted2", us(noon_today), M1,
                             {"input_tokens": 5000, "output_tokens": 0})
        quoted_prompt = prompt_line("qp-quoted", us(noon_today))
        log = self.write_log("quoted.jsonl", [
            prompt_line("qp-real", us(noon_today)),
            mc_line("q-real", us(noon_today), M1,
                    {"input_tokens": 200, "output_tokens": 10}),
            frame_line(mc_line("q-frame", us(noon_today), M1,
                               {"input_tokens": 100, "output_tokens": 5})),
            frame_line(prompt_line("qp-frame", us(noon_today))),
            json.dumps({"id": "tool-1", "record_type": "event",
                        "recorded_at": us(noon_today),
                        "payload": {"kind": "tool_result", "output": quoted_mc}}),
            json.dumps({"id": "tool-2", "record_type": "event",
                        "recorded_at": us(noon_today),
                        "payload": {"kind": "tool_result",
                                    "stdout_lines": [quoted_mc2]}}),
            json.dumps({"id": "tool-3", "record_type": "event",
                        "recorded_at": us(noon_today),
                        "payload": {"kind": "tool_result",
                                    "output": quoted_prompt}}),
        ])
        share = self.make_share("quoted-share", [
            ("sess-q", log, M1, 7, us(noon_today), us(noon_today)),
        ])
        u = cab._collect_muse_usage(share)
        # Real 200 + frame-only 100; the quoted 9000/5000 events are nothing.
        self.assertEqual(u["totals"]["input_tokens"], 300, u)
        self.assertEqual(u["totals"]["output_tokens"], 15, u)
        self.assertEqual(u["totals"]["prompts"], 2, u)  # qp-real + qp-frame
        self.assertEqual(u["by_model"], {M1: 315}, u)
        self.assertFalse(u["partial"], u)

    def test_prompt_fallback_requires_in_window_created(self):
        # R2-P2: the lifetime prompt_count fallback needs a valid in-window
        # created_at_us. Null/missing creation contributes zero and is
        # flagged approximate with a note, never the lifetime total.
        noon_today = noon(self.today)
        log_null = self.write_log("fb-null.jsonl", [
            mc_line("fn-1", us(noon_today), M1, {"input_tokens": 40, "output_tokens": 0}),
        ])
        log_zero = self.write_log("fb-zero.jsonl", [
            mc_line("fz-1", us(noon_today), M1, {"input_tokens": 10, "output_tokens": 0}),
        ])
        share = self.make_share("fb-unknown-share", [
            ("fb-null", log_null, M1, 99, None, us(noon_today)),
            ("fb-zero", log_zero, M1, 42, 0, us(noon_today)),
        ])
        u = cab._collect_muse_usage(share)
        self.assertEqual(u["totals"]["prompts"], 0, u)  # not 99 + 42
        self.assertEqual(u["totals"]["input_tokens"], 50, u)
        self.assertTrue(u.get("prompts_approximate"), u)
        self.assertTrue(u.get("prompts_note"), u)
        self.assertIn("created", u.get("prompts_note", "").lower(), u)

        # Same when the index schema has no created_at_us column at all.
        log_nc = self.write_log("fb-nocol.jsonl", [
            mc_line("nc-1", us(noon_today), M1, {"input_tokens": 50, "output_tokens": 0}),
        ])
        share2 = self.root / "fb-nocol-share"
        share2.mkdir()
        con = sqlite3.connect(share2 / "session-index.db")
        con.execute(
            "CREATE TABLE sessions (session_id TEXT PRIMARY KEY,"
            " session_log_path TEXT NOT NULL, model_id TEXT,"
            " updated_at_us INTEGER, prompt_count INTEGER NOT NULL DEFAULT 0)"
        )
        con.execute(
            "INSERT INTO sessions VALUES (?,?,?,?,?)",
            ("fb-nocol", str(log_nc), M1, us(noon_today), 99),
        )
        con.commit()
        con.close()
        u2 = cab._collect_muse_usage(share2)
        self.assertNotIn("usage_error", u2, u2)
        self.assertEqual(u2["totals"]["prompts"], 0, u2)
        self.assertEqual(u2["totals"]["input_tokens"], 50, u2)
        self.assertTrue(u2.get("prompts_approximate"), u2)
        self.assertIn("created", u2.get("prompts_note", "").lower(), u2)

    def test_malformed_model_completed_line_marks_partial(self):
        # R2-P2: a malformed line containing model_completed is a skipped
        # usage record: partial + named in the rendered usage_note, even
        # when every log file exists and reads fine.
        noon_today = noon(self.today)
        log = self.write_log("malformed.jsonl", [
            prompt_line("mp-1", us(noon_today)),
            mc_line("mm-1", us(noon_today), M1,
                    {"input_tokens": 120, "output_tokens": 6}),
            '{"id":"bad-2","record_type":"event","event":{"kind":"model_completed", BROKEN',
        ])
        share = self.make_share("malformed-share", [
            ("sess-m", log, M1, 1, us(noon_today), us(noon_today)),
        ])
        out = self.collect(share_dir=share)
        u = out["usage"]
        self.assertEqual(u["totals"]["input_tokens"], 120, u)
        self.assertEqual(u["logs_missing"], 0, u)
        self.assertEqual(u["malformed_lines"], 1, u)
        self.assertTrue(u["partial"], u)
        self.assertIn("malformed", u.get("usage_note", "").lower(), u)
        snap = {
            "refreshed_at": "2026-10-12 14:00:00 PDT",
            "claude": {}, "codex": {}, "kimi": {}, "agy": {},
            "muse": out, "dsh": {}, "routine_proxy": {}, "grok": {},
        }
        html = cab.render_html(snap)
        self.assertIn("PARTIAL", html)
        self.assertIn("Usage incomplete", html)
        self.assertIn("malformed", html.lower())

    def test_malformed_prompt_line_marks_partial(self):
        # R3-P2: a malformed top-level line carrying only a prompt marker is
        # a skipped prompt record: partial + named in usage_note, not a
        # silent undercount with partial False.
        noon_today = noon(self.today)
        log = self.write_log("badprompt.jsonl", [
            prompt_line("bp-good", us(noon_today)),
            mc_line("bp-m1", us(noon_today), M1,
                    {"input_tokens": 90, "output_tokens": 9}),
            '{"payload_type":"runtime.user_intent.accepted","id": BROKEN',
        ])
        share = self.make_share("badprompt-share", [
            ("sess-bp", log, M1, 1, us(noon_today), us(noon_today)),
        ])
        u = cab._collect_muse_usage(share)
        self.assertNotIn("usage_error", u, u)
        self.assertEqual(u["totals"]["input_tokens"], 90, u)
        self.assertEqual(u["totals"]["prompts"], 1, u)
        self.assertEqual(u["malformed_lines"], 1, u)
        self.assertEqual(u.get("malformed_prompt_lines"), 1, u)
        self.assertTrue(u["partial"], u)
        self.assertIn("malformed", u.get("usage_note", "").lower(), u)

    def test_malformed_retained_frame_marks_partial(self):
        # R3-P2: retained-frame record_json strings that fail to parse are
        # skipped records (usage and prompt alike): each must surface as
        # partial + a usage_note reason rendered on the card.
        noon_today = noon(self.today)
        log = self.write_log("badframe.jsonl", [
            prompt_line("bf-good-p", us(noon_today)),
            mc_line("bf-good-m", us(noon_today), M1,
                    {"input_tokens": 80, "output_tokens": 8}),
            frame_line('{"kind":"model_completed","usage": BROKEN'),
            frame_line('{"payload_type":"runtime.user_intent.accepted", BROKEN'),
        ])
        share = self.make_share("badframe-share", [
            ("sess-bf", log, M1, 1, us(noon_today), us(noon_today)),
        ])
        out = self.collect(share_dir=share)
        u = out["usage"]
        self.assertNotIn("usage_error", u, u)
        self.assertEqual(u["totals"]["input_tokens"], 80, u)
        self.assertEqual(u["totals"]["prompts"], 1, u)
        self.assertEqual(u.get("malformed_frame_records"), 2, u)
        self.assertTrue(u["partial"], u)
        self.assertIn("retained-frame", u.get("usage_note", ""), u)
        snap = {
            "refreshed_at": "2026-10-12 14:00:00 PDT",
            "claude": {}, "codex": {}, "kimi": {}, "agy": {},
            "muse": out, "dsh": {}, "routine_proxy": {}, "grok": {},
        }
        html = cab.render_html(snap)
        self.assertIn("PARTIAL", html)
        self.assertIn("Usage incomplete", html)
        self.assertIn("retained-frame", html)

    def test_ro_open_failure_falls_back_to_copy(self):
        # Round-3 critical: when the read-only open fails (system python +
        # WAL index: "unable to open database file"), the collector copies
        # db + -wal/-shm to a temp dir, reads the copy, returns correct
        # totals, and never writes to the original files.
        noon_today = noon(self.today)
        log = self.write_log("fallback.jsonl", [
            prompt_line("fb-p1", us(noon_today)),
            mc_line("fb-m1", us(noon_today), M1,
                    {"input_tokens": 321, "output_tokens": 21}),
        ])
        share = self.root / "fallback-share"
        share.mkdir()
        db = share / "session-index.db"
        con = sqlite3.connect(db)
        con.execute("PRAGMA journal_mode=WAL")
        con.execute(SCHEMA)
        con.execute(
            "INSERT INTO sessions (session_id, session_log_path, model_id,"
            " msp_model_id, provider_id, created_at_us, updated_at_us,"
            " prompt_count, status) VALUES (?,?,?,?,?,?,?,?,?)",
            ("sess-fb", str(log), M1, "", "meta",
             us(noon_today), us(noon_today), 1, "valid"),
        )
        con.commit()
        # WAL files are live while the writer connection stays open; the
        # committed row may exist only in -wal, so the copy must include it.
        self.assertTrue(Path(str(db) + "-wal").exists())
        before = db.read_bytes()
        real_connect = cab.sqlite3.connect

        def fake_connect(database, *a, **kw):
            if isinstance(database, str) and "mode=ro" in database:
                raise sqlite3.OperationalError("unable to open database file")
            return real_connect(database, *a, **kw)

        cab.sqlite3.connect = fake_connect
        try:
            u = cab._collect_muse_usage(share)
            after = db.read_bytes()
        finally:
            cab.sqlite3.connect = real_connect
            con.close()
        self.assertNotIn("usage_error", u, u)
        self.assertEqual(u["totals"]["input_tokens"], 321, u)
        self.assertEqual(u["totals"]["output_tokens"], 21, u)
        self.assertEqual(u["totals"]["prompts"], 1, u)
        self.assertFalse(u["partial"], u)
        self.assertEqual(after, before)  # original db untouched

    def test_db_failure_after_fallback_marks_partial_and_renders(self):
        # Round-3: if the copy fallback also fails, the payload is partial
        # with a usage_note reason and the card shows PARTIAL + the reason
        # instead of plain zeros.
        noon_today = noon(self.today)
        log = self.write_log("dbfail.jsonl", [
            mc_line("df-m1", us(noon_today), M1,
                    {"input_tokens": 111, "output_tokens": 0}),
        ])
        share = self.make_share("dbfail-share", [
            ("sess-df", log, M1, 1, us(noon_today), us(noon_today)),
        ])
        real_connect = cab.sqlite3.connect

        def always_fail(database, *a, **kw):
            raise sqlite3.OperationalError("unable to open database file")

        cab.sqlite3.connect = always_fail
        try:
            out = self.collect(share_dir=share)
        finally:
            cab.sqlite3.connect = real_connect
        u = out["usage"]
        self.assertIn("unable to open", u.get("usage_error", ""), u)
        self.assertTrue(u["partial"], u)
        self.assertIn("could not be read", u.get("usage_note", ""), u)
        self.assertEqual(u["totals"]["input_tokens"], 0, u)
        snap = {
            "refreshed_at": "2026-10-12 14:00:00 PDT",
            "claude": {}, "codex": {}, "kimi": {}, "agy": {},
            "muse": out, "dsh": {}, "routine_proxy": {}, "grok": {},
        }
        html = cab.render_html(snap)
        self.assertIn("PARTIAL", html)
        self.assertIn("Usage incomplete", html)
        self.assertIn("could not be read", html)

    def test_slow_reads_stop_early_within_short_file(self):
        # R3-P2: slow reads must stop at the deadline even in a short file.
        # Each line read advances the fake clock 2 s (30 lines = 60 s of
        # reads against the 20 s budget); the scan must stop after ~10
        # lines instead of running to EOF counting everything.
        noon_today = noon(self.today)
        lines = [
            mc_line("slow-%d" % i, us(noon_today), M1,
                    {"input_tokens": 100, "output_tokens": 0})
            for i in range(30)
        ]
        log = self.write_log("slow.jsonl", lines)
        share = self.make_share("slowread-share", [
            ("sess-slow", log, M1, 0, us(noon_today), us(noon_today)),
        ])
        state = {"t": 0.0, "yielded": 0}
        real_open = open
        real_time = cab.time
        target = str(log)

        class SlowLines:
            def __init__(self, all_lines):
                self._it = iter(all_lines)

            def __enter__(self):
                return self

            def __exit__(self, *exc):
                return False

            def __iter__(self):
                return self

            def __next__(self):
                line = next(self._it)
                state["t"] += 2.0
                state["yielded"] += 1
                return line

        def fake_open(path, *a, **kw):
            if str(path) == target:
                with real_open(path, *a, **kw) as fh:
                    return SlowLines(fh.readlines())
            return real_open(path, *a, **kw)

        cab.open = fake_open
        cab.time = types.SimpleNamespace(
            monotonic=lambda: state["t"], sleep=real_time.sleep)
        try:
            u = cab._collect_muse_usage(share)
        finally:
            del cab.open
            cab.time = real_time
        self.assertTrue(u["partial"], u)
        self.assertIn("time budget", u.get("usage_note", ""), u)
        self.assertLess(state["yielded"], 30, state)  # stopped before EOF
        self.assertLessEqual(state["yielded"], 12, state)
        self.assertGreater(u["totals"]["input_tokens"], 0, u)
        self.assertLess(u["totals"]["input_tokens"], 3000, u)  # not all 30

    def test_slow_reads_stop_early_on_lines_without_markers(self):
        # The per-line deadline also covers lines the marker filter skips: 30 slow
        # metadata lines (2 s each) must stop the scan inside the filler, so the
        # model event after them is never counted.
        noon_today = noon(self.today)
        filler = [json.dumps({"id": "fill-%d" % i, "payload": {"kind": "metadata"}})
                  for i in range(30)]
        log = self.write_log("slow-filler.jsonl", filler + [
            mc_line("late-m", us(noon_today), M1, {"input_tokens": 100, "output_tokens": 0}),
        ])
        share = self.make_share("slowfiller-share", [
            ("sess-filler", log, M1, 0, us(noon_today), us(noon_today)),
        ])
        state = {"t": 0.0, "yielded": 0}
        real_open = open
        real_time = cab.time

        def slow_lines(all_lines):
            for line in all_lines:
                state["t"] += 2.0
                state["yielded"] += 1
                yield line

        class SlowFile:
            def __init__(self, all_lines):
                self._lines = slow_lines(all_lines)

            def __enter__(self):
                return self._lines

            def __exit__(self, *exc):
                return False

        def fake_open(path, *a, **kw):
            if str(path) == str(log):
                with real_open(path, *a, **kw) as fh:
                    return SlowFile(fh.readlines())
            return real_open(path, *a, **kw)

        cab.open = fake_open
        cab.time = types.SimpleNamespace(monotonic=lambda: state["t"], sleep=real_time.sleep)
        try:
            u = cab._collect_muse_usage(share)
        finally:
            del cab.open
            cab.time = real_time
        self.assertTrue(u["partial"], u)
        self.assertIn("time budget", u.get("usage_note", ""), u)
        self.assertLessEqual(state["yielded"], 12, state)  # stopped inside the filler
        self.assertEqual(u["totals"]["input_tokens"], 0, u)


if __name__ == "__main__":
    unittest.main()
