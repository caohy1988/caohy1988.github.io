"""Reconcile a retained chain record's job inventory against the platform's own job list (Astra PR 45 #1).

The chain records the jobs it knows it submitted. That is a claim about its own bookkeeping, not about the run: a job it
forgot to retain is invisible to it by construction. This module reads `jobs.list` + `jobs.get` for the record's own run
window under the OPERATOR - no query is submitted, no grant is changed - and compares the two sets.

A listing that stopped with pages left is `INDETERMINATE`, never a pass: a complete match against a prefix of the window
proves nothing about the rest of it.

The verdict is deliberately asymmetric. A job in the window carrying the REQUESTER's identity that the record does not
list means the inventory understated what the requester did: `INCOMPLETE`. A job carrying some other identity is
reported but does not by itself condemn the record, because the project is shared and the operator has other work; the
run's claim is about the requester. An inventory job the listing cannot produce is also `INCOMPLETE` - the record
references a job the platform did not show for that window.

    python3 -m okf_bq_graph.job_audit evidence/chain/chain_live_restricted.json
"""
from __future__ import annotations

import argparse
import datetime as _dt
import json
import sys
from pathlib import Path
from typing import Any, Optional

from . import LOCATION, PROJECT

PAD_S = 60        # the window is the record's own start/finish, padded for clock skew between the client and the service
PAGE_SIZE = 1000  # how many jobs per HTTP page. NOT a cap on the listing: `max_results` would cap the whole iterator
MAX_LISTED = 50000  # a refusal to read an unbounded window forever; hitting it is truncation, never a pass


def _ts(text: str) -> _dt.datetime:
    d = _dt.datetime.fromisoformat(text.replace("Z", "+00:00"))
    return d if d.tzinfo else d.replace(tzinfo=_dt.timezone.utc)


def inventory(record: dict) -> dict:
    """Every job id the record claims, by the role it claims it under."""
    inv = record.get("job_inventory") or {}
    roles = {"graph": list(inv.get("graph") or []), "receipt": [j for j in (inv.get("receipt") or []) if j],
             "requester_probe": list(inv.get("requester_probe") or []), "policy_admin": list(inv.get("policy_admin") or [])}
    return {"roles": roles, "ids": sorted({j for ids in roles.values() for j in ids})}


def list_window(client: Any, start: _dt.datetime, end: _dt.datetime, page_size: int = PAGE_SIZE,
                cap: int = MAX_LISTED) -> tuple[list[dict], bool]:
    """Every job created in the window, all users, ALL PAGES. Read-only. Returns `(jobs, truncated)`.

    `max_results` caps the whole iterator rather than the page, so a window with more jobs than the cap returns a full
    prefix and leaves a continuation token behind - and a reconciliation that simply iterated it would report a complete
    match while never seeing the rest of the window (Astra PR 45 re-review #4). Paging is therefore controlled with
    `page_size`, the iterator is drained, and anything that stops it early is reported as truncation."""
    it = client.list_jobs(all_users=True, min_creation_time=start, max_creation_time=end, page_size=page_size)
    out: list[dict] = []
    truncated = False
    for j in it:
        out.append({"job_id": j.job_id, "user_email": j.user_email, "state": j.state,
                    "job_type": getattr(j, "job_type", None),
                    "created": j.created.isoformat() if j.created else None,
                    "error": (j.error_result or {}).get("reason") if getattr(j, "error_result", None) else None})
        if len(out) >= cap:
            truncated = True
            break
    if getattr(it, "next_page_token", None):   # pages left behind: what was read is not the window
        truncated = True
    return out, truncated


def audit(record: dict, client: Any = None, requester_email: Optional[str] = None, pad_s: int = PAD_S,
          page_size: int = PAGE_SIZE, cap: int = MAX_LISTED) -> dict:
    from .authz import redact, restricted_sa
    requester_email = requester_email or restricted_sa()
    inv = inventory(record)
    start, end = _ts(record["started_at"]) - _dt.timedelta(seconds=pad_s), _ts(record["finished_at"]) + _dt.timedelta(seconds=pad_s)
    out: dict = {"audit": "read-only jobs.list + jobs.get over the record's own run window; no query submitted, no grant changed",
                 "run_id": record.get("run_id"), "chain": record.get("chain"), "mode": record.get("mode"),
                 "window": {"start": start.isoformat(), "end": end.isoformat(), "pad_s": pad_s},
                 "inventory": {"total": len(inv["ids"]), "by_role": {r: len(ids) for r, ids in inv["roles"].items()}}}
    if client is None:
        from google.cloud import bigquery
        client = bigquery.Client(project=PROJECT, location=LOCATION)
    try:
        listed, truncated = list_window(client, start, end, page_size=page_size, cap=cap)
    except Exception as e:  # noqa: BLE001 - an audit that could not read is UNAVAILABLE, never a pass
        out.update(status="UNAVAILABLE", reason=f"{type(e).__name__}: {str(e)[:200]}")
        return redact(out)
    by_id = {j["job_id"]: j for j in listed}
    claimed = set(inv["ids"])
    extra = [j for j in listed if j["job_id"] not in claimed]
    unaccounted_requester = sorted(j["job_id"] for j in extra if j["user_email"] == requester_email)
    not_listed = sorted(j for j in claimed if j not in by_id)
    identities: dict[str, int] = {}
    for j in listed:
        identities[j["user_email"] or "<none>"] = identities.get(j["user_email"] or "<none>", 0) + 1
    out.update(listed=len(listed), identity_counts=identities,
               matched=len(claimed) - len(not_listed),
               not_listed=not_listed,
               unaccounted_requester_jobs=unaccounted_requester,
               unaccounted_other_jobs=sorted(j["job_id"] for j in extra if j["user_email"] != requester_email),
               unaccounted_other_note="other identities in the same window are reported, not condemned: the project is shared "
                                      "and the operator has work outside this run; the run's claim is about the requester",
               jobs=sorted(listed, key=lambda j: (j["created"] or "", j["job_id"])))
    # the record's own declaration of administrative work it could not name. An audit must not certify a run that
    # already says it lost track of its own jobs, and must not let those become somebody else's unrelated work.
    unresolved_admin = list((record.get("job_inventory") or {}).get("policy_admin_unresolved") or [])
    out["truncated"] = truncated
    out["declared_admin_unresolved"] = len(unresolved_admin)
    reasons = []
    if unaccounted_requester:
        reasons.append(f"{len(unaccounted_requester)} requester job(s) in the window are absent from the inventory")
    if not_listed and not truncated:
        reasons.append(f"{len(not_listed)} inventory job(s) were not listed for the window")
    elif not_listed:   # the listing stopped early, so an absence is unread, not established
        out["not_listed_note"] = ("the listing was truncated, so these were not observed to be missing - only jobs that WERE "
                                  "read and are absent from the inventory are a definite gap")
    if unresolved_admin:
        reasons.append(f"the record declares {len(unresolved_admin)} administrative statement(s) it never named a job for")
    if reasons:
        out["status"] = "INCOMPLETE"
    elif truncated:
        out["status"] = "INDETERMINATE"
        reasons.append(f"the platform listing stopped with pages left ({len(listed)} read, cap {cap}): what was read is a "
                       "prefix of the window, so a complete match proves nothing")
    else:
        out["status"] = "RECONCILED"
    if reasons:
        out["reason"] = "; ".join(reasons)
    return redact(out)


def main(argv: Optional[list[str]] = None) -> int:
    ap = argparse.ArgumentParser(description="reconcile a retained chain record's job inventory against jobs.list (read-only)")
    ap.add_argument("record", help="path to a retained chain_*.json")
    ap.add_argument("--out", default=None, help="where to write the audit (default: beside the record, job_audit_<name>)")
    ap.add_argument("--pad-s", type=int, default=PAD_S)
    ap.add_argument("--page-size", type=int, default=PAGE_SIZE, help="jobs per HTTP page; the listing itself is never capped")
    ap.add_argument("--cap", type=int, default=MAX_LISTED, help="refuse to read more than this many jobs; hitting it is truncation")
    a = ap.parse_args(argv)
    path = Path(a.record)
    record = json.loads(path.read_text(encoding="utf-8"))
    if record.get("mode") != "live":
        ap.error(f"{path} is a {record.get('mode')} record: only a live run submits jobs to reconcile")
    out = audit(record, pad_s=a.pad_s, page_size=a.page_size, cap=a.cap)
    dest = Path(a.out) if a.out else path.with_name(f"job_audit_{path.stem}.json")
    dest.write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    run_dir = Path(record.get("run_dir") or "")
    if run_dir.is_dir():
        (run_dir / dest.name).write_text(json.dumps(out, indent=1, sort_keys=True, default=str) + "\n", encoding="utf-8")
    print(f"status={out['status']} listed={out.get('listed')} truncated={out.get('truncated')} inventory={out['inventory']['total']} "
          f"unaccounted_requester={len(out.get('unaccounted_requester_jobs', []))} not_listed={len(out.get('not_listed', []))} "
          f"declared_admin_unresolved={out.get('declared_admin_unresolved', 0)} -> {dest}")
    return 0 if out["status"] == "RECONCILED" else 1


if __name__ == "__main__":
    sys.exit(main())
