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
    rows = ["| cell | corpus | C | n measured / target | state | ok rate | errors | timeouts | p50 all (ms) | p95 all (ms) | max (ms) | p50 seed | p50 walk | p50 context | p50 nodes | jobs | slot-ms | slot attribution USD |",
            "|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|"]
    for c in summary["cells"]:
        if "measured_n" not in c:
            rows.append(f"| {c['cell']} | — | — | 0 / — | {c['state']} | — | — | — | — | — | — | — | — | — | — | — | — | — |")
            continue
        sp = c.get("stage_p50_ms", {})
        rows.append(f"| {c['cell']} | {c['corpus']} | {c['concurrency']} | {c['measured_n']} / {c['measured_target']} | {c['state']} | "
                    f"{fmt(c['success_rate'] * 100 if c['success_rate'] is not None else None, 1)}% | {c['errors']} | {c['timeouts']} | "
                    f"{fmt(c['p50_ms_all'])} | {fmt(c['p95_ms_all'])} | {fmt(c['max_ms_all'])} | {fmt(sp.get('seed'))} | {fmt(sp.get('walk'))} | "
                    f"{fmt(sp.get('context'))} | {fmt(sp.get('nodes'))} | {c['jobs_total']} | {fmt(c['slot_ms_total'])} | {c['slot_attribution_usd']:.4f} |")
    return "\n".join(rows)


def parity_table(allj: dict) -> str:
    rows = ["| forced seed | GQL status | hops | computation | SQL digest = oracle | trust = oracle | replacement = oracle | freshness = oracle | via = oracle | total ms |", "|---|---|---|---|---|---|---|---|---|---|"]
    for k, v in allj.get("forced", {}).items():
        p = v["parity"]
        t = lambda b: "✓" if b else "✗"
        rows.append(f"| {k} | {p['gql_status']} | {t(p['hops_ok'])} | {t(p['computation_ok'])} | {t(p['sql_sha_matches_oracle'])} | "
                    f"{t(p['trust_matches_oracle'])} | {t(p['replacement_matches_oracle'])} | {t(p['freshness_matches_oracle'])} | "
                    f"{t(p['via_matches_oracle'])} | {fmt(p['timing']['total_ms'])} |")
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


def governance_table(allj: dict) -> str:
    g = allj.get("governance", {})
    rows = ["| case | dataset / mechanism | observed | verdict |", "|---|---|---|---|"]
    h = g.get("rls_hidden_intermediate", {})
    rows.append(f"| hidden intermediate (`metrics/gross-margin`) inside GQL walk | `_rls`: ROW ACCESS POLICY on nodes/edges/vectors | status {h.get('status')}, computations {h.get('computations')}, paths {h.get('paths')}, replacement {h.get('replacement')}, hidden id in output: {h.get('leaks_hidden_id')} | {h.get('verdict')} |")
    n = g.get("rls_natural", {})
    rows.append(f"| natural question on RLS dataset | `_rls` vector seed + walk | seeds {n.get('seeds')}, computations {n.get('computations')}, hidden id leak: {n.get('leaks_hidden_id')} | {'ENFORCED' if n and not n.get('leaks_hidden_id') else 'LEAK/NOT_RUN'} |")
    i = g.get("rls_impact", {})
    rows.append(f"| impact on RLS dataset | `_rls` ACYCLIC {{1,6}} | impacted {i.get('impacted')}, hidden id leak: {i.get('leaks_hidden_id')} | {'ENFORCED' if i and not i.get('leaks_hidden_id') else 'LEAK/NOT_RUN'} |")
    m = g.get("meta_source_denied", {})
    rows.append(f"| metadata visible, source (Section rows) denied | `_meta`: policy hides every Section row | paths {m.get('paths')}, SQL withheld: {m.get('sql_withheld')}, warnings {m.get('warnings')} | {m.get('verdict')} |")
    r = g.get("revoke_before_cached_replay", {})
    rows.append(f"| revoke before cached replay | `_rls`: policy replaced with FILTER USING (FALSE) at {r.get('revoked_at')} | warm {r.get('warm')}, hit {r.get('hit')}, replay {r.get('replay')}, fresh {r.get('fresh_after_revoke')} | {r.get('verdict')} |")
    a = g.get("authorized_views", {})
    rows.append(f"| authorized views as graph inputs | `_av`: views over base dataset; CREATE PROPERTY GRAPH over views: {a.get('graph_over_views')} | status {a.get('status')}, computations {a.get('computations')}, hidden id leak: {a.get('leaks_hidden_id')}, {fmt(a.get('timing'))} ms | {a.get('verdict')} |")
    p = g.get("publication_consistency", {})
    rows.append(f"| publication consistency (concurrent requests during re-publish) | `bundle_b` re-published {p.get('pointer_before')} → {p.get('published')} | pins seen {p.get('pins_seen')}, all single-pin: {p.get('all_single_pin')}, pins ⊆ {{old,new}}: {p.get('pins_subset_of_old_new')} | {'PASS' if p.get('all_single_pin') and p.get('pins_subset_of_old_new') else 'FAIL/NOT_RUN'} |")
    rows.append(f"| failed publish leaves old pointer | injected failure before pointer switch ({p.get('failed_publication_id')}) | raised: {p.get('failed_publish_raised')}, pointer after: {p.get('pointer_after_failed_publish')} | {'PASS' if p.get('failed_publish_left_pointer') else 'FAIL/NOT_RUN'} |")
    for b in g.get("blocked", []):
        head, _, tail = b.partition(" — ")
        rows.append(f"| {head} | — | {tail} | BLOCKED |")
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
        parts += ["## Cost reconciliation", "",
                  f"Window {c['window']['since']} → {c['window']['until']}: {c['reservation_jobs']} reservation jobs, {c['ondemand_jobs']} on-demand jobs; "
                  f"slot-ms on reservation {c['slot_ms_on_reservation']:,} → attribution ${c['slot_attribution_usd']}; "
                  f"allocated autoscale slot-minutes {c['allocated_slot_minutes']} → capacity bill ${c['allocated_capacity_usd']}; "
                  f"on-demand bytes billed {c['ondemand_bytes_billed']:,} → ${c['ondemand_usd']}.", "",
                  "| minute (UTC) | baseline slots | autoscaled slots |", "|---|---|---|"]
        for r in c["timeline"]:
            parts.append(f"| {str(r['period_start'])[:16]} | {r['slot_capacity']} | {r['autoscale_current_slots']} |")
    with open("evidence/report_tables.md", "w") as fh:
        fh.write("\n".join(parts) + "\n")
    print("wrote evidence/report_tables.md from", files[-1] if files else "no all_*.json")


if __name__ == "__main__":
    main()
