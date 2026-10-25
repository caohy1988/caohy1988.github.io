"""Regression coverage for the installed Mac routine-proxy input formats and state."""
import os
import contextlib
import io
import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import collect_and_build as cab


REVIEWER_FIXTURE = """## ENABLED
| Routine | Cron (PT) | Folder |
| --- | --- | --- |
| sample collect | 32 * * * * | packs |

## PAUSED
| Routine | Cron (PT) | Folder |
| --- | --- | --- |
| paused collect | 10 * * * * | packs |
"""


class RoutineProxy(unittest.TestCase):
    def test_reviewer_fixture_keeps_168_fires_and_paused_row(self):
        rows = cab._parse_active_routine_table(REVIEWER_FIXTURE, "Collection Bot")
        self.assertEqual([(r["name"], r["status"], r["fires_per_week"]) for r in rows],
                         [("sample collect", "enabled", 168.0), ("paused collect", "paused", 0)])
        self.assertEqual(sum(r["fires_per_week"] for r in rows), 168.0)

    def test_first_routine_table_and_paused_only_fallback(self):
        for blob in (REVIEWER_FIXTURE.replace("## ENABLED\n", ""), REVIEWER_FIXTURE):
            self.assertEqual(len(cab._parse_active_routine_table(blob, "Collection Bot")), 2)
        paused = REVIEWER_FIXTURE[REVIEWER_FIXTURE.index("## PAUSED"):]
        rows = cab._parse_active_routine_table(paused, "Collection Bot")
        self.assertEqual([(r["status"], r["fires_per_week"]) for r in rows], [("paused", 0)])

    def test_newest_github_dump_and_mac_manage_state(self):
        with tempfile.TemporaryDirectory() as directory:
            hunt = Path(directory)
            (hunt / "collection-bot-active-routines.md").write_text(REVIEWER_FIXTURE)
            old = hunt / "old-github-bot-active-routines.md"
            old.write_text(REVIEWER_FIXTURE.replace("sample collect", "stale heartbeat"))
            os.utime(old, (1, 1))
            new = hunt / "new-github-bot-active-routines.md"
            new.write_text("""## Active
| Name | Cron (PT) | Status | Notes |
| --- | --- | --- | --- |
| current heartbeat | 4,19,34,49 * * * * | enabled | current |
| PR listener | Github listener | enabled | event |
## Paused
| Name | Cron (PT) | Status | Notes |
| --- | --- | --- | --- |
| paused heartbeat | */5 * * * * | paused | retained |
""")
            result = cab.collect_routine_proxy(hunt=hunt)
            rows = {r["name"]: r for r in result["rows"]}
            self.assertNotIn("stale heartbeat", rows)
            self.assertIn(str(new), result["dump_paths"])
            self.assertNotIn(str(old), result["dump_paths"])
            self.assertEqual(rows["current heartbeat"]["fires_per_week"], 672.0)
            self.assertIsNone(rows["PR listener"]["fires_per_week"])
            self.assertEqual(rows["paused heartbeat"]["fires_per_week"], 0)
            for name in ("Weekday usage dashboard refresh", "Field Brief 6h orchestration watch"):
                self.assertEqual((rows[name]["status"], rows[name]["fires_per_week"]), ("paused", 0))
            self.assertEqual(result["total_fires_per_week"], 168 + 672 + 14)

    def test_minute_field_counts_match_mac_behavior(self):
        for minute, weekly in (("*", 10080), ("*/15", 672), ("4,19,34,49", 672),
                               ("10-12", 504), ("32", 168)):
            with self.subTest(minute=minute):
                self.assertEqual(cab._cron_fires_per_week(f"{minute} * * * *"), weekly)

    def test_publication_keeps_paused_row_with_human_note_label(self):
        with tempfile.TemporaryDirectory() as directory, contextlib.ExitStack() as stack:
            stack.enter_context(patch.object(cab, "HERE", Path(directory)))
            for name in dir(cab):
                if name.startswith("collect_"):
                    stack.enter_context(patch.object(cab, name, return_value={}))
            routine = {"rows": [{"owner": "Collection Bot", "name": "Research output watch",
                                "cron": "*/20 * * * *", "status": "paused", "fires_per_week": 0,
                                "notes": "PAUSED · `internal-seat-output-watch`"}]}
            stack.enter_context(patch.object(cab, "collect_routine_proxy", return_value=routine))
            with contextlib.redirect_stdout(io.StringIO()):
                cab.main()
            snapshot = json.loads((cab.HERE / "snapshot.json").read_text())
            row = snapshot["routine_proxy"]["rows"][0]
            self.assertEqual((row["status"], row["fires_per_week"]), ("paused", 0))
            self.assertEqual(row["notes"], "PAUSED · Research output watch")
            for file in ("snapshot.json", "index.html"):
                self.assertNotIn("internal-seat-output-watch", (cab.HERE / file).read_text())


if __name__ == "__main__":
    unittest.main()
