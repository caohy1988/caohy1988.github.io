"""Both RFC pages stay under the word ceilings set in rfc/rfc-shorten-spec.md.

Counted the way a reader meets the page: headless Chromium, document.body.innerText, every fold opened. The
counter is rfc/tools/rfc_word_count.mjs; the test skips, not passes, when node or Playwright is not resolvable.
"""
import json
import shutil
import subprocess

import pytest

from okf_bq_graph import sql_baseline as sb

REPO = sb.ROOT.parents[2]
CEILINGS = {"rfc/index.html": 1800, "rfc/detailed-rfc/index.html": 7500}


def test_both_pages_stay_under_their_word_ceilings():
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(REPO / "rfc" / "tools" / "rfc_word_count.mjs"), *CEILINGS],
                         cwd=REPO, capture_output=True, text=True, timeout=300)
    if out.returncode == 3:
        pytest.skip("Playwright is not resolvable: " + out.stderr.strip())
    assert out.returncode == 0, out.stdout + out.stderr
    counts = json.loads(out.stdout)
    over = {p: counts[p]["open"] for p in CEILINGS if counts[p]["open"] > CEILINGS[p]}
    assert not over, f"pages over their all-folds-open word ceiling {CEILINGS}: {over}"
    for p in CEILINGS:
        assert counts[p]["rendered"] <= counts[p]["open"]
