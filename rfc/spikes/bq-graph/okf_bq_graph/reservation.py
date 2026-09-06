"""Execution-only reservation window helpers (spec §2, plan Task 1).

Creates the short-lived Enterprise autoscaling reservation + QUERY assignment,
records everything in evidence/cleanup_manifest.json, and tears it down.
Zero baseline, no idle-slot borrowing, autoscale max 100. Pay-as-you-go.
"""
from __future__ import annotations

import datetime as _dt
import json
import os
import subprocess
import sys
import time

from . import PROJECT, LOCATION, RESERVATION

MANIFEST = "evidence/cleanup_manifest.json"


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _bq(*args: str) -> dict:
    cmd = ["bq", f"--project_id={PROJECT}", f"--location={LOCATION}", "--format=prettyjson", *args]
    p = subprocess.run(cmd, capture_output=True, text=True)
    return {"cmd": " ".join(cmd), "rc": p.returncode, "at": _now(),
            "stdout": p.stdout.strip()[:6000], "stderr": p.stderr.strip()[:2000]}


def _load() -> dict:
    if os.path.exists(MANIFEST):
        with open(MANIFEST) as fh:
            return json.load(fh)
    return {"project": PROJECT, "location": LOCATION, "windows": [], "resources": []}


def _save(m: dict) -> None:
    with open(MANIFEST, "w") as fh:
        json.dump(m, fh, indent=2)


def open_window(label: str, max_slots: int = 100) -> dict:
    m = _load()
    w = {"label": label, "opened_at": _now(), "steps": [], "max_slots": max_slots}
    w["steps"].append(_bq("mk", "--reservation", "--edition=ENTERPRISE", "--slots=0",
                          f"--autoscale_max_slots={max_slots}", "--ignore_idle_slots=true", RESERVATION))
    w["steps"].append(_bq("mk", "--reservation_assignment", f"--reservation_id={RESERVATION}",
                          f"--assignee_id={PROJECT}", "--assignee_type=PROJECT", "--job_type=QUERY"))
    w["steps"].append(_bq("ls", "--reservation"))
    w["steps"].append(_bq("ls", "--reservation_assignment"))
    m["windows"].append(w)
    m["resources"].append({"kind": "reservation", "name": f"projects/{PROJECT}/locations/{LOCATION}/reservations/{RESERVATION}",
                           "created_at": w["opened_at"], "state": "open"})
    _save(m)
    return w


def close_window(label: str) -> dict:
    m = _load()
    w = next((x for x in reversed(m["windows"]) if x["label"] == label), None)
    if w is None:
        w = {"label": label, "steps": []}
        m["windows"].append(w)
    w["closing_at"] = _now()
    # find assignment id(s) for this reservation
    ls = _bq("ls", "--reservation_assignment")
    w["steps"].append(ls)
    try:
        assignments = json.loads(ls["stdout"]) if ls["stdout"].startswith("[") else []
    except ValueError:
        assignments = []
    for a in assignments:
        name = a.get("name", "")
        if f"/reservations/{RESERVATION}/" in name:
            # bq expects <reservation_id>.<assignment_id> (with --location/--project_id)
            res_id, asg_id = name.split("/reservations/")[1].split("/assignments/")
            w["steps"].append(_bq("rm", "--reservation_assignment", f"{res_id}.{asg_id}"))
    w["steps"].append(_bq("rm", "--reservation", RESERVATION))
    w["steps"].append(_bq("ls", "--reservation"))
    w["steps"].append(_bq("ls", "--reservation_assignment"))
    w["closed_at"] = _now()
    gone = "No reservations found" in w["steps"][-2]["stdout"] or w["steps"][-2]["stdout"] in ("[]", "")
    w["verified_gone"] = gone
    for r in m["resources"]:
        if r["kind"] == "reservation":
            r["state"] = "deleted" if gone else "DELETE_UNVERIFIED"
            r["deleted_at"] = w["closed_at"]
    _save(m)
    return w


if __name__ == "__main__":
    action, label = sys.argv[1], sys.argv[2]
    out = open_window(label) if action == "open" else close_window(label)
    print(json.dumps({k: v for k, v in out.items() if k != "steps"}, indent=2))
    for s in out["steps"]:
        print(s["at"], "rc=%s" % s["rc"], s["cmd"].split("--format=prettyjson ")[1][:90], "|", (s["stdout"] or s["stderr"])[:160].replace("\n", " "))
