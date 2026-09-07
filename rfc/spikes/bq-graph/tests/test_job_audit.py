"""Offline tests for the job-inventory reconciliation (Astra PR 45 #1).

The audit exists because a record's own inventory cannot detect a job the record forgot. These drive the real `audit`
against a fake `jobs.list`, so the verdict rule itself is under test: a requester job the record does not claim is
INCOMPLETE, another identity's job in the same window is reported but not condemned, and an unreadable listing is
UNAVAILABLE rather than a pass.
"""
from __future__ import annotations

import okf_bq_graph.job_audit as JA
from okf_bq_graph.authz import SA_ALIAS

SA = "okf-receipt-restricted@test-project-0728-467323.iam.gserviceaccount.com"
OP = "operator@example.test"


def _record(**kw):
    base = {"run_id": "live_restricted-x", "chain": "okf_bq_graph.chain/0.8.0", "mode": "live",
            "started_at": "2026-09-07T22:10:38.426058+00:00", "finished_at": "2026-09-07T22:12:07.852479+00:00",
            "job_inventory": {"graph": ["g1", "g2"], "receipt": ["r1"], "requester_probe": ["p1"], "policy_admin": ["d1"]}}
    base.update(kw)
    return base


class _Listing:
    def __init__(self, jobs):
        self.jobs, self.calls = jobs, []

    def list_jobs(self, all_users=None, min_creation_time=None, max_creation_time=None, max_results=None):
        self.calls.append({"all_users": all_users, "start": min_creation_time, "end": max_creation_time})
        return iter(self.jobs)


class _Job:
    def __init__(self, job_id, email, state="DONE", error=None):
        self.job_id, self.user_email, self.state = job_id, email, state
        self.job_type, self.created, self.error_result = "query", None, ({"reason": error} if error else None)


def _all(extra=()):
    return _Listing([_Job("g1", SA), _Job("g2", SA), _Job("r1", SA), _Job("p1", SA), _Job("d1", OP), *extra])


def test_a_complete_inventory_reconciles_and_reads_the_records_own_window():
    out = JA.audit(_record(), client=(cl := _all()), requester_email=SA)
    assert out["status"] == "RECONCILED" and out["listed"] == 5 and out["matched"] == 5
    assert out["not_listed"] == [] and out["unaccounted_requester_jobs"] == []
    assert out["inventory"]["by_role"] == {"graph": 2, "receipt": 1, "requester_probe": 1, "policy_admin": 1}
    call = cl.calls[0]                                   # all users, and the window is the record's own, padded
    assert call["all_users"] is True
    assert call["start"].isoformat() == "2026-09-07T22:09:38.426058+00:00"
    assert call["end"].isoformat() == "2026-09-07T22:13:07.852479+00:00"
    assert SA not in str(out) and out["identity_counts"][SA_ALIAS] == 4   # redacted to the alias


def test_a_requester_job_the_record_never_claimed_makes_the_audit_incomplete():
    """The exact defect: a denied re-check and a broker probe ran as the SA and were absent from the inventory."""
    out = JA.audit(_record(), client=_all([_Job("recheck-x", SA, error="accessDenied"), _Job("probe-x", SA)]), requester_email=SA)
    assert out["status"] == "INCOMPLETE" and out["unaccounted_requester_jobs"] == ["probe-x", "recheck-x"]
    assert "2 requester job(s)" in out["reason"] and out["unaccounted_other_jobs"] == []


def test_another_identity_in_the_window_is_reported_but_does_not_condemn_the_run():
    out = JA.audit(_record(), client=_all([_Job("someone-elses-job", "third@example.test")]), requester_email=SA)
    assert out["status"] == "RECONCILED" and out["unaccounted_other_jobs"] == ["someone-elses-job"]
    assert out["unaccounted_requester_jobs"] == []


def test_an_inventory_job_the_platform_does_not_list_is_incomplete():
    listing = _Listing([_Job("g1", SA), _Job("r1", SA), _Job("p1", SA), _Job("d1", OP)])
    out = JA.audit(_record(), client=listing, requester_email=SA)
    assert out["status"] == "INCOMPLETE" and out["not_listed"] == ["g2"] and out["matched"] == 4


def test_a_listing_that_cannot_be_read_is_unavailable_never_a_pass():
    class Boom:
        def list_jobs(self, **kw):
            raise RuntimeError("jobs.list denied")

    out = JA.audit(_record(), client=Boom(), requester_email=SA)
    assert out["status"] == "UNAVAILABLE" and "jobs.list denied" in out["reason"] and "listed" not in out


def test_the_cli_refuses_a_hermetic_record(tmp_path, capsys):
    import json
    import pytest
    p = tmp_path / "chain_hermetic_restricted.json"
    p.write_text(json.dumps(_record(mode="hermetic")))
    with pytest.raises(SystemExit):
        JA.main([str(p)])
    assert "only a live run submits jobs" in capsys.readouterr().err
