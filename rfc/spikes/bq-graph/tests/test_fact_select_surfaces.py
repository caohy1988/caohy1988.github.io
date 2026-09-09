"""The fact-data selection moved every current-tense surface together (2026-09-09).

Rule from `rfc/board-pack/spec-sqlchain-fact-select.md` §5: SELECTED never appears without "synthetic" beside it,
the customer (Alder) dependency stays its own row or sentence, no surface still says the version is unchosen, and
reader-facing board-pack prose carries no digest, job id, PR number or reviewer name. Dated slice documents are
history and are not gated here.
"""
import re

import pytest

from okf_bq_graph import sql_baseline as sb

REPO = sb.ROOT.parents[2]
SURFACES = {
    "board-pack/index.html": REPO / "rfc" / "board-pack" / "index.html",
    "board-pack/STORY.md": REPO / "rfc" / "board-pack" / "STORY.md",
    "board-pack/spec-sep19-pack.md": REPO / "rfc" / "board-pack" / "spec-sep19-pack.md",
    "rfc/index.html": REPO / "rfc" / "index.html",
    "spike README": sb.ROOT / "README.md",
    "baseline card": sb.OUT_DIR / "baseline.md",
}
STALE = [
    "no selected fact-data version)",              # the parenthetical clause on the two rfc/index.html rows
    "no runner and no selected version of the fact data",
    "Not yet chosen",
    "nobody has picked one",
    "UNSELECTED / INCOMPLETE",
]
READER_FACING = ["board-pack/index.html"]


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_no_current_tense_surface_still_says_the_version_is_unchosen(name):
    text = SURFACES[name].read_text()
    if name == "rfc/index.html":
        # the footer keeps its dated history line; only the two current rows and the newest footer clause are gated
        text = text.replace("its request-to-consumer cells have no runner and no selected fact-data version, its cost cells "
                            "remain unmeasured and every threshold remains proposed · Updated 2026-09-09 (later)", "")
    hits = [s for s in STALE if s in text]
    assert not hits, f"{name} still carries {hits}"


@pytest.mark.parametrize("name", ["board-pack/index.html", "board-pack/STORY.md", "board-pack/spec-sep19-pack.md",
                                  "rfc/index.html", "spike README", "baseline card"])
def test_every_surface_says_synthetic_and_keeps_alder_unselected(name):
    text = SURFACES[name].read_text()
    assert re.search(r"synthetic", text, re.I), f"{name} does not call the selected fact data synthetic"
    if name == "rfc/index.html":
        assert "not customer data" in text and "customer (Alder) data remains unselected" in text
    elif name == "board-pack/index.html":
        assert "Alder’s cohort has never been selected" in text and "not customer data" in text
    else:
        assert re.search(r"Alder[^|\n]{0,80}(never|NOT|not) (been )?selected|NOT SELECTED", text), \
            f"{name} does not keep the Alder cohort unselected as its own statement"


def test_selected_never_appears_without_synthetic_in_the_same_sentence_on_the_pack_tables():
    for name in ("board-pack/STORY.md", "board-pack/spec-sep19-pack.md"):
        for line in SURFACES[name].read_text().splitlines():
            if "**SELECTED" in line:
                assert "synthetic" in line.lower(), f"{name}: {line[:120]}"
                assert "NOT_IMPLEMENTED" in line, f"{name}: the SELECTED row must say the consumer cells stay unrun"


def test_reader_facing_prose_carries_no_digest_job_id_or_pr_number():
    for name in READER_FACING:
        text = SURFACES[name].read_text()
        body = re.sub(r"<a [^>]*>|https?://\S+", "", text)
        assert not re.search(r"\b[0-9a-f]{12,}\b", body), f"{name}: a long hex digest leaked into reader-facing prose"
        assert "bqjob_" not in body and "FACTS_UNSELECTED" not in body
        assert not re.search(r"\bPR ?\d+\b", body)


def test_the_pack_rows_split_the_synthetic_selection_from_the_customer_dependency():
    for name in ("board-pack/STORY.md", "board-pack/spec-sep19-pack.md"):
        text = SURFACES[name].read_text()
        assert "| Fact data and its version (comparison fixture) |" in text
        assert "| Customer fact data (Alder cohort) |" in text
        assert "**NOT SELECTED** — customer dependency" in text
