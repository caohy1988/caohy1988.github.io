"""Render evidence/report_tables.md from raw evidence (benchmark cells, governance, parity, cost).
report.md is hand-written around these tables so prose never invents a number."""
from __future__ import annotations

import glob
import json
import os


def _load(path):
    with open(path) as fh:
        return json.load(fh)


def fmt(v, nd=0):
    if v is None:
        return "—"
    return f"{v:,.{nd}f}" if isinstance(v, (int, float)) else str(v)


def benchmark_table(summary: dict) -> str:
    rows = ["| run | cell | corpus | C | n measured / target | state | ok rate | errors | timeouts | p50 all (ms) | p95 all (ms) | max (ms) | p50 seed | p50 walk | p50 context | p50 nodes | jobs | slot-ms | slot attribution USD |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in summary["cells"]:
        run_id = c.get("run_id") or "legacy-unlabeled"
        if "measured_n" not in c:
            rows.append(f"| {run_id} | {c['cell']} | — | — | 0 / — | {c['state']} | — | — | — | — | — | — | — | — | — | — | — | — | — |")
            continue
        sp = c.get("stage_p50_ms", {})
        success = f"{fmt(c['success_rate'] * 100, 1)}%" if c['success_rate'] is not None else "—"
        rows.append(f"| {run_id} | {c['cell']} | {c['corpus']} | {c['concurrency']} | {c['measured_n']} / {c['measured_target']} | {c['state']} | "
                    f"{success} | {c['errors']} | {c['timeouts']} | "
                    f"{fmt(c['p50_ms_all'])} | {fmt(c['p95_ms_all'])} | {fmt(c['max_ms_all'])} | {fmt(sp.get('seed'))} | {fmt(sp.get('walk'))} | "
                    f"{fmt(sp.get('context'))} | {fmt(sp.get('nodes'))} | {c['jobs_total']} | {fmt(c['slot_ms_total'])} | {c['slot_attribution_usd']:.4f} |")
    return "\n".join(rows)


def parity_table(allj: dict) -> str:
    rows = ["| forced seed | GQL status | hops | computation | SQL digest = oracle | trust = oracle | replacement = oracle | freshness = oracle | via = oracle | total ms |", "|---|---|---|---|---|---|---|---|---|---|"]
    rows[0] = rows[0].replace("| via = oracle |", "| via = oracle | provenance resources = oracle (post hoc) |")
    rows[1] += "---|"
    for k, v in allj.get("forced", {}).items():
        p = v["parity"]
        t = lambda b: "✓" if b else "✗"
        gp = {x.get("resource") for x in (v["result"]["concepts"][0].get("provenance") if v["result"].get("concepts") else [])}
        op = {x.get("resource") for x in v["oracle"].get("provenance", [])}
        prov = "✓ (resource set)" if gp == op else f"✗ {sorted(gp)} vs {sorted(op)}"
        rows.append(f"| {k} | {p['gql_status']} | {t(p['hops_ok'])} | {t(p['computation_ok'])} | {t(p['sql_sha_matches_oracle'])} | "
                    f"{t(p['trust_matches_oracle'])} | {t(p['replacement_matches_oracle'])} | {t(p['freshness_matches_oracle'])} | "
                    f"{t(p['via_matches_oracle'])} | {prov} | {fmt(p['timing']['total_ms'])} |")
    return "\n".join(rows)


def natural_table(allj: dict) -> str:
    out = []
    for k, r in allj.get("natural", {}).items():
        out.append(f"**{k}** — status {r['status']}, total {fmt(r['timing']['total_ms'])} ms, stages {r['timing']['stages_ms']}")
        out.append("")
        out.append("| seed concept | status | trust | freshness | matched sections (cosine distance) | computation | hops |")
        out.append("|---|---|---|---|---|---|---|")
        comps = {c["seed"]: c for c in r["computations"]}
        for c in r["concepts"]:
            secs = "; ".join(f"{s['heading']} ({s['distance']:.4f})" for s in c["matched_sections"])
            cp = comps.get(c["concept"])
            out.append(f"| {c['concept']} | {c['lifecycle_status']} | {c['trust_tier']} | {c['freshness']['verdict']} | {secs} | {cp['concept'] if cp else '—'} | {cp['concept_hops'] if cp else '—'} |")
        out.append("")
    return "\n".join(out)


import re
HIDDEN_RE = re.compile(r"metrics/gross-margin(?![-\w])")


def _recheck_note(case: dict) -> str:
    """Post-hoc note only. NEVER changes the recorded verdict. If the full answer surface was retained
    (`full_result`, added after review), an exact regex check is reported; otherwise the case is INCONCLUSIVE
    because the runtime detector was a plain substring that matched `metrics/gross-margin-legacy`."""
    if not case:
        return "NOT_RUN"
    if "full_result" in case:
        leak = bool(HIDDEN_RE.search(json.dumps(case["full_result"], default=str)))
        return f"exact regex over retained full payload: {'HIDDEN ID PRESENT' if leak else 'no hidden id'}"
    if case.get("leaks_hidden_id"):
        return "INCONCLUSIVE — runtime flag came from a substring detector that also matches `-legacy`; full payload not retained; no re-run"
    return "runtime flag false (substring detector); full payload not retained"


def _disclosure_label(case: dict, clean_label="ENFORCED", legacy_note="no-leak claim unverified") -> str:
    """Publish negative evidence explicitly, leaving every recorded field intact."""
    if not case:
        return "NOT_RUN"
    if "full_result" in case:
        if HIDDEN_RE.search(json.dumps(case["full_result"], default=str)):
            return "FAIL/LEAK (hidden ID present in retained full payload)"
        if case.get("leaks_hidden_id"):
            return "FAIL (recorded positive leak flag; retained payload check disagrees)"
    elif case.get("leaks_hidden_id"):
        return f"INCONCLUSIVE ({legacy_note})"
    if case.get("verdict") in ("LEAK_OR_UNEXPECTED", "FAIL", "LEAK"):
        return f"FAIL ({case['verdict']}; retained record)"
    if case.get("status") != "OK" or case.get("leaks_hidden_id") is not False:
        return "INCONCLUSIVE (no successful negative disclosure check)"
    return clean_label


def governance_table(allj: dict) -> str:
    g = allj.get("governance", {})
    rows = ["| case | dataset / mechanism | observed (recorded, unmodified) | recorded verdict / flag | post-hoc note (does not change the record) | published label |",
            "|---|---|---|---|---|---|"]
    h = g.get("rls_hidden_intermediate", {})
    hidden_label = _disclosure_label(h, legacy_note="path removal corroborated: computations 0, paths [], replacement NONE, RLS probe hidden=0; no-leak claim unverified")
    rows.append(f"| hidden intermediate (`metrics/gross-margin`) inside GQL walk | `_rls`: ROW ACCESS POLICY on nodes/edges/vectors | status {h.get('status')}, computations {h.get('computations')}, paths {h.get('paths')}, replacement {h.get('replacement')} | `leaks_hidden_id={h.get('leaks_hidden_id')}`, `{h.get('verdict')}` | {_recheck_note(h)} | {hidden_label} |")
    n = g.get("rls_natural", {})
    rows.append(f"| natural question on RLS dataset | `_rls` vector seed + walk | seeds {n.get('seeds')}, computations {n.get('computations')} | `leaks_hidden_id={n.get('leaks_hidden_id')}`, `{n.get('verdict')}` | {_recheck_note(n)} | {_disclosure_label(n)} |")
    i = g.get("rls_impact", {})
    rows.append(f"| impact on RLS dataset | `_rls` ACYCLIC {{1,6}} | impacted {i.get('impacted')} | `leaks_hidden_id={i.get('leaks_hidden_id')}`, `{i.get('verdict')}` | {_recheck_note(i)} | {_disclosure_label(i, 'ENFORCED (hidden concept absent from impacted set; recorded flag false)')} |")
    m = g.get("meta_source_denied", {})
    rows.append(f"| metadata visible, source (Section rows) denied | `_meta`: policy hides every Section row | paths {m.get('paths')}, SQL withheld: {m.get('sql_withheld')} | `{m.get('verdict')}` | SQL null with `SOURCE_DENIED_OR_MISSING` warning; operator identity | {m.get('verdict')} |")
    r = g.get("revoke_before_cached_replay", {})
    rows.append(f"| revoke before cached replay (all rows) | `_rls`: policy replaced with FILTER USING (FALSE) at {r.get('revoked_at')} | warm {r.get('warm')}, hit {r.get('hit')}, replay {r.get('replay')}, fresh {r.get('fresh_after_revoke')} | `{r.get('verdict')}` | edge-only revocation was NOT exercised live; outer SQL now projects traversal edge_ids, version-2 cache requires complete dependencies, and incomplete/legacy entries trigger fresh retrieval; second-hop revocation has offline coverage using actual result columns, not new live evidence | {r.get('verdict')} (all-rows case only) |")
    a = g.get("authorized_views", {})
    rows.append(f"| authorized views as graph inputs | `_av`: views over base dataset; graph-input acceptance: {a.get('graph_over_views', 'NOT_RUN')} | status {a.get('status')}, computations {a.get('computations')}, {fmt(a.get('timing'))} ms | `leaks_hidden_id={a.get('leaks_hidden_id')}`, `{a.get('verdict')}` | {_recheck_note(a)}; same operator identity, no second principal | {_disclosure_label(a)} |")
    p = g.get("publication_consistency", {})
    partial = p.get("checker") is None
    rows.append(f"| publication consistency (concurrent requests during re-publish) | `bundle_b` re-published {p.get('pointer_before')} → {p.get('published')} | pins seen {p.get('pins_seen')}, all single-pin: {p.get('all_single_pin')} | recorded by {'scope-only checker (invalid: could not detect a mixed payload)' if partial else 'single_pin() over scoped identifiers/provenance and hashes of returned SQL bytes'} | {'PARTIAL — six requests all reported the old pin by scope; payload-level single-pin was not verifiable at measurement time; checker replaced and unit-tested offline, not re-measured' if partial else 'Unscoped paths, section text and provenance attributes excluded from checker; full content integrity remains PARTIAL'} | {'FAIL' if not partial and p.get('all_single_pin') is False else 'PARTIAL'} |")
    rows.append(f"| failed publish leaves old pointer | injected failure before pointer switch ({p.get('failed_publication_id')}) | raised: {p.get('failed_publish_raised')}, pointer after: {p.get('pointer_after_failed_publish')} | `{p.get('failed_publish_left_pointer')}` | pointer read back after the raised failure | {'PASS' if p.get('failed_publish_left_pointer') else 'FAIL/NOT_RUN'} |")
    for b in g.get("blocked", []):
        head, _, tail = b.partition(" — ")
        rows.append(f"| {head} | — | {tail} | — | — | BLOCKED |")
    return "\n".join(rows)


def impact_table(allj: dict) -> str:
    imp = allj.get("impact", {}).get("gql", {})
    o = allj.get("impact", {}).get("oracle", {})
    rows = [f"GQL status {imp.get('status')}, parity {imp.get('parity')}, {fmt(imp.get('timing', {}).get('total_ms'))} ms; oracle truncated={o.get('truncated')}", "",
            "| impacted concept | type | status | min hops (GQL) | min hops (oracle) | path (GQL) |", "|---|---|---|---|---|---|"]
    oh = {x["impacted"]: x["hops"] for x in o.get("impacted", [])}
    for x in imp.get("impacted", []):
        rows.append(f"| {x['impacted']} | {x['type']} | {x['status']} | {x['hops']} | {oh.get(x['impacted'], '—')} | {' → '.join(p.split('|')[-1] for p in x['path'])} |")
    return "\n".join(rows)


def main():
    files = sorted(glob.glob("evidence/all_*.json"), key=os.path.getmtime)
    allj = _load(files[-1]) if files else {}
    parts = ["<!-- generated by okf_bq_graph.report from evidence/*.json; do not edit by hand -->", ""]
    parts += ["## Forced-seed landmine parity (GQL vs oracle)", "", parity_table(allj), ""]
    parts += ["## Natural question (GQL, vector seed top-k=5)", "", natural_table(allj)]
    parts += ["## Impact analysis (GQL vs oracle)", "", impact_table(allj), ""]
    b = allj.get("backlog_acme", {}); bb = allj.get("backlog_bundle_b", {}); amb = allj.get("ambiguous_bundle_b", {}); cx = allj.get("cross_scope", {})
    parts += ["## Stub backlog / ambiguity / scope", "",
              f"* Acme backlog (GQL): status {b.get('status')}, {len(b.get('backlog', []))} stubs — {b.get('backlog')}",
              f"* bundle_b backlog (GQL): status {bb.get('status')}, parity with oracle: {bb.get('parity')} — {[(x['missing_concept'], x['reference_count']) for x in bb.get('backlog', [])]}",
              f"* bundle_b deprecated anchor: replacement {amb['concepts'][0].get('replacement') if amb.get('concepts') else None}; computations {[(c['concept'], c['concept_hops']) for c in amb.get('computations', [])]}",
              f"* cross-scope request (acme seed with bundle_b publication): status {cx.get('status')}, computations {len(cx.get('computations', []))}, warnings {cx.get('warnings')}", ""]
    parts += ["## Governance (spec §5)", "", governance_table(allj), ""]
    if os.path.exists("evidence/summary.json"):
        parts += ["## Benchmark cells (spec §6)", "", benchmark_table(_load("evidence/summary.json")), ""]
    if os.path.exists("evidence/cost.json"):
        c = _load("evidence/cost.json")
        parts += ["## Cost reconciliation (provisional)", "",
                  f"Window {c['window']['since']} → {c['window']['until']}. Named reservation `{c['named_reservation']}`: {c['named_reservation_jobs']} jobs, "
                  f"{c['slot_ms_named']:,} slot-ms → attribution ${c['slot_attribution_named_usd']}. Other pool(s) {c['other_pools']}: {c['other_pool_jobs']} jobs, "
                  f"{c['slot_ms_other_pool']:,} slot-ms (not billed at the Enterprise rate here). On-demand: {c['ondemand_jobs']} jobs, {c['ondemand_bytes_billed']:,} bytes billed "
                  f"→ ${c['ondemand_list_usd']} at list rate (free tier not applied). Charged autoscale slot-seconds from RESERVATIONS_TIMELINE: "
                  f"{c['charged_autoscale_slot_seconds']:,} → **${c['charged_autoscale_usd']}** capacity bill estimate (baseline slot-seconds {c['baseline_slot_seconds']}); "
                  f"legacy snapshot sum {c['snapshot_slot_minutes_legacy']} slot-minutes shown for comparison only. Timeline last row: {c['timeline_last_period_start']}.", "",
                  "| minute (UTC) | baseline slots | autoscaled slots (snapshot) | charged autoscale slot-seconds |", "|---|---|---|---|"]
        for r in c["timeline"]:
            parts.append(f"| {str(r['period_start'])[:16]} | {r['slot_capacity']} | {r['autoscale_current_slots']} | {r.get('period_autoscale_slot_seconds')} |")
    with open("evidence/report_tables.md", "w") as fh:
        fh.write("\n".join(parts) + "\n")
    print("wrote evidence/report_tables.md from", files[-1] if files else "no all_*.json")


if __name__ == "__main__":
    main()
