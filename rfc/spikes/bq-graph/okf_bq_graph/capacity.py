"""Task 1: capacity gate. Read-only inventory of BigQuery reservations,
assignments, ancestry, IAM and public SKU prices for the spike project.

Writes evidence/capacity.json. Never creates a reservation. The creation /
teardown helpers live in reservation.py and are execution-only.
"""
from __future__ import annotations

import datetime as _dt
import json
import subprocess
import sys
from typing import Any

import google.auth
from google.auth.transport.requests import AuthorizedSession

RESV = "https://bigqueryreservation.googleapis.com/v1"
CRM = "https://cloudresourcemanager.googleapis.com/v1"
BILLING = "https://cloudbilling.googleapis.com/v1"
RESERVATION_SERVICE = "16B8-3DDA-9F10"   # "BigQuery Reservation API" in the Billing Catalog
BIGQUERY_SERVICE = "24E6-581D-38E5"      # "BigQuery" (on-demand analysis, storage)

NEEDED_PERMS = [
    "bigquery.reservations.create", "bigquery.reservations.delete", "bigquery.reservations.list",
    "bigquery.reservationAssignments.create", "bigquery.reservationAssignments.delete",
    "bigquery.datasets.create", "bigquery.jobs.create",
]


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def _get(session: AuthorizedSession, url: str, **params: Any) -> dict:
    r = session.get(url, params=params or None)
    out: dict[str, Any] = {"url": url, "status": r.status_code, "at": _now()}
    try:
        out["body"] = r.json()
    except ValueError:
        out["body"] = r.text[:2000]
    return out


def _cli(args: list[str]) -> dict:
    p = subprocess.run(args, capture_output=True, text=True)
    return {"cmd": " ".join(args), "rc": p.returncode, "at": _now(),
            "stdout": p.stdout.strip()[:4000], "stderr": p.stderr.strip()[:2000]}


def inspect_capacity(project: str, locations: list[str], session: AuthorizedSession | None = None) -> dict:
    """Return READY / BLOCKED / UNKNOWN_CAPACITY with proof.

    READY here means "no usable assignment exists, and the principal holds the
    permissions and billing needed to create the short-lived reservation".
    A real GQL smoke job on the reservation is still required (spec §2).
    """
    if session is None:
        creds, _ = google.auth.default()
        session = AuthorizedSession(creds)
    ev: dict[str, Any] = {"project": project, "started_at": _now(), "locations": {}}
    ev["principal"] = _cli(["gcloud", "config", "get-value", "account"])["stdout"]
    ev["cli_versions"] = {"bq": _cli(["bq", "version"])["stdout"],
                          "gcloud": _cli(["gcloud", "version", "--format=value(core)"])["stdout"]}
    ev["ancestry"] = _cli(["gcloud", "projects", "get-ancestors", project])
    ev["billing"] = _cli(["gcloud", "billing", "projects", "describe", project, "--format=json"])
    ev["iam_test"] = {"at": _now()}
    r = session.post(f"{CRM}/projects/{project}:testIamPermissions", json={"permissions": NEEDED_PERMS})
    ev["iam_test"].update({"status": r.status_code, "granted": r.json().get("permissions", []) if r.ok else r.text[:500]})

    listing_failed = False
    any_assignment = False
    for loc in locations:
        L: dict[str, Any] = {}
        L["reservations"] = _get(session, f"{RESV}/projects/{project}/locations/{loc}/reservations")
        L["capacity_commitments"] = _get(session, f"{RESV}/projects/{project}/locations/{loc}/capacityCommitments")
        # legacy searchAssignments supports the assignee query and returns
        # direct + inherited assignments for this assignee in this location.
        L["search_assignments"] = _get(session, f"{RESV}/projects/{project}/locations/{loc}:searchAssignments",
                                       query=f"assignee=projects/{project}")
        L["bq_ls_reservation"] = _cli(["bq", f"--project_id={project}", f"--location={loc}", "--format=prettyjson", "ls", "--reservation"])
        L["bq_ls_assignment"] = _cli(["bq", f"--project_id={project}", f"--location={loc}", "--format=prettyjson", "ls", "--reservation_assignment"])
        for k in ("reservations", "capacity_commitments", "search_assignments"):
            if L[k]["status"] != 200:
                listing_failed = True
        body = L["search_assignments"]["body"]
        if isinstance(body, dict) and body.get("assignments"):
            any_assignment = True
        ev["locations"][loc] = L

    ev["skus"] = public_skus(session)
    granted = set(ev["iam_test"].get("granted") or [])
    missing = sorted(set(NEEDED_PERMS) - granted)
    if listing_failed:
        state = "UNKNOWN_CAPACITY"
    elif any_assignment:
        state = "EXISTING_ASSIGNMENT_FOUND"  # document cost/isolation before use
    elif missing:
        state = "BLOCKED"
    else:
        state = "READY_TO_PROVISION"
    ev["missing_permissions"] = missing
    ev["state"] = state
    ev["finished_at"] = _now()
    return ev


def public_skus(session: AuthorizedSession) -> dict:
    """Pay-as-you-go edition slot-hour prices and on-demand/storage SKUs for
    US multi-region and us-central1, from the Cloud Billing Catalog."""
    out: dict[str, Any] = {"read_at": _now(), "rows": []}
    for svc in (RESERVATION_SERVICE, BIGQUERY_SERVICE):
        r = _get(session, f"{BILLING}/services/{svc}/skus", pageSize=5000)
        if r["status"] != 200:
            out.setdefault("errors", []).append(r)
            continue
        for s in r["body"].get("skus", []):
            desc = s["description"]
            regs = [x for x in s["serviceRegions"] if x in ("us", "us-central1")]
            if not regs or "Commit" in desc or "Year" in desc:
                continue
            if not any(k in desc for k in ("Enterprise", "Standard Edition", "Analysis", "Active Logical Storage")):
                continue
            pe = s["pricingInfo"][0]["pricingExpression"]
            tiers = [{"start": t["startUsageAmount"],
                      "usd": float(t["unitPrice"]["units"]) + t["unitPrice"]["nanos"] / 1e9}
                     for t in pe["tieredRates"]]
            out["rows"].append({"sku": s["skuId"], "description": desc, "regions": regs,
                                "unit": pe["usageUnitDescription"], "tiers": tiers})
    return out


def main(argv: list[str]) -> int:
    from . import PROJECT
    locs = argv[1:] or ["US", "us-central1", "EU"]
    ev = inspect_capacity(PROJECT, locs)
    path = "evidence/capacity.json"
    with open(path, "w") as fh:
        json.dump(ev, fh, indent=2, default=str)
    print(json.dumps({"state": ev["state"], "missing_permissions": ev["missing_permissions"],
                      "locations": {l: {"reservations": v["reservations"]["body"],
                                         "assignments": v["search_assignments"]["body"]}
                                    for l, v in ev["locations"].items()},
                      "written": path}, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
