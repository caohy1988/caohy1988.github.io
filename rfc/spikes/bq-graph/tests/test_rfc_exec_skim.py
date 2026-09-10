"""The /rfc/ landing page stays a five-minute decision brief (rfc/rfc-exec-skim-spec.md §4, gates G1, G3, G4).

Rendered words (folds closed) at most 950; the first 450 rendered words name the proposal, the data, the feature,
the pilot and the checkpoint date; rendered words divided by 230 fit in five minutes. The counter is
rfc/tools/rfc_skim_check.mjs; the test skips, not passes, when node or Playwright is not resolvable.
"""
import json
import shutil
import subprocess

import pytest

from okf_bq_graph import sql_baseline as sb

REPO = sb.ROOT.parents[2]


def test_the_landing_page_reads_as_a_five_minute_decision_brief():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(REPO / "rfc" / "tools" / "rfc_skim_check.mjs"), "rfc/index.html"],
                         cwd=REPO, capture_output=True, text=True, timeout=300)
    if out.returncode == 3:
        pytest.skip("Playwright is not resolvable: " + out.stderr.strip())
    result = json.loads(out.stdout)
    assert result["rendered"] <= 950, result
    assert result["missingInWindow"] == [], result
    assert result["minutes"] <= 5, result
    assert out.returncode == 0, out.stdout + out.stderr
