"""Window orchestrator: open reservation -> integration (GQL) -> landmine/impact/backlog evidence
-> benchmark cells -> close reservation. A watchdog closes the window on exception or deadline.

Usage: python -m okf_bq_graph.run integration|benchmark [--minutes N]
"""
from __future__ import annotations

import datetime as _dt
import json
import sys
import threading
import time
import traceback

from google.cloud import bigquery

from . import PROJECT, LOCATION, DATASET, BUNDLE_ID
from .compile import compile_bundle
from .oracle import Graph
from .publish import resolve_pointer
from .reservation import open_window, close_window
from .retrieve import retrieve, impact, stub_backlog
from .benchmark import measure

ACME_ROOT = "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _client_factory():
    local = threading.local()

    def get() -> dict:
        if not hasattr(local, "c"):
            local.c = bigquery.Client(project=PROJECT, location=LOCATION)
        return {"engine": "gql", "bq": local.c, "use_cache": False}
    return get


def integration(client: bigquery.Client, cases: dict, pub: str, out: dict) -> None:
    from . import SOURCE_PIN
    proj = compile_bundle(ACME_ROOT, BUNDLE_ID, SOURCE_PIN)
    assert proj["publication_id"] == pub, (proj["publication_id"], pub)
    g = Graph(proj)
    gql = {"engine": "gql", "bq": client}
    fb = {"engine": "fallback", "bq": client}
    as_of = cases["as_of"]
    out["forced"] = {}
    for f in cases["forced_seeds"]:
        r = retrieve(f["text"], BUNDLE_ID, pub, "operator", as_of, gql)
        o = g.governed(f["text"][len("forced:"):-3], as_of)
        parity = {
            "gql_status": r["status"],
            "hops_ok": bool(r["paths"]) and r["paths"][0]["concept_hops"] == f["expect_hops"],
            "computation_ok": bool(r["computations"]) and r["computations"][0]["path"] == f["expect_computation"],
            "sql_sha_matches_oracle": bool(r["computations"]) and r["computations"][0]["sql_sha256"] == o["computations"][0]["sql_sha256"],
            "trust_matches_oracle": r["concepts"] and r["concepts"][0]["trust_tier"] == o["trust_tier"],
            "replacement_matches_oracle": r["concepts"] and r["concepts"][0]["replacement"] == o["replacement"],
            "freshness_matches_oracle": r["concepts"] and r["concepts"][0]["freshness"] == o["freshness"],
            "via_matches_oracle": bool(r["paths"]) and r["paths"][0]["via"] == o["paths"][0]["via"],
            "timing": r["timing"],
        }
        out["forced"][f["id"]] = {"result": r, "oracle": o, "parity": parity}
        print(f["id"], {k: v for k, v in parity.items() if k != "timing"}, r["timing"]["total_ms"], "ms")
    out["natural"] = {}
    for q in cases["natural_queries"][:2]:
        r = retrieve(q["text"], BUNDLE_ID, pub, "operator", as_of, gql)
        out["natural"][q["id"]] = r
        print(q["id"], r["status"], [(c["concept"], c["lifecycle_status"]) for c in r["concepts"]],
              [(p["seed"], p["concept_hops"]) for p in r["paths"]], r["timing"]["total_ms"], "ms")
    imp = impact(cases["impact_target"], BUNDLE_ID, pub, "operator", gql)
    oi = g.impact(cases["impact_target"][:-3])
    imp["parity"] = {"same_set": {x["impacted"] for x in imp.get("impacted", [])} == {x["impacted"] for x in oi["impacted"]},
                     "same_min_hops": {x["impacted"]: x["hops"] for x in imp.get("impacted", [])} == {x["impacted"]: x["hops"] for x in oi["impacted"]}}
    out["impact"] = {"gql": imp, "oracle": oi}
    print("impact", imp["status"], imp.get("parity"), imp["timing"]["total_ms"], "ms", [(x["impacted"], x["hops"]) for x in imp.get("impacted", [])])
    sb = stub_backlog(BUNDLE_ID, pub, "operator", gql)
    out["backlog_acme"] = sb
    print("backlog acme", sb["status"], sb["backlog"])
    # injected-stub fixture (bundle_b)
    pb = resolve_pointer(client, "bundle_b")
    if pb:
        gb = Graph(compile_bundle("fixtures/bundle_b", "bundle_b", "fixture"))
        sbb = stub_backlog("bundle_b", pb, "operator", gql)
        sbb["parity"] = sbb.get("backlog") == gb.stub_backlog()
        out["backlog_bundle_b"] = sbb
        print("backlog bundle_b", sbb["status"], sbb["parity"], [x["missing_concept"] for x in sbb.get("backlog", [])])
        rb = retrieve("forced:metrics/gross-margin-legacy.md", "bundle_b", pb, "operator", as_of, gql)
        out["ambiguous_bundle_b"] = rb
        print("bundle_b ambiguous", rb["status"], rb["concepts"][0]["replacement"] if rb["concepts"] else None,
              [(c["concept"], c["concept_hops"]) for c in rb["computations"]])
        # cross-bundle isolation: acme seed with bundle_b publication must fail closed
        rx = retrieve("forced:metrics/gross-margin-legacy.md", "acme_retail", pb, "operator", as_of, gql)
        out["cross_scope"] = {"status": rx["status"], "computations": rx["computations"], "warnings": rx["warnings"]}
        print("cross-scope", rx["status"], len(rx["computations"]))
    # fallback parity on the same publication
    rf = retrieve("forced:metrics/gross-margin-legacy.md", BUNDLE_ID, pub, "operator", as_of, fb)
    out["fallback_forced"] = rf
    print("fallback", rf["status"], rf["paths"], rf["timing"]["total_ms"], "ms")
    governance(client, pub, as_of, out)


def _leaks(obj, needle: str) -> bool:
    return needle in json.dumps(obj, default=str)


def governance(client: bigquery.Client, pub: str, as_of: str, out: dict) -> None:
    """Spec §5 cases measurable under the operator identity with real policy objects (see authz.py)."""
    from .authz import RLS_DS, META_DS, AV_DS, HIDDEN, BLOCKED_CASES, revoke, restore
    gov: dict = {"blocked": BLOCKED_CASES}
    legacy = "forced:metrics/gross-margin-legacy.md"
    # (1) hidden intermediate inside GQL traversal (RLS)
    c = {"engine": "gql", "bq": client, "ds": RLS_DS}
    r = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, c)
    gov["rls_hidden_intermediate"] = {"status": r["status"], "computations": len(r["computations"]), "paths": r["paths"],
                                      "replacement": r["concepts"][0]["replacement"] if r["concepts"] else None,
                                      "leaks_hidden_id": _leaks(r, HIDDEN), "warnings": r["warnings"], "timing": r["timing"]["total_ms"],
                                      "verdict": "ENFORCED" if (r["computations"] == [] and not _leaks(r, HIDDEN) and r["status"] in ("OK", "DENIED")) else "LEAK_OR_UNEXPECTED"}
    print("rls hidden intermediate:", gov["rls_hidden_intermediate"]["verdict"], r["status"], len(r["computations"]), "leak", _leaks(r, HIDDEN))
    # natural query on the RLS dataset: hidden sections must not seed
    rn = retrieve("How do we calculate gross margin, exactly?", BUNDLE_ID, pub, "operator", as_of, c)
    gov["rls_natural"] = {"status": rn["status"], "seeds": [x["concept"] for x in rn["concepts"]], "leaks_hidden_id": _leaks(rn, HIDDEN),
                          "computations": [(x["seed"], x["concept"], x["concept_hops"]) for x in rn["computations"]]}
    print("rls natural:", gov["rls_natural"])
    # impact on RLS dataset must not route through the hidden node
    ri = impact("policies/margin-standard.md", BUNDLE_ID, pub, "operator", c)
    gov["rls_impact"] = {"status": ri["status"], "impacted": [(x["impacted"], x["hops"]) for x in ri.get("impacted", [])], "leaks_hidden_id": _leaks(ri, HIDDEN)}
    print("rls impact:", gov["rls_impact"])
    # (2) metadata visible, source denied
    cm = {"engine": "gql", "bq": client, "ds": META_DS}
    rm = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, cm)
    gov["meta_source_denied"] = {"status": rm["status"], "paths": rm["paths"], "sql_withheld": all(x["sql"] is None for x in rm["computations"]),
                                 "warnings": rm["warnings"], "verdict": "WITHHELD" if rm["computations"] and all(x["sql"] is None for x in rm["computations"]) else "UNEXPECTED"}
    print("meta source denied:", gov["meta_source_denied"]["verdict"], rm["paths"])
    # (3) revoke before cached replay (real policy change on _rls)
    cache: dict = {}
    cc = {"engine": "gql", "bq": client, "ds": RLS_DS, "cache": cache}
    warm = retrieve("forced:metrics/revenue.md", BUNDLE_ID, pub, "operator", as_of, cc)
    hit = retrieve("forced:metrics/revenue.md", BUNDLE_ID, pub, "operator", as_of, cc)
    rev = revoke(client)
    time.sleep(5)
    replay = retrieve("forced:metrics/revenue.md", BUNDLE_ID, pub, "operator", as_of, cc)
    fresh = retrieve("forced:metrics/revenue.md", BUNDLE_ID, pub, "operator", as_of, {"engine": "gql", "bq": client, "ds": RLS_DS})
    res = restore(client)
    gov["revoke_before_cached_replay"] = {"warm": (warm["status"], warm["scope"].get("cache")), "hit": (hit["status"], hit["scope"].get("cache")),
                                         "revoked_at": rev["at"], "replay": (replay["status"], replay["scope"].get("cache"), len(replay["computations"])),
                                         "fresh_after_revoke": (fresh["status"], len(fresh["computations"]), fresh["warnings"][:2]),
                                         "restored_at": res["at"],
                                         "verdict": "FAIL_CLOSED" if replay["status"] != "OK" and replay["computations"] == [] and fresh["computations"] == [] else "LEAK_OR_UNEXPECTED"}
    print("revoke before cached replay:", gov["revoke_before_cached_replay"])
    # (4) authorized views: graph over views
    setup = json.load(open("evidence/authz_setup.json"))
    gov["authorized_views"] = {"graph_over_views": setup.get("graph_over_views"), "error": setup.get("graph_av", {}).get("error")}
    if setup.get("graph_over_views") == "ACCEPTED":
        ca = {"engine": "gql", "bq": client, "ds": AV_DS}
        ra = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, ca)
        gov["authorized_views"].update({"status": ra["status"], "computations": len(ra["computations"]), "leaks_hidden_id": _leaks(ra, HIDDEN),
                                        "warnings": ra["warnings"], "timing": ra["timing"]["total_ms"],
                                        "verdict": "ENFORCED" if ra["computations"] == [] and not _leaks(ra, HIDDEN) else "LEAK_OR_UNEXPECTED"})
    print("authorized views:", gov["authorized_views"])
    # (5) publication consistency: concurrent requests during a re-publish must each use one pin
    gov["publication_consistency"] = publication_consistency(client, pub, as_of)
    print("publication consistency:", gov["publication_consistency"])
    out["governance"] = gov


def publication_consistency(client: bigquery.Client, pub: str, as_of: str) -> dict:
    """Publish a changed source (bundle_b variant) while issuing concurrent 'active'-pointer requests;
    every response must carry exactly one publication id across seed/walk/SQL. Then a failed publish
    (injected before pointer switch) must leave the old pointer."""
    import shutil, tempfile
    from concurrent.futures import ThreadPoolExecutor
    from .publish import publish, resolve_pointer
    tmp = tempfile.mkdtemp()
    shutil.copytree("fixtures/bundle_b", f"{tmp}/bundle_b")
    with open(f"{tmp}/bundle_b/metrics/gross-margin-alt.md", "a") as fh:
        fh.write("\n\n# Changed\n\nRe-published during concurrent requests (publication consistency test).\n")
    proj = compile_bundle(f"{tmp}/bundle_b", "bundle_b", "fixture-changed")
    before = resolve_pointer(client, "bundle_b")
    results = []

    def req(i):
        c = {"engine": "gql", "bq": bigquery.Client(project=PROJECT, location=LOCATION)}
        r = retrieve("forced:metrics/gross-margin-legacy.md", "bundle_b", "active", f"consistency-{i}", as_of, c)
        pubs = {r["scope"]["publication_id"]} | {x.split("|")[1] for cc in r["computations"] for x in [cc.get("sql_sha256") or ""] if "|" in x}
        return {"i": i, "status": r["status"], "publication_id": r["scope"]["publication_id"], "n_pubs_seen": len(pubs), "hops": [p["concept_hops"] for p in r["paths"]]}
    with ThreadPoolExecutor(max_workers=4) as ex:
        futs = [ex.submit(req, i) for i in range(6)]
        pubres = publish(proj, client, manifest_path="evidence/publish_log.jsonl")
        results = [f.result() for f in futs]
    after = resolve_pointer(client, "bundle_b")
    # failed publish: injected failure before pointer switch, using a third variant
    with open(f"{tmp}/bundle_b/metrics/gross-margin-alt.md", "a") as fh:
        fh.write("\n\nSecond change (failed publish test).\n")
    proj3 = compile_bundle(f"{tmp}/bundle_b", "bundle_b", "fixture-failed")
    try:
        publish(proj3, client, inject_failure="before_pointer", manifest_path="evidence/publish_log.jsonl")
        failed_ok = False
    except RuntimeError:
        failed_ok = True
    after_failed = resolve_pointer(client, "bundle_b")
    seen = {r["publication_id"] for r in results}
    return {"pointer_before": before, "published": pubres["publication_id"], "pointer_after": after, "concurrent": results,
            "all_single_pin": all(r["n_pubs_seen"] == 1 for r in results), "pins_seen": sorted(seen),
            "pins_subset_of_old_new": seen <= {before, pubres["publication_id"]},
            "failed_publish_raised": failed_ok, "pointer_after_failed_publish": after_failed,
            "failed_publish_left_pointer": after_failed == after, "failed_publication_id": proj3["publication_id"]}


def benchmark(client: bigquery.Client, cases: dict, pub: str, out: dict, deadline: float, cells_spec: list[dict]) -> None:
    queries = [dict(q, bundle_id=BUNDLE_ID) for q in cases["natural_queries"]] + \
              [dict(q, bundle_id=BUNDLE_ID) for q in cases["forced_seeds"]]
    cells = []
    corpora = {"acme": {"ds": DATASET, "bundles": None}}
    for c in ("copies_100", "copies_1000"):
        try:
            sc = json.load(open(f"evidence/scale_{c}.json"))
            corpora[c] = {"ds": sc["ds"], "bundles": [(b, v["publication_id"]) for b, v in sorted(sc["publications"].items())]}
        except FileNotFoundError:
            corpora[c] = None
    for spec in cells_spec:
        corp = corpora.get(spec.get("corpus", "acme"))
        if corp is None:
            out.setdefault("skipped_cells", []).append({"cell": spec["name"], "state": "NOT_RUN", "reason": "corpus not published"})
            continue
        cells.append({"name": spec["name"], "engine": spec.get("engine", "gql"), "corpus": spec.get("corpus", "acme"),
                      "ds": corp["ds"], "bundles": corp["bundles"],
                      "publication_id": spec.get("publication_id", pub), "concurrency": spec["concurrency"],
                      "warmups": spec.get("warmups", 20), "measured": spec.get("measured", 100), "as_of": cases["as_of"],
                      "seed": spec.get("seed", 20260905), "timeout_s": 60, "model": "text-embedding-005"})
    cfg = {"cells": cells, "queries": queries, "budget": {"cell_seconds": 1500, "deadline_monotonic": deadline}}
    out["benchmark"] = measure(cfg, _client_factory())


def main(argv: list[str]) -> int:
    mode = argv[1]
    minutes = int(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else (25 if mode == "integration" else 85)
    # cumulative allowance guard: two hours across all windows (spec §6)
    used = 0.0
    try:
        for w in json.load(open("evidence/cleanup_manifest.json"))["windows"]:
            if w.get("opened_at") and w.get("closed_at"):
                used += (_dt.datetime.fromisoformat(w["closed_at"].replace("Z", "+00:00")) - _dt.datetime.fromisoformat(w["opened_at"].replace("Z", "+00:00"))).total_seconds() / 60
    except Exception:  # noqa: BLE001
        pass
    minutes = int(min(minutes, max(0, 120 - used - 2)))
    print(f"cumulative reservation minutes used so far: {used:.1f}; this window budget: {minutes} min", flush=True)
    cases = json.load(open("fixtures/cases.json"))
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    pub = resolve_pointer(client, BUNDLE_ID)
    label = f"{mode}-{_dt.datetime.now(_dt.timezone.utc).strftime('%H%M')}"
    out: dict = {"mode": mode, "label": label, "publication_id": pub, "started_at": _now()}
    deadline = time.monotonic() + minutes * 60
    stop = threading.Event()

    def watchdog():
        while not stop.wait(15):
            if time.monotonic() > deadline + 120:
                print("WATCHDOG: hard deadline exceeded; closing window", flush=True)
                close_window(label)
                stop.set()
    threading.Thread(target=watchdog, daemon=True).start()
    w = open_window(label)
    out["window_open"] = {"opened_at": w["opened_at"]}
    # assignment propagation is not atomic: jobs route inconsistently for a few minutes. Require 6 consecutive
    # successful trivial GQL jobs (≥10 s apart) before measuring; record how long propagation took.
    ok_streak, attempts, t_prop = 0, 0, time.monotonic()
    while ok_streak < 6 and attempts < 60:
        attempts += 1
        try:
            j = client.query(f"SELECT COUNT(*) FROM GRAPH_TABLE(`{PROJECT}.{DATASET}.okf_graph` MATCH (n:Node) COLUMNS (n.node_id))",
                             job_config=bigquery.QueryJobConfig(use_query_cache=False), location=LOCATION)
            j.result(); ok_streak += 1; out["assignment_ready_job"] = j.job_id
        except Exception as e:  # noqa: BLE001
            ok_streak = 0; print("waiting for assignment:", str(e).split("\n")[0][:100], flush=True)
        time.sleep(10)
    out["assignment_propagation_s"] = round(time.monotonic() - t_prop, 1)
    out["assignment_probe_attempts"] = attempts
    print("assignment propagation seconds:", out["assignment_propagation_s"], "attempts", attempts, flush=True)
    try:
        if mode in ("integration", "all"):
            integration(client, cases, pub, out)
            with open(f"evidence/{mode}_{label}.json", "w") as fh:
                json.dump(out, fh, indent=1, default=str)
        if mode in ("benchmark", "all"):
            spec = json.load(open("fixtures/scale.json"))["cells"]
            benchmark(client, cases, pub, out, deadline, spec)
    except Exception:
        out["error"] = traceback.format_exc()
        print(out["error"])
    finally:
        stop.set()
        out["window_close"] = {k: v for k, v in close_window(label).items() if k != "steps"}
        out["finished_at"] = _now()
        with open(f"evidence/{mode}_{label}.json", "w") as fh:
            json.dump(out, fh, indent=1, default=str)
        print("window closed:", out["window_close"])
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
