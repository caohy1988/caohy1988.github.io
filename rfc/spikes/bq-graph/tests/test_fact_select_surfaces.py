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
    # PR 62 moved the pages: the board-pack story is the /rfc/ landing page and the full technical RFC lives at
    # /rfc/detailed-rfc/. The keys keep their pre-move names because the rules below are keyed by surface role.
    "board-pack/index.html": REPO / "rfc" / "index.html",
    "board-pack/STORY.md": REPO / "rfc" / "board-pack" / "STORY.md",
    "board-pack/spec-sep19-pack.md": REPO / "rfc" / "board-pack" / "spec-sep19-pack.md",
    "rfc/index.html": REPO / "rfc" / "detailed-rfc" / "index.html",
    "spike README": sb.ROOT / "README.md",
    "baseline card": sb.OUT_DIR / "baseline.md",
}
STALE = [
    r"\bhas no runner\b(?! yet)",                          # FS-1 (2026-09-09): the runner exists, hermetic only
    r"\bhave no runner\b",
    r"no sampled runner exists",
    r"runner does not exist",
    r"No runner exists",
    r"\bno runner yet\b",
    r"no selected (version of the )?fact[- ]?data version",
    r"no selected fact version",
    r"no selected version of the fact data",
    r"FACTS_UNSELECTED \+ NOT_IMPLEMENTED",          # the pre-selection refusal order, as a current summary
    r"Not yet chosen",
    r"nobody has picked one",
    r"UNSELECTED / INCOMPLETE",
    r"checks the live tables against that digest",   # Astra P2 #1: a count check is not a digest check
]
READER_FACING = ["board-pack/index.html"]


@pytest.mark.parametrize("name", sorted(SURFACES))
def test_no_current_tense_surface_still_says_the_version_is_unchosen(name):
    text = SURFACES[name].read_text()
    if name == "rfc/index.html":
        # the footer keeps its dated history line; only the two current rows and the newest footer clause are gated
        text = text.replace("its request-to-consumer cells have no runner and no selected fact-data version, its cost cells "
                            "remain unmeasured and every threshold remains proposed · Updated 2026-09-09 (later)", "")
        # the second dated clause is history too (state at the fact selection); the evening clause is the current one
        text = text.replace("consumer cells still have no runner, customer (Alder) data remains unselected, the live rows are "
                            "unverified against the digest, cost cells remain unmeasured and every threshold remains proposed · "
                            "Updated 2026-09-09 (FS-1)", "")
    hits = [pattern for pattern in STALE if re.search(pattern, text)]
    assert not hits, f"{name} still carries {hits}"


def test_the_three_summaries_astra_named_now_say_synthetic_selected_and_alder_unselected():
    story = SURFACES["board-pack/STORY.md"].read_text()
    assert "two request-to-consumer cells with **a hermetic-only runner, no live attempt sampled**" in story and "their fact version is now a selected synthetic fixture" in story
    rfc = SURFACES["rfc/index.html"].read_text()
    assert "request-to-consumer cells have a hermetic-only runner, never run live (their fact data is a selected synthetic fixture, not customer data; the Alder cohort stays unselected)" in rfc
    readme = SURFACES["spike README"].read_text()
    assert "Consumer cells (`sqlchain_*`) are refused: `NOT_IMPLEMENTED` (no sampled runner) until the FS-1 hermetic-only runner landed on 2026-09-09 and `RUNNER_HERMETIC_ONLY` since" in readme


def test_no_surface_says_a_count_check_verifies_the_digest():
    for name, path in SURFACES.items():
        text = path.read_text()
        assert not re.search(r"checks? the live (tables|rows) against (that|the) digest", text), name
    page = SURFACES["board-pack/index.html"].read_text()
    assert "match the rows and columns to their own digest, not the script’s" in page and "no live run has done this yet" in page


SDLC_DOCS = {name: REPO / "rfc" / "board-pack" / f"{name}-sqlchain-fact-select.md" for name in ("intent", "spec", "plan")}
SCRIPT_DIGEST_AS_TARGET = [
    r"match (it|them) to that digest",                       # "that digest" was the script digest on the page
    r"checks? the live (tables|rows) against (that|the) digest",
    r"live precheck \(row counts and",                       # the counts-and-result-only summary
    r"pinned by the digest of the\s+script that loads them and by the job that loaded them; a run checks",
]


def test_the_readback_target_is_the_content_digest_not_the_script_digest():
    """Astra re-review of 93e3534: fixture_sha256 (script) and content_manifest_sha256 (rows and columns) are
    different identities; every surface that names a readback target names the content digest."""
    page = SURFACES["board-pack/index.html"].read_text()
    assert "a digest of the rows and columns themselves" in page
    for name, path in SDLC_DOCS.items():
        text = path.read_text()
        hits = [p for p in SCRIPT_DIGEST_AS_TARGET if re.search(p, text)]
        assert not hits, f"{name}: {hits}"
    spec = SDLC_DOCS["spec"].read_text()
    assert "match the rows and columns to the content digest, not the script digest" in spec
    intent = SDLC_DOCS["intent"].read_text()
    assert "matched to the content digest, the digest of the rows and columns rather than" in intent
    plan = SDLC_DOCS["plan"].read_text()
    assert "matched to the content digest" in plan
    card = SURFACES["baseline card"].read_text()
    assert "requires its digest to equal content_manifest_sha256" in card
    for name, path in SURFACES.items():
        assert not re.search(r"match (it|them) to that digest", path.read_text()), name


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
                assert "RUNNER_HERMETIC_ONLY" in line, f"{name}: the SELECTED row must say the consumer cells stay unrun (hermetic only)"


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
