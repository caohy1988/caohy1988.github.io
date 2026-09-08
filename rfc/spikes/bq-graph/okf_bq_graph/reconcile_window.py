"""Read-only reconciliation of a legacy opened reservation window (Slice A, U1).

`reservation.require_clean_windows` refuses to open a paid window while an earlier OPENED window has no verified
job-cleanup receipt. Five legacy openings (`smoke-1`, `integration-0007`, `integration-0009`, `all-0012`, `all-0017`)
have no `jobs_<label>.json` at all, so there is nothing for `lifecycle.job_cleanup_verified` to verify. This module
rebuilds those two artifacts from evidence that can be established WITHOUT mutating anything:

  * `jobs.list` for the window span - all users, FULL projection, no state filter, every page drained, plus one child
    listing per script parent (`parentJobId`), because top-level listings omit script children;
  * `jobs.get` per owned qualified reference `(project, location, job_id)` for its actual terminal state.

Everything else is a refusal. In particular:

  * an incomplete listing (a page token left behind, a cap hit, an `unreachable` location, a transport error) is
    BLOCKED, never "no more jobs";
  * a job created inside the span with no ownership signal is AMBIGUOUS and blocks; so does a job that only carries the
    window's reservation NAME, because a reservation name or a timestamp alone cannot settle ownership;
  * `NotFound` on a `jobs.get` is UNVERIFIED, never `verified_done`. `lifecycle._cancel_one` may treat NOT_FOUND as
    closed because it journals an id BEFORE submitting it; a legacy submission that was never journaled has no such
    guarantee, so that permissive reading must not be inherited here;
  * a non-terminal (PENDING/RUNNING) job blocks;
  * quiescence of the original submitters is an INPUT that must be evidenced - an `established` boolean with a named
    record AND the moment the last submitter stopped - not inferred from a stable count. A second drained listing that
    adds owned references also blocks;
  * the listing covers the SUBMISSION LIFETIME, not the capacity interval. It is bounded by the later of capacity close
    and evidenced submitter shutdown, then extended while owned work reaches its edge, so a job created after capacity
    was deleted is read rather than filtered away;
  * script children are listed WITHOUT a time filter and reconciled against the parent's declared `numChildJobs`: an
    exhausted time-filtered page is not proof of complete child membership;
  * a declared evidence source that cannot be read is missing evidence and blocks.

Nothing here cancels, deletes or submits. `reservation.close_window`, `lifecycle.cancel_journal`, `safety.cleanup` and
`bin/safety_teardown.sh` are mutations and are deliberately not imported.

A produced journal says `reconstructed: true` and names its evidence sources with their SHA-256; it never poses as a
contemporaneous pre-submission log. `verified` in the receipt is DERIVED here from the readbacks - an operator cannot
hand it in. Staged files land in a caller-chosen directory; promoting them into `evidence/` is a separate, authorized
delivery step, and this module refuses to overwrite an original artifact.

    python3 -m okf_bq_graph.reconcile_window --plan plan.json --stage-dir /tmp/stage        # no transport: BLOCKED
    python3 -m okf_bq_graph.reconcile_window --plan plan.json --stage-dir /tmp/stage --live # authorized operator GET
"""
from __future__ import annotations

import argparse
import datetime as _dt
import hashlib
import json
import os
import sys
from pathlib import Path
from typing import Any, Callable, Iterable, Optional

from . import LOCATION, PROJECT, RESERVATION
from .lifecycle import job_cleanup_verified

BLOCKED, RECONCILED = "BLOCKED", "RECONCILED"
OWNED, EXCLUDED, AMBIGUOUS = "OWNED", "EXCLUDED", "AMBIGUOUS"
TERMINAL, NONTERMINAL, UNVERIFIED = "TERMINAL", "NONTERMINAL", "UNVERIFIED"
DONE = "DONE"
PAGE_SIZE = 1000
LISTED_CAP = 50000     # a refusal to read forever; hitting it is truncation, never "that was all of them"
MAX_PAGES = 1000       # a page stream that never ends (or repeats a token) is truncation too
PAD_S = 120            # clock skew between the recorded local open/close stamps and the service's creationTime


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def _ts(text: str) -> _dt.datetime:
    d = _dt.datetime.fromisoformat(str(text).replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)


def _epoch_ms(value: Any) -> Optional[_dt.datetime]:
    try:
        return _dt.datetime.fromtimestamp(int(value) / 1000, _dt.timezone.utc)
    except (TypeError, ValueError):
        return None


def source_hashes(paths: Iterable[str | os.PathLike]) -> list[dict]:
    """Freeze the local inputs a reconstruction rests on. An unreadable source is retained as an error, not dropped."""
    out = []
    for p in paths:
        path = Path(p)
        try:
            raw = path.read_bytes()
            out.append({"path": str(path), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw)})
        except OSError as e:
            out.append({"path": str(path), "error": f"{type(e).__name__}: {str(e)[:200]}"})
    return out


# ----------------------------------------------------------------------------- references
def job_ref(job: dict) -> dict:
    r = job.get("jobReference") or {}
    return {"project": r.get("projectId"), "location": r.get("location"), "job_id": r.get("jobId")}


def qualified(ref: dict) -> bool:
    return all(isinstance(ref.get(k), str) and ref.get(k) for k in ("project", "location", "job_id"))


def ref_key(ref: dict) -> tuple:
    return (ref.get("project"), ref.get("location"), ref.get("job_id"))


def _stats(job: dict) -> dict:
    return job.get("statistics") or {}


def _labels(job: dict) -> dict:
    labels = ((job.get("configuration") or {}).get("labels")) or {}
    return labels if isinstance(labels, dict) else {}


def _created(job: dict) -> Optional[_dt.datetime]:
    return _epoch_ms(_stats(job).get("creationTime"))


def _stats_parent(entry: dict) -> Optional[str]:
    """The parent id of a ledger entry, from the job resource it was classified from."""
    return _stats(entry.get("source_job") or {}).get("parentJobId")


# ----------------------------------------------------------------------------- listing
def _declared_children(job: dict) -> Optional[int]:
    """How many children this job DECLARES.

    `numChildJobs` is the parent's declaration. `scriptStatistics` is the *child's* own context - the Job API defines
    it as the statistics of a script child, so an ordinary terminal script leaf carries it while declaring nothing
    about children of its own. Reading a leaf's `scriptStatistics` as an undeclared parent blocked perfectly good
    reconciliations (Astra PR47 re-review P2)."""
    stats = _stats(job)
    for key in ("numChildJobs", "num_child_jobs"):
        if key in stats:
            try:
                return int(stats[key])
            except (TypeError, ValueError):
                return None       # a declaration we cannot read is not a count we can reconcile
    return 0


def drain_listing(transport: Any, *, project: str, start: Optional[_dt.datetime], end: Optional[_dt.datetime],
                  parent_job_id: Optional[str] = None, page_size: int = PAGE_SIZE,
                  cap: int = LISTED_CAP) -> dict:
    """Every page of one `jobs.list` call. Returns jobs plus an explicit completeness verdict.

    `complete` is true only when the stream ended with no continuation token, no cap hit, no transport error and no
    `unreachable` location. Callers must not read absence out of an incomplete listing."""
    jobs: list[dict] = []
    pages, token, unreachable, error = 0, None, [], None
    while pages < MAX_PAGES:
        try:
            page = transport.list_jobs(project=project, min_creation_time=start, max_creation_time=end,
                                       page_token=token, page_size=page_size, parent_job_id=parent_job_id)
        except Exception as e:  # noqa: BLE001 - an unread page is not an empty page
            error = f"{type(e).__name__}: {str(e)[:300]}"
            break
        pages += 1
        unreachable += list(page.get("unreachable") or [])
        jobs += list(page.get("jobs") or [])
        token = page.get("nextPageToken")
        if len(jobs) >= cap:
            return {"jobs": jobs[:cap], "pages": pages, "next_page_token": token, "unreachable": unreachable,
                    "error": None, "capped": True, "complete": False, "parent_job_id": parent_job_id}
        if not token:
            break
    capped_pages = pages >= MAX_PAGES and bool(token)
    return {"jobs": jobs, "pages": pages, "next_page_token": token, "unreachable": unreachable, "error": error,
            "capped": capped_pages,
            "complete": error is None and not token and not unreachable, "parent_job_id": parent_job_id}


def list_window(transport: Any, *, project: str, start: _dt.datetime, end: _dt.datetime,
                page_size: int = PAGE_SIZE, cap: int = LISTED_CAP) -> dict:
    """The top-level listing plus one child listing per script parent seen. `jobs.list` does not return script children
    unless they are asked for by `parentJobId`, so a top-level drain alone is a partial inventory."""
    top = drain_listing(transport, project=project, start=start, end=end, page_size=page_size, cap=cap)
    jobs = list(top["jobs"])
    children, seen = [], {j.get("jobReference", {}).get("jobId") for j in jobs}
    frontier = [j for j in jobs if _declared_children(j)]
    complete = top["complete"]
    while frontier:
        parent = frontier.pop()
        pid = (parent.get("jobReference") or {}).get("jobId")
        if not pid:
            complete = False
            continue
        # A child listing is NOT time-filtered. A script child can be created long after its parent - and after the
        # window bound - so exhausting a time-filtered page proves nothing about complete membership. The declared
        # `numChildJobs` is reconciled against what was actually read (Astra PR47 #7).
        page = drain_listing(transport, project=project, start=None, end=None, parent_job_id=pid,
                             page_size=page_size, cap=cap)
        found = len(page["jobs"])
        declared = _declared_children(parent)
        membership_ok = declared is not None and found >= declared
        children.append({"parent": pid, "declared_children": declared, "children_read": found,
                         "membership_reconciled": bool(membership_ok),
                         **{k: page[k] for k in ("pages", "next_page_token", "unreachable", "error", "capped", "complete")}})
        complete = complete and page["complete"] and membership_ok
        for child in page["jobs"]:
            cid = (child.get("jobReference") or {}).get("jobId")
            if cid in seen:
                continue
            seen.add(cid)
            jobs.append(child)
            if _declared_children(child):
                frontier.append(child)
    return {"jobs": jobs, "top": {k: top[k] for k in ("pages", "next_page_token", "unreachable", "error", "capped", "complete")},
            "children": children, "listed": len(jobs), "complete": complete}


# ----------------------------------------------------------------------------- ownership
def classify(job: dict, *, label: str, start: _dt.datetime, end: _dt.datetime, recovered: frozenset = frozenset(),
             owned_parents: frozenset = frozenset(), reservation: str = RESERVATION,
             decisions: Optional[dict] = None) -> dict:
    """One job's ownership decision, with the evidence that produced it.

    An explicit operator decision wins, but only when it carries a reason: a bare override is not evidence. Otherwise
    ownership needs a positive signal that ties the job to THIS window. A job that merely ran inside the span, or that
    only carries the window's reservation name, is AMBIGUOUS and must be resolved explicitly before the window can be
    reconciled - a name or a timestamp cannot settle ownership on a shared project."""
    ref = job_ref(job)
    jid = ref.get("job_id")
    decision = (decisions or {}).get(jid)
    if decision:
        ownership = decision.get("ownership")
        reason = decision.get("reason")
        if ownership not in (OWNED, EXCLUDED) or not reason:
            return {"ref": ref, "ownership": AMBIGUOUS, "signal": "operator_decision_invalid",
                    "reason": "an explicit ownership decision needs ownership OWNED|EXCLUDED and a reason"}
        return {"ref": ref, "ownership": ownership, "signal": "operator_decision", "reason": reason,
                "evidence": decision.get("evidence")}
    labels = _labels(job)
    created = _created(job)
    parent = _stats(job).get("parentJobId")
    if jid in recovered:
        return {"ref": ref, "ownership": OWNED, "signal": "recovered_local_evidence",
                "reason": "the job id appears in retained local evidence for this window"}
    if labels.get("window") == label:
        return {"ref": ref, "ownership": OWNED, "signal": "job_label", "reason": f"configuration.labels.window == {label!r}"}
    if isinstance(jid, str) and jid.startswith(f"okf_graph_{label}_"):
        return {"ref": ref, "ownership": OWNED, "signal": "job_id_prefix", "reason": f"driver job-id prefix okf_graph_{label}_"}
    if parent and parent in owned_parents:
        return {"ref": ref, "ownership": OWNED, "signal": "script_child", "reason": f"script child of owned parent {parent}"}
    reservation_id = _stats(job).get("reservation_id") or _stats(job).get("reservationId")
    if reservation and isinstance(reservation_id, str) and reservation_id.endswith(reservation):
        return {"ref": ref, "ownership": AMBIGUOUS, "signal": "reservation_name",
                "reason": "the job names this window's reservation, but a reservation name alone does not settle "
                          "ownership: resolve it explicitly with invocation evidence"}
    if created is not None and start <= created <= end:
        return {"ref": ref, "ownership": AMBIGUOUS, "signal": "in_span",
                "reason": "created inside the window span with no ownership signal on a shared project"}
    if created is None:
        return {"ref": ref, "ownership": AMBIGUOUS, "signal": "no_creation_time",
                "reason": "no creationTime: the job cannot be placed inside or outside the window"}
    return {"ref": ref, "ownership": EXCLUDED, "signal": "outside_span",
            "reason": "created outside the window span and carries no signal tying it to this window"}


# ----------------------------------------------------------------------------- terminal readback
def read_back(transport: Any, refs: list[dict]) -> list[dict]:
    """`jobs.get` per qualified reference, with its EXACT project and location. A 404, a transport failure, a missing
    state or a returned reference that is not the one requested leaves the job UNVERIFIED."""
    out = []
    for ref in refs:
        if not qualified(ref):
            out.append({"ref": ref, "readback": UNVERIFIED, "reason": "reference is not qualified (project, location, job_id)"})
            continue
        try:
            job = transport.get_job(project=ref["project"], location=ref["location"], job_id=ref["job_id"])
        except Exception as e:  # noqa: BLE001
            out.append({"ref": ref, "readback": UNVERIFIED, "reason": f"{type(e).__name__}: {str(e)[:250]}"})
            continue
        got = job_ref(job)
        if ref_key(got) != ref_key(ref):
            out.append({"ref": ref, "readback": UNVERIFIED, "reason": f"jobs.get returned a different reference: {got}"})
            continue
        state = (job.get("status") or {}).get("state")
        stats = _stats(job)
        rec = {"ref": ref, "state": state, "user_email": job.get("user_email") or job.get("userEmail"),
               "error_result": (job.get("status") or {}).get("errorResult"),
               "created": (_created(job) or _epoch_ms(stats.get("creationTime")) or None),
               "ended": _epoch_ms(stats.get("endTime")),
               "parent_job_id": stats.get("parentJobId"),
               "reservation_id": stats.get("reservation_id") or stats.get("reservationId"),
               "edition": stats.get("edition"), "read_at": _now()}
        rec["created"] = rec["created"].isoformat() if rec["created"] else None
        rec["ended"] = rec["ended"].isoformat() if rec["ended"] else None
        if state == DONE:
            rec["readback"] = TERMINAL
            # an errored or cancelled job is terminal: the OBLIGATION is closed even though the work failed
            rec["verified_done"] = True
            rec["declared_children"] = _declared_children(job)
        elif state in ("PENDING", "RUNNING"):
            rec["readback"] = NONTERMINAL
            rec["verified_done"] = False
            rec["reason"] = f"job state {state}: not terminal"
        else:
            rec["readback"] = UNVERIFIED
            rec["verified_done"] = False
            rec["reason"] = f"unknown job state {state!r}"
        out.append(rec)
    return out


# ----------------------------------------------------------------------------- reconciliation
def reconcile(label: str, *, transport: Any, window: dict, sources: Iterable[str | os.PathLike] = (),
              recovered: Iterable[str] = (), decisions: Optional[dict] = None,
              quiescence: Optional[dict] = None, project: str = PROJECT, location: str = LOCATION,
              reservation: str = RESERVATION, pad_s: int = PAD_S, page_size: int = PAGE_SIZE,
              cap: int = LISTED_CAP, passes: int = 2) -> dict:
    """Reconstruct one window's job inventory read-only. Returns RECONCILED only when the inventory is complete AND
    every owned job read back terminal AND the original submitters are evidenced quiescent."""
    blockers: list[str] = []
    opened, closed = window.get("opened_at"), window.get("closed_at")
    out: dict[str, Any] = {"label": label, "project": project, "location": location, "reconstructed": True,
                           "reconciled_at": _now(), "sources": source_hashes(sources),
                           "recovered_ids": sorted({r for r in recovered if r}),
                           "decisions": {k: dict(v) for k, v in (decisions or {}).items()},
                           "quiescence": dict(quiescence or {"established": False, "evidence": "not supplied"}),
                           "procedure": "read-only jobs.list (all users, FULL, every page, script children) + jobs.get "
                                        "per owned qualified reference; no cancellation, deletion or submission"}
    if not opened:
        out.update(status=BLOCKED, blockers=["the manifest row has no opened_at: it is a closer record, not an opening"])
        return out
    if transport is None:
        out.update(status=BLOCKED, blockers=["no read-only GET transport was configured: the reconciliation did not run"])
        return out
    # a source the reconstruction declares but cannot read is missing evidence, not a footnote (Astra PR47 #8)
    unreadable = [src["path"] for src in out["sources"] if src.get("error")]
    if unreadable:
        blockers.append(f"{len(unreadable)} declared evidence source(s) could not be read: " + ", ".join(unreadable)[:400])

    # quiescence must be EVIDENCED, not asserted: a bare boolean is an operator opinion, and the moment the last
    # submitter stopped is what actually bounds the listing (Astra PR47 #7, #8)
    q = out["quiescence"]
    stopped_at = None
    if not q.get("established"):
        blockers.append("quiescence of the original submitters is not established: a later job could still appear")
    else:
        if not str(q.get("evidence") or "").strip():
            blockers.append("quiescence is asserted with no evidence: name the launcher/session record that shows the "
                            "submitting processes stopped")
        if not q.get("stopped_at"):
            blockers.append("quiescence has no stopped_at: without the moment the last submitter stopped, the listing "
                            "cannot cover the submission lifetime")
        else:
            try:
                stopped_at = _ts(q["stopped_at"])
            except (TypeError, ValueError):
                blockers.append(f"quiescence stopped_at {q.get('stopped_at')!r} is not a timestamp")

    start = _ts(opened) - _dt.timedelta(seconds=pad_s)
    # the listing covers the SUBMISSION LIFETIME, not the capacity interval: a submitter that outlived capacity
    # deletion could still have created an owned job after it
    base_end = _ts(closed) if closed else _dt.datetime.now(_dt.timezone.utc)
    if stopped_at is not None and stopped_at > base_end:
        base_end = stopped_at
    end = base_end + _dt.timedelta(seconds=pad_s)
    out["window"] = {"opened_at": opened, "closed_at": closed, "pad_s": pad_s,
                     "submitters_stopped_at": q.get("stopped_at"),
                     "listing_start": start.isoformat(), "listing_end": end.isoformat(),
                     "closed_at_present": bool(closed),
                     "bound_note": "the listing is bounded by the later of capacity close and evidenced submitter "
                                   "shutdown, then extended while owned work reaches the edge"}

    # extend while an owned job reaches the edge of the window: a tail can pull the bound forward
    extensions = []
    for _attempt in range(4):
        probe = list_window(transport, project=project, start=start, end=end, page_size=page_size, cap=cap)
        edge = end - _dt.timedelta(seconds=pad_s)
        latest = None
        for job in probe["jobs"]:
            entry = classify(job, label=label, start=start, end=end, recovered=frozenset(out["recovered_ids"]),
                             reservation=reservation, decisions=decisions)
            if entry["ownership"] == EXCLUDED:
                continue
            for stamp in (_created(job), _epoch_ms(_stats(job).get("endTime"))):
                if stamp is not None and (latest is None or stamp > latest):
                    latest = stamp
        if latest is None or latest <= edge:
            break
        end = latest + _dt.timedelta(seconds=pad_s)
        extensions.append({"extended_to": end.isoformat(), "reason": "owned work reached the edge of the window"})
    else:
        blockers.append("the window kept extending: owned work never stopped reaching its edge, so the submission "
                        "lifetime is not bounded")
    out["window"]["extensions"] = extensions
    out["window"]["listing_end"] = end.isoformat()

    listings = [list_window(transport, project=project, start=start, end=end, page_size=page_size, cap=cap)
                for _ in range(max(1, passes))]
    listing = listings[0]
    out["listing"] = {"passes": len(listings), "listed": listing["listed"], "complete": listing["complete"],
                      "top": listing["top"], "children": listing["children"]}
    if not listing["complete"]:
        unreconciled = [c["parent"] for c in listing["children"] if not c.get("membership_reconciled")]
        detail = (f"; script children unreconciled for {unreconciled}" if unreconciled else "")
        blockers.append("the platform listing is incomplete (page token, cap, unreachable location, transport error or "
                        "unreconciled script children): what was read is a prefix of the window" + detail)

    recovered_set = frozenset(out["recovered_ids"])
    # two passes: parents first (so a child's parent is already classified), then children of owned parents
    ledger: list[dict] = []
    owned_parents: set = set()
    for _round in range(len(listing["jobs"]) + 1):     # to a fixpoint: a chain of script children resolves generation by generation
        ledger = [dict(classify(job, label=label, start=start, end=end, recovered=recovered_set,
                                owned_parents=frozenset(owned_parents), reservation=reservation, decisions=decisions),
                       source_job=job)
                  for job in listing["jobs"]]
        grown = {e["ref"]["job_id"] for e in ledger if e["ownership"] == OWNED and e["ref"].get("job_id")}
        if grown == owned_parents:
            break
        owned_parents = grown

    listed_keys = {ref_key(job_ref(j)) for j in listing["jobs"]}
    for entry in ledger:
        if entry["ownership"] == OWNED and not qualified(entry["ref"]):
            entry["ownership"] = AMBIGUOUS
            entry["signal"] = "unqualified_reference"
            entry["reason"] = "an owned job needs a full (project, location, job_id) reference"
    ambiguous = [e for e in ledger if e["ownership"] == AMBIGUOUS]
    if ambiguous:
        blockers.append(f"{len(ambiguous)} listed job(s) could not be classified; resolve each explicitly: "
                        + ", ".join(sorted(str(e["ref"].get("job_id")) for e in ambiguous))[:600])

    owned = [e for e in ledger if e["ownership"] == OWNED]
    owned_ids = {e["ref"]["job_id"] for e in owned}
    # a locally recovered id the platform listing never produced: the union is bigger than what was read
    listed_ids = {job_ref(j).get("job_id") for j in listing["jobs"]}
    unlisted_recovered = sorted(i for i in recovered_set if i not in owned_ids)
    if unlisted_recovered:
        absent = [i for i in unlisted_recovered if i not in listed_ids]
        reclassified = [i for i in unlisted_recovered if i in listed_ids]
        if absent:
            blockers.append(f"{len(absent)} recovered job id(s) were not produced by the listing: " + ", ".join(absent)[:400])
        if reclassified:
            blockers.append(f"{len(reclassified)} recovered job id(s) were listed but classified away from OWNED by an "
                            "explicit decision: " + ", ".join(reclassified)[:400])

    if len(listings) > 1:
        later = set()
        for extra in listings[1:]:
            for job in extra["jobs"]:
                entry = classify(job, label=label, start=start, end=end, recovered=recovered_set,
                                 owned_parents=frozenset(owned_parents), reservation=reservation, decisions=decisions)
                if entry["ownership"] != EXCLUDED:
                    later.add(entry["ref"].get("job_id"))
            if not extra["complete"]:
                blockers.append("a repeated listing pass was itself incomplete")
        new = sorted(i for i in later if i and i not in owned_ids and i not in {e["ref"].get("job_id") for e in ambiguous})
        out["listing"]["stable"] = not new
        if new:
            blockers.append(f"a repeated listing produced {len(new)} reference(s) the first pass did not: " + ", ".join(new)[:400])

    readbacks = read_back(transport, [e["ref"] for e in owned])

    # The TERMINAL parent snapshot governs child membership. Submitter shutdown does not stop an already-running
    # server-side script: a parent that listed as RUNNING with one child can finish a second statement between the
    # last listing pass and its own `jobs.get`. Its terminal `numChildJobs` is the only complete declaration, so a
    # count that has grown is drained and read again, to a fixpoint (Astra PR47 re-review R6).
    child_rounds = []
    for _round in range(4):
        short = []
        for rec in readbacks:
            declared = rec.get("declared_children")
            if not declared:
                continue
            parent_id = rec["ref"]["job_id"]
            observed = sum(1 for e in owned if _stats_parent(e) == parent_id)
            if observed < declared:
                short.append({"parent": parent_id, "declared": declared, "observed": observed})
        if not short:
            break
        child_rounds.append(short)
        discovered = []
        for entry in short:
            page = drain_listing(transport, project=project, start=None, end=None, parent_job_id=entry["parent"],
                                 page_size=page_size, cap=cap)
            entry.update({k: page[k] for k in ("pages", "next_page_token", "unreachable", "error", "complete")})
            if not page["complete"]:
                continue
            for child in page["jobs"]:
                ref = job_ref(child)
                if ref["job_id"] in owned_ids:
                    continue
                if not qualified(ref):
                    blockers.append(f"a child of {entry['parent']} has no qualified reference: {ref}")
                    continue
                owned_ids.add(ref["job_id"])
                record = {"ref": ref, "ownership": OWNED, "signal": "script_child",
                          "reason": f"script child of owned parent {entry['parent']}, revealed by its terminal snapshot",
                          "source_job": child}
                owned.append(record)
                ledger.append(record)
                discovered.append(ref)
        if not discovered:
            break
        readbacks += read_back(transport, discovered)
    else:
        blockers.append("script child membership never settled: the terminal parent snapshot kept declaring more "
                        "children than could be read")
    still_short = [entry for round_ in child_rounds[-1:] for entry in round_
                   if sum(1 for e in owned if _stats_parent(e) == entry["parent"]) < entry["declared"]]
    if still_short:
        blockers.append("the terminal parent snapshot declares more children than were read: "
                        + ", ".join(f'{e["parent"]} declares {e["declared"]}, read '
                                    f'{sum(1 for o in owned if _stats_parent(o) == e["parent"])}' for e in still_short)[:400])
    out["child_membership"] = child_rounds

    by_id = {r["ref"]["job_id"]: r for r in readbacks}
    for entry in owned:
        entry["readback"] = by_id.get(entry["ref"]["job_id"], {})
    nonterminal = [r for r in readbacks if r.get("readback") == NONTERMINAL]
    unverified = [r for r in readbacks if r.get("readback") == UNVERIFIED]
    if nonterminal:
        blockers.append(f"{len(nonterminal)} owned job(s) are not terminal: "
                        + ", ".join(sorted(f'{r["ref"]["job_id"]}={r.get("state")}' for r in nonterminal))[:400])
    if unverified:
        blockers.append(f"{len(unverified)} owned job(s) could not be read back to a terminal state (a 404 or an "
                        "unreadable job is UNVERIFIED, never done): "
                        + ", ".join(sorted(f'{r["ref"]["job_id"]}: {r.get("reason")}' for r in unverified))[:600])
    if not owned and not blockers:
        blockers.append("no owned job was established for an opened window: an empty inventory is not evidence of an "
                        "empty window")

    out["ledger"] = [{k: v for k, v in e.items() if k != "source_job"} for e in ledger]
    out["owned"] = sorted(owned_ids)
    out["owned_refs"] = sorted((e["ref"] for e in owned), key=lambda r: r["job_id"])
    out["excluded"] = [{"ref": e["ref"], "reason": e["reason"], "signal": e["signal"]} for e in ledger if e["ownership"] == EXCLUDED]
    out["ambiguous"] = [{"ref": e["ref"], "reason": e["reason"], "signal": e["signal"]} for e in ambiguous]
    out["readbacks"] = readbacks
    out["listed_keys"] = len(listed_keys)
    out["blockers"] = blockers
    out["status"] = RECONCILED if not blockers else BLOCKED
    return out


# ----------------------------------------------------------------------------- staging
def _receipt_of(result: dict) -> dict:
    jobs = [{"job_id": r["ref"]["job_id"], "project": r["ref"]["project"], "location": r["ref"]["location"],
             "state": r.get("state"), "verified_done": bool(r.get("verified_done")), "error": r.get("error_result"),
             "read_at": r.get("read_at"), "reason": r.get("reason")} for r in result.get("readbacks", [])]
    done = sorted({j["job_id"] for j in jobs if j["verified_done"]})
    ids = sorted(result.get("owned", []))
    return {"label": result["label"], "project": result["project"], "location": result["location"],
            "job_ids": ids, "verified_done_job_ids": done, "jobs": jobs,
            # DERIVED here from the readbacks; never accepted from an operator input
            "verified": bool(ids) and set(ids) <= set(done),
            "reconstructed": True,
            "reconstruction_note": "reconstructed read-only from platform listings/readbacks; not a contemporaneous "
                                   "cleanup receipt, and no cancellation was performed"}


def _journal_of(result: dict) -> dict:
    return {"label": result["label"], "project": result["project"], "location": result["location"],
            "job_ids": sorted(result.get("owned", [])),
            "finished_job_ids": sorted({r["ref"]["job_id"] for r in result.get("readbacks", []) if r.get("verified_done")}),
            "job_refs": result.get("owned_refs", []),
            "reconstructed": True,
            "reconstructed_at": result.get("reconciled_at"),
            "reconstruction_note": "RECONSTRUCTED from read-only platform evidence after the fact. This is NOT the "
                                   "contemporaneous pre-submission journal the driver writes; no such file survived "
                                   "for this window.",
            "reconstruction": {"procedure": result.get("procedure"), "window": result.get("window"),
                               "sources": result.get("sources"), "recovered_ids": result.get("recovered_ids"),
                               "decisions": result.get("decisions"), "quiescence": result.get("quiescence"),
                               "listing": result.get("listing"), "excluded": result.get("excluded")}}


def stage(result: dict, stage_dir: str | os.PathLike, replace_reconstruction: bool = False) -> dict:
    """Materialize `jobs_<label>.json` + `jobs_<label>.cleanup.json` for a RECONCILED result, in a caller-owned
    staging directory. A BLOCKED result stages nothing. An existing ORIGINAL artifact is never overwritten."""
    d = Path(stage_dir)
    d.mkdir(parents=True, exist_ok=True)
    journal_path = d / f"jobs_{result['label']}.json"
    receipt_path = d / f"jobs_{result['label']}.cleanup.json"
    if result.get("status") != RECONCILED:
        return {"staged": False, "reason": f"result is {result.get('status')}: nothing is staged from unreconciled evidence",
                "blockers": result.get("blockers", [])}
    for path in (journal_path, receipt_path):
        if path.exists():
            try:
                existing = json.loads(path.read_text(encoding="utf-8"))
            except (OSError, ValueError):
                existing = {}
            if not (existing.get("reconstructed") is True and replace_reconstruction):
                return {"staged": False, "reason": f"{path} already exists; an original artifact is never overwritten"}
    journal = _journal_of(result)
    raw = json.dumps(journal, indent=2, sort_keys=True, default=str) + "\n"
    receipt = _receipt_of(result)
    receipt["journal_sha256"] = hashlib.sha256(raw.encode("utf-8")).hexdigest()
    journal_path.write_text(raw, encoding="utf-8")
    receipt_path.write_text(json.dumps(receipt, indent=2, sort_keys=True, default=str) + "\n", encoding="utf-8")
    return {"staged": True, "journal": str(journal_path), "receipt": str(receipt_path),
            "job_ids": journal["job_ids"], "verified": receipt["verified"],
            "journal_sha256": receipt["journal_sha256"]}


def gate(stage_dir: str | os.PathLike, labels: Iterable[str]) -> dict:
    """Re-run the structural cleanup gate against staged files only. Pure file reads: no transport, no cloud."""
    d = Path(stage_dir)
    per = {label: job_cleanup_verified(label, d / f"jobs_{label}.json") for label in labels}
    return {"stage_dir": str(d), "labels": per, "all_verified": bool(per) and all(per.values())}


# ----------------------------------------------------------------------------- live transport (read-only)
class RestGetTransport:
    """`jobs.list` / `jobs.get` over the BigQuery REST API through an authorized client's connection.

    Only HTTP GET is issued. `INFORMATION_SCHEMA` is deliberately not used: querying it would itself submit a job."""

    def __init__(self, client: Any):
        self.client = client

    def list_jobs(self, *, project: str, min_creation_time=None, max_creation_time=None, page_token=None,
                  page_size: int = PAGE_SIZE, parent_job_id: Optional[str] = None) -> dict:
        params: dict[str, Any] = {"allUsers": True, "projection": "FULL", "maxResults": page_size}
        if min_creation_time is not None:
            params["minCreationTime"] = int(min_creation_time.timestamp() * 1000)
        if max_creation_time is not None:
            params["maxCreationTime"] = int(max_creation_time.timestamp() * 1000)
        if page_token:
            params["pageToken"] = page_token
        if parent_job_id:
            params["parentJobId"] = parent_job_id
        return self.client._connection.api_request(method="GET", path=f"/projects/{project}/jobs", query_params=params)

    def get_job(self, *, project: str, location: str, job_id: str) -> dict:
        return self.client._connection.api_request(method="GET", path=f"/projects/{project}/jobs/{job_id}",
                                                   query_params={"location": location})


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="read-only reconstruction of a legacy window's job journal + cleanup receipt")
    ap.add_argument("--plan", required=True, help="JSON: {windows: [{label, opened_at, closed_at, sources, recovered, "
                                                  "decisions, quiescence}], project, location}")
    ap.add_argument("--stage-dir", required=True, help="directory the staged artifacts are written to (never evidence/)")
    ap.add_argument("--live", action="store_true", help="build the authorized operator GET transport (read-only)")
    ap.add_argument("--pad-s", type=int, default=PAD_S)
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE)
    ap.add_argument("--cap", type=int, default=LISTED_CAP)
    ap.add_argument("--replace-reconstruction", action="store_true",
                    help="allow replacing a previously STAGED reconstruction (never an original artifact)")
    a = ap.parse_args(argv)
    plan = json.loads(Path(a.plan).read_text(encoding="utf-8"))
    transport = None
    if a.live:
        from google.cloud import bigquery
        transport = RestGetTransport(bigquery.Client(project=plan.get("project", PROJECT),
                                                     location=plan.get("location", LOCATION)))
    results = []
    for w in plan.get("windows", []):
        result = reconcile(w["label"], transport=transport, window=w, sources=w.get("sources", []),
                           recovered=w.get("recovered", []), decisions=w.get("decisions"),
                           quiescence=w.get("quiescence"), project=plan.get("project", PROJECT),
                           location=plan.get("location", LOCATION), pad_s=a.pad_s, page_size=a.page_size, cap=a.cap)
        staged = stage(result, a.stage_dir, replace_reconstruction=a.replace_reconstruction)
        Path(a.stage_dir).mkdir(parents=True, exist_ok=True)
        (Path(a.stage_dir) / f"reconcile_{w['label']}.json").write_text(
            json.dumps({"result": result, "staged": staged}, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
        results.append((result, staged))
        print(f"{w['label']:20s} status={result['status']:10s} owned={len(result.get('owned', []))} "
              f"staged={staged['staged']} blockers={len(result.get('blockers', []))}")
        for b in result.get("blockers", []):
            print(f"    BLOCKED: {b}")
    verdict = gate(a.stage_dir, [w["label"] for w in plan.get("windows", [])])
    print(json.dumps(verdict, indent=1))
    return 0 if all(r["status"] == RECONCILED for r, _ in results) and verdict["all_verified"] else 1


if __name__ == "__main__":
    sys.exit(main())
