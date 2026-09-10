"""The detailed RFC agrees with the five-minute decision brief (rfc/rfc-detailed-align-spec.md §4, gates G2 and G3).

Its first 800 rendered words name the proposal, the data, Knowledge Publications, BigQuery Agent Analytics and the
2026-09-19 checkpoint; the two pages link each other, the detailed page calling the landing the 5-minute decision
brief. The counter is rfc/tools/rfc_skim_check.mjs; the token test skips, not passes, without node or Playwright.
"""
import json
import re
import shutil
import subprocess

import pytest

from okf_bq_graph import sql_baseline as sb

REPO = sb.ROOT.parents[2]
LANDING = REPO / "rfc" / "index.html"
DETAILED = REPO / "rfc" / "detailed-rfc" / "index.html"
TOKENS = "proposed,invented,Knowledge Publications,BigQuery Agent Analytics,2026-09-19"


def test_the_detailed_first_screen_carries_the_decision_brief_terms():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(REPO / "rfc" / "tools" / "rfc_skim_check.mjs"), "rfc/detailed-rfc/index.html",
                          "--window", "800", "--tokens", TOKENS, "--max-rendered", "7500", "--max-minutes", "60"],
                         cwd=REPO, capture_output=True, text=True, timeout=300)
    if out.returncode == 3:
        pytest.skip("Playwright is not resolvable: " + out.stderr.strip())
    result = json.loads(out.stdout)
    assert result["missingInWindow"] == [], result
    assert out.returncode == 0, out.stdout + out.stderr


def test_the_two_pages_link_each_other_as_brief_and_companion():
    detailed = DETAILED.read_text()
    assert re.search(r'<a href="\.\./"><strong>5-minute decision brief', detailed)
    assert "engineering companion of the 5-minute decision brief" in detailed
    assert 'href="detailed-rfc/"' in LANDING.read_text()


def test_the_detailed_page_names_both_roles_the_way_the_brief_does():
    detailed = DETAILED.read_text()
    assert "BigQuery Knowledge Publications · proposed" in detailed
    assert "BigQuery Agent Analytics</span><p>observes use; does not grant access or certify results</p>" in detailed
    for row in ("Recorded feasibility", "Measured retrieval", "Still to validate"):
        assert f"<dt>{row}</dt>" in detailed, row
    assert "over five seconds at five at once" in detailed and "are not measured" in detailed
