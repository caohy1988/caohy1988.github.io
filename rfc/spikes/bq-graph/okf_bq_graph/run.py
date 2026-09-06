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
from .model import sha256_text
from .oracle import Graph
from .publish import resolve_pointer
from .reservation import open_window, close_window
from .retrieve import retrieve, impact, stub_backlog
from .benchmark import measure
from .lifecycle import WindowJobs, WindowClient, WindowStopped, window_executor

ACME_ROOT = "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _client_factory(window=None):
    local = threading.local()

    def get() -> dict:
        if not hasattr(local, "c"):
            raw = bigquery.Client(project=PROJECT, location=LOCATION)
            local.c = window.bind(raw) if window else raw
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


import re


def _leaks(obj, needle: str) -> bool:
    """Exact hidden-identifier check: matches the concept id and its sections (`#sN`) but not
    `metrics/gross-margin-legacy` (the earlier plain-substring check false-positived on it)."""
    return bool(re.search(re.escape(needle) + r"(?![-\w])", json.dumps(obj, default=str)))


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
                                      "full_result": r,   # complete answer surface retained so the leak check is auditable
                                      "verdict": "ENFORCED" if (r["computations"] == [] and not _leaks(r, HIDDEN) and r["status"] in ("OK", "DENIED")) else "LEAK_OR_UNEXPECTED"}
    print("rls hidden intermediate:", gov["rls_hidden_intermediate"]["verdict"], r["status"], len(r["computations"]), "leak", _leaks(r, HIDDEN))
    # natural query on the RLS dataset: hidden sections must not seed
    rn = retrieve("How do we calculate gross margin, exactly?", BUNDLE_ID, pub, "operator", as_of, c)
    gov["rls_natural"] = {"status": rn["status"], "seeds": [x["concept"] for x in rn["concepts"]], "leaks_hidden_id": _leaks(rn, HIDDEN),
                          "computations": [(x["seed"], x["concept"], x["concept_hops"]) for x in rn["computations"]], "full_result": rn}
    print("rls natural:", gov["rls_natural"])
    # impact on RLS dataset must not route through the hidden node
    ri = impact("policies/margin-standard.md", BUNDLE_ID, pub, "operator", c)
    gov["rls_impact"] = {"status": ri["status"], "impacted": [(x["impacted"], x["hops"]) for x in ri.get("impacted", [])], "leaks_hidden_id": _leaks(ri, HIDDEN), "full_result": ri}
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
                                        "warnings": ra["warnings"], "timing": ra["timing"]["total_ms"], "full_result": ra,
                                        "verdict": "FILTERED_VIEW_ACCEPTED" if ra["computations"] == [] and not _leaks(ra, HIDDEN) else "LEAK_OR_UNEXPECTED",
                                        "verdict_note": "same operator identity; the view predicate removes the node — not enforcement against a second principal"})
    print("authorized views:", gov["authorized_views"])
    # (5) publication consistency: concurrent requests during a re-publish must each use one pin
    gov["publication_consistency"] = publication_consistency(client, pub, as_of)
    print("publication consistency:", gov["publication_consistency"])
    out["governance"] = gov


def _sha_of_projection(proj: dict) -> dict:
    """Expected sanctioned-SQL digests per computation for a projection (from the oracle, not from GQL)."""
    g = Graph(proj)
    out = {}
    for n in proj["nodes"]:
        if n["kind"] == "Concept" and n["type"] == "Attested Computation":
            sq = g.sanctioned_sql(n["node_id"])
            if sq:
                out[n["local_id"]] = sq["sql_sha256"]
    return out


def _expected_sql_sha(client: bigquery.Client, bundle_id: str, pub: str) -> dict:
    """Expected digests for an already-published publication, read from the nodes table's Computation sections."""
    from .oracle import SQL_FENCE_RE
    rows = client.query(f"""SELECT c.local_id, s.text FROM `{PROJECT}.{DATASET}.edges` e
                            JOIN `{PROJECT}.{DATASET}.nodes` c ON c.node_id = e.src_id JOIN `{PROJECT}.{DATASET}.nodes` s ON s.node_id = e.dst_id
                            WHERE e.publication_id = @p AND e.relation = 'HAS_SECTION' AND c.type = 'Attested Computation' AND s.heading LIKE 'Computation%'""",
                        job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("p", "STRING", pub)]), location=LOCATION).result()
    out = {}
    for r in rows:
        m = SQL_FENCE_RE.search(r["text"] or "")
        sql = m.group(1) if m else (r["text"] or "")
        out[r["local_id"]] = sha256_text(sql)
    return out


def single_pin(result: dict, expected_sql: dict) -> dict:
    """Check scoped identifiers (including provenance) and actual SQL bytes against independent digests.

    Unscoped paths, section headings/text and provenance attributes are NOT content-validated here.
    G7 stays PARTIAL until pinned artifact comparisons and live old/new coverage are retained.
    """
    pin = result.get("scope", {}).get("publication_id")
    ids = []
    for c in result.get("concepts", []):
        ids.append(c.get("concept_id"))
        ids += [s.get("section_id") for s in c.get("matched_sections", [])]
        ids += [p.get("source_id") for p in c.get("provenance", [])]
    for c in result.get("computations", []):
        ids += [c.get("computation_id"), c.get("section_id")]
    if not pin or not ids or any(not isinstance(i, str) or len(i.split("|", 3)) != 4 for i in ids):
        return {"ok": False, "pins": [], "reason": "missing or malformed scoped identifier"}
    pins = {i.split("|")[1] for i in ids}
    bundle = result.get("scope", {}).get("bundle_id")
    if len({i.split("|")[0] for i in ids} | ({bundle} if bundle else set())) != 1:
        return {"ok": False, "pins": sorted(pins), "reason": "mixed bundle identifiers"}
    if pin:
        pins_all = pins | {pin}
    else:
        pins_all = pins
    if len(pins_all) != 1:
        return {"ok": False, "pins": sorted(pins_all), "reason": "more than one publication in payload/scope" if pins_all else "no scoped ids"}
    for c in result.get("computations", []):
        exp = (expected_sql.get(pin) or {}).get(c.get("concept"))
        actual_sql = c.get("sql")
        actual_sha = sha256_text(actual_sql) if isinstance(actual_sql, str) else None
        if exp is None or c.get("sql_sha256") != exp or actual_sha != exp:
            return {"ok": False, "pins": sorted(pins_all), "reason": f"sql digest for {c.get('concept')} does not match publication {pin}"}
    return {"ok": True, "pins": sorted(pins_all), "reason": None,
            "checked": "scoped identifiers and sanctioned SQL bytes",
            "not_checked": ["unscoped paths", "section headings/text", "provenance attributes"]}


def publication_consistency(client: bigquery.Client, pub: str, as_of: str) -> dict:
    """Publish a changed source (bundle_b variant) while issuing concurrent 'active'-pointer requests;
    every response must carry exactly one publication id across seed/walk/SQL. Then a failed publish
    (injected before pointer switch) must leave the old pointer."""
    import shutil, tempfile
    from .publish import publish, resolve_pointer
    tmp = tempfile.mkdtemp()
    shutil.copytree("fixtures/bundle_b", f"{tmp}/bundle_b")
    with open(f"{tmp}/bundle_b/metrics/gross-margin-alt.md", "a") as fh:
        fh.write("\n\n# Changed\n\nRe-published during concurrent requests (publication consistency test).\n")
    proj = compile_bundle(f"{tmp}/bundle_b", "bundle_b", "fixture-changed")
    before = resolve_pointer(client, "bundle_b")
    results = []

    expected_sql = {before: _expected_sql_sha(client, "bundle_b", before), proj["publication_id"]: _sha_of_projection(proj)}

    def req(i):
        c = {"engine": "gql", "bq": client}
        r = retrieve("forced:metrics/gross-margin-legacy.md", "bundle_b", "active", f"consistency-{i}", as_of, c)
        chk = single_pin(r, expected_sql)
        return {"i": i, "status": r["status"], "publication_id": r["scope"]["publication_id"], "pins_in_payload": sorted(chk["pins"]),
                "n_pubs_seen": len(chk["pins"]), "single_pin": chk["ok"], "reason": chk["reason"], "hops": [p["concept_hops"] for p in r["paths"]],
                "full_result": r}
    with window_executor(client, max_workers=4) as ex:
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
    seen = {p for r in results for p in r["pins_in_payload"]}
    return {"pointer_before": before, "published": pubres["publication_id"], "pointer_after": after, "concurrent": results,
            "all_single_pin": all(r["single_pin"] for r in results), "pins_seen": sorted(seen),
            "checker": "single_pin(): concept/section/computation/provenance source IDs share the scope pin; hash returned SQL bytes "
                       "against independently pinned digests. Unscoped paths, section headings/text and provenance attributes are not validated; G7 PARTIAL.",
            "pins_subset_of_old_new": seen <= {before, pubres["publication_id"]},
            "failed_publish_raised": failed_ok, "pointer_after_failed_publish": after_failed,
            "failed_publish_left_pointer": after_failed == after, "failed_publication_id": proj3["publication_id"]}


def benchmark(client: WindowClient, cases: dict, pub: str, out: dict, cells_spec: list[dict]) -> None:
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
    window = client.window
    cfg = {"cells": cells, "queries": queries, "budget": {"cell_seconds": 1500, "deadline_monotonic": window.deadline}}
    cfg["budget"]["window"] = window
    cfg["run_id"] = out["label"]
    out["benchmark"] = measure(cfg, _client_factory(window))


def main(argv: list[str]) -> int:
    import os
    import signal
    import subprocess
    from pathlib import Path

    mode = argv[1]
    minutes = int(argv[argv.index("--minutes") + 1]) if "--minutes" in argv else (25 if mode == "integration" else 85)
    used = 0.0
    try:
        manifest = json.loads(Path("evidence/cleanup_manifest.json").read_text())
    except FileNotFoundError:
        manifest = {"windows": []}
    for w in manifest["windows"]:
        if not w.get("opened_at"):
            continue
        if not w.get("verified_gone") or not w.get("closed_at"):
            print("outstanding reservation window; verified cleanup required:", w["label"], flush=True)
            return 1
        used += (_dt.datetime.fromisoformat(w["closed_at"].replace("Z", "+00:00")) -
                 _dt.datetime.fromisoformat(w["opened_at"].replace("Z", "+00:00"))).total_seconds() / 60
    minutes = int(min(minutes, max(0, 120 - used - 2)))
    print(f"cumulative reservation minutes used so far: {used:.1f}; this window budget: {minutes} min", flush=True)
    if minutes <= 0:
        return 1  # no submissions and no paid resources when the budget is already exhausted
    cases = json.loads(Path("fixtures/cases.json").read_text())
    label = f"{mode}-{_dt.datetime.now(_dt.timezone.utc).strftime('%Y%m%d-%H%M%S-%f')}"
    out: dict = {"mode": mode, "label": label, "started_at": _now()}
    deadline = time.monotonic() + minutes * 60
    window = WindowJobs(label, deadline, f"evidence/jobs_{label}.json")
    client = window.bind(bigquery.Client(project=PROJECT, location=LOCATION))
    interrupted = False

    def _interrupt(signum, frame):
        nonlocal interrupted
        if interrupted:
            return
        interrupted = True
        # Never acquire locks or perform network I/O from a signal handler.
        # window_executor / run_cell cancel before waiting for workers.
        window.stop.set()
        raise KeyboardInterrupt(f"signal {signum}")

    old_handlers = {sig: signal.signal(sig, _interrupt) for sig in (signal.SIGTERM, signal.SIGINT)}

    def watchdog():
        if not window.stop.wait(max(0, deadline - time.monotonic())):
            print("WATCHDOG: deadline reached; stopping submissions and cancelling jobs", flush=True)
            out["deadline_reached"] = True
            window.stop_and_cancel()

    deadline_thread = threading.Thread(target=watchdog, daemon=True)
    deadline_thread.start()
    try:
        # Spawn before provisioning so even interruption during open has an independent closer.
        watcher = Path(__file__).resolve().parents[1] / "bin" / "safety_teardown.sh"
        with open("evidence/safety_teardown.log", "a") as log:
            subprocess.Popen(["/bin/bash", str(watcher), str(os.getpid()), label, sys.executable],
                             stdout=log, stderr=subprocess.STDOUT, start_new_session=True)
        out["safety_watcher"] = "spawned"
        window.check()
        w = open_window(label)
        out["window_open"] = {"opened_at": w["opened_at"], "state": w.get("state")}
        window.check()
        pub = resolve_pointer(client, BUNDLE_ID)
        out["publication_id"] = pub
        ok_streak, attempts, t_prop = 0, 0, time.monotonic()
        out["assignment_probes"] = []
        while ok_streak < 6 and attempts < 60:
            window.check()
            attempts += 1
            try:
                j = client.query(f"SELECT COUNT(*) FROM GRAPH_TABLE(`{PROJECT}.{DATASET}.okf_graph` MATCH (n:Node) COLUMNS (n.node_id))",
                                 job_config=bigquery.QueryJobConfig(use_query_cache=False), location=LOCATION)
                j.result()
                ok_streak += 1
                out["assignment_ready_job"] = j.job_id
                out["assignment_probes"].append({"at": _now(), "job_id": j.job_id, "ok": True})
            except WindowStopped:
                raise
            except Exception as exc:
                ok_streak = 0
                msg = str(exc).split("\n")[0][:100]
                out["assignment_probes"].append({"at": _now(), "ok": False, "error": msg})
                print("waiting for assignment:", msg, flush=True)
            if ok_streak < 6:
                window.wait(10)
        out["assignment_propagation_s"] = round(time.monotonic() - t_prop, 1)
        out["assignment_probe_attempts"] = attempts
        if ok_streak < 6:
            raise RuntimeError("assignment never reached six successful probes")
        window.check()
        if mode in ("integration", "all"):
            integration(client, cases, pub, out)
            Path(f"evidence/{mode}_{label}.json").write_text(json.dumps(out, indent=1, default=str))
        window.check()
        if mode in ("benchmark", "all"):
            spec = json.loads(Path("fixtures/scale.json").read_text())["cells"]
            benchmark(client, cases, pub, out, spec)
        window.check()
    except (Exception, KeyboardInterrupt):
        out["error"] = traceback.format_exc()
        print(out["error"], flush=True)
    finally:
        # Repeated signals must not interrupt cancellation or reservation readback.
        for sig in old_handlers:
            signal.signal(sig, signal.SIG_IGN)
        out["job_cancellation"] = window.stop_and_cancel()
        deadline_thread.join()
        try:
            out["window_close"] = {k: v for k, v in close_window(label).items() if k != "steps"}
        except Exception:
            out["window_close"] = {"verified_gone": False, "error": traceback.format_exc()}
        out["finished_at"] = _now()
        Path(f"evidence/{mode}_{label}.json").write_text(json.dumps(out, indent=1, default=str))
        for sig, handler in old_handlers.items():
            signal.signal(sig, handler)
        print("window closed:", out["window_close"], flush=True)
    return 0 if not out.get("error") and out["window_close"]["verified_gone"] and all(
        j["verified_done"] for j in out["job_cancellation"]) else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
