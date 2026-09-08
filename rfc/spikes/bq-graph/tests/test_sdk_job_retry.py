"""The SDK's own job retry versus this spike's job accounting (Astra PR 45 re-review 2).

These drive the real `google.cloud.bigquery` Client, QueryJob and retry machinery at the pinned 3.45.0; only the HTTP
transport is faked, so the behaviour under test is the SDK's, not a model of it. Nothing here touches the network.

The hazard: on a retryable terminal failure `QueryJob.result()` submits a NEW job and repoints the object at it. A
caller that recorded the id at submission then holds the id of a job that failed, marks it DONE because the helper
returned success, and never learns the id of the job that actually ran.
"""
from __future__ import annotations

import datetime as _dt
import json
from unittest.mock import patch

import pytest
from google.auth.credentials import AnonymousCredentials
from google.cloud import bigquery

import okf_bq_graph.job_audit as JA
import okf_bq_graph.principal as PR
import okf_bq_graph.publish as PUB
from okf_bq_graph import LOCATION, PROJECT

SA = "okf-receipt-restricted@test-project-0728-467323.iam.gserviceaccount.com"
OP = "operator@example.test"
DDL = "CREATE OR REPLACE ROW ACCESS POLICY p ON `x.y.z` GRANT TO ('user:a@b.co') FILTER USING (TRUE)"


class _Fake:
    """A BigQuery HTTP transport: the Nth submitted job fails with `reason`, everything else succeeds."""

    def __init__(self, fail_on=(1,), reason="backendError"):
        self.fail_on, self.reason = set(fail_on), reason
        self.submitted: list[str] = []
        self.responses: dict[str, dict] = {}

    def __call__(self, method=None, path=None, data=None, **kw):
        if method == "POST" and path.endswith("/jobs"):
            jid = data["jobReference"]["jobId"]
            self.submitted.append(jid)
            status: dict = {"state": "DONE"}
            if len(self.submitted) in self.fail_on:
                status["errorResult"] = {"reason": self.reason, "message": "offline simulated job failure"}
                status["errors"] = [status["errorResult"]]
            self.responses[jid] = {"jobReference": data["jobReference"], "configuration": data["configuration"],
                                   "status": status, "statistics": {"query": {"statementType": "CREATE_ROW_ACCESS_POLICY"}},
                                   "user_email": OP}
            return self.responses[jid]
        if method == "GET" and "/queries/" in path:
            return {"jobReference": self.responses[path.rsplit("/", 1)[-1]]["jobReference"], "jobComplete": True,
                    "schema": {"fields": []}}
        if method == "GET" and "/jobs/" in path:
            return self.responses[path.rsplit("/", 1)[-1]]
        raise AssertionError((method, path))


@pytest.fixture
def client():
    return bigquery.Client(project=PROJECT, location=LOCATION, credentials=AnonymousCredentials())


def test_the_real_sdk_substitutes_a_job_on_a_retryable_failure(client):
    """The hazard itself, measured against the pinned SDK: two jobs exist and the object now names the second."""
    fake = _Fake()
    with patch.object(client._connection, "api_request", fake):
        job = client.query(DDL)
        first = job.job_id
        job.result()                                   # default job_retry: re-submits behind the caller
    assert len(fake.submitted) == 2 and job.job_id != first and job.job_id == fake.submitted[1]

    # ... and with job re-submission disabled the failure surfaces on the one job that was actually submitted
    fake2 = _Fake()
    with patch.object(client._connection, "api_request", fake2):
        job2 = client.query(DDL)
        with pytest.raises(Exception) as exc:
            job2.result(job_retry=None)
    assert len(fake2.submitted) == 1 and job2.job_id == fake2.submitted[0]
    assert job2.error_result["reason"] == "backendError" and "backendError" not in type(exc.value).__name__


def test_run_accounts_for_every_attempt_it_makes(client):
    """`publish.run` retries a retryable job itself, one accounted attempt at a time: every job that exists reaches the
    hook, with its own outcome, and no job is created that the hook did not see."""
    fake = _Fake(fail_on=(1,))
    events: list[tuple] = []
    with patch.object(client._connection, "api_request", fake):
        job = PUB.run(client, DDL, on_job=lambda n, j, s, e: events.append((n, getattr(j, "job_id", None), s, e is not None)),
                      attempts=3)
    assert len(fake.submitted) == 2 and job.job_id == fake.submitted[1]
    assert [(n, jid, st) for n, jid, st, _ in events] == [
        (1, None, "DISPATCHING"), (1, fake.submitted[0], "SUBMITTED"), (1, fake.submitted[0], "FAILED"),
        (2, None, "DISPATCHING"), (2, fake.submitted[1], "SUBMITTED"), (2, fake.submitted[1], "DONE")]
    assert events[2][3] is True and events[5][3] is False        # the failed attempt carries its own error
    # every attempt is owned before its request leaves, so an id can never be attributed to the wrong attempt
    assert [n for n, _, st, _ in events if st == "DISPATCHING"] == [1, 2]

    # a failure the SDK would not have re-submitted for is surfaced, not retried
    fake = _Fake(fail_on=(1,), reason="invalidQuery")
    seen: list[str] = []
    with patch.object(client._connection, "api_request", fake):
        with pytest.raises(Exception):
            PUB.run(client, DDL, on_job=lambda n, j, s, e: seen.append(s), attempts=3)
    assert len(fake.submitted) == 1 and seen == ["DISPATCHING", "SUBMITTED", "FAILED"]

    # a submission whose response never came back owns an attempt with no id, and is not re-issued blindly
    fake = _Fake()
    seen = []
    with patch.object(client._connection, "api_request", side_effect=ValueError("response could not be decoded")):
        with pytest.raises(ValueError):
            PUB.run(client, DDL, on_job=lambda n, j, s, e: seen.append((n, getattr(j, "job_id", None), s)), attempts=3)
    assert seen == [(1, None, "DISPATCHING"), (1, None, "UNRESOLVED")]

    # an untracked caller keeps the SDK's default behaviour, unchanged
    fake = _Fake(fail_on=(1,))
    with patch.object(client._connection, "api_request", fake):
        PUB.run(client, DDL)
    assert len(fake.submitted) == 2


def _broker(client, fake):
    class Owner:
        def __init__(self):
            self.emails = {"g1": SA, "r1": SA}

        def query(self, *a, **kw):
            return client.query(*a, **kw)

        def get_job(self, jid, project=None, location=None):
            class J:
                user_email = OP if jid in fake.responses else self.emails.get(jid, "missing")
            return J()

    b = PR.RestrictedBroker("fallback", "sdk_ds", sa_email=SA, factory=lambda _p: None, owner=Owner())
    b._operator_email = OP
    return b


def test_a_retried_policy_statement_puts_both_jobs_in_the_inventory(client):
    """End to end through the real SDK: the retry is a job of this run's own, and the attempt it replaced is not
    quietly relabelled as the one that succeeded. Before the fix this was 4 submitted / 3 retained, with the failed
    job recorded as DONE."""
    fake = _Fake(fail_on=(1,))
    b = _broker(client, fake)
    with patch.object(client._connection, "api_request", fake):
        b._set_rls([f"user:{OP}"], [f"user:{OP}"], "restore")

    retained = [j["job_id"] for j in b.admin_jobs]
    assert len(fake.submitted) == 4 and retained == fake.submitted        # every submitted job, in order
    assert [j["state"] for j in b.admin_jobs] == ["FAILED", "DONE", "DONE", "DONE"]
    assert [(o["table"], o["attempt"], o["state"]) for o in b.admin_ops] == [
        ("nodes", 1, "FAILED"), ("nodes", 2, "DONE"), ("edges", 1, "DONE"), ("section_vectors", 1, "DONE")]
    assert b.admin_unresolved() == [] and all(o["hook"] == "seen" for o in b.admin_ops)

    ident = b.identity(["g1"], [{"job_id": "r1"}])
    assert ident["status"] == "BOUND" and ident["roles"]["policy_admin"]["jobs"] == 4
    assert ident["admin_ops"] == {"attempted": 4, "by_state": {"DONE": 3, "FAILED": 1}}

    class _It:
        next_page_token = None

        def __iter__(self):
            for jid in ["g1", "r1"] + fake.submitted:
                job = type("J", (), {})()
                job.job_id, job.state, job.job_type = jid, "DONE", "query"
                job.user_email = OP if jid in fake.responses else SA
                job.created = _dt.datetime(2026, 9, 7, 22, 49, tzinfo=_dt.timezone.utc)
                job.error_result = (fake.responses.get(jid) or {}).get("status", {}).get("errorResult")
                yield job

    record = {"mode": "live", "run_id": "offline-sdk-retry", "chain": PR.__name__,
              "started_at": "2026-09-07T22:48:31+00:00", "finished_at": "2026-09-07T22:51:25+00:00",
              "job_inventory": {"graph": ["g1"], "receipt": ["r1"], "policy_admin": retained,
                                "policy_admin_unresolved": b.admin_unresolved()}}
    audited = JA.audit(record, client=type("C", (), {"list_jobs": lambda self, **kw: _It()})(), requester_email=SA)
    assert audited["status"] == "RECONCILED" and audited["unaccounted_other_jobs"] == []   # was: the retry, "unrelated"


def test_a_job_the_hook_never_saw_blocks_the_completeness_claim(client, monkeypatch):
    """The guard behind the guard. With submission-time capture but the SDK's own job re-submission left on - the
    pre-fix shape - the helper returns an id no hook event carried. That id is kept AND flagged, because a job created
    behind the broker means earlier attempts may be missing too; it must not be silently adopted as the final answer."""
    def legacy_run(cl, query, params=None, labels=None, use_cache=False, on_job=None, attempts=1):
        cfg = bigquery.QueryJobConfig(query_parameters=params or [], use_query_cache=use_cache,
                                      labels=labels or {"okf_spike": "bq_graph_20260905"})
        job = cl.query(query, job_config=cfg, location=LOCATION)
        if on_job is not None:
            on_job(1, job, "SUBMITTED", None)   # the pre-fix hook fired here and nowhere else
        job.result()                            # default job_retry: substitutes, and the hook never learns
        return job

    monkeypatch.setattr(PUB, "run", legacy_run)
    fake = _Fake(fail_on=(1,))
    b = _broker(client, fake)
    with patch.object(client._connection, "api_request", fake):
        b._set_rls([f"user:{OP}"], [f"user:{OP}"], "restore")

    # nothing is dropped: the substituted job is kept too, it just arrives at settle time rather than through the hook
    assert len(fake.submitted) == 4 and {j["job_id"] for j in b.admin_jobs} == set(fake.submitted)
    missed = [o for o in b.admin_ops if o["hook"] == "missed"]
    assert [o["job_id"] for o in missed] == [fake.submitted[1]]
    unresolved = b.admin_unresolved()
    assert missed[0] in unresolved                                     # the job nobody watched being submitted
    # and the pre-fix hook also leaves every attempt non-terminal, which is unaccounted for in its own right
    assert all(o["state"] == "SUBMITTED" for o in unresolved if o["hook"] == "seen")

    ident = b.identity(["g1"], [{"job_id": "r1"}])
    assert ident["status"] == "UNKNOWN" and ident["roles"]["policy_admin"]["status"] == "UNKNOWN"
    assert "without the submission hook seeing them" in ident["reason"]


def test_a_retry_whose_response_is_lost_cannot_hide_behind_the_failed_attempt(client):
    """Astra PR 45 re-review 3. A known attempt fails with backendError; the retry IS accepted by the server but its
    response cannot be decoded, so no job reaches the hook. The failing statement must not be credited with the
    previous attempt's id: that made the accepted retry vanish from the inventory, left nothing UNRESOLVED, and let the
    reconciliation classify a job of this run's own as unrelated operator work."""
    fake = _Fake(fail_on=(1,))
    b = _broker(client, fake)
    real_request = client._connection.api_request

    def transport(method=None, path=None, data=None, **kw):
        body = fake(method=method, path=path, data=data, **kw)
        if method == "POST" and path.endswith("/jobs") and len(fake.submitted) == 2:
            raise ValueError("the server accepted the job; its response could not be decoded")
        return body

    with patch.object(client._connection, "api_request", transport):
        with pytest.raises(RuntimeError, match=r"failed for \['nodes'\]"):
            b._set_rls([f"user:{OP}"], [f"user:{OP}"], "restore")

    assert len(fake.submitted) == 4                       # nodes attempt 1 + the accepted retry + edges + vectors
    nodes = [o for o in b.admin_ops if o["table"] == "nodes"]
    assert [(o["attempt"], o["state"]) for o in nodes] == [(1, "FAILED"), (2, "UNRESOLVED")]
    assert nodes[0]["job_id"] == fake.submitted[0]
    assert nodes[1]["job_id"] is None                     # NOT the previous attempt's id, which is what used to happen
    assert "could not be decoded" in nodes[1]["error"]
    assert b.admin_unresolved() == [nodes[1]]

    ident = b.identity(["g1"], [{"job_id": "r1"}])
    assert ident["status"] == "UNKNOWN" and ident["roles"]["policy_admin"]["status"] == "UNKNOWN"
    assert ident["admin_ops"]["by_state"]["UNRESOLVED"] == 1

    # through the record the chain serialises, the reconciliation refuses to certify the run - even though the accepted
    # retry is sitting in the platform listing under the operator, which it would otherwise write off as unrelated
    record = {"mode": "live", "run_id": "offline-lost-retry-response", "chain": "okf_bq_graph.chain/0.11.0",
              "started_at": "2026-09-07T22:48:31+00:00", "finished_at": "2026-09-07T22:51:25+00:00",
              "job_inventory": {"graph": ["g1"], "receipt": ["r1"],
                                "policy_admin": [j["job_id"] for j in b.admin_jobs],
                                "policy_admin_ops": b.admin_ops,
                                "policy_admin_unresolved": b.admin_unresolved()}}
    assert json.loads(json.dumps(record, default=str)) == record        # it survives the record's own serialisation

    class _It:
        next_page_token = None

        def __iter__(self):
            for jid in ["g1", "r1"] + fake.submitted:                   # the accepted retry IS on the platform
                job = type("J", (), {})()
                job.job_id, job.state, job.job_type = jid, "DONE", "query"
                job.user_email = OP if jid in fake.responses else SA
                job.created = _dt.datetime(2026, 9, 7, 22, 49, tzinfo=_dt.timezone.utc)
                job.error_result = None
                yield job

    audited = JA.audit(record, client=type("C", (), {"list_jobs": lambda self, **kw: _It()})(), requester_email=SA)
    assert audited["status"] == "INCOMPLETE" and audited["declared_admin_unresolved"] == 1
    assert "never named a job for" in audited["reason"]
    assert fake.submitted[1] in audited["unaccounted_other_jobs"]        # reported, and no longer able to pass as unrelated
