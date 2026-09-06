"""Task 5 governance fixtures (spec §5) + distinct-principal negatives (2026-09-06 second slice).

Fixtures measurable under the operator identity with real BigQuery policy objects (setup/revoke/restore, unchanged
in shape from the 2026-09-05 run):
  * `_rls`: copies the Acme publication; ROW ACCESS POLICY hides the intermediate concept metrics/gross-margin
    (and its sections and touching edges) so the legacy->current->computation path must vanish.
  * `_meta`: hides every Section row (no text) but keeps Concept rows.
  * `_av`: authorized views over the base dataset; graph over views.

Second principal (this slice). The 2026-09-05 run recorded every case that needs a second real principal as
BLOCKED because *creating* an IAM principal was denied. No principal is created here: the receipt spike's existing
restricted service account (alias `sa:okf-receipt-restricted`, env OKF_SPIKE_RESTRICTED_SA) is used through IAM
impersonation, the same pattern as the receipt spike's broker.open_impersonated_session (copied, not imported, so
this spike stays self-contained). Grants are dataset-level READER entries and row-policy grantees on the temporary
fixture datasets only, removed again in `finally`. Each case ends MEASURED / FAILED / BLOCKED-with-reason /
NOT_APPLICABLE-with-reason; a skipped run is never acceptance evidence. Judges run on the original payloads; the
published evidence JSON then carries the SA alias only (`redact`) and masks every identifier of the pinned publication
(`sanitize_ids`), so neither a passing nor a failing run can republish a denied identifier.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import inspect
import json
import os as _os
import re
import subprocess as _sp
import time
from typing import Any, Callable, Optional

from google.cloud import bigquery

from . import PROJECT, LOCATION, DATASET, BUNDLE_ID

RLS_DS = f"{DATASET}_rls"
META_DS = f"{DATASET}_meta"
AV_DS = f"{DATASET}_av"


_OPERATOR: Optional[str] = None


def operator(refresh: bool = False) -> str:
    """`user:<email>` of the operator: OKF_OPERATOR_EMAIL, else the active gcloud account. Resolved lazily (never at
    import: hermetic tests and offline imports must not touch gcloud) and tolerant of a missing/silent gcloud, in
    which case the result is `user:` and any live grant that needs it raises a clear error."""
    global _OPERATOR
    if _OPERATOR is None or refresh:
        e = _os.environ.get("OKF_OPERATOR_EMAIL")
        if not e:
            try:
                e = _sp.run(["gcloud", "config", "get-value", "account"], capture_output=True, text=True).stdout.strip()
            except (FileNotFoundError, OSError):
                e = ""
        _OPERATOR = f"user:{e}"
    return _OPERATOR


def _operator_member() -> str:
    op = operator()
    if op == "user:":
        raise RuntimeError("operator identity unknown: set OKF_OPERATOR_EMAIL or log in to gcloud")
    return op


HIDDEN = "metrics/gross-margin"
SA_ALIAS = "sa:okf-receipt-restricted"
SA_DEFAULT = f"okf-receipt-restricted@{PROJECT}.iam.gserviceaccount.com"
CASES = {
    "hidden_intermediate": "hidden intermediate under the second principal (RLS + walk): path removed, no hidden id in context or explain",
    "denied_bundle": "same path in a denied bundle under the second identity: zero rows, no id in the error text",
    "output_denied_seed_visible": "output denied despite seed access: vectors visible, nodes/edges denied, no denied id named",
    "owner_fallback_negative": "owner-credential fallback negative: every SA job is bound to the SA (jobs.get user_email), results differ at the hidden set",
    "revocation_before_cached_replay": "grant, run, cache, revoke dataset reader, replay from cache under the SA: replay refused",
}
LABELS = ("MEASURED", "FAILED", "BLOCKED", "NOT_APPLICABLE")
FIXTURE_IDS = (HIDDEN, "metrics/gross-margin-legacy", "metrics/revenue", "computations/revenue-ytd", "computations/gross-margin-period")
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


# ----------------------------------------------------------------------------- identity / redaction
def restricted_sa() -> str:
    return _os.environ.get("OKF_SPIKE_RESTRICTED_SA") or SA_DEFAULT


def redact(obj: Any, sa_email: Optional[str] = None) -> Any:
    """Evidence hygiene: the SA e-mail becomes its alias, the operator e-mail becomes `user:operator`, any other
    e-mail becomes `<email>`. Works on any JSON-serialisable object; returns the same shape."""
    text = json.dumps(obj, default=str)
    for secret, alias in ((sa_email or restricted_sa(), SA_ALIAS), (operator().split(":", 1)[-1], "operator")):
        if secret:
            text = text.replace(secret, alias)
    text = _EMAIL_RE.sub("<email>", text)
    return json.loads(text)


def leaks(obj: Any, needle: str) -> bool:
    """Exact identifier check: matches the concept id and its sections (`#sN`) but not `metrics/gross-margin-legacy`
    (an earlier plain-substring check false-positived on it)."""
    return bool(re.search(re.escape(needle) + r"(?![-\w])", json.dumps(obj, default=str)))


def leaked_ids(obj: Any, ids: list[str]) -> list[str]:
    return sorted(i for i in set(ids) if leaks(obj, i))


def id_token(local_id: str) -> str:
    return "<id:" + hashlib.sha256(local_id.encode()).hexdigest()[:8] + ">"


def sanitize_ids(obj: Any, ids: list[str]) -> Any:
    """Mask every publication identifier (exact match, longest first, so `x-legacy` is masked before `x`) in any
    JSON-serialisable object: bare local ids, scoped node/edge ids, section ids (`#sN`) and paths (`.md`) all
    become `<id:sha256[:8]>`. Judges run on the original payloads; only published surfaces are masked."""
    text = json.dumps(obj, default=str)
    for i in sorted(set(ids), key=len, reverse=True):
        if i:
            text = re.sub(re.escape(i) + r"(?![-\w])", id_token(i), text)
    return json.loads(text)


# ----------------------------------------------------------------------------- impersonation (receipt pattern, by copy)
def impersonated_client(target_principal: str, lifetime: int = 600) -> bigquery.Client:
    """BigQuery client for a real restricted principal via IAM impersonation. The identity is the target principal
    that IAM honours, never a label; the client's jobs carry that identity in jobs.get user_email."""
    import google.auth
    import google.auth.transport.requests
    from google.auth import impersonated_credentials
    scopes = ["https://www.googleapis.com/auth/cloud-platform"]
    source, _ = google.auth.default(scopes=scopes)
    creds = impersonated_credentials.Credentials(source_credentials=source, target_principal=target_principal,
                                                 target_scopes=scopes, lifetime=lifetime)
    creds.refresh(google.auth.transport.requests.Request())
    return bigquery.Client(project=PROJECT, location=LOCATION, credentials=creds)


def preflight(target_principal: str, factory: Callable[[str], Any] = impersonated_client) -> tuple[dict, Any]:
    """Impersonate and run one trivial job. Returns ({"status": "OK", ...}, client) or ({"status": "BLOCKED", "error": ...}, None) with the exact
    (redacted) API error; the caller records the blocker instead of inventing IAM."""
    out: dict = {"principal": SA_ALIAS, "at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    try:
        client = factory(target_principal)
        job = client.query("SELECT 1 AS ok", job_config=bigquery.QueryJobConfig(use_query_cache=False,
                                                                                labels={"okf_spike": "bq_graph_20260905", "stage": "sa_preflight"}), location=LOCATION)
        list(job.result())
        out.update(status="OK", job=job.job_id)
        return out, client
    except Exception as e:  # noqa: BLE001 - the blocker itself is the evidence
        out.update(status="BLOCKED", error=redact(f"{type(e).__name__}: {str(e)[:400]}", target_principal))
        return out, None


# ----------------------------------------------------------------------------- grants (temporary fixture datasets only)
def set_dataset_reader(client: bigquery.Client, ds: str, principal: str, grant: bool) -> str:
    """Dataset-level READER entry for one principal on a fixture dataset (receipt pattern `_set_dataset_reader`)."""
    d = client.get_dataset(f"{PROJECT}.{ds}")
    entries = [e for e in d.access_entries
               if not (e.entity_type in ("userByEmail", "iamMember") and (e.entity_id or "").replace("serviceAccount:", "") == principal)]
    if grant:
        entries.append(bigquery.AccessEntry("READER", "userByEmail", principal))
    d.access_entries = entries
    client.update_dataset(d, ["access_entries"])
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def rls_statements(grantees: list[str], vector_grantees: Optional[list[str]] = None, hide: bool = True) -> dict[str, str]:
    """The three `_rls` policies with an explicit grantee list. hide=True keeps the hidden-intermediate filter;
    hide=False is the all-rows revocation (FILTER USING (FALSE))."""
    rls = f"{PROJECT}.{RLS_DS}"
    g = ", ".join(f"'{x}'" for x in grantees)
    vg = ", ".join(f"'{x}'" for x in (vector_grantees if vector_grantees is not None else grantees))
    if not hide:
        f_nodes = f_edges = f_vec = "FALSE"
    else:
        f_nodes = f"local_id <> '{HIDDEN}' AND NOT STARTS_WITH(local_id, '{HIDDEN}#')"
        f_edges = (f"NOT REGEXP_CONTAINS(src_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)') AND "
                   f"NOT REGEXP_CONTAINS(dst_id, r'\\|(Concept|Section)\\|{HIDDEN}(#|$)')")
        f_vec = f"NOT REGEXP_CONTAINS(node_id, r'\\|Section\\|{HIDDEN}#')"
    return {"nodes": f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_nodes ON `{rls}.nodes` GRANT TO ({g}) FILTER USING ({f_nodes})",
            "edges": f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_edges ON `{rls}.edges` GRANT TO ({g}) FILTER USING ({f_edges})",
            "section_vectors": f"CREATE OR REPLACE ROW ACCESS POLICY hide_intermediate_vectors ON `{rls}.section_vectors` GRANT TO ({vg}) FILTER USING ({f_vec})"}


def set_rls(client: bigquery.Client, grantees: list[str], vector_grantees: Optional[list[str]] = None, hide: bool = True,
            strict: bool = True) -> dict:
    """Apply the three `_rls` policies. Every statement is attempted even if an earlier one failed (each table's
    policy is an independent grant); per-table outcome is a job id or {"error": ...}. strict=True raises after all
    three were attempted so callers that need the full shape still fail; teardown uses strict=False."""
    from .publish import run
    out: dict = {"at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    errors = []
    for t, q in rls_statements(grantees, vector_grantees, hide).items():
        try:
            out[t] = run(client, q).job_id
        except Exception as e:  # noqa: BLE001 - keep going: the other tables' grants are independent
            out[t] = {"error": f"{type(e).__name__}: {str(e)[:300]}"}; errors.append(t)
    if errors and strict:
        raise RuntimeError(f"row access policy statements failed for {errors}: " + "; ".join(out[t]["error"] for t in errors))
    return out


def rls_grantees(client: bigquery.Client, ds: str = RLS_DS) -> dict[str, list[str]]:
    """Current grantee lists per `_rls` table, read back from the service (REST: rowAccessPolicies.list, then
    getIamPolicy per policy; grantees are the filteredDataViewer members). Redacted by the caller."""
    out: dict[str, list[str]] = {}
    api = client._connection.api_request
    for t in ("nodes", "edges", "section_vectors"):
        base = f"/projects/{PROJECT}/datasets/{ds}/tables/{t}/rowAccessPolicies"
        members: list[str] = []
        for pol in api(method="GET", path=base).get("rowAccessPolicies", []):
            pid = pol["rowAccessPolicyReference"]["policyId"]
            iam = api(method="POST", path=f"{base}/{pid}:getIamPolicy", data={})
            members += [m for b in iam.get("bindings", []) for m in b.get("members", [])]
        out[t] = sorted(set(members))
    return out


def gql_window_gate() -> dict:
    """Whether this spike's Enterprise-window admission gate would let a GQL variant run right now. GQL needs an
    Enterprise reservation; the gate refuses when any earlier window's job cleanup is unverified."""
    from .reservation import require_clean_windows, _load
    try:
        require_clean_windows(_load())
        return {"open": True}
    except Exception as e:  # noqa: BLE001 - the gate's own message is the reason
        return {"open": False, "reason": f"{type(e).__name__}: {str(e)[:300]}"}


def _mk_ds(client: bigquery.Client, ds: str, desc: str) -> None:
    d = bigquery.Dataset(f"{PROJECT}.{ds}"); d.location = LOCATION; d.default_table_expiration_ms = 14 * 86400 * 1000
    d.description = desc
    client.create_dataset(d, exists_ok=True)


def setup(client: bigquery.Client, base_pub: str) -> dict:
    from .publish import run, ensure_graph
    P = lambda k, t, v: bigquery.ScalarQueryParameter(k, t, v)
    log: dict = {"started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(),
                 "second_principal": "measured separately by `authz cases` -> evidence/authz_cases.json", "policies": []}
    base = f"{PROJECT}.{DATASET}"
    for ds in (RLS_DS, META_DS):
        _mk_ds(client, ds, "OKF BigQuery Graph spike 2026-09-05 governance fixture (temporary)")
        full = f"{PROJECT}.{ds}"
        for t in ("nodes", "edges", "section_vectors"):
            run(client, f"CREATE OR REPLACE TABLE `{full}.{t}` AS SELECT * FROM `{base}.{t}` WHERE publication_id = @p", [P("p", "STRING", base_pub)])
        run(client, f"CREATE MODEL IF NOT EXISTS `{full}.text_embedding` REMOTE WITH CONNECTION `{PROJECT}.us.bq-llm` OPTIONS (ENDPOINT = 'text-embedding-005')")
        log[f"graph_{ds}"] = ensure_graph(client, ds)
    meta = f"{PROJECT}.{META_DS}"
    OPERATOR = _operator_member()
    pol = list(rls_statements([OPERATOR]).values()) + [
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
    return set_rls(client, [_operator_member()], hide=False)


def restore(client: bigquery.Client, strict: bool = True) -> dict:
    """Operator-only hidden-intermediate policies (the 2026-09-05 fixture shape)."""
    return set_rls(client, [_operator_member()], hide=True, strict=strict)


# ----------------------------------------------------------------------------- judges (pure; hermetically tested)
def _label(ok: bool) -> str:
    return "MEASURED" if ok else "FAILED"


def _content(result: dict) -> dict:
    return {k: len(result.get(k) or []) for k in ("concepts", "paths", "computations")}


def allowed_control(allowed: dict, negative: dict, seed_local: str, hidden: str = HIDDEN) -> dict:
    """The restricted principal must be able to retrieve when it is allowed to, on the SAME restricted fixture:
    an allowed seed returns OK with at least one computation and no hidden id, and the negative case's own seed is
    visible (its concept is returned). Without this control an empty answer could be a stale fixture or a broken
    client, not enforcement."""
    a_ok = allowed.get("status") == "OK" and len(allowed.get("computations") or []) >= 1 and not leaks(allowed, hidden)
    seeds = [c.get("concept") for c in negative.get("concepts") or []]
    n_ok = negative.get("status") == "OK" and seeds == [seed_local]
    ok = a_ok and n_ok
    return {"ok": ok, "allowed": {"status": allowed.get("status"), **_content(allowed), "leaks_hidden_id": leaks(allowed, hidden)},
            "negative_seed_visible": n_ok, "negative_status": negative.get("status"),
            "reason": None if ok else ("allowed retrieval on the restricted fixture did not succeed" if not a_ok else "negative case's seed concept not visible to the principal")}


def _blocked_by_control(control: Optional[dict]) -> Optional[dict]:
    if control is None or not control.get("ok"):
        return {"label": "BLOCKED", "verdict": "NO_ALLOWED_CONTROL",
                "reason": "no working allowed control on the same restricted fixture: " + str((control or {}).get("reason") or "control not run")}
    return None


def judge_hidden_intermediate(result: dict, control: Optional[dict] = None, hidden: str = HIDDEN) -> dict:
    """Path through the hidden concept removed AND the hidden id absent from the whole answer surface
    (concepts, paths, warnings = the "explain" the caller sees). Graded only behind a working allowed control."""
    if (b := _blocked_by_control(control)):
        return b
    leak = leaks(result, hidden)
    ok = result.get("status") == "OK" and result.get("computations") == [] and result.get("paths") == [] and not leak
    return {"label": _label(ok), "verdict": "ENFORCED" if ok else "LEAK_OR_UNEXPECTED", "status": result.get("status"),
            **_content(result), "leaks_hidden_id": leak,
            "replacement": (result.get("concepts") or [{}])[0].get("replacement") if result.get("concepts") else None,
            "warnings": result.get("warnings")}


def judge_denied_bundle(result: dict, denied_ids: list[str], api_error: Optional[str] = None, control: Optional[dict] = None) -> dict:
    """No grant at all: DENIED with empty content, and neither the response nor the raw API error names an id."""
    if (b := _blocked_by_control(control)):
        return b
    leaked = leaked_ids(result, denied_ids) + (leaked_ids(api_error, denied_ids) if api_error else [])
    ok = (result.get("status") == "DENIED" and result.get("computations") == [] and result.get("concepts") == []
          and result.get("paths") == [] and not leaked)
    return {"label": _label(ok), "verdict": "DENIED_NO_LEAK" if ok else "LEAK_OR_UNEXPECTED", "status": result.get("status"),
            **_content(result), "leaked_id_count": len(leaked),
            "warnings": result.get("warnings"), "api_error_class": (api_error or "").split(":", 1)[0] or None}


def judge_output_denied(result: dict, probe: dict, denied_ids: list[str], seed_local: str, control: Optional[dict] = None) -> dict:
    """Seed store visible (vectors > 0, measured by a plain row count under the same principal) while nodes/edges
    yield zero rows: no computation, no SQL, and no id other than the caller-supplied seed appears anywhere."""
    if (b := _blocked_by_control(control)):
        return b
    others = [i for i in denied_ids if i != seed_local and not i.startswith(seed_local + "#")]
    leaked = leaked_ids(result, others)
    seed_visible = (probe.get("vectors") or 0) > 0
    walk_denied = (probe.get("nodes") or 0) == 0 and (probe.get("edges") or 0) == 0
    ok = (seed_visible and walk_denied and result.get("computations") == [] and result.get("paths") == [] and not leaked)
    return {"label": _label(ok), "verdict": "OUTPUT_DENIED_NO_LEAK" if ok else "LEAK_OR_UNEXPECTED", "status": result.get("status"),
            "seed_visible": seed_visible, "seed_visibility_evidence": "row count of section_vectors under the principal (not VECTOR_SEARCH)",
            "walk_denied": walk_denied, **_content(result), "leaked_id_count": len(leaked), "warnings": result.get("warnings"), "probe": probe}


def fold_variant(case: dict, name: str, variant: dict) -> dict:
    """An executed variant (e.g. the natural-language seed) keeps its own label and verdict, and a FAILED variant
    fails the enclosing case. A variant that could not execute (NOT_RUN) is recorded and does not grade the case."""
    case[name] = variant
    if variant.get("label") == "FAILED" and case.get("label") != "FAILED":
        case["label_before_variant"] = case.get("label")
        case["label"] = "FAILED"; case["verdict"] = f"{name.upper()}_{variant.get('verdict')}"
    return case


def judge_owner_fallback(owner_result: dict, sa_result: dict, sa_job_emails: list[str], sa_email: str,
                         owner_job_emails: list[str], operator_email: str, hidden: str = HIDDEN,
                         owner_on_restricted: Optional[dict] = None) -> dict:
    """Every job the SA session created is bound to the SA (jobs.get user_email), every owner job to the operator,
    and the two answers differ at the hidden set: the owner on the ungoverned base dataset sees the hidden path, the
    SA on the governed fixture does not. The owner arm runs on a different dataset, so the differential is a property
    of the fixture as much as of the principal; the identity binding is what earns NO_FALLBACK."""
    sa_bound = bool(sa_job_emails) and all(e == sa_email for e in sa_job_emails)
    owner_bound = bool(owner_job_emails) and all(e == operator_email for e in owner_job_emails)
    owner_saw, sa_saw = leaks(owner_result, hidden), leaks(sa_result, hidden)
    ok = sa_bound and owner_bound and owner_saw and not sa_saw and sa_result.get("computations") == []
    out = {"label": _label(ok), "verdict": "NO_FALLBACK" if ok else "FALLBACK_OR_UNEXPECTED",
           "sa_jobs": len(sa_job_emails), "sa_jobs_bound_to_sa": sa_bound,
           "owner_jobs": len(owner_job_emails), "owner_jobs_bound_to_operator": owner_bound,
           "owner_saw_hidden": owner_saw, "sa_saw_hidden": sa_saw,
           "owner_computations": len(owner_result.get("computations") or []), "sa_computations": len(sa_result.get("computations") or []),
           "note": "owner arm runs on the ungoverned base dataset; SA arm on the governed fixture"}
    if owner_on_restricted is not None:
        out["owner_on_restricted_fixture"] = {"status": owner_on_restricted.get("status"), "saw_hidden": leaks(owner_on_restricted, hidden),
                                              "computations": len(owner_on_restricted.get("computations") or [])}
    return out


def _closed(result: dict, denied_ids: list[str]) -> tuple[bool, dict]:
    """Explicit denial with nothing disclosed on any surface: status DENIED, every content array empty, and no
    publication identifier anywhere in the payload (warnings included)."""
    leaked = leaked_ids(result, denied_ids)
    ok = (result.get("status") == "DENIED" and result.get("concepts") == [] and result.get("paths") == []
          and result.get("computations") == [] and not leaked)
    return ok, {"status": result.get("status"), "cache": result.get("scope", {}).get("cache"), **_content(result), "leaked_id_count": len(leaked)}


def judge_revocation(warm: dict, hit: dict, replay: dict, fresh: dict, revocation_observed: bool, denied_ids: list[str]) -> dict:
    """Cached entry stored under the SA, replayed after the SA's dataset grant was removed: the replay AND a fresh
    request are explicitly DENIED with nothing on any disclosure surface. NOT_APPLICABLE only when no entry was stored."""
    wc, hc = (x.get("scope", {}).get("cache") for x in (warm, hit))
    if warm.get("status") != "OK" or wc != "MISS_STORED":
        return {"label": "NOT_APPLICABLE", "verdict": "NO_CACHE_ENTRY", "reason": f"warm run did not store a cache entry (status {warm.get('status')}, cache {wc})",
                "warm": (warm.get("status"), wc)}
    r_ok, r = _closed(replay, denied_ids)
    f_ok, f = _closed(fresh, denied_ids)
    ok = revocation_observed and hc == "HIT_RECHECKED" and r_ok and r["cache"] == "HIT_DENIED" and f_ok
    return {"label": _label(ok), "verdict": "FAIL_CLOSED" if ok else "LEAK_OR_UNEXPECTED", "revocation_observed": revocation_observed,
            "warm": (warm.get("status"), wc, len(warm.get("computations") or [])), "hit": (hit.get("status"), hc), "replay": r, "fresh_after_revoke": f}


def judge_cross_principal_replay(owner_warm: dict, sa_replay: dict, denied_ids: list[str]) -> dict:
    """An entry the owner stored (ungoverned dataset, hidden path inside) replayed under the SA with the same cache
    and the same requester label: the SA must get an explicit DENIED with nothing disclosed (re-check runs under the
    SA's own credential), never the owner's content."""
    stored = owner_warm.get("status") == "OK" and owner_warm.get("scope", {}).get("cache") == "MISS_STORED"
    if not stored:
        return {"label": "NOT_APPLICABLE", "verdict": "NO_CACHE_ENTRY", "reason": "owner warm run did not store a cache entry"}
    ok, r = _closed(sa_replay, denied_ids)
    return {"label": _label(ok and r["cache"] == "HIT_DENIED"), "verdict": "CACHE_BOUND_TO_CREDENTIAL" if ok and r["cache"] == "HIT_DENIED" else "LEAK_OR_UNEXPECTED",
            "owner_entry_computations": len(owner_warm.get("computations") or []), "sa_replay": r}


# ----------------------------------------------------------------------------- live runner
def _probe(client: bigquery.Client, ds: str, pub: str) -> dict:
    """Row counts the principal can see (plain SQL). Raises on permission errors (caller decides)."""
    q = f"""SELECT (SELECT COUNT(*) FROM `{PROJECT}.{ds}.nodes` WHERE publication_id = @p) AS nodes,
                   (SELECT COUNTIF(local_id = '{HIDDEN}') FROM `{PROJECT}.{ds}.nodes` WHERE publication_id = @p) AS hidden,
                   (SELECT COUNT(*) FROM `{PROJECT}.{ds}.edges` WHERE publication_id = @p) AS edges,
                   (SELECT COUNT(*) FROM `{PROJECT}.{ds}.section_vectors` WHERE publication_id = @p) AS vectors"""
    cfg = bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("p", "STRING", pub)], use_query_cache=False,
                                  labels={"okf_spike": "bq_graph_20260905", "stage": "sa_probe"})
    return dict(list(client.query(q, job_config=cfg, location=LOCATION).result())[0])


def _wait(fn: Callable[[], Any], pred: Callable[[Any], bool], timeout_s: int, every_s: int = 10) -> tuple[bool, Any, int]:
    """Poll a propagation-dependent observation; returns (satisfied, last_observation, seconds_waited)."""
    t0 = time.monotonic()
    last: Any = None
    while True:
        try:
            last = fn()
        except Exception as e:  # noqa: BLE001 - the exception is a legitimate observation (e.g. Forbidden)
            last = e
        if pred(last):
            return True, last, int(time.monotonic() - t0)
        if time.monotonic() - t0 >= timeout_s:
            return False, last, int(time.monotonic() - t0)
        time.sleep(every_s)


def _is_denied(obs: Any) -> bool:
    from google.api_core import exceptions as gexc
    return isinstance(obs, (gexc.Forbidden, gexc.Unauthorized, gexc.NotFound))


def _job_emails(owner: bigquery.Client, result: dict) -> list[str]:
    return [owner.get_job(j["job_id"], location=LOCATION).user_email for j in result.get("timing", {}).get("jobs", []) if j.get("job_id")]


def _bound(owner: bigquery.Client, result: dict, sa: str) -> dict:
    emails = _job_emails(owner, result)
    return {"jobs": len(emails), "bound_to_sa": bool(emails) and all(e == sa for e in emails)}


def mask(text: Any, sa: str, ids: tuple | list = ()) -> Any:
    """Every emitted or stored failure text: e-mails redacted AND publication identifiers masked (the known
    universe plus the fixture constants), so no log line or reason can name a denied identifier."""
    return sanitize_ids(redact(text, sa), list(FIXTURE_IDS) + list(ids))


def _err(e: BaseException, sa: str, n: int = 400, ids: tuple | list = ()) -> str:
    return mask(f"{type(e).__name__}: {str(e)[:n]}", sa, ids)


def record_case(cases: dict, key: str, fn: Callable[..., dict], sa: str, ids: tuple | list = ()) -> None:
    """Merge a judge result into the case slot. The placeholder reason is dropped first so a judge-supplied reason
    (NOT_APPLICABLE / BLOCKED) survives. `fn` may accept a `partial` dict and judge each completed observation into
    it promptly; on an exception those observations are retained, and an executed FAILED observation takes
    precedence over the blocker (an exception after a leak is not a pass and not merely BLOCKED). The log line is
    masked before it is written."""
    cases[key].pop("reason", None)
    partial: dict = {}
    try:
        cases[key].update(fn(partial) if inspect.signature(fn).parameters else fn())
    except Exception as e:  # noqa: BLE001
        cases[key].update(partial)
        failed = [n for n, v in partial.items() if isinstance(v, dict) and v.get("label") == "FAILED"]
        if failed:
            cases[key].update(label="FAILED", verdict=f"PARTIAL_{failed[0].upper()}_{partial[failed[0]].get('verdict')}",
                              reason=f"executed observation failed before the case completed; then {_err(e, sa, ids=ids)}")
        else:
            cases[key].update(label="BLOCKED", reason=_err(e, sa, ids=ids))
    print(key, cases[key].get("label"), mask(cases[key].get("verdict") or cases[key].get("reason"), sa, ids), flush=True)


def teardown(owner: bigquery.Client, sa_client: Any, sa: str, pub: str, wait_s: int) -> dict:
    """Independent cleanup steps, each attempted even when an earlier one failed; VERIFIED only when every step
    succeeded, the read-back grantees exclude the SA, and the SA is observed denied on the fixture."""
    td: dict = {"steps": {}}

    def step(name: str, fn: Callable[[], Any]) -> Any:
        try:
            v = fn(); td["steps"][name] = {"ok": True}; return v
        except Exception as e:  # noqa: BLE001
            td["steps"][name] = {"ok": False, "error": _err(e, sa, 300)}; return None  # ids masked by _err

    td["reader_removed_at"] = step("remove_dataset_reader", lambda: set_dataset_reader(owner, RLS_DS, sa, False))
    restored = step("restore_policies", lambda: restore(owner, strict=False)) or {}
    for t in ("nodes", "edges", "section_vectors"):   # each policy is an independent grant: attempted and recorded separately
        r = restored.get(t)
        td["steps"][f"restore_policy_{t}"] = {"ok": isinstance(r, str)} if isinstance(r, str) else {"ok": False, "error": mask((r or {}).get("error", "not attempted"), sa)}
    td["policies_restored"] = {k: (v if isinstance(v, str) else mask(v, sa)) for k, v in restored.items()}
    grantees = step("readback_grantees", lambda: rls_grantees(owner))
    if grantees is not None:
        td["rls_grantees_after"] = redact(grantees, sa)
        td["sa_still_in_grantees"] = any(sa in g or SA_ALIAS in g for gs in td["rls_grantees_after"].values() for g in gs)
    if sa_client is not None:
        obs = step("sa_denied_after_teardown", lambda: _wait(lambda: _probe(sa_client, RLS_DS, pub), _is_denied, wait_s))
        if obs is not None:
            td["sa_denied_after_teardown"], td["waited_s"] = obs[0], obs[2]
    else:
        td["steps"]["sa_denied_after_teardown"] = {"ok": False, "error": "no impersonated client to observe with"}
    td["status"] = ("VERIFIED" if all(s["ok"] for s in td["steps"].values()) and td.get("sa_still_in_grantees") is False
                    and td.get("sa_denied_after_teardown") is True else "UNVERIFIED")
    return td


def second_principal_cases(owner: bigquery.Client, pub: str, as_of: str, engine: str = "fallback", wait_s: int = 240,
                           sa_email: Optional[str] = None, factory: Callable[[str], Any] = impersonated_client,
                           out_path: Optional[str] = "evidence/authz_cases.json") -> dict:
    """Run the five second-principal negatives live. Every case ends with a label from LABELS (a shared-setup
    failure blocks the unreached cases with the stage and reason); grants are removed by `teardown` whatever
    happened; the evidence is always finalized (`_finish`: alias only, every publication identifier masked)."""
    from .retrieve import retrieve
    sa = sa_email or restricted_sa()
    member = f"serviceAccount:{sa}"
    op_email = operator().split(":", 1)[-1]
    seed_local = "metrics/gross-margin-legacy"
    legacy, revenue = f"forced:{seed_local}.md", "forced:metrics/revenue.md"
    ev: dict = {"started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "principal": SA_ALIAS, "engine": engine,
                "publication_id": pub, "as_of": as_of, "cases": {k: {"description": v, "label": "BLOCKED", "reason": "not reached"} for k, v in CASES.items()},
                "grants": [], "stages": [], "teardown": {}}
    cases = ev["cases"]
    gate = gql_window_gate()
    ev["window_gate"] = gate
    if engine == "gql":
        # GQL needs an Enterprise reservation, i.e. this spike's bounded window lifecycle (WindowJobs admission, deadline,
        # job journal, cancellation, separate capacity and job-cleanup receipts) for BOTH clients. This slice does not
        # wire the impersonated client into that lifecycle, so no GQL job is submitted: every case is BLOCKED.
        reason = ("engine=gql refused before preflight: GQL requires the bounded window lifecycle for both the owner and "
                  "the impersonated client (not wired in this slice); " + ("window gate open" if gate["open"] else f"window gate: {gate['reason']}"))
        for c in cases.values():
            c.update(label="BLOCKED", reason=reason)
        ev["gql_variant"] = {"label": "BLOCKED", "reason": reason}
        return _finish(ev, out_path, sa, [])
    ev["engine_note"] = ("relational fallback (on-demand): the same RLS policies apply to the same base tables, but this is not a "
                         "GQL traversal (labelled FALLBACK in every result)")
    ev["gql_variant"] = {"label": "BLOCKED", "reason": "GQL variant not run: requires the bounded window lifecycle for both clients (not wired in this slice)"
                         + ("" if gate["open"] else f"; window gate also refuses: {gate['reason']}")}
    pre, sa_client = preflight(sa, factory)
    ev["preflight"] = pre
    if pre["status"] != "OK":
        for c in cases.values():
            c.update(label="BLOCKED", reason=f"impersonation preflight failed: {pre['error']}")
        return _finish(ev, out_path, sa, [])
    denied_ids: list[str] = []
    stage = "start"

    def mark(s: str) -> None:
        nonlocal stage
        stage = s; ev["stages"].append(s)

    try:
        try:
            mark("denied_id_universe")
            denied_ids = [r.local_id for r in owner.query(f"SELECT DISTINCT local_id FROM `{PROJECT}.{DATASET}.nodes` WHERE publication_id = @p",
                                                          job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("p", "STRING", pub)]),
                                                          location=LOCATION).result()]
            ev["denied_id_universe"] = len(denied_ids)
            # ---- phase A: SA is a reader of `_rls` with the same hidden-intermediate policy as the operator
            mark("phase_a_grants")
            ev["grants"].append({"at": set_dataset_reader(owner, RLS_DS, sa, True), "ds": RLS_DS, "principal": SA_ALIAS, "reader": True})
            ev["grants"].append({"policies": set_rls(owner, [_operator_member(), member]), "grantees": ["operator", SA_ALIAS], "shape": "hidden-intermediate"})
            mark("phase_a_propagation")
            ok, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub), lambda o: isinstance(o, dict) and o["nodes"] > 0 and o["hidden"] == 0, wait_s)
            ev["phase_a_propagation"] = {"ready": ok, "waited_s": waited, "probe": obs if isinstance(obs, dict) else redact(str(obs)[:200], sa)}
            if not ok:
                raise RuntimeError(f"SA grant on {RLS_DS} did not propagate within {wait_s}s: {redact(str(obs)[:200], sa)}")
            sa_rls = {"engine": engine, "bq": sa_client, "ds": RLS_DS}
            # ---- allowed control on the same restricted fixture, same principal: must succeed before any negative is graded
            mark("allowed_control")
            r_ctl = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
            r1 = retrieve(legacy, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
            control = allowed_control(r_ctl, r1, seed_local)
            control["allowed_jobs"] = _bound(owner, r_ctl, sa)
            ev["allowed_control"] = control
            mark("cases")

            def case1():
                j = judge_hidden_intermediate(r1, control); j["timing_ms"] = r1["timing"]["total_ms"]; j["sa_jobs"] = _bound(owner, r1, sa); j["full_result"] = r1
                return j
            record_case(cases, "hidden_intermediate", case1, sa, denied_ids)

            def case4():
                r_owner = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, {"engine": engine, "bq": owner, "ds": DATASET})
                r_owner_rls = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, {"engine": engine, "bq": owner, "ds": RLS_DS})
                j = judge_owner_fallback(r_owner, r1, _job_emails(owner, r1), sa, _job_emails(owner, r_owner), op_email, owner_on_restricted=r_owner_rls)
                j["owner_paths"] = r_owner["paths"]; j["sa_paths"] = r1["paths"]
                return j
            record_case(cases, "owner_fallback_negative", case4, sa, denied_ids)

            def case5(partial: dict):
                cache: dict = {}
                cc = dict(sa_rls, cache=cache)
                warm = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, cc)
                hit = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, cc)
                # cross-principal: an entry the OWNER stored on the ungoverned dataset, replayed under the SA with the same cache and label
                xc: dict = {}
                owner_warm = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, {"engine": engine, "bq": owner, "ds": DATASET, "cache": xc})
                sa_replay = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, {"engine": engine, "bq": sa_client, "ds": DATASET, "cache": xc})
                partial["cross_principal_replay"] = judge_cross_principal_replay(owner_warm, sa_replay, denied_ids)   # judged promptly
                revoked_at = set_dataset_reader(owner, RLS_DS, sa, False)
                ev["grants"].append({"at": revoked_at, "ds": RLS_DS, "principal": SA_ALIAS, "reader": False})
                seen, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub), _is_denied, wait_s)
                replay = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, cc)
                r_ok, r = _closed(replay, denied_ids)
                partial["replay_observation"] = {"label": _label(r_ok and r["cache"] == "HIT_DENIED"), "verdict": "REPLAY_CLOSED" if r_ok else "REPLAY_LEAK_OR_UNEXPECTED", **r}
                fresh = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
                j = judge_revocation(warm, hit, replay, fresh, seen, denied_ids)
                j.update(revoked_at=revoked_at, revocation_propagation_s=waited, revocation_observation=type(obs).__name__,
                         replay_warnings=replay.get("warnings"), sa_jobs=_bound(owner, warm, sa))
                return fold_variant(j, "cross_principal_replay", partial["cross_principal_replay"])
            record_case(cases, "revocation_before_cached_replay", case5, sa, denied_ids)

            # ---- phase B: never granted on the base dataset
            def case2():
                r2 = retrieve(legacy, BUNDLE_ID, pub, SA_ALIAS, as_of, {"engine": engine, "bq": sa_client, "ds": DATASET})
                try:
                    _probe(sa_client, DATASET, pub); api_err = None
                except Exception as e:  # noqa: BLE001
                    api_err = f"{type(e).__name__}: {str(e)}"
                j = judge_denied_bundle(r2, denied_ids, api_err, control)
                j["api_error_redacted"] = redact(api_err[:300], sa) if api_err else None
                j["sa_jobs"] = _bound(owner, r2, sa); j["full_result"] = r2
                return j
            record_case(cases, "denied_bundle", case2, sa, denied_ids)

            # ---- phase C: vectors visible, nodes/edges denied (policy grantees exclude the SA on nodes/edges only)
            def case3(partial: dict):
                ev["grants"].append({"at": set_dataset_reader(owner, RLS_DS, sa, True), "ds": RLS_DS, "principal": SA_ALIAS, "reader": True})
                ev["grants"].append({"policies": set_rls(owner, [_operator_member()], vector_grantees=[_operator_member(), member]),
                                     "grantees": {"nodes_edges": ["operator"], "section_vectors": ["operator", SA_ALIAS]}, "shape": "hidden-intermediate"})
                ok, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub),
                                        lambda o: isinstance(o, dict) and o["vectors"] > 0 and o["nodes"] == 0 and o["edges"] == 0, wait_s)
                if not ok:
                    raise RuntimeError(f"phase C grants did not propagate within {wait_s}s: {redact(str(obs)[:200], sa)}")
                r3 = retrieve(legacy, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
                j = judge_output_denied(r3, obs, denied_ids, seed_local, control)
                partial["forced_seed"] = {k: j[k] for k in ("label", "verdict", "status", "leaked_id_count")}   # judged promptly
                j["propagation_s"] = waited; j["sa_jobs"] = _bound(owner, r3, sa); j["full_result"] = r3
                try:  # natural seed exercises the vector store itself; the remote embedding model may not be usable by the SA
                    rn = retrieve("How do we calculate gross margin, exactly?", BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
                    jn = judge_output_denied(rn, obs, denied_ids, "", control)
                    jn.update(seed_hits=len(rn["concepts"]), full_result=rn)
                except Exception as e:  # noqa: BLE001 - could not execute: recorded, not graded
                    jn = {"label": "NOT_RUN", "verdict": None, "error": _err(e, sa, 200, denied_ids)}
                return fold_variant(j, "natural_seed", jn)
            record_case(cases, "output_denied_seed_visible", case3, sa, denied_ids)
        except Exception as e:  # noqa: BLE001 - shared setup failed: block what was not reached, keep cleaning up, still finalize
            ev["abort"] = {"stage": stage, "reason": _err(e, sa, ids=denied_ids)}
            for c in cases.values():
                if c.get("reason") == "not reached":
                    c["reason"] = f"aborted at {stage}: {ev['abort']['reason']}"
            print("ABORT at", stage, ev["abort"]["reason"], flush=True)
    finally:
        ev["teardown"] = teardown(owner, sa_client, sa, pub, wait_s)
    return _finish(ev, out_path, sa, denied_ids)


def _finish(ev: dict, out_path: Optional[str], sa: str, denied_ids: list[str]) -> dict:
    """Finalize and publish: labels summarized, e-mails redacted, every publication identifier masked (the known
    universe plus the fixture constants, so a run that never learned the universe still masks what it could have
    named). Verified before writing; a violation raises instead of publishing."""
    ev["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ev["summary"] = {k: c.get("label") for k, c in ev["cases"].items()}
    ids = sorted(set(denied_ids) | set(FIXTURE_IDS))
    ev["id_sanitization"] = {"masked_ids": len(ids), "universe_known": bool(denied_ids), "token": "<id:sha256[:8]>"}
    ev = sanitize_ids(redact(ev, sa), ids)
    text = json.dumps(ev, default=str)
    if sa in text or (operator().split(":", 1)[-1] or "\x00") in text:
        raise RuntimeError("raw principal e-mail must never reach evidence")
    if any(leaks(text, i) for i in ids):
        raise RuntimeError("publication identifier survived sanitization")
    if out_path:
        with open(out_path, "w") as fh:
            json.dump(ev, fh, indent=1, default=str)
    return ev


if __name__ == "__main__":
    import sys
    from .publish import resolve_pointer
    client = bigquery.Client(project=PROJECT, location=LOCATION)
    if sys.argv[1] == "setup":
        o = setup(client, sys.argv[2]); print(json.dumps({k: v for k, v in o.items() if k != "policies"}, indent=1, default=str))
        for p in o["policies"]: print(p["ok"], p.get("error", ""), p["sql"][:100])
    elif sys.argv[1] == "revoke":
        print(revoke(client))
    elif sys.argv[1] == "restore":
        print(restore(client))
    elif sys.argv[1] == "cases":
        engine = sys.argv[sys.argv.index("--engine") + 1] if "--engine" in sys.argv else "fallback"
        pub = sys.argv[sys.argv.index("--pub") + 1] if "--pub" in sys.argv else resolve_pointer(client, BUNDLE_ID)
        as_of = sys.argv[sys.argv.index("--as-of") + 1] if "--as-of" in sys.argv else "2026-09-05T00:00:00Z"
        o = second_principal_cases(client, pub, as_of, engine=engine)
        print(json.dumps({"summary": o["summary"], "preflight": o.get("preflight"), "abort": o.get("abort"), "teardown": o["teardown"]}, indent=1, default=str))
