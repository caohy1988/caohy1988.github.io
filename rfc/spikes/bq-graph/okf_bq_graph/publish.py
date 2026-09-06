"""Publish an immutable projection into BigQuery and switch the pointer (spec §3, Task 3).

Append -> validate counts/digests/vectors -> mark READY -> atomic pointer MERGE.
An interrupted publish (inject_failure="before_pointer") leaves the old pointer serving.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import time
from typing import Any, Optional

from google.cloud import bigquery

from . import DATASET, LOCATION, PROJECT
from .compile import validate_projection

SQL_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "sql")
EMBEDDING_MODEL = "text-embedding-005"
EMBEDDING_MODEL_REF = "text_embedding"    # remote model in the spike dataset


def sql(name: str, ds: str) -> str:
    with open(os.path.join(SQL_DIR, name)) as fh:
        return fh.read().replace("{ds}", ds)


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _ts(s: Optional[str]) -> Optional[str]:
    if not s or "T" not in s:
        return None
    try:
        return _dt.datetime.fromisoformat(s.replace("Z", "+00:00")).astimezone(_dt.timezone.utc).strftime("%Y-%m-%d %H:%M:%S+00")
    except ValueError:
        return None


def run(client: bigquery.Client, query: str, params: Optional[list] = None, labels: Optional[dict] = None,
        use_cache: bool = False) -> bigquery.QueryJob:
    cfg = bigquery.QueryJobConfig(query_parameters=params or [], use_query_cache=use_cache,
                                  labels=labels or {"okf_spike": "bq_graph_20260905"})
    job = client.query(query, job_config=cfg, location=LOCATION)
    job.result()
    return job


def ensure_schema(client: bigquery.Client, ds: str = DATASET) -> None:
    text = "\n".join(l for l in sql("schema.sql", f"{PROJECT}.{ds}").splitlines() if not l.strip().startswith("--"))
    for stmt in text.split(";"):
        if stmt.strip():
            run(client, stmt)


def ensure_graph(client: bigquery.Client, ds: str = DATASET) -> dict:
    """Graph DDL is shared across publications; (re)creating it is idempotent."""
    job = run(client, sql("graph.sql", f"{PROJECT}.{ds}"))
    return {"job_id": job.job_id, "at": _now().isoformat()}


def _load(client: bigquery.Client, table: str, rows: list[dict]) -> bigquery.LoadJob:
    t = client.get_table(table)
    cfg = bigquery.LoadJobConfig(schema=t.schema, write_disposition="WRITE_APPEND",
                                 source_format=bigquery.SourceFormat.NEWLINE_DELIMITED_JSON)
    job = client.load_table_from_json(rows, table, job_config=cfg, location=LOCATION)
    job.result()
    return job


def resolve_pointer(client: bigquery.Client, bundle_id: str, ds: str = DATASET) -> Optional[str]:
    job = run(client, f"SELECT publication_id FROM `{PROJECT}.{ds}.active_publication` WHERE bundle_id = @b",
              [bigquery.ScalarQueryParameter("b", "STRING", bundle_id)])
    rows = list(job.result())
    return rows[0]["publication_id"] if rows else None


def publish(projection: dict, bq_client: bigquery.Client, ds: str = DATASET, embed: bool = True,
            inject_failure: Optional[str] = None, manifest_path: Optional[str] = "evidence/publish_log.jsonl") -> dict:
    B, P = projection["bundle_id"], projection["publication_id"]
    full = f"{PROJECT}.{ds}"
    log: dict[str, Any] = {"bundle_id": B, "publication_id": P, "started_at": _now().isoformat(), "jobs": [], "ds": ds}
    t0 = time.monotonic()
    v = validate_projection(projection)
    log["validation"] = v
    if not v["valid"]:
        log["state"] = "REJECTED"
        _append(manifest_path, log)
        return log
    ensure_schema(bq_client, ds)
    # immutability: an existing READY publication is never rewritten
    existing = list(run(bq_client, f"SELECT validation_status FROM `{full}.publications` WHERE publication_id = @p",
                        [bigquery.ScalarQueryParameter("p", "STRING", P)]).result())
    if existing and existing[0]["validation_status"] == "READY":
        log["state"] = "ALREADY_READY"
        prev = resolve_pointer(bq_client, B, ds)
        if prev != P and inject_failure != "before_pointer":
            log["pointer"] = _switch(bq_client, full, B, P, prev)
        log["pointer_now"] = resolve_pointer(bq_client, B, ds)
        _append(manifest_path, log)
        return log
    nodes = [dict(n, stale_after_ts=_ts(n.get("stale_after"))) for n in projection["nodes"]]
    j = _load(bq_client, f"{full}.nodes", nodes); log["jobs"].append({"load_nodes": j.job_id, "rows": j.output_rows})
    j = _load(bq_client, f"{full}.edges", projection["edges"]); log["jobs"].append({"load_edges": j.job_id, "rows": j.output_rows})
    vector_count = 0
    if embed:
        q = f"""
        INSERT INTO `{full}.section_vectors`
          (node_id, bundle_id, publication_id, concept_id, heading, embedding_model, embedding_model_version, task_type,
           text_sha256, dims, embedding, created_at)
        SELECT node_id, bundle_id, publication_id, concept_id, heading, @model, NULL, 'RETRIEVAL_DOCUMENT',
               text_sha256, ARRAY_LENGTH(ml_generate_embedding_result), ml_generate_embedding_result, CURRENT_TIMESTAMP()
        FROM ML.GENERATE_EMBEDDING(MODEL `{full}.{EMBEDDING_MODEL_REF}`,
          (SELECT n.node_id, n.bundle_id, n.publication_id, e.src_id AS concept_id, n.heading, n.text_sha256,
                  CONCAT(COALESCE(c.title, ''), ' — ', COALESCE(n.heading, ''), '\\n', n.text) AS content
           FROM `{full}.nodes` n
           JOIN `{full}.edges` e ON e.dst_id = n.node_id AND e.relation = 'HAS_SECTION' AND e.publication_id = @p
           JOIN `{full}.nodes` c ON c.node_id = e.src_id
           WHERE n.publication_id = @p AND n.kind = 'Section'),
          STRUCT(TRUE AS flatten_json_output, 'RETRIEVAL_DOCUMENT' AS task_type))
        WHERE ml_generate_embedding_status = ''
        """
        j = run(bq_client, q, [bigquery.ScalarQueryParameter("p", "STRING", P),
                               bigquery.ScalarQueryParameter("model", "STRING", EMBEDDING_MODEL)])
        log["jobs"].append({"embed": j.job_id, "rows": j.num_dml_affected_rows, "slot_ms": j.slot_millis,
                            "bytes": j.total_bytes_processed})
        vector_count = j.num_dml_affected_rows or 0
    # readback validation
    chk = list(run(bq_client, f"""
      SELECT (SELECT COUNT(*) FROM `{full}.nodes` WHERE publication_id = @p) AS nodes,
             (SELECT COUNT(*) FROM `{full}.edges` WHERE publication_id = @p) AS edges,
             (SELECT COUNT(*) FROM `{full}.nodes` WHERE publication_id = @p AND kind = 'Section') AS sections,
             (SELECT COUNT(*) FROM `{full}.section_vectors` WHERE publication_id = @p) AS vectors,
             (SELECT COUNT(*) FROM `{full}.edges` e WHERE e.publication_id = @p AND NOT EXISTS (
                 SELECT 1 FROM `{full}.nodes` n WHERE n.node_id = e.src_id) OR NOT EXISTS (
                 SELECT 1 FROM `{full}.nodes` n WHERE n.node_id = e.dst_id)) AS dangling,
             (SELECT COUNT(DISTINCT node_id) FROM `{full}.nodes` WHERE publication_id = @p) AS distinct_nodes,
             (SELECT COUNT(*) FROM `{full}.section_vectors` v JOIN `{full}.nodes` n USING (node_id)
               WHERE v.publication_id = @p AND v.text_sha256 <> n.text_sha256) AS vector_digest_mismatch
    """, [bigquery.ScalarQueryParameter("p", "STRING", P)]).result())[0]
    chk = dict(chk)
    log["readback"] = chk
    ok = (chk["nodes"] == len(projection["nodes"]) and chk["edges"] == len(projection["edges"]) and chk["dangling"] == 0
          and chk["distinct_nodes"] == chk["nodes"] and chk["vector_digest_mismatch"] == 0
          and (not embed or chk["vectors"] == chk["sections"]))
    om = projection["output_manifest"]
    status = "READY" if ok else "INVALID_READBACK"
    run(bq_client, f"""
      INSERT INTO `{full}.publications`
        (publication_id, bundle_id, source_pin, compiler_version, source_manifest_sha256, nodes_sha256, edges_sha256,
         node_count, edge_count, section_count, vector_count, embedding_model, validation_status, validation_reasons, created_at, ready_at)
      VALUES (@p, @b, @pin, @cv, @sm, @ns, @es, @nc, @ec, @sc, @vc, @model, @st, [], CURRENT_TIMESTAMP(),
              IF(@st = 'READY', CURRENT_TIMESTAMP(), NULL))
    """, [bigquery.ScalarQueryParameter("p", "STRING", P), bigquery.ScalarQueryParameter("b", "STRING", B),
          bigquery.ScalarQueryParameter("pin", "STRING", projection["source_pin"]),
          bigquery.ScalarQueryParameter("cv", "STRING", projection["compiler_version"]),
          bigquery.ScalarQueryParameter("sm", "STRING", projection["source_manifest_sha256"]),
          bigquery.ScalarQueryParameter("ns", "STRING", om["nodes_sha256"]), bigquery.ScalarQueryParameter("es", "STRING", om["edges_sha256"]),
          bigquery.ScalarQueryParameter("nc", "INT64", om["nodes"]), bigquery.ScalarQueryParameter("ec", "INT64", om["edges"]),
          bigquery.ScalarQueryParameter("sc", "INT64", chk["sections"]), bigquery.ScalarQueryParameter("vc", "INT64", vector_count),
          bigquery.ScalarQueryParameter("model", "STRING", EMBEDDING_MODEL if embed else None),
          bigquery.ScalarQueryParameter("st", "STRING", status)])
    log["graph"] = ensure_graph(bq_client, ds)
    log["state"] = status
    if status != "READY":
        _append(manifest_path, log)
        return log
    if inject_failure == "before_pointer":
        log["state"] = "INTERRUPTED_BEFORE_POINTER"
        log["pointer_now"] = resolve_pointer(bq_client, B, ds)
        _append(manifest_path, log)
        raise RuntimeError("injected failure before pointer switch")
    prev = resolve_pointer(bq_client, B, ds)
    log["pointer"] = _switch(bq_client, full, B, P, prev)
    log["pointer_now"] = resolve_pointer(bq_client, B, ds)
    log["elapsed_s"] = round(time.monotonic() - t0, 3)
    _append(manifest_path, log)
    return log


def _switch(client: bigquery.Client, full: str, B: str, P: str, prev: Optional[str]) -> dict:
    j = run(client, f"""
      MERGE `{full}.active_publication` t USING (SELECT @b AS bundle_id, @p AS publication_id) s ON t.bundle_id = s.bundle_id
      WHEN MATCHED THEN UPDATE SET previous_publication_id = t.publication_id, publication_id = s.publication_id, switched_at = CURRENT_TIMESTAMP()
      WHEN NOT MATCHED THEN INSERT (bundle_id, publication_id, switched_at, previous_publication_id) VALUES (s.bundle_id, s.publication_id, CURRENT_TIMESTAMP(), NULL)
    """, [bigquery.ScalarQueryParameter("b", "STRING", B), bigquery.ScalarQueryParameter("p", "STRING", P)])
    return {"job_id": j.job_id, "from": prev, "to": P, "at": _now().isoformat()}


def _append(path: Optional[str], rec: dict) -> None:
    if not path:
        return
    with open(path, "a") as fh:
        fh.write(json.dumps(rec, default=str) + "\n")


if __name__ == "__main__":
    import sys
    from .compile import compile_bundle
    from . import BUNDLE_ID, SOURCE_PIN
    root = sys.argv[1]
    bundle = sys.argv[2] if len(sys.argv) > 2 else BUNDLE_ID
    pin = sys.argv[3] if len(sys.argv) > 3 else SOURCE_PIN
    proj = compile_bundle(root, bundle, pin)
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    out = publish(proj, client)
    print(json.dumps(out, indent=2, default=str))
