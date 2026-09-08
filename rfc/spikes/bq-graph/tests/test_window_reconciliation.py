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
    t.list_jobs(project=PROJ, min_creation_time=start, max_creation_time=start)
    t.get_job(project=PROJ, location=LOC, job_id="j")
    assert [c["method"] for c in seen] == ["GET", "GET"]
    assert seen[0]["query_params"]["allUsers"] is True and seen[0]["query_params"]["projection"] == "FULL"
    assert "stateFilter" not in seen[0]["query_params"]       # no state filter: a listing must not hide a state
    assert seen[1]["query_params"] == {"location": LOC}
    t.list_jobs(project=PROJ, min_creation_time=None, max_creation_time=None, parent_job_id="p")
    assert seen[2]["query_params"]["parentJobId"] == "p"
    assert "minCreationTime" not in seen[2]["query_params"]   # a child listing is not time-filtered


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


# ----------------------------------------------------------------------------- campaign membership + window exclusivity
CAMPAIGN = {"label_key": "okf_spike", "label_value": "bq_graph_20260905", "datasets": ["okf_graph_spike_20260905"]}
W1 = {"label": "smoke-1", "opened_at": OPEN, "closed_at": CLOSE}
W2 = {"label": "later-2", "opened_at": "2026-09-05T23:50:00Z", "closed_at": "2026-09-05T23:55:00Z"}


def spike_job(job_id, *, created=OPEN, query=None, labels=None, **kw):
    j = job(job_id, created=created, labels=labels, **kw)
    j["configuration"]["query"] = {"query": query if query is not None else
                                   "SELECT 1 FROM `p.okf_graph_spike_20260905.nodes`"}
    return j


def classify_one(j, label="smoke-1", windows=(W1, W2), **kw):
    return RW.classify(j, label=label, start=RW._ts(OPEN), end=RW._ts(CLOSE), campaign=CAMPAIGN,
                       windows=windows, **kw)


def test_campaign_signal_reads_a_driver_label_a_query_and_a_load_destination():
    assert "labels.okf_spike" in RW.campaign_signal(job("a", labels={"okf_spike": "bq_graph_20260905"}), CAMPAIGN)
    assert "query text" in RW.campaign_signal(spike_job("b"), CAMPAIGN)
    load = job("c")
    load["configuration"]["load"] = {"destinationTable": {"datasetId": "okf_graph_spike_20260905"}}
    assert "load job writes into" in RW.campaign_signal(load, CAMPAIGN)
    # a job of a DIFFERENT spike on the same project is not campaign work
    other = spike_job("d", query="SELECT 1 FROM `p.okf_receipt_spike_20260905.orders`")
    assert RW.campaign_signal(other, CAMPAIGN) is None
    assert RW.campaign_signal(spike_job("e"), None) is None       # no campaign configured: the signal is off


def test_campaign_work_inside_exactly_one_recorded_interval_is_owned():
    entry = classify_one(spike_job("x", created="2026-09-05T23:45:00Z"))
    assert entry["ownership"] == RW.OWNED and entry["signal"] == "campaign_exclusive_window"
    assert entry["evidence"]["containing_windows"] == ["smoke-1"]


def test_a_job_with_no_campaign_signal_is_still_only_ambiguous_in_span():
    """Time never owns a job on its own: the campaign signal is what the new rule adds, and without it nothing moves."""
    entry = classify_one(job("y", created="2026-09-05T23:45:00Z"))
    assert entry["ownership"] == RW.AMBIGUOUS and entry["signal"] == "in_span"


def test_overlapping_recorded_intervals_make_the_claim_contested_not_owned():
    overlapping = {"label": "later-2", "opened_at": "2026-09-05T23:44:00Z", "closed_at": "2026-09-05T23:50:00Z"}
    entry = classify_one(spike_job("z", created="2026-09-05T23:45:00Z"), windows=(W1, overlapping))
    assert entry["ownership"] == RW.AMBIGUOUS and entry["signal"] == "campaign_contested_window"
    assert "later-2" in entry["reason"]


def test_an_unbounded_opening_contests_every_instant():
    """A window that was opened and never recorded a close cannot be shown to exclude a later job."""
    unbounded = {"label": "later-2", "opened_at": "2026-09-05T23:50:00Z"}
    entry = classify_one(spike_job("z", created="2026-09-05T23:45:00Z"), windows=(W1, unbounded))
    assert entry["ownership"] == RW.AMBIGUOUS and entry["signal"] == "campaign_contested_window"
    assert entry["evidence"]["unbounded_windows"] == ["later-2"]


def test_campaign_work_under_another_opening_is_excluded_but_work_under_none_stays_unresolved():
    """Inside another declared span is a positive assignment. Inside NO span is not: where a job ran does not say
    which invocation submitted it, so it must stay unresolved until invocation evidence settles it (Astra PR50 P1)."""
    other = classify_one(spike_job("a", created="2026-09-05T23:51:00Z"))
    assert other["ownership"] == RW.EXCLUDED and other["signal"] == "campaign_other_window"
    assert other["evidence"]["containing_windows"] == ["later-2"]
    gap = classify_one(spike_job("b", created="2026-09-05T23:48:30Z"))
    assert gap["ownership"] == RW.AMBIGUOUS and gap["signal"] == "campaign_unassigned_invocation"
    assert "which invocation submitted it" in gap["reason"]


def test_the_shared_reservation_name_cannot_override_another_windows_interval():
    """The spike recreated ONE reservation name for every opening, so the name is shared by all five and discriminates
    none of them. A campaign job inside a neighbour's recorded interval belongs to that neighbour, reservation or not."""
    j = spike_job("n", created="2026-09-05T23:51:00Z", reservation=f"p:US.{RW.RESERVATION}")
    entry = classify_one(j)
    assert entry["ownership"] == RW.EXCLUDED and entry["signal"] == "campaign_other_window"
    assert entry["evidence"]["containing_windows"] == ["later-2"]


def test_a_job_on_this_reservation_outside_the_interval_stays_unresolved():
    """The `okf_rcpt_*` tail: capacity deletion propagates late, so a job can carry a reservation the interval says was
    already gone. That contradiction is surfaced and named, never resolved by an exclusion rule."""
    j = spike_job("t", created="2026-09-05T23:48:30Z", reservation=f"p:US.{RW.RESERVATION}")
    entry = classify_one(j)
    assert entry["ownership"] == RW.AMBIGUOUS and entry["signal"] == "campaign_unassigned_invocation"
    assert entry["evidence"]["on_campaign_reservation"] is True
    assert f"on the campaign reservation (p:US.{RW.RESERVATION})" in entry["reason"]


def test_a_closer_only_row_declares_no_interval_and_contests_nothing():
    closer = {"label": "safety-0011", "closed_at": "2026-09-05T23:45:30Z"}
    entry = classify_one(spike_job("x", created="2026-09-05T23:45:00Z"), windows=(W1, closer))
    assert entry["ownership"] == RW.OWNED and entry["signal"] == "campaign_exclusive_window"
    assert RW.containing_windows(RW._ts(OPEN), [closer]) == ([], [])


def test_padding_widens_the_listing_but_never_an_ownership_claim():
    """`pad_s` exists for clock skew between the local stamp and the service's creationTime. A job in the pad is read
    (so it cannot hide) and is NOT silently claimed by the interval - but neither is it dismissed: it is unresolved."""
    just_after = spike_job("p", created="2026-09-05T23:47:50Z")            # 30s past the recorded close
    entry = RW.classify(just_after, label="smoke-1", start=RW._ts(OPEN) - _dt.timedelta(seconds=120),
                        end=RW._ts(CLOSE) + _dt.timedelta(seconds=120), campaign=CAMPAIGN, windows=[W1])
    assert entry["ownership"] == RW.AMBIGUOUS and entry["signal"] == "campaign_unassigned_invocation"


# ------------------------------------------------------- Astra PR50 P1: setup and tails are the invocation's, not the
# ------------------------------------------------------- capacity interval's
def test_a_retained_invocation_span_owns_setup_and_tail_outside_the_capacity_interval():
    """The 2026-09-05 driver resolved the publication pointer BEFORE it stamped `started_at` and opened capacity
    (`run.py@b6e4f09:252-265`), and its watchdog could delete capacity while its own submissions continued. Where the
    driver's run record survived, that span - not the capacity interval - is what owns the work."""
    w = dict(W1, invocation={"started_at": "2026-09-05T23:43:00Z", "finished_at": "2026-09-05T23:48:30Z"})
    assert RW._interval(w) == (RW._ts("2026-09-05T23:43:00Z"), RW._ts("2026-09-05T23:48:30Z"))
    setup = classify_one(spike_job("s", created="2026-09-05T23:43:10Z"), windows=(w, W2))
    tail = classify_one(spike_job("t", created="2026-09-05T23:48:00Z"), windows=(w, W2))
    for entry in (setup, tail):
        assert entry["ownership"] == RW.OWNED and entry["signal"] == "campaign_exclusive_window"


def test_a_pre_opening_pointer_lookup_is_never_silently_dropped():
    """`fccaf7f9…` (00:09:56.310, 0.69s before integration-0009 opens) and `8526efa6…` (00:17:55.499, 0.50s before
    all-0017 opens) are the retained shape: a campaign-labelled active-publication lookup immediately before an
    opening. HEAD excluded both. It must not: with no invocation record covering them they are unresolved, and the
    window blocks until a decision assigns or excludes them."""
    lookup = spike_job("fccaf7f9", created="2026-09-05T23:43:42.310Z",
                       query="SELECT publication_id FROM `p.okf_graph_spike_20260905.active_publication` WHERE b = @b")
    entry = classify_one(lookup)                                   # opens at 23:43:43
    assert entry["ownership"] == RW.AMBIGUOUS and entry["signal"] == "campaign_unassigned_invocation"
    result = RW.reconcile("smoke-1", transport=transport_for([lookup] + [spike_job("in", created="2026-09-05T23:45:00Z")]),
                          window=window(), quiescence=quiescence(), campaign=CAMPAIGN, windows=[W1, W2])
    assert result["status"] == RW.BLOCKED
    assert any("fccaf7f9" in b for b in result["blockers"])
    # and an explicit decision citing the driver's ordering is what resolves it
    decision = {"fccaf7f9": {"ownership": RW.OWNED, "reason": "run.py@b6e4f09:252 resolves the publication pointer "
                                                              "before started_at/open_window: this is smoke-1's setup"}}
    owned = RW.reconcile("smoke-1", transport=transport_for([lookup]), window=window(), quiescence=quiescence(),
                         campaign=CAMPAIGN, windows=[W1, W2], decisions=decision)
    assert owned["status"] == RW.RECONCILED and owned["owned"] == ["fccaf7f9"]


def test_a_running_post_close_continuation_without_a_reservation_blocks_and_refuses_quiescence(tmp_path):
    """Astra's PR50 P1 reproduction: one DONE campaign job inside the interval, and a same-invocation campaign job
    still RUNNING 30s after the close with no reservation, plus a truthful driver-exit record. HEAD excluded the
    running job, never called `jobs.get` on it, and still produced RECONCILED / verified."""
    done = spike_job("uuid-done", created="2026-09-05T23:45:00Z")
    running = spike_job("uuid-running", created="2026-09-05T23:47:50Z", state="RUNNING")
    t = transport_for([done, running])
    q = RW.quiescence_probe(t, label="smoke-1", project=PROJ, window=W1, until=NOW, campaign=CAMPAIGN,
                            windows=[W1, W2], local_record=local_record(stopped_at="2026-09-05T23:48:20Z"))
    assert q["established"] is False
    assert any("non-terminal" in r for r in q["not_established_because"])
    assert [n["ref"]["job_id"] for n in q["probe"]["nonterminal"]] == ["uuid-running"]
    assert q["probe"]["nonterminal"][0]["ownership"] == RW.AMBIGUOUS
    result = RW.reconcile("smoke-1", transport=t, window=window(), quiescence=q, campaign=CAMPAIGN, windows=[W1, W2])
    assert result["status"] == RW.BLOCKED
    assert any("uuid-running" in b for b in result["blockers"])
    assert RW.stage(result, tmp_path)["staged"] is False


def test_reconcile_owns_a_campaign_window_the_local_record_never_named(tmp_path):
    jobs = [spike_job(f"uuid-{i}", created="2026-09-05T23:45:00Z") for i in range(3)]
    result = RW.reconcile("smoke-1", transport=transport_for(jobs), window=window(), quiescence=quiescence(),
                          campaign=CAMPAIGN, windows=[W1, W2])
    assert result["status"] == RW.RECONCILED, result["blockers"]
    assert result["owned"] == ["uuid-0", "uuid-1", "uuid-2"]
    assert {e["signal"] for e in result["ledger"]} == {"campaign_exclusive_window"}
    assert result["campaign"] == CAMPAIGN
    assert RW.stage(result, tmp_path)["verified"] is True


def test_reconcile_still_blocks_on_an_unresolved_neighbour_of_the_campaign(tmp_path):
    jobs = [spike_job("uuid-0", created="2026-09-05T23:45:00Z"),
            job("stranger", created="2026-09-05T23:45:01Z")]         # no campaign signal, inside the span
    result = RW.reconcile("smoke-1", transport=transport_for(jobs), window=window(), quiescence=quiescence(),
                          campaign=CAMPAIGN, windows=[W1, W2])
    assert result["status"] == RW.BLOCKED
    assert any("stranger" in b for b in result["blockers"])
    assert RW.stage(result, tmp_path)["staged"] is False


# ----------------------------------------------------------------------------- derived quiescence
def probe_transport(jobs, **kw):
    return transport_for(jobs, **kw)


def local_record(source="window_all.log", stopped_at="2026-09-05T23:47:30Z", note=None):
    return {"source": source, "stopped_at": stopped_at, "note": note}


NOW = _dt.datetime(2026, 9, 8, 0, 0, tzinfo=_dt.timezone.utc)


def test_quiescence_probe_derives_an_established_record_from_a_silent_platform():
    q = RW.quiescence_probe(probe_transport([]), label="smoke-1", project=PROJ, window=W1, until=NOW,
                            campaign=CAMPAIGN, windows=[W1, W2], local_record=local_record())
    assert q["established"] is True and q["not_established_because"] == []
    assert q["stopped_at"] == "2026-09-05T23:47:30+00:00"          # the named local record, later than the close
    assert "jobs.list drain" in q["evidence"] and q["basis"] == "platform_probe+local_record"
    assert q["local_record"]["gap"] is False
    # and it is usable as the reconcile input, unchanged
    result = RW.reconcile("smoke-1", transport=transport_for([spike_job("u", created="2026-09-05T23:45:00Z")]),
                          window=window(), quiescence=q, campaign=CAMPAIGN, windows=[W1, W2])
    assert result["status"] == RW.RECONCILED, result["blockers"]


def test_an_attributable_tail_after_the_close_is_not_quiescence():
    tail = spike_job("tail", created="2026-09-05T23:47:25Z", reservation=f"p:US.{RW.RESERVATION}")
    q = RW.quiescence_probe(probe_transport([tail]), label="smoke-1", project=PROJ, window=W1, until=NOW,
                            campaign=CAMPAIGN, windows=[W1, W2], local_record=local_record())
    assert q["probe"]["attributable_after_close"][0]["ref"]["job_id"] == "tail"
    assert q["stopped_at"] > "2026-09-05T23:47:25"                 # the stop moment moves to the tail we found


def test_an_unresolved_nonterminal_job_refuses_quiescence():
    running = spike_job("busy", created="2026-09-06T01:00:00Z", state="RUNNING",
                        reservation=f"p:US.{RW.RESERVATION}")     # unresolved: reservation_outside_interval
    q = RW.quiescence_probe(probe_transport([running]), label="smoke-1", project=PROJ, window=W1, until=NOW,
                            campaign=CAMPAIGN, windows=[W1, W2], local_record=local_record())
    assert q["established"] is False
    assert any("non-terminal" in r for r in q["not_established_because"])


def test_an_unrelated_running_job_is_retained_but_does_not_refuse_quiescence():
    """A shared project has live traffic. A recurring transfer that is RUNNING right now says nothing about whether a
    driver killed two days ago stopped submitting - but it is still written down."""
    stranger = job("scheduled_query_x", created="2026-09-08T00:00:00Z", state="RUNNING", email="transfer@example.test")
    q = RW.quiescence_probe(probe_transport([stranger]), label="smoke-1", project=PROJ, window=W1, until=NOW,
                            campaign=CAMPAIGN, windows=[W1, W2], local_record=local_record())
    assert q["established"] is True, q["not_established_because"]
    assert q["probe"]["nonterminal"][0]["ref"]["job_id"] == "scheduled_query_x"
    assert q["probe"]["nonterminal"][0]["ownership"] == RW.EXCLUDED
    assert q["probe"]["attributable_after_close"] == []


def test_an_incomplete_probe_listing_is_never_silence():
    t = FakeTransport(pages=[{"jobs": [], "nextPageToken": "1"}, {"jobs": []}], unreachable=["US"])
    q = RW.quiescence_probe(t, label="smoke-1", project=PROJ, window=W1, until=NOW, campaign=CAMPAIGN,
                            windows=[W1, W2], local_record=local_record())
    assert q["established"] is False
    assert any("incomplete" in r for r in q["not_established_because"])


def test_a_short_silence_and_an_unnamed_local_record_both_refuse():
    soon = _dt.datetime(2026, 9, 5, 23, 48, tzinfo=_dt.timezone.utc)
    q = RW.quiescence_probe(probe_transport([]), label="smoke-1", project=PROJ, window=W1, until=soon,
                            campaign=CAMPAIGN, windows=[W1, W2], local_record=local_record())
    assert q["established"] is False and any("silence" in r for r in q["not_established_because"])
    q2 = RW.quiescence_probe(probe_transport([]), label="smoke-1", project=PROJ, window=W1, until=NOW,
                             campaign=CAMPAIGN, windows=[W1, W2], local_record={})
    assert q2["established"] is False
    assert any("no local shutdown record" in r for r in q2["not_established_because"])


def test_a_retained_gap_in_the_local_record_is_reported_not_filled():
    """`integration-0009` was killed by session teardown with no kill timestamp retained. The gap stays visible and the
    stop moment falls back to what the platform shows."""
    q = RW.quiescence_probe(probe_transport([]), label="smoke-1", project=PROJ, window=W1, until=NOW,
                            campaign=CAMPAIGN, windows=[W1, W2],
                            local_record=local_record(stopped_at=None, note="killed by session teardown"))
    assert q["local_record"] == {"source": "window_all.log", "stopped_at": None, "gap": True,
                                 "note": "killed by session teardown"}
    assert q["established"] is True and q["stopped_at"] == RW._ts(CLOSE).isoformat()
    assert "not proof that the original process object no longer exists" in q["limit"]


# ----------------------------------------------------------------------------- plan construction
def test_recover_job_ids_walks_the_whole_document_and_records_where_it_looked(tmp_path):
    src = tmp_path / "all_x.json"
    src.write_text(json.dumps({"assignment_ready_job": "a1",
                               "cases": [{"timing": {"jobs": [{"job_id": "b1"}, {"job_id": "b2"}]}}],
                               "nested": {"deep": {"deeper": [{"jobId": "c1"}]}},
                               "not_a_job": "ignore-me"}))
    ids = RW.recover_job_ids([src])
    assert sorted(ids) == ["a1", "b1", "b2", "c1"]
    assert ids["b1"] == [f"{src}#/cases/0/timing/jobs/0/job_id"]
    sidecar = tmp_path / "s.jobids"
    sidecar.write_text("d1\nd2\n")
    assert sorted(RW.recover_job_ids([sidecar])) == ["d1", "d2"]
    assert RW.recover_job_ids([tmp_path / "missing.json"]) == {}    # the read error surfaces through source_hashes


def test_build_plan_derives_every_opening_and_declares_the_closer_row(tmp_path):
    manifest = tmp_path / "cleanup_manifest.json"
    manifest.write_text(json.dumps({"project": PROJ, "location": LOC, "windows": [
        {"label": "smoke-1", "opened_at": OPEN, "closed_at": CLOSE, "verified_gone": True},
        {"label": "safety-0011", "closed_at": "2026-09-05T23:50:00Z", "verified_gone": True},
        {"label": "later-2", "opened_at": W2["opened_at"], "closed_at": W2["closed_at"], "verified_gone": True}]}))
    (tmp_path / "smoke.jobids").write_text("okf_graph_smoke_ent_1\n")
    plan = RW.build_plan(manifest, evidence_dir=tmp_path, campaign=CAMPAIGN,
                         recover_from={"smoke-1": ["smoke.jobids"]},
                         local_records={"smoke-1": local_record()})
    assert [w["label"] for w in plan["windows"]] == ["smoke-1", "later-2"]      # the closer row is not an opening
    assert [d["label"] for d in plan["declared"]] == ["smoke-1", "safety-0011", "later-2"]
    smoke = plan["windows"][0]
    assert smoke["recovered"] == ["okf_graph_smoke_ent_1"]
    assert str(manifest) in smoke["sources"]                                    # the manifest is hashed per window
    assert smoke["quiescence"]["probe"]["local_record"]["source"] == "window_all.log"
    assert plan["built_from"][0]["sha256"] and plan["campaign"] == CAMPAIGN


def test_build_plan_carries_operator_decisions_through_to_the_right_window(tmp_path):
    manifest = tmp_path / "m.json"
    manifest.write_text(json.dumps({"windows": [{"label": "smoke-1", "opened_at": OPEN, "closed_at": CLOSE}]}))
    decision = {"stranger": {"ownership": RW.EXCLUDED, "reason": "a scheduled query of an unrelated pipeline"}}
    plan = RW.build_plan(manifest, evidence_dir=tmp_path, decisions={"smoke-1": decision})
    assert plan["windows"][0]["decisions"] == decision


def test_a_child_listing_never_asks_for_all_users():
    """`jobs.list` rejects `allUsers` together with `parentJobId` ("all_users and parent_job_id cannot be combined"),
    so every live child listing failed until the pair was dropped. The child page is caller-scoped as a result, which
    is exactly why membership is proved against the parent's declared `numChildJobs` and not against the page."""
    class Conn:
        def __init__(self):
            self.queries = []

        def api_request(self, *, method, path, query_params):
            self.queries.append((path, dict(query_params)))
            return {"jobs": []}

    class Client:
        def __init__(self):
            self._connection = Conn()

    client = Client()
    t = RW.RestGetTransport(client)
    t.list_jobs(project=PROJ)
    t.list_jobs(project=PROJ, parent_job_id="parent-1")
    top, child = client._connection.queries
    assert top[1]["allUsers"] is True and top[1]["projection"] == "FULL"
    assert "allUsers" not in child[1]
    assert child[1]["parentJobId"] == "parent-1" and child[1]["projection"] == "FULL"


def test_a_short_child_read_keeps_the_window_blocked():
    """A caller-scoped child listing that comes back short of the declared count is not an empty child set."""
    parent = job("okf_graph_smoke-1_p")
    parent["statistics"]["numChildJobs"] = 3
    t = FakeTransport(pages=[{"jobs": [parent]}], children={"okf_graph_smoke-1_p": [{"jobs": []}]},
                      get={"okf_graph_smoke-1_p": parent})
    result = run(transport=t)
    assert result["status"] == RW.BLOCKED
    assert any("script children unreconciled" in b for b in result["blockers"])


def test_only_a_two_sided_invocation_record_may_exclude_work_outside_every_span():
    """The driver's own `started_at`/`finished_at` (or a watcher that only tears down once `pgrep` finds no driver)
    bounds the process at both ends, so it positively did not submit a job created outside that span. A one-sided record - the
    `all-0017` run that never stamped an exit - bounds nothing on that side, and the job stays unresolved."""
    outside = spike_job("o", created="2026-09-05T23:48:30Z")
    both = dict(W1, invocation={"started_at": "2026-09-05T23:43:40Z", "finished_at": "2026-09-05T23:47:30Z"})
    entry = classify_one(outside, windows=(both, W2))
    assert entry["ownership"] == RW.EXCLUDED and entry["signal"] == "outside_retained_invocation"
    assert entry["evidence"]["invocation"]["finished_at"] == "2026-09-05T23:47:30Z"

    one_sided = dict(W1, invocation={"started_at": "2026-09-05T23:43:40Z", "finished_at": None})
    assert RW.closed_invocation([one_sided], "smoke-1") is None
    assert classify_one(outside, windows=(one_sided, W2))["signal"] == "campaign_unassigned_invocation"
    assert classify_one(outside, windows=(W1, W2))["signal"] == "campaign_unassigned_invocation"


def test_a_closed_invocation_record_does_not_excuse_a_running_job_inside_the_span():
    """Exclusion by process lifetime applies to work created outside it. A job inside the span is still owned, and if
    it is not terminal the window blocks - a truthful exit record is not a substitute for a readback."""
    both = dict(W1, invocation={"started_at": "2026-09-05T23:43:40Z", "finished_at": "2026-09-05T23:47:30Z"})
    running = spike_job("r", created="2026-09-05T23:45:00Z", state="RUNNING")
    result = RW.reconcile("smoke-1", transport=transport_for([running]), window=window(), quiescence=quiescence(),
                          campaign=CAMPAIGN, windows=[both, W2])
    assert result["status"] == RW.BLOCKED
    assert any("not terminal" in b and "r=RUNNING" in b for b in result["blockers"])


def test_the_decision_generator_accepts_the_committed_listing_envelope(tmp_path):
    """`episode_listing_index.json` is an object with a `jobs` array, not a bare list; pointing the generator at the
    retained evidence used to die with AttributeError (Astra PR50 P2)."""
    import importlib.util
    import pathlib
    spec = importlib.util.spec_from_file_location(
        "legacy_window_decisions",
        pathlib.Path(__file__).resolve().parent.parent / "bin" / "legacy_window_decisions.py")
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    rows = [{"jobReference": {"projectId": PROJ, "location": LOC, "jobId": "okf_rcpt_x"}, "configuration": {},
             "statistics": {}, "user_email": "operator@example.test"}]
    assert mod.listing_jobs(rows) == rows
    assert mod.listing_jobs({"note": "…", "listing": {}, "jobs": rows}) == rows
    with pytest.raises(SystemExit):
        mod.listing_jobs({"note": "no jobs array here"})
    with pytest.raises(SystemExit):
        mod.listing_jobs("a string")
    envelope = tmp_path / "index.json"
    envelope.write_text(json.dumps({"jobs": rows}))
    out = tmp_path / "d.json"
    mod.main(str(envelope), str(out))
    assert json.loads(out.read_text())["smoke-1"]["okf_rcpt_x"]["ownership"] == "EXCLUDED"


# ------------------------------------------------------- Astra PR50 RR2 P1: the LISTING must cover the ownership span
class FilteringTransport:
    """A `jobs.list` that actually honours `minCreationTime`/`maxCreationTime`, like the service does.

    `FakeTransport` returns its page whatever the bounds are, so it cannot show a job being missed BECAUSE the listing
    started too late. That is the whole defect here, so this transport is what the end-to-end regressions use."""

    def __init__(self, jobs):
        self.jobs = list(jobs)
        self.lists, self.gets = [], []

    def list_jobs(self, *, project, min_creation_time=None, max_creation_time=None, page_token=None, page_size=None,
                  parent_job_id=None):
        self.lists.append({"min": min_creation_time, "max": max_creation_time, "parent": parent_job_id})
        if parent_job_id:
            return {"jobs": []}
        return {"jobs": [j for j in self.jobs
                         if (min_creation_time is None or RW._created(j) >= min_creation_time)
                         and (max_creation_time is None or RW._created(j) <= max_creation_time)]}

    def get_job(self, *, project, location, job_id):
        self.gets.append(job_id)
        return next(j for j in self.jobs if RW.job_ref(j)["job_id"] == job_id)


INVOCATION = {"started_at": "2026-09-05T23:38:00Z", "finished_at": "2026-09-05T23:48:20Z",
              "source": "retained launcher lifetime"}
W_INV = dict(W1, invocation=INVOCATION)


def setup_and_inside(setup_state="DONE"):
    """The retained shape: the invocation starts at 23:38, its campaign setup lookup at 23:39 - both EARLIER than
    `opened_at - pad_s` (23:41:43) - then capacity opens at 23:43:43 and ordinary work runs inside it."""
    setup = spike_job("setup-2339", created="2026-09-05T23:39:00Z", state=setup_state,
                      query="SELECT publication_id FROM `p.okf_graph_spike_20260905.active_publication` WHERE b = @b")
    inside = spike_job("inside-2345", created="2026-09-05T23:45:00Z")
    return setup, inside


def probe_and_reconcile(transport, **kw):
    q = RW.quiescence_probe(transport, label="smoke-1", project=PROJ, window=W_INV, until=NOW, campaign=CAMPAIGN,
                            windows=[W_INV], local_record=local_record(stopped_at=INVOCATION["finished_at"]))
    return q, RW.reconcile("smoke-1", transport=transport, window=W_INV, campaign=CAMPAIGN, windows=[W_INV],
                           quiescence=q, **kw)


def test_the_listing_starts_at_the_invocation_not_at_opened_at_minus_padding():
    """`_interval` owned setup from the invocation start while `reconcile` still listed from `opened_at - pad_s`, so a
    23:39 setup job was OWNED in principle and never read in practice - RECONCILED, verified, gate passing, no
    `jobs.get` for it at all (Astra PR50 RR2 P1)."""
    setup, inside = setup_and_inside()
    t = FilteringTransport([setup, inside])
    q, result = probe_and_reconcile(t)
    assert result["window"]["ownership_start"] == RW._ts(INVOCATION["started_at"]).isoformat()
    assert RW._ts(result["window"]["listing_start"]) <= RW._ts("2026-09-05T23:39:00Z")
    assert result["status"] == RW.RECONCILED, result["blockers"]
    assert result["owned"] == ["inside-2345", "setup-2339"]
    assert "setup-2339" in t.gets                      # it was actually read back, not merely classifiable
    # the inventory drain itself reached back to the invocation start (the post-close quiescence probe, which runs
    # over a later span by design, is not what covers setup)
    inventory = [c for c in t.lists if c["parent"] is None and c["min"] is not None
                 and c["min"] <= RW._ts("2026-09-05T23:38:00Z")]
    assert inventory, t.lists


def test_a_running_setup_job_before_the_capacity_interval_blocks(tmp_path):
    """The RUNNING-setup variant: the job that the narrow listing hid is not terminal. It must be read and it must
    block, rather than being invisible to the gate."""
    setup, inside = setup_and_inside(setup_state="RUNNING")
    t = FilteringTransport([setup, inside])
    q, result = probe_and_reconcile(t)
    assert result["status"] == RW.BLOCKED
    assert any("setup-2339=RUNNING" in b for b in result["blockers"])
    assert RW.stage(result, tmp_path)["staged"] is False
    with pytest.raises(RuntimeError):
        RES.require_clean_windows({"windows": [dict(W_INV, verified_gone=True)]}, evidence_dir=tmp_path)


def test_the_reconciler_refuses_a_listing_narrower_than_the_ownership_span():
    """A belt-and-braces invariant: if the two bounds ever diverge again, the window blocks instead of reporting a
    clean inventory over a subset of its own span."""
    span = RW.effective_span(W_INV, [W_INV], "smoke-1")
    assert span[0] == RW._ts(INVOCATION["started_at"])
    assert span[1] == RW._ts(INVOCATION["finished_at"])
    # a declared row reaching further than the row handed in still widens the listing
    wider = dict(W1, invocation={"started_at": "2026-09-05T23:30:00Z", "finished_at": "2026-09-05T23:50:00Z"})
    merged = RW.effective_span(W1, [wider], "smoke-1")
    assert merged == (RW._ts("2026-09-05T23:30:00Z"), RW._ts("2026-09-05T23:50:00Z"))
    # an unbounded end anywhere stays unbounded, so the caller searches to now rather than to a close stamp
    assert RW.effective_span(dict(W1, closed_at=None), [W1], "smoke-1")[1] is None


def test_the_quiescence_probe_starts_after_the_ownership_span_not_after_capacity():
    """`all-0017`'s evidenced exit is later than its capacity close, and that stretch is the invocation's, covered by
    the main listing. The probe therefore begins where ownership ends."""
    setup, inside = setup_and_inside()
    t = FilteringTransport([setup, inside])
    q, _ = probe_and_reconcile(t)
    assert q["probe"]["since"] == RW._ts(INVOCATION["finished_at"]).isoformat()   # not closed_at 23:47:20
    assert q["established"] is True, q["not_established_because"]
