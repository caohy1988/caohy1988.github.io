"""Connected end-to-end run (2026-09-14): the RFC's still-open bar in one invocation.

    one requester (sa:okf-receipt-restricted) x one run_id x one engine:
    Catalog discovery (the requester's own Dataplex read) -> pinned publication -> trusted source -> governed retrieval
    -> payload guard -> bind -> authorization (requester) -> synthetic fact read-back against the selected digest
    -> caller-delegated computation (SDK receipt CLI under the requester) -> result-bound receipt -> enforcing consumer,
    with access and revocation checks in the same run.

Five cases, in this order (docs/spec-connected-e2e.md):

* `connected-approved`            everything granted: RELEASED on VERIFIED.
* `connected-sql-substitution`    same Catalog-seeded path; the SDK's executed-SQL swap is REJECTED -> REFUSED.
* `connected-denied-intermediate` row policy hides the intermediate concept on the `_rls` copy of the pinned
                                  publication; injected legacy seed (labelled, not a Catalog discovery); no path -> REFUSED.
* `connected-unauthorized-output` Catalog-seeded path binds, but the requester cannot read the computation's tables:
                                  authorization DENIED before execution -> REFUSED.
* `connected-revocation`          control observed ALLOWED; Catalog, graph and fact access revoked and observed DENIED;
                                  a fresh request is refused at Catalog discovery; a bypass with the retained pin is
                                  refused at publication, retrieval and authorization; the stored approved receipt is
                                  re-decided REFUSED; nothing executes after revocation.

Modes. `--live` touches test-project-0728-467323: live Dataplex, BigQuery, IAM and the SDK receipt CLI with `--live`,
relational `fallback` engine (not BigQuery Graph), synthetic Acme data. `--hermetic` runs the same stages against the
policy-emulating broker, the oracle engine, a policy-gated retained store and Catalog reader, and the SDK's SYNTHETIC
emulation: it proves the harness, not the platform.

Evidence: `evidence/connected-e2e/<run_id>/` (create-or-fail), `connected_<mode>.json` inside it and atomically at
`evidence/connected-e2e/connected_<mode>.json`. Published copies carry the SA alias only, no e-mail, and mask the pinned
publication's local identifiers as `<id:sha256[:8]>` (authz.sanitize_ids); judges run on the unmasked payloads.
"""
from __future__ import annotations

import argparse
import copy
import datetime as _dt
import json
import os
import secrets
import subprocess
import sys
import time
from pathlib import Path
from typing import Any, Callable, Optional

from . import BUNDLE_ID, DATASET, LOCATION, PROJECT, SOURCE_PIN
from . import chain as CH
from . import fact_content
from .authz import FIXTURE_IDS, HIDDEN, RLS_DS, SA_ALIAS, id_token, leaks, redact, sanitize_ids
from .catalog import CatalogConfig, CatalogRefusal, MockReader, Response, read_seed
from .catalog_access import ALLOWED, DENIED, UNKNOWN, CatalogAccess, observe_entry
from .journal import Journal
from .principal import REVOKED, HermeticBroker, policy as _policy
from .publication import ProjectionStore, resolve_publication, trusted_source, verify_payload
from .retrieve import retrieve

RUNNER_VERSION = "okf_bq_graph.connected/0.1.0"
ROOT = Path(__file__).resolve().parents[1]
OUT_DIR = ROOT / "evidence" / "connected-e2e"
FACTS_DIR = ROOT / "fixtures" / "facts"
APPROVED, SUBST, DENIED_INT, UNAUTH, REVOKE = CASES = (
    "connected-approved", "connected-sql-substitution", "connected-denied-intermediate",
    "connected-unauthorized-output", "connected-revocation")
EXPECTED = {APPROVED: "RELEASED", SUBST: "REFUSED", DENIED_INT: "REFUSED", UNAUTH: "REFUSED", REVOKE: "REFUSED"}
LABELS = {
    "data": "synthetic (invented Acme fixture; no customer data)",
    "apis": "live GCP (Dataplex Catalog, BigQuery, IAM) in --live; emulated in --hermetic",
    "engine": "relational fallback on the published tables (not BigQuery Graph / GQL)",
    "requester": "restricted service account through IAM impersonation, on every execution leg including the Catalog read",
    "catalog_access": "the harness grants the requester catalogViewer on the demo entry group for the run and removes it for revocation",
    "receipt": "the SDK example's own verifier with a requester-held key; no independent attester",
    "denied_intermediate_seed": "injected legacy fixture seed on the `_rls` governance copy of the pinned publication, not a Catalog discovery",
    "cache": "Catalog concept seeds disable the retrieval cache: revocation is shown on a fresh request, a retained-pin bypass and the stored receipt, not on a cached replay",
    "sample": "n = 1 run; no latency or cost benchmark",
}
VERDICT_RULE = ("E2E_CONNECTED only when provenance holds before any case, every case is MET (reached its stage with its "
                "specific evidence), live identity is BOUND over every job the run submitted, no journaled job is unresolved, "
                "and both the Catalog IAM restore and the requester broker teardown are VERIFIED; E2E_BROKEN when a reached stage "
                "contradicts its expectation or a job ran as an unexpected identity; E2E_INCOMPLETE otherwise")


def _now() -> _dt.datetime:
    return _dt.datetime.now(_dt.timezone.utc)


def _err(e: BaseException) -> dict:
    return {"status": "ERROR", "error": f"{type(e).__name__}: {str(e)[:300]}"}


def selected_fact_version() -> dict:
    return json.loads((ROOT / "fixtures" / "sql_baseline.json").read_text(encoding="utf-8"))["facts"]["selected_version"]


def vendored_manifest() -> dict:
    return json.loads((FACTS_DIR / "content.json").read_text(encoding="utf-8"))


# ----------------------------------------------------------------------------- fact read-back (secondary bar)
_BQ_TYPES = {"INTEGER": "INT64", "INT64": "INT64", "NUMERIC": "NUMERIC", "STRING": "STRING", "TIMESTAMP": "TIMESTAMP", "DATE": "DATE"}


def cook_value(field: dict, value: Any) -> Any:
    """A BigQuery client value in the `okf-fact-content/1` canonical form fact_content derives from the SQL literals."""
    if value is None:
        return None
    if field["type"] == "TIMESTAMP" and hasattr(value, "isoformat"):
        value = value.isoformat()
    elif field["type"] == "DATE" and hasattr(value, "isoformat"):
        value = value.isoformat()
    elif field["type"] in ("NUMERIC", "INT64"):
        value = str(value)
    return fact_content._cook(field, value)


def manifest_from_rows(tables: dict[str, tuple[list[dict], list[dict]]]) -> dict:
    """{table: (schema fields [{name, type, mode}], rows [dict])} -> canonical manifest (rows sorted like fact_content)."""
    out: dict[str, dict] = {}
    for name, (schema, rows) in tables.items():
        fields = [{"name": f["name"], "type": _BQ_TYPES.get(f["type"], f["type"]), "mode": f.get("mode") or "NULLABLE"} for f in schema]
        cooked = [[cook_value(f, r.get(f["name"])) for f in fields] for r in rows]
        cooked.sort(key=fact_content.encoded)
        out[name] = {"schema": fields, "rows": cooked}
    return {"format": fact_content.FORMAT, "tables": dict(sorted(out.items()))}


def admit_facts(readback: Callable[[], dict], today: _dt.date) -> dict:
    """Read the synthetic facts back under the requester and admit them only when they hash to the selected digest."""
    from .consumer_run import admit_live
    version = selected_fact_version()
    try:
        manifest = readback()
    except Exception as e:  # noqa: BLE001 - a denied or failed read decides nothing: not admitted
        from google.api_core import exceptions as gexc
        denied = isinstance(e, (PermissionError, gexc.Forbidden, gexc.Unauthorized))
        return {"status": "DENIED" if denied else "ERROR", "error": f"{type(e).__name__}: {str(e)[:240]}"}
    res = admit_live(version, manifest, today, today)
    res["tables"] = fact_content.row_counts(manifest)
    res["selected_content_digest"] = version["content_manifest_sha256"]
    return res


# ----------------------------------------------------------------------------- environments
class HermeticCatalogAccess:
    """Policy emulation of the Catalog grant: a flag, observed through the same reader contract as the live one."""

    def __init__(self) -> None:
        self.granted = False
        self.mutated = False
        self.events: list[dict] = []

    def grant(self) -> dict:
        self.granted, self.mutated = True, True
        self.events.append({"event": "grant", "at": _now().isoformat()})
        return {"status": "GRANTED", "role": "roles/dataplex.catalogViewer (emulated)"}

    def revoke(self) -> dict:
        self.granted = False
        self.events.append({"event": "revoke", "at": _now().isoformat()})
        return {"status": "REVOKED", "role": "roles/dataplex.catalogViewer (emulated)"}

    def restore(self) -> dict:
        self.granted = False
        return {"status": "VERIFIED" if self.mutated else "NOT_NEEDED", "steps": {"emulated": {"ok": True}}}

    def record(self, redact: Callable[[Any], Any] = lambda x: x) -> dict:
        return {"kind": "hermetic-catalog-policy", "events": self.events}


class PolicyCatalogReader(MockReader):
    """Injected Catalog responses (fixtures/catalog_responses.json through the real parser) answered as 403 while the
    requester holds no Catalog access. Seeds read through it are `catalog-mock`, never a live Catalog read."""

    DENIED_BODY = b'{"error":{"code":403,"message":"Permission denied (hermetic policy)","status":"PERMISSION_DENIED"}}'

    def __init__(self, pages: list, entries: dict, allowed: Callable[[], bool]):
        super().__init__(pages, entries)
        self._allowed = allowed

    def list_entries(self, group, page_size, page_token):
        if not self._allowed():
            self.calls.append(("list-denied", group, page_size, page_token))
            return Response(403, self.DENIED_BODY)
        return super().list_entries(group, page_size, page_token)

    def get_entry(self, name, view):
        if not self._allowed():
            self.calls.append(("get-denied", name, view))
            return Response(403, self.DENIED_BODY)
        return super().get_entry(name, view)


class PolicyStore(ProjectionStore):
    """Hermetic retained store that refuses every read while the requester holds no dataset grant (BigQuery's 403)."""

    def __init__(self, journal: Any, broker: Any, dataset: str):
        super().__init__(journal, dataset)
        self.broker = broker

    def _gate(self) -> None:
        if not self.broker.state["dataset_reader"] or self.broker.state["dataset"] != "base":
            raise PermissionError("403 Access Denied: requester holds no read on the retained store (hermetic policy)")

    def publication(self, bundle, pub):
        self._gate(); return super().publication(bundle, pub)

    def seed(self, node_id, bundle, pub):
        self._gate(); return super().seed(node_id, bundle, pub)

    def head(self, bundle):
        self._gate(); return super().head(bundle)

    def declaration(self, node_id, pub):
        self._gate(); return super().declaration(node_id, pub)

    def rows(self, bundle, pub):
        self._gate(); return super().rows(bundle, pub)


class HermeticEnv:
    live, engine, mode = False, "oracle", "hermetic"

    def __init__(self, projection: dict, sdk_root: str, cfg: CatalogConfig, runner: Callable = subprocess.run,
                 broker: Any = None, catalog: Any = None, facts: Optional[Callable[[], dict]] = None):
        self.projection, self.sdk_root, self.cfg, self.runner = projection, sdk_root, cfg, runner
        self.broker = broker or HermeticBroker(projection)
        self.access = catalog or HermeticCatalogAccess()
        body = json.loads((ROOT / "fixtures" / "catalog_responses.json").read_text(encoding="utf-8"))
        self.reader = PolicyCatalogReader(body["pages"], body["entries"], allowed=lambda: self.access.granted)
        self._facts = facts or vendored_manifest
        self.receipt_launches = 0

    def describe(self) -> dict:
        return {"kind": "hermetic", "broker": self.broker.describe(), "catalog": "policy-gated injected responses (catalog-mock)",
                "store": "policy-gated compiled projection", "engine": "oracle (in-process reference)", "sdk": "SYNTHETIC emulation"}

    def catalog_reader(self) -> Any:
        return self.reader

    def catalog_grant(self) -> dict:
        return self.access.grant()

    def catalog_revoke(self) -> dict:
        return self.access.revoke()

    def catalog_observe(self) -> dict:
        return observe_entry(self.reader, self.cfg.entry, self.cfg.aspect_key)

    def catalog_wait(self, want: str) -> dict:
        obs = self.catalog_observe()
        return {"want": want, "observed": obs["status"] == want, "status": obs["status"], "http_status": obs.get("http_status"), "waited_s": 0, "polls": 1}

    def caller(self) -> dict:
        return {"status": "NOT_APPLICABLE", "reason": "hermetic: the principal is a policy label, no token exists"}

    def requester_apply(self, pol: dict) -> dict:
        return self.broker.apply(pol)

    def requester_revoke(self) -> dict:
        return self.broker.revoke()

    def store(self, journal: Journal) -> Any:
        s = PolicyStore(journal, self.broker, dataset=f"hermetic-store ({self.cfg.runtime_dataset} policy-gated)")
        s.add(self.projection)
        s.set_head(self.projection["bundle_id"], self.projection["publication_id"])
        return s

    def graph_clients(self, journal: Journal) -> dict:
        return dict(self.broker.graph_clients(), cache=None)

    def graph_probe(self) -> dict:
        return {"status": ALLOWED if self.broker.state["dataset_reader"] else DENIED, "checked_by": "hermetic policy"}

    def authorize(self, deps: list[str]) -> dict:
        return self.broker.authorize(deps)

    def read_facts(self, journal: Journal, sdk_pub: dict) -> dict:
        if not self.broker.state["sdk_tables"]:
            raise PermissionError("403 Access Denied: requester holds no read on the SDK fixture tables (hermetic policy)")
        return copy.deepcopy(self._facts())

    def receipt(self, sdk_case: str, label: str, receipt_dir: Path) -> dict:
        self.receipt_launches += 1
        return CH.run_receipt(sdk_case, self.sdk_root, str(receipt_dir), live=False, runner=self.runner,
                              env_extra=self.broker.receipt_env(), label=label)

    def identity(self, graph_ids: list[str], receipt_jobs: list[dict]) -> dict:
        return self.broker.identity(graph_ids, receipt_jobs)

    def teardown(self) -> dict:
        return {"catalog": self.access.restore(), "broker": self.broker.teardown()}


class LiveEnv:
    live, engine, mode = True, "fallback", "live"
    CLOUD = "https://www.googleapis.com/auth/cloud-platform"
    USERINFO = "https://www.googleapis.com/auth/userinfo.email"

    def __init__(self, sdk_pub: dict, sdk_root: str, cfg: CatalogConfig, wait_s: int = 600, sdk_python: Optional[str] = None,
                 runner: Callable = subprocess.run, catalog_resources: Optional[list[str]] = None):
        import google.auth
        from google.auth import impersonated_credentials
        from google.auth.transport.requests import AuthorizedSession
        from .catalog import HttpReader
        from .principal import RestrictedBroker
        self.sdk_root, self.cfg, self.wait_s, self.sdk_python, self.runner = sdk_root, cfg, wait_s, sdk_python, runner
        self.broker = RestrictedBroker("fallback", sdk_pub["dataset"], dependencies=sdk_pub["dependencies"], wait_s=wait_s)
        source, _ = google.auth.default(scopes=[self.CLOUD])
        self._req_creds = impersonated_credentials.Credentials(source_credentials=source, target_principal=self.broker.email,
                                                               target_scopes=[self.CLOUD, self.USERINFO], lifetime=3600)
        self.reader = HttpReader(session=AuthorizedSession(self._req_creds))
        op, _ = google.auth.default(scopes=[self.CLOUD])
        self.access = CatalogAccess(catalog_resources or [cfg.group], f"serviceAccount:{self.broker.email}", AuthorizedSession(op))
        self.receipt_launches = 0

    def describe(self) -> dict:
        return {"kind": "live", "broker": self.broker.describe(), "catalog": "dataplex v1 entries.list + entries.get(view=ALL) under the "
                "requester's impersonated credential (cloud-platform + userinfo.email scopes)",
                "catalog_access": {"role": self.access.role, "resources": self.access.resources},
                "store": f"BigQueryStore on {self.cfg.runtime_dataset} under the requester", "engine": "fallback (relational, on-demand)",
                "sdk": "examples/okf_attested_computation/run.py --live under the requester's impersonated ADC file",
                "sdk_python": "OKF_SDK_PYTHON / --sdk-python" if self.sdk_python or os.environ.get("OKF_SDK_PYTHON") else "this interpreter"}

    def catalog_reader(self) -> Any:
        return self.reader

    def catalog_grant(self) -> dict:
        return self.access.grant()

    def catalog_revoke(self) -> dict:
        return self.access.revoke()

    def catalog_observe(self) -> dict:
        return self.access.observe(self.reader, self.cfg.entry, self.cfg.aspect_key)

    def catalog_wait(self, want: str) -> dict:
        return self.access.wait(want, self.reader, self.cfg.entry, self.cfg.aspect_key, self.wait_s)

    def caller(self) -> dict:
        """Whose token the Catalog session carries: Catalog attests no principal, so read tokeninfo of the session's own
        access token. Only the match is recorded; the token and the e-mail never leave memory."""
        import requests
        from google.auth.transport.requests import Request
        try:
            self._req_creds.refresh(Request())
            r = requests.get("https://oauth2.googleapis.com/tokeninfo", params={"access_token": self._req_creds.token}, timeout=10)
            email = (r.json() or {}).get("email")
        except Exception as e:  # noqa: BLE001
            return {"status": "UNKNOWN", "error": type(e).__name__}
        match = bool(email) and email == self.broker.email
        return {"status": "REQUESTER" if match else ("OTHER" if email else "UNKNOWN"), "caller_is_requester": match,
                "principal": SA_ALIAS if match else None, "http_status": r.status_code,
                "checked_by": "oauth2 tokeninfo of the Catalog session's own access token"}

    def requester_apply(self, pol: dict) -> dict:
        return self.broker.apply(pol)

    def requester_revoke(self) -> dict:
        """Every read the broker may have granted, gone: base graph dataset, `_rls` dataset, SDK fixture dataset and the
        `_rls` row-policy grantee; then wait until the requester observes the graph probe and authorization DENIED."""
        b = self.broker
        b.state.update(REVOKED)
        for ds in (DATASET, RLS_DS, b.sdk_dataset):
            b._reader(ds, False)
        b._rls_grantee(False)
        g_ok, g_obs, g_s = b._wait(lambda: b._probe_table(f"{PROJECT}.{DATASET}.nodes"), DENIED)
        s_ok, s_obs, s_s = b._wait(lambda: b.authorize(b.dependencies), DENIED)
        return b._log("revoke_all", datasets=[DATASET, RLS_DS, b.sdk_dataset], observed=g_ok and s_ok,
                      graph={"waited_s": g_s, "status": g_obs.get("status")}, sdk={"waited_s": s_s, "status": s_obs.get("status")})

    def store(self, journal: Journal) -> Any:
        from .publication import BigQueryStore
        return BigQueryStore(self.broker.sa, self.cfg.runtime_project, self.cfg.runtime_dataset, self.cfg.runtime_location, journal,
                             labels={"okf_spike": "connected_e2e"})

    def graph_clients(self, journal: Journal) -> dict:
        return dict(self.broker.graph_clients(), cache=None, journal=journal)

    def graph_probe(self) -> dict:
        return dict(self.broker._probe_table(f"{PROJECT}.{DATASET}.nodes"), checked_by="dry-run SELECT under the requester")

    def authorize(self, deps: list[str]) -> dict:
        return self.broker.authorize(deps)

    def read_facts(self, journal: Journal, sdk_pub: dict) -> dict:
        from google.cloud import bigquery
        from .publication import run_journaled
        m = sdk_pub["manifest"]
        tables: dict[str, tuple[list[dict], list[dict]]] = {}
        for name in vendored_manifest()["tables"]:
            ref = f"{m['project']}.{m['dataset']}.{name}"
            schema = [{"name": f.name, "type": f.field_type, "mode": f.mode} for f in self.broker.sa.get_table(ref).schema]
            cfg = bigquery.QueryJobConfig(use_query_cache=False, maximum_bytes_billed=10 * 1024 * 1024,
                                          labels={"okf_spike": "connected_e2e", "stage": "facts-readback"})
            rows, _job, _e = run_journaled(self.broker.sa, journal, "facts_readback", f"full read of synthetic fact table {name}",
                                           f"SELECT * FROM `{ref}`", cfg, m.get("location", LOCATION), project=m["project"],
                                           job_project=getattr(self.broker.sa, "project", None))
            tables[name] = (schema, rows)
        return manifest_from_rows(tables)

    def receipt(self, sdk_case: str, label: str, receipt_dir: Path) -> dict:
        self.receipt_launches += 1
        return CH.run_receipt(sdk_case, self.sdk_root, str(receipt_dir), live=True, runner=self.runner,
                              env_extra=self.broker.receipt_env(), label=label, python=self.sdk_python)

    def identity(self, graph_ids: list[str], receipt_jobs: list[dict]) -> dict:
        return self.broker.identity(graph_ids, receipt_jobs)

    def teardown(self) -> dict:
        out: dict[str, Any] = {}
        try:
            out["catalog"] = self.access.restore()
        except Exception as e:  # noqa: BLE001
            out["catalog"] = dict(_err(e), status="UNVERIFIED")
        try:
            out["broker"] = self.broker.teardown()
        except Exception as e:  # noqa: BLE001
            out["broker"] = dict(_err(e), status="UNVERIFIED")
        return out


# ----------------------------------------------------------------------------- consumer + acceptance
def consume_connected(bind: dict, rec: dict, authz: Optional[dict], facts: Optional[dict]) -> dict:
    """chain.consume plus the fact admission: a receipt over facts that do not hash to the selected digest is withheld."""
    c = CH.consume(bind, rec, authz, containment=rec.get("containment"))
    if facts is not None and facts.get("status") != "OK":
        reasons = list(c.get("reasons") or []) + [f"fact admission {facts.get('status')}: the read-back does not admit the selected synthetic facts"]
        return {"decision": "REFUSED", "reasons": reasons}
    return c


def _verdict(case: str, failed: list[str], not_reached: list[str]) -> dict:
    if failed:
        return {"status": "WRONG", "expected": EXPECTED.get(case), "failed": failed + not_reached}
    if not_reached:
        return {"status": "NOT_REACHED", "expected": EXPECTED.get(case), "failed": not_reached}
    return {"status": "MET", "expected": EXPECTED.get(case), "failed": []}


def _seeded_path(c: dict) -> tuple[list[str], list[str]]:
    """Catalog -> publication -> source -> retrieval -> declaration -> payload: an outage is NOT_REACHED, a reached stage
    that contradicts the pin (stale / mismatched pin, unverified source, inconsistent payload) is WRONG."""
    failed: list[str] = []
    nr: list[str] = []
    cat = c.get("catalog") or {}
    if cat.get("status") != "OK":
        nr.append(f"catalog status={cat.get('status')} http={cat.get('http_status')}")
        return failed, nr
    pub = c.get("publication") or {}
    if pub.get("status") in ("FAIL_STALE", "PIN_MISMATCH"):
        failed.append(f"publication {pub.get('status')}: {pub.get('reasons')}")
        return failed, nr
    if pub.get("status") != "OK":
        nr.append(f"publication status={pub.get('status')}")
        return failed, nr
    src = c.get("source") or {}
    if src.get("status") != "OK":
        failed.append(f"source {src.get('status')}")
        return failed, nr
    r = c.get("retrieval") or {}
    if r.get("status") != "OK" or not r.get("reached"):
        nr.append(f"retrieval status={r.get('status')} reached={r.get('reached')}")
        return failed, nr
    if (c.get("declaration") or {}).get("status") != "OK":
        nr.append(f"declaration status={(c.get('declaration') or {}).get('status')}")
        return failed, nr
    p = c.get("payload") or {}
    if p.get("status") == "INCONSISTENT":
        failed.append(f"payload INCONSISTENT: {','.join(p.get('failed') or [])}")
    elif p.get("status") != "CONSISTENT":
        nr.append(f"payload status={p.get('status')}")
    return failed, nr


def _pre_execution(c: dict, failed: list[str], nr: list[str]) -> None:
    if (c.get("bind") or {}).get("status") != "BOUND":
        failed.append(f"bind status={(c.get('bind') or {}).get('status')} (graph and SDK publication disagree)")
        return
    az = (c.get("authorization") or {}).get("status")
    if az == DENIED:
        nr.append("authorization DENIED with grants present: grant not effective, execution stage never reached")
        return
    if az != ALLOWED:
        nr.append(f"authorization status={az}")
        return
    facts = c.get("facts") or {}
    if facts.get("status") == "FACTS_DRIFTED":
        failed.append("facts FACTS_DRIFTED: the requester's read-back does not hash to the selected synthetic digest")
    elif facts.get("status") != "OK":
        nr.append(f"facts status={facts.get('status')}")
    rec = c.get("receipt") or {}
    if not failed and not nr:
        if not rec.get("invoked"):
            nr.append("receipt not invoked")
        elif rec.get("exit_code") == -1 or not rec.get("diag_present"):
            nr.append(f"receipt child did not complete: exit_code={rec.get('exit_code')} diag_present={rec.get('diag_present')}")


def accept(c: dict) -> dict:
    case = c["case"]
    decision = (c.get("consume") or {}).get("decision")
    if c.get("status") == "NOT_RUN":
        return _verdict(case, [], [c.get("reason") or "not run"])
    if case == DENIED_INT:
        v = CH.accept_restricted(dict(c, case="denied-intermediate"))
        return dict(v, expected=EXPECTED[case])
    if case == REVOKE:
        return _accept_revocation(c)
    failed, nr = _seeded_path(c)
    rec = c.get("receipt") or {}
    if case in (APPROVED, SUBST):
        if not failed and not nr:
            _pre_execution(c, failed, nr)
        if case == APPROVED:
            if decision == "RELEASED" and (failed or nr):
                failed.append("RELEASED although a stage did not hold")
            if not failed and not nr:
                if rec.get("exit_code") != 0:
                    failed.append(f"exit_code={rec.get('exit_code')} != 0")
                if decision != "RELEASED":
                    failed.append(f"consume decision={decision} != RELEASED")
        else:
            if decision != "REFUSED":
                failed.append(f"consume decision={decision}: a substitution was released")
            if not failed and not nr:
                rc, o = rec.get("receipt") or {}, rec.get("output") or {}
                if rec.get("exit_code") != 2:
                    failed.append(f"exit_code={rec.get('exit_code')} != 2 (the CLI's blocked exit)")
                for label, v in (("receipt.verdict", rc.get("verdict")), ("output.verdict", o.get("verdict"))):
                    if v != CH.REJECTED:
                        failed.append(f"{label}={v} != REJECTED")
                if rc.get("execution_match") != "MISMATCH" or o.get("execution_match") != "MISMATCH":
                    failed.append(f"execution_match={rc.get('execution_match')}/{o.get('execution_match')} != MISMATCH")
                if "sql_mismatch" not in (o.get("reason_codes") or []):
                    failed.append(f"reason_codes={o.get('reason_codes')} lack sql_mismatch")
                if rec.get("released"):
                    failed.append("CLI reported released=true on a substitution")
        return _verdict(case, failed, nr)
    if case == UNAUTH:
        if decision != "REFUSED":
            failed.append(f"consume decision={decision}: released without authorization")
        if rec.get("invoked"):
            failed.append("receipt invoked although authorization was denied")
        if not failed and not nr:
            az = c.get("authorization") or {}
            if (c.get("bind") or {}).get("status") != "BOUND":
                failed.append(f"bind status={(c.get('bind') or {}).get('status')}")
            elif az.get("status") == ALLOWED:
                failed.append("authorization ALLOWED: the missing read on the computation's tables was not enforced")
            elif az.get("status") != DENIED:
                nr.append(f"authorization status={az.get('status')}: probe did not produce a platform decision")
            elif not az.get("denied"):
                failed.append("authorization DENIED without a denied table")
            elif not any("authorization" in x for x in (c.get("consume") or {}).get("reasons", [])):
                failed.append("refusal does not name the authorization denial")
        return _verdict(case, failed, nr)
    return _verdict(case, [f"unknown case {case}"], [])


def _accept_revocation(c: dict) -> dict:
    failed: list[str] = []
    nr: list[str] = []
    if (c.get("first_release") or {}).get("decision") != "RELEASED":
        nr.append("the approved case never released: nothing to revoke from")
    ctl = c.get("control") or {}
    for surface in ("catalog", "graph", "authorization"):
        if (ctl.get(surface) or {}).get("status") != ALLOWED:
            nr.append(f"control {surface}={(ctl.get(surface) or {}).get('status')}: access was not present right before revocation")
    rev = c.get("revocation") or {}
    if not nr and not rev.get("observed"):
        nr.append(f"revocation not observed by the requester: catalog={(rev.get('catalog_wait') or {}).get('status')} "
                  f"requester={(rev.get('requester') or {}).get('observed')}")
    decision = (c.get("consume") or {}).get("decision")
    if decision != "REFUSED":
        failed.append(f"stored receipt decision={decision} after revocation")
    if c.get("receipt_invocations_after_revocation", 0) > 0:
        failed.append(f"receipt CLI launched {c.get('receipt_invocations_after_revocation')} time(s) after revocation")
    if not nr:
        fresh = c.get("fresh_request") or {}
        cat = fresh.get("catalog") or {}
        if cat.get("status") == "OK":
            failed.append("Catalog served the pin to the requester after revocation")
        elif cat.get("status") != "CATALOG_ERROR" or cat.get("http_status") != 403:
            nr.append(f"fresh Catalog request status={cat.get('status')} http={cat.get('http_status')}: not a platform denial")
        if fresh.get("downstream_ran"):
            failed.append("a stage after the refused Catalog read ran")
        bp = (c.get("bypass") or {}).get("publication") or {}
        if bp.get("status") in ("OK", "FAIL_STALE", "PIN_MISMATCH"):
            failed.append(f"retained-pin publication read status={bp.get('status')} after revocation: the store was readable")
        elif bp.get("status") != "ERROR":
            nr.append(f"retained-pin publication status={bp.get('status')}")
        br = (c.get("bypass") or {}).get("retrieval") or {}
        if br.get("status") == "OK" or br.get("disclosed_anything"):
            failed.append(f"retained-pin retrieval status={br.get('status')} disclosed content after revocation")
        elif br.get("status") != "DENIED":
            nr.append(f"retained-pin retrieval status={br.get('status')}")
        az = (c.get("authorization") or {}).get("status")
        if az == ALLOWED:
            failed.append("authorization ALLOWED after revocation")
        elif az != DENIED:
            nr.append(f"authorization status={az} after revocation")
        if decision == "REFUSED" and not any("authorization" in x for x in (c.get("consume") or {}).get("reasons", [])):
            failed.append("the stored receipt's refusal does not name the revoked authorization")
    return _verdict(REVOKE, failed, nr)


# ----------------------------------------------------------------------------- the run
def _retrieval_record(r: dict, hidden: tuple = ()) -> dict:
    return {"status": r["status"], "warnings": r.get("warnings", []), "scope": r.get("scope"),
            "concepts": [c.get("concept") for c in r.get("concepts", [])], "paths": r.get("paths", []),
            "computations": [c.get("path") for c in r.get("computations", [])], "timing": r.get("timing"),
            "hidden_id_in_full_result": [h for h in hidden if leaks(r, h)]}


def _publish(out: dict) -> dict:
    """What is written: e-mails redacted, the pinned publication's local ids masked, the home directory elided."""
    text = json.dumps(sanitize_ids(redact(out), list(FIXTURE_IDS)), default=str)
    home = os.path.expanduser("~")
    if home and home != "/":
        text = text.replace(home, "~")
    return json.loads(text)


def run_connected(env: Any, sdk_root: str, acme_root: str, out_dir: Path | str = OUT_DIR, as_of: Optional[str] = None,
                  cfg: Optional[CatalogConfig] = None, today: Optional[_dt.date] = None,
                  progress: Callable[..., None] = lambda *a, **k: None) -> dict:
    cfg = cfg or CatalogConfig()
    started = _now()
    as_of = as_of or started.strftime("%Y-%m-%dT%H:%M:%SZ")
    today = today or started.date()
    run_id = f"e2e-{started:%Y%m%dt%H%M%Sz}-{secrets.token_hex(4)}"
    run_dir = Path(out_dir) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)            # create-or-fail: this invocation owns the directory
    journal = Journal(run_dir, run_id)
    receipt_dir = run_dir / "receipt"
    out: dict[str, Any] = {"runner": RUNNER_VERSION, "run_id": run_id, "mode": env.mode, "engine": env.engine,
                           "started_at": started.isoformat(), "as_of": as_of, "labels": LABELS, "verdict_rule": VERDICT_RULE,
                           "requester": {"principal": SA_ALIAS, "environment": env.describe()},
                           "selected_cases": list(CASES), "cases": []}

    def retain_catalog(label: str) -> Callable[[str, bytes], None]:
        def keep(name: str, raw: bytes) -> None:
            try:
                body = redact(json.loads(raw.decode("utf-8")))
                data = (json.dumps(sanitize_ids(body, list(FIXTURE_IDS)), indent=1, sort_keys=True) + "\n").encode("utf-8")
            except (UnicodeDecodeError, ValueError):
                data = b""
            rec = journal.retain(f"{label}__{name}", data, subdir="catalog")
            journal.note("catalog_raw", name=f"{label}__{name}", raw_sha256=CH.sha256_hex(raw), retained_sha256=rec["sha256"],
                         note="retained copy is redacted and id-masked; raw_sha256 is the response as received")
        return keep

    # ---- S0 provenance
    progress("provenance", detail="SDK pin, clean checkout")
    try:
        sdk_pub = CH.sdk_publication(sdk_root)
    except (OSError, ValueError, KeyError) as e:
        out["sdk"] = _err(e)
        return _finish(out, env, journal, run_dir, out_dir, "provenance", None)
    out["sdk"] = {"head": sdk_pub["sdk_head"], "pin": CH.SDK_PIN, "head_matches_pin": sdk_pub["sdk_head_matches_pin"],
                  "repo_dirty": sdk_pub["sdk_repo_dirty"], "publication_id": sdk_pub["manifest"]["publication_id"],
                  "context_ref": sdk_pub["manifest"]["context_ref"], "computation_sha256": sdk_pub["computation_sha256"],
                  "computation_digest": sdk_pub["computation_digest"], "synthetic_fixture": bool(sdk_pub["manifest"].get("synthetic")),
                  "dependencies": len(sdk_pub["dependencies"])}
    prov = {"sdk_head_pin": bool(sdk_pub["sdk_head_matches_pin"]), "sdk_clean": sdk_pub["sdk_repo_dirty"] is False}
    prov["ok"] = all(prov.values())
    out["provenance"] = prov
    if not prov["ok"]:
        return _finish(out, env, journal, run_dir, out_dir, "provenance", None)
    deps = sdk_pub["dependencies"]
    trusted_cache: dict[str, dict] = {}
    state: dict[str, Any] = {"pin": None, "approved": None}

    def seeded(label: str) -> tuple[dict, dict]:
        """One Catalog-seeded path under the requester, up to bind. Returns (record, context)."""
        rec: dict[str, Any] = {}
        ctx: dict[str, Any] = {}
        try:
            seed = read_seed(env.catalog_reader(), cfg, retain=retain_catalog(label))
        except Exception as e:  # noqa: BLE001
            seed = CatalogRefusal("CATALOG_ERROR", f"reader raised {type(e).__name__}: {str(e)[:200]}", "list")
        if isinstance(seed, CatalogRefusal):
            rec["catalog"] = seed.record()
            return rec, ctx
        rec["catalog"] = dict(seed.record(), note=("fresh Dataplex list + get(view=ALL) under the requester's impersonated credential"
                                                   if seed.mode == "catalog" else "injected responses through the real parser, policy-gated (hermetic)"))
        pin = ctx["pin"] = seed.pin
        if state["pin"] is None:
            state["pin"] = pin
        rec["catalog"]["same_pin_as_first_discovery"] = pin == state["pin"]
        store = ctx["store"] = env.store(journal)
        res = resolve_publication(store, pin)
        rec["publication"] = {"status": res["status"], "publication_id": pin.publication_id, "reasons": res.get("reasons"),
                              "checks": res.get("checks"), "head": res.get("head"), "error": res.get("error")}
        if res["status"] != "OK":
            return rec, ctx
        key = f"{pin.publication_id}|{pin.source_pin}"
        if key not in trusted_cache:
            trusted_cache[key] = trusted_source(pin, acme_root)
        t = trusted_cache[key]
        rec["source"] = {k: v for k, v in t.items() if k != "projection"}
        if t["status"] != "OK":
            return rec, ctx
        clients = dict(env.graph_clients(journal), store=store)
        try:
            r = retrieve(pin.seed(seed.mode), pin.bundle_id, pin.publication_id, SA_ALIAS, as_of, clients)
        except Exception as e:  # noqa: BLE001
            rec["retrieval"] = dict(_err(e), reached=False)
            return rec, ctx
        kept = journal.retain(f"retrieval_{label}", (json.dumps(sanitize_ids(redact(r), list(FIXTURE_IDS)), indent=1, sort_keys=True, default=str) + "\n").encode("utf-8"), subdir="retrieval")
        rec["retrieval"] = dict(_retrieval_record(r), retained={"path": kept["path"], "sha256": kept["sha256"], "masked": True})
        comp = CH.pick_computation(r, CH.COMPUTATION_PATH) if r["status"] == "OK" else None
        rec["retrieval"]["reached"] = comp is not None
        if comp is None:
            return rec, ctx
        rec["computation"] = {k: comp.get(k) for k in ("concept", "path", "concept_hops", "via", "status", "runtime", "trust_tier", "sql_sha256", "runtime_verdict")}
        try:
            decl = CH.declaration(clients, comp["computation_id"], pin.publication_id)
        except Exception as e:  # noqa: BLE001
            decl = _err(e)
        rec["declaration"] = decl
        if decl.get("status") != "OK":
            return rec, ctx
        rec["payload"] = verify_payload(store, pin, t["projection"], r, comp, decl, expected_path=CH.COMPUTATION_PATH,
                                        seed_id=pin.concept_id, engine=env.engine)
        if rec["payload"]["status"] != "CONSISTENT":
            rec["bind"] = {"status": "NOT_BOUND", "reason": f"payload consistency {rec['payload']['status']}"}
            return rec, ctx
        rec["bind"] = CH.bind(comp, decl, sdk_pub, as_of, source_pin=pin.source_pin)
        return rec, ctx

    def seeded_case(label: str, sdk_case: Optional[str], pol: Optional[dict] = None) -> dict:
        c: dict[str, Any] = {"case": label, "expected": EXPECTED[label], "seed_origin": "Catalog discovery under the requester", "receipt_invocations": 0}
        if pol is not None:
            try:
                c["policy_apply"] = env.requester_apply(pol)
            except Exception as e:  # noqa: BLE001
                c["policy_apply"] = _err(e)
                c.update(catalog={"status": "NOT_RUN"}, bind={"status": "NOT_REACHED", "reason": "policy not applied"},
                         authorization={"status": "NOT_RUN"}, receipt={"invoked": False, "reason": "policy not applied"})
                c["consume"] = consume_connected(c["bind"], c["receipt"], None, None)
                c["acceptance"] = accept(c)
                return c
        progress("case", case=label, stage="catalog -> publication -> retrieval -> payload -> bind")
        rec, _ctx = seeded(label)
        c.update(rec)
        bind = c.get("bind") or {"status": "NOT_REACHED", "reason": "an upstream stage did not hold"}
        c["bind"] = bind
        facts = None
        if bind.get("status") == "BOUND":
            c["authorization"] = env.authorize(deps)
            if c["authorization"]["status"] == ALLOWED:
                progress("case", case=label, stage="facts read-back under the requester")
                facts = c["facts"] = admit_facts(lambda: env.read_facts(journal, sdk_pub), today)
                if facts.get("status") == "OK" and sdk_case:
                    progress("case", case=label, stage=f"receipt CLI ({sdk_case}) under the requester")
                    c["receipt"] = env.receipt(sdk_case, label, receipt_dir)
                    c["receipt_invocations"] = 1
                    c["receipt"]["diag"] = None if c["receipt"].get("diag") is None else "retained"
                else:
                    c["receipt"] = {"invoked": False, "reason": f"facts {facts.get('status')}: nothing was executed"}
            else:
                c["receipt"] = {"invoked": False, "reason": f"authorization {c['authorization']['status']} under the requester: nothing was executed"}
        else:
            c["authorization"] = {"status": "NOT_RUN", "reason": "nothing bound"}
            c["receipt"] = {"invoked": False, "reason": f"bind {bind.get('status')}: nothing was executed"}
        az = c["authorization"] if c["authorization"].get("status") in (ALLOWED, DENIED, UNKNOWN) else None
        c["consume"] = consume_connected(bind, c["receipt"], az, facts)
        c["acceptance"] = accept(c)
        progress("decision", case=label, decision=c["consume"]["decision"], acceptance=c["acceptance"]["status"],
                 display=c["consume"].get("display"))
        return c

    def denied_intermediate_case() -> dict:
        label = DENIED_INT
        pub = state["pin"].publication_id if state["pin"] is not None else CH.PUBLICATION_PIN
        pol = _policy(dataset="rls", hidden=(HIDDEN,))
        c: dict[str, Any] = {"case": label, "expected": EXPECTED[label], "seed_origin": "injected-fixture-seed",
                             "note": "the `_rls` governance copy of the pinned publication; the Catalog pin names the base runtime dataset, so this seed is a labelled injection, not a discovery",
                             "policy": dict(pol, hidden=list(pol["hidden"])), "hidden": [HIDDEN], "receipt_invocations": 0,
                             "publication_source": "first Catalog discovery" if state["pin"] is not None else "module pin"}
        progress("case", case=label, stage="row policy hides the intermediate; retrieval under the requester")
        try:
            c["grant"] = env.requester_apply(pol)
        except Exception as e:  # noqa: BLE001
            c["grant"] = _err(e)
            c.update(retrieval={"status": "NOT_RUN", "reached": False}, bind={"status": "NOT_REACHED", "reason": "policy_not_applied"},
                     authorization={"status": "NOT_RUN"}, receipt={"invoked": False, "reason": "policy not applied"})
            c["consume"] = consume_connected(c["bind"], c["receipt"], None, None)
            c["acceptance"] = accept(c)
            return c
        try:
            r = retrieve(CH.LEGACY_SEED, BUNDLE_ID, pub, SA_ALIAS, as_of, env.graph_clients(journal))
            c["retrieval"] = _retrieval_record(r, hidden=(HIDDEN,))
            c["retrieval"]["reached"] = CH.pick_computation(r, CH.COMPUTATION_PATH) is not None if r["status"] == "OK" else False
        except Exception as e:  # noqa: BLE001
            c["retrieval"] = dict(_err(e), reached=False)
        r = c["retrieval"]
        if not r.get("reached"):
            c["bind"] = {"status": "NOT_REACHED", "reason": "retrieval_denied" if r.get("status") in ("OK", "DENIED") else "retrieval_error"}
        else:
            c["bind"] = {"status": "NOT_BOUND", "reason": "a path through the hidden intermediate was returned; nothing is bound on it"}
        c["authorization"] = {"status": "NOT_RUN", "reason": "nothing bound"}
        c["receipt"] = {"invoked": False, "reason": f"bind {c['bind']['status']}: nothing was executed"}
        c["consume"] = consume_connected(c["bind"], c["receipt"], None, None)
        c["acceptance"] = accept(c)
        progress("decision", case=label, decision=c["consume"]["decision"], acceptance=c["acceptance"]["status"])
        return c

    def revocation_case(approved: dict) -> dict:
        label = REVOKE
        c: dict[str, Any] = {"case": label, "expected": EXPECTED[label], "receipt_invocations_after_revocation": 0,
                             "first_release": {"case": APPROVED, "decision": (approved.get("consume") or {}).get("decision")},
                             "cache": "not exercised: Catalog concept seeds disable the retrieval cache"}
        progress("case", case=label, stage="control: access present")
        try:
            c["control_policy"] = env.requester_apply(_policy())
        except Exception as e:  # noqa: BLE001
            c["control_policy"] = _err(e)
        c["control"] = {"catalog": env.catalog_observe(), "graph": env.graph_probe(), "authorization": env.authorize(deps)}
        launches_before = env.receipt_launches
        progress("case", case=label, stage="revoke Catalog, graph and fact access; wait for the requester to observe it")
        rev: dict[str, Any] = {}
        try:
            rev["catalog"] = env.catalog_revoke()
        except Exception as e:  # noqa: BLE001
            rev["catalog"] = _err(e)
        try:
            rev["requester"] = env.requester_revoke()
        except Exception as e:  # noqa: BLE001
            rev["requester"] = dict(_err(e), observed=False)
        rev["catalog_wait"] = env.catalog_wait(DENIED)
        rev["observed"] = bool(rev["catalog_wait"].get("observed")) and bool((rev["requester"] or {}).get("observed"))
        c["revocation"] = rev
        progress("case", case=label, stage="fresh request from Catalog discovery")
        fresh, _ = seeded(f"{label}-fresh")
        c["fresh_request"] = {"catalog": fresh.get("catalog"), "downstream_ran": any(k in fresh for k in ("publication", "retrieval", "bind")),
                              "stopped_at": "seed" if (fresh.get("catalog") or {}).get("status") != "OK" else None}
        progress("case", case=label, stage="retained-pin bypass: publication, retrieval, authorization")
        pin = state["pin"]
        bypass: dict[str, Any] = {"note": "an agent that cached the pin skips Catalog and goes straight to the store and retrieval"}
        if pin is None:
            bypass["publication"] = {"status": "NOT_RUN", "reason": "no pin was ever discovered"}
            bypass["retrieval"] = {"status": "NOT_RUN"}
        else:
            store = env.store(journal)
            res = resolve_publication(store, pin)
            bypass["publication"] = {"status": res["status"], "error": res.get("error"), "reasons": res.get("reasons")}
            try:
                clients = dict(env.graph_clients(journal), store=store)
                r = retrieve(pin.seed("retained-pin-bypass"), pin.bundle_id, pin.publication_id, SA_ALIAS, as_of, clients)
                bypass["retrieval"] = dict(_retrieval_record(r), disclosed_anything=bool(r.get("concepts") or r.get("paths") or r.get("computations")))
            except Exception as e:  # noqa: BLE001
                bypass["retrieval"] = dict(_err(e), disclosed_anything=False)
        c["bypass"] = bypass
        c["authorization"] = env.authorize(deps)
        stored = approved.get("receipt") or {"invoked": False}
        c["consume"] = CH.consume(approved.get("bind") or {}, stored, c["authorization"], containment=stored.get("containment"))
        c["stored_receipt_note"] = "the approved case's sealed receipt re-decided under the post-revocation authorization; never re-executed"
        c["receipt_invocations_after_revocation"] = env.receipt_launches - launches_before
        c["acceptance"] = accept(c)
        progress("decision", case=label, decision=c["consume"]["decision"], acceptance=c["acceptance"]["status"])
        return c

    blocked: Optional[str] = None
    try:
        progress("grant", detail="Catalog viewer + dataset reads for the requester; waiting until the requester observes them")
        g: dict[str, Any] = {"catalog_before": env.catalog_observe()}
        try:
            g["catalog"] = env.catalog_grant()
            g["catalog_wait"] = env.catalog_wait(ALLOWED)
        except Exception as e:  # noqa: BLE001
            g["catalog"] = _err(e)
            g["catalog_wait"] = {"observed": False, "status": "NOT_RUN"}
        if not g["catalog_wait"].get("observed"):
            blocked = f"Catalog access for the requester not observed: {g['catalog_wait'].get('status')}"
        else:
            try:
                g["requester"] = env.requester_apply(_policy())
            except Exception as e:  # noqa: BLE001
                g["requester"] = _err(e)
                blocked = f"requester grants not observed: {g['requester']['error'][:160]}"
        out["grant"] = g
        progress("grant_done", catalog=g["catalog_wait"].get("status"), waited_s=g["catalog_wait"].get("waited_s"), blocked=blocked)
        if blocked is None:
            out["caller"] = env.caller()
            approved = seeded_case(APPROVED, "approved")
            out["cases"].append(approved)
            out["cases"].append(seeded_case(SUBST, "sql-substitution"))
            out["cases"].append(denied_intermediate_case())
            out["cases"].append(seeded_case(UNAUTH, None, pol=_policy(sdk_tables=False)))
            out["cases"].append(revocation_case(approved))
    except Exception as e:  # noqa: BLE001 - an unexpected failure still tears down and writes its record
        out["run_error"] = _err(e)
    finally:
        progress("teardown", detail="restore Catalog IAM, dataset ACLs, row-policy grantees; read back")
        out["teardown"] = env.teardown()
        out["catalog_access"] = env.access.record(redact)
        out["broker_journal"] = list(getattr(env.broker, "journal", []))
    done = {c["case"] for c in out["cases"]}
    for name in CASES:
        if name not in done:
            c = {"case": name, "status": "NOT_RUN", "reason": blocked or (out.get("run_error") or {}).get("error") or "not reached",
                 "consume": {"decision": "REFUSED", "reasons": ["not run"]}}
            c["acceptance"] = accept(c)
            out["cases"].append(c)
    return _finish(out, env, journal, run_dir, out_dir, None, blocked)


def _finish(out: dict, env: Any, journal: Journal, run_dir: Path, out_dir: Path | str, broken_at: Optional[str], blocked: Optional[str]) -> dict:
    cases = out.get("cases") or []
    out["decisions"] = {c["case"]: (c.get("consume") or {}).get("decision") for c in cases}
    out["acceptance"] = {c["case"]: (c.get("acceptance") or {}).get("status") for c in cases}
    ids = CH.job_ids_of(cases, None, journal.job_ids())
    roles: dict[str, int] = {}
    for e in journal.jobs():
        if e.get("job_id"):
            roles[e["role"]] = roles.get(e["role"], 0) + 1
    unresolved = journal.unresolved()
    out["job_inventory"] = {"graph_and_store": ids["graph"], "receipt": [j.get("job_id") for j in ids["receipt"]],
                            "journal_by_role": roles, "unresolved": [{"seq": e.get("seq"), "role": e.get("role"), "job_id": e.get("job_id"),
                                                                      "state": e.get("state"), "error": e.get("error")} for e in unresolved],
                            "note": "every journaled job (Catalog-seeded store reads, retrieval, declaration, payload rows, facts read-back, the "
                                    "bypass attempts) and every receipt job; broker probes and row-policy DDL are in identity.roles"}
    if broken_at is None and cases:
        try:
            out["identity"] = env.identity(ids["graph"], ids["receipt"])
        except Exception as e:  # noqa: BLE001
            out["identity"] = dict(_err(e), status="UNKNOWN")
    else:
        out["identity"] = {"status": "NOT_RUN", "reason": "refused before any case"}
    statuses = list(out["acceptance"].values())
    td = out.get("teardown") or {}
    want_td = ("VERIFIED",) if env.live else ("VERIFIED", "NOT_NEEDED")
    teardown_ok = (td.get("catalog") or {}).get("status") in want_td and (td.get("broker") or {}).get("status") in (("VERIFIED",) if env.live else ("NOT_NEEDED", "VERIFIED"))
    ident = (out.get("identity") or {}).get("status")
    ident_ok = ident == "BOUND" if env.live else ident in ("NOT_APPLICABLE", "BOUND")
    out["checks"] = {"provenance": (out.get("provenance") or {}).get("ok"), "cases_met": sum(s == "MET" for s in statuses),
                     "cases": len(statuses), "identity": ident, "unresolved_jobs": len(unresolved), "teardown_ok": teardown_ok}
    if broken_at is not None:
        out["verdict"], out["broken_at"] = "E2E_BROKEN", broken_at
    elif "WRONG" in statuses or ident == "UNBOUND":
        out["verdict"] = "E2E_BROKEN"
        out["broken_at"] = next((c["case"] for c in cases if (c.get("acceptance") or {}).get("status") == "WRONG"), "identity")
    elif blocked or "NOT_REACHED" in statuses or not ident_ok or unresolved or not teardown_ok or out.get("run_error"):
        out["verdict"] = "E2E_INCOMPLETE"
        out["broken_at"] = ("grant" if blocked else next((c["case"] for c in cases if (c.get("acceptance") or {}).get("status") == "NOT_REACHED"),
                            "identity" if not ident_ok else ("unresolved_jobs" if unresolved else ("teardown" if not teardown_ok else "run_error"))))
    else:
        out["verdict"] = "E2E_CONNECTED"
    out["finished_at"] = _now().isoformat()
    out["journal"] = journal.record()
    try:
        out["run_dir"] = str(run_dir.resolve().relative_to(ROOT))
    except ValueError:
        out["run_dir"] = str(run_dir)
    published = _publish(out)
    text = json.dumps(published, indent=1, sort_keys=True, default=str) + "\n"
    name = f"connected_{out['mode']}.json"
    (run_dir / name).write_text(text, encoding="utf-8")
    final = Path(out_dir) / name
    tmp = final.with_name(f".{name}.{out['run_id']}.tmp")
    tmp.write_text(text, encoding="utf-8")
    os.replace(tmp, final)
    return out


# ----------------------------------------------------------------------------- summary (CLI / agent)
def summary(out: dict) -> dict:
    """A compact, identifier-free view of the record: decisions, acceptance, waits, identity and teardown."""
    cases = {c["case"]: {"decision": (c.get("consume") or {}).get("decision"), "acceptance": (c.get("acceptance") or {}).get("status")}
             for c in out.get("cases", [])}
    by = {c["case"]: c for c in out.get("cases", [])}
    ap = by.get(APPROVED) or {}
    answer = (ap.get("consume") or {}).get("display") if (ap.get("consume") or {}).get("decision") == "RELEASED" else None
    rid = ((ap.get("receipt") or {}).get("receipt") or {}).get("receipt_id")
    rv = by.get(REVOKE) or {}
    rev = rv.get("revocation") or {}
    g = out.get("grant") or {}
    ident = out.get("identity") or {}
    td = out.get("teardown") or {}
    return {"run_id": out.get("run_id"), "mode": out.get("mode"), "engine": out.get("engine"), "verdict": out.get("verdict"),
            "broken_at": out.get("broken_at"), "answer": answer, "receipt_ref": id_token(rid) if rid else None,
            "receipt_verdict": ((ap.get("receipt") or {}).get("output") or {}).get("verdict"),
            "facts": (ap.get("facts") or {}).get("status"), "cases": cases,
            "access": {"catalog_before_grant": (g.get("catalog_before") or {}).get("status"),
                       "catalog_grant_observed": (g.get("catalog_wait") or {}).get("status"), "catalog_grant_waited_s": (g.get("catalog_wait") or {}).get("waited_s"),
                       "caller_is_requester": (out.get("caller") or {}).get("caller_is_requester"),
                       "revocation_observed": rev.get("observed"), "catalog_revocation_waited_s": (rev.get("catalog_wait") or {}).get("waited_s"),
                       "fresh_request_after_revocation": ((rv.get("fresh_request") or {}).get("catalog") or {}).get("status"),
                       "bypass_publication": ((rv.get("bypass") or {}).get("publication") or {}).get("status"),
                       "bypass_retrieval": ((rv.get("bypass") or {}).get("retrieval") or {}).get("status"),
                       "authorization_after_revocation": (rv.get("authorization") or {}).get("status"),
                       "receipt_launches_after_revocation": rv.get("receipt_invocations_after_revocation")},
            "identity": {"status": ident.get("status"), "roles": {k: {"jobs": v.get("jobs"), "status": v.get("status")} for k, v in (ident.get("roles") or {}).items()}},
            "unresolved_jobs": (out.get("checks") or {}).get("unresolved_jobs"),
            "teardown": {"catalog": (td.get("catalog") or {}).get("status"), "broker": (td.get("broker") or {}).get("status")},
            "labels": out.get("labels"), "run_dir": out.get("run_dir")}


def print_progress(event: str, **kw: Any) -> None:
    parts = " ".join(f"{k}={v}" for k, v in kw.items() if v is not None)
    print(f"  [{time.strftime('%H:%M:%S')}] {event:12s} {parts}", flush=True)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="connected end-to-end run: Catalog discovery -> consumer, restricted requester, access + revocation")
    ap.add_argument("--live", action="store_true", help="live GCP (test-project-0728-467323); default hermetic")
    ap.add_argument("--hermetic", action="store_true")
    ap.add_argument("--out", default=str(OUT_DIR))
    ap.add_argument("--sdk-root", default=CH.sdk_root())
    ap.add_argument("--acme-root", default=os.environ.get("OKF_ACME_ROOT", "/Users/haiyuancao/knowledge-catalog/okf/bundles/acme_retail"))
    ap.add_argument("--as-of", default=None)
    ap.add_argument("--wait-s", type=int, default=600, help="live: how long a grant or revocation may be waited for (default 600)")
    ap.add_argument("--sdk-python", default=None, help="interpreter for the SDK receipt child (default OKF_SDK_PYTHON, else this one)")
    ap.add_argument("--catalog-resource", action="append", default=None, help="live: Dataplex resource(s) the Catalog role is granted on (default: the entry group)")
    ap.add_argument("--json", action="store_true", help="print the summary as JSON")
    a = ap.parse_args(argv)
    if a.live and a.hermetic:
        ap.error("--live and --hermetic are exclusive")
    cfg = CatalogConfig()
    if a.live:
        env: Any = LiveEnv(CH.sdk_publication(a.sdk_root), a.sdk_root, cfg, wait_s=a.wait_s, sdk_python=a.sdk_python,
                           catalog_resources=a.catalog_resource)
    else:
        from .compile import compile_bundle
        env = HermeticEnv(compile_bundle(a.acme_root, BUNDLE_ID, SOURCE_PIN), a.sdk_root, cfg)
    print(f"okf connected e2e · runner {RUNNER_VERSION} · mode {env.mode} · engine {env.engine} · requester {SA_ALIAS}")
    out = run_connected(env, a.sdk_root, a.acme_root, out_dir=a.out, as_of=a.as_of, cfg=cfg, progress=print_progress)
    s = summary(out)
    if a.json:
        print(json.dumps(s, indent=1, sort_keys=True))
    else:
        for name, v in s["cases"].items():
            print(f"{name:32s} decision={v['decision']:9s} acceptance={v['acceptance']}")
        print(f"answer={s['answer']} receipt={s['receipt_ref']} identity={s['identity']['status']} teardown={s['teardown']}")
        print(f"verdict={s['verdict']}" + (f" broken_at={s['broken_at']}" if s["broken_at"] else "") + f" run_dir={s['run_dir']}")
    return 0 if out["verdict"] == "E2E_CONNECTED" else 1


if __name__ == "__main__":
    sys.exit(main())
