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
    base = {"run_id": "online_restricted-x", "chain": "okf_bq_graph.chain/0.8.0", "mode": "live",
            "started_at": "2026-09-07T22:10:38.426058+00:00", "finished_at": "2026-09-07T22:12:07.852479+00:00",
            "job_inventory": {"graph": ["g1", "g2"], "receipt": ["r1"], "requester_probe": ["p1"], "policy_admin": ["d1"]}}
    base.update(kw)
    return base


class _Iterator:
    """What `Client.list_jobs` actually returns: an iterator that leaves `next_page_token` behind when it stops early."""

    def __init__(self, jobs, stop_after=None, token="tok-1000"):
        self._jobs, self._stop_after, self._token = jobs, stop_after, token
        self.next_page_token = None

    def __iter__(self):
        for i, j in enumerate(self._jobs):
            if self._stop_after is not None and i >= self._stop_after:
                self.next_page_token = self._token     # a capped iterator stops with pages still to come
                return
            yield j


class _Listing:
    def __init__(self, jobs, stop_after=None):
        self.jobs, self.calls, self.stop_after = jobs, [], stop_after

    def list_jobs(self, all_users=None, min_creation_time=None, max_creation_time=None, page_size=None, **kw):
        assert "max_results" not in kw, "max_results caps the whole iterator, not the page: it would hide truncation"
        self.calls.append({"all_users": all_users, "start": min_creation_time, "end": max_creation_time, "page_size": page_size})
        return _Iterator(self.jobs, stop_after=self.stop_after)


class _Job:
    def __init__(self, job_id, email, state="DONE", error=None):
        self.job_id, self.user_email, self.state = job_id, email, state
        self.job_type, self.created, self.error_result = "query", None, ({"reason": error} if error else None)


def _all(extra=(), stop_after=None):
    return _Listing([_Job("g1", SA), _Job("g2", SA), _Job("r1", SA), _Job("p1", SA), _Job("d1", OP), *extra], stop_after=stop_after)


def test_a_complete_inventory_reconciles_and_reads_the_records_own_window():
    out = JA.audit(_record(), client=(cl := _all()), requester_email=SA)
    assert out["status"] == "RECONCILED" and out["listed"] == 5 and out["matched"] == 5
    assert out["not_listed"] == [] and out["unaccounted_requester_jobs"] == []
    assert out["inventory"]["by_role"] == {"graph": 2, "receipt": 1, "requester_probe": 1, "policy_admin": 1}
    call = cl.calls[0]                                   # all users, and the window is the record's own, padded
    assert call["all_users"] is True and call["page_size"] == JA.PAGE_SIZE and out["truncated"] is False
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


def test_a_truncated_listing_is_indeterminate_never_reconciled():   # Astra PR 45 re-review #4
    """`max_results` caps the whole iterator and leaves a continuation token, so a run whose window holds more jobs
    than the cap would match its entire inventory against a prefix and look complete. A listing that stopped with pages
    left proves nothing about the rest of the window."""
    out = JA.audit(_record(), client=_all([_Job("unread-x", SA)], stop_after=5), requester_email=SA)   # every claim matched
    assert out["status"] == "INDETERMINATE" and out["truncated"] is True
    assert out["matched"] == 5 and out["unaccounted_requester_jobs"] == [] and out["not_listed"] == []
    assert "pages left" in out["reason"]


def test_the_read_cap_is_truncation_not_a_pass():
    out = JA.audit(_record(), client=_all(), requester_email=SA, cap=3)
    assert out["status"] == "INDETERMINATE" and out["truncated"] is True and out["listed"] == 3
    assert "cap 3" in out["reason"] and out["not_listed"] == ["d1", "p1"]
    # a truncated listing cannot establish an absence: those two are unread, not missing
    assert "not observed to be missing" in out["not_listed_note"]


def test_a_definite_gap_outranks_truncation():
    out = JA.audit(_record(), client=_all([_Job("probe-x", SA), _Job("unread-y", SA)], stop_after=6), requester_email=SA)
    assert out["status"] == "INCOMPLETE" and out["truncated"] is True
    assert out["unaccounted_requester_jobs"] == ["probe-x"]


def test_a_record_that_declares_unresolved_admin_work_cannot_be_certified():   # Astra PR 45 re-review #1
    """A run that already says it lost track of statements it submitted must not be certified by an audit, and those
    jobs must not be written off as somebody else's unrelated operator work."""
    rec = _record()
    rec["job_inventory"]["policy_admin_unresolved"] = [{"transition": "restore", "table": "edges", "error": "ServiceUnavailable"}]
    out = JA.audit(rec, client=_all(), requester_email=SA)
    assert out["status"] == "INCOMPLETE" and out["declared_admin_unresolved"] == 1
    assert "never named a job for" in out["reason"]
    assert out["unaccounted_requester_jobs"] == [] and out["not_listed"] == []   # nothing else is wrong: the record's own admission is
