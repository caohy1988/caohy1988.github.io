"""Regression checks for database privacy, recorded costs and inherited fork history."""
import json
import math
import sqlite3
import tempfile
import unittest
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from unittest.mock import patch

import collect_and_build as cab


class OpenCodeEdgeCases(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(dir="/tmp")
        self.addCleanup(self.tmp.cleanup)
        self.db = Path(self.tmp.name) / "opencode.db"
        self.now = datetime(2026, 10, 24, 18, 30, tzinfo=cab.PT)
        self.ts = int(self.now.timestamp() * 1000)
        self.private = "/private/customer-project synthetic secret prompt"
        self.sequence = 0
        self.con = sqlite3.connect(str(self.db))
        self.con.executescript("CREATE TABLE session (id TEXT, parent_id TEXT, time_created INTEGER DEFAULT 0);"
                               "CREATE TABLE message (id TEXT PRIMARY KEY, session_id TEXT, time_created INTEGER,"
                               "time_updated INTEGER, data TEXT);"
                               "CREATE TABLE part (id TEXT PRIMARY KEY, message_id TEXT, session_id TEXT,"
                               "time_created INTEGER, time_updated INTEGER, data TEXT);")
        self.con.execute("INSERT INTO session VALUES ('session', NULL, ?)", (self.ts - 10_000,))
        self.addCleanup(self.con.close)

    def store_message(self, session, data, created, message_id=None, executed=True):
        parent = data.get("parentID")
        if data.get("role") == "assistant" and parent and not self.con.execute("SELECT 1 FROM message WHERE id=?", (parent,)).fetchone():
            # Native forks copy the preceding user message and its input parts, remapping ids.
            parent_time = data.get("time", {}).get("created", created) - 500
            user = {"role": "user", "time": {"created": parent_time}, "agent": "build",
                    "model": {"providerID": "openrouter", "modelID": "z-ai/glm-5.3"}}
            self.store_message(session, user, parent_time, parent, executed=False)
            self.con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                             (parent + '-text', parent, session, parent_time, parent_time,
                              json.dumps({"type": "text", "text": self.private + ' immutable input'})))
        self.sequence += 1
        message_id = message_id or f"message-{self.sequence}"
        self.con.execute("INSERT INTO message VALUES (?, ?, ?, ?, ?)",
                         (message_id, session, created, created, json.dumps(data)))
        if executed:
            for kind in ("step-start", "step-finish"):
                self.con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                                 (message_id + kind, message_id, session, created, created, json.dumps({"type": kind})))
        self.con.commit()
        return message_id

    def add_request(self, cost=0.25):
        data = {"role": "assistant", "modelID": "z-ai/glm-5.3", "cost": cost,
                "tokens": {"input": 10, "output": 2, "reasoning": 1, "cache": {"read": 3, "write": 0}}}
        return self.store_message("session", data, self.ts)

    def summary(self):
        return cab.summarize_opencode_usage(self.db, self.now)

    def add_execution(self, session, message_id, parent, created=None, completed=None, stored_at=None):
        created = self.ts - 1000 if created is None else created
        completed = created + 500 if completed is None else completed
        data = {"id": message_id, "sessionID": session, "parentID": parent, "role": "assistant",
                "providerID": "openrouter", "modelID": "z-ai/glm-5.3", "mode": "build", "agent": "build",
                "path": {"cwd": self.private},
                "time": {"created": created, "completed": completed}, "cost": 0.25,
                "tokens": {"input": 10, "output": 2, "reasoning": 1, "cache": {"read": 3, "write": 0}}}
        return self.store_message(session, data, created if stored_at is None else stored_at, message_id)

    def test_fork_alone_preserves_request_tokens_cost_and_windows(self):
        self.add_execution("session", "original-message", "original-user")
        original = self.summary()
        self.con.execute("INSERT INTO session (id, parent_id) VALUES ('fork', NULL)")
        self.add_execution("fork", "copied-message", "copied-user")
        first_fork = self.summary()
        self.assertEqual(first_fork["requests"], 1)
        self.assertEqual(first_fork["windows"], original["windows"])
        self.assertEqual(first_fork["windows"]["all_time"]["cost_usd"], 0.25)
        self.con.execute("INSERT INTO session (id, parent_id) VALUES ('nested-fork', NULL)")
        self.add_execution("nested-fork", "second-copy", "second-user")
        usage = self.summary()
        self.assertEqual(usage["requests"], 1)
        self.assertEqual(usage["sessions"], 1)
        self.assertEqual(usage["windows"], original["windows"])
        self.assertEqual(usage["models"], original["models"])
        self.assertEqual(usage["last_run_pt"], original["last_run_pt"])
        self.assertEqual(usage["deduplicated_requests"], 2)
        self.assertNotIn("original-message", json.dumps(usage))
        self.assertNotIn(self.private, json.dumps(usage) + cab.render_opencode_body({"usage": usage}))
        self.assertNotIn("copied-user", cab.render_opencode_body({"usage": usage}))

    def test_new_fork_execution_and_same_session_requests_still_count(self):
        self.add_execution("session", "first", "user-one")
        self.add_execution("session", "second", "user-two")
        self.con.execute("INSERT INTO session (id, parent_id) VALUES ('fork', NULL)")
        self.add_execution("fork", "copy-first", "copied-user-one")
        self.add_execution("fork", "copy-second", "copied-user-two")
        self.add_execution("fork", "new-call", "new-user", created=self.ts - 999)
        usage = self.summary()
        self.assertEqual(usage["requests"], 3)
        self.assertEqual(usage["deduplicated_requests"], 2)
        totals = usage["windows"]["all_time"]
        self.assertEqual((totals["input_tokens"], totals["output_tokens"], totals["cost_usd"]), (39, 6, 0.75))

    def test_missing_execution_metadata_does_not_merge_distinct_rows(self):
        self.add_request()
        self.con.execute("INSERT INTO message SELECT 'copy-' || id, 'fork', time_created, time_updated, data FROM message")
        self.con.execute("INSERT INTO part SELECT 'copy-' || id, 'copy-' || message_id, 'fork', time_created, time_updated, data FROM part")
        self.con.commit()
        self.assertEqual(self.summary()["requests"], 2)

    def test_execution_clock_survives_fork_insertion_and_source_removal(self):
        executed = self.ts - 2 * 86_400_000
        self.add_execution("session", "original", "original-user", created=executed)
        original = self.summary()
        self.con.execute("DELETE FROM message")
        self.add_execution("fork", "inherited", "copied-user", created=executed, stored_at=self.ts)
        usage = self.summary()
        self.assertEqual(usage["windows"], original["windows"])
        self.assertEqual(usage["last_run_pt"], original["last_run_pt"])
        self.assertEqual(usage["windows"]["last_24h"]["requests"], 0)

    def test_different_execution_clocks_remain_separate(self):
        self.add_execution("fork", "copy", "copied-user")
        self.add_execution("session", "original", "original-user")
        self.add_execution("fork", "new", "new-user", created=self.ts - 999)
        usage = self.summary()
        self.assertEqual(usage["requests"], 2)
        self.assertEqual(usage["deduplicated_requests"], 1)
        self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.5)

    def test_independent_same_millisecond_sessions_are_not_deduplicated(self):
        self.con.execute("INSERT INTO session VALUES ('independent', NULL, ?)", (self.ts - 9000,))
        self.add_execution("session", "first-call", "first-user")
        self.add_execution("independent", "second-call", "second-user", completed=self.ts - 100)
        self.con.execute("UPDATE part SET data=? WHERE message_id='second-user'",
                         (json.dumps({"type": "text", "text": "a different independent input"}),))
        self.con.commit()
        for parent_evidence in (True, False):
            with self.subTest(parent_evidence=parent_evidence):
                if not parent_evidence:
                    self.con.execute("DELETE FROM message WHERE id IN ('first-user', 'second-user')")
                    self.con.commit()
                usage = self.summary()
                self.assertEqual((usage["requests"], usage["sessions"]), (2, 2))
                self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.5)
                self.assertEqual(usage["deduplicated_requests"], 0)

    def test_partial_fork_keeps_canonical_origin_session(self):
        self.add_execution("session", "z-first", "first-user")
        self.add_execution("session", "z-second", "second-user", created=self.ts - 900)
        original = self.summary()
        self.con.execute("INSERT INTO session VALUES ('fork', NULL, ?)", (self.ts - 100,))
        self.add_execution("fork", "a-copy", "copied-user")
        self.con.execute("UPDATE message SET time_updated=? WHERE id='a-copy'", (self.ts - 50,))
        self.con.commit()
        usage = self.summary()
        self.assertEqual((usage["sessions"], usage["requests"]), (1, 2))
        self.assertEqual(usage["windows"], original["windows"])
        self.assertEqual(usage["models"], original["models"])
        self.assertEqual(usage["deduplicated_requests"], 1)

    def prepare_compaction(self, kind="compaction", text=None, tail=True, auto=True, overflow=False):
        seed = {"role": "user", "time": {"created": self.ts - 4000}, "agent": "build",
                "model": {"providerID": "openrouter", "modelID": "z-ai/glm-5.3"}}
        self.store_message("session", seed, self.ts - 4000, "01-seed", executed=False)
        self.con.execute("INSERT INTO part VALUES ('01-input', '01-seed', 'session', ?, ?, ?)",
                         (self.ts - 4000, self.ts - 4000,
                          json.dumps({"type": "text", "text": text or self.private + ' prior input'})))
        # A non-model assistant also exercises the fork-rewritten preceding parent chain.
        wrapper = {"role": "assistant", "parentID": "01-seed", "mode": "build", "agent": "build",
                   "providerID": "openrouter", "modelID": "z-ai/glm-5.3", "time": {"created": self.ts - 3000},
                   "cost": 0, "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}}
        self.store_message("session", wrapper, self.ts - 3000, "02-wrapper", executed=False)
        parent = dict(seed, time={"created": self.ts - 2000})
        self.store_message("session", parent, self.ts - 2000, "03-parent", executed=False)
        if kind == "compaction":
            part = {"type": "compaction", "auto": auto}
            if overflow is not None:
                part["overflow"] = overflow
            if tail:
                part["tail_start_id"] = "02-wrapper"
        elif kind == "file":
            part = {"type": "file", "mime": "text/plain", "url": "file:///private/input.txt"}
        else:
            part = {"type": "text", "text": self.private + ' current input'}
        self.con.execute("INSERT INTO part VALUES ('03-input', '03-parent', 'session', ?, ?, ?)",
                         (self.ts - 2000, self.ts - 2000, json.dumps(part)))
        self.add_execution("session", "04-call", "03-parent")
        if kind == "compaction":
            data = json.loads(self.con.execute("SELECT data FROM message WHERE id='04-call'").fetchone()[0])
            data.update(mode="compaction", agent="compaction", summary=True)
            self.con.execute("UPDATE message SET data=? WHERE id='04-call'", (json.dumps(data),))
            self.con.commit()

    def fork_history(self):
        rows = self.con.execute("SELECT id, time_created, time_updated, data FROM message WHERE session_id='session'"
                                " ORDER BY time_created, id").fetchall()
        remap = {row[0]: f"copy-{i:04d}" for i, row in enumerate(rows)}
        self.con.execute("INSERT INTO session VALUES ('fork', NULL, ?)", (self.ts - 100,))
        for mid, created, updated, raw in rows:
            data = dict(json.loads(raw), id=remap[mid], sessionID="fork")
            if data.get("role") == "assistant" and data.get("parentID") in remap:
                data["parentID"] = remap[data["parentID"]]
            self.con.execute("INSERT INTO message VALUES (?, 'fork', ?, ?, ?)",
                             (remap[mid], created, self.ts - 50, json.dumps(data)))
        parts = self.con.execute("SELECT message_id, time_created, data FROM part WHERE session_id='session' ORDER BY id").fetchall()
        for i, (mid, created, raw) in enumerate(parts):
            data = dict(json.loads(raw), id=f"copied-part-{i:04d}", messageID=remap[mid], sessionID="fork")
            if data.get("type") == "compaction" and data.get("tail_start_id"):
                data["tail_start_id"] = remap[data["tail_start_id"]]
            self.con.execute("INSERT INTO part VALUES (?, ?, 'fork', ?, ?, ?)",
                             (data["id"], remap[mid], created, self.ts - 50, json.dumps(data)))
        self.con.commit()

    def test_compaction_only_parent_fork_preserves_usage(self):
        self.prepare_compaction()
        original = self.summary()
        self.assertEqual((original["requests"], original["sessions"], original["windows"]["all_time"]["cost_usd"]), (1, 1, 0.25))
        self.fork_history()
        usage = self.summary()
        self.assertEqual((usage["requests"], usage["sessions"]), (1, 1))
        self.assertEqual(usage["windows"], original["windows"])
        self.assertEqual(usage["models"], original["models"])
        self.assertEqual(usage["deduplicated_requests"], 1)
        self.assertNotIn(self.private, json.dumps(usage) + cab.render_opencode_body({"usage": usage}))

    def test_fork_usage_preserved_for_supported_parent_kinds(self):
        for kind, auto, overflow in (("text", True, False), ("file", True, False),
                                     ("compaction", True, False), ("compaction", False, None)):
            with self.subTest(kind=kind, auto=auto, overflow=overflow):
                self.con.executescript("DELETE FROM part; DELETE FROM message; DELETE FROM session WHERE id='fork';")
                self.prepare_compaction(kind, tail=False, auto=auto, overflow=overflow)
                original = self.summary()
                self.fork_history()
                if kind == "compaction":
                    part = {"type": "compaction", "auto": auto, "tail_start_id": "02-wrapper"}
                    if overflow is not None:
                        part["overflow"] = overflow
                    self.con.execute("UPDATE part SET data=? WHERE id='03-input'", (json.dumps(part),))
                    self.con.commit()  # Native compaction may assign the tail reference after forking.
                usage = self.summary()
                self.assertEqual(usage["windows"], original["windows"])
                self.assertEqual((usage["requests"], usage["sessions"]), (1, 1))

    def test_independent_compactions_require_matching_preceding_history(self):
        self.prepare_compaction()
        self.fork_history()
        self.con.execute("UPDATE part SET data=? WHERE session_id='fork' AND message_id='copy-0000'",
                         (json.dumps({"type": "text", "text": "independent preceding input"}),))
        self.con.commit()
        usage = self.summary()
        self.assertEqual((usage["requests"], usage["sessions"]), (2, 2))
        self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.5)

    def test_fork_after_usage_before_completion_counts_once(self):
        self.add_execution("session", "z-original", "original-user")
        data = json.loads(self.con.execute("SELECT data FROM message WHERE id='z-original'").fetchone()[0])
        data["time"].pop("completed")
        self.con.execute("UPDATE message SET data=? WHERE id='z-original'", (json.dumps(data),))
        self.con.commit()
        original = self.summary()
        copy = dict(data, id="a-copy", sessionID="fork", parentID="copied-user")
        self.store_message("fork", copy, self.ts - 1000, "a-copy")
        data["time"]["completed"] = self.ts
        data["finish"] = "stop"
        self.con.execute("UPDATE message SET data=?, time_updated=? WHERE id='z-original'", (json.dumps(data), self.ts))
        self.con.commit()
        usage = self.summary()
        self.assertEqual(usage["requests"], 1)
        self.assertEqual(usage["windows"], original["windows"])
        self.assertEqual(usage["models"], original["models"])
        self.assertEqual(usage["deduplicated_requests"], 1)

    def test_later_usage_reconciles_a_stale_fork_copy(self):
        self.add_execution("session", "z-original", "original-user")
        data = json.loads(self.con.execute("SELECT data FROM message WHERE id='z-original'").fetchone()[0])
        data["time"].pop("completed")
        self.store_message("fork", dict(data, id="a-copy", sessionID="fork", parentID="copied-user"), self.ts - 1000, "a-copy")
        data["cost"] = 0.5
        data["tokens"]["input"] = 20
        self.con.execute("UPDATE message SET data=?, time_updated=? WHERE id='z-original'", (json.dumps(data), self.ts))
        self.con.commit()
        usage = self.summary()
        totals = usage["windows"]["all_time"]
        self.assertEqual((usage["requests"], totals["input_tokens"], totals["cost_usd"]), (1, 23, 0.5))

    def add_synthetic(self, tool):
        data = {"role": "assistant", "mode": "build", "agent": "build", "modelID": "z-ai/glm-5.3",
                "providerID": "openrouter", "time": {"created": self.ts - 1000, "completed": self.ts},
                "cost": 0, "tokens": {"input": 0, "output": 0, "reasoning": 0, "cache": {"read": 0, "write": 0}}}
        mid = self.store_message("session", data, self.ts - 1000, executed=False)
        self.con.execute("INSERT INTO part VALUES (?, ?, 'session', ?, ?, ?)",
                         (mid + '-tool', mid, self.ts, self.ts, json.dumps({"type": "tool", "tool": tool})))
        self.con.commit()

    def test_shell_only_has_no_model_requests(self):
        self.add_synthetic("bash")
        usage = self.summary()
        self.assertEqual((usage["state"], usage["requests"], usage["bad_rows"]), ("no_requests", 0, 0))

    def test_subtask_wrapper_plus_model_call_counts_only_call(self):
        self.add_synthetic("task")
        self.con.execute("INSERT INTO session (id, parent_id) VALUES ('child', 'session')")
        self.add_execution("child", "actual-call", "child-user")
        usage = self.summary()
        self.assertEqual((usage["requests"], usage["sessions"]), (1, 1))
        self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.25)

    def test_genuine_zero_cost_and_zero_token_call_still_counts(self):
        self.add_synthetic("bash")
        data = json.loads(self.con.execute("SELECT data FROM message").fetchone()[0])
        mid = self.store_message("session", data, self.ts - 1000, "zero-cost-call")
        self.con.execute("DELETE FROM part WHERE message_id=? AND data LIKE '%step-finish%'", (mid,))
        self.con.commit()
        usage = self.summary()
        self.assertEqual(usage["requests"], 1)
        self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.0)

    def test_invalid_utf8_rows_keep_valid_neighbors(self):
        self.add_request()
        raw = self.private.encode() + b"\xff"
        self.con.execute("INSERT INTO message VALUES ('bad-data', 'session', ?, ?, CAST(? AS TEXT))", (self.ts, self.ts, raw))
        self.con.execute("INSERT INTO message VALUES ('bad-session', CAST(? AS TEXT), ?, ?, '{}')", (raw, self.ts, self.ts))
        self.con.execute("INSERT INTO session (id, parent_id) VALUES (CAST(? AS TEXT), NULL)", (raw,))
        self.con.execute("INSERT INTO session (id, parent_id) VALUES ('bad-parent', CAST(? AS TEXT))", (raw,))
        self.con.commit()
        usage = self.summary()
        self.assertEqual((usage["state"], usage["requests"], usage["bad_rows"]), ("ok", 1, 4))
        self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.25)
        public = json.dumps(cab.scrub_tree(usage), allow_nan=False) + cab.render_opencode_body({"usage": usage})
        self.assertNotIn(self.private, public)

    def test_database_exception_has_fixed_public_category(self):
        with patch.object(cab, "_opencode_connect", side_effect=sqlite3.OperationalError(self.private)):
            usage = self.summary()
        self.assertEqual(usage, {"state": "unreadable", "error": "opencode.db unreadable: database read failed"})
        self.assertNotIn(self.private, json.dumps(cab.scrub_tree(usage)))
        self.assertNotIn(self.private, cab.render_opencode_body({"usage": usage, "error": usage["error"]}))

    def test_malformed_parts_preserve_valid_usage_and_privacy(self):
        self.add_request()
        raw = self.private.encode() + b"\xff"
        self.con.execute("INSERT INTO part VALUES ('bad-data', 'unknown', 'session', ?, ?, CAST(? AS TEXT))",
                         (self.ts, self.ts, raw))
        self.con.execute("INSERT INTO part VALUES ('bad-id', CAST(? AS TEXT), 'session', ?, ?, '{}')",
                         (raw, self.ts, self.ts))
        self.con.commit()
        usage = self.summary()
        self.assertEqual((usage["requests"], usage["bad_rows"]), (1, 2))
        self.assertNotIn(self.private, json.dumps(usage, allow_nan=False) + cab.render_opencode_body({"usage": usage}))

    def test_oversized_cost_rejects_only_its_row(self):
        self.add_request()
        self.add_request(10 ** 400)
        usage = self.summary()
        self.assertEqual((usage["state"], usage["requests"], usage["bad_rows"]), ("ok", 1, 1))
        self.assertEqual(usage["windows"]["all_time"]["cost_usd"], 0.25)

    def test_overflow_cost_is_unavailable_with_counts_preserved(self):
        self.add_request(1e308)
        self.add_request(1e308)
        usage = self.summary()
        for window in list(usage["windows"].values()) + usage["models"]:
            self.assertEqual(window["requests"], 2)
            self.assertIsNone(window["cost_usd"])
            self.assertTrue(window["cost_overflow"])
        json.dumps(usage, allow_nan=False)
        html = cab.render_opencode_body({"usage": usage})
        self.assertIn("Cost unavailable: aggregate overflow", html)
        self.assertNotIn("$inf", html)

    def test_finite_cost_and_empty_windows_stay_finite(self):
        self.add_request(1e308)
        usage = self.summary()
        self.assertTrue(math.isfinite(usage["windows"]["all_time"]["cost_usd"]))
        self.assertNotIn("cost_overflow", usage["windows"]["all_time"])
        json.dumps(usage, allow_nan=False)

    def test_main_refuses_nonfinite_json_before_writing(self):
        with patch.object(cab, "HERE", Path(self.tmp.name) / "output"):
            with ExitStack() as stack:
                for name in dir(cab):
                    if name.startswith("collect_"):
                        stack.enter_context(patch.object(cab, name, return_value={}))
                stack.enter_context(patch.object(cab, "collect_opencode", return_value={"cost": float("inf")}))
                with self.assertRaises(ValueError):
                    cab.main()
                self.assertFalse((cab.HERE / "snapshot.json").exists())
                self.assertFalse((cab.HERE / "index.html").exists())


if __name__ == "__main__":
    unittest.main()
