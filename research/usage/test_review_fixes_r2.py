#!/usr/bin/env python3
"""Round-two review regressions using synthetic logs and memory-only outputs."""
import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab
from test_muse_usage import SCHEMA, frame_line, mc_line, prompt_line, us
from test_review_fixes_r1 import FAKE_KEY, MODEL, NOW, build_in_memory

MAX_COUNTER = 2 ** 64 - 1
COUNTERS = ("input_tokens", "output_tokens", "cached_tokens", "cache_read_tokens", "reasoning_tokens")


class ReviewFixesR2Tests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.root = Path(self.tmp.name)

    def usage(self, lines, model=MODEL):
        log = self.root / "session.jsonl"
        log.write_text("\n".join(lines) + "\n")
        with sqlite3.connect(self.root / "session-index.db") as con:
            con.execute("DROP TABLE IF EXISTS sessions")
            con.execute(SCHEMA)
            con.execute("INSERT INTO sessions (session_id, session_log_path, model_id, "
                        "created_at_us, updated_at_us, prompt_count) VALUES (?,?,?,?,?,?)",
                        ("synthetic-session", str(log), model, us(NOW), us(NOW), 0))
        return cab._collect_muse_usage(self.root, now=NOW)

    def record(self, rec_id, **counters):
        return mc_line(rec_id, us(NOW), MODEL, {"input_tokens": 100, **counters})

    def test_credentials_inside_model_identifiers_are_rejected_and_scrubbed(self):
        for prefix in ("muse_", "muse__", "muse-", "muse.", "muse/", "muse"):
            identifier = prefix + FAKE_KEY
            for event_model in (identifier, None):
                with self.subTest(prefix=prefix, fallback=event_model is None):
                    usage = self.usage([
                        self.record("before"),
                        mc_line("bad", us(NOW), event_model, {"input_tokens": 900000}),
                        self.record("after", input_tokens=200),
                    ], model=identifier)
                    self.assertEqual(usage["by_model"], {MODEL: 300})
                    self.assertEqual(usage["invalid_model_events"], 1)
                    self.assertTrue(usage["partial"])
                    _, outputs = build_in_memory(self.root, muse={"usage": usage})
                    for text in outputs.values():
                        self.assertNotIn(FAKE_KEY, text)
                    # The final scrub must also protect keys/values missed by a collector.
                    usage["by_model"][identifier] = 900000
                    usage["days"][-1]["models"][identifier] = 900000
                    _, outputs = build_in_memory(self.root, muse={"usage": usage, "note": identifier})
                    for text in outputs.values():
                        self.assertNotIn(FAKE_KEY, text)
                        self.assertIn("[REDACTED]", text)

    def test_embedded_jwt_is_rejected_and_scrubbed(self):
        secret = "eyJhbGciOiJmYWtlIn0.eyJzdWIiOiJmYWtlIn0.c3ludGhldGlj"
        identifier = "muse_" + secret
        self.assertIsNone(cab._muse_model_id(identifier))
        _, outputs = build_in_memory(self.root, muse={"model": identifier, "extra": {identifier: identifier}})
        for text in outputs.values():
            self.assertNotIn(secret, text)

    def test_out_of_range_counters_skip_events_and_serialize(self):
        # Each huge integer fits the default 4300-digit parse limit; their sum does not.
        huge = 9 * 10 ** 4299
        for counter in COUNTERS:
            for value in (MAX_COUNTER + 1, float(2 ** 64), huge):
                with self.subTest(counter=counter, kind=type(value).__name__):
                    usage = self.usage([
                        self.record("before"), self.record("bad-1", **{counter: value}),
                        self.record("bad-2", **{counter: value}),
                        self.record("after", input_tokens=200),
                    ])
                    self.assertNotIn("usage_error", usage)
                    self.assertEqual(usage["invalid_counter_events"], 2)
                    self.assertTrue(usage["partial"])
                    self.assertIn("counter", usage["usage_note"])
                    self.assertEqual(usage["totals"]["input_tokens"], 300)
                    self.assertEqual(usage["today"]["input_tokens"], 300)
                    self.assertEqual(usage["by_model"], {MODEL: 300})
                    snap, outputs = build_in_memory(self.root, muse={"usage": usage})
                    self.assertEqual(snap["muse"]["usage"]["totals"]["input_tokens"], 300)
                    self.assertEqual(set(outputs), {"snapshot.json", "index.html"})
                    self.assertIn("Usage incomplete", outputs["index.html"])

    def test_counter_upper_boundary_aggregates_and_serializes(self):
        counters = {name: MAX_COUNTER for name in COUNTERS}
        usage = self.usage([self.record("one", **counters), self.record("two", **counters)])
        self.assertFalse(usage["partial"], usage)
        self.assertEqual(usage["totals"]["input_tokens"], 2 * MAX_COUNTER)
        self.assertEqual(usage["totals"]["cached_tokens"], 4 * MAX_COUNTER)
        self.assertEqual(usage["by_model"], {MODEL: 4 * MAX_COUNTER})
        snap, outputs = build_in_memory(self.root, muse={"usage": usage})
        self.assertEqual(snap["muse"]["usage"]["totals"], usage["totals"])
        self.assertEqual(set(outputs), {"snapshot.json", "index.html"})

    def test_rejected_top_level_runtime_envelopes_mark_incomplete(self):
        for field in ("schema_version", "stream", "id", "record_type"):
            for record in (self.record("bad", input_tokens=200), prompt_line("bad-prompt", us(NOW))):
                with self.subTest(field=field, prompt="bad-prompt" in record):
                    rejected = json.loads(record)
                    del rejected[field]
                    usage = self.usage([self.record("before"), json.dumps(rejected),
                                        self.record("after", input_tokens=50)])
                    self.assertEqual(usage["totals"]["input_tokens"], 150)
                    self.assertEqual(usage["totals"]["prompts"], 0)
                    self.assertTrue(usage["partial"], usage)
                    self.assertEqual(usage["rejected_runtime_records"], 1)
                    self.assertIn("runtime", usage["usage_note"])
                    _, outputs = build_in_memory(self.root, muse={"usage": usage})
                    self.assertIn("Usage incomplete", outputs["index.html"])

    def test_tool_results_with_rejected_envelopes_stay_excluded(self):
        rejected = json.loads(self.record("bad", input_tokens=900000))
        del rejected["schema_version"]
        examples = {"record": rejected, "record_json": json.dumps(rejected),
                    "frame": json.loads(frame_line(json.dumps(rejected)))}
        tool = json.loads(self.record("tool"))
        tool["payload"]["event"] = {"kind": "tool_completed", "result": examples}
        usage = self.usage([self.record("good"), json.dumps(tool), frame_line(json.dumps(tool)),
                            json.dumps({"payload": {"kind": "tool_result", **examples}})])
        self.assertEqual(usage["totals"]["input_tokens"], 100)
        self.assertFalse(usage["partial"], usage)
        self.assertEqual(usage.get("rejected_runtime_records", 0), 0)


if __name__ == "__main__":
    unittest.main()
