"""Only identified nightly audits advance the Qwen trial, including outage makeup runs."""
import json
import unittest
import tempfile
from pathlib import Path
from unittest.mock import patch
from datetime import datetime

import collect_and_build as cab


class QwenAuditRuns(unittest.TestCase):
    def record(self, day, sid, job_type="nightly-mac-harness-audit"):
        return json.dumps({
            "version": 1, "sessionId": sid,
            "timestamp": int(datetime(2026, 10, day, 3, tzinfo=cab.PT).timestamp() * 1000),
            "models": {"qwen/qwen3.8-max-0902": {"requests": 1}},
            "job_type": job_type,
        })

    def summary(self, records, day=28):
        return cab.summarize_qwen_usage("\n".join(records), datetime(2026, 10, day, 12, tzinfo=cab.PT))

    def test_third_audit_after_outage_completes_run_count(self):
        records = [self.record(day, f"audit-{day}") for day in (25, 26, 28)]
        u = self.summary(records)
        t = u["trial"]
        self.assertEqual((t["runs"], t["runs_display"]), (3, "3/3"))
        self.assertIn("3/3 runs; keep/drop pending review", t["status"])
        self.assertEqual(t["later_sessions"], 0)
        self.assertIn("TRIAL PENDING 3/3", cab.render_qwen_body({"usage": u, "trial": t}))

    def test_ordinary_sessions_inside_and_after_window_do_not_count(self):
        records = [self.record(day, f"audit-{day}") for day in (25, 26)]
        for day in (27, 28):
            records.append(self.record(day, f"ordinary-{day}", job_type=None))
        u = self.summary(records)
        self.assertEqual(u["sessions"], 4)
        self.assertEqual(u["windows"]["all_time"]["requests"], 4)
        self.assertEqual((u["trial"]["runs"], u["trial"]["runs_display"]), (2, "2/3"))
        self.assertIn("pending the third recorded run", u["trial"]["status"])
        self.assertEqual(u["trial"]["later_sessions"], 1)

    def test_repeated_record_for_same_audit_counts_once(self):
        record = self.record(28, "audit-makeup")
        u = self.summary([record, record])
        self.assertEqual((u["trial"]["runs"], u["duplicate_records"]), (1, 1))
        # As with usage counters, the final record owns the session's classification.
        u = self.summary([record, self.record(28, "audit-makeup", job_type=None)])
        self.assertIsNone(u["trial"]["runs"])

    def test_setup_and_future_audits_do_not_count(self):
        u = self.summary([self.record(day, f"audit-{day}") for day in (24, 25, 29)])
        self.assertEqual((u["trial"]["runs"], u["future_records"]), (1, 1))
        self.assertEqual(u["trial"]["setup_test_sessions"], 1)

    def test_native_records_through_production_collector_are_unavailable(self):
        # These are the native v1 producer fields: it never emits a job label.
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            (home / ".qwen").mkdir()
            (home / ".dsh").mkdir()
            (home / ".dsh" / ".env").write_text("OPENROUTER_API_KEY=fixture-key\n")
            (home / ".qwen" / "settings.json").write_text(json.dumps({
                "model": {"name": "qwen/qwen3.8-max-0902"}}))
            binary = home / "qwen"
            binary.write_text("#!/bin/sh\necho 0.26.1\n")
            binary.chmod(0o700)
            records = []
            for day in (25, 26, 28):
                record = json.loads(self.record(day, f"native-private-{day}"))
                del record["job_type"]
                record.update(project="private-project", startTime=record["timestamp"] - 1000,
                              durationMs=1000, totalLatencyMs=500, files={}, skills={}, tools={})
                record["models"]["qwen/qwen3.8-max-0902"].update(
                    inputTokens=25000, cachedTokens=0, outputTokens=10,
                    thoughtsTokens=0, totalTokens=25010, totalLatencyMs=500)
                records.append(json.dumps(record))
            usage_path = home / ".qwen" / "usage_record.jsonl"
            usage_path.write_text("\n".join(records))
            for day in (28, 29):
                with self.subTest(day=day), patch.object(cab.Path, "home", return_value=home), \
                        patch.object(cab, "QWEN_BIN", binary), \
                        patch.object(cab, "now_pt", return_value=datetime(2026, 10, day, 12, tzinfo=cab.PT)):
                    card = cab.collect_qwen()
                    self.assertTrue(card["ok"])
                    self.assertEqual(card["usage"]["sessions"], 3)
                    self.assertIsNone(card["trial"]["runs"])
                    self.assertIsNone(card["trial"]["runs_display"])
                    self.assertEqual(card["trial"]["status"], "audit status unavailable (no audit receipts)")
                    public = json.dumps(card) + cab.render_qwen_body(card)
                    for private in ("0/3", "native-private", "private-project"):
                        self.assertNotIn(private, public)

    def test_exact_audit_marker_required_and_not_published(self):
        records = [self.record(28, f"ordinary-{i}", marker) for i, marker in enumerate(
            (None, True, "audit", "nightly-mac-harness-audit-extra", {"name": "nightly-mac-harness-audit"}))]
        # A native record without an annotation remains ordinary usage.
        native = json.loads(self.record(28, "ordinary-native"))
        del native["job_type"]
        records.append(json.dumps(native))
        u = self.summary(records)
        self.assertEqual((u["sessions"], u["trial"]["runs"]), (6, None))
        u = self.summary(records + [self.record(28, "private-audit-id")])
        self.assertEqual(u["trial"]["runs"], 1)
        public = json.dumps(u) + cab.render_qwen_body({"usage": u, "trial": u["trial"]})
        for private in ("private-audit-id", "ordinary-native", "job_type", "nightly-mac-harness-audit"):
            self.assertNotIn(private, public)


if __name__ == "__main__":
    unittest.main()
