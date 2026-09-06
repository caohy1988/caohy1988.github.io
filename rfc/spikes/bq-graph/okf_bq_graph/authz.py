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
NOT_APPLICABLE-with-reason; a skipped run is never acceptance evidence. Evidence never carries the raw service
account e-mail (alias only) and never names a denied identifier (see `redact`).
"""
from __future__ import annotations

import datetime as _dt
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


def _operator() -> str:
    e = _os.environ.get("OKF_OPERATOR_EMAIL") or _sp.run(["gcloud", "config", "get-value", "account"], capture_output=True, text=True).stdout.strip()
    return f"user:{e}"


OPERATOR = _operator()   # never committed; resolved from the active gcloud account or OKF_OPERATOR_EMAIL
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
_EMAIL_RE = re.compile(r"[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}")


# ----------------------------------------------------------------------------- identity / redaction
def restricted_sa() -> str:
    return _os.environ.get("OKF_SPIKE_RESTRICTED_SA") or SA_DEFAULT


def redact(obj: Any, sa_email: Optional[str] = None) -> Any:
    """Evidence hygiene: the SA e-mail becomes its alias, the operator e-mail becomes `user:operator`, any other
    e-mail becomes `<email>`. Works on any JSON-serialisable object; returns the same shape."""
    text = json.dumps(obj, default=str)
    for secret, alias in ((sa_email or restricted_sa(), SA_ALIAS), (OPERATOR.split(":", 1)[-1], "operator")):
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


def set_rls(client: bigquery.Client, grantees: list[str], vector_grantees: Optional[list[str]] = None, hide: bool = True) -> dict:
    from .publish import run
    out = {"at": _dt.datetime.now(_dt.timezone.utc).isoformat()}
    for t, q in rls_statements(grantees, vector_grantees, hide).items():
        out[t] = run(client, q).job_id
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
    return set_rls(client, [OPERATOR], hide=False)


def restore(client: bigquery.Client) -> dict:
    """Operator-only hidden-intermediate policies (the 2026-09-05 fixture shape)."""
    return set_rls(client, [OPERATOR], hide=True)


# ----------------------------------------------------------------------------- judges (pure; hermetically tested)
def _label(ok: bool) -> str:
    return "MEASURED" if ok else "FAILED"


def judge_hidden_intermediate(result: dict, hidden: str = HIDDEN) -> dict:
    """Path through the hidden concept removed AND the hidden id absent from the whole answer surface
    (concepts, paths, warnings = the "explain" the caller sees)."""
    leak = leaks(result, hidden)
    ok = result.get("status") in ("OK", "DENIED", "NO_SEED") and result.get("computations") == [] and not leak
    return {"label": _label(ok), "verdict": "ENFORCED" if ok else "LEAK_OR_UNEXPECTED", "status": result.get("status"),
            "computations": len(result.get("computations") or []), "paths": result.get("paths"), "leaks_hidden_id": leak,
            "replacement": (result.get("concepts") or [{}])[0].get("replacement") if result.get("concepts") else None,
            "warnings": result.get("warnings")}


def judge_denied_bundle(result: dict, denied_ids: list[str], api_error: Optional[str] = None) -> dict:
    """No grant at all: DENIED with empty content, and neither the response nor the raw API error names an id."""
    leaked = leaked_ids(result, denied_ids) + (leaked_ids(api_error, denied_ids) if api_error else [])
    ok = (result.get("status") == "DENIED" and result.get("computations") == [] and result.get("concepts") == []
          and result.get("paths") == [] and not leaked)
    return {"label": _label(ok), "verdict": "DENIED_NO_LEAK" if ok else "LEAK_OR_UNEXPECTED", "status": result.get("status"),
            "rows": len(result.get("concepts") or []) + len(result.get("computations") or []), "leaked_id_count": len(leaked),
            "warnings": result.get("warnings"), "api_error_class": (api_error or "").split(":", 1)[0] or None}


def judge_output_denied(result: dict, probe: dict, denied_ids: list[str], seed_local: str) -> dict:
    """Seed store visible (vectors > 0) while nodes/edges yield zero rows: no computation, no SQL, and no id other than
    the caller-supplied seed appears anywhere in the answer."""
    others = [i for i in denied_ids if i != seed_local and not i.startswith(seed_local + "#")]
    leaked = leaked_ids(result, others)
    seed_visible = (probe.get("vectors") or 0) > 0
    walk_denied = (probe.get("nodes") or 0) == 0 and (probe.get("edges") or 0) == 0
    ok = (seed_visible and walk_denied and result.get("computations") == [] and not leaked
          and all(c.get("sql") is None for c in result.get("computations") or []))
    return {"label": _label(ok), "verdict": "OUTPUT_DENIED_NO_LEAK" if ok else "LEAK_OR_UNEXPECTED", "status": result.get("status"),
            "seed_visible": seed_visible, "walk_denied": walk_denied, "computations": len(result.get("computations") or []),
            "leaked_id_count": len(leaked), "warnings": result.get("warnings"), "probe": probe}


def judge_owner_fallback(owner_result: dict, sa_result: dict, sa_job_emails: list[str], sa_email: str,
                         owner_job_emails: list[str], operator_email: str, hidden: str = HIDDEN) -> dict:
    """Every job the SA session created is bound to the SA (jobs.get user_email), every owner job to the operator,
    and the two answers differ exactly at the hidden set: owner sees the hidden path, SA does not."""
    sa_bound = bool(sa_job_emails) and all(e == sa_email for e in sa_job_emails)
    owner_bound = bool(owner_job_emails) and all(e == operator_email for e in owner_job_emails)
    owner_saw, sa_saw = leaks(owner_result, hidden), leaks(sa_result, hidden)
    ok = sa_bound and owner_bound and owner_saw and not sa_saw and sa_result.get("computations") == []
    return {"label": _label(ok), "verdict": "NO_FALLBACK" if ok else "FALLBACK_OR_UNEXPECTED",
            "sa_jobs": len(sa_job_emails), "sa_jobs_bound_to_sa": sa_bound,
            "owner_jobs": len(owner_job_emails), "owner_jobs_bound_to_operator": owner_bound,
            "owner_saw_hidden": owner_saw, "sa_saw_hidden": sa_saw,
            "owner_computations": len(owner_result.get("computations") or []), "sa_computations": len(sa_result.get("computations") or [])}


def judge_revocation(warm: dict, hit: dict, replay: dict, fresh: dict, revocation_observed: bool) -> dict:
    """Cached entry stored under the SA, replayed after the SA's dataset grant was removed: replay refused with no
    content; a fresh request is refused too. NOT_APPLICABLE only when no entry was ever stored."""
    wc, hc, rc = (x.get("scope", {}).get("cache") for x in (warm, hit, replay))
    if warm.get("status") != "OK" or wc != "MISS_STORED":
        return {"label": "NOT_APPLICABLE", "verdict": "NO_CACHE_ENTRY", "reason": f"warm run did not store a cache entry (status {warm.get('status')}, cache {wc})",
                "warm": (warm.get("status"), wc)}
    ok = (revocation_observed and hc == "HIT_RECHECKED" and replay.get("status") != "OK" and replay.get("computations") == []
          and rc == "HIT_DENIED" and fresh.get("status") != "OK" and fresh.get("computations") == [])
    return {"label": _label(ok), "verdict": "FAIL_CLOSED" if ok else "LEAK_OR_UNEXPECTED", "revocation_observed": revocation_observed,
            "warm": (warm.get("status"), wc), "hit": (hit.get("status"), hc),
            "replay": (replay.get("status"), rc, len(replay.get("computations") or [])),
            "fresh_after_revoke": (fresh.get("status"), len(fresh.get("computations") or []), (fresh.get("warnings") or [])[:2])}


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


def second_principal_cases(owner: bigquery.Client, pub: str, as_of: str, engine: str = "fallback", wait_s: int = 240,
                           sa_email: Optional[str] = None, factory: Callable[[str], Any] = impersonated_client,
                           out_path: Optional[str] = "evidence/authz_cases.json") -> dict:
    """Run the five second-principal negatives live. Every case ends with a label from LABELS; grants are removed in
    `finally`; the evidence written is redacted (alias only, no denied ids: only counts and booleans about them)."""
    from .retrieve import retrieve
    sa = sa_email or restricted_sa()
    member = f"serviceAccount:{sa}"
    op_email = OPERATOR.split(":", 1)[-1]
    legacy, revenue = "forced:metrics/gross-margin-legacy.md", "forced:metrics/revenue.md"
    ev: dict = {"started_at": _dt.datetime.now(_dt.timezone.utc).isoformat(), "principal": SA_ALIAS, "engine": engine,
                "publication_id": pub, "as_of": as_of, "cases": {k: {"description": v, "label": "BLOCKED", "reason": "not reached"} for k, v in CASES.items()},
                "grants": [], "teardown": {}}
    if engine != "gql":
        gate = gql_window_gate()
        ev["engine_note"] = ("relational fallback (on-demand): the same RLS policies apply to the same base tables, but this is not a "
                             "GQL traversal (labelled FALLBACK in every result)")
        ev["gql_variant"] = ({"label": "NOT_RUN", "reason": "window gate open; GQL variant not requested in this pass"} if gate["open"] else
                             {"label": "BLOCKED", "reason": f"GQL needs an Enterprise reservation window and the spike's admission gate refuses: {gate['reason']}"})
    pre, sa_client = preflight(sa, factory)
    ev["preflight"] = pre
    if pre["status"] != "OK":
        for c in ev["cases"].values():
            c.update(label="BLOCKED", reason=f"impersonation preflight failed: {pre['error']}")
        return _finish(ev, out_path, sa)
    cases = ev["cases"]

    def run_case(key: str, fn: Callable[[], dict]) -> None:
        try:
            cases[key].update(fn()); cases[key].pop("reason", None)
        except Exception as e:  # noqa: BLE001 - a case that cannot run is a recorded blocker, not a pass
            cases[key].update(label="BLOCKED", reason=redact(f"{type(e).__name__}: {str(e)[:400]}", sa))
        print(key, cases[key].get("label"), cases[key].get("verdict") or cases[key].get("reason"), flush=True)

    try:
        denied_ids = [r.local_id for r in owner.query(f"SELECT DISTINCT local_id FROM `{PROJECT}.{DATASET}.nodes` WHERE publication_id = @p",
                                                      job_config=bigquery.QueryJobConfig(query_parameters=[bigquery.ScalarQueryParameter("p", "STRING", pub)]),
                                                      location=LOCATION).result()]
        ev["denied_id_universe"] = len(denied_ids)
        # ---- phase A: SA is a reader of `_rls` with the same hidden-intermediate policy as the operator
        ev["grants"].append({"at": set_dataset_reader(owner, RLS_DS, sa, True), "ds": RLS_DS, "principal": SA_ALIAS, "reader": True})
        ev["grants"].append({"policies": set_rls(owner, [OPERATOR, member]), "grantees": ["operator", SA_ALIAS], "shape": "hidden-intermediate"})
        ok, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub), lambda o: isinstance(o, dict) and o["nodes"] > 0 and o["hidden"] == 0, wait_s)
        ev["phase_a_propagation"] = {"ready": ok, "waited_s": waited, "probe": obs if isinstance(obs, dict) else redact(str(obs)[:200], sa)}
        if not ok:
            raise RuntimeError(f"SA grant on {RLS_DS} did not propagate within {wait_s}s: {redact(str(obs)[:200], sa)}")
        sa_rls = {"engine": engine, "bq": sa_client, "ds": RLS_DS}
        r1 = retrieve(legacy, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)

        def case1():
            j = judge_hidden_intermediate(r1); j["timing_ms"] = r1["timing"]["total_ms"]; j["full_result"] = r1
            return j
        run_case("hidden_intermediate", case1)

        def case4():
            r_owner = retrieve(legacy, BUNDLE_ID, pub, "operator", as_of, {"engine": engine, "bq": owner, "ds": DATASET})
            j = judge_owner_fallback(r_owner, r1, _job_emails(owner, r1), sa, _job_emails(owner, r_owner), op_email)
            j["owner_paths"] = r_owner["paths"]; j["sa_paths"] = r1["paths"]
            return j
        run_case("owner_fallback_negative", case4)

        def case5():
            cache: dict = {}
            cc = dict(sa_rls, cache=cache)
            warm = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, cc)
            hit = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, cc)
            revoked_at = set_dataset_reader(owner, RLS_DS, sa, False)
            ev["grants"].append({"at": revoked_at, "ds": RLS_DS, "principal": SA_ALIAS, "reader": False})
            seen, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub), _is_denied, wait_s)
            replay = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, cc)
            fresh = retrieve(revenue, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
            j = judge_revocation(warm, hit, replay, fresh, seen)
            j.update(revoked_at=revoked_at, revocation_propagation_s=waited, revocation_observation=type(obs).__name__,
                     replay_warnings=replay.get("warnings"))
            return j
        run_case("revocation_before_cached_replay", case5)

        # ---- phase B: never granted on the base dataset
        def case2():
            r2 = retrieve(legacy, BUNDLE_ID, pub, SA_ALIAS, as_of, {"engine": engine, "bq": sa_client, "ds": DATASET})
            try:
                _probe(sa_client, DATASET, pub); api_err = None
            except Exception as e:  # noqa: BLE001
                api_err = f"{type(e).__name__}: {str(e)}"
            j = judge_denied_bundle(r2, denied_ids, api_err)
            j["api_error_redacted"] = redact(api_err[:300], sa) if api_err else None
            j["full_result"] = r2
            return j
        run_case("denied_bundle", case2)

        # ---- phase C: vectors visible, nodes/edges denied (policy grantees exclude the SA on nodes/edges only)
        def case3():
            ev["grants"].append({"at": set_dataset_reader(owner, RLS_DS, sa, True), "ds": RLS_DS, "principal": SA_ALIAS, "reader": True})
            ev["grants"].append({"policies": set_rls(owner, [OPERATOR], vector_grantees=[OPERATOR, member]),
                                 "grantees": {"nodes_edges": ["operator"], "section_vectors": ["operator", SA_ALIAS]}, "shape": "hidden-intermediate"})
            ok, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub),
                                    lambda o: isinstance(o, dict) and o["vectors"] > 0 and o["nodes"] == 0 and o["edges"] == 0, wait_s)
            if not ok:
                raise RuntimeError(f"phase C grants did not propagate within {wait_s}s: {redact(str(obs)[:200], sa)}")
            r3 = retrieve(legacy, BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
            j = judge_output_denied(r3, obs, denied_ids, "metrics/gross-margin-legacy")
            j["propagation_s"] = waited; j["full_result"] = r3
            try:  # natural seed exercises the vector store itself; the remote embedding model may not be usable by the SA
                rn = retrieve("How do we calculate gross margin, exactly?", BUNDLE_ID, pub, SA_ALIAS, as_of, sa_rls)
                jn = judge_output_denied(rn, obs, denied_ids, "")
                j["natural_seed"] = {"status": rn["status"], "seed_hits": len(rn["concepts"]), "computations": len(rn["computations"]),
                                     "leaked_id_count": jn["leaked_id_count"], "warnings": rn["warnings"]}
            except Exception as e:  # noqa: BLE001
                j["natural_seed"] = {"status": "NOT_RUN", "error": redact(f"{type(e).__name__}: {str(e)[:200]}", sa)}
            return j
        run_case("output_denied_seed_visible", case3)
    finally:
        td = ev["teardown"]
        try:
            td["reader_removed_at"] = set_dataset_reader(owner, RLS_DS, sa, False)
            td["policies_restored"] = restore(owner)
            td["rls_grantees_after"] = redact(rls_grantees(owner), sa)
            td["sa_still_in_grantees"] = any(SA_ALIAS in g or sa in g for gs in td["rls_grantees_after"].values() for g in gs)
            seen, obs, waited = _wait(lambda: _probe(sa_client, RLS_DS, pub), _is_denied, wait_s)
            td["sa_denied_after_teardown"] = seen; td["waited_s"] = waited
            td["status"] = "VERIFIED" if seen and not td["sa_still_in_grantees"] else "UNVERIFIED"
        except Exception as e:  # noqa: BLE001
            td["status"] = "UNVERIFIED"; td["error"] = redact(f"{type(e).__name__}: {str(e)[:300]}", sa)
    return _finish(ev, out_path, sa)


def _finish(ev: dict, out_path: Optional[str], sa: str) -> dict:
    ev["finished_at"] = _dt.datetime.now(_dt.timezone.utc).isoformat()
    ev["summary"] = {k: c.get("label") for k, c in ev["cases"].items()}
    ev = redact(ev, sa)
    assert sa not in json.dumps(ev), "raw service-account e-mail must never reach evidence"
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
        print(json.dumps({"summary": o["summary"], "preflight": o["preflight"], "teardown": o["teardown"]}, indent=1, default=str))
