import json
from okf_bq_graph.compile import compile_bundle, validate_projection, Compiler
from okf_bq_graph import SOURCE_PIN

L = lambda i: i.split("|", 3)[3]


def test_projection_is_deterministic_and_closed(sample_root):
    a = compile_bundle(sample_root, "acme_retail", SOURCE_PIN)
    b = compile_bundle(sample_root, "acme_retail", SOURCE_PIN)
    assert a == b
    assert validate_projection(a)["valid"]
    ids = {node["node_id"] for node in a["nodes"]}
    assert all(edge["src_id"] in ids and edge["dst_id"] in ids for edge in a["edges"])
    assert a["publication_id"].startswith("pub_")
    assert all(n["node_id"].startswith(f"acme_retail|{a['publication_id']}|") for n in a["nodes"])


def test_acme_landmine_structure(sample_root):
    p = compile_bundle(sample_root, "acme_retail", SOURCE_PIN)
    links = {(L(e["src_id"]), L(e["dst_id"])) for e in p["edges"] if e["relation"] == "LINKS_TO"}
    assert ("metrics/gross-margin-legacy", "metrics/gross-margin") in links
    assert ("metrics/gross-margin", "computations/gross-margin-period") in links
    # legacy has no direct link to any computation
    assert not any(s == "metrics/gross-margin-legacy" and d.startswith("computations/") for s, d in links)
    kinds = p["counts"]["nodes_by_kind"]
    assert kinds["Concept"] == 9 and kinds["Artifact"] == 2 and kinds["LogEntry"] == 4
    assert p["counts"]["stubs"] == 0            # original backlog is empty
    # attester/executor resolved only via root fallback and labelled inferred
    for e in p["edges"]:
        if e["relation"] in ("EXECUTED_BY", "ATTESTED_BY"):
            assert e["resolution"] == "root_fallback" and e["inferred"] is True
    # attester is an Artifact, never a Concept
    art = [n for n in p["nodes"] if n["kind"] == "Artifact" and n["path"] == "attesters/sql_equality.py"]
    assert len(art) == 1 and art[0]["stub"] is False
    # unknown frontmatter preserved (`not:` on metrics/gross-margin)
    gm = next(n for n in p["nodes"] if L(n["node_id"]) == "metrics/gross-margin")
    assert "not" in json.loads(gm["extra_frontmatter"])
    assert gm["stale_after"] == "2026-12-31T00:00:00Z"   # authored text, not a datetime


def test_second_bundle_scope_and_negatives(sample_root, bundle_b_root):
    a = compile_bundle(sample_root, "acme_retail", SOURCE_PIN)
    b = compile_bundle(bundle_b_root, "bundle_b", "fixture")
    assert validate_projection(b)["valid"]
    # identical relative paths never collide across bundles
    ida = {n["node_id"] for n in a["nodes"]}
    idb = {n["node_id"] for n in b["nodes"]}
    assert ida.isdisjoint(idb)
    assert {L(i) for i in ida} & {L(i) for i in idb}   # same local ids exist in both
    # missing target -> non-executable stub with referring edges
    stubs = [n for n in b["nodes"] if n["kind"] == "Concept" and n["stub"]]
    # (the fixture's executor skills/run-on-bq.md does not exist in bundle B -> stub resource, resolved relative-first)
    assert {L(n["node_id"]) for n in stubs} == {"metrics/not-written", "computations/missing-comp", "computations/skills/run-on-bq"}
    assert all(n["type"] == "Concept" and n["runtime"] is None and n["text"] is None for n in stubs)
    # escape rejected: no node, recorded rejection
    assert not any("passwd" in n["node_id"] for n in b["nodes"])
    assert any(r["reason"] == "escapes bundle" for r in b["rejections"])
    # duplicate hits: two LINKS_TO edges from legacy to gross-margin in the same section (distinct raw), and one MENTIONS
    legacy = "metrics/gross-margin-legacy"
    dup = [e for e in b["edges"] if e["relation"] == "LINKS_TO" and L(e["src_id"]) == legacy and L(e["dst_id"]) == "metrics/gross-margin"]
    assert len(dup) == 3   # Deprecated section (1) + Duplicate hits section (2 distinct raw targets)
    mentions = [e for e in b["edges"] if e["relation"] == "MENTIONS" and L(e["dst_id"]) == "metrics/gross-margin"
                and L(e["src_id"]).startswith(legacy + "#")]
    assert len(mentions) == 2   # one per section, deduplicated within a section
    # unknown frontmatter preserved
    lg = next(n for n in b["nodes"] if L(n["node_id"]) == legacy)
    assert json.loads(lg["extra_frontmatter"]) == {"custom_key": "preserved"}


def test_strict_path_resolution(bundle_b_root):
    c = Compiler(bundle_b_root, "bundle_b", "fixture")
    assert c.resolve("/metrics/gross-margin.md", "metrics") == ("metrics/gross-margin.md", "absolute")
    assert c.resolve("./gross-margin.md", "metrics") == ("metrics/gross-margin.md", "relative")
    assert c.resolve("../computations/gross-margin-period.md", "metrics") == ("computations/gross-margin-period.md", "relative")
    assert c.resolve("../../../etc/passwd.md", "metrics")[1] == "escape"
    assert c.resolve("/../etc/passwd.md", "metrics")[1] == "escape"
    assert c.resolve("https://example.com/x.md", "metrics") == (None, "url")
    assert c.resolve("nope.md", "metrics") == ("metrics/nope.md", "unresolved")
    assert c.resolve("policies/margin-standard.md", "metrics") == ("policies/margin-standard.md", "root_fallback")
