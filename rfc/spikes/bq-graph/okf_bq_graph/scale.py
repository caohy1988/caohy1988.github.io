"""Synthetic scale cells (spec §6): N namespace-isolated copies of the Acme projection.

Each copy is a distinct bundle_id (acme_copy_NNNN) with its own deterministic publication id
(re-derived through the compiler, so scope binding holds). No cross-bundle edges exist.
Vectors are reused from the pinned Acme publication by (text_sha256, heading) — one common
vector artifact, same model — instead of re-embedding identical text 1,000 times.
These cells measure tenant/corpus overhead only; they are not high-degree production graphs.
"""
from __future__ import annotations

import datetime as _dt
import json
import time

from google.cloud import bigquery

from . import PROJECT, LOCATION, DATASET, SOURCE_PIN
from .compile import compile_bundle
from .publish import run, _load, EMBEDDING_MODEL

ACME_ROOT = "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"


def ensure_corpus_dataset(client: bigquery.Client, ds: str) -> None:
    from .publish import ensure_schema, ensure_graph
    from google.cloud.bigquery import Dataset
    d = Dataset(f"{PROJECT}.{ds}"); d.location = LOCATION; d.default_table_expiration_ms = 14 * 86400 * 1000
    d.description = "OKF BigQuery Graph spike 2026-09-05 synthetic scale corpus (temporary; teardown per manifest)"
    client.create_dataset(d, exists_ok=True)
    ensure_schema(client, ds)
    run(client, f"CREATE MODEL IF NOT EXISTS `{PROJECT}.{ds}.text_embedding` REMOTE WITH CONNECTION `{PROJECT}.us.bq-llm` OPTIONS (ENDPOINT = 'text-embedding-005')")
    ensure_graph(client, ds)


def publish_copies(client: bigquery.Client, n: int, start: int, corpus: str, base_pub: str, ds: str = DATASET,
                   base_ds: str = DATASET, batch: int = 250) -> dict:
    full = f"{PROJECT}.{ds}"
    base_full = f"{PROJECT}.{base_ds}"
    ensure_corpus_dataset(client, ds)
    t0 = time.monotonic()
    pubs = {}
    nodes, edges = [], []
    for i in range(start, start + n):
        proj = compile_bundle(ACME_ROOT, f"acme_copy_{i:04d}", SOURCE_PIN)
        pubs[proj["bundle_id"]] = {"publication_id": proj["publication_id"], "nodes": len(proj["nodes"]), "edges": len(proj["edges"])}
        nodes += [dict(x, stale_after_ts=None if not x["stale_after"] or "T" not in x["stale_after"] else
                       _dt.datetime.fromisoformat(x["stale_after"].replace("Z", "+00:00")).strftime("%Y-%m-%d %H:%M:%S+00")) for x in proj["nodes"]]
        edges += proj["edges"]
    compile_s = round(time.monotonic() - t0, 1)
    jn = je = None
    for i in range(0, len(nodes), batch * 44):
        jn = _load(client, f"{full}.nodes", nodes[i:i + batch * 44])
    for i in range(0, len(edges), batch * 109):
        je = _load(client, f"{full}.edges", edges[i:i + batch * 109])
    bundle_ids = sorted(pubs)
    P = lambda k, t, v: bigquery.ScalarQueryParameter(k, t, v)
    A = lambda k, t, v: bigquery.ArrayQueryParameter(k, t, v)
    jv = run(client, f"""
      INSERT INTO `{full}.section_vectors`
        (node_id, bundle_id, publication_id, concept_id, heading, embedding_model, embedding_model_version, task_type,
         text_sha256, dims, embedding, created_at)
      SELECT n.node_id, n.bundle_id, n.publication_id, e.src_id, n.heading, @model, NULL, 'RETRIEVAL_DOCUMENT',
             n.text_sha256, v.dims, v.embedding, CURRENT_TIMESTAMP()
      FROM `{full}.nodes` n
      JOIN `{full}.edges` e ON e.dst_id = n.node_id AND e.relation = 'HAS_SECTION' AND e.bundle_id = n.bundle_id
      JOIN (SELECT text_sha256, heading, ANY_VALUE(dims) AS dims, ANY_VALUE(embedding) AS embedding
            FROM `{base_full}.section_vectors` WHERE publication_id = @base_pub GROUP BY 1, 2) v
        ON v.text_sha256 = n.text_sha256 AND v.heading = n.heading
      WHERE n.kind = 'Section' AND n.bundle_id IN UNNEST(@bundles)
        AND NOT EXISTS (SELECT 1 FROM `{full}.section_vectors` x WHERE x.node_id = n.node_id)
    """, [P("model", "STRING", EMBEDDING_MODEL), P("base_pub", "STRING", base_pub), A("bundles", "STRING", bundle_ids)])
    chk = [dict(r) for r in run(client, f"""
      SELECT n.bundle_id, n.publication_id, COUNT(DISTINCT n.node_id) AS nodes,
             (SELECT COUNT(*) FROM `{full}.edges` e WHERE e.bundle_id = n.bundle_id) AS edges,
             (SELECT COUNT(*) FROM `{full}.section_vectors` v WHERE v.bundle_id = n.bundle_id) AS vectors,
             COUNTIF(n.kind = 'Section') AS sections
      FROM `{full}.nodes` n WHERE n.bundle_id IN UNNEST(@bundles) GROUP BY 1, 2""", [A("bundles", "STRING", bundle_ids)]).result()]
    bad = [r for r in chk if r["nodes"] != pubs[r["bundle_id"]]["nodes"] or r["edges"] != pubs[r["bundle_id"]]["edges"]
           or r["vectors"] != r["sections"] or r["publication_id"] != pubs[r["bundle_id"]]["publication_id"]]
    rows = [{"publication_id": pubs[b]["publication_id"], "bundle_id": b, "source_pin": SOURCE_PIN, "compiler_version": "okf_bq_graph.compile/0.1.0",
             "node_count": pubs[b]["nodes"], "edge_count": pubs[b]["edges"], "section_count": 22, "vector_count": 22,
             "embedding_model": EMBEDDING_MODEL + " (reused by text digest)", "validation_status": "READY" if b not in {x["bundle_id"] for x in bad} else "INVALID_READBACK",
             "validation_reasons": [], "created_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "ready_at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
            for b in bundle_ids]
    _load(client, f"{full}.publications", rows)
    _load(client, f"{full}.active_publication", [{"bundle_id": b, "publication_id": pubs[b]["publication_id"],
                                                  "switched_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "previous_publication_id": None}
                                                 for b in bundle_ids if b not in {x["bundle_id"] for x in bad}])
    out = {"corpus": corpus, "ds": ds, "copies": n, "start": start, "compile_s": compile_s, "load_nodes_job": jn.job_id, "load_edges_job": je.job_id,
           "vector_reuse_job": jv.job_id, "vector_rows": jv.num_dml_affected_rows, "vector_slot_ms": jv.slot_millis,
           "nodes_loaded": len(nodes), "edges_loaded": len(edges), "invalid": bad, "wall_s": round(time.monotonic() - t0, 1),
           "publications": pubs}
    with open(f"evidence/scale_{corpus}.json", "w") as fh:
        json.dump(out, fh, indent=1, default=str)
    return out


if __name__ == "__main__":
    import sys
    n, start, corpus, base_pub, ds = int(sys.argv[1]), int(sys.argv[2]), sys.argv[3], sys.argv[4], sys.argv[5]
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    o = publish_copies(client, n, start, corpus, base_pub, ds=ds)
    print(json.dumps({k: v for k, v in o.items() if k != "publications"}, indent=1, default=str))
