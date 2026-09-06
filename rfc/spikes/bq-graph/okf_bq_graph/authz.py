"""Task 5 governance fixtures (spec §5) — REDUCED SCOPE.

Creating distinct service accounts / project IAM bindings was denied by this session's permission
classifier, so every case that needs a real second principal is BLOCKED (recorded, not simulated).
What CAN be measured under the operator identity with real BigQuery policy objects:
  * RLS enforced inside a GQL traversal: dataset `_rls` copies the Acme publication and a row access
    policy grants the operator only rows that exclude the intermediate concept metrics/gross-margin
    (and its sections and touching edges). If GQL honoured RLS, the legacy->current->computation path
    must vanish and no hidden identifier may appear.
  * Metadata-visible / source-denied: dataset `_meta` hides every Section row (no text) but keeps Concept rows.
  * Revocation before cached replay: the `_rls` policy is replaced with FILTER USING (FALSE) (a real policy
    change), then a cached response is replayed; disclosure must re-check and fail closed.
  * Authorized views: dataset `_av` holds authorized views over the base dataset; we record whether
    CREATE PROPERTY GRAPH accepts views and whether GQL runs over them.
"""
from __future__ import annotations

import datetime as _dt
import json

from google.cloud import bigquery

from . import PROJECT, LOCATION, DATASET

RLS_DS = f"{DATASET}_rls"
META_DS = f"{DATASET}_meta"
AV_DS = f"{DATASET}_av"
import os as _os, subprocess as _sp


def _operator() -> str:
    e = _os.environ.get("OKF_OPERATOR_EMAIL") or _sp.run(["gcloud", "config", "get-value", "account"], capture_output=True, text=True).stdout.strip()
    return f"user:{e}"


OPERATOR = _operator()   # never committed; resolved from the active gcloud account or OKF_OPERATOR_EMAIL
HIDDEN = "metrics/gross-margin"
BLOCKED_CASES = [
    "distinct restricted principal (service account) — IAM principal creation denied by session permission classifier",
    "same path in a denied bundle under a second identity — needs distinct principal",
    "output denied despite seed access under a second identity — needs distinct principal",
    "owner-credential fallback negative — needs distinct principal",
]


def _mk_ds(client: bigquery.Client, ds: str, desc: str) -> None:
    d = bigquery.Dataset(f"{PROJECT}.{ds}"); d.location = LOCATION; d.default_table_expiration_ms = 14 * 86400 * 1000
    d.description = desc
    client.create_dataset(d, exists_ok=True)


def setup(client: bigquery.Client, base_pub: str) -> dict:
    from .publish import run, ensure_graph
    P = lambda k, t, v: bigquery.ScalarQueryParameter(k, t, v)
    log: dict = {"started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "blocked": BLOCKED_CASES, "policies": []}
    base = f"{PROJECT}.{DATASET}"
    for ds in (RLS_DS, META_DS):
        _mk_ds(client, ds, "OKF BigQuery Graph spike 2026-09-05 governance fixture (temporary)")
        full = f"{PROJECT}.{ds}"
        for t in ("nodes", "edges", "section_vectors"):
            run(client, f"CREATE OR REPLACE TABLE `{full}.{t}` AS SELECT * FROM `{base}.{t}` WHERE publication_id = @p", [P("p", "STRING", base_pub)])
        run(client, f"CREATE MODEL IF NOT EXISTS `{full}.text_embedding` REMOTE WITH CONNECTION `{PROJECT}.us.bq-llm` OPTIONS (ENDPOINT = 'text-embedding-005')")
        log[f"graph_{ds}"] = ensure_graph(client, ds)
    rls, meta = f"{PROJECT}.{RLS_DS}", f"{PROJECT}.{META_DS}"
    pol = [
        f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_nodes ON `{rls}.nodes` GRANT TO ('{OPERATOR}') FILTER USING (local_id <> '{HIDDEN}' AND NOT STARTS_WITH(local_id, '{HIDDEN}#'))",
        f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_edges ON `{rls}.edges` GRANT TO ('{OPERATOR}') FILTER USING (NOT REGEXP_CONTAINS(src_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)') AND NOT REGEXP_CONTAINS(dst_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)'))",
        f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_vectors ON `{rls}.section_vectors` GRANT TO ('{OPERATOR}') FILTER USING (NOT REGEXP_CONTAINS(node_id, r'\\|Section\\|{HIDDEN}#'))",
        f"CREATE OR REPLACE ROW ACCESS POLICY hide_sections_nodes ON `{meta}.nodes` GRANT TO ('{OPERATOR}') FILTER USING (kind <> 'Section')",
        f"CREATE OR REPLACE ROW ACCESS POLICY hide_sections_edges ON `{meta}.edges` GRANT TO ('{OPERATOR}') FILTER USING (relation NOT IN ('HAS_SECTION', 'NEXT', 'CITES', 'MENTIONS'))",
        f"CREATE OR REPLACE ROW ACCESS POLICY all_vectors ON `{meta}.section_vectors` GRANT TO ('{OPERATOR}') FILTER USING (TRUE)",
    ]
    for q in pol:
        try:
            j = run(client, q); log["policies"].append({"ok": True, "job": j.job_id, "sql": q[:140]})
        except Exception as e:  # noqa: BLE001
            log["policies"].append({"ok": False, "error": str(e)[:300], "sql": q[:140]})
    # authorized views
    _mk_ds(client, AV_DS, "OKF BigQuery Graph spike 2026-09-05 authorized-view fixture (temporary)")
    av = f"{PROJECT}.{AV_DS}"
    run(client, f"""CREATE OR REPLACE VIEW `{av}.nodes` AS SELECT * FROM `{base}.nodes`
                    WHERE publication_id = '{base_pub}' AND local_id <> '{HIDDEN}' AND NOT STARTS_WITH(local_id, '{HIDDEN}#')""")
    run(client, f"""CREATE OR REPLACE VIEW `{av}.edges` AS SELECT * FROM `{base}.edges`
                    WHERE publication_id = '{base_pub}' AND NOT REGEXP_CONTAINS(src_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)')
                      AND NOT REGEXP_CONTAINS(dst_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)')""")
    run(client, f"CREATE OR REPLACE VIEW `{av}.section_vectors` AS SELECT * FROM `{base}.section_vectors` WHERE publication_id = '{base_pub}' AND NOT REGEXP_CONTAINS(node_id, r'\\|Section\\|{HIDDEN}#')")
    bd = client.get_dataset(base); be = list(bd.access_entries)
    for v in ("nodes", "edges", "section_vectors"):
        be.append(bigquery.AccessEntry(None, "view", {"projectId": PROJECT, "datasetId": AV_DS, "tableId": v}))
    bd.access_entries = be; client.update_dataset(bd, ["access_entries"])
    log["authorized_views"] = [v for v in ("nodes", "edges", "section_vectors")]
    try:
        log["graph_av"] = ensure_graph(client, AV_DS); log["graph_over_views"] = "ACCEPTED"
    except Exception as e:  # noqa: BLE001
        log["graph_av"] = {"error": str(e)[:400]}; log["graph_over_views"] = "REJECTED"
    # visibility probe (plain SQL, operator)
    log["probe"] = {}
    for ds in (DATASET, RLS_DS, META_DS, AV_DS):
        try:
            r = list(client.query(f"SELECT COUNT(*) n, COUNTIF(local_id = '{HIDDEN}') hidden, COUNTIF(kind='Section') sections FROM `{PROJECT}.{ds}.nodes`", location=LOCATION).result())[0]
            log["probe"][ds] = dict(r)
        except Exception as e:  # noqa: BLE001
            log["probe"][ds] = {"error": str(e)[:200]}
    log["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    with open("evidence/authz_setup.json", "w") as fh:
        json.dump(log, fh, indent=1, default=str)
    return log


def revoke(client: bigquery.Client) -> dict:
    """Real policy change: the operator's grant on `_rls` becomes FILTER USING (FALSE) (zero rows)."""
    from .publish import run
    rls = f"{PROJECT}.{RLS_DS}"
    out = {"at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    for name, t in (("hide_intermediate_nodes", "nodes"), ("hide_intermediate_edges", "edges"), ("hide_intermediate_vectors", "section_vectors")):
        out[name] = run(client, f"CREATE OR REPLACE ROW ACCESS POLICY {name} ON `{rls}.{t}` GRANT TO ('{OPERATOR}') FILTER USING (FALSE)").job_id
    return out


def restore(client: bigquery.Client) -> dict:
    from .publish import run
    rls = f"{PROJECT}.{RLS_DS}"
    out = {"at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    out["nodes"] = run(client, f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_nodes ON `{rls}.nodes` GRANT TO ('{OPERATOR}') FILTER USING (local_id <> '{HIDDEN}' AND NOT STARTS_WITH(local_id, '{HIDDEN}#'))").job_id
    out["edges"] = run(client, f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_edges ON `{rls}.edges` GRANT TO ('{OPERATOR}') FILTER USING (NOT REGEXP_CONTAINS(src_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)') AND NOT REGEXP_CONTAINS(dst_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)'))").job_id
    out["vectors"] = run(client, f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_vectors ON `{rls}.section_vectors` GRANT TO ('{OPERATOR}') FILTER USING (NOT REGEXP_CONTAINS(node_id, r'\\|Section\\|{HIDDEN}#'))").job_id
    return out


if __name__ == "__main__":
    import sys
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    if sys.argv[1] == "setup":
        o = setup(client, sys.argv[2]); print(json.dumps({k: v for k, v in o.items() if k != "policies"}, indent=1, default=str))
        for p in o["policies"]: print(p["ok"], p.get("error", ""), p["sql"][:100])
    elif sys.argv[1] == "revoke":
        print(revoke(client))
    elif sys.argv[1] == "restore":
        print(restore(client))
