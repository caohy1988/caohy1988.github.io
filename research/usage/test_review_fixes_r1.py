#!/usr/bin/env python3
"""Review regressions: synthetic logs, isolated SQLite and memory-only build outputs."""
import contextlib
import copy
import io
import json
import sqlite3
import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab
from test_muse_usage import SCHEMA, frame_line, mc_line, prompt_line, us

NOW = datetime(2026, 10, 24, 12, tzinfo=cab.PT)
MODEL = "muse-synthetic-model"
FAKE_KEY = "sk-or-v1-SYNTHETIC0123456789abcdef"


def build_in_memory(root, **seats):
    outputs = {}

    def capture(path, text, *args, **kwargs):
        outputs[path.name] = text
        return len(text)

    with contextlib.ExitStack() as stack:
        for name in dir(cab):
            if name.startswith("collect_") and callable(getattr(cab, name)):
                value = seats.get(name[len("collect_"):], {})
                stack.enter_context(mock.patch.object(cab, name, lambda v=value: copy.deepcopy(v)))
        stack.enter_context(mock.patch.object(cab, "HERE", root))
        stack.enter_context(mock.patch.object(Path, "write_text", capture))
        stack.enter_context(contextlib.redirect_stdout(io.StringIO()))
        cab.main()
    return json.loads(outputs["snapshot.json"]), outputs


class ReviewFixesTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def usage(self, lines, model=MODEL):
        log = self.root / "session.jsonl"
        log.write_text("\n".join(lines) + "\n")
        db = self.root / "session-index.db"
        with sqlite3.connect(db) as con:
            con.execute("DROP TABLE IF EXISTS sessions")
            con.execute(SCHEMA)
            con.execute("INSERT INTO sessions (session_id, session_log_path, model_id, "
                        "created_at_us, updated_at_us, prompt_count) VALUES (?,?,?,?,?,?)",
                        ("synthetic-session", str(log), model, us(NOW), us(NOW), 0))
        return cab._collect_muse_usage(self.root, now=NOW)

    def model_record(self, rec_id, count=100, model=MODEL, **counters):
        return mc_line(rec_id, us(NOW), model, {"input_tokens": count, **counters})

    def test_credential_models_rejected_before_aggregation_and_main(self):
        for secret in (FAKE_KEY, "provider/" + FAKE_KEY, "SK-SYNTHETIC0123456789abcdef",
                       "eyJhbGciOiJmYWtlIn0.eyJzdWIiOiJmYWtlIn0.c3ludGhldGlj"):
            for event_model in (secret, None):  # index fallback is untrusted too
                with self.subTest(secret=secret, fallback=event_model is None):
                    usage = self.usage([self.model_record("good"),
                                        self.model_record("bad", 900000, model=event_model)], model=secret)
                    self.assertEqual(usage["by_model"], {MODEL: 100})
                    self.assertTrue(usage["partial"])
                    self.assertNotIn(secret, json.dumps(usage))
                    _, outputs = build_in_memory(self.root, muse={"usage": usage})
                    for text in outputs.values():
                        self.assertNotIn(secret, text)

    def test_main_scrubs_dynamic_keys_even_if_a_collector_misses_them(self):
        usage = self.usage([self.model_record("good")])
        usage["by_model"][FAKE_KEY] = 900000
        usage["days"][-1]["models"][FAKE_KEY] = 900000
        _, outputs = build_in_memory(self.root, muse={"usage": usage})
        for text in outputs.values():
            self.assertNotIn(FAKE_KEY, text)
            self.assertIn("[REDACTED]", text)
        self.assertEqual(cab.scrub_tree({"outer": [{"literal-secret": 1}]}, ("literal-secret",)),
                         {"outer": [{"[REDACTED]": 1}]})
        self.assertEqual(cab.scrub_tree(({FAKE_KEY: FAKE_KEY},)),
                         [{"[REDACTED]": "[REDACTED]"}])

    def test_huge_finite_window_builds_both_outputs(self):
        seat = {"ok": True, "bars": [{"label": "Synthetic", "used_percent": 25,
                                      "reset_at": (NOW + timedelta(hours=1)).isoformat(),
                                      "window_seconds": 1e308}]}
        with mock.patch.object(cab, "datetime", wraps=datetime) as clock:
            clock.now.return_value = NOW
            snap, outputs = build_in_memory(self.root, codex=seat)
        pace = snap["codex"]["bars"][0]["pacing"]
        self.assertEqual(pace["status"], "ok")
        self.assertAlmostEqual(pace["elapsed_pct"], 100)
        self.assertAlmostEqual(pace["ahead_points"], -75)
        self.assertIn("pacing: 25% used vs 100%", outputs["index.html"])
        for text in outputs.values():
            for token in ("Infinity", "NaN", "inf%", "nan%"):
                self.assertNotIn(token, text)

    def test_tool_results_cannot_supply_records_frames_or_events(self):
        quoted = self.model_record("example", 900000)
        prompt = prompt_line("example-prompt", us(NOW))
        examples = {"record_json": quoted, "prompt": {"record_json": prompt},
                    "record": json.loads(quoted), "frame": json.loads(frame_line(quoted)),
                    "event": {"kind": "model_completed", "model": MODEL,
                              "usage": {"input_tokens": 900000}}}
        tool = json.loads(self.model_record("tool"))
        tool["payload"]["event"] = {"kind": "tool_completed", "result": examples}
        usage = self.usage([self.model_record("good"), prompt_line("real-prompt", us(NOW)),
                            json.dumps(tool), frame_line(json.dumps(tool)),
                            json.dumps({"payload": {"kind": "tool_result", **examples}}),
                            json.dumps(examples),
                            frame_line(self.model_record("frame-only", 50)),
                            frame_line(prompt_line("frame-prompt", us(NOW)))])
        self.assertEqual(usage["totals"]["input_tokens"], 150)
        self.assertEqual(usage["totals"]["prompts"], 2)
        self.assertEqual(usage["by_model"], {MODEL: 150})
        self.assertFalse(usage["partial"], usage)

    def test_invalid_muse_counters_skip_one_event_and_continue(self):
        for counter in ("input_tokens", "output_tokens", "cached_tokens", "cache_read_tokens", "reasoning_tokens"):
            for value in (float("inf"), float("-inf"), float("nan"), -1, True, "100", 1.5):
                with self.subTest(counter=counter, value=value):
                    bad = self.model_record("bad", **{counter: value})
                    usage = self.usage([self.model_record("before"), bad,
                                        self.model_record("after", 200)])
                    self.assertNotIn("usage_error", usage)
                    self.assertTrue(usage["partial"], usage)
                    self.assertIn("counter", usage["usage_note"])
                    self.assertEqual(usage["totals"]["input_tokens"], 300)
                    self.assertEqual(usage["today"]["input_tokens"], 300)
                    self.assertEqual(sum(d["input_tokens"] for d in usage["days"]), 300)
                    self.assertEqual(usage["by_model"], {MODEL: 300})
                    _, outputs = build_in_memory(self.root, muse={"usage": usage})
                    self.assertIn("Usage incomplete", outputs["index.html"])

    def test_later_scan_failure_still_finalizes_accumulated_totals(self):
        real_find = cab._muse_find_model_completed

        def fail_later(obj, *args, **kwargs):
            if obj.get("id") == "later-failure":
                raise RuntimeError("synthetic scan failure")
            return real_find(obj, *args, **kwargs)

        with mock.patch.object(cab, "_muse_find_model_completed", fail_later):
            usage = self.usage([self.model_record("good"), self.model_record("later-failure")])
        self.assertTrue(usage["partial"])
        self.assertEqual(usage["totals"]["input_tokens"], 100)
        self.assertEqual(usage["today"]["input_tokens"], 100)
        self.assertEqual(usage["totals"]["sessions"], 1)
        self.assertEqual(usage["by_model"], {MODEL: 100})

    def test_spend_retries_utc_boundary_and_dates_the_retry(self):
        for start in (datetime(2026, 10, 25, 23, 59, 59, tzinfo=timezone.utc),  # Sunday -> Monday
                      datetime(2026, 10, 31, 23, 59, 59, tzinfo=timezone.utc)):
            end = start + timedelta(seconds=2)
            clocks = [start, end, end, end + timedelta(seconds=1)]
            replies = [{"data": {"usage": 10, "usage_daily": 9, "usage_weekly": 9, "usage_monthly": 9}},
                       {"data": {"usage": 10, "usage_daily": 0, "usage_weekly": 0, "usage_monthly": 0}}]
            with self.subTest(start=start), mock.patch.object(cab, "read_openrouter_key", return_value=FAKE_KEY), \
                    mock.patch.object(cab, "_openrouter_get", side_effect=replies) as get:
                seat = cab.collect_openrouter(clock=mock.Mock(side_effect=clocks))
            self.assertTrue(seat["ok"], seat)
            self.assertEqual(get.call_count, 2)
            self.assertEqual(seat["windows"], cab._openrouter_window_labels(end))
            self.assertEqual(seat["fetched_at"], cab.iso_pt(clocks[-1]))
            self.assertEqual(seat["spend_usd"]["today_utc"], 0)

    def test_spend_repeated_boundary_crossing_stays_unavailable(self):
        start = datetime(2026, 10, 25, 23, 59, 59, tzinfo=timezone.utc)
        reply = {"data": {"usage": 10, "usage_daily": 1, "usage_weekly": 2, "usage_monthly": 3}}
        clocks = [start, start + timedelta(days=1), start + timedelta(days=1), start + timedelta(days=2)]
        with mock.patch.object(cab, "read_openrouter_key", return_value=FAKE_KEY), \
                mock.patch.object(cab, "_openrouter_get", return_value=reply) as get:
            seat = cab.collect_openrouter(clock=mock.Mock(side_effect=clocks))
        self.assertEqual(get.call_count, 2)
        self.assertFalse(seat["ok"])
        self.assertTrue(all(v is None for v in seat["spend_usd"].values()))
        self.assertIsNone(seat["fetched_at"])


if __name__ == "__main__":
    unittest.main()
