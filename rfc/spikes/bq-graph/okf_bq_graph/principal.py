"""Requester brokers for the connected chain (second principal, 2026-09-06 Slice A: hermetic).

The chain never holds a credential. It asks a broker for the graph-leg clients under the requester, the environment
for the receipt subprocess, a pre-execution authorization probe under the requester's own credential, the policy
transitions a case needs (grant, hide, revoke) and the identity binding of the submitted jobs. Two brokers share that
contract:

* `HermeticBroker` (this slice, exercised): a policy-emulating broker over the compiled projection. The restricted
  principal is a label, not IAM: what it can see is decided by a mutable policy (dataset grant, hidden concept rows in
  the `_rls` fixture shape, read on the SDK fixture tables). It submits no BigQuery job and proves nothing about the
  platform; it proves that the chain's stages, refusals and acceptance rules behave as designed against enforced
  denials, so a live pass can be judged against the same record shape.
* `RestrictedBroker` (Slice B, 2026-09-07: exercised live): IAM impersonation of the receipt spike's restricted service
  account through authz.py's `impersonated_client` (the receipt broker pattern, copied not imported) for the graph leg,
  an `impersonated_service_account` credential file for the SDK subprocess (run.py has no impersonation flag and is
  not edited), dataset-level reader grants through authz.py's `set_dataset_reader`, the SA added to the `_rls` fixture's
  hidden-intermediate row access policies for a case that runs on it (authz.py's `set_rls`: dataset READER alone leaves a
  non-grantee reading zero rows, which is an outage, not enforcement), and a dry-run probe per dependency table as the
  pre-execution authorization check (the SDK's own `probe_sources` shape).

Evidence hygiene: brokers describe themselves by the SA alias only; the raw e-mail stays in memory and chain.py's
`redact` masks every e-mail before anything is written.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import shutil
import stat
import tempfile
import time
from typing import Any, Callable, Optional

from . import DATASET, LOCATION, PROJECT
from .authz import HIDDEN, SA_ALIAS, RLS_DS, restricted_sa
from .oracle import Graph

ALLOWED, DENIED, UNKNOWN = "ALLOWED", "DENIED", "UNKNOWN"
RLS_TABLES = ("nodes", "edges", "section_vectors")
IAM_CREDENTIALS = "https://iamcredentials.googleapis.com/v1/projects/-/serviceAccounts/{sa}:generateAccessToken"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _norm_predicate(text: str) -> str:
    return " ".join((text or "").split())


def hide_predicates() -> dict:
    """The filter expression of each hidden-intermediate `_rls` policy, taken from `authz.rls_statements` itself so the
    live broker never carries a second copy of the fixture's shape."""
    from .authz import rls_statements
    return {t: _norm_predicate(stmt.split("FILTER USING (", 1)[1].rsplit(")", 1)[0]) for t, stmt in rls_statements(["x"]).items()}


# ----------------------------------------------------------------------------- policy (what a case asks the broker for)
def policy(dataset: str = "base", dataset_reader: bool = True, hidden: tuple = (), sdk_tables: bool = True) -> dict:
    """One case's requester policy. `dataset`: "base" (the published tables) or "rls" (the `_rls` governance fixture,
    whose row policies hide `metrics/gross-margin`); `dataset_reader`: the requester holds a reader grant on it;
    `hidden`: concept ids the policy hides (recorded for the leak check; on the live fixture the `_rls` policies decide);
    `sdk_tables`: the requester can read every dependency table of the SDK fixture publication."""
    return {"dataset": dataset, "dataset_reader": bool(dataset_reader), "hidden": tuple(hidden), "sdk_tables": bool(sdk_tables)}


REVOKED = {"dataset_reader": False, "sdk_tables": False}


def filtered_projection(projection: dict, hidden: tuple | list | set) -> dict:
    """The projection as a principal under the `_rls` hidden-intermediate policy sees it: rows of every hidden concept
    and its sections are gone, and so is every edge touching them (the three `_rls` policies of authz.py)."""
    hid = tuple(hidden)
    if not hid:
        return projection

    def gone(n: dict) -> bool:
        lid = n.get("local_id") or ""
        return any(lid == h or lid.startswith(h + "#") for h in hid)

    dropped = {n["node_id"] for n in projection["nodes"] if gone(n)}
    return dict(projection, nodes=[n for n in projection["nodes"] if n["node_id"] not in dropped],
                edges=[e for e in projection["edges"] if e["src_id"] not in dropped and e["dst_id"] not in dropped])


class PolicyGraph:
    """Oracle graph that answers as the restricted principal under the broker's CURRENT policy: a revoked dataset grant
    denies every call (the relational engine's Forbidden), hidden rows are filtered before traversal, and `visible`
    answers the cached-replay re-check the same way. Rebuilt lazily whenever the policy changes, so a replay after a
    revocation sees the revocation."""

    def __init__(self, projection: dict, state: dict):
        self._projection, self._state = projection, state
        self._key: Optional[tuple] = None
        self._graph: Optional[Graph] = None
        # the scope the oracle engine checks a request against (retrieve._retrieve_oracle refuses any other publication)
        self.bundle_id, self.publication_id = projection["bundle_id"], projection["publication_id"]

    def sanctioned_sql(self, comp_nid: str) -> Optional[dict]:
        """The Computation section under the CURRENT policy: a revoked grant or a hidden section discloses nothing."""
        if not self._state["dataset_reader"]:
            return None
        return self._current().sanctioned_sql(comp_nid)

    def _current(self) -> Graph:
        key = tuple(sorted(self._state["hidden"]))
        if self._graph is None or key != self._key:
            self._graph, self._key = Graph(filtered_projection(self._projection, key)), key
        return self._graph

    def governed(self, local: str, as_of: str) -> dict:
        if not self._state["dataset_reader"]:
            return {"status": "DENIED", "concept": local}
        return self._current().governed(local, as_of)

    def visible(self, node_ids: list[str] | tuple, edge_ids: list[str] | tuple = ()) -> bool:
        if not self._state["dataset_reader"]:
            return False
        return self._current().visible(node_ids, edge_ids)


# ----------------------------------------------------------------------------- hermetic broker (exercised in this slice)
class HermeticBroker:
    """Policy-emulating broker over the compiled projection (no cloud, no IAM). Every transition is journaled so the
    evidence shows what the emulation did and when; `describe()` says so in the record."""
    mode = "restricted-sa"
    hermetic = True

    def __init__(self, projection: dict, sa_email: Optional[str] = None):
        self.projection = projection
        self.email = sa_email or restricted_sa()
        self.principal = SA_ALIAS
        self.state: dict = dict(policy())
        self.journal: list[dict] = []
        self.receipt_launches = 0

    def describe(self) -> dict:
        return {"kind": "hermetic-policy-broker", "iam": False, "principal": self.principal,
                "note": "emulated policy over the compiled projection (dataset grant, hidden rows in the `_rls` shape, SDK fixture "
                        "table reads); the principal is a label, no BigQuery job is submitted, nothing here is platform enforcement"}

    def _log(self, event: str, **kw: Any) -> dict:
        entry = {"at": _now(), "event": event, **kw}
        self.journal.append(entry)
        return entry

    def apply(self, pol: dict) -> dict:
        self.state.update(dataset=pol["dataset"], dataset_reader=pol["dataset_reader"], hidden=tuple(pol["hidden"]), sdk_tables=pol["sdk_tables"])
        return self._log("apply", policy=dict(self.state, hidden=list(self.state["hidden"])), observed=True)

    def grant(self) -> dict:
        return self.apply(policy())

    def revoke(self) -> dict:
        """The revocation transition: the requester loses its dataset grant AND its read on the SDK fixture tables. The
        emulation observes its own state change; a live broker must observe the platform (probe denied)."""
        self.state.update(REVOKED)
        return self._log("revoke", policy=dict(self.state, hidden=list(self.state["hidden"])), observed=True)

    def graph_clients(self) -> dict:
        """Fresh per call: a case-private cache (the replay case replays against its own entry)."""
        return {"engine": "oracle", "graph": PolicyGraph(self.projection, self.state), "projection": self.projection,
                "cache": {}, "ds": self.state["dataset"]}

    def receipt_env(self) -> dict:
        """The SDK's SYNTHETIC world runs under its own fixed emulated principal; nothing to inject."""
        self.receipt_launches += 1
        return {}

    def authorize(self, dependencies: list[str]) -> dict:
        ok = bool(self.state["sdk_tables"])
        tables = [{"table": t, "status": ALLOWED if ok else DENIED} for t in dependencies]
        return {"status": ALLOWED if ok and tables else (DENIED if tables else UNKNOWN), "tables": tables,
                "denied": 0 if ok else len(tables), "checked_by": "hermetic policy broker (emulated; no dry run, no job)", "at": _now()}

    def identity(self, graph_job_ids: list[str], receipt_jobs: list[dict]) -> dict:
        return {"status": "NOT_APPLICABLE", "expected": self.principal,
                "reason": "hermetic mode: oracle graph + SDK SYNTHETIC emulation submit no BigQuery jobs; the emulated principal is a "
                          "policy label, not an IAM identity"}

    def teardown(self) -> dict:
        self.state.update(policy())
        return {"status": "NOT_NEEDED", "reason": "hermetic policy broker holds no grant"}


# ----------------------------------------------------------------------------- live broker (wired; Slice B exercises it)
def impersonated_credential_file(sa_email: str, source_path: Optional[str] = None, directory: Optional[str] = None) -> str:
    """Write an `impersonated_service_account` ADC file for the SDK subprocess (google-auth reads it through
    GOOGLE_APPLICATION_CREDENTIALS; run.py stays unedited). The file embeds the operator's ADC as
    `source_credentials`, so it lives in a private 0700 directory the broker removes in `teardown`."""
    src = source_path or os.environ.get("GOOGLE_APPLICATION_CREDENTIALS") or os.path.expanduser("~/.config/gcloud/application_default_credentials.json")
    with open(src, "r", encoding="utf-8") as fh:
        source = json.load(fh)
    if source.get("type") == "impersonated_service_account":
        raise RuntimeError("source ADC is already an impersonated credential: the SDK subprocess must impersonate from the operator's own ADC")
    d = directory or tempfile.mkdtemp(prefix=".okf_sa_adc_")
    os.chmod(d, stat.S_IRWXU)
    path = os.path.join(d, "adc.json")
    with open(os.open(path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, stat.S_IRUSR | stat.S_IWUSR), "w", encoding="utf-8") as fh:
        json.dump({"type": "impersonated_service_account", "service_account_impersonation_url": IAM_CREDENTIALS.format(sa=sa_email),
                   "source_credentials": source, "delegates": []}, fh)
    return path


def bound_to(client: Any, graph_job_ids: list[str], receipt_jobs: list[dict], expected_email: str) -> dict:
    """jobs.get under the OWNER: every graph-leg job (pointer lookup included) and every receipt-leg job must carry
    `user_email == expected_email`. Nothing to compare, an unreadable job or a missing identity is UNKNOWN (never
    BOUND); any job under another identity is UNBOUND."""
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
        return {"status": "UNKNOWN", "reason": f"identity missing on {len(missing)} job(s)", "jobs": emails, "jobs_compared": len(emails)}
    other = sorted({em for em in emails.values() if em != expected_email})
    return {"status": "BOUND" if not other else "UNBOUND", "expected": expected_email, "other_identities": other, "jobs": emails,
            "jobs_compared": len(emails), "graph_jobs": len(graph_job_ids), "receipt_jobs": len(receipt_ids), "checked_by": "operator jobs.get"}


class RestrictedBroker:
    """IAM impersonation of the restricted SA for both legs. Constructed lazily against real clients; every
    platform-changing step is journaled; `teardown` always removes what the broker granted."""
    mode = "restricted-sa"
    hermetic = False

    def __init__(self, engine: str, sdk_dataset: str, dependencies: Optional[list[str]] = None, sa_email: Optional[str] = None,
                 factory: Optional[Callable[[str], Any]] = None, owner: Any = None, wait_s: int = 240,
                 credential_file: Callable[..., str] = impersonated_credential_file):
        from .authz import impersonated_client
        self.engine, self.sdk_dataset = engine, sdk_dataset
        self.dependencies: list[str] = list(dependencies or [])   # the bound SDK publication's tables: known BEFORE the first grant probe
        self.original: dict[str, list] = {}                         # per touched dataset: the principal's ACL entries before this broker's first mutation
        self.email = sa_email or restricted_sa()
        self.principal = SA_ALIAS
        self.wait_s = wait_s
        self.state: dict = dict(policy())
        self.journal: list[dict] = []
        self.receipt_launches = 0
        self._credential_file = credential_file
        self._cred_dir: Optional[str] = None
        self._cred_path: Optional[str] = None
        self.granted: set[str] = set()
        self._rls_original: Optional[dict] = None   # the `_rls` policies' grantees + predicates before this broker's first mutation
        self._rls_granted = False
        if owner is None:
            from google.cloud import bigquery
            owner = bigquery.Client(project=PROJECT, location=LOCATION)
        self.owner = owner
        self.sa = (factory or impersonated_client)(self.email)

    def describe(self) -> dict:
        return {"kind": "iam-impersonation-broker", "iam": True, "principal": self.principal, "engine": self.engine,
                "graph_leg": "authz.impersonated_client (IAM generateAccessToken; jobs carry the SA user_email)",
                "receipt_leg": "SDK subprocess under an impersonated_service_account ADC file (GOOGLE_APPLICATION_CREDENTIALS)",
                "authorization_probe": "dry-run SELECT per dependency table under the impersonated client",
                "rls_grantee": "a case on the `_rls` fixture adds the SA to the three hidden-intermediate row access policies "
                               "(authz.set_rls) and observes the rows it can actually read; teardown restores the snapshot"}

    def _log(self, event: str, **kw: Any) -> dict:
        entry = {"at": _now(), "event": event, **kw}
        self.journal.append(entry)
        return entry

    # -- grants (dataset-level reader entries through authz.py; the `_rls` row policies are the authz fixture's)
    def _mine(self, ds: str) -> list:
        """The principal's current ACL entries on `ds` (the same match `authz.set_dataset_reader` uses)."""
        d = self.owner.get_dataset(f"{PROJECT}.{ds}")
        return [e for e in d.access_entries
                if e.entity_type in ("userByEmail", "iamMember") and (e.entity_id or "").replace("serviceAccount:", "") == self.email]

    def _reader(self, ds: str, grant: bool) -> None:
        """Grant: only when the principal holds NO entry on the dataset (an existing READER/WRITER/OWNER already reads and
        is never downgraded). Revoke: removes the principal's entries, pre-existing ones included (a revocation case must
        observe the denial), and `teardown` restores the snapshot taken before this broker's first mutation."""
        from .authz import set_dataset_reader
        if ds not in self.original:
            self.original[ds] = list(self._mine(ds))
        mine = self._mine(ds)
        if grant:
            if mine:
                self._log("grant_preexisting", ds=ds, roles=sorted({e.role or "" for e in mine}), note="left untouched; not this broker's to change")
                return
            set_dataset_reader(self.owner, ds, self.email, True)
            self.granted.add(ds)
        else:
            if mine:
                set_dataset_reader(self.owner, ds, self.email, False)
            self.granted.discard(ds)

    # -- `_rls` row access policies (dataset READER alone leaves a non-grantee reading zero rows: RLS decides the rows)
    def _rls_state(self) -> dict:
        """Grantees and filter predicate of each `_rls` row access policy, read back from the service under the owner
        (REST rowAccessPolicies.list + getIamPolicy, the shape `authz.rls_grantees` uses)."""
        api = self.owner._connection.api_request
        state: dict = {}
        for t in RLS_TABLES:
            base = f"/projects/{PROJECT}/datasets/{RLS_DS}/tables/{t}/rowAccessPolicies"
            pols = api(method="GET", path=base).get("rowAccessPolicies", [])
            if len(pols) != 1:
                raise RuntimeError(f"{RLS_DS}.{t} carries {len(pols)} row access policies: the governance fixture is exactly one per table")
            pid = pols[0]["rowAccessPolicyReference"]["policyId"]
            members = [m for b in api(method="POST", path=f"{base}/{pid}:getIamPolicy", data={}).get("bindings", []) for m in b.get("members", [])]
            state[t] = {"policy_id": pid, "grantees": sorted(set(members)), "predicate": _norm_predicate(pols[0].get("filterPredicate") or "")}
        return state

    def _rls_grantee(self, want: bool) -> None:
        """Add or remove the SA from the three `_rls` policies. The first call snapshots them and refuses to touch a
        fixture that is not the hidden-intermediate shape (a case graded against unknown policies proves nothing);
        `want=False` before any mutation is a no-op, so a broker that never ran an `_rls` case changes nothing."""
        from .authz import set_rls
        if self._rls_original is None:
            if not want:
                return
            snap = self._rls_state()
            want_pred = hide_predicates()
            wrong = sorted(t for t in RLS_TABLES if snap[t]["predicate"] != want_pred[t])
            if wrong:
                raise RuntimeError(f"`{RLS_DS}` row access policies are not the hidden-intermediate fixture shape on {wrong}: "
                                   "the broker will not overwrite policies it cannot restore")
            if snap["nodes"]["grantees"] != snap["edges"]["grantees"]:
                raise RuntimeError("`_rls` nodes and edges policies carry different grantee lists: the broker's restore assumes the fixture's shared list")
            self._rls_original = snap
        if want == self._rls_granted:
            return
        member = f"serviceAccount:{self.email}"
        base_ne = set(self._rls_original["nodes"]["grantees"])
        base_v = set(self._rls_original["section_vectors"]["grantees"])
        ne = sorted(base_ne | {member} if want else base_ne - {member})
        vec = sorted(base_v | {member} if want else base_v - {member})
        jobs = set_rls(self.owner, ne, vector_grantees=vec, hide=True)
        self._rls_granted = want
        self._log("rls_policies", sa_grantee=want, ds=RLS_DS, jobs={t: jobs.get(t) for t in RLS_TABLES},
                  note="hidden-intermediate policies re-issued with the SA added to / removed from the fixture's grantee list")

    def _rls_rows(self) -> dict:
        """What the requester actually reads on the `_rls` fixture (a real query under the impersonated client, not a
        dry run: a dry run passes on dataset READER alone and never observes the row policy). ALLOWED only when rows are
        visible AND the hidden intermediate is gone; a non-grantee reads zero rows, which is DENIED here."""
        from google.api_core import exceptions as gexc
        from google.cloud import bigquery
        q = (f"SELECT COUNT(*) AS visible, COUNTIF(local_id = '{HIDDEN}' OR STARTS_WITH(local_id, '{HIDDEN}#')) AS hidden "
             f"FROM `{PROJECT}.{RLS_DS}.nodes`")
        cfg = bigquery.QueryJobConfig(use_query_cache=False, labels={"okf_spike": "bq_graph_20260905", "stage": "rls_rows"})
        try:
            row = dict(list(self.sa.query(q, job_config=cfg, location=LOCATION).result())[0])
        except (gexc.Forbidden, gexc.Unauthorized, gexc.NotFound) as e:
            return {"status": DENIED, "error_class": type(e).__name__}
        except Exception as e:  # noqa: BLE001 - not a platform decision: unknown, never allowed
            return {"status": UNKNOWN, "error_class": type(e).__name__}
        return {"status": ALLOWED if row["visible"] > 0 and row["hidden"] == 0 else DENIED,
                "visible": row["visible"], "hidden": row["hidden"]}

    def _restore(self, ds: str) -> None:
        """Put the principal's ACL entries on `ds` back to the snapshot: nothing this broker added survives, everything
        that pre-existed (whatever its role) is back."""
        d = self.owner.get_dataset(f"{PROJECT}.{ds}")
        keep = [e for e in d.access_entries
                if not (e.entity_type in ("userByEmail", "iamMember") and (e.entity_id or "").replace("serviceAccount:", "") == self.email)]
        d.access_entries = keep + list(self.original[ds])
        self.owner.update_dataset(d, ["access_entries"])

    def _graph_ds(self) -> str:
        return RLS_DS if self.state["dataset"] == "rls" else DATASET

    def _wait(self, fn: Callable[[], dict], want: str) -> tuple[bool, dict, int]:
        t0 = time.monotonic()
        while True:
            obs = fn()
            if obs.get("status") == want or time.monotonic() - t0 >= self.wait_s:
                return obs.get("status") == want, obs, int(time.monotonic() - t0)
            time.sleep(10)

    def apply(self, pol: dict) -> dict:
        """Bring the platform to the case's policy and wait until the requester observes it: reader grants on the graph
        dataset and the SDK fixture dataset are added or removed, then probed under the impersonated client."""
        self.state.update(dataset=pol["dataset"], dataset_reader=pol["dataset_reader"], hidden=tuple(pol["hidden"]), sdk_tables=pol["sdk_tables"])
        rls = self.state["dataset"] == "rls" and pol["dataset_reader"]
        self._reader(self._graph_ds(), pol["dataset_reader"])
        self._reader(self.sdk_dataset, pol["sdk_tables"])
        self._rls_grantee(rls)
        g_ok, g_obs, g_s = self._wait(lambda: self._probe_table(f"{PROJECT}.{self._graph_ds()}.nodes"), ALLOWED if pol["dataset_reader"] else DENIED)
        s_ok, s_obs, s_s = self._wait(lambda: self.authorize(self.dependencies), ALLOWED if pol["sdk_tables"] else DENIED)
        # a `_rls` case needs the row policy in force for the requester too: dataset READER alone reads zero rows
        r_ok, r_obs, r_s = self._wait(self._rls_rows, ALLOWED) if rls else (True, {}, 0)
        entry = self._log("apply", policy=dict(self.state, hidden=list(self.state["hidden"])), observed=g_ok and s_ok and r_ok,
                          graph={"waited_s": g_s, "status": g_obs.get("status")}, sdk={"waited_s": s_s, "status": s_obs.get("status")},
                          rls=({"waited_s": r_s, **r_obs} if rls else {"status": "NOT_APPLICABLE", "reason": "case does not use the `_rls` fixture"}))
        if not (g_ok and s_ok and r_ok):
            raise RuntimeError(f"policy did not propagate within {self.wait_s}s: graph={g_obs.get('status')} sdk={s_obs.get('status')} "
                               f"rls={r_obs.get('status') if rls else 'NOT_APPLICABLE'}")
        return entry

    def grant(self) -> dict:
        return self.apply(policy())

    def revoke(self) -> dict:
        self.state.update(REVOKED)
        self._reader(self._graph_ds(), False)
        self._reader(self.sdk_dataset, False)
        self._rls_grantee(False)
        g_ok, g_obs, g_s = self._wait(lambda: self._probe_table(f"{PROJECT}.{self._graph_ds()}.nodes"), DENIED)
        s_ok, s_obs, s_s = self._wait(lambda: self.authorize(self.dependencies), DENIED)
        return self._log("revoke", policy=dict(self.state, hidden=list(self.state["hidden"])), observed=g_ok and s_ok,
                         graph={"waited_s": g_s, "status": g_obs.get("status")}, sdk={"waited_s": s_s, "status": s_obs.get("status")})


    # -- clients / env / probes
    def graph_clients(self) -> dict:
        return {"engine": self.engine, "bq": self.sa, "ds": self._graph_ds(), "cache": {}}

    def receipt_env(self) -> dict:
        if self._cred_path is None:
            self._cred_dir = tempfile.mkdtemp(prefix=".okf_sa_adc_")
            self._cred_path = self._credential_file(self.email, directory=self._cred_dir)
        self.receipt_launches += 1
        return {"GOOGLE_APPLICATION_CREDENTIALS": self._cred_path}

    def _probe_table(self, table: str) -> dict:
        """Dry-run read of one table under the impersonated client: no job, no bytes, but the platform's own access
        decision (the SDK's `probe_sources` shape)."""
        from google.api_core import exceptions as gexc
        from google.cloud import bigquery
        try:
            self.sa.query(f"SELECT 1 FROM `{table}` WHERE FALSE", job_config=bigquery.QueryJobConfig(dry_run=True, use_query_cache=False), location=LOCATION)
            return {"table": table, "status": ALLOWED}
        except (gexc.Forbidden, gexc.Unauthorized, gexc.NotFound) as e:
            return {"table": table, "status": DENIED, "error_class": type(e).__name__}
        except Exception as e:  # noqa: BLE001 - not a platform decision: unknown, never allowed
            return {"table": table, "status": UNKNOWN, "error_class": type(e).__name__}

    def authorize(self, dependencies: list[str]) -> dict:
        tables = [self._probe_table(t) for t in dependencies]
        statuses = {t["status"] for t in tables}
        status = UNKNOWN if not tables or UNKNOWN in statuses else (DENIED if DENIED in statuses else ALLOWED)
        return {"status": status, "tables": tables, "denied": sum(t["status"] == DENIED for t in tables),
                "checked_by": "dry-run SELECT per dependency table under the impersonated client", "at": _now()}

    def identity(self, graph_job_ids: list[str], receipt_jobs: list[dict]) -> dict:
        return bound_to(self.owner, graph_job_ids, receipt_jobs, self.email)

    def teardown(self) -> dict:
        """Restore every dataset this broker touched to the ACL snapshot taken before its first mutation (grants it added
        are gone, pre-existing entries are back with their original role) and read each one back; remove the credential
        file. Each step is attempted independently; VERIFIED needs at least one step, every step ok and every read-back
        equal to the snapshot; nothing touched is NOT_NEEDED, never VERIFIED."""
        td: dict = {"steps": {}, "datasets": {}}
        for ds in sorted(self.original):
            try:
                self._restore(ds); td["steps"][f"restore_{ds}"] = {"ok": True}
            except Exception as e:  # noqa: BLE001
                td["steps"][f"restore_{ds}"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
            try:
                want = sorted((e.role or "", e.entity_type or "") for e in self.original[ds])
                have = sorted((e.role or "", e.entity_type or "") for e in self._mine(ds))
                td["datasets"][ds] = {"original_roles": [r for r, _ in want], "roles_after": [r for r, _ in have], "added_by_broker": ds in self.granted}
                td["steps"][f"readback_{ds}"] = {"ok": want == have}
            except Exception as e:  # noqa: BLE001
                td["steps"][f"readback_{ds}"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        self.granted.clear()
        if self._rls_original is not None:
            from .authz import set_rls
            try:
                set_rls(self.owner, self._rls_original["nodes"]["grantees"],
                        vector_grantees=self._rls_original["section_vectors"]["grantees"], hide=True, strict=True)
                self._rls_granted = False
                td["steps"]["restore_rls_policies"] = {"ok": True}
            except Exception as e:  # noqa: BLE001
                td["steps"]["restore_rls_policies"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
            try:
                after = self._rls_state()
                member = f"serviceAccount:{self.email}"
                same = all(after[t]["grantees"] == self._rls_original[t]["grantees"]
                           and after[t]["predicate"] == self._rls_original[t]["predicate"] for t in RLS_TABLES)
                td["rls"] = {"tables": len(RLS_TABLES), "restored_to_snapshot": same,
                             "sa_in_grantees_after": any(member in after[t]["grantees"] for t in RLS_TABLES),
                             "grantees_after": {t: len(after[t]["grantees"]) for t in RLS_TABLES}}
                td["steps"]["readback_rls_policies"] = {"ok": same and not td["rls"]["sa_in_grantees_after"]}
            except Exception as e:  # noqa: BLE001
                td["steps"]["readback_rls_policies"] = {"ok": False, "error": f"{type(e).__name__}: {str(e)[:200]}"}
        if self._cred_dir:
            shutil.rmtree(self._cred_dir, ignore_errors=True)
            td["steps"]["remove_credential_file"] = {"ok": not os.path.exists(self._cred_dir)}
        if not td["steps"]:
            td["status"] = "NOT_NEEDED"; td["reason"] = "no dataset or row access policy touched and no credential file written"
        else:
            td["status"] = "VERIFIED" if all(s["ok"] for s in td["steps"].values()) else "UNVERIFIED"
        return td
