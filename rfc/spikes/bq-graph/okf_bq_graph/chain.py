"""Connected chain (JOINT B, 2026-09-06): one Acme path from a seed to a consumer decision.

    seed (fixture | catalog) -> pinned publication -> governed retrieval (this spike) -> Attested Computation declaration + SQL
    -> SDK receipt example runs that computation under the caller's identity (subprocess, no SDK edits)
    -> independent verifier verdict -> consumer releases only on VERIFIED, refuses on UNVERIFIABLE / REJECTED.

Catalog-seeded mode (2026-09-06, plan U1-U3): a fresh Dataplex Catalog list + get(view=ALL) returns the runtime-owned
pin (publication + exact Concept id); that returned pin is validated against trusted configuration, resolved to exactly
one retained READY publication and exact seed (the head is observed, never followed), the exact clean pinned source is
compiled as the trusted projection, and every retrieved payload is verified row/byte-wise against it before binding.
A stale, missing, invalid or unavailable pin is a typed refusal before any content, SDK call or fallback.

Honesty labels carried in the evidence:
* seed.mode = "fixture": the seed is the harness's forced override (no live KC discovery, no semantic ranking).
* seed.mode = "catalog": a fresh live Dataplex read through `catalog.HttpReader`; "catalog-mock": injected responses
  through the same parser (hermetic; never a live Catalog success). The declaration-mismatch adversary uses an
  explicitly labelled injected fixture seed in either mode, never a second Catalog discovery.
* engine: "oracle" (in-process reference, hermetic), "fallback" (relational joins on the published tables, on-demand;
  NOT BigQuery Graph) or "gql" (GA GQL; needs an Enterprise window this module does not open).
* same requester: the graph leg and the receipt leg run under the operator's own ADC credential; the second
  principal (`sa:okf-receipt-restricted`) is not exercised here.
* the SDK is invoked as a subprocess (`examples/okf_attested_computation/run.py`); its fixture publication is bound to
  the graph's declaration by file digest and SQL text, and the sealed receipt's `computation_digest` is recomputed
  here from the same bytes (domain constant copied from the SDK's contracts.py at the pinned commit).
* substitution: the SDK's fixed `sql-substitution` case (product-cost-only formula) is the executed-SQL swap; the CLI
  has no free-form case, so a "total ARR" swap is not what runs. The graph-side swap (`declaration-mismatch`) is a
  different reachable computation that the bind step refuses before anything executes.
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import re
import secrets
import shutil
import subprocess
import sys
import tempfile
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import BUNDLE_ID, DATASET, LOCATION, PROJECT, SOURCE_PIN
from .catalog import CatalogConfig, CatalogRefusal, is_live_reader, read_seed
from .journal import Journal
from .model import node_id as _node_id
from .publication import BigQueryStore, ProjectionStore, resolve_publication, trusted_source, verify_payload
from .retrieve import retrieve, _freshness
from .seed import ConceptSeed

SDK_ROOT_DEFAULT = "/Users/haiyuancao/BigQuery-Agent-Analytics-SDK-receipt-spike"
SDK_PIN = "6719eb535667963fa640dd4535e508b550eb6cb1"
EXAMPLE_REL = "examples/okf_attested_computation"
PUBLICATION_PIN = "pub_190192147fd7fd78"                 # evidence/projection_acme.json, deterministic from the source bytes
COMPUTATION_PATH = "computations/gross-margin-period.md"
SEED = "forced:metrics/gross-margin.md"                  # one LINKS_TO hop to the sanctioned computation
MISMATCH_SEED = "forced:metrics/revenue.md"
MISMATCH_PATH = "computations/revenue-ytd.md"
DOMAIN_COMPUTATION = "okf-receipt:computation-bytes"     # SDK contracts.DOMAIN_COMPUTATION at SDK_PIN (copied, not imported)
SDK_FENCE_RE = re.compile(r"```sql\n(.*?)```", re.DOTALL)  # SDK publication._FENCE_RE at SDK_PIN
CASES = ("approved", "sql-substitution", "declaration-mismatch")
VERIFIED, UNVERIFIABLE, REJECTED = "VERIFIED", "UNVERIFIABLE", "REJECTED"
Runner = Callable[..., subprocess.CompletedProcess]


def sha256_hex(raw: bytes) -> str:
    return hashlib.sha256(raw).hexdigest()


def computation_digest(raw: bytes) -> str:
    """The SDK receipt's `computation_digest`: SHA-256 over domain || 0x00 || raw computation bytes."""
    return sha256_hex(DOMAIN_COMPUTATION.encode("ascii") + b"\x00" + raw)


def sdk_root() -> str:
    return os.environ.get("OKF_SDK_ROOT") or SDK_ROOT_DEFAULT


def _git(root: str, *args: str) -> Optional[str]:
    try:
        r = subprocess.run(["git", "-C", root, *args], capture_output=True, text=True, timeout=30)
        return r.stdout.strip() if r.returncode == 0 else None
    except (OSError, subprocess.TimeoutExpired):
        return None


def sdk_publication(root: str) -> dict:
    """The SDK example's pinned fixture publication, read from its data files only (manifest + copied Acme bytes)."""
    ex = Path(root) / EXAMPLE_REL
    manifest = json.loads((ex / "fixtures" / "publication.json").read_text(encoding="utf-8"))
    raw = (ex / "fixtures" / manifest["computation_path"]).read_bytes()
    fences = SDK_FENCE_RE.findall(raw.decode("utf-8"))
    head = _git(root, "rev-parse", "HEAD")
    dirty = _git(root, "status", "--porcelain", "--", EXAMPLE_REL)
    repo_dirty = _git(root, "status", "--porcelain")   # the example imports SDK modules: the whole checkout must be clean
    return {"manifest": manifest, "computation_sha256": sha256_hex(raw), "computation_digest": computation_digest(raw),
            "sanctioned_sql": fences[0] if len(fences) == 1 else None, "fence_count": len(fences),
            "sdk_head": head, "sdk_head_matches_pin": head == SDK_PIN, "sdk_dirty": bool(dirty) if dirty is not None else None,
            "sdk_repo_dirty": bool(repo_dirty) if repo_dirty is not None else None, "run_py": str(ex / "run.py")}


# ----------------------------------------------------------------------------- graph leg
def governed(query: str, publication_id: str, requester: Any, as_of: str, clients: dict) -> dict:
    return retrieve(query, BUNDLE_ID, publication_id, requester, as_of, clients)


def pick_computation(result: dict, path: str) -> Optional[dict]:
    """The reached computation at `path`. The oracle engine reports only the local concept id; the scoped node id is
    derived the same way the live engines report it."""
    for c in result.get("computations", []):
        if c.get("path") == path:
            if not c.get("computation_id"):
                c = dict(c, computation_id=_node_id(BUNDLE_ID, result["scope"]["publication_id"], "Concept", c["concept"]))
            return c
    return None


def declaration(clients: dict, computation_id: str, publication_id: str) -> dict:
    """The Attested Computation node as the caller sees it (the retained store's node rows or the projection for the
    oracle, `nodes` table otherwise). Catalog mode reads the store so the read is journaled like the live one."""
    if clients.get("engine") == "oracle" and clients.get("store") is not None:
        store = clients["store"]
        rows = [n for n in store.nodes.get(publication_id, []) if n["node_id"] == computation_id]
        store._job("chain_declaration", "nodes WHERE node_id=@id AND publication_id=@p (declaration)", rows)
    elif clients.get("engine") == "oracle":
        rows = [n for n in clients["projection"]["nodes"] if n["node_id"] == computation_id and n["publication_id"] == publication_id]
    else:
        from google.cloud import bigquery
        from .publish import run
        full = f"{PROJECT}.{clients.get('ds', DATASET)}"
        job = run(clients["bq"], f"""SELECT node_id, kind, local_id, path, type, runtime, status, stale_after, file_sha256, attrs
                                    FROM `{full}.nodes` WHERE node_id = @id AND publication_id = @p""",
                  [bigquery.ScalarQueryParameter("id", "STRING", computation_id), bigquery.ScalarQueryParameter("p", "STRING", publication_id)],
                  labels={"okf_spike": "bq_graph_20260905", "stage": "chain_declaration"})
        rows = [dict(r) for r in job.result()]
        rows[0:1] = [dict(rows[0], _job_id=job.job_id)] if rows else []
    if not rows:
        return {"status": "NOT_VISIBLE", "node_id": computation_id}
    n = rows[0]
    attrs = json.loads(n.get("attrs") or "{}") if isinstance(n.get("attrs"), str) else (n.get("attrs") or {})
    return {"status": "OK", "node_id": n["node_id"], "path": n.get("path"), "type": n.get("type"), "runtime": n.get("runtime"),
            "lifecycle_status": n.get("status") or "stable", "stale_after": n.get("stale_after"), "file_sha256": n.get("file_sha256"),
            "parameters": attrs.get("parameters"), "receipt_fields": attrs.get("receipt"), "job_id": n.get("_job_id")}


def _norm_sql(s: Optional[str]) -> str:
    return "\n".join(line.rstrip() for line in (s or "").strip().splitlines())


def bind(comp: dict, decl: dict, sdk_pub: dict, as_of: str, source_pin: str = SOURCE_PIN) -> dict:
    """Bind what governed retrieval returned to what the SDK example will execute. Every check is recorded; any
    failure is MISMATCH and the receipt leg must not run. `source_pin` is the verified graph source revision (the
    validated Catalog pin in catalog mode; the module constant in fixture mode) and must appear in full in the SDK
    fixture's `derived_from` lineage label."""
    m = sdk_pub["manifest"]
    derived_from = m.get("derived_from") or ""
    fresh = _freshness(decl.get("stale_after"), as_of)
    decl_params = [(p.get("name"), str(p.get("type", "")).upper()) for p in (decl.get("parameters") or [])]
    sdk_params = [(p["name"], p["type"].upper()) for p in m["parameters"]]
    checks = {
        "declared_type": {"ok": decl.get("type") == "Attested Computation", "graph": decl.get("type")},
        "runtime": {"ok": decl.get("runtime") == "bigquery" == m["runtime"], "graph": decl.get("runtime"), "sdk": m["runtime"]},
        "path": {"ok": comp.get("path") == COMPUTATION_PATH and os.path.basename(comp.get("path") or "") == os.path.basename(m["computation_path"]),
                 "graph": comp.get("path"), "sdk": m["computation_path"]},
        "file_sha256": {"ok": bool(decl.get("file_sha256")) and decl.get("file_sha256") == sdk_pub["computation_sha256"] == m["computation_sha256"],
                        "graph": decl.get("file_sha256"), "sdk_bytes": sdk_pub["computation_sha256"], "sdk_manifest": m["computation_sha256"]},
        "sql_text": {"ok": bool(comp.get("sql")) and _norm_sql(comp.get("sql")) == _norm_sql(sdk_pub["sanctioned_sql"]),
                     "graph_sql_sha256": comp.get("sql_sha256"),
                     "sdk_fence_sha256": sha256_hex((sdk_pub["sanctioned_sql"] or "").encode()) if sdk_pub["sanctioned_sql"] else None,
                     "note": "compared after trailing-whitespace normalisation: the graph fence regex drops the final newline the SDK keeps"},
        "parameters": {"ok": bool(decl_params) and decl_params == sdk_params, "graph": decl_params, "sdk": sdk_params},
        "source_pin": {"ok": bool(source_pin) and derived_from.endswith("@ " + source_pin), "graph": source_pin, "sdk": derived_from,
                       "note": "the SDK fixture manifest's derived_from is a free-text lineage label at the pinned SDK commit, compared "
                               "against the full verified graph revision; it is not a Git attestation of that revision"},
        "freshness": {"ok": fresh["verdict"] == "FRESH", "verdict": fresh["verdict"], "stale_after": fresh.get("stale_after"), "as_of": as_of},
        "lifecycle": {"ok": decl.get("lifecycle_status", "stable") == "stable", "graph": decl.get("lifecycle_status")},
        "not_executed_by_graph": {"ok": comp.get("runtime_verdict") == "NOT_EXECUTED", "graph": comp.get("runtime_verdict")},
    }
    ok = all(c["ok"] for c in checks.values())
    return {"status": "BOUND" if ok else "MISMATCH", "checks": checks,
            "computation_digest": sdk_pub["computation_digest"] if checks["file_sha256"]["ok"] else None,
            "sdk_publication_id": m["publication_id"], "sdk_context_ref": m["context_ref"],
            "trust_tier": comp.get("trust_tier"), "concept_hops": comp.get("concept_hops"), "via": comp.get("via")}


# ----------------------------------------------------------------------------- receipt leg (subprocess)
def run_receipt(case: str, root: str, out_dir: str, live: bool, runner: Runner = subprocess.run,
                timeout: int = 900) -> dict:
    """Invoke the SDK example CLI for one case. The verdict is read from the CLI's own per-case diagnostic JSON, not
    from stdout. The CLI writes into an invocation-private directory that no other launch can see (overlapping runs
    cannot exchange evidence: Astra P2), the file must be newer than the launch, and the retained file is moved from
    that private artifact into `out_dir`, which the caller owns for this run alone (run_chain passes its own run
    directory, so two successful overlapping runs never share a retained path). The record carries the diagnostic's
    request id and SHA-256 so every reference reconciles. A missing, stale or unparsable diagnostic is UNVERIFIABLE and
    `diag_present = False`."""
    out_dir = str(Path(out_dir).resolve())   # the CLI runs with the SDK root as cwd: never let a relative path land there
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    mode = "live" if live else "hermetic"
    inv_dir = tempfile.mkdtemp(prefix=f".inv_{case}_{mode}_", dir=out_dir)
    argv = [sys.executable, str(Path(root) / EXAMPLE_REL / "run.py"), "--case", case, "--evidence-dir", inv_dir]
    env = dict(os.environ)
    if live:
        argv.append("--live")
        env["GOOGLE_CLOUD_PROJECT"] = PROJECT
    private_diag = Path(inv_dir) / f"case_{case}_{mode}.json"
    diag_path = Path(out_dir) / f"case_{case}_{mode}.json"   # retained artifact, moved from this invocation's private dir only
    launched_at = time.time()
    t0 = time.monotonic()
    try:
        r = runner(argv, cwd=root if os.path.isdir(root) else None, env=env, capture_output=True, text=True, timeout=timeout)
        exit_code, stdout, stderr = r.returncode, r.stdout or "", r.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:  # the CLI never ran to completion: nothing to verify
        exit_code, stdout, stderr = -1, "", f"{type(e).__name__}: {str(e)[:300]}"
    elapsed = round((time.monotonic() - t0) * 1000, 1)
    diag, reason, raw = None, "diag_missing", None
    try:
        if private_diag.stat().st_mtime < launched_at - 1.0:   # 1 s tolerance for filesystem timestamp granularity
            reason = "diag_stale"
        else:
            raw = private_diag.read_bytes()
            diag = json.loads(raw.decode("utf-8"))
    except (OSError, ValueError):
        diag = None
    if diag is not None and raw is not None:
        os.replace(private_diag, diag_path)
    shutil.rmtree(inv_dir, ignore_errors=True)
    rec = {"case": case, "invoked": True, "argv": argv, "cwd": root, "live": live, "exit_code": exit_code, "elapsed_ms": elapsed,
           "stdout": stdout[-2000:], "stderr_tail": stderr[-1500:], "invocation_dir": inv_dir,
           "diag_path": str(diag_path) if diag is not None else None, "diag": diag, "diag_present": diag is not None,
           "diag_sha256": sha256_hex(raw) if diag is not None and raw is not None else None,
           "request_id": (diag or {}).get("request_id")}
    if diag is None:
        rec["receipt"] = {"verdict": UNVERIFIABLE, "execution_match": "UNKNOWN", "reason": reason}
        rec["output"] = {"verdict": UNVERIFIABLE, "execution_match": "UNKNOWN", "reason_codes": [reason]}
        rec["released"] = False
        return rec
    issued = diag.get("issue_out") or {}
    receipt = issued.get("receipt") or {}
    rec["receipt"] = {k: receipt.get(k, issued.get(k)) for k in ("verdict", "execution_match", "computation_digest", "publication_id",
                                                                "context_ref", "receipt_id", "request_id", "job", "reason_codes",
                                                                "policy_version", "attester_artifact_hash", "issued_at", "expires_at")}
    o = diag.get("output") or {}
    rec["output"] = {k: o.get(k) for k in ("verdict", "execution_match", "reason_codes", "job", "access_probe", "receipt_id", "request_id")}
    rec["output"]["reason_codes"] = list(rec["output"].get("reason_codes") or [])
    rec["released"] = bool(diag.get("released"))
    return rec


# ----------------------------------------------------------------------------- consumer
def consume(b: dict, rec: dict) -> dict:
    """Deterministic consumer: every binding must hold or the number is withheld. Reasons name the failed check."""
    reasons: list[str] = []
    if b.get("status") != "BOUND":
        reasons.append(f"bind status {b.get('status')}: declaration not bound to the executed publication")
    if not rec.get("invoked"):
        reasons.append("receipt not invoked: nothing executed, nothing verifiable")
        return {"decision": "REFUSED", "reasons": reasons}
    receipt, out = rec.get("receipt") or {}, rec.get("output") or {}
    if rec.get("exit_code") != 0:
        reasons.append(f"exit_code {rec.get('exit_code')} != 0")
    for label, v in (("receipt.verdict", receipt.get("verdict")), ("output.verdict", out.get("verdict"))):
        if v != VERIFIED:
            reasons.append(f"{label} {v}: consumer refuses on {UNVERIFIABLE}/{REJECTED}")
    if receipt.get("execution_match") != "MATCH" or out.get("execution_match") != "MATCH":
        reasons.append(f"execution_match {receipt.get('execution_match')}/{out.get('execution_match')} != MATCH")
    if out.get("reason_codes"):
        reasons.append("reason_codes " + ",".join(out["reason_codes"]))
    if not b.get("computation_digest") or receipt.get("computation_digest") != b.get("computation_digest"):
        reasons.append("computation_digest of the sealed receipt differs from the digest of the retrieved declaration bytes")
    if receipt.get("publication_id") != b.get("sdk_publication_id"):
        reasons.append("publication_id of the receipt is not the bound SDK publication")
    if receipt.get("context_ref") != b.get("sdk_context_ref"):
        reasons.append("context_ref of the receipt is not the bound SDK context_ref")
    if not rec.get("released"):
        reasons.append("CLI consumer did not report released=true")
    lines = [ln for ln in (rec.get("stdout") or "").splitlines() if ln.strip()]
    if len(lines) != 1 or VERIFIED not in lines[0]:
        reasons.append("stdout is not exactly one VERIFIED release line")
    if reasons:
        return {"decision": "REFUSED", "reasons": reasons}
    return {"decision": "RELEASED", "reasons": [], "display": lines[0]}


# ----------------------------------------------------------------------------- acceptance (Astra P1)
EXPECTED = {"approved": "RELEASED", "sql-substitution": "REFUSED", "declaration-mismatch": "REFUSED"}


def accept(c: dict) -> dict:
    """Did this case reach its intended stage AND produce its specific evidence? A refused consumer decision is not
    proof that a negative executed: each case must show the stage it was meant to reach and the exact rejection it was
    meant to trigger. `NOT_REACHED` = infrastructure or upstream failure before the intended stage (fail-closed but
    unproven); `WRONG` = the stage was reached and the outcome contradicts the expectation; `MET` = as designed."""
    case = c["case"]
    failed: list[str] = []
    not_reached: list[str] = []
    r = c.get("retrieval") or {}
    if r.get("status") != "OK" or not r.get("reached"):
        not_reached.append(f"retrieval status={r.get('status')} reached={r.get('reached')}")
    if (c.get("declaration") or {}).get("status") != "OK":
        not_reached.append(f"declaration status={(c.get('declaration') or {}).get('status')}")
    p = c.get("payload")
    if p is not None:   # catalog mode: the payload guard sits between retrieval and bind
        if p.get("status") == "INCONSISTENT":   # reached, and the content contradicts the pinned publication: never an outage
            failed.append(f"payload INCONSISTENT: {','.join(p.get('failed') or [])}")
        elif p.get("status") != "CONSISTENT":
            not_reached.append(f"payload status={p.get('status')}")
    b, rec, decision = c.get("bind") or {}, c.get("receipt") or {}, (c.get("consume") or {}).get("decision")
    if case in ("approved", "sql-substitution"):
        if not not_reached and b.get("status") != "BOUND":
            failed.append(f"bind status={b.get('status')} (graph and SDK publication disagree)")
        if not rec.get("invoked"):
            not_reached.append("receipt not invoked")
        elif rec.get("exit_code") == -1 or not rec.get("diag_present"):
            not_reached.append(f"receipt child did not complete: exit_code={rec.get('exit_code')} diag_present={rec.get('diag_present')}")
    if case == "approved":
        if not not_reached:   # an unreached stage ends REFUSED by design: that is unproven, not contradictory
            if rec.get("exit_code") != 0:
                failed.append(f"exit_code={rec.get('exit_code')} != 0")
            if decision != "RELEASED":
                failed.append(f"consume decision={decision} != RELEASED")
    elif case == "sql-substitution":
        if decision != "REFUSED":
            failed.append(f"consume decision={decision}: a substitution was released")
        if rec.get("invoked") and rec.get("diag_present"):
            rc, o = rec.get("receipt") or {}, rec.get("output") or {}
            if rec.get("exit_code") != 2:
                failed.append(f"exit_code={rec.get('exit_code')} != 2 (the CLI's blocked exit)")
            for label, v in (("receipt.verdict", rc.get("verdict")), ("output.verdict", o.get("verdict"))):
                if v != REJECTED:
                    failed.append(f"{label}={v} != REJECTED")
            if rc.get("execution_match") != "MISMATCH" or o.get("execution_match") != "MISMATCH":
                failed.append(f"execution_match={rc.get('execution_match')}/{o.get('execution_match')} != MISMATCH")
            if "sql_mismatch" not in (o.get("reason_codes") or []):
                failed.append(f"reason_codes={o.get('reason_codes')} lack sql_mismatch")
            if rec.get("released"):
                failed.append("CLI reported released=true on a substitution")
    elif case == "declaration-mismatch":
        if decision != "REFUSED":
            failed.append(f"consume decision={decision}: an unbound declaration was released")
        if not not_reached:
            if b.get("status") != "MISMATCH":
                failed.append(f"bind status={b.get('status')} != MISMATCH")
            else:
                bad = {k for k, v in (b.get("checks") or {}).items() if not v.get("ok")}
                for must in ("file_sha256", "sql_text"):
                    if must not in bad:
                        failed.append(f"bind check {must} did not fail: the alternate declaration was not distinguished by content")
        if rec.get("invoked"):
            failed.append("receipt invoked on an unbound declaration")
    else:
        failed.append(f"unknown case {case}")
    if failed:
        return {"status": "WRONG", "expected": EXPECTED.get(case), "failed": failed + not_reached}
    if not_reached:
        return {"status": "NOT_REACHED", "expected": EXPECTED.get(case), "failed": not_reached}
    return {"status": "MET", "expected": EXPECTED.get(case), "failed": []}


# ----------------------------------------------------------------------------- identity (live only)
def resolve_pointer_job(client: Any, ds: str = DATASET) -> tuple[Optional[str], Optional[str]]:
    """`active_publication` pointer under the caller's client, returning the job id too: this one query job precedes the
    provenance gate and belongs in the identity set."""
    from google.cloud import bigquery
    from .publish import run
    job = run(client, f"SELECT publication_id FROM `{PROJECT}.{ds}.active_publication` WHERE bundle_id = @b",
              [bigquery.ScalarQueryParameter("b", "STRING", BUNDLE_ID)], labels={"okf_spike": "bq_graph_20260905", "stage": "chain_pointer"})
    rows = list(job.result())
    return (rows[0]["publication_id"] if rows else None), job.job_id


def job_ids_of(cases: list[dict], pointer_job_id: Optional[str] = None, journal_job_ids: Optional[list[str]] = None) -> dict:
    """Every job the chain submitted: the pointer lookup, the journaled pin-resolution / head-observation / payload-row
    jobs (catalog mode), retrieval jobs and the declaration job of each case (graph leg) and every receipt job (SDK
    leg). The identity claim covers all of them, not a capped sample (Astra P2 #4)."""
    graph: list[str] = [pointer_job_id] if pointer_job_id else []
    for jid in journal_job_ids or []:
        if jid and jid not in graph:
            graph.append(jid)
    receipt: list[dict] = []
    for c in cases:
        for j in ((c.get("retrieval") or {}).get("timing") or {}).get("jobs", []) or []:
            if j.get("job_id"):
                graph.append(j["job_id"])
        d = c.get("declaration") or {}
        if d.get("job_id"):
            graph.append(d["job_id"])
        for j in (c.get("payload") or {}).get("jobs") or []:          # catalog mode: payload row reads (BigQueryStore returns two)
            for jj in (j.values() if isinstance(j, dict) and "nodes_job" in j else [j]):
                if isinstance(jj, dict) and jj.get("job_id") and jj["job_id"] not in graph:
                    graph.append(jj["job_id"])
        rec = c.get("receipt") or {}
        job = (rec.get("receipt") or {}).get("job") if rec.get("invoked") else None
        if job and job.get("job_id"):
            receipt.append(job)
    return {"graph": graph, "receipt": receipt}


def same_requester(client: Any, graph_job_ids: list[str], receipt_jobs: list[dict]) -> dict:
    """jobs.get under the operator: every graph-leg job and every receipt-leg job must carry one KNOWN user_email.
    Nothing to compare, an unreadable job, or a missing identity is UNKNOWN (never SAME); more than one identity is
    DIFFERENT."""
    receipt_ids = [j for j in receipt_jobs if j.get("job_id")]
    if not graph_job_ids or not receipt_ids:
        return {"status": "UNKNOWN", "reason": f"nothing to compare: graph_jobs={len(graph_job_ids)} receipt_jobs={len(receipt_ids)}"}
    emails: dict[str, Any] = {}
    try:
        for jid in graph_job_ids:
            emails[jid] = client.get_job(jid, project=PROJECT, location=LOCATION).user_email
        for job in receipt_ids:
            emails[job["job_id"]] = client.get_job(job["job_id"], project=job.get("project", PROJECT), location=job.get("location", LOCATION)).user_email
    except Exception as e:  # noqa: BLE001 - unknown identity blocks the claim, never invents it
        return {"status": "UNKNOWN", "reason": f"{type(e).__name__}: {str(e)[:200]}", "jobs_compared": len(emails)}
    missing = [jid for jid, em in emails.items() if not em]
    if missing:
        return {"status": "UNKNOWN", "reason": f"identity missing on {len(missing)} job(s): equality of absent identities proves nothing",
                "jobs": emails, "jobs_compared": len(emails)}
    distinct = sorted(set(emails.values()))
    return {"status": "SAME" if len(distinct) == 1 else "DIFFERENT", "user_email": distinct, "jobs": emails,
            "jobs_compared": len(emails), "graph_jobs": len(graph_job_ids), "receipt_jobs": len(receipt_ids),
            "note": "operator ADC on both legs; the restricted SA is not exercised in this chain"}


# ----------------------------------------------------------------------------- whole chain
CHAIN_VERSION = "okf_bq_graph.chain/0.5.0"
SEED_MODES = ("fixture", "catalog")


def _stage_error(e: BaseException) -> dict:
    return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:400]}"}


def _broken(out: dict, at: str, run_dir: str, out_dir: str, mode: str, redact: Callable, journal: Optional[Journal]) -> dict:
    out["verdict"] = "CHAIN_BROKEN"; out["broken_at"] = at; out["cases"] = []
    out.setdefault("same_requester", {"status": "NOT_RUN", "reason": f"refused at {at} before any case executed"})
    return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal)


def run_chain(engine: str, live: bool, sdk_root: str, out_dir: str, clients: Optional[dict] = None, projection: Optional[dict] = None,
              requester: Any = None, as_of: Optional[str] = None, runner: Runner = subprocess.run, cases: tuple = CASES,
              acme_root: Optional[str] = None, seed_mode: str = "fixture", catalog_reader: Any = None,
              catalog_cfg: Optional[CatalogConfig] = None, store: Any = None) -> dict:
    from .authz import operator, redact
    if live and engine == "oracle":
        raise ValueError("live mode needs a BigQuery graph engine (fallback|gql): oracle + SDK --live is not a mode")
    if not live and engine != "oracle":
        raise ValueError("hermetic mode uses the oracle engine only")
    if seed_mode not in SEED_MODES:
        raise ValueError(f"seed_mode must be one of {SEED_MODES}")
    catalog = seed_mode == "catalog"
    if catalog and catalog_reader is None:
        raise ValueError("catalog seed mode needs a Catalog reader (HttpReader live; an injected reader hermetic)")
    acme_root = acme_root or os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail")
    as_of = as_of or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mode = "live" if live else "hermetic"
    run_id = f"{mode}-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
    # KTD5: the run-owned evidence directory exists before any external operation (Catalog, BigQuery, SDK)
    run_dir = str(Path(out_dir) / run_id) if catalog else str(Path(out_dir) / "receipt" / run_id)
    Path(run_dir).mkdir(parents=True, exist_ok=True)
    journal = Journal(run_dir, run_id)
    receipt_dir = str(Path(run_dir) / "receipt") if catalog else run_dir
    out: dict[str, Any] = {"chain": CHAIN_VERSION, "run_id": run_id, "run_dir": run_dir, "mode": mode, "engine": engine,
                           "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                           "as_of": as_of, "bundle_id": BUNDLE_ID, "source_pin": SOURCE_PIN,
                           "requester": {"mode": "same-requester", "note": "graph leg and receipt leg both under the operator's ADC credential"},
                           "verdict_rule": "CHAIN_CONNECTED only when provenance pins hold before any case executes, every case is MET (reached its "
                                           "stage with its specific evidence) and, live, every submitted job (pointer lookup, pin resolution, head "
                                           "observation, payload rows, retrieval, declaration, receipt) carries one known user_email; CHAIN_INCOMPLETE "
                                           "when a case never reached its stage (outage on any leg, including approved); CHAIN_BROKEN when a reached "
                                           "stage contradicts the expectation, a payload is inconsistent with the pinned publication, or a pin/seed "
                                           "refuses (stale, invalid, unavailable, out of scope)"}
    if catalog:
        out["seed"] = {"mode": getattr(catalog_reader, "mode", "catalog-mock"), "status": "PENDING",
                       "note": "exact Concept id from the Catalog runtime aspect; no fixture, head, vector or saved-response fallback"}
    else:
        out["seed"] = {"mode": "fixture", "query": SEED, "note": "forced seed: harness-only deterministic override, not a semantic ranking; "
                                                                  "live Knowledge Catalog discovery is out of scope for this chain"}
    # SDK pin
    try:
        sdk_pub = sdk_publication(sdk_root)
    except (OSError, ValueError, KeyError) as e:
        out["sdk"] = _stage_error(e)
        return _broken(out, "sdk", run_dir, out_dir, mode, redact, journal)
    out["sdk"] = {"root": sdk_root, "head": sdk_pub["sdk_head"], "pin": SDK_PIN, "head_matches_pin": sdk_pub["sdk_head_matches_pin"],
                  "example_dirty": sdk_pub["sdk_dirty"], "repo_dirty": sdk_pub["sdk_repo_dirty"],
                  "publication_id": sdk_pub["manifest"]["publication_id"],
                  "computation_sha256": sdk_pub["computation_sha256"], "computation_digest": sdk_pub["computation_digest"],
                  "synthetic_fixture": bool(sdk_pub["manifest"].get("synthetic")), "invocation": "subprocess run.py (no SDK source edits)"}
    out["sdk_publication"] = {"publication_id": sdk_pub["manifest"]["publication_id"], "context_ref": sdk_pub["manifest"]["context_ref"],
                              "computation_sha256": sdk_pub["computation_sha256"], "derived_from": sdk_pub["manifest"].get("derived_from"),
                              "note": "the SDK receipt example's fixture publication: a separate identity from the graph publication, joined only by bytes"}
    # clients + requester
    if clients is None:
        if engine == "oracle" and not catalog:
            from .compile import compile_bundle
            projection = projection or compile_bundle(acme_root, BUNDLE_ID, SOURCE_PIN)
            from .oracle import Graph
            clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection}
        elif engine == "oracle":
            clients = {"engine": "oracle"}      # graphs come from the retained store below
        else:
            from google.cloud import bigquery
            clients = {"engine": engine, "bq": bigquery.Client(project=PROJECT, location=LOCATION)}
    requester = requester or operator()
    pointer_job_id = None
    source_pin = SOURCE_PIN
    pin = None
    trusted: Optional[dict] = None
    if catalog:
        # ---- reader mode gate (KTD1): live needs the real HTTP reader; hermetic must not touch the network
        reader_live = is_live_reader(catalog_reader)
        if live and not reader_live:
            out["seed"].update(status="READER_REFUSED", reason="live catalog mode refuses a mock/saved-response/fixture reader")
            return _broken(out, "seed", run_dir, out_dir, mode, redact, journal)
        if not live and reader_live:
            out["seed"].update(status="READER_REFUSED", reason="hermetic catalog mode needs an injected reader; the HTTP reader is live-only")
            return _broken(out, "seed", run_dir, out_dir, mode, redact, journal)
        cfg = catalog_cfg or CatalogConfig()
        out["catalog"] = {"api": "dataplex v1 entries.list + entries.get(view=ALL)", "group": cfg.group, "entry": cfg.entry,
                          "aspect_key": cfg.aspect_key, "reader": type(catalog_reader).__name__, "reader_mode": getattr(catalog_reader, "mode", None)}
        # ---- fresh read
        journal.note("catalog_read_started", entry=cfg.entry, reader=type(catalog_reader).__name__)
        try:
            seed = read_seed(catalog_reader, cfg, retain=lambda name, raw: journal.retain(name, raw, subdir="catalog"))
        except Exception as e:  # noqa: BLE001
            seed = CatalogRefusal("CATALOG_ERROR", f"reader raised {type(e).__name__}: {str(e)[:200]}", "list")
        if isinstance(seed, CatalogRefusal):
            out["seed"].update(seed.record(), retained=list(journal.retained))
            return _broken(out, "seed", run_dir, out_dir, mode, redact, journal)
        out["seed"] = dict(out["seed"], **seed.record(), retained=list(journal.retained))
        pin = seed.pin
        source_pin = pin.source_pin
        out["source_pin"] = source_pin
        out["bundle_id"] = pin.bundle_id
        # ---- retained store (configured destination only; the pin cannot name it)
        if store is None:
            if live:
                if clients.get("bq") is None:
                    out["publication"] = {"status": "ERROR", "error": "live mode needs a BigQuery client in clients['bq']"}
                    return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
                store = BigQueryStore(clients["bq"], cfg.runtime_project, clients.get("ds", cfg.runtime_dataset), cfg.runtime_location, journal)
            else:
                out["publication"] = {"status": "ERROR", "error": "hermetic catalog mode needs an injected retained store (ProjectionStore)"}
                return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
        elif getattr(store, "journal", None) is not journal:
            store.journal = journal                 # every store read is journaled under this run
        out["store"] = {"engine": getattr(store, "engine", None), "dataset": getattr(store, "dataset", None)}
        # ---- exact retained publication + seed (head observed only)
        res = resolve_publication(store, pin)
        out["publication"] = {"status": res["status"], "publication_id": pin.publication_id, "pin": pin.publication_id,
                              "source": "Catalog pin resolved against the retained publications/nodes tables (parameterised)",
                              "reasons": res.get("reasons"), "checks": res.get("checks"), "head": res.get("head"),
                              "matches_pin": res["status"] == "OK", "error": res.get("error")}
        if res["status"] != "OK":
            return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
        # ---- trusted compilation of the exact clean source
        t = trusted_source(pin, acme_root)
        out["source"] = {k: v for k, v in t.items() if k != "projection"}
        out["source"]["bundle_root"] = acme_root
        if t["status"] != "OK":
            return _broken(out, "source", run_dir, out_dir, mode, redact, journal)
        trusted = t["projection"]
        pub = pin.publication_id
        out["graph_publication"] = {"bundle_id": pin.bundle_id, "publication_id": pub, "source_pin": pin.source_pin,
                                    "source_manifest_sha256": pin.source_manifest_sha256, "compiler_version": pin.compiler_version,
                                    "nodes_sha256": trusted["output_manifest"]["nodes_sha256"], "edges_sha256": trusted["output_manifest"]["edges_sha256"],
                                    "note": "the graph publication / source manifest identity, separate from the SDK fixture publication"}
        if engine == "oracle":
            clients = dict(clients, graphs=getattr(store, "graphs", {}), store=store)
        prov = {"publication_pin": trusted["publication_id"] == pub, "sdk_head_pin": bool(sdk_pub["sdk_head_matches_pin"]),
                "sdk_clean": sdk_pub["sdk_repo_dirty"] is False, "sdk_git_state_known": sdk_pub["sdk_repo_dirty"] is not None,
                "source_verified": True, "seed_mode": out["seed"]["mode"]}
    else:
        # pinned publication (live: one query job, submitted before the gate and counted in the identity set)
        try:
            if engine == "oracle":
                pub = projection["publication_id"]
                out["publication"] = {"status": "OK", "publication_id": pub, "source": "compiled projection (deterministic from the pinned bytes)"}
            else:
                if clients.get("bq") is None:
                    raise RuntimeError("live mode needs a BigQuery client in clients['bq']")
                pub, pointer_job_id = resolve_pointer_job(clients["bq"], clients.get("ds", DATASET))
                out["publication"] = {"status": "OK" if pub else "NO_PUBLICATION", "publication_id": pub, "source": "active_publication pointer",
                                      "job_id": pointer_job_id}
            out["publication"]["matches_pin"] = pub == PUBLICATION_PIN
            out["publication"]["pin"] = PUBLICATION_PIN
        except Exception as e:  # noqa: BLE001
            out["publication"] = _stage_error(e); pub = None
        if not pub:
            return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
        prov = {"publication_pin": out["publication"]["matches_pin"], "sdk_head_pin": bool(sdk_pub["sdk_head_matches_pin"]),
                "sdk_clean": sdk_pub["sdk_repo_dirty"] is False, "sdk_git_state_known": sdk_pub["sdk_repo_dirty"] is not None}
        out["graph_publication"] = {"bundle_id": BUNDLE_ID, "publication_id": pub, "source_pin": SOURCE_PIN,
                                    "note": "fixture mode: the compiled/pointer publication checked against the module pin constant"}
    # provenance gate (Astra P2 #2): no case executes on an unknown or mismatched pin
    prov["ok"] = prov["publication_pin"] and prov["sdk_head_pin"] and prov["sdk_clean"]
    out["provenance"] = prov
    if not prov["ok"]:
        out["same_requester"] = {"status": "NOT_RUN", "reason": "provenance gate refused before any case executed"}
        return _broken(out, "provenance", run_dir, out_dir, mode, redact, journal)

    def graph_leg(seed: Any, path: str) -> tuple[dict, Optional[dict], Optional[dict], Optional[dict]]:
        try:
            r = governed(seed, pub, requester, as_of, clients)
        except Exception as e:  # noqa: BLE001 - e.g. GQL without an Enterprise window
            return {"retrieval": dict(_stage_error(e), seed=str(seed), reached=False)}, None, None, None
        rec = {"retrieval": {"seed": str(seed), "seed_origin": getattr(seed, "origin", "forced"), "status": r["status"],
                             "warnings": r.get("warnings", []), "scope": r.get("scope"),
                             "concepts": [c.get("concept") for c in r.get("concepts", [])],
                             "paths": r.get("paths", []), "computations": [c.get("path") for c in r.get("computations", [])],
                             "timing": r.get("timing")}}
        comp = pick_computation(r, path) if r["status"] == "OK" else None
        if comp is None:
            rec["retrieval"]["reached"] = False
            return rec, None, None, r
        rec["retrieval"]["reached"] = True
        rec["computation"] = {k: comp.get(k) for k in ("concept", "computation_id", "section_id", "path", "concept_hops", "via", "status",
                                                        "runtime", "trust_tier", "freshness", "sql_sha256", "runtime_verdict")}
        rec["computation"]["sql_chars"] = len(comp.get("sql") or "")
        try:
            decl = declaration(clients, comp["computation_id"], pub)
        except Exception as e:  # noqa: BLE001
            decl = _stage_error(e)
        rec["declaration"] = decl
        return rec, comp, decl, r

    out["cases"] = []
    Path(receipt_dir).mkdir(parents=True, exist_ok=True)
    for case in cases:
        if catalog:
            if case == "declaration-mismatch":
                seed: Any = ConceptSeed(_node_id(pin.bundle_id, pub, "Concept", MISMATCH_SEED[len("forced:"):-3]), origin="injected-fixture-seed")
            else:
                seed = pin.seed(out["seed"]["mode"])
            path = MISMATCH_PATH if case == "declaration-mismatch" else COMPUTATION_PATH
        else:
            seed, path = (MISMATCH_SEED, MISMATCH_PATH) if case == "declaration-mismatch" else (SEED, COMPUTATION_PATH)
        c: dict[str, Any] = {"case": case, "expected": EXPECTED.get(case)}
        c["attack"] = {"approved": None,
                       "sql-substitution": "SDK case: agent executes a product-cost-only formula for the approved request and claims 600 (executed-SQL swap)",
                       "declaration-mismatch": "graph-side swap: a different reachable Attested Computation (revenue-ytd) is offered in place of the bound one"
                                               + ("; its seed is an explicit harness injection under the pinned publication, not a Catalog discovery" if catalog else "")}[case]
        leg, comp, decl, full_result = graph_leg(seed, path)
        c.update(leg)
        if catalog and full_result is not None and comp is not None and decl is not None and decl.get("status") == "OK":
            c["payload"] = verify_payload(store, pin, trusted, full_result, comp, decl, expected_path=path, seed_id=seed.concept_id)
        elif catalog:
            c["payload"] = {"status": "NOT_REACHED", "reason": "computation not reached or declaration not visible: nothing to verify"}
        if comp is None or decl is None or decl.get("status") != "OK":
            c["bind"] = {"status": "NOT_BOUND", "reason": "computation not reached or declaration not visible"}
        elif catalog and c["payload"]["status"] != "CONSISTENT":
            c["bind"] = {"status": "NOT_BOUND", "reason": f"payload consistency {c['payload']['status']}: the returned payload is not the pinned publication's content"}
        else:
            c["bind"] = bind(comp, decl, sdk_pub, as_of, source_pin=source_pin)
        if c["bind"]["status"] == "BOUND":
            sdk_case = "sql-substitution" if case == "sql-substitution" else "approved"
            c["receipt"] = run_receipt(sdk_case, sdk_root, receipt_dir, live, runner=runner)
            c["receipt"]["diag"] = None if c["receipt"].get("diag") is None else f"see {c['receipt']['diag_path']}"
        else:
            c["receipt"] = {"invoked": False, "reason": "bind did not hold: nothing was executed"}
        c["consume"] = consume(c["bind"], c["receipt"])
        c["acceptance"] = accept(c)
        out["cases"].append(c)
    out["decisions"] = {c["case"]: c["consume"]["decision"] for c in out["cases"]}
    out["acceptance"] = {c["case"]: c["acceptance"]["status"] for c in out["cases"]}
    ids = job_ids_of(out["cases"], pointer_job_id, journal.job_ids())
    out["job_inventory"] = {"graph": ids["graph"], "receipt": [j.get("job_id") for j in ids["receipt"]],
                            "journal": journal.summary(), "note": "every submitted job including empty/failed lookups; roles in journal.jsonl"}
    if live:
        out["same_requester"] = same_requester(clients.get("bq"), ids["graph"], ids["receipt"]) if clients.get("bq") is not None \
            else {"status": "UNKNOWN", "reason": "no BigQuery client"}
    else:
        out["same_requester"] = {"status": "NOT_APPLICABLE", "reason": "hermetic mode: oracle graph + SDK SYNTHETIC emulation submit no BigQuery jobs"}
    statuses = [c["acceptance"]["status"] for c in out["cases"]]
    if any(s == "WRONG" for s in statuses) or (live and out["same_requester"]["status"] == "DIFFERENT"):
        out["verdict"] = "CHAIN_BROKEN"
    elif any(s == "NOT_REACHED" for s in statuses) or (live and out["same_requester"]["status"] != "SAME"):
        out["verdict"] = "CHAIN_INCOMPLETE"
    else:
        out["verdict"] = "CHAIN_CONNECTED"
    if out["verdict"] != "CHAIN_CONNECTED":
        out["broken_at"] = next((c["case"] for c in out["cases"] if c["acceptance"]["status"] == "WRONG"),
                                next((c["case"] for c in out["cases"] if c["acceptance"]["status"] == "NOT_REACHED"), "same_requester"))
    return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal)


def _finish(out: dict, out_dir: str, mode: str, redact: Callable, run_dir: Optional[str] = None, journal: Optional[Journal] = None) -> dict:
    """Publish the record: atomically to `chain_<mode>.json` (last writer wins, but it references only its own run
    directory) and as a retained copy inside the run directory. Early refusals get the same retained final record."""
    out["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if journal is not None:
        out["journal"] = journal.record()
        out["evidence"] = {"run_dir": run_dir, "journal": str(journal.path), "unresolved_jobs": journal.summary()["unresolved"],
                           "retained": [{"name": r["name"], "sha256": r["sha256"]} for r in journal.retained]}
    out = redact(out)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, indent=1, sort_keys=True, default=str) + "\n"
    final = Path(out_dir) / f"chain_{mode}.json"
    tmp = final.with_name(f".{final.name}.{out.get('run_id', 'norun')}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, final)
    own = Path(run_dir) if run_dir else (Path(out_dir) / "receipt" / out["run_id"] if out.get("run_id") else None)
    if own is not None and own.is_dir():
        (own / final.name).write_text(text, encoding="utf-8")
    return out


def _mock_reader_from_file(path: str) -> Any:
    from .catalog import MockReader
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    return MockReader(body["pages"], body["entries"])


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="connected graph -> receipt chain (fixture or Catalog seed; same requester)")
    ap.add_argument("--hermetic", action="store_true", help="oracle graph engine + SDK synthetic emulation (default)")
    ap.add_argument("--live", action="store_true", help="published tables under ADC + SDK --live (real BigQuery jobs)")
    ap.add_argument("--engine", choices=("oracle", "fallback", "gql"), default=None,
                    help="graph engine for --live (default fallback; gql needs an Enterprise window this module does not open)")
    ap.add_argument("--seed-mode", choices=SEED_MODES, default="fixture",
                    help="fixture: forced local seed (default). catalog: fresh Dataplex list/get returns the pin (live) or injected responses (hermetic, --catalog-responses)")
    ap.add_argument("--catalog-group", default=None, help="entry group resource name (default: the KC-unblock demo group)")
    ap.add_argument("--catalog-entry", default=None, help="entry resource name inside the group (default: the KC-unblock gross-margin entry)")
    ap.add_argument("--catalog-responses", default=None, help="hermetic only: JSON {pages: [...], entries: {name: body}} fed through the real parser (seed.mode=catalog-mock)")
    ap.add_argument("--sdk-root", default=sdk_root())
    ap.add_argument("--out", default=None, help="evidence root (default evidence/chain; evidence/catalog-chain for --seed-mode catalog)")
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--acme-root", default=None)
    a = ap.parse_args(argv)
    if a.live and a.hermetic:
        ap.error("--live and --hermetic are exclusive")
    live = bool(a.live)
    if live and a.engine == "oracle":
        ap.error("--live needs --engine fallback|gql: the oracle engine submits no jobs, so a live identity claim cannot be made")
    if not live and a.engine not in (None, "oracle"):
        ap.error("--engine other than oracle requires --live")
    engine = (a.engine or "fallback") if live else "oracle"
    out_dir = a.out or ("evidence/catalog-chain" if a.seed_mode == "catalog" else "evidence/chain")
    reader, cfg, store = None, None, None
    if a.seed_mode == "catalog":
        kw = {k: v for k, v in (("group", a.catalog_group), ("entry", a.catalog_entry)) if v}
        if "group" in kw and "entry" not in kw:
            ap.error("--catalog-group needs --catalog-entry")
        cfg = CatalogConfig(**kw)
        if live:
            if a.catalog_responses:
                ap.error("--live --seed-mode catalog cannot take --catalog-responses: a saved/mock provider is not a live Catalog read")
            from .catalog import HttpReader
            reader = HttpReader()
        else:
            if not a.catalog_responses:
                ap.error("--seed-mode catalog without --live needs --catalog-responses (injected responses; labelled catalog-mock)")
            reader = _mock_reader_from_file(a.catalog_responses)
            from .compile import compile_bundle
            proj = compile_bundle(a.acme_root or os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"), BUNDLE_ID, SOURCE_PIN)
            store = ProjectionStore(journal=None, dataset="hermetic-store (clean pinned compile as READY head)")
            store.add(proj); store.set_head(BUNDLE_ID, proj["publication_id"])
    elif a.catalog_group or a.catalog_entry or a.catalog_responses:
        ap.error("--catalog-* flags need --seed-mode catalog")
    out = run_chain(engine=engine, live=live, sdk_root=a.sdk_root, out_dir=out_dir, as_of=a.as_of, acme_root=a.acme_root,
                    seed_mode=a.seed_mode, catalog_reader=reader, catalog_cfg=cfg, store=store)
    for c in out.get("cases", []):
        rec = c.get("receipt") or {}
        rv = (rec.get("output") or {}).get("verdict", "NOT_INVOKED") if rec.get("invoked") else "NOT_INVOKED"
        acc = c.get("acceptance", {})
        pl = f" payload={c['payload']['status']:12s}" if c.get("payload") else ""
        print(f"{c['case']:22s}{pl} bind={c.get('bind', {}).get('status'):9s} receipt={rv:13s} consume={c['consume']['decision']:8s} "
              f"acceptance={acc.get('status')}" + (f" failed={'; '.join(acc.get('failed', []))[:200]}" if acc.get("failed") else ""))
    print(f"seed_mode={out['seed'].get('mode')} seed_status={out['seed'].get('status', 'fixture')} publication={out.get('publication', {}).get('status')} "
          f"provenance_ok={out.get('provenance', {}).get('ok')} same_requester={out.get('same_requester', {}).get('status')} "
          f"engine={out['engine']} mode={out['mode']} sdk_head={str(out.get('sdk', {}).get('head'))[:7]} run_dir={out.get('run_dir')}")
    print(f"verdict={out['verdict']}" + (f" broken_at={out.get('broken_at')}" if out['verdict'] != 'CHAIN_CONNECTED' else ""))
    return 0 if out["verdict"] == "CHAIN_CONNECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
