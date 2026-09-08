"""The board pack's links to this spike's artifacts have to resolve (PR 46 P2).

PR 46 shipped a card link pinned to `ad18b07`, the revision *before* the file existed, so it
returned 404. Two gates, both offline:

* every relative href on the page resolves to a file on disk;
* every pinned GitHub blob URL into this repository names a path that really exists at that
  revision, checked against the local object store (revisions git does not have are skipped
  rather than assumed good).
"""
import re
import subprocess

import pytest

from okf_bq_graph import sql_baseline as sb

REPO = sb.ROOT.parents[2]
PAGE = REPO / "rfc" / "board-pack" / "index.html"
BLOB = re.compile(r"https://github\.com/caohy1988/caohy1988\.github\.io/blob/([0-9a-f]{7,40})/([^\"#\s]+)")


def _hrefs():
    return re.findall(r'href="([^"]+)"', PAGE.read_text())


def test_the_page_is_where_the_test_thinks_it_is():
    assert PAGE.is_file(), PAGE


def _resolve(href):
    """Site-absolute hrefs are rooted at the repository; a directory is served by its index.html."""
    path = href.split("#")[0].split("?")[0]
    base = REPO if path.startswith("/") else PAGE.parent
    target = (base / path.lstrip("/")).resolve()
    return target / "index.html" if target.is_dir() else target


def test_every_relative_link_resolves_on_disk():
    relative = [h for h in _hrefs() if not h.startswith(("http://", "https://", "#", "mailto:"))]
    assert relative, "the card links to the baseline by relative path; if that stops being true, retire this test"
    missing = [h for h in relative if not _resolve(h).is_file()]
    assert not missing, f"relative links that do not resolve: {missing}"


def test_the_baseline_card_is_one_of_them():
    target = PAGE.parent / "../spikes/bq-graph/evidence/sql-baseline/baseline.md"
    assert target.resolve() == (sb.OUT_DIR / "baseline.md").resolve()
    assert f'href="../spikes/bq-graph/evidence/sql-baseline/baseline.md"' in PAGE.read_text()


def test_every_pinned_blob_link_exists_at_its_revision():
    pins = set(BLOB.findall(PAGE.read_text()))
    assert pins, "the page pins evidence links by revision; if that stops being true, retire this test"
    checked, missing = 0, []
    for rev, path in sorted(pins):
        have_rev = subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{rev}^{{commit}}"],
                                  capture_output=True).returncode == 0
        if not have_rev:
            continue
        checked += 1
        if subprocess.run(["git", "-C", str(REPO), "cat-file", "-e", f"{rev}:{path}"],
                          capture_output=True).returncode != 0:
            missing.append(f"{rev}:{path}")
    if not checked:
        pytest.skip("no pinned revision is present in the local object store")
    assert not missing, f"pinned links whose path does not exist at that revision: {missing}"
