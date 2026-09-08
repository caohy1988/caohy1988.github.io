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
* requester: `--requester operator` (default) runs both legs under the operator's own ADC credential (same requester;
  the second principal is not exercised). `--requester restricted` (2026-09-06 Slice A) runs both legs through a
  requester broker for `sa:okf-receipt-restricted` (principal.py): four cases with stage-reachability acceptance
  (approved-restricted, denied-intermediate, unauthorized-output, revocation-before-replay), a pre-execution
  authorization probe under the requester's credential before the SDK CLI is invoked, and an identity check that expects
  the SA e-mail on every job including the pointer lookup. Hermetic = policy-emulating broker over the projection (no
  IAM, no job); live = IAM impersonation broker (wired, exercised in Slice B).
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

from . import BUNDLE_ID, DATASET, LOCATION, PROJECT, RESERVATION, SOURCE_PIN
from .catalog import CatalogConfig, CatalogRefusal, is_live_reader, read_seed
from .journal import Journal
from .model import node_id as _node_id
from .publication import BigQueryStore, ProjectionStore, resolve_publication, trusted_source, verify_payload
from .retrieve import retrieve, _freshness
from .seed import ConceptSeed
from .authz import HIDDEN, SA_ALIAS, leaks
from .principal import ALLOWED, DENIED, HermeticBroker, RestrictedBroker, policy as _policy

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
LEGACY_SEED = "forced:metrics/gross-margin-legacy.md"        # deprecated anchor: reaches the computation only THROUGH metrics/gross-margin
RESTRICTED_CASES = ("approved-restricted", "denied-intermediate", "unauthorized-output", "revocation-before-replay")
CACHE_EXEMPT_CASES = ("revocation-before-replay",)   # the cached replay IS this case's evidence; every other case executes
RESTRICTED = {   # per case: seed, the policy the broker applies before the graph leg, the attack the case models
    "approved-restricted": {"seed": SEED, "policy": _policy(), "attack": None,
                            "expects": "grants present: reached, bound, authorized, executed under the requester, VERIFIED, RELEASED"},
    "denied-intermediate": {"seed": LEGACY_SEED, "policy": _policy(dataset="rls", hidden=(HIDDEN,)),
                            "attack": f"row policy hides the intermediate concept {HIDDEN}: the only path from the legacy seed to the computation runs through it",
                            "expects": "seed visible, no path, no computation, hidden id absent from every surface the requester received (the harness's "
                                       "own policy record names it by design); bind NOT_REACHED (retrieval_denied); CLI never invoked; REFUSED"},
    "unauthorized-output": {"seed": SEED, "policy": _policy(sdk_tables=False),
                            "attack": "seed and declaration visible, but the requester cannot read the computation's dependency tables (no read on the SDK fixture dataset)",
                            "expects": "reached and bound; pre-execution authorization DENIED under the requester's credential; CLI never invoked; REFUSED before execution"},
    "revocation-before-replay": {"seed": SEED, "policy": _policy(),
                                 "attack": "grant, retrieve, execute and release once; revoke the requester's grants; replay the same request from cache and re-decide the consumer",
                                 "expects": "first pass RELEASED; after revocation the cached replay is HIT_DENIED with nothing disclosed, authorization DENIED, consumer REFUSED; CLI invoked once"},
}
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
    deps = sorted(f"{manifest['project']}.{manifest['dataset']}.{t}" for t in (manifest.get("table_map") or {}).values())   # SDK publication.py's `dependencies`
    return {"manifest": manifest, "computation_sha256": sha256_hex(raw), "computation_digest": computation_digest(raw),
            "sanctioned_sql": fences[0] if len(fences) == 1 else None, "fence_count": len(fences),
            "dependencies": deps, "dataset": manifest.get("dataset"),
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
    job_id = None
    if clients.get("store") is not None:
        # catalog mode, either engine: the store journals the read as a job before waiting (BigQueryStore: real job id
        # chosen before the send and reconciled on failure; ProjectionStore: hermetic-store record with no job id)
        rows, entry = clients["store"].declaration(computation_id, publication_id)
        job_id = entry.get("job_id")
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
        job_id = job.job_id                          # fixture mode: the id is kept even when the lookup is empty
    if not rows:
        return {"status": "NOT_VISIBLE", "node_id": computation_id, "job_id": job_id}
    n = rows[0]
    attrs = json.loads(n.get("attrs") or "{}") if isinstance(n.get("attrs"), str) else (n.get("attrs") or {})
    return {"status": "OK", "node_id": n["node_id"], "path": n.get("path"), "type": n.get("type"), "runtime": n.get("runtime"),
            "lifecycle_status": n.get("status") or "stable", "stale_after": n.get("stale_after"), "file_sha256": n.get("file_sha256"),
            "parameters": attrs.get("parameters"), "receipt_fields": attrs.get("receipt"), "job_id": job_id}


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
                timeout: int = 900, env_extra: Optional[dict] = None, label: Optional[str] = None) -> dict:
    """Invoke the SDK example CLI for one case. The verdict is read from the CLI's own per-case diagnostic JSON, not
    from stdout. The CLI writes into an invocation-private directory that no other launch can see (overlapping runs
    cannot exchange evidence: Astra P2), the file must be newer than the launch, and the retained file is moved from
    that private artifact into `out_dir`, which the caller owns for this run alone (run_chain passes its own run
    directory, so two successful overlapping runs never share a retained path). The record carries the diagnostic's
    request id and SHA-256 so every reference reconciles. A missing, stale or unparsable diagnostic is UNVERIFIABLE and
    `diag_present = False`. `label` names the retained file after the CHAIN case when several chain cases run the same
    SDK case (the restricted chain runs `approved` twice): two retained diagnostics never share a name inside one run."""
    out_dir = str(Path(out_dir).resolve())   # the CLI runs with the SDK root as cwd: never let a relative path land there
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    mode = "live" if live else "hermetic"
    inv_dir = tempfile.mkdtemp(prefix=f".inv_{case}_{mode}_", dir=out_dir)
    argv = [sys.executable, str(Path(root) / EXAMPLE_REL / "run.py"), "--case", case, "--evidence-dir", inv_dir]
    env = dict(os.environ)
    if live:
        argv.append("--live")
        env["GOOGLE_CLOUD_PROJECT"] = PROJECT
    env.update(env_extra or {})   # requester broker: e.g. GOOGLE_APPLICATION_CREDENTIALS of the impersonated SA (live restricted)
    private_diag = Path(inv_dir) / f"case_{case}_{mode}.json"
    diag_path = Path(out_dir) / f"case_{label or case}_{mode}.json"   # retained artifact, moved from this invocation's private dir only
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
           "env_injected": sorted(env_extra or {}), "retained_as": label or case,
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
def consume(b: dict, rec: dict, authz: Optional[dict] = None, containment: Optional[dict] = None) -> dict:
    """Deterministic consumer: every binding must hold or the number is withheld. Reasons name the failed check. When
    the chain runs under a requester broker, `authz` is the authorization probe taken under the requester's own
    credential at decision time (before execution, and again on a replay): anything but ALLOWED refuses, so a receipt
    sealed before a revocation cannot be replayed into a release."""
    reasons: list[str] = []
    if b.get("status") != "BOUND":
        reasons.append(f"bind status {b.get('status')}: declaration not bound to the executed publication")
    # A receipt is only as good as the containment of the process that produced it. An uncontained child was neither
    # bounded by the window deadline nor inventoried, so its verdict cannot authorize a release however well-formed.
    if containment is not None and not containment.get("contained", True):
        reasons.append(f"receipt containment failed: {containment.get('reason')}")
    if authz is not None and authz.get("status") != ALLOWED:
        reasons.append(f"authorization {authz.get('status')} at decision time: the requester's credential cannot read every dependency "
                       f"of the bound computation ({authz.get('denied', '?')} denied)")
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
EXPECTED = {"approved": "RELEASED", "sql-substitution": "REFUSED", "declaration-mismatch": "REFUSED",
            "approved-restricted": "RELEASED", "denied-intermediate": "REFUSED", "unauthorized-output": "REFUSED", "revocation-before-replay": "REFUSED"}


# what the requester sees: every stage output. The harness's own policy record (`policy`, `hidden`, `grant`, `attack`,
# `expects`) names the hidden id by design and is not a disclosure.
DISCLOSURE_SURFACE = ("retrieval", "computation", "declaration", "bind", "authorization", "receipt", "consume", "first_pass", "replay")


def _verdict(case: str, failed: list[str], not_reached: list[str]) -> dict:
    if failed:
        return {"status": "WRONG", "expected": EXPECTED.get(case), "failed": failed + not_reached}
    if not_reached:
        return {"status": "NOT_REACHED", "expected": EXPECTED.get(case), "failed": not_reached}
    return {"status": "MET", "expected": EXPECTED.get(case), "failed": []}


def accept_restricted(c: dict) -> dict:
    """Stage-reachability acceptance for the four restricted-requester cases (same rule as PR 35: a refusal alone never
    counts; each case must name the stage it reached and its specific rejection). `NOT_REACHED` = an upstream outage or
    an unpropagated grant before the intended stage (refused, unproven); `WRONG` = the stage was reached and the outcome
    contradicts the expectation (a traversed hidden row, a leaked id, an invoked CLI, a released replay)."""
    case = c["case"]
    failed: list[str] = []
    not_reached: list[str] = []
    r, b, rec, az = c.get("retrieval") or {}, c.get("bind") or {}, c.get("receipt") or {}, c.get("authorization") or {}
    decision = (c.get("consume") or {}).get("decision")
    if r.get("status") != "OK":   # every case needs the seed visible to the requester; DENIED/ERROR is an outage or an unpropagated grant
        not_reached.append(f"retrieval status={r.get('status')}: seed not visible to the requester, enforcement cannot be told from an outage")
    if case == "denied-intermediate":
        if decision != "REFUSED":
            failed.append(f"consume decision={decision}: released through a hidden intermediate")
        if rec.get("invoked"):
            failed.append("receipt invoked although no path was authorized")
        if not not_reached:
            if r.get("reached") or r.get("computations") or r.get("paths"):
                failed.append(f"hidden intermediate traversed: reached={r.get('reached')} paths={r.get('paths')} computations={r.get('computations')}")
            if b.get("status") != "NOT_REACHED" or b.get("reason") != "retrieval_denied":
                failed.append(f"bind status={b.get('status')} reason={b.get('reason')} != NOT_REACHED/retrieval_denied")
        for hid in c.get("hidden") or ():
            if leaks({k: c.get(k) for k in DISCLOSURE_SURFACE}, hid):
                failed.append("hidden identifier present on the case's disclosure surface")
        if r.get("hidden_id_in_full_result"):
            failed.append("hidden identifier present in the full retrieval result the requester received")
        return _verdict(case, failed, not_reached)
    # the other three must reach the computation and bind it
    if not r.get("reached"):
        not_reached.append(f"retrieval reached={r.get('reached')}")
    if (c.get("declaration") or {}).get("status") != "OK":
        not_reached.append(f"declaration status={(c.get('declaration') or {}).get('status')}")
    if not not_reached and b.get("status") != "BOUND":
        failed.append(f"bind status={b.get('status')} (graph and SDK publication disagree)")
    if case == "approved-restricted":
        if az.get("status") == DENIED and not not_reached:
            not_reached.append("authorization DENIED with grants present: grant not effective, execution stage never reached")
        elif az.get("status") not in (ALLOWED, DENIED):
            not_reached.append(f"authorization status={az.get('status')}")
        if not rec.get("invoked"):
            not_reached.append("receipt not invoked")
        elif rec.get("exit_code") == -1 or not rec.get("diag_present"):
            not_reached.append(f"receipt child did not complete: exit_code={rec.get('exit_code')} diag_present={rec.get('diag_present')}")
        # An uncontained child is a containment outage, not a contradicted expectation: the stage was never reached
        # under the guarantees the case exists to demonstrate, so it is unproven rather than WRONG.
        cont = rec.get("containment") or {}
        if cont and not cont.get("contained", True):
            not_reached.append(f"receipt child ran uncontained: {cont.get('reason')}")
        if not not_reached:
            if rec.get("exit_code") != 0:
                failed.append(f"exit_code={rec.get('exit_code')} != 0")
            if decision != "RELEASED":
                failed.append(f"consume decision={decision} != RELEASED")
    elif case == "unauthorized-output":
        if decision != "REFUSED":
            failed.append(f"consume decision={decision}: released without authorization")
        if rec.get("invoked"):
            failed.append("receipt invoked although authorization was denied")
        if not not_reached:
            if az.get("status") == ALLOWED:
                failed.append("authorization ALLOWED: the missing read on the dependency tables was not enforced")
            elif az.get("status") != DENIED:
                not_reached.append(f"authorization status={az.get('status')}: probe did not produce a platform decision")
            elif not az.get("denied"):
                failed.append("authorization DENIED without a denied table")
            if decision == "REFUSED" and not any("authorization" in x for x in (c.get("consume") or {}).get("reasons", [])):
                failed.append("refusal does not name the authorization denial")
    elif case == "revocation-before-replay":
        first, rev, rp = c.get("first_pass") or {}, c.get("revocation") or {}, c.get("replay") or {}
        if decision != "REFUSED":
            failed.append(f"consume decision={decision}: a replay after revocation was released")
        if c.get("receipt_invocations", 0) > 1:
            failed.append(f"receipt invoked {c.get('receipt_invocations')} times: a replay must not re-execute")
        if not not_reached:
            if first.get("decision") != "RELEASED":
                not_reached.append(f"first pass decision={first.get('decision')}: the grant never produced a release, so nothing was revoked from")
            if not rev.get("observed"):
                not_reached.append("revocation not observed by the requester")
        if not not_reached:
            rr = rp.get("retrieval") or {}
            if rr.get("status") == "OK" or rr.get("disclosed_anything") or rr.get("computations") or rr.get("paths"):
                failed.append(f"replay retrieval status={rr.get('status')} served content after revocation")
            elif rr.get("cache") != "HIT_DENIED":
                not_reached.append(f"replay cache={rr.get('cache')}: the cached-replay path was not exercised")
            for hid in c.get("hidden") or ():
                if leaks(rp, hid):
                    failed.append("identifier present on the replay surface")
            ra = rp.get("authorization") or {}
            if ra.get("status") == ALLOWED:
                failed.append("authorization ALLOWED after revocation")
            elif ra.get("status") != DENIED:
                not_reached.append(f"replay authorization status={ra.get('status')}")
            if (rp.get("consume") or {}).get("decision") != "REFUSED":
                failed.append(f"replay consume decision={(rp.get('consume') or {}).get('decision')} != REFUSED")
    else:
        failed.append(f"unknown case {case}")
    return _verdict(case, failed, not_reached)


def accept(c: dict) -> dict:
    """Did this case reach its intended stage AND produce its specific evidence? A refused consumer decision is not
    proof that a negative executed: each case must show the stage it was meant to reach and the exact rejection it was
    meant to trigger. `NOT_REACHED` = infrastructure or upstream failure before the intended stage (fail-closed but
    unproven); `WRONG` = the stage was reached and the outcome contradicts the expectation; `MET` = as designed."""
    case = c["case"]
    if case in RESTRICTED_CASES:
        return accept_restricted(c)
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
        # An uncontained child is a containment outage, not a contradicted expectation: the stage was never reached
        # under the guarantees the case exists to demonstrate, so it is unproven rather than WRONG.
        cont = rec.get("containment") or {}
        if cont and not cont.get("contained", True):
            not_reached.append(f"receipt child ran uncontained: {cont.get('reason')}")
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
    return _verdict(case, failed, not_reached)


# ----------------------------------------------------------------------------- identity (live only)
# ----------------------------------------------------------------------------- engine admission and proof (U1/U4)
GQL_WINDOW_NOT_CONFIGURED = "GQL_WINDOW_NOT_CONFIGURED"
ENGINE_PROVEN, ENGINE_NOT_PROVEN, ENGINE_CONTRADICTED = "PROVEN", "NOT_PROVEN", "CONTRADICTED"


def gql_admission(engine: str, live: bool, window: Any) -> dict:
    """A bare `--live --engine gql` must refuse BEFORE any grant, client query or SDK launch.

    `chain.py` opens no Enterprise capacity of its own. Without an owned, already-open window controller a GQL request
    can only end one of two ways: an edition error, or a silent relational answer. Neither is a Graph chain, so the run
    stops here with a typed record instead of spending anything to find out (Slice A U1, requirement R1)."""
    if not (live and engine == "gql"):
        return {"status": "NOT_REQUIRED", "engine": engine, "live": live}
    if window is None:
        return {"status": GQL_WINDOW_NOT_CONFIGURED, "engine": engine,
                "reason": "--live --engine gql needs an owned Enterprise window controller (okf_bq_graph.chain_window); "
                          "this module does not open capacity, and a GQL request without one either fails on edition "
                          "or is answered by something that is not BigQuery Graph",
                "remedy": "supply --gql-window/--gql-manifest (or pass window= to run_chain) once the legacy cleanup "
                          "gate and an explicit live authorization allow a window to open"}
    state = getattr(window, "state", None)
    if state != "OPEN":
        return {"status": "GQL_WINDOW_NOT_OPEN", "engine": engine, "window_state": state,
                "reason": "the supplied window controller has not proven an open Enterprise assignment"}
    return {"status": "OK", "engine": engine, "window": getattr(getattr(window, "cfg", None), "label", None),
            "window_state": state,
            "assignment_probes": len(((getattr(window, "record", {}) or {}).get("assignment") or {}).get("probes") or [])}


DEFERRED_TEARDOWN = "DEFERRED_TO_WINDOW_CLEANUP"


def rebuild_identity(broker: Any, out: dict, audit: Any = None) -> dict:
    """Re-audit the administrative role AFTER the deferred restoration ran.

    The chain computes its identity verdict before `window.close()`, but the registered teardown submits its
    grant-restoring DDL during close. Those jobs belong to the same "every job the run submitted" claim, so the
    inventory and the identity verdict are rebuilt over the broker's actual post-restoration state - including
    attempts it could not resolve (Astra PR47 RR3 N4)."""
    inv = out.setdefault("job_inventory", {})
    before = list(inv.get("policy_admin") or [])
    admin_jobs = [j for j in (getattr(broker, "admin_jobs", None) or []) if j.get("job_id")]
    admin_ops = list(getattr(broker, "admin_ops", None) or [])
    inv["policy_admin"] = [j["job_id"] for j in admin_jobs]
    inv["policy_admin_ops"] = admin_ops
    inv["policy_admin_unresolved"] = (broker.admin_unresolved() if hasattr(broker, "admin_unresolved")
                                      else [op for op in admin_ops if not op.get("job_id")])
    inv.setdefault("refs", {}).update({j["job_id"]: {"project": j.get("project"), "location": j.get("location"),
                                                     "stage": j.get("stage")} for j in admin_jobs})
    receipt_refs = inv.get("receipt_refs") or [{"job_id": j} for j in (inv.get("receipt") or []) if j]
    # the audit reads through the window's BOUNDED read-only channel; expiry leaves references unread, never assumed
    previous_owner = getattr(broker, "owner", None)
    if audit is not None:
        broker.owner = audit
    try:
        identity = broker.identity(list(inv.get("graph") or []), receipt_refs)
    finally:
        if audit is not None:
            broker.owner = previous_owner
    added = sorted(set(inv["policy_admin"]) - set(before))
    identity["rebuilt_after_restoration"] = {
        "policy_admin_before_close": len(before), "policy_admin_after_close": len(inv["policy_admin"]),
        "added_by_restoration": added, "unresolved": len(inv["policy_admin_unresolved"]),
        "note": "the deferred restoration submits administrative DDL during close; the identity claim covers those "
                "jobs too, so it is re-audited once they exist"}
    identity.setdefault("job_set", {}).update({"policy_admin": len(inv["policy_admin"]),
                                               "policy_admin_added_by_restoration": len(added)})
    if audit is not None:
        record = audit.record() if hasattr(audit, "record") else {}
        identity["audit"] = record
        read = set((identity.get("jobs") or {}))
        claimed = ({j for j in inv["policy_admin"]} | {j for j in (inv.get("graph") or []) if j}
                   | {r.get("job_id") for r in receipt_refs if r.get("job_id")})
        unread = sorted(j for j in claimed if j not in read)
        identity["audit"]["unread_references"] = unread
        if (record.get("expired") or unread) and identity.get("status") == "BOUND":
            identity["status"] = "UNKNOWN"
            identity["reason"] = (f"the post-close audit did not read {len(unread)} reference(s) before its deadline; "
                                  "an identity claim cannot rest on references nobody read")
    out["identity"] = identity
    return identity


def broker_teardown(broker: Any, deferred: bool) -> dict:
    """The broker's restoration, unless the window owns it.

    Under an owned window the teardown is a REGISTERED restoration: it runs at close, on the bounded cleanup channel,
    with its outcome persisted as an obligation. Running it inline here would submit its DDL on the workload channel
    (after stop, so every statement raises) and its failure would never reach the reopening gate (Astra PR47
    re-review R3)."""
    if deferred:
        return {"status": DEFERRED_TEARDOWN,
                "reason": "registered with the window controller; it runs on the bounded cleanup channel at close and "
                          "its result is written into this record by finalize_cleanup"}
    return broker.teardown()


def _is_bound(client: Any, window: Any) -> bool:
    from .lifecycle import WindowClient
    return isinstance(client, WindowClient) and client.window is getattr(window, "jobs", None)


def unbound_clients(clients: Optional[dict], broker: Any, window: Any) -> list[str]:
    """Every BigQuery client that would submit OUTSIDE the controller's single admission gate.

    A window that records a controller but hands the chain an untracked client bounds nothing: the client keeps sending
    after stop, its jobs never reach the journal, and the window still closes `clean` (Astra PR47 #1)."""
    if window is None:
        return []
    out = []
    for name, client in (("clients.bq", (clients or {}).get("bq")),
                         ("broker.requester", getattr(broker, "sa", None)),
                         ("broker.operator", getattr(broker, "owner", None))):
        if client is not None and not _is_bound(client, window):
            out.append(name)
    return out


def engine_proof(requested: str, clients: dict, result: Optional[dict], reservation: str = RESERVATION) -> dict:
    """Was the answer produced by the engine that was asked for?

    The engine label the caller passes is not evidence, and neither is a label echoed back inside a result: a returned
    selector can pick a different schema (vault: PR41 fix3). This checks the trusted client configuration, the returned
    scope, the SQL template that actually compiled, and - for GQL - the platform's own reservation/edition on the jobs
    that ran. A cached-only answer cannot establish execution, so it is NOT_PROVEN rather than proven."""
    trusted = clients.get("engine")
    out: dict[str, Any] = {"requested": requested, "trusted_client_engine": trusted,
                           "note": "engine identity comes from the trusted client configuration, the compiled template "
                                   "and the platform's own job metadata; never from a label in the answer"}
    reasons: list[str] = []
    if trusted != requested:
        return dict(out, status=ENGINE_CONTRADICTED,
                    reasons=[f"the client is configured for engine {trusted!r}, not the requested {requested!r}"])
    if result is None:
        return dict(out, status=ENGINE_NOT_PROVEN, reasons=["no retrieval result: the engine never ran"])
    scope = result.get("scope") or {}
    out["returned_engine"] = scope.get("engine")
    out["cache"] = scope.get("cache")
    out["templates"] = scope.get("templates")
    out["warnings"] = list(result.get("warnings") or [])
    if scope.get("engine") != requested:
        reasons.append(f"the returned scope names engine {scope.get('engine')!r}")
    jobs = [j for j in ((result.get("timing") or {}).get("jobs") or []) if j.get("job_id")]
    out["jobs"] = [{"stage": j.get("stage"), "job_id": j.get("job_id"), "state": j.get("state"),
                    "reservation_id": j.get("reservation_id"), "edition": j.get("edition")} for j in jobs]
    if requested != "gql":
        out["status"] = ENGINE_CONTRADICTED if reasons else ENGINE_PROVEN
        out["reasons"] = reasons
        return out
    templates = scope.get("templates") or {}
    walk = templates.get("walk") or {}
    if walk.get("name") != "governed.sql" or not walk.get("graph_table"):
        reasons.append(f"the walk stage compiled {walk.get('name')!r}"
                       + ("" if walk.get("graph_table") else " and it contains no GRAPH_TABLE clause"))
    if any("FALLBACK engine" in w for w in out["warnings"]):
        reasons.append("the answer carries the relational FALLBACK warning")
    if scope.get("cache") in ("HIT_RECHECKED", "HIT_DENIED"):
        reasons.append(f"the answer was served from cache ({scope.get('cache')}): a cached entry cannot establish that "
                       "GQL executed in this window")
    walk_jobs = [j for j in jobs if j.get("stage") in ("walk", "context")]
    if not walk_jobs:
        reasons.append("no walk/context job was submitted: nothing executed on the graph")
    for j in walk_jobs:
        if not (j.get("reservation_id") or "").endswith(reservation):
            reasons.append(f"job {j.get('job_id')} ran under reservation {j.get('reservation_id')!r}, not {reservation}")
        if (j.get("edition") or "").upper() != "ENTERPRISE":
            reasons.append(f"job {j.get('job_id')} reports edition {j.get('edition')!r}, not ENTERPRISE")
    out["reasons"] = reasons
    contradicted = any(("FALLBACK" in r) or ("compiled" in r) or ("returned scope names" in r) or ("cache" in r)
                       for r in reasons)
    out["status"] = ENGINE_PROVEN if not reasons else (ENGINE_CONTRADICTED if contradicted else ENGINE_NOT_PROVEN)
    return out


def merge_engine_proof(per_case: list[dict]) -> dict:
    """One verdict over every case that actually retrieved. Any contradiction wins; anything unproven blocks."""
    proofs = [p for p in per_case if p]
    if not proofs:
        return {"status": ENGINE_NOT_PROVEN, "cases": 0, "reasons": ["no case reached retrieval"]}
    statuses = {p["status"] for p in proofs}
    status = (ENGINE_CONTRADICTED if ENGINE_CONTRADICTED in statuses
              else (ENGINE_NOT_PROVEN if ENGINE_NOT_PROVEN in statuses else ENGINE_PROVEN))
    return {"status": status, "cases": len(proofs),
            "reasons": sorted({r for p in proofs for r in (p.get("reasons") or [])}),
            "by_case": {p.get("case"): p["status"] for p in proofs if p.get("case")}}


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
            if j.get("job_id") and j["job_id"] not in graph:
                graph.append(j["job_id"])
        d = c.get("declaration") or {}
        if d.get("job_id") and d["job_id"] not in graph:
            graph.append(d["job_id"])
        for j in (c.get("payload") or {}).get("jobs") or []:          # catalog mode: payload row reads (BigQueryStore returns two)
            for jj in (j.values() if isinstance(j, dict) and "nodes_job" in j else [j]):
                if isinstance(jj, dict) and jj.get("job_id") and jj["job_id"] not in graph:
                    graph.append(jj["job_id"])
        for j in (((c.get("replay") or {}).get("retrieval") or {}).get("timing") or {}).get("jobs", []) or []:   # the cached-replay re-check job (restricted)
            if j.get("job_id") and j["job_id"] not in graph:
                graph.append(j["job_id"])
        rec = c.get("receipt") or {}
        job = (rec.get("receipt") or {}).get("job") if rec.get("invoked") else None
        if job and job.get("job_id"):
            receipt.append(job)
    return {"graph": graph, "receipt": receipt}


def same_requester(client: Any, graph_job_ids: list[str], receipt_jobs: list[dict], refs: Optional[dict] = None) -> dict:
    """jobs.get under the operator: every graph-leg job and every receipt-leg job must carry one KNOWN user_email.
    Nothing to compare, an unreadable job, or a missing identity is UNKNOWN (never SAME); more than one identity is
    DIFFERENT. `refs` maps a graph job id to the (project, location) it was submitted under (the journal's reference);
    ids without a reference are read under the module defaults, as the fixture chain always did."""
    receipt_ids = [j for j in receipt_jobs if j.get("job_id")]
    if not graph_job_ids or not receipt_ids:
        return {"status": "UNKNOWN", "reason": f"nothing to compare: graph_jobs={len(graph_job_ids)} receipt_jobs={len(receipt_ids)}"}
    emails: dict[str, Any] = {}
    refs = refs or {}
    try:
        for jid in graph_job_ids:
            proj, loc = refs.get(jid, (PROJECT, LOCATION))
            emails[jid] = client.get_job(jid, project=proj or PROJECT, location=loc or LOCATION).user_email
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
CHAIN_VERSION = "okf_bq_graph.chain/0.11.0"  # 0.11.0: each DDL attempt owned before dispatch; a lost submission stays unresolved
SEED_MODES = ("fixture", "catalog")


def _stage_error(e: BaseException) -> dict:
    return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:400]}"}


def _broken(out: dict, at: str, run_dir: str, out_dir: str, mode: str, redact: Callable, journal: Optional[Journal], tag: str = "") -> dict:
    out["verdict"] = "CHAIN_BROKEN"; out["broken_at"] = at; out["cases"] = []
    out.setdefault("same_requester", {"status": "NOT_RUN", "reason": f"refused at {at} before any case executed"})
    return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)


def run_chain(engine: str, live: bool, sdk_root: str, out_dir: str, clients: Optional[dict] = None, projection: Optional[dict] = None,
              requester: Any = None, as_of: Optional[str] = None, runner: Runner = subprocess.run, cases: Optional[tuple] = None,
              acme_root: Optional[str] = None, seed_mode: str = "fixture", catalog_reader: Any = None,
              catalog_cfg: Optional[CatalogConfig] = None, store: Any = None, requester_mode: str = "operator", broker: Any = None,
              window: Any = None, receipt_bridge: Any = None) -> dict:
    from .authz import operator, redact
    if requester_mode not in ("operator", "restricted"):
        raise ValueError(f"requester_mode must be operator|restricted, not {requester_mode!r}")
    restricted = requester_mode == "restricted"
    deferred_teardown = False
    suite = RESTRICTED_CASES if restricted else CASES
    cases = tuple(cases or suite)
    unknown = [c for c in cases if c not in suite]
    if unknown:
        raise ValueError(f"unknown case(s) for requester_mode={requester_mode}: {unknown}; the suite is {list(suite)}")
    if live and engine == "oracle":
        raise ValueError("live mode needs a BigQuery graph engine (fallback|gql): oracle + SDK --live is not a mode")
    if not live and engine != "oracle":
        raise ValueError("hermetic mode uses the oracle engine only")
    if seed_mode not in SEED_MODES:
        raise ValueError(f"seed_mode must be one of {SEED_MODES}")
    catalog = seed_mode == "catalog"
    if catalog and restricted:
        raise ValueError("catalog seed mode with the restricted requester is not a mode in Slice A (the broker runs the fixture seed)")
    if catalog and catalog_reader is None:
        raise ValueError("catalog seed mode needs a Catalog reader (HttpReader live; an injected reader hermetic)")
    acme_root = acme_root or os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail")
    as_of = as_of or _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    mode = "live" if live else "hermetic"
    tag = "_restricted" if restricted else ""
    # run_id must NOT start with "live_" — GitHub secret scanning treats that as a GoCardless
    # live access token (alerts #1–#5 on 2026-09-07). Keep out["mode"] as live|hermetic; only the
    # directory / journal id uses a scanner-safe slug.
    id_mode = "online" if live else "hermetic"
    run_id = f"{id_mode}{tag}-{_dt.datetime.now(_dt.timezone.utc):%Y%m%dT%H%M%SZ}-{secrets.token_hex(4)}"
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
                                           "stage with its specific evidence), no journaled job is left in an unverified (UNKNOWN) state and, live, every "
                                           "submitted job (pointer lookup, pin resolution, head observation, payload rows, retrieval, declaration, receipt) "
                                           "carries one known user_email; CHAIN_INCOMPLETE when a case never reached its stage (outage on any leg, "
                                           "including approved) or a job's server state was never reconciled; CHAIN_BROKEN when a reached "
                                           "stage contradicts the expectation, a payload is inconsistent with the pinned publication, or a pin/seed "
                                           "refuses (stale, invalid, unavailable, out of scope)"}
    if catalog:
        out["seed"] = {"mode": getattr(catalog_reader, "mode", "catalog-mock"), "status": "PENDING",
                       "note": "exact Concept id from the Catalog runtime aspect; no fixture, head, vector or saved-response fallback"}
    else:
        out["seed"] = {"mode": "fixture", "query": SEED, "note": "forced seed: harness-only deterministic override, not a semantic ranking; "
                                                                  "live Knowledge Catalog discovery is out of scope for this chain"}
    if restricted:
        out["requester"] = {"mode": "restricted-sa", "principal": SA_ALIAS,
                            "note": "graph leg and receipt leg both under the restricted service account through a requester broker; "
                                    "the operator's credential only grants, revokes and reads job identities",
                            "cases": {k: {"seed": v["seed"], "policy": dict(v["policy"], hidden=list(v["policy"]["hidden"])), "expects": v["expects"]}
                                      for k, v in RESTRICTED.items() if k in cases}}
        out["verdict_rule"] = ("CHAIN_CONNECTED only when provenance pins hold before any case executes, every case is MET (reached its "
                               "stage with its specific evidence: approved-restricted RELEASED; denied-intermediate seed visible, no path, "
                               "no hidden id, CLI never invoked; unauthorized-output bound, authorization DENIED under the requester's "
                               "credential, CLI never invoked; revocation-before-replay released once, then HIT_DENIED replay, authorization "
                               "DENIED and REFUSED with the CLI invoked once) and, live, every job the run submitted carries the identity "
                               "of the role that submitted it -- the graph leg (pointer lookup, retrieval, declaration, the cached-replay "
                               "re-check whether it succeeded or was denied) and the receipt leg execute as the SA, the broker's own platform "
                               "observations are submitted as the SA, and the row-policy grant/revoke/restore DDL is administrative work under "
                               "the operator (identity BOUND); CHAIN_INCOMPLETE when a case never reached its stage, the identity is UNKNOWN, "
                               "or a replay ran without contributing its job reference; CHAIN_BROKEN when a reached stage contradicts the expectation, "
                               "a job carries another identity or a pin fails; hermetic runs prove the harness, not the platform")
    omitted = [c for c in suite if c not in cases]
    out["selected_cases"] = list(cases)
    out["omitted_cases"] = omitted
    out["scope"] = {"complete_suite": not omitted, "suite": list(suite),
                    "note": "a scoped run proves the cases it selected. The omitted cases are NOT_RUN: an approved case "
                            "passing on its own is not the suite's negative coverage"}
    # ---- explicit engine admission (U1/R1): refuse BEFORE any grant, client query or SDK launch
    out["engine_admission"] = gql_admission(engine, live, window)
    if out["engine_admission"]["status"] not in ("OK", "NOT_REQUIRED"):
        journal.note("engine_admission_refused", status=out["engine_admission"]["status"], engine=engine)
        out["cases"] = []
        out["verdict"] = "CHAIN_INCOMPLETE"
        out["broken_at"] = "engine_admission"
        out["engine_proof"] = {"status": ENGINE_NOT_PROVEN, "reasons": ["the run was refused before retrieval"]}
        out["same_requester"] = {"status": "NOT_RUN",
                                 "reason": "refused at engine_admission before any client, grant or SDK launch"}
        return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)
    if window is not None:
        out["window"] = {"label": getattr(getattr(window, "cfg", None), "label", None),
                         "state": getattr(window, "state", None),
                         "controller": (getattr(window, "record", {}) or {}).get("controller")}
    # ---- KTD3: the receipt child runs inside this window, or the run says so
    receipt_runner = runner

    def _stamp_containment(rec: dict, launched_before: int) -> None:
        """No bridge, no containment claim: an unbridged run records nothing rather than asserting it was contained."""

    if receipt_bridge is not None:
        status = (receipt_bridge.record or {}).get("status")
        out["receipt_bridge"] = {"status": status, "label": getattr(receipt_bridge, "label", None),
                                 "clock_domain": (receipt_bridge.record or {}).get("clock_domain"),
                                 "preflight": ((receipt_bridge.record or {}).get("preflight") or {}).get("status"),
                                 "child": (receipt_bridge.record or {}).get("child"),
                                 "reason": (receipt_bridge.record or {}).get("reason")}
        if status != "SUPPORTED":
            journal.note("receipt_bridge_unsupported", status=status)
            out["cases"] = []
            out["verdict"] = "CHAIN_INCOMPLETE"
            out["broken_at"] = "receipt_bridge"
            out["engine_proof"] = {"status": ENGINE_NOT_PROVEN, "reasons": ["the run was refused before retrieval"]}
            out["same_requester"] = {"status": "NOT_RUN",
                                     "reason": "the SDK window bridge is unsupported at this pin: refused before any "
                                               "grant, query or SDK launch"}
            return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)
        receipt_runner = receipt_bridge.runner()

        def _stamp_containment(rec: dict, launched_before: int) -> None:
            """Record whether THIS invocation's child actually ran inside the bridge, before the consumer decides."""
            if not rec.get("invoked") or not hasattr(receipt_bridge, "containment"):
                return
            rec["containment"] = receipt_bridge.containment(since=launched_before)

        if window is not None:
            # stop reaches the child, close joins it BEFORE sealing, and its retained references are adopted
            window.register_worker("receipt_child", stop=receipt_bridge.stop, join=receipt_bridge.join,
                                   jobs=receipt_bridge.jobs, obligations=receipt_bridge.obligations,
                                   # where a recovery process finds this child's retained references
                                   evidence={"journal_dir": str(receipt_bridge.journal_dir),
                                             "bridge_dir": str(receipt_bridge.dir),
                                             "stop_file": str(receipt_bridge.stop_path),
                                             "label": receipt_bridge.label})
            out["receipt_bridge"]["worker"] = "registered with the window controller (stop, join, job union)"
        else:
            out["receipt_bridge"]["worker"] = None
    # ---- KTD4: the first live GQL case must execute; a memoized answer cannot establish that GQL ran
    if live and engine == "gql":
        out["cache_policy"] = {"memoization": "DISABLED", "exempt_cases": list(CACHE_EXEMPT_CASES),
                               "reason": "a cached or fallback-filled entry cannot establish GQL execution; the "
                                         "replay case keeps its cache because the cached replay IS its evidence"}
    # SDK pin
    try:
        sdk_pub = sdk_publication(sdk_root)
    except (OSError, ValueError, KeyError) as e:
        out["sdk"] = _stage_error(e)
        return _broken(out, "sdk", run_dir, out_dir, mode, redact, journal, tag)
    out["sdk"] = {"root": sdk_root, "head": sdk_pub["sdk_head"], "pin": SDK_PIN, "head_matches_pin": sdk_pub["sdk_head_matches_pin"],
                  "example_dirty": sdk_pub["sdk_dirty"], "repo_dirty": sdk_pub["sdk_repo_dirty"],
                  "publication_id": sdk_pub["manifest"]["publication_id"],
                  "computation_sha256": sdk_pub["computation_sha256"], "computation_digest": sdk_pub["computation_digest"],
                  "dependencies": sdk_pub["dependencies"],
                  "synthetic_fixture": bool(sdk_pub["manifest"].get("synthetic")), "invocation": "subprocess run.py (no SDK source edits)"}
    out["sdk_publication"] = {"publication_id": sdk_pub["manifest"]["publication_id"], "context_ref": sdk_pub["manifest"]["context_ref"],
                              "computation_sha256": sdk_pub["computation_sha256"], "derived_from": sdk_pub["manifest"].get("derived_from"),
                              "note": "the SDK receipt example's fixture publication: a separate identity from the graph publication, joined only by bytes"}
    # clients + requester
    if engine == "oracle" and projection is None and not catalog and (clients is None or restricted):
        from .compile import compile_bundle
        projection = compile_bundle(acme_root, BUNDLE_ID, SOURCE_PIN)
    def _bind(raw: Any, role: str, principal: Optional[str] = None) -> Any:
        """Every client the chain builds under an owned window is registered with its single submission gate."""
        return window.bind_client(raw, role=role, principal=principal) if window is not None else raw

    if restricted:
        if broker is None:
            if not live:
                broker = HermeticBroker(projection)
            else:
                from .authz import impersonated_client
                broker = RestrictedBroker(
                    engine, sdk_pub["dataset"], dependencies=sdk_pub["dependencies"],
                    factory=(lambda email: _bind(impersonated_client(email), "requester", email)),
                    owner=(window.operator if window is not None and window.operator is not None else None))
        out["requester"]["broker"] = broker.describe()
        # R3: register the restoration BEFORE the first mutation, so a crash between grant and close still leaves the
        # obligation behind, and so it runs on the bounded cleanup channel rather than the stopped workload channel.
        deferred_teardown = window is not None and hasattr(window, "register_restore")
        if deferred_teardown:
            window.register_restore("broker_teardown", lambda client: broker.teardown(owner=client), takes_client=True)
            out["requester"]["teardown"] = {"owner": "window controller", "channel": "bounded cleanup"}
            if hasattr(window, "register_post_close"):
                # the restoration's own DDL lands during close: the identity claim is rebuilt over it
                window.register_post_close(
                    "broker_identity",
                    lambda record: rebuild_identity(broker, record,
                                                    audit=window.audit_client() if hasattr(window, "audit_client") else None))
        unbound = unbound_clients(clients, broker, window)
        if unbound:
            out["engine_admission"] = {"status": "GQL_CLIENTS_UNBOUND", "engine": engine, "unbound": unbound,
                                       "reason": "a client would submit outside the window's admission gate: its jobs "
                                                 "would not be journaled, bounded or cleaned up"}
            out["cases"] = []; out["verdict"] = "CHAIN_INCOMPLETE"; out["broken_at"] = "engine_admission"
            out["engine_proof"] = {"status": ENGINE_NOT_PROVEN, "reasons": ["the run was refused before retrieval"]}
            out["same_requester"] = {"status": "NOT_RUN", "reason": "refused before any grant, query or SDK launch"}
            out["teardown"] = {"status": "NOT_RUN", "reason": "no grant was issued"}
            return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)
        requester = requester or SA_ALIAS
        try:
            out["grant"] = broker.grant()   # before the pointer lookup: that job runs under the requester too
        except Exception as e:  # noqa: BLE001 - a grant the platform refused blocks every case (nothing is invented)
            out["grant"] = _stage_error(e); out["verdict"] = "CHAIN_INCOMPLETE"; out["broken_at"] = "grant"; out["cases"] = []
            out["teardown"] = broker_teardown(broker, deferred_teardown)
            return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)
        clients = broker.graph_clients()
    elif clients is None:
        if engine == "oracle" and not catalog:
            from .oracle import Graph
            clients = {"engine": "oracle", "graph": Graph(projection), "projection": projection}
        elif engine == "oracle":
            clients = {"engine": "oracle"}      # graphs come from the retained store below
        else:
            from google.cloud import bigquery
            clients = {"engine": engine,
                       "bq": _bind(bigquery.Client(project=PROJECT, location=LOCATION), "requester")}
    unbound = unbound_clients(clients, broker, window)
    if unbound:
        out["engine_admission"] = {"status": "GQL_CLIENTS_UNBOUND", "engine": engine, "unbound": unbound,
                                   "reason": "a client would submit outside the window's admission gate: its jobs "
                                             "would not be journaled, bounded or cleaned up"}
        out["cases"] = []; out["verdict"] = "CHAIN_INCOMPLETE"; out["broken_at"] = "engine_admission"
        out["engine_proof"] = {"status": ENGINE_NOT_PROVEN, "reasons": ["the run was refused before retrieval"]}
        out["same_requester"] = {"status": "NOT_RUN", "reason": "refused before any query or SDK launch"}
        return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)
    if window is not None:
        out["window"]["bound_clients"] = list(window.clients)
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
        # one destination for the pin resolution, the payload rows, the retrieval and the declaration (Opus PR41 P2):
        # the configured runtime dataset; a client wired to a different dataset is refused, never silently split
        if live and clients.get("ds") not in (None, cfg.runtime_dataset):
            out["publication"] = {"status": "DESTINATION_MISMATCH", "publication_id": pin.publication_id, "configured": cfg.runtime_dataset,
                                  "client_dataset": clients.get("ds"), "error": "clients['ds'] differs from the configured runtime dataset"}
            return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
        if live:
            clients = dict(clients, ds=cfg.runtime_dataset, journal=journal)
        if store is None:
            if live:
                if clients.get("bq") is None:
                    out["publication"] = {"status": "ERROR", "error": "live mode needs a BigQuery client in clients['bq']"}
                    return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
                store = BigQueryStore(clients["bq"], cfg.runtime_project, cfg.runtime_dataset, cfg.runtime_location, journal)
            else:
                out["publication"] = {"status": "ERROR", "error": "hermetic catalog mode needs an injected retained store (ProjectionStore)"}
                return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
        elif getattr(store, "journal", None) is not journal:
            store.journal = journal                 # every store read is journaled under this run
        if live and getattr(store, "dataset", None) != cfg.runtime_dataset:   # checked BEFORE the first store read
            out["publication"] = {"status": "DESTINATION_MISMATCH", "publication_id": pin.publication_id, "configured": cfg.runtime_dataset,
                                  "store_dataset": getattr(store, "dataset", None), "error": "retained store dataset differs from the configured runtime dataset"}
            return _broken(out, "publication", run_dir, out_dir, mode, redact, journal)
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
        clients = dict(clients, store=store)          # declaration reads go through the journaled store on every engine
        if engine == "oracle":
            clients["graphs"] = getattr(store, "graphs", {})
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
            if restricted:
                out["teardown"] = broker_teardown(broker, deferred_teardown)
            return _broken(out, "publication", run_dir, out_dir, mode, redact, journal, tag)
        prov = {"publication_pin": out["publication"]["matches_pin"], "sdk_head_pin": bool(sdk_pub["sdk_head_matches_pin"]),
                "sdk_clean": sdk_pub["sdk_repo_dirty"] is False, "sdk_git_state_known": sdk_pub["sdk_repo_dirty"] is not None}
        out["graph_publication"] = {"bundle_id": BUNDLE_ID, "publication_id": pub, "source_pin": SOURCE_PIN,
                                    "note": "fixture mode: the compiled/pointer publication checked against the module pin constant"}
    # provenance gate (Astra P2 #2): no case executes on an unknown or mismatched pin
    prov["ok"] = prov["publication_pin"] and prov["sdk_head_pin"] and prov["sdk_clean"]
    out["provenance"] = prov
    if not prov["ok"]:
        out["same_requester"] = {"status": "NOT_RUN", "reason": "provenance gate refused before any case executed"}
        if restricted:
            out["teardown"] = broker_teardown(broker, deferred_teardown)
        return _broken(out, "provenance", run_dir, out_dir, mode, redact, journal, tag)

    def engine_clients(cl: dict, case: str) -> dict:
        """The clients one case retrieves with. Under a live GQL window every case but the cached-replay case runs
        with memoization off, so its walk/context jobs are real."""
        if not (live and engine == "gql") or case in CACHE_EXEMPT_CASES:
            return cl
        return dict(cl, cache=None)

    def graph_leg(seed: Any, path: str, cl: Optional[dict] = None, hidden: tuple = ()) -> tuple[dict, Optional[dict], Optional[dict], Optional[dict]]:
        cl = clients if cl is None else cl
        try:
            r = governed(seed, pub, requester, as_of, cl)
        except Exception as e:  # noqa: BLE001 - e.g. GQL without an Enterprise window
            return ({"retrieval": dict(_stage_error(e), seed=str(seed), reached=False),
                     "engine_proof": engine_proof(engine, cl, None) if live else None}, None, None, None)
        rec = {"retrieval": {"seed": str(seed), "seed_origin": getattr(seed, "origin", "forced"), "status": r["status"],
                             "warnings": r.get("warnings", []), "scope": r.get("scope"),
                             "concepts": [c.get("concept") for c in r.get("concepts", [])],
                             "paths": r.get("paths", []), "computations": [c.get("path") for c in r.get("computations", [])],
                             "timing": r.get("timing")}}
        rec["retrieval"]["hidden_id_in_full_result"] = [h for h in hidden if leaks(r, h)]   # the FULL answer the requester got, not this trimmed record
        if live:
            rec["engine_proof"] = engine_proof(engine, cl, r)
        comp = pick_computation(r, path) if r["status"] == "OK" else None
        if comp is None:
            rec["retrieval"]["reached"] = False
            return rec, None, None, r
        rec["retrieval"]["reached"] = True
        rec["computation"] = {k: comp.get(k) for k in ("concept", "computation_id", "section_id", "path", "concept_hops", "via", "status",
                                                        "runtime", "trust_tier", "freshness", "sql_sha256", "runtime_verdict")}
        rec["computation"]["sql_chars"] = len(comp.get("sql") or "")
        try:
            decl = declaration(cl, comp["computation_id"], pub)
        except Exception as e:  # noqa: BLE001
            decl = _stage_error(e)
        rec["declaration"] = decl
        return rec, comp, decl, r

    out["cases"] = []
    Path(receipt_dir).mkdir(parents=True, exist_ok=True)

    def operator_case(case: str) -> dict:
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
        leg, comp, decl, full_result = graph_leg(seed, path, engine_clients(clients, case))
        c.update(leg)
        if catalog and full_result is not None:      # the governed input itself is retained (redacted like the record), not only the re-read rows
            kept = journal.retain(f"retrieval_{case}", (json.dumps(redact(full_result), indent=1, sort_keys=True, default=str) + "\n").encode("utf-8"), subdir="retrieval")
            c["retrieval"]["retained"] = {"path": kept["path"], "sha256": kept["sha256"], "redacted": True}
        if catalog and full_result is not None and comp is not None and decl is not None and decl.get("status") == "OK":
            c["payload"] = verify_payload(store, pin, trusted, full_result, comp, decl, expected_path=path, seed_id=seed.concept_id, engine=engine)
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
            launched = len(getattr(receipt_bridge, "launches", ()) or ())
            c["receipt"] = run_receipt(sdk_case, sdk_root, receipt_dir, live, runner=receipt_runner)
            _stamp_containment(c["receipt"], launched)
            c["receipt"]["diag"] = None if c["receipt"].get("diag") is None else f"see {c['receipt']['diag_path']}"
        else:
            c["receipt"] = {"invoked": False, "reason": "bind did not hold: nothing was executed"}
        c["consume"] = consume(c["bind"], c["receipt"], containment=c["receipt"].get("containment"))
        c["acceptance"] = accept(c)
        return c

    def restricted_case(case: str) -> dict:
        """One restricted-requester case: the broker applies the case's policy, the graph leg runs under the requester's
        clients, a BOUND declaration is authorized under the requester's credential BEFORE the CLI is invoked, and the
        revocation case then revokes, replays from cache and re-decides the consumer on the stored receipt."""
        spec = RESTRICTED[case]
        c: dict[str, Any] = {"case": case, "expected": EXPECTED[case], "attack": spec["attack"], "expects": spec["expects"],
                             "policy": dict(spec["policy"], hidden=list(spec["policy"]["hidden"])), "hidden": list(spec["policy"]["hidden"]),
                             "receipt_invocations": 0}
        try:
            c["grant"] = broker.apply(spec["policy"])
        except Exception as e:  # noqa: BLE001 - the policy never took effect: the stage is unreached, not contradicted
            c["grant"] = _stage_error(e)
            c["retrieval"] = {"status": "NOT_RUN", "reached": False, "reason": "policy not applied"}
            c["bind"] = {"status": "NOT_REACHED", "reason": "policy_not_applied"}
            c["authorization"] = {"status": "NOT_RUN", "reason": "policy not applied"}
            c["receipt"] = {"invoked": False, "reason": "policy not applied: nothing was executed"}
            c["consume"] = consume(c["bind"], c["receipt"])
            c["acceptance"] = accept(c)
            return c
        cc = broker.graph_clients()
        leg, comp, decl, _full = graph_leg(spec["seed"], COMPUTATION_PATH, engine_clients(cc, case), hidden=spec["policy"]["hidden"])
        c.update(leg)
        r = c["retrieval"]
        if not r.get("reached"):
            c["bind"] = {"status": "NOT_REACHED",
                         "reason": "retrieval_denied" if r.get("status") in ("OK", "DENIED") else "retrieval_error",
                         "detail": ("governed retrieval returned no authorized path to the computation (seed visible, status OK)" if r.get("status") == "OK"
                                    else f"governed retrieval status {r.get('status')}")}
        elif decl is None or decl.get("status") != "OK":
            c["bind"] = {"status": "NOT_BOUND", "reason": "declaration not visible"}
        else:
            c["bind"] = bind(comp, decl, sdk_pub, as_of)
        if c["bind"]["status"] == "BOUND":
            c["authorization"] = broker.authorize(sdk_pub["dependencies"])
            if c["authorization"]["status"] == ALLOWED:
                launched = len(getattr(receipt_bridge, "launches", ()) or ())
                c["receipt"] = run_receipt("approved", sdk_root, receipt_dir, live, runner=receipt_runner,
                                           env_extra=broker.receipt_env(), label=case)
                _stamp_containment(c["receipt"], launched)
                c["receipt"]["diag"] = None if c["receipt"].get("diag") is None else f"see {c['receipt']['diag_path']}"
                c["receipt_invocations"] = 1
            else:
                c["receipt"] = {"invoked": False, "reason": f"authorization {c['authorization']['status']} under the requester's credential: nothing was executed"}
        else:
            c["authorization"] = {"status": "NOT_RUN", "reason": "nothing bound: no dependency to authorize"}
            c["receipt"] = {"invoked": False, "reason": f"bind {c['bind']['status']}: nothing was executed"}
        az = c["authorization"] if c["authorization"].get("status") in (ALLOWED, DENIED, "UNKNOWN") else None
        c["consume"] = consume(c["bind"], c["receipt"], az, containment=c["receipt"].get("containment"))
        if case == "revocation-before-replay":
            c["first_pass"] = {"decision": c["consume"]["decision"], "reasons": c["consume"]["reasons"],
                               "cache": (r.get("scope") or {}).get("cache"), "authorization": c["authorization"].get("status"),
                               "receipt_verdict": (c["receipt"].get("output") or {}).get("verdict") if c["receipt"].get("invoked") else None}
            try:
                c["revocation"] = broker.revoke()
            except Exception as e:  # noqa: BLE001
                c["revocation"] = dict(_stage_error(e), observed=False)
            rp: dict[str, Any] = {"note": "same request, same requester, same case-private cache; the stored receipt is re-decided, never re-executed"}
            try:
                r2 = governed(spec["seed"], pub, requester, as_of, cc)
                rp["retrieval"] = {"status": r2["status"], "cache": (r2.get("scope") or {}).get("cache"), "warnings": r2.get("warnings", []),
                                   "concepts": [x.get("concept") for x in r2.get("concepts", [])], "paths": r2.get("paths", []),
                                   "computations": [x.get("path") for x in r2.get("computations", [])],
                                   "disclosed_anything": bool(r2.get("concepts") or r2.get("paths") or r2.get("computations")),
                                   "timing": r2.get("timing")}   # the re-check job belongs to the identity set (job_ids_of)
            except Exception as e:  # noqa: BLE001
                rp["retrieval"] = dict(_stage_error(e), reached=False)
            rp["authorization"] = broker.authorize(sdk_pub["dependencies"])
            rp["consume"] = consume(c["bind"], c["receipt"], rp["authorization"])
            c["replay"] = rp
            c["consume"] = rp["consume"]   # the case's decision is the replay's: a release here is the failure the case exists to catch
        c["acceptance"] = accept(c)
        return c

    try:
        for case in cases:
            out["cases"].append(restricted_case(case) if restricted else operator_case(case))
    finally:
        if restricted:
            out["teardown"] = broker_teardown(broker, deferred_teardown)
            out["broker_journal"] = list(getattr(broker, "journal", []))
    if live:
        out["engine_proof"] = merge_engine_proof([dict(c["engine_proof"], case=c["case"])
                                                  for c in out["cases"] if c.get("engine_proof")])
    else:
        out["engine_proof"] = {"status": "NOT_APPLICABLE",
                               "reason": "hermetic mode runs the in-process oracle: no BigQuery engine executed"}
    out["decisions"] = {c["case"]: c["consume"]["decision"] for c in out["cases"]}
    out["acceptance"] = {c["case"]: c["acceptance"]["status"] for c in out["cases"]}
    ids = job_ids_of(out["cases"], pointer_job_id, journal.job_ids())
    replay_cases = sum(1 for c in out["cases"] if c.get("replay"))
    replay_ids = [j["job_id"] for c in out["cases"]
                  for j in (((c.get("replay") or {}).get("retrieval") or {}).get("timing") or {}).get("jobs", []) or []
                  if j.get("job_id")]
    # a replay whose first pass submitted jobs must submit its own: the re-check runs against the engine, and a DENIED
    # one is still a submitted job. Losing it is exactly how the inventory understated itself (Astra PR 45 #1).
    replay_missing = [c["case"] for c in out["cases"] if c.get("replay")
                      and (((c.get("retrieval") or {}).get("timing") or {}).get("jobs") or [])
                      and not ((((c["replay"] or {}).get("retrieval") or {}).get("timing") or {}).get("jobs") or [])]
    refs = {e["job_id"]: (e.get("project"), e.get("location")) for e in journal.jobs() if e.get("job_id")}
    out["job_inventory"] = {"graph": ids["graph"], "receipt": [j.get("job_id") for j in ids["receipt"]],
                            "receipt_refs": ids["receipt"],
                            "refs": {k: {"project": v[0], "location": v[1]} for k, v in refs.items()},
                            "journal": journal.summary(), "note": "every submitted job once, including empty/failed lookups; roles and (project, location, job_id) in journal.jsonl"}
    if receipt_bridge is not None:
        ingested = receipt_bridge.ingest()
        out["job_inventory"]["receipt_child"] = [j["job_id"] for j in ingested["jobs"]]
        out["job_inventory"]["receipt_child_unresolved"] = ingested["unresolved"]
        out["job_inventory"]["receipt_child_operations"] = {"operations": ingested["operations"],
                                                            "dry_runs": ingested["dry_runs"],
                                                            "refused": ingested.get("refused", 0),
                                                            "blocked": ingested["blocked"]}
        out["job_inventory"]["refs"].update({j["job_id"]: {"project": j.get("project"), "location": j.get("location"),
                                                           "stage": "receipt_child"} for j in ingested["jobs"]})
        # a diagnostic the SDK reported that the child journal never saw, or the reverse, is a gap in the inventory
        reported = {j.get("job_id") for j in ids["receipt"] if j.get("job_id")}
        journaled = {j["job_id"] for j in ingested["jobs"]}
        out["job_inventory"]["receipt_child_only"] = sorted(journaled - reported)
        out["job_inventory"]["receipt_reported_only"] = sorted(reported - journaled)
    statuses = [c["acceptance"]["status"] for c in out["cases"]]
    unresolved = journal.unresolved()
    if receipt_bridge is not None:
        # a submission the child could not resolve is a job the window may owe cleanup for; so is a job the SDK
        # diagnostic named that the child journal never saw, and the reverse (Astra PR47 #6)
        unresolved = unresolved + [dict(u, role="receipt_child", state=u.get("state", "UNRESOLVED"))
                                   for u in out["job_inventory"]["receipt_child_unresolved"]]
        for job_id in out["job_inventory"]["receipt_reported_only"]:
            unresolved.append({"role": "receipt_child", "job_id": job_id, "state": "DIAGNOSTIC_ONLY",
                               "error": "the SDK diagnostic names a job the child's own journal never recorded"})
        for job_id in out["job_inventory"]["receipt_child_only"]:
            unresolved.append({"role": "receipt_child", "job_id": job_id, "state": "JOURNAL_ONLY",
                               "error": "the child journaled a submission the SDK diagnostic never reported"})
    # every unresolved entry, whatever produced it: journal entries carry seq/role, while a receipt-child mismatch or a
    # damaged child journal carries neither. Reading them positionally crashed the whole record assembly, so the run
    # wrote no evidence at all (Astra PR47 re-review R5).
    out["job_inventory"]["unresolved"] = [{"seq": e.get("seq"), "role": e.get("role", "chain"),
                                           "job_id": e.get("job_id"), "state": e.get("state", "UNKNOWN"),
                                           "error": e.get("error")} for e in unresolved]
    if restricted:
        probe_jobs = list(getattr(broker, "probe_jobs", []) or [])       # requester-submitted platform observations
        admin_jobs = list(getattr(broker, "admin_jobs", []) or [])       # operator-submitted row-policy DDL
        out["job_inventory"]["requester_probe"] = [j["job_id"] for j in probe_jobs]
        out["job_inventory"]["policy_admin"] = [j["job_id"] for j in admin_jobs]
        admin_ops = list(getattr(broker, "admin_ops", []) or [])
        out["job_inventory"]["policy_admin_ops"] = admin_ops
        # administrative work the broker cannot fully account for, as the BROKER judges it: an attempt that never named
        # a job, one that is not terminal, or a job that appeared without the submission hook seeing it. Recomputing
        # the rule here dropped the last kind, so the missed-hook guard never reached the audit (re-review 3 #3).
        out["job_inventory"]["policy_admin_unresolved"] = (broker.admin_unresolved() if hasattr(broker, "admin_unresolved")
                                                           else [op for op in admin_ops if not op.get("job_id")])
        out["job_inventory"]["refs"].update({j["job_id"]: {"project": j.get("project"), "location": j.get("location"), "stage": j.get("stage")}
                                             for j in probe_jobs + admin_jobs})
        out["identity"] = broker.identity(ids["graph"], ids["receipt"])
        out["identity"]["job_set"] = {"graph": len(ids["graph"]), "receipt": len(ids["receipt"]),
                                      "requester_probe": len(probe_jobs), "policy_admin": len(admin_jobs),
                                      "total": len(ids["graph"]) + len(ids["receipt"]) + len(probe_jobs) + len(admin_jobs),
                                      "pointer_lookup_included": pointer_job_id is not None,
                                      "replay_jobs": len(replay_ids), "replay_cases": replay_cases,
                                      "replay_jobs_missing": replay_missing,
                                      "note": "every job the run submitted, in the role that submitted it: the graph and receipt legs execute as the "
                                              "requester, the broker's platform observations are also submitted as the requester, and the "
                                              "grant/revoke/restore row-policy DDL is administrative work under the operator"}
        if replay_missing:
            out["identity"]["job_set"]["replay_note"] = (f"the replay of {replay_missing} contributed no job reference although its first pass did: "
                                                         "a job the run submitted is missing from the inventory")
        if out["identity"]["status"] == "NOT_APPLICABLE":
            out["identity"]["job_set"]["note"] = ("counts are the SDK emulation's synthetic receipt ids (okf_rcpt_…); no BigQuery job exists in "
                                                  "hermetic mode, so there is no identity to read")
        out["receipt_launches"] = {"chain_counted": sum(c.get("receipt_invocations", 0) for c in out["cases"]),
                                   "broker_counted": getattr(broker, "receipt_launches", None)}
        out["same_requester"] = {"status": "NOT_APPLICABLE", "reason": "restricted-sa mode: the identity claim is `identity` (every job bound to the SA)"}
        ident_broken = live and out["identity"]["status"] == "UNBOUND"
        ident_incomplete = live and (out["identity"]["status"] != "BOUND" or bool(replay_missing))
        fallback_at = "identity"
    else:
        if live:
            out["same_requester"] = same_requester(clients.get("bq"), ids["graph"], ids["receipt"], refs=refs) if clients.get("bq") is not None \
                else {"status": "UNKNOWN", "reason": "no BigQuery client"}
        else:
            out["same_requester"] = {"status": "NOT_APPLICABLE", "reason": "hermetic mode: oracle graph + SDK SYNTHETIC emulation submit no BigQuery jobs"}
        ident_broken = live and out["same_requester"]["status"] == "DIFFERENT"
        ident_incomplete = live and out["same_requester"]["status"] != "SAME"
        fallback_at = "same_requester"
    engine_broken = live and engine == "gql" and out["engine_proof"]["status"] == ENGINE_CONTRADICTED
    engine_incomplete = live and engine == "gql" and out["engine_proof"]["status"] != ENGINE_PROVEN
    if any(s == "WRONG" for s in statuses) or ident_broken or engine_broken:
        out["verdict"] = "CHAIN_BROKEN"
    elif any(s == "NOT_REACHED" for s in statuses) or ident_incomplete or unresolved or engine_incomplete:
        out["verdict"] = "CHAIN_INCOMPLETE"      # a job whose server state was never verified leaves the inventory unproven
    else:
        out["verdict"] = "CHAIN_CONNECTED"
    if out["verdict"] != "CHAIN_CONNECTED":
        out["broken_at"] = next((c["case"] for c in out["cases"] if c["acceptance"]["status"] == "WRONG"),
                                next((c["case"] for c in out["cases"] if c["acceptance"]["status"] == "NOT_REACHED"),
                                     "unresolved_jobs" if unresolved else
                                     ("engine_proof" if (engine_broken or engine_incomplete) else fallback_at)))
    return _finish(out, out_dir, mode, redact, run_dir=run_dir, journal=journal, tag=tag)


def _finish(out: dict, out_dir: str, mode: str, redact: Callable, run_dir: Optional[str] = None, journal: Optional[Journal] = None, tag: str = "") -> dict:
    """Publish the record: atomically to `chain_<mode>[_restricted].json` (last writer wins, but it references only its
    own run directory) and as a retained copy inside the run directory. Early refusals get the same retained final record."""
    out["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    if journal is not None:
        out["journal"] = journal.record()
        out["evidence"] = {"run_dir": run_dir, "journal": str(journal.path), "unresolved_jobs": journal.summary()["unresolved"],
                           "retained": [{"name": r["name"], "sha256": r["sha256"]} for r in journal.retained]}
    out = redact(out)
    Path(out_dir).mkdir(parents=True, exist_ok=True)
    text = json.dumps(out, indent=1, sort_keys=True, default=str) + "\n"
    final = Path(out_dir) / f"chain_{mode}{tag}.json"
    tmp = final.with_name(f".{final.name}.{out.get('run_id', 'norun')}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, final)
    own = Path(run_dir) if run_dir else (Path(out_dir) / "receipt" / out["run_id"] if out.get("run_id") else None)
    if own is not None and own.is_dir():
        (own / final.name).write_text(text, encoding="utf-8")
    return out


def _graph_probe(client: Any) -> Optional[str]:
    """One real GRAPH_TABLE count under the window's operator client: the assignment is proven, not assumed."""
    from google.cloud import bigquery
    job = client.query(f"SELECT COUNT(*) FROM GRAPH_TABLE(`{PROJECT}.{DATASET}.okf_graph` MATCH (n:Node) COLUMNS (n.node_id))",
                       job_config=bigquery.QueryJobConfig(use_query_cache=False), location=LOCATION)
    list(job.result())
    return job.job_id


def open_gql_window(label: str, minutes: int, manifest: str, evidence_dir: str, max_slots: int = 100,
                    probe_attempts: int = 12, probe_seconds: float = 120.0) -> Any:
    """Build and open the owned Enterprise window the GQL chain admits against.

    Every gate lives in the controller: the exclusive lease, the prior-cleanup receipts read from `evidence_dir`, the
    cumulative budget, the independent closer and the assignment probes. This function adds no waiver of its own.

    `probe_attempts`/`probe_seconds` size only how long readiness may be WAITED for; the number of consecutive
    successes that count as ready is not theirs to change, and the window's own `minutes` deadline stays the outer
    bound. A raised budget is an authorization question - the measured cost is more probe jobs inside an
    already-bounded paid window, not a weaker readiness test."""
    import subprocess as _sp
    from .chain_window import ChainWindow, WindowConfig
    from .reservation import close_window, open_window

    cfg = WindowConfig(label=label, minutes=minutes, manifest=manifest, evidence_dir=evidence_dir, max_slots=max_slots,
                       probe_attempts=probe_attempts, probe_seconds=probe_seconds)

    def watcher(window_label: str):
        script = Path(__file__).resolve().parents[1] / "bin" / "safety_teardown.sh"
        log = Path(evidence_dir) / "safety_teardown.log"
        with log.open("a") as fh:
            # The detached closer is handed this window's OWN evidence directory: it journals there, so a watcher
            # resolving `evidence/jobs_<label>.json` instead would find nothing to cancel and still delete capacity.
            _sp.Popen(["/bin/bash", str(script), str(os.getpid()), window_label, sys.executable, str(evidence_dir)],
                      stdout=fh, stderr=_sp.STDOUT, start_new_session=True)
        return str(script)

    def factory():
        from google.cloud import bigquery
        return bigquery.Client(project=PROJECT, location=LOCATION)

    window = ChainWindow(cfg, opener=open_window, closer=close_window, spawn_watcher=watcher,
                         probe=_graph_probe, client_factory=factory)
    window.preflight()
    window.open()
    return window


def finalize_cleanup(out: dict, window: Any, out_dir: str, receipt_bridge: Any = None) -> dict:
    """Amend the chain record with the window's ACTUAL closeout, after the controller closed.

    `run_chain` returns before the window closes, so its verdict cannot yet account for cleanup. A chain that reached
    its stages inside a window whose capacity, jobs, restores or workers are unresolved is not a completed run: the
    final retained record says so rather than leaving a `CHAIN_CONNECTED` that a later reader would over-read
    (Astra PR47 #1)."""
    from .authz import redact
    cleanup = (window.record or {}).get("cleanup") or {}
    clean = bool((window.record or {}).get("clean"))
    out.setdefault("window", {})
    out["window"].update({"label": getattr(getattr(window, "cfg", None), "label", None),
                          "state": getattr(window, "state", None), "clean": clean, "cleanup": cleanup,
                          "restores": (window.record or {}).get("restores"),
                          "workers": (window.record or {}).get("workers")})
    # the broker's restoration ran at close, on the bounded cleanup channel: its ACTUAL result belongs in the record
    for restore in ((window.record or {}).get("restores") or []):
        if restore.get("name") == "broker_teardown":
            out["teardown"] = restore.get("result") if restore.get("ok") else dict(
                restore.get("result") or {}, status=(restore.get("result") or {}).get("status", "FAILED"),
                restore_error=restore.get("error"))
    # rebuild any evidence that CLOSING itself changed (the deferred restoration's own administrative DDL)
    for hook in (window.post_close_callbacks() if hasattr(window, "post_close_callbacks") else []):
        try:
            out.setdefault("post_close", {})[hook["name"]] = hook["call"](out)
        except Exception as e:  # noqa: BLE001 - evidence we could not rebuild is not evidence that held
            out.setdefault("post_close", {})[hook["name"]] = {"status": "ERROR",
                                                              "error": f"{type(e).__name__}: {str(e)[:250]}"}
            clean = False
            out["window"]["clean"] = False
    if receipt_bridge is not None:
        # re-ingest AFTER the child was joined: a submission it made late is still this window's obligation
        ingested = receipt_bridge.ingest()
        inventory = out.setdefault("job_inventory", {})
        inventory["receipt_child"] = [j["job_id"] for j in ingested["jobs"]]
        inventory["receipt_child_unresolved"] = ingested["unresolved"]
        inventory["receipt_child_sealed_after_join"] = True
        out["receipt_bridge_journal"] = ingested
        if ingested["unresolved"]:
            clean = False
            out["window"]["clean"] = False
            cleanup = dict(cleanup, receipt_child_unresolved=len(ingested["unresolved"]))
            out["window"]["cleanup"] = cleanup
    # the rebuilt identity governs the final verdict exactly as the pre-close one did
    identity = out.get("identity") or {}
    if out.get("mode") == "live" and "rebuilt_after_restoration" in identity:
        unresolved_admin = (out.get("job_inventory") or {}).get("policy_admin_unresolved") or []
        if identity.get("status") == "UNBOUND":
            out["verdict"] = "CHAIN_BROKEN"
            out["broken_at"] = "identity"
            out["identity_note"] = ("a job the run submitted carries an unexpected identity once the restoration's own "
                                    "administrative DDL is included")
        elif identity.get("status") != "BOUND" or unresolved_admin:
            if out.get("verdict") != "CHAIN_BROKEN":
                out["verdict"] = "CHAIN_INCOMPLETE"
                out["broken_at"] = "identity"
                out["identity_note"] = ("the identity of the post-restoration administrative work is not established: "
                                        f"status {identity.get('status')}, {len(unresolved_admin)} unresolved "
                                        "statement(s)")
    if not clean and out.get("verdict") != "CHAIN_BROKEN":
        out["verdict"] = "CHAIN_INCOMPLETE"
        out["broken_at"] = "window_cleanup"
        out["cleanup_note"] = ("the chain ran inside a window whose closeout is not complete: capacity, job cleanup, "
                               "resource restoration or a worker join is outstanding, so this run is not a clean "
                               "closeout whatever its case outcomes were")
    text = json.dumps(redact(out), indent=1, sort_keys=True, default=str) + "\n"
    final = Path(out_dir) / f"chain_{out['mode']}{'_restricted' if out.get('requester', {}).get('mode') == 'restricted-sa' else ''}.json"
    tmp = final.with_name(f".{final.name}.{out.get('run_id', 'norun')}.final.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, final)
    run_dir = Path(out.get("run_dir") or "")
    if run_dir.is_dir():
        (run_dir / final.name).write_text(text, encoding="utf-8")
    return out


def _mock_reader_from_file(path: str) -> Any:
    from .catalog import MockReader
    body = json.loads(Path(path).read_text(encoding="utf-8"))
    return MockReader(body["pages"], body["entries"])


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="connected graph -> receipt chain (fixture or Catalog seed; operator or restricted requester)")
    ap.add_argument("--requester", choices=("operator", "restricted"), default="operator",
                    help="operator (default): both legs under the operator's ADC; restricted: both legs under sa:okf-receipt-restricted "
                         "through the requester broker (hermetic: policy emulation; live: IAM impersonation), four restricted cases")
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
    ap.add_argument("--cases", default=None,
                    help="comma-separated subset of the requester's case suite (default: the whole suite). The record "
                         "carries selected_cases and omitted_cases; omitted cases are NOT_RUN, never implied to pass")
    ap.add_argument("--gql-window", default=None, metavar="LABEL",
                    help="open and own an Enterprise window under this ORIGINAL label for --live --engine gql. Without "
                         "it a GQL request is refused with a typed record before any grant, query or SDK launch")
    ap.add_argument("--gql-window-minutes", type=int, default=10)
    ap.add_argument("--gql-manifest", default="evidence/cleanup_manifest.json",
                    help="the canonical capacity ledger; it must exist (an absent manifest is refused, never treated as empty)")
    ap.add_argument("--gql-evidence-dir", default="evidence",
                    help="where jobs_<label>.json cleanup receipts are read and written")
    ap.add_argument("--gql-max-slots", type=int, default=100)
    ap.add_argument("--gql-probe-attempts", type=int, default=12,
                    help="how many assignment probes may be spent waiting for readiness (default 12). This sizes the "
                         "WAIT only: six consecutive successes are still required, and the window's own deadline is "
                         "still the outer bound. Raising it is an authorization question, not a runner's default")
    ap.add_argument("--gql-probe-seconds", type=float, default=120.0,
                    help="how long assignment probing may run before it is abandoned (default 120s)")
    a = ap.parse_args(argv)
    if a.live and a.hermetic:
        ap.error("--live and --hermetic are exclusive")
    live = bool(a.live)
    if live and a.engine == "oracle":
        ap.error("--live needs --engine fallback|gql: the oracle engine submits no jobs, so a live identity claim cannot be made")
    if not live and a.engine not in (None, "oracle"):
        ap.error("--engine other than oracle requires --live")
    engine = (a.engine or "fallback") if live else "oracle"
    if a.gql_window and not (live and (a.engine == "gql")):
        ap.error("--gql-window is only meaningful with --live --engine gql")
    if a.requester == "restricted" and a.seed_mode == "catalog":
        ap.error("--requester restricted with --seed-mode catalog is not a mode in Slice A: the restricted broker runs the fixture seed")
    out_dir = a.out or ("evidence/catalog-chain" if a.seed_mode == "catalog" else "evidence/chain")
    reader, cfg, store = None, None, None
    if a.seed_mode == "catalog":
        kw = {k: v for k, v in (("group", a.catalog_group), ("entry", a.catalog_entry)) if v}
        if len(kw) == 1:
            ap.error("--catalog-group and --catalog-entry must be given together (the entry must belong to the group)")
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
    selected = tuple(c.strip() for c in a.cases.split(",") if c.strip()) if a.cases else None
    window, bridge = None, None
    if a.gql_window:
        # KTD3: the SDK bridge handshake runs BEFORE any paid capacity. An unsupported pin is an honest refusal, not a
        # window that opens and then discovers it cannot bound its own receipt child.
        from .receipt_window import SUPPORTED, ReceiptBridge
        bridge = ReceiptBridge(a.sdk_root, label=a.gql_window,
                               deadline_epoch=time.time() + a.gql_window_minutes * 60,
                               directory=Path(out_dir) / "receipt-bridge" / a.gql_window)
        # probe the cwd the receipt child will actually run in: `run_receipt` launches with cwd=<sdk_root>
        record = bridge.handshake(cwd=a.sdk_root)
        Path(out_dir).mkdir(parents=True, exist_ok=True)
        (Path(out_dir) / f"receipt_bridge_{a.gql_window}.json").write_text(
            json.dumps(record, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
        if record["status"] != SUPPORTED:
            print(f"SDK_WINDOW_BRIDGE_UNSUPPORTED: {record.get('reason')}")
            print("no window was opened; the live GQL chain stays blocked until the bridge is supported at an explicit pin")
            return 1
        try:
            window = open_gql_window(a.gql_window, a.gql_window_minutes, a.gql_manifest, a.gql_evidence_dir,
                                     a.gql_max_slots, a.gql_probe_attempts, a.gql_probe_seconds)
            # the child's budget is the window's ACTUAL remaining time, in absolute wall-clock seconds
            bridge.deadline_epoch = time.time() + max(0.0, window.deadline - time.monotonic())
        except Exception as e:  # noqa: BLE001 - a refused window is reported, and the chain still records its refusal
            print(f"gql window refused: {type(e).__name__}: {e}")
            record = getattr(e, "record", None)
            if record is not None:
                Path(out_dir).mkdir(parents=True, exist_ok=True)
                (Path(out_dir) / f"window_{a.gql_window}.json").write_text(
                    json.dumps(record, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
            return 1
    out = None
    try:
        out = run_chain(engine=engine, live=live, sdk_root=a.sdk_root, out_dir=out_dir, as_of=a.as_of, acme_root=a.acme_root,
                        seed_mode=a.seed_mode, catalog_reader=reader, catalog_cfg=cfg, store=store,
                        requester_mode=a.requester, cases=selected, window=window, receipt_bridge=bridge if window else None)
    finally:
        if window is not None:
            window.close()          # stops the child, joins it, then seals the union
            Path(out_dir).mkdir(parents=True, exist_ok=True)
            (Path(out_dir) / f"window_{a.gql_window}.json").write_text(
                json.dumps(window.record, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
            if out is not None:
                out = finalize_cleanup(out, window, out_dir, receipt_bridge=bridge)
            print("window cleanup:", json.dumps(window.record.get("cleanup"), default=str))
    for c in out.get("cases", []):
        rec = c.get("receipt") or {}
        rv = (rec.get("output") or {}).get("verdict", "NOT_INVOKED") if rec.get("invoked") else "NOT_INVOKED"
        acc = c.get("acceptance", {})
        pl = f" payload={c['payload']['status']:12s}" if c.get("payload") else ""
        print(f"{c['case']:22s}{pl} bind={c.get('bind', {}).get('status'):9s} receipt={rv:13s} consume={c['consume']['decision']:8s} "
              f"acceptance={acc.get('status')}" + (f" failed={'; '.join(acc.get('failed', []))[:200]}" if acc.get("failed") else ""))
    ident = f"identity={out['identity']['status']}" if "identity" in out else f"same_requester={out.get('same_requester', {}).get('status')}"
    print(f"seed_mode={out['seed'].get('mode')} seed_status={out['seed'].get('status', 'fixture')} publication={out.get('publication', {}).get('status')} "
          f"provenance_ok={out.get('provenance', {}).get('ok')} {ident} requester={out.get('requester', {}).get('mode')} "
          f"engine={out['engine']} mode={out['mode']} sdk_head={str(out.get('sdk', {}).get('head'))[:7]} run_dir={out.get('run_dir')}")
    print(f"engine_admission={out.get('engine_admission', {}).get('status')} engine_proof={out.get('engine_proof', {}).get('status')} "
          f"selected_cases={','.join(out.get('selected_cases', []))}"
          + (f" omitted_cases={','.join(out['omitted_cases'])}" if out.get("omitted_cases") else ""))
    print(f"verdict={out['verdict']}" + (f" broken_at={out.get('broken_at')}" if out['verdict'] != 'CHAIN_CONNECTED' else ""))
    if window is not None and not window.record.get("clean"):
        print("window cleanup is NOT complete: the run cannot be reported as a clean closeout")
        return 1
    return 0 if out["verdict"] == "CHAIN_CONNECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
