"""Execution-only reservation window helpers (spec §2, plan Task 1).

Creates the short-lived Enterprise autoscaling reservation + QUERY assignment, records every step and
resource in evidence/cleanup_manifest.json immediately, and tears it down. Teardown is only "verified"
when every delete command succeeded AND a successful listing (rc=0) shows neither the reservation nor an
assignment of this session; anything else stays DELETE_UNVERIFIED as an outstanding operational task.
Zero baseline, no idle-slot borrowing, autoscale max 100. Pay-as-you-go.
"""
from __future__ import annotations

import datetime as _dt
import fcntl
from functools import wraps
import json
import os
import subprocess
from typing import Optional
from pathlib import Path

from . import PROJECT, LOCATION, RESERVATION
from .lifecycle import job_cleanup_verified, restores_clear

MANIFEST = "evidence/cleanup_manifest.json"


def _serialized(fn):
    @wraps(fn)
    def locked(*args, **kwargs):
        # Coordinate driver watchdog, foreground cleanup and detached processes.
        # Read the manifest only AFTER acquiring the lock, including open gates.
        with open(f"{MANIFEST}.lock", "a") as lock:
            fcntl.flock(lock, fcntl.LOCK_EX)
            try:
                return fn(*args, **kwargs)
            finally:
                fcntl.flock(lock, fcntl.LOCK_UN)
    return locked


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bq(*args: str) -> dict:
    cmd = ["bq", f"--project_id={PROJECT}", f"--location={LOCATION}", "--format=prettyjson", *args]
    try:
        p = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except subprocess.TimeoutExpired:
        return {"cmd": " ".join(cmd), "rc": 124, "at": _now(), "stdout": "", "stderr": "bq command timed out"}
    except OSError as exc:
        return {"cmd": " ".join(cmd), "rc": 126, "at": _now(), "stdout": "", "stderr": f"bq could not start: {exc}"[:2000]}
    return {"cmd": " ".join(cmd), "rc": p.returncode, "at": _now(),
            "stdout": p.stdout.strip()[:6000], "stderr": p.stderr.strip()[:2000]}


def _load() -> dict:
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            return json.load(fh)
    return {"project": PROJECT, "location": LOCATION, "windows": [], "resources": []}


def _save(m: dict) -> None:
    temporary = f"{MANIFEST}.{os.getpid()}.tmp"
    with open(temporary, "w") as fh:
        json.dump(m, fh, indent=2)
    os.replace(temporary, MANIFEST)


def _parse_list(step: dict) -> Optional[list]:
    """Return the parsed list from a successful `bq ls` (rc=0), [] for the CLI's 'No ... found', else None."""
    if step["rc"] != 0:
        return None
    out = step["stdout"]
    if "No reservations found" in out or "No reservation assignments found" in out:
        return []
    try:
        val = json.loads(out)
        return val if isinstance(val, list) and all(isinstance(r, dict) and isinstance(r.get("name"), str) for r in val) else None
    except ValueError:
        return None


def require_clean_windows(m: dict, evidence_dir: Optional[str | Path] = None):
    """Capacity deletion AND a separate verified job-cleanup receipt, for every window that was ever opened.

    `evidence_dir` names where the journal/receipt pair is read from; it defaults to the manifest's own directory. A
    reconstruction staged by `reconcile_window` can therefore be gated in place, before anyone decides to publish it
    into `evidence/` (Slice A U1). A different directory relaxes nothing: the same structural check runs."""
    d = Path(evidence_dir) if evidence_dir is not None else Path(MANIFEST).parent
    if any(w.get("opened_at") and not w.get("verified_gone") for w in m["windows"]):
        raise RuntimeError("an earlier reservation window is outstanding; verify its cleanup before opening another")
    for w in m["windows"]:
        if w.get("opened_at") and not job_cleanup_verified(w["label"], d / f'jobs_{w["label"]}.json'):
            raise RuntimeError(f'job cleanup is unverified for {w["label"]}; reconcile its journal before opening another')
    # A resource this window changed and could not put back is its own outstanding obligation: verified capacity
    # deletion and a complete job receipt say nothing about a row policy or ACL left in place. Every obligation file in
    # the evidence directory is checked, not only the ones whose manifest row survived - a run that crashed before
    # recording its window still left the resource changed (Astra PR47 #3).
    labels = {w["label"] for w in m["windows"] if w.get("opened_at")}
    labels.update(path.name[len("restores_"):-len(".json")] for path in d.glob("restores_*.json"))
    for label in sorted(labels):
        if not restores_clear(label, d):
            raise RuntimeError(f"resource restoration is outstanding for {label}; clear restores_{label}.json "
                               "before opening another")


def reservation_state() -> dict:
    """Read-only: does this reservation name already exist, and whose assignments point at it?

    Nonownership must be established BEFORE any mutation. A listing that failed is `listing_ok: False` - unknown, never
    "absent" - because provisioning on top of an unreadable inventory is how another invocation's capacity gets deleted
    by a rollback that thinks it owns it (Astra PR47 #2)."""
    ls_r, ls_a = _bq("ls", "--reservation"), _bq("ls", "--reservation_assignment")
    reservations, assignments = _parse_list(ls_r), _parse_list(ls_a)
    if reservations is None or assignments is None:
        return {"listing_ok": False, "present": None, "assignments": [], "steps": [ls_r, ls_a],
                "reason": "the reservation listing failed or was unparseable: ownership cannot be established"}
    mine = [r for r in reservations if r.get("name", "").endswith(f"/reservations/{RESERVATION}")]
    asg = [a for a in assignments if f"/reservations/{RESERVATION}/" in a.get("name", "")]
    return {"listing_ok": True, "present": bool(mine), "assignments": [a.get("name") for a in asg],
            "reservations": [r.get("name") for r in mine], "steps": [ls_r, ls_a]}


@_serialized
def release_own_resources(label: str, closer: str = "own-rollback") -> dict:
    """Delete ONLY what this invocation created, from the manifest's own record.

    Used when provisioning refuses after partially succeeding. It never deletes a reservation that was already there
    (`pre_existing`), and never touches an assignment recorded under another window."""
    m = _load()
    w = next((x for x in reversed(m["windows"]) if x["label"] == label), None)
    steps, removed, preserved = [], [], []
    for r in m["resources"]:
        if r.get("window") != label or r.get("state") not in ("open", "DELETE_UNVERIFIED"):
            continue
        if r.get("pre_existing"):
            preserved.append(r.get("name"))
            r["state"] = "preserved_not_ours"
            continue
        if r["kind"] == "assignment":
            name = r.get("name", "")
            if "/reservations/" in name and "/assignments/" in name:
                res_id, asg_id = name.split("/reservations/")[1].split("/assignments/")
                step = _bq("rm", "--reservation_assignment", f"{res_id}.{asg_id}")
                steps.append(step)
                if step["rc"] == 0:
                    r["state"] = "deleted"; r["deleted_at"] = _now(); removed.append(name)
                else:
                    r["state"] = "DELETE_UNVERIFIED"
        elif r["kind"] == "reservation":
            step = _bq("rm", "--reservation", RESERVATION)
            steps.append(step)
            if step["rc"] == 0 or "not found" in (step["stderr"] + step["stdout"]).lower():
                r["state"] = "deleted"; r["deleted_at"] = _now(); removed.append(r.get("name"))
            else:
                r["state"] = "DELETE_UNVERIFIED"
    outcome = {"label": label, "closer": closer, "removed": removed, "preserved": preserved,
               "verified_gone": all(r.get("state") != "DELETE_UNVERIFIED" for r in m["resources"] if r.get("window") == label),
               "note": "rollback of this invocation's own resources only; capacity another invocation owns is preserved"}
    if w is not None:
        w["state"] = "REFUSED_PRESERVING_EXISTING"
        w["own_rollback"] = dict(outcome, steps=steps)
        w["verified_gone"] = outcome["verified_gone"]
        w.setdefault("closed_at", _now())
    m["resources"] = m["resources"]
    _save(m)
    return dict(outcome, steps=steps)


@_serialized
def open_window(label: str, max_slots: int = 100) -> dict:
    m = _load()
    require_clean_windows(m)
    w = {"label": label, "opened_at": _now(), "steps": [], "max_slots": max_slots, "state": "OPENING"}
    m["windows"].append(w)
    _save(m)
    mk = _bq("mk", "--reservation", "--edition=ENTERPRISE", "--slots=0",
             f"--autoscale_max_slots={max_slots}", "--ignore_idle_slots=true", RESERVATION)
    w["steps"].append(mk)
    pre_existing = mk["rc"] != 0 and "already exists" in (mk["stderr"] + mk["stdout"]).lower()
    if mk["rc"] == 0 or pre_existing:
        # `pre_existing` marks capacity this invocation did NOT create, so a rollback never deletes it
        m["resources"].append({"kind": "reservation", "window": label,
                               "name": f"projects/{PROJECT}/locations/{LOCATION}/reservations/{RESERVATION}",
                               "created_at": mk["at"], "state": "open", "pre_existing": pre_existing})
    _save(m)   # persist the paid resource before anything else can fail
    asg = _bq("mk", "--reservation_assignment", f"--reservation_id={RESERVATION}",
              f"--assignee_id={PROJECT}", "--assignee_type=PROJECT", "--job_type=QUERY")
    w["steps"].append(asg)
    try:
        name = json.loads(asg["stdout"]).get("name") if asg["rc"] == 0 else None
    except ValueError:
        name = None
    if name:
        m["resources"].append({"kind": "assignment", "window": label, "name": name, "created_at": asg["at"], "state": "open"})
    w["steps"].append(_bq("ls", "--reservation"))
    w["steps"].append(_bq("ls", "--reservation_assignment"))
    w["state"] = "OPEN" if mk["rc"] == 0 and asg["rc"] == 0 else "OPEN_WITH_ERRORS"
    _save(m)
    return w


@_serialized
def close_window(label: str, closer: str = "driver") -> dict:
    m = _load()
    w = next((x for x in reversed(m["windows"]) if x["label"] == label), None)
    if w is None:
        raise ValueError(f"unknown reservation window: {label}; use the original opening label")
    if w.get("verified_gone") and w.get("closed_at"):
        # Its verified receipt remains valid if a newer window has reused the same
        # reservation name. A late watcher must not delete that newer resource.
        return w
    w["closing_at"] = _now()
    errors: list[str] = []
    ls = _bq("ls", "--reservation_assignment")
    w["steps"].append(ls)
    assignments = _parse_list(ls)
    if assignments is None:
        errors.append("assignment listing failed")
        assignments = []
    for a in assignments:
        name = a.get("name", "")
        if f"/reservations/{RESERVATION}/" in name:
            res_id, asg_id = name.split("/reservations/")[1].split("/assignments/")
            rm = _bq("rm", "--reservation_assignment", f"{res_id}.{asg_id}")
            w["steps"].append(rm)
            if rm["rc"] != 0:
                errors.append(f"assignment delete failed: {asg_id}")
    rm_r = _bq("rm", "--reservation", RESERVATION)
    w["steps"].append(rm_r)
    if rm_r["rc"] != 0 and "not found" not in (rm_r["stderr"] + rm_r["stdout"]).lower():
        errors.append("reservation delete failed")
    ls_r = _bq("ls", "--reservation")
    ls_a = _bq("ls", "--reservation_assignment")
    w["steps"] += [ls_r, ls_a]
    res_list, asg_list = _parse_list(ls_r), _parse_list(ls_a)
    if res_list is None or asg_list is None:
        errors.append("post-delete listing failed (rc != 0 or unparseable)")
        gone = False
    else:
        still_res = [r for r in res_list if r.get("name", "").endswith(f"/reservations/{RESERVATION}")]
        still_asg = [a for a in asg_list if f"/reservations/{RESERVATION}/" in a.get("name", "")]
        gone = not still_res and not still_asg
        if still_res or still_asg:
            errors.append("resource still listed after delete")
    attempted_at = _now()
    w["errors"] = errors
    w["verified_gone"] = bool(gone and not errors)
    w["state"] = "CLOSED_VERIFIED" if w["verified_gone"] else "DELETE_UNVERIFIED"
    w.setdefault("cleanup_attempts", []).append({"at": attempted_at, "closer": closer,
                                                "verified_gone": w["verified_gone"], "errors": list(errors)})
    if w["verified_gone"]:
        w.setdefault("closed_at", attempted_at)
        w["closed_by"] = closer
    else:
        w.pop("closed_at", None)
    for r in m["resources"]:
        if r.get("state") in ("open", "DELETE_UNVERIFIED") and r.get("window") == label and r.get("kind") in ("reservation", "assignment"):
            r["state"] = "deleted" if w["verified_gone"] else "DELETE_UNVERIFIED"
            r["cleanup_attempted_at"] = attempted_at
            if w["verified_gone"]:
                r["closed_by"] = closer
                r["deleted_at"] = w["closed_at"]
            else:
                r.pop("deleted_at", None)
    _save(m)
    return w


if __name__ == "__main__":
    import sys
    action, label = sys.argv[1], sys.argv[2]
    out = open_window(label) if action == "open" else close_window(label)
    print(json.dumps({k: v for k, v in out.items() if k != "steps"}, indent=2))
    for s in out["steps"]:
        print(s["at"], "rc=%s" % s["rc"], s["cmd"].split("--format=prettyjson ")[1][:90], "|", (s["stdout"] or s["stderr"])[:160].replace("\n", " "))
    sys.exit(0 if action == "open" or out["verified_gone"] else 1)
