"""Connected chain (JOINT B, 2026-09-06): one Acme path from a fixture seed to a consumer decision.

    seed (fixture) -> pinned publication -> governed retrieval (this spike) -> Attested Computation declaration + SQL
    -> SDK receipt example runs that computation under the caller's identity (subprocess, no SDK edits)
    -> independent verifier verdict -> consumer releases only on VERIFIED, refuses on UNVERIFIABLE / REJECTED.

Honesty labels carried in the evidence:
* seed.mode = "fixture": the seed is the harness's forced override (no live KC discovery, no semantic ranking).
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
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import BUNDLE_ID, DATASET, LOCATION, PROJECT, SOURCE_PIN
from .model import node_id as _node_id
from .retrieve import retrieve, _freshness

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
    """The Attested Computation node as the caller sees it (projection for the oracle, `nodes` table otherwise)."""
    if clients.get("engine") == "oracle":
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


def bind(comp: dict, decl: dict, sdk_pub: dict, as_of: str) -> dict:
    """Bind what governed retrieval returned to what the SDK example will execute. Every check is recorded; any
    failure is MISMATCH and the receipt leg must not run."""
    m = sdk_pub["manifest"]
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
        "source_pin": {"ok": SOURCE_PIN[:7] in (m.get("derived_from") or ""), "graph": SOURCE_PIN, "sdk": m.get("derived_from")},
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
    from stdout. The diagnostic path is cleared before the launch and must be newer than the launch: a missing, stale
    or unparsable diagnostic is UNVERIFIABLE and `diag_present = False` (Astra P2 #3)."""
    out_dir = str(Path(out_dir).resolve())   # the CLI runs with the SDK root as cwd: never let a relative path land there
    argv = [sys.executable, str(Path(root) / EXAMPLE_REL / "run.py"), "--case", case, "--evidence-dir", out_dir]
    env = dict(os.environ)
    if live:
        argv.append("--live")
        env["GOOGLE_CLOUD_PROJECT"] = PROJECT
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    diag_path = Path(out_dir) / f"case_{case}_{'live' if live else 'hermetic'}.json"
    diag_path.unlink(missing_ok=True)
    launched_at = time.time()
    t0 = time.monotonic()
    try:
        r = runner(argv, cwd=root if os.path.isdir(root) else None, env=env, capture_output=True, text=True, timeout=timeout)
        exit_code, stdout, stderr = r.returncode, r.stdout or "", r.stderr or ""
    except (OSError, subprocess.TimeoutExpired) as e:  # the CLI never ran to completion: nothing to verify
        exit_code, stdout, stderr = -1, "", f"{type(e).__name__}: {str(e)[:300]}"
    elapsed = round((time.monotonic() - t0) * 1000, 1)
    diag, reason = None, "diag_missing"
    try:
        if diag_path.stat().st_mtime < launched_at - 1.0:   # 1 s tolerance for filesystem timestamp granularity
            reason = "diag_stale"
        else:
            diag = json.loads(diag_path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        diag = None
    rec = {"case": case, "invoked": True, "argv": argv, "cwd": root, "live": live, "exit_code": exit_code, "elapsed_ms": elapsed,
           "stdout": stdout[-2000:], "stderr_tail": stderr[-1500:], "diag_path": str(diag_path), "diag": diag,
           "diag_present": diag is not None}
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
    b, rec, decision = c.get("bind") or {}, c.get("receipt") or {}, (c.get("consume") or {}).get("decision")
    if case in ("approved", "sql-substitution"):
        if not not_reached and b.get("status") != "BOUND":
            failed.append(f"bind status={b.get('status')} (graph and SDK publication disagree)")
        if not rec.get("invoked"):
            not_reached.append("receipt not invoked")
        elif rec.get("exit_code") == -1 or not rec.get("diag_present"):
            not_reached.append(f"receipt child did not complete: exit_code={rec.get('exit_code')} diag_present={rec.get('diag_present')}")
    if case == "approved":
        if rec.get("invoked") and rec.get("diag_present") and rec.get("exit_code") != 0:
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
def job_ids_of(cases: list[dict]) -> dict:
    """Every job the chain submitted: retrieval jobs and the declaration job of each case (graph leg) and every
    receipt job (SDK leg). The identity claim covers all of them, not a capped sample (Astra P2 #4)."""
    graph: list[str] = []
    receipt: list[dict] = []
    for c in cases:
        for j in ((c.get("retrieval") or {}).get("timing") or {}).get("jobs", []) or []:
            if j.get("job_id"):
                graph.append(j["job_id"])
        d = c.get("declaration") or {}
        if d.get("job_id"):
            graph.append(d["job_id"])
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
def _stage_error(e: BaseException) -> dict:
    return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:400]}"}


def run_chain(engine: str, live: bool, sdk_root: str, out_dir: str, clients: Optional[dict] = None, projection: Optional[dict] = None,
              requester: Any = None, as_of: Optional[str] = None, runner: Runner = subprocess.run, cases: tuple = CASES,
              acme_root: Optional[str] = None) -> dict:
    from .authz import operator, redact
    if live and engine == "oracle":
        raise ValueError("live mode needs a BigQuery graph engine (fallback|gql): oracle + SDK --live is not a mode")
    if not live and engine != "oracle":
        raise ValueError("hermetic mode uses the oracle engine only")
    as_of = as_of or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mode = "live" if live else "hermetic"
    out = {"chain": "okf_bq_graph.chain/0.2.0", "mode": mode, "engine": engine, "started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
           "as_of": as_of, "bundle_id": BUNDLE_ID, "source_pin": SOURCE_PIN,
           "seed": {"mode": "fixture", "query": SEED, "note": "forced seed: harness-only deterministic override, not a semantic ranking; "
                                                                "live Knowledge Catalog discovery is out of scope for this chain"},
           "requester": {"mode": "same-requester", "note": "graph leg and receipt leg both under the operator's ADC credential"},
           "verdict_rule": "CHAIN_CONNECTED only when provenance pins hold, every case is MET (reached its stage with its specific "
                           "evidence) and, live, every submitted job carries one known user_email; CHAIN_INCOMPLETE when a case never "
                           "reached its stage; CHAIN_BROKEN when a reached stage contradicts the expectation or a pin fails"}
    # SDK pin
    try:
        sdk_pub = sdk_publication(sdk_root)
    except (OSError, ValueError, KeyError) as e:
        out["sdk"] = _stage_error(e); out["verdict"] = "CHAIN_BROKEN"; out["broken_at"] = "sdk"; out["cases"] = []
        return _finish(out, out_dir, mode, redact)
    out["sdk"] = {"root": sdk_root, "head": sdk_pub["sdk_head"], "pin": SDK_PIN, "head_matches_pin": sdk_pub["sdk_head_matches_pin"],
                  "example_dirty": sdk_pub["sdk_dirty"], "repo_dirty": sdk_pub["sdk_repo_dirty"],
                  "publication_id": sdk_pub["manifest"]["publication_id"],
                  "computation_sha256": sdk_pub["computation_sha256"], "computation_digest": sdk_pub["computation_digest"],
                  "synthetic_fixture": bool(sdk_pub["manifest"].get("synthetic")), "invocation": "subprocess run.py (no SDK source edits)"}
    # clients + requester
    if clients is None:
        if engine == "oracle":
            from .compile import compile_bundle
            projection = projection or compile_bundle(acme_root or os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"),
                                                      BUNDLE_ID, SOURCE_PIN)
            from .oracle import Graph
            clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection}
        else:
            from google.cloud import bigquery
            clients = {"engine": engine, "bq": bigquery.Client(project=PROJECT, location=LOCATION)}
    requester = requester or operator()
    # pinned publication
    try:
        if engine == "oracle":
            pub = projection["publication_id"]
            out["publication"] = {"status": "OK", "publication_id": pub, "source": "compiled projection (deterministic from the pinned bytes)"}
        else:
            from .publish import resolve_pointer
            pub = resolve_pointer(clients["bq"], BUNDLE_ID, clients.get("ds", DATASET))
            out["publication"] = {"status": "OK" if pub else "NO_PUBLICATION", "publication_id": pub, "source": "active_publication pointer"}
        out["publication"]["matches_pin"] = pub == PUBLICATION_PIN
        out["publication"]["pin"] = PUBLICATION_PIN
    except Exception as e:  # noqa: BLE001
        out["publication"] = _stage_error(e); pub = None
    if not pub:
        out["verdict"] = "CHAIN_BROKEN"; out["broken_at"] = "publication"; out["cases"] = []
        return _finish(out, out_dir, mode, redact)
    # provenance gate (Astra P2 #2): nothing executes on an unknown or mismatched pin
    prov = {"publication_pin": out["publication"]["matches_pin"], "sdk_head_pin": bool(sdk_pub["sdk_head_matches_pin"]),
            "sdk_clean": sdk_pub["sdk_repo_dirty"] is False, "sdk_git_state_known": sdk_pub["sdk_repo_dirty"] is not None}
    prov["ok"] = prov["publication_pin"] and prov["sdk_head_pin"] and prov["sdk_clean"]
    out["provenance"] = prov
    if not prov["ok"]:
        out["verdict"] = "CHAIN_BROKEN"; out["broken_at"] = "provenance"; out["cases"] = []
        out["same_requester"] = {"status": "NOT_RUN", "reason": "provenance gate refused before any job"}
        return _finish(out, out_dir, mode, redact)

    def graph_leg(seed: str, path: str) -> tuple[dict, Optional[dict], Optional[dict]]:
        try:
            r = governed(seed, pub, requester, as_of, clients)
        except Exception as e:  # noqa: BLE001 - e.g. GQL without an Enterprise window
            return {"retrieval": dict(_stage_error(e), seed=seed, reached=False)}, None, None
        rec = {"retrieval": {"seed": seed, "status": r["status"], "warnings": r.get("warnings", []), "scope": r.get("scope"),
                             "concepts": [c.get("concept") for c in r.get("concepts", [])],
                             "paths": r.get("paths", []), "computations": [c.get("path") for c in r.get("computations", [])],
                             "timing": r.get("timing")}}
        comp = pick_computation(r, path) if r["status"] == "OK" else None
        if comp is None:
            rec["retrieval"]["reached"] = False
            return rec, None, None
        rec["retrieval"]["reached"] = True
        rec["computation"] = {k: comp.get(k) for k in ("concept", "computation_id", "section_id", "path", "concept_hops", "via", "status",
                                                        "runtime", "trust_tier", "freshness", "sql_sha256", "runtime_verdict")}
        rec["computation"]["sql_chars"] = len(comp.get("sql") or "")
        try:
            decl = declaration(clients, comp["computation_id"], pub)
        except Exception as e:  # noqa: BLE001
            decl = _stage_error(e)
        rec["declaration"] = decl
        return rec, comp, decl

    out["cases"] = []
    receipt_dir = str(Path(out_dir) / "receipt")
    for case in cases:
        seed, path = (MISMATCH_SEED, MISMATCH_PATH) if case == "declaration-mismatch" else (SEED, COMPUTATION_PATH)
        c: dict[str, Any] = {"case": case, "expected": EXPECTED.get(case)}
        c["attack"] = {"approved": None,
                       "sql-substitution": "SDK case: agent executes a product-cost-only formula for the approved request and claims 600 (executed-SQL swap)",
                       "declaration-mismatch": "graph-side swap: a different reachable Attested Computation (revenue-ytd) is offered in place of the bound one"}[case]
        leg, comp, decl = graph_leg(seed, path)
        c.update(leg)
        if comp is None or decl is None or decl.get("status") != "OK":
            c["bind"] = {"status": "NOT_BOUND", "reason": "computation not reached or declaration not visible"}
        else:
            c["bind"] = bind(comp, decl, sdk_pub, as_of)
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
    ids = job_ids_of(out["cases"])
    if live:
        out["same_requester"] = same_requester(clients["bq"], ids["graph"], ids["receipt"])
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
    return _finish(out, out_dir, mode, redact)


def _finish(out: dict, out_dir: str, mode: str, redact: Callable) -> dict:
    out["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    out = redact(out)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    (Path(out_dir) / f"chain_{mode}.json").write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return out


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="connected graph -> receipt chain (fixture seed; same requester)")
    ap.add_argument("--hermetic", action="store_true", help="oracle graph engine + SDK synthetic emulation (default)")
    ap.add_argument("--live", action="store_true", help="published tables under ADC + SDK --live (real BigQuery jobs)")
    ap.add_argument("--engine", choices=("oracle", "fallback", "gql"), default=None,
                    help="graph engine for --live (default fallback; gql needs an Enterprise window this module does not open)")
    ap.add_argument("--sdk-root", default=sdk_root())
    ap.add_argument("--out", default="evidence/chain")
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
    out = run_chain(engine=engine, live=live, sdk_root=a.sdk_root, out_dir=a.out, as_of=a.as_of, acme_root=a.acme_root)
    for c in out.get("cases", []):
        rec = c.get("receipt") or {}
        rv = (rec.get("output") or {}).get("verdict", "NOT_INVOKED") if rec.get("invoked") else "NOT_INVOKED"
        acc = c.get("acceptance", {})
        print(f"{c['case']:22s} bind={c.get('bind', {}).get('status'):9s} receipt={rv:13s} consume={c['consume']['decision']:8s} "
              f"acceptance={acc.get('status')}" + (f" failed={'; '.join(acc.get('failed', []))[:200]}" if acc.get("failed") else ""))
    print(f"provenance_ok={out.get('provenance', {}).get('ok')} same_requester={out.get('same_requester', {}).get('status')} "
          f"engine={out['engine']} mode={out['mode']} sdk_head={str(out.get('sdk', {}).get('head'))[:7]}")
    print(f"verdict={out['verdict']}" + (f" broken_at={out.get('broken_at')}" if out['verdict'] != 'CHAIN_CONNECTED' else ""))
    return 0 if out["verdict"] == "CHAIN_CONNECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
