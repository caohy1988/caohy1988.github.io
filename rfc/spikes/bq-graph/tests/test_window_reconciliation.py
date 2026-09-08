"""U1: read-only legacy window reconciliation and the explicit GQL admission gate.

Every transport here is injected. No ADC, no reservation, no job submission and no cancellation helper is reachable
from these tests: a reconciliation that mutates anything is the defect the module exists to prevent.
"""
import copy
import datetime as _dt
import json

import pytest

from okf_bq_graph import lifecycle as L
from okf_bq_graph import reconcile_window as RW
from okf_bq_graph import reservation as RES

OPEN = "2026-09-05T23:43:43Z"
CLOSE = "2026-09-05T23:47:20Z"
PROJ, LOC = RW.PROJECT, RW.LOCATION


def ms(text):
    return str(int(_dt.datetime.fromisoformat(text.replace("Z", "+00:00")).timestamp() * 1000))


def job(job_id, *, created=OPEN, state="DONE", project=PROJ, location=LOC, labels=None, parent=None,
        reservation=None, children=False, email="operator@example.test", error=None):
    stats = {"creationTime": ms(created), "endTime": ms(created)}
    if parent:
        stats["parentJobId"] = parent
    if reservation:
        stats["reservation_id"] = reservation
    if children:
        stats["scriptStatistics"] = {"evaluationKind": "STATEMENT"}
    return {"jobReference": {"projectId": project, "location": location, "jobId": job_id},
            "status": {"state": state, **({"errorResult": error} if error else {})},
            "configuration": {"labels": labels or {}}, "statistics": stats, "user_email": email}


class FakeTransport:
    """A jobs.list/jobs.get transport with explicit pages, children and per-job get behaviour."""

    def __init__(self, pages=None, children=None, get=None, unreachable=None, list_error=None):
        self.pages = pages or [{"jobs": []}]
        self.children = children or {}          # parent job id -> list of pages
        self.get = get or {}                    # job id -> resource | Exception
        self.unreachable = unreachable or []
        self.list_error = list_error
        self.calls = []
        self.gets = []

    def list_jobs(self, *, project, min_creation_time=None, max_creation_time=None, page_token=None, page_size=None,
                  parent_job_id=None):
        self.calls.append({"project": project, "page_token": page_token, "parent_job_id": parent_job_id,
                           "start": min_creation_time, "end": max_creation_time})
        if self.list_error and parent_job_id is None:
            raise self.list_error
        pages = self.children.get(parent_job_id, [{"jobs": []}]) if parent_job_id else self.pages
        index = 0 if page_token is None else int(page_token)
        page = dict(pages[index])
        if parent_job_id is None and self.unreachable:
            page = dict(page, unreachable=self.unreachable)
        return page

    def get_job(self, *, project, location, job_id):
        self.gets.append((project, location, job_id))
        value = self.get.get(job_id)
        if value is None:
            raise KeyError(f"no such job {job_id}")
        if isinstance(value, Exception):
            raise value
        return value


def transport_for(jobs, **kw):
    """One complete page plus a matching jobs.get for every listed job."""
    return FakeTransport(pages=[{"jobs": jobs}], get={j["jobReference"]["jobId"]: j for j in jobs}, **kw)


def window(label="smoke-1", **kw):
    return {"label": label, "opened_at": OPEN, "closed_at": CLOSE, **kw}


def quiescence(established=True, evidence="launcher log: the driver exited", stopped_at="2026-09-05T23:48:10Z"):
    """The reconciler needs an EVIDENCED shutdown: a boolean, a named record and the moment the last submitter
    stopped, because that moment - not capacity deletion - bounds the submission lifetime."""
    q = {"established": established}
    if evidence is not None:
        q["evidence"] = evidence
    if stopped_at is not None:
        q["stopped_at"] = stopped_at
    return q


def run(label="smoke-1", *, transport, recovered=(), decisions=None, quiescent=True, win=None, q=None, **kw):
    return RW.reconcile(label, transport=transport, window=win or window(label), recovered=recovered,
                        decisions=decisions, quiescence=q or quiescence(established=quiescent), **kw)


# ----------------------------------------------------------------------------- the success fixture
def owned_jobs(label="smoke-1", n=3):
    return [job(f"okf_graph_{label}_{i:02d}") for i in range(n)]


def test_complete_window_reconciles_and_stages_a_verifiable_receipt(tmp_path):
    jobs = owned_jobs()
    t = transport_for(jobs)
    result = run(transport=t)
    assert result["status"] == RW.RECONCILED, result["blockers"]
    assert result["owned"] == sorted(j["jobReference"]["jobId"] for j in jobs)
    staged = RW.stage(result, tmp_path)
    assert staged["staged"] and staged["verified"] is True
    # the structural gate the reservation module runs, against the staged files only
    assert RW.gate(tmp_path, ["smoke-1"]) == {"stage_dir": str(tmp_path), "labels": {"smoke-1": True}, "all_verified": True}
    assert L.job_cleanup_verified("smoke-1", tmp_path / "jobs_smoke-1.json") is True


def test_reconstructed_journal_says_so_and_names_its_sources(tmp_path):
    src = tmp_path / "cost.json"
    src.write_text('{"rows": []}')
    result = RW.reconcile("smoke-1", transport=transport_for(owned_jobs()), window=window(), sources=[src],
                          quiescence=quiescence())
    RW.stage(result, tmp_path / "stage")
    journal = json.loads((tmp_path / "stage" / "jobs_smoke-1.json").read_text())
    receipt = json.loads((tmp_path / "stage" / "jobs_smoke-1.cleanup.json").read_text())
    assert journal["reconstructed"] is True and "RECONSTRUCTED" in journal["reconstruction_note"]
    assert receipt["reconstructed"] is True
    assert journal["reconstruction"]["sources"][0]["path"] == str(src)
    assert journal["reconstruction"]["sources"][0]["sha256"]
    # the journal is hashed into its receipt: the pair cannot be split or edited independently
    import hashlib
    raw = (tmp_path / "stage" / "jobs_smoke-1.json").read_text()
    assert receipt["journal_sha256"] == hashlib.sha256(raw.encode()).hexdigest()
    # every owned reference is fully qualified, not a bare id
    assert journal["job_refs"] and all(RW.qualified(r) for r in journal["job_refs"])


def test_qualified_refs_are_read_back_with_their_own_project_and_location():
    jobs = [job("okf_graph_smoke-1_a", project="other-project", location="EU")]
    t = transport_for(jobs)
    result = run(transport=t, decisions={"okf_graph_smoke-1_a": {"ownership": RW.OWNED, "reason": "driver prefix"}})
    assert t.gets == [("other-project", "EU", "okf_graph_smoke-1_a")]
    assert result["status"] == RW.RECONCILED


# ----------------------------------------------------------------------------- incomplete evidence blocks
def test_page_two_omission_blocks():
    jobs = owned_jobs()
    t = FakeTransport(pages=[{"jobs": jobs[:1], "nextPageToken": "1"}, {"jobs": jobs[1:]}],
                      get={j["jobReference"]["jobId"]: j for j in jobs})
    assert run(transport=t)["status"] == RW.RECONCILED       # drained: both pages read
    stops = FakeTransport(pages=[{"jobs": jobs[:1], "nextPageToken": "1"}], get={jobs[0]["jobReference"]["jobId"]: jobs[0]})
    stops.pages.append({"jobs": [], "nextPageToken": "1"})   # a token that never clears
    out = run(transport=stops)
    assert out["status"] == RW.BLOCKED
    assert any("incomplete" in b for b in out["blockers"])


def test_unreachable_location_blocks():
    out = run(transport=transport_for(owned_jobs(), unreachable=["us-east7"]))
    assert out["status"] == RW.BLOCKED and any("incomplete" in b for b in out["blockers"])


def test_listing_transport_error_is_not_an_empty_window():
    out = run(transport=FakeTransport(list_error=RuntimeError("503 backend")))
    assert out["status"] == RW.BLOCKED
    assert any("incomplete" in b for b in out["blockers"])
    assert not out["owned"]


def test_cap_hit_is_truncation():
    jobs = owned_jobs(n=5)
    t = transport_for(jobs)
    out = run(transport=t, cap=2)
    assert out["status"] == RW.BLOCKED and any("incomplete" in b for b in out["blockers"])


def test_an_opened_window_with_no_owned_job_is_not_an_empty_inventory():
    out = run(transport=FakeTransport(pages=[{"jobs": []}]))
    assert out["status"] == RW.BLOCKED
    assert any("empty inventory" in b for b in out["blockers"])


def test_closer_only_row_without_opened_at_is_refused():
    out = RW.reconcile("safety-0011", transport=transport_for([]), window={"label": "safety-0011", "closed_at": CLOSE})
    assert out["status"] == RW.BLOCKED and "closer record" in out["blockers"][0]


def test_no_transport_is_blocked_not_reconciled():
    out = RW.reconcile("smoke-1", transport=None, window=window())
    assert out["status"] == RW.BLOCKED and "no read-only GET transport" in out["blockers"][0]


# ----------------------------------------------------------------------------- ownership
def test_in_span_job_without_a_signal_is_ambiguous_not_owned():
    jobs = owned_jobs() + [job("someone_elses_job", created="2026-09-05T23:45:00Z", email="other@example.test")]
    out = run(transport=transport_for(jobs))
    assert out["status"] == RW.BLOCKED
    assert [a["ref"]["job_id"] for a in out["ambiguous"]] == ["someone_elses_job"]
    assert any("could not be classified" in b for b in out["blockers"])


def test_reservation_name_alone_does_not_settle_ownership():
    tail = job("okf_rcpt_cfa80316f42228ab90a14537_7ea69d58a509ba43", created="2026-09-06T00:27:56Z",
               reservation=f"{PROJ}:{LOC}.{RW.RESERVATION}")
    out = run(transport=transport_for(owned_jobs() + [tail]))
    assert out["status"] == RW.BLOCKED
    entry = next(a for a in out["ambiguous"] if a["ref"]["job_id"].startswith("okf_rcpt_"))
    assert entry["signal"] == "reservation_name"


def test_an_explicit_decision_resolves_ambiguity_but_needs_a_reason():
    tail = job("okf_rcpt_tail", created="2026-09-06T00:27:56Z", reservation=f"{PROJ}:{LOC}.{RW.RESERVATION}")
    jobs = owned_jobs() + [tail]
    bare = run(transport=transport_for(jobs), decisions={"okf_rcpt_tail": {"ownership": RW.EXCLUDED}})
    assert bare["status"] == RW.BLOCKED and bare["ambiguous"][0]["signal"] == "operator_decision_invalid"
    resolved = run(transport=transport_for(jobs),
                   decisions={"okf_rcpt_tail": {"ownership": RW.EXCLUDED, "reason": "concurrent receipt work",
                                                "evidence": "receipt run log"}})
    assert resolved["status"] == RW.RECONCILED
    assert [e["ref"]["job_id"] for e in resolved["excluded"]] == ["okf_rcpt_tail"]


def test_extra_owned_job_enters_the_inventory(tmp_path):
    """A job the original record never mentioned, but the platform attributes to the window, is owned."""
    extra = job("okf_graph_smoke-1_forgotten")
    result = run(transport=transport_for(owned_jobs() + [extra]))
    assert "okf_graph_smoke-1_forgotten" in result["owned"]
    RW.stage(result, tmp_path)
    assert "okf_graph_smoke-1_forgotten" in json.loads((tmp_path / "jobs_smoke-1.json").read_text())["job_ids"]


def test_script_children_are_listed_and_owned():
    parent = job("okf_graph_smoke-1_script", children=True)
    parent["statistics"]["numChildJobs"] = "1"
    child = job("child_of_script", parent="okf_graph_smoke-1_script")
    grandchild = job("grandchild", parent="child_of_script")
    t = FakeTransport(pages=[{"jobs": [parent]}],
                      children={"okf_graph_smoke-1_script": [{"jobs": [child]}], "child_of_script": [{"jobs": [grandchild]}]},
                      get={j["jobReference"]["jobId"]: j for j in (parent, child, grandchild)})
    child["statistics"]["scriptStatistics"] = {"evaluationKind": "STATEMENT"}
    child["statistics"]["numChildJobs"] = "1"
    out = run(transport=t)
    assert out["status"] == RW.RECONCILED
    assert out["owned"] == ["child_of_script", "grandchild", "okf_graph_smoke-1_script"]


def test_an_ordinary_script_leaf_is_not_mistaken_for_a_parent():
    """Astra PR47 re-review P2: `scriptStatistics` is a CHILD's own context. A terminal leaf declares no children of
    its own, and reading it as an undeclared parent blocked a perfectly good reconciliation."""
    parent = job("okf_graph_smoke-1_script")
    parent["statistics"]["numChildJobs"] = "1"
    leaf = job("script_leaf", parent="okf_graph_smoke-1_script", children=True)   # scriptStatistics, no numChildJobs
    t = FakeTransport(pages=[{"jobs": [parent]}], children={"okf_graph_smoke-1_script": [{"jobs": [leaf]}]},
                      get={j["jobReference"]["jobId"]: j for j in (parent, leaf)})
    out = run(transport=t)
    assert out["status"] == RW.RECONCILED, out["blockers"]
    assert out["owned"] == ["okf_graph_smoke-1_script", "script_leaf"]
    assert not [c for c in t.calls if c["parent_job_id"] == "script_leaf"], "a leaf has no child listing to drain"


def test_a_parent_that_declares_children_but_produces_none_blocks():
    parent = job("okf_graph_smoke-1_script")
    parent["statistics"]["numChildJobs"] = "1"
    t = FakeTransport(pages=[{"jobs": [parent]}], children={"okf_graph_smoke-1_script": [{"jobs": []}]},
                      get={"okf_graph_smoke-1_script": parent})
    out = run(transport=t)
    assert out["status"] == RW.BLOCKED and any("unreconciled script children" in b for b in out["blockers"])


def test_child_listing_that_stops_early_blocks():
    parent = job("okf_graph_smoke-1_script", children=True)
    parent["statistics"]["numChildJobs"] = "1"
    t = FakeTransport(pages=[{"jobs": [parent]}],
                      children={"okf_graph_smoke-1_script": [{"jobs": [], "nextPageToken": "0"}]},
                      get={"okf_graph_smoke-1_script": parent})
    out = run(transport=t)
    assert out["status"] == RW.BLOCKED and any("incomplete" in b for b in out["blockers"])


def test_recovered_id_the_listing_never_produced_blocks():
    out = run(transport=transport_for(owned_jobs()), recovered=["okf_graph_smoke_ent_20260905234528_1"])
    assert out["status"] == RW.BLOCKED
    assert any("not produced by the listing" in b for b in out["blockers"])


def test_recovered_id_is_owned_when_it_is_listed():
    recovered = job("okf_graph_smoke_ent_20260905234528_1", labels={})
    out = run(transport=transport_for(owned_jobs() + [recovered]), recovered=["okf_graph_smoke_ent_20260905234528_1"])
    assert out["status"] == RW.RECONCILED
    assert "okf_graph_smoke_ent_20260905234528_1" in out["owned"]


def test_window_label_on_a_job_of_another_window_is_not_this_window():
    other = job("okf_graph_all-0012_x", labels={"window": "all-0012"}, created="2026-09-05T23:45:00Z")
    out = run(transport=transport_for(owned_jobs() + [other]))
    assert out["status"] == RW.BLOCKED
    assert [a["ref"]["job_id"] for a in out["ambiguous"]] == ["okf_graph_all-0012_x"]


# ----------------------------------------------------------------------------- readback
def test_running_job_blocks():
    running = job("okf_graph_smoke-1_running", state="RUNNING")
    out = run(transport=transport_for(owned_jobs() + [running]))
    assert out["status"] == RW.BLOCKED
    assert any("not terminal" in b for b in out["blockers"])


def test_not_found_is_unverified_never_done():
    from google.api_core.exceptions import NotFound
    jobs = owned_jobs()
    t = transport_for(jobs)
    t.get[jobs[0]["jobReference"]["jobId"]] = NotFound("no such job")
    out = run(transport=t)
    assert out["status"] == RW.BLOCKED
    assert any("UNVERIFIED, never done" in b for b in out["blockers"])
    rec = next(r for r in out["readbacks"] if r["ref"]["job_id"] == jobs[0]["jobReference"]["jobId"])
    assert rec["readback"] == RW.UNVERIFIED and not rec.get("verified_done")


def test_readback_of_a_different_reference_is_unverified():
    jobs = owned_jobs(n=1)
    t = transport_for(jobs)
    t.get[jobs[0]["jobReference"]["jobId"]] = job("some_other_job")
    out = run(transport=t)
    assert out["status"] == RW.BLOCKED
    assert out["readbacks"][0]["readback"] == RW.UNVERIFIED


def test_a_done_job_that_errored_still_closes_its_obligation():
    failed = job("okf_graph_smoke-1_failed", error={"reason": "invalidQuery"})
    out = run(transport=transport_for(owned_jobs() + [failed]))
    assert out["status"] == RW.RECONCILED
    rec = next(r for r in out["readbacks"] if r["ref"]["job_id"] == "okf_graph_smoke-1_failed")
    assert rec["verified_done"] is True and rec["error_result"] == {"reason": "invalidQuery"}


# ----------------------------------------------------------------------------- quiescence and late entries
def test_quiescence_must_be_evidenced():
    out = run(transport=transport_for(owned_jobs()), quiescent=False)
    assert out["status"] == RW.BLOCKED
    assert any("quiescence" in b for b in out["blockers"])


def test_a_bare_quiescence_boolean_is_not_evidence():
    """`{"established": true}` is an operator opinion, not a record of when submitting stopped (Astra PR47 #8)."""
    out = run(transport=transport_for(owned_jobs()), q={"established": True})
    assert out["status"] == RW.BLOCKED
    assert any("no evidence" in b for b in out["blockers"])
    assert any("no stopped_at" in b for b in out["blockers"])


def test_an_unparsable_stopped_at_blocks():
    out = run(transport=transport_for(owned_jobs()), q=quiescence(stopped_at="last tuesday"))
    assert out["status"] == RW.BLOCKED and any("not a timestamp" in b for b in out["blockers"])


def test_a_declared_source_that_cannot_be_read_blocks(tmp_path):
    out = RW.reconcile("smoke-1", transport=transport_for(owned_jobs()), window=window(),
                       sources=[tmp_path / "launcher-that-was-never-written.log"], quiescence=quiescence())
    assert out["status"] == RW.BLOCKED
    assert any("could not be read" in b for b in out["blockers"])
    assert out["sources"][0]["error"]


def test_the_listing_covers_the_submission_lifetime_not_the_capacity_interval():
    """A submitter that outlived capacity deletion could still have created an owned job (Astra PR47 #7)."""
    late = job("okf_graph_smoke-1_after_capacity_close", created="2026-09-05T23:50:00Z", state="RUNNING")
    t = transport_for(owned_jobs() + [late])
    out = run(transport=t, q=quiescence(stopped_at="2026-09-05T23:51:00Z"))
    assert "okf_graph_smoke-1_after_capacity_close" in [g[2] for g in t.gets], "the tail job was filtered away, not read"
    assert out["status"] == RW.BLOCKED and any("not terminal" in b for b in out["blockers"])
    assert out["window"]["submitters_stopped_at"] == "2026-09-05T23:51:00Z"


def test_the_window_extends_while_owned_work_reaches_its_edge():
    tail = job("okf_graph_smoke-1_tail", created="2026-09-05T23:49:00Z")
    t = transport_for(owned_jobs() + [tail])
    out = run(transport=t, q=quiescence(stopped_at="2026-09-05T23:48:30Z"))
    assert out["status"] == RW.RECONCILED, out["blockers"]
    assert out["window"]["extensions"], "an owned job at the edge must pull the bound forward"
    assert "okf_graph_smoke-1_tail" in out["owned"]


def test_a_script_parent_whose_children_are_not_all_read_blocks():
    parent = job("okf_graph_smoke-1_script", children=True)
    parent["statistics"]["numChildJobs"] = "2"
    child = job("script_child_1", parent="okf_graph_smoke-1_script")
    t = FakeTransport(pages=[{"jobs": [parent]}],
                      children={"okf_graph_smoke-1_script": [{"jobs": [child]}]},
                      get={j["jobReference"]["jobId"]: j for j in (parent, child)})
    out = run(transport=t)
    assert out["status"] == RW.BLOCKED
    assert any("unreconciled script children" in b for b in out["blockers"])


def test_child_listings_are_not_time_filtered():
    """A script child created after the window bound is still a child; a time-filtered page cannot prove membership."""
    parent = job("okf_graph_smoke-1_script", children=True)
    parent["statistics"]["numChildJobs"] = "1"
    child = job("script_child_late", created="2026-09-06T02:00:00Z", parent="okf_graph_smoke-1_script")
    t = FakeTransport(pages=[{"jobs": [parent]}],
                      children={"okf_graph_smoke-1_script": [{"jobs": [child]}]},
                      get={j["jobReference"]["jobId"]: j for j in (parent, child)})
    out = run(transport=t)
    child_calls = [c for c in t.calls if c["parent_job_id"]]
    assert child_calls and all(c["start"] is None and c["end"] is None for c in child_calls)
    assert out["status"] == RW.RECONCILED and "script_child_late" in out["owned"]


def test_a_late_entry_on_the_second_pass_blocks():
    jobs = owned_jobs()
    late = job("okf_graph_smoke-1_late", created="2026-09-05T23:47:00Z")

    class Late(FakeTransport):
        def __init__(self):
            super().__init__(pages=[{"jobs": jobs}], get={j["jobReference"]["jobId"]: j for j in jobs + [late]})
            self.passes = 0

        def list_jobs(self, **kw):
            if kw.get("parent_job_id") is None and kw.get("page_token") is None:
                self.passes += 1
                # call 1 is the lifetime-extension probe, call 2 the first drained pass, call 3 the repeat pass
                if self.passes >= 3:
                    return {"jobs": jobs + [late]}
            return super().list_jobs(**kw)

    out = run(transport=Late())
    assert out["status"] == RW.BLOCKED
    assert out["listing"]["stable"] is False
    assert any("a repeated listing produced" in b for b in out["blockers"])


# ----------------------------------------------------------------------------- staging refuses to launder evidence
def test_blocked_result_stages_nothing(tmp_path):
    out = run(transport=transport_for(owned_jobs()), quiescent=False)
    staged = RW.stage(out, tmp_path)
    assert staged["staged"] is False
    assert not list(tmp_path.iterdir())


def test_stage_never_overwrites_an_original_artifact(tmp_path):
    (tmp_path / "jobs_smoke-1.json").write_text(json.dumps({"label": "smoke-1", "job_ids": ["original"]}))
    result = run(transport=transport_for(owned_jobs()))
    staged = RW.stage(result, tmp_path)
    assert staged["staged"] is False and "never overwritten" in staged["reason"]
    assert json.loads((tmp_path / "jobs_smoke-1.json").read_text())["job_ids"] == ["original"]


def test_a_previous_reconstruction_may_be_replaced_explicitly(tmp_path):
    result = run(transport=transport_for(owned_jobs()))
    assert RW.stage(result, tmp_path)["staged"]
    assert RW.stage(result, tmp_path)["staged"] is False
    assert RW.stage(result, tmp_path, replace_reconstruction=True)["staged"] is True


def test_verified_is_derived_not_accepted(tmp_path):
    """An operator-supplied `verified` in the plan input can never reach the receipt."""
    jobs = owned_jobs()
    t = transport_for(jobs)
    t.get[jobs[0]["jobReference"]["jobId"]] = job(jobs[0]["jobReference"]["jobId"], state="RUNNING")
    out = run(transport=t)
    out["verified"] = True                    # a hostile caller edits the result
    out["status"] = RW.RECONCILED
    staged = RW.stage(out, tmp_path)
    receipt = json.loads((tmp_path / "jobs_smoke-1.cleanup.json").read_text())
    assert staged["verified"] is False and receipt["verified"] is False
    assert L.job_cleanup_verified("smoke-1", tmp_path / "jobs_smoke-1.json") is False


# ----------------------------------------------------------------------------- the gate the reservation module runs
def test_gate_rejects_missing_stale_and_malformed_receipts(tmp_path):
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is False          # missing
    result = run(transport=transport_for(owned_jobs()))
    RW.stage(result, tmp_path)
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is True
    receipt = json.loads((tmp_path / "jobs_smoke-1.cleanup.json").read_text())
    # a receipt for another window
    (tmp_path / "jobs_smoke-1.cleanup.json").write_text(json.dumps(dict(receipt, label="all-0012")))
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is False
    # a receipt for another project
    (tmp_path / "jobs_smoke-1.cleanup.json").write_text(json.dumps(dict(receipt, project="somewhere-else")))
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is False
    # a receipt for another location
    (tmp_path / "jobs_smoke-1.cleanup.json").write_text(json.dumps(dict(receipt, location="EU")))
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is False
    # a partial journal: an id the receipt never closed
    (tmp_path / "jobs_smoke-1.cleanup.json").write_text(json.dumps(receipt))
    journal = json.loads((tmp_path / "jobs_smoke-1.json").read_text())
    (tmp_path / "jobs_smoke-1.json").write_text(json.dumps(dict(journal, job_ids=journal["job_ids"] + ["never_read"])))
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is False
    # malformed bytes
    (tmp_path / "jobs_smoke-1.json").write_text("{not json")
    assert RW.gate(tmp_path, ["smoke-1"])["all_verified"] is False


def test_gate_requires_every_named_label(tmp_path):
    RW.stage(run(transport=transport_for(owned_jobs())), tmp_path)
    verdict = RW.gate(tmp_path, ["smoke-1", "integration-0007"])
    assert verdict["labels"] == {"smoke-1": True, "integration-0007": False}
    assert verdict["all_verified"] is False


# ----------------------------------------------------------------------------- the module performs no mutation
def test_the_module_imports_no_mutating_helper():
    import inspect
    source = inspect.getsource(RW)
    for forbidden in ("close_window", "cancel_journal", "safety_teardown", "stop_and_cancel", "cancel_job"):
        assert forbidden not in source.split('"""')[2], forbidden   # not in the code body (the docstring names them)


def test_rest_transport_issues_only_get():
    seen = []

    class Conn:
        def api_request(self, **kw):
            seen.append(kw)
            return {"jobs": []}

    class Client:
        _connection = Conn()

    t = RW.RestGetTransport(Client())
    start = _dt.datetime(2026, 9, 5, tzinfo=_dt.timezone.utc)
    t.list_jobs(project=PROJ, min_creation_time=start, max_creation_time=start, parent_job_id="p")
    t.get_job(project=PROJ, location=LOC, job_id="j")
    assert [c["method"] for c in seen] == ["GET", "GET"]
    assert seen[0]["query_params"]["allUsers"] is True and seen[0]["query_params"]["projection"] == "FULL"
    assert seen[0]["query_params"]["parentJobId"] == "p"
    t.list_jobs(project=PROJ, min_creation_time=None, max_creation_time=None, parent_job_id="p")
    assert "minCreationTime" not in seen[2]["query_params"]   # a child listing is not time-filtered
    assert "stateFilter" not in seen[0]["query_params"]
    assert seen[1]["query_params"] == {"location": LOC}


# ----------------------------------------------------------------------------- reservation gate still refuses today
def test_the_five_legacy_openings_still_block_a_new_window():
    manifest = json.loads((RES.Path(RES.MANIFEST).read_text()) if RES.os.path.exists(RES.MANIFEST) else '{"windows": []}')
    with pytest.raises(RuntimeError) as e:
        RES.require_clean_windows(manifest)
    assert "job cleanup is unverified" in str(e.value)


def test_require_clean_windows_reads_a_named_evidence_directory(tmp_path):
    """The gate must be able to check a staged reconstruction without publishing it into evidence/ first."""
    manifest = {"windows": [{"label": "smoke-1", "opened_at": OPEN, "closed_at": CLOSE, "verified_gone": True}]}
    with pytest.raises(RuntimeError):
        RES.require_clean_windows(manifest, evidence_dir=tmp_path)
    RW.stage(run(transport=transport_for(owned_jobs())), tmp_path)
    RES.require_clean_windows(manifest, evidence_dir=tmp_path)   # no raise


def test_capacity_bytes_are_preserved_by_a_reconciliation(tmp_path):
    """Reconciling job cleanup must not touch the capacity manifest."""
    manifest = tmp_path / "cleanup_manifest.json"
    original = {"windows": [{"label": "smoke-1", "opened_at": OPEN, "verified_gone": True, "steps": [{"rc": 0}]}]}
    manifest.write_text(json.dumps(original))
    before = manifest.read_bytes()
    RW.stage(run(transport=transport_for(owned_jobs())), tmp_path)
    assert manifest.read_bytes() == before
