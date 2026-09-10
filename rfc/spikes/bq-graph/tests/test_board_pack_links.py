"""The published RFC pages' links to this spike's artifacts have to resolve (PR 46 P2).

PR 46 shipped a card link pinned to `ad18b07`, the revision *before* the file existed, so it
returned 404. Two gates, both offline:

* every relative href on the page resolves to a file on disk;
* every pinned GitHub blob URL into this repository names a path that really exists at that
  revision, checked against the local object store (revisions git does not have are skipped
  rather than assumed good).

Since the /rfc/ restructure the board pack is the landing page at `rfc/index.html` and the full
technical RFC lives at `rfc/detailed-rfc/index.html`; both are gated. The old
`rfc/board-pack/` and `rfc/bq-vp/` addresses stay as redirect stubs pointing at `/rfc/`, fragment
intact, and the landing page forwards the old technical RFC's bookmarks to `/rfc/detailed-rfc/`.
"""
import json
import re
import shutil
import subprocess

import pytest

from okf_bq_graph import sql_baseline as sb

REPO = sb.ROOT.parents[2]
PAGE = REPO / "rfc" / "index.html"
DETAILED = REPO / "rfc" / "detailed-rfc" / "index.html"
PAGES = {"board-pack landing": PAGE, "detailed RFC": DETAILED}
REDIRECTS = [REPO / "rfc" / "board-pack" / "index.html", REPO / "rfc" / "bq-vp" / "index.html"]
BLOB = re.compile(r"https://github\.com/caohy1988/caohy1988\.github\.io/blob/([0-9a-f]{7,40})/([^\"#\s]+)")


def _hrefs(page):
    return re.findall(r'href="([^"]+)"', page.read_text())


@pytest.mark.parametrize("page", PAGES.values(), ids=list(PAGES))
def test_the_page_is_where_the_test_thinks_it_is(page):
    assert page.is_file(), page


def _resolve(page, href):
    """Site-absolute hrefs are rooted at the repository; a directory is served by its index.html."""
    path = href.split("#")[0].split("?")[0]
    base = REPO if path.startswith("/") else page.parent
    target = (base / path.lstrip("/")).resolve()
    return target / "index.html" if target.is_dir() else target


@pytest.mark.parametrize("page", PAGES.values(), ids=list(PAGES))
def test_every_relative_link_resolves_on_disk(page):
    relative = [h for h in _hrefs(page) if not h.startswith(("http://", "https://", "#", "mailto:"))]
    assert relative, "the page links the baseline by relative path; if that stops being true, retire this test"
    missing = [h for h in relative if not _resolve(page, h).is_file()]
    assert not missing, f"relative links that do not resolve from {page.relative_to(REPO)}: {missing}"


def test_the_baseline_card_is_one_of_them():
    target = PAGE.parent / "spikes/bq-graph/evidence/sql-baseline/baseline.md"
    assert target.resolve() == (sb.OUT_DIR / "baseline.md").resolve()
    assert 'href="spikes/bq-graph/evidence/sql-baseline/baseline.md"' in PAGE.read_text()


def test_the_landing_page_and_the_detailed_rfc_link_each_other():
    assert 'href="detailed-rfc/"' in PAGE.read_text()
    assert _resolve(PAGE, "detailed-rfc/") == DETAILED
    detailed = DETAILED.read_text()
    assert 'href="../"' in detailed
    assert _resolve(DETAILED, "../") == PAGE
    assert '<a href="/rfc/detailed-rfc/" aria-current="page">Detailed RFC</a>' in detailed


def test_the_moved_pages_declare_their_new_canonical_addresses():
    assert '<link rel="canonical" href="https://caohy1988.github.io/rfc/">' in PAGE.read_text()
    assert '<link rel="canonical" href="https://caohy1988.github.io/rfc/detailed-rfc/">' in DETAILED.read_text()
    assert 'href="styles.css"' in PAGE.read_text() and (PAGE.parent / "styles.css").is_file()


@pytest.mark.parametrize("stub", REDIRECTS, ids=[p.parent.name for p in REDIRECTS])
def test_old_addresses_redirect_to_the_landing_page_keeping_the_fragment(stub):
    """PR 62 Astra P2 #1: a meta refresh drops `#sep19-envelope`; the script forwards it, the refresh is the
    no-script fallback."""
    text = stub.read_text()
    assert '<script>location.replace("/rfc/" + location.hash);</script>' in text
    assert '<noscript><meta http-equiv="refresh" content="0; url=/rfc/"></noscript>' in text
    assert text.index("<script>") < text.index("<noscript>")
    assert '<link rel="canonical" href="https://caohy1988.github.io/rfc/">' in text
    assert "/rfc/board-pack/" not in text, "the stub must not send readers back to the retired address"


SVG_DEFS = {"marker", "lineargradient", "radialgradient", "filter", "pattern", "clippath", "symbol", "mask"}
LEGACY_LIST = re.compile(r"var legacy = (\[[^\]]*\]);")


def _section_ids(page):
    return {i for tag, i in re.findall(r'<(\w+)[^>]*\sid="([^"]+)"', page.read_text()) if tag.lower() not in SVG_DEFS}


def test_the_landing_page_forwards_every_old_technical_bookmark_and_none_of_its_own():
    """PR 62 Astra P2 #2: `/rfc/#current-evidence` used to be a technical-RFC bookmark. The landing page
    forwards exactly the detailed page's section ids it does not define itself, on load and on hash change."""
    text = PAGE.read_text()
    m = LEGACY_LIST.search(text)
    assert m, "the landing page carries the legacy-bookmark forwarder"
    legacy = set(json.loads(m.group(1)))
    expected = _section_ids(DETAILED) - _section_ids(PAGE)
    assert legacy == expected, f"stale forwarder list; regenerate from the pages: {sorted(legacy ^ expected)}"
    assert {"architecture", "repro", "current-evidence", "summary"} <= legacy
    assert not (legacy & _section_ids(PAGE)), "the landing page's own anchors must stay on /rfc/"
    assert "sep19-envelope" in _section_ids(PAGE) and "sep19-envelope" not in legacy
    assert 'location.replace("detailed-rfc/#" + h)' in text
    assert 'window.addEventListener("hashchange", forward)' in text
    assert text.index("var legacy") < text.index("<body"), "forward before the story renders"


def test_both_demos_carry_the_detailed_rfc_nav_item():
    """PR 62 Astra P2 #3. Since the shared site chrome (research/site-nav-spec.md) both links sit inside the
    Builds folder of the generated block; the demos still mark /rfc/ as the current page."""
    for demo in ("demo", "full-demo"):
        text = (REPO / "rfc" / demo / "index.html").read_text()
        block = text[text.index("<!-- site-nav:start -->"):text.index("<!-- site-nav:end -->")]
        rfc = block.index('<a href="/rfc/" aria-current="page">RFC</a>')
        detailed = block.index('<a href="/rfc/detailed-rfc/">Detailed RFC</a>')
        assert rfc < detailed, demo
        assert block.count('aria-current="page"') == 1, demo


def test_routes_in_a_real_browser():
    """rfc/tools/check_rfc_routes.mjs drives headless Chromium over a loopback static server: the retired
    addresses and the old technical bookmarks forward with their fragment, the landing page's own anchors
    stay, both demos show the nav item. Skipped, not passed, when node or Playwright is not resolvable."""
    node = shutil.which("node")
    if not node:
        pytest.skip("node is not installed")
    out = subprocess.run([node, str(REPO / "rfc" / "tools" / "check_rfc_routes.mjs")], capture_output=True, text=True, timeout=300)
    if out.returncode == 3:
        pytest.skip("Playwright is not resolvable: " + out.stderr.strip())
    assert out.returncode == 0, out.stdout + out.stderr
    assert "all routes behave" in out.stdout


@pytest.mark.parametrize("page", PAGES.values(), ids=list(PAGES))
def test_every_pinned_blob_link_exists_at_its_revision(page):
    pins = set(BLOB.findall(page.read_text()))
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
