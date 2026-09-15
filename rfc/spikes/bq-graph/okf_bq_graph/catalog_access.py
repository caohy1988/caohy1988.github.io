"""Requester access to Dataplex Catalog resources for the connected end-to-end run (2026-09-14).

Every earlier Catalog-seeded run read the Catalog under the operator's own ADC credential, so no access decision was
ever made on the Catalog leg. The connected run reads it as the restricted requester instead. The requester holds no
Catalog role by default (a live `entries.get` under it returns 403), so the harness grants one role on named resources
for the duration of the run and takes it away again for the revocation case:

* `snapshot()` reads each resource's IAM policy under the operator **before the first mutation**;
* `grant()` adds the member to the role (a member that already holds it is left alone and recorded as pre-existing);
* `revoke()` removes the member from the role;
* `restore()` writes each touched resource back to its snapshot bindings and reads it back: `VERIFIED` only when every
  read-back equals its snapshot;
* `observe()` / `wait()` decide access by what the **requester** actually receives from `entries.get(view=ALL)`:
  `ALLOWED` needs HTTP 200 *and* the runtime aspect's data, `DENIED` is HTTP 403, anything else is `UNKNOWN`. Elapsed
  time is never an outcome: a wait that runs out reports the last observation with `observed: false`.

A resource is marked mutated **before** its `setIamPolicy` is sent, so a lost response still gets restored. Every call is
kept with its HTTP status and the SHA-256 of its response body; policy snapshots are published redacted.
"""
from __future__ import annotations

import copy
import datetime as _dt
import hashlib
import json
import time
from typing import Any, Callable, Optional

CATALOG_VIEWER = "roles/dataplex.catalogViewer"
API = "https://dataplex.googleapis.com/v1/"
ALLOWED, DENIED, UNKNOWN = "ALLOWED", "DENIED", "UNKNOWN"


class CatalogAccessError(RuntimeError):
    """An IAM read or write that did not return HTTP 200: the platform's decision is unknown, never assumed."""


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


def canonical_bindings(bindings: Optional[list]) -> list[dict]:
    """Bindings in a comparable form: members sorted, bindings sorted by their own encoding, empty bindings dropped."""
    out = []
    for b in bindings or []:
        members = sorted(set(b.get("members") or []))
        if not members:
            continue
        item = {"role": b.get("role"), "members": members}
        if b.get("condition"):
            item["condition"] = b["condition"]
        out.append(item)
    return sorted(out, key=lambda x: json.dumps(x, sort_keys=True))


def holds(bindings: Optional[list], role: str, member: str) -> bool:
    """The member holds the role unconditionally (a conditional binding is not the access this run grants)."""
    return any(b.get("role") == role and member in (b.get("members") or []) and not b.get("condition") for b in bindings or [])


def with_member(bindings: Optional[list], role: str, member: str) -> list[dict]:
    out = copy.deepcopy(list(bindings or []))
    for b in out:
        if b.get("role") == role and not b.get("condition"):
            b["members"] = sorted(set(b.get("members") or []) | {member})
            return out
    out.append({"role": role, "members": [member]})
    return out


def without_member(bindings: Optional[list], role: str, member: str) -> list[dict]:
    out = []
    for b in copy.deepcopy(list(bindings or [])):
        if b.get("role") == role and not b.get("condition"):
            b["members"] = [m for m in b.get("members") or [] if m != member]
            if not b["members"]:
                continue
        out.append(b)
    return out


def observe_entry(reader: Any, entry: str, aspect_key: str) -> dict:
    """What the requester receives for one entry: ALLOWED only with the runtime aspect's data, DENIED on 403."""
    try:
        r = reader.get_entry(entry, "ALL")
    except Exception as e:  # noqa: BLE001 - transport failure is not a platform decision
        return {"status": UNKNOWN, "http_status": None, "error": f"{type(e).__name__}: {str(e)[:160]}", "at": _now()}
    body = r.json if isinstance(getattr(r, "json", None), dict) else {}
    data = ((body.get("aspects") or {}).get(aspect_key) or {}).get("data")
    if r.status == 200 and isinstance(data, dict) and data:
        status = ALLOWED
    elif r.status == 403:
        status = DENIED
    else:
        status = UNKNOWN
    return {"status": status, "http_status": r.status, "at": _now()}


class CatalogAccess:
    """IAM policy transitions for one member and one role on a list of Dataplex resources (entry group first)."""

    def __init__(self, resources: list[str], member: str, session: Any, role: str = CATALOG_VIEWER, api: str = API,
                 timeout: float = 30.0, sleep: Callable[[float], None] = time.sleep, clock: Callable[[], float] = time.monotonic):
        if not resources:
            raise ValueError("at least one Catalog resource is required")
        self.resources, self.member, self.session, self.role = list(resources), member, session, role
        self.api, self.timeout, self._sleep, self._clock = api, timeout, sleep, clock
        self.snapshots: dict[str, dict] = {}
        self.mutated: list[str] = []
        self.preexisting: dict[str, bool] = {}
        self.calls: list[dict] = []

    # -- transport
    def _call(self, method: str, resource: str, verb: str, body: Optional[dict] = None) -> dict:
        url = f"{self.api}{resource}:{verb}"
        raw, status, error = b"", None, None
        try:
            if method == "GET":
                r = self.session.request("GET", url, params={"options.requestedPolicyVersion": 3}, timeout=self.timeout)
            else:
                r = self.session.request("POST", url, json=body, timeout=self.timeout)
            status, raw = r.status_code, r.content or b""
        except Exception as e:  # noqa: BLE001
            error = f"{type(e).__name__}: {str(e)[:200]}"
        self.calls.append({"at": _now(), "verb": verb, "resource": resource, "http_status": status,
                           "response_sha256": hashlib.sha256(raw).hexdigest(), "error": error})
        if status != 200:
            detail = error or raw[:200].decode("utf-8", "replace")
            raise CatalogAccessError(f"{verb} on {resource.rsplit('/', 1)[-1]}: HTTP {status} {detail}".rstrip())
        try:
            return json.loads(raw.decode("utf-8")) if raw else {}
        except ValueError as e:
            raise CatalogAccessError(f"{verb}: non-JSON body") from e

    def _get(self, resource: str) -> dict:
        return self._call("GET", resource, "getIamPolicy")

    def _set(self, resource: str, bindings: list[dict], etag: Optional[str]) -> dict:
        policy: dict[str, Any] = {"bindings": bindings}
        if etag:
            policy["etag"] = etag
        return self._call("POST", resource, "setIamPolicy", {"policy": policy})

    # -- transitions
    def snapshot(self) -> dict:
        for res in self.resources:
            if res not in self.snapshots:
                pol = self._get(res)
                self.snapshots[res] = {"bindings": canonical_bindings(pol.get("bindings")), "etag": pol.get("etag"),
                                       "member_held_role": holds(pol.get("bindings"), self.role, self.member), "at": _now()}
        return {res: {"bindings": len(s["bindings"]), "member_held_role": s["member_held_role"]} for res, s in self.snapshots.items()}

    def grant(self) -> dict:
        self.snapshot()
        out = {}
        for res in self.resources:
            cur = self._get(res)
            if holds(cur.get("bindings"), self.role, self.member):
                self.preexisting[res] = True
                out[res] = "PREEXISTING"
                continue
            if res not in self.mutated:
                self.mutated.append(res)          # before the send: a lost response is still restored
            self._set(res, with_member(cur.get("bindings"), self.role, self.member), cur.get("etag"))
            out[res] = "GRANTED"
        return {"status": "GRANTED" if "GRANTED" in out.values() else "PREEXISTING", "role": self.role, "resources": out, "at": _now()}

    def revoke(self) -> dict:
        self.snapshot()
        out = {}
        for res in self.resources:
            cur = self._get(res)
            if not holds(cur.get("bindings"), self.role, self.member):
                out[res] = "NOT_HELD"
                continue
            if res not in self.mutated:
                self.mutated.append(res)
            self._set(res, without_member(cur.get("bindings"), self.role, self.member), cur.get("etag"))
            out[res] = "REVOKED"
        return {"status": "REVOKED" if "REVOKED" in out.values() else "NOT_HELD", "role": self.role, "resources": out, "at": _now()}

    def restore(self) -> dict:
        """Write every touched resource back to its snapshot and read it back. Each resource is attempted even if an
        earlier one failed; VERIFIED needs every read-back equal to its snapshot."""
        if not self.mutated:
            return {"status": "NOT_NEEDED", "reason": "no Catalog IAM policy was changed", "steps": {}}
        steps: dict[str, dict] = {}
        for res in self.mutated:
            snap = self.snapshots[res]
            step: dict[str, Any] = {}
            try:
                cur = self._get(res)
                self._set(res, snap["bindings"], cur.get("etag"))
                step["restore"] = True
            except Exception as e:  # noqa: BLE001
                step.update(restore=False, error=f"{type(e).__name__}: {str(e)[:200]}")
            try:
                after = self._get(res)
                step["readback_equal"] = canonical_bindings(after.get("bindings")) == snap["bindings"]
                step["member_holds_role_after"] = holds(after.get("bindings"), self.role, self.member)
                step["ok"] = bool(step.get("restore")) and step["readback_equal"] and step["member_holds_role_after"] == snap["member_held_role"]
            except Exception as e:  # noqa: BLE001
                step.update(readback_equal=False, ok=False, readback_error=f"{type(e).__name__}: {str(e)[:200]}")
            steps[res] = step
        return {"status": "VERIFIED" if all(s.get("ok") for s in steps.values()) else "UNVERIFIED", "steps": steps, "at": _now()}

    # -- observation under the requester
    def observe(self, reader: Any, entry: str, aspect_key: str) -> dict:
        return observe_entry(reader, entry, aspect_key)

    def wait(self, want: str, reader: Any, entry: str, aspect_key: str, wait_s: float, every_s: float = 10.0) -> dict:
        t0 = self._clock()
        polls = 0
        while True:
            obs = self.observe(reader, entry, aspect_key)
            polls += 1
            waited = self._clock() - t0
            if obs["status"] == want or waited >= wait_s:
                return {"want": want, "observed": obs["status"] == want, "status": obs["status"], "http_status": obs.get("http_status"),
                        "waited_s": int(waited), "polls": polls, "note": "a poll interval, not a propagation bound"}
            self._sleep(every_s)

    def record(self, redact: Callable[[Any], Any] = lambda x: x) -> dict:
        return redact({"role": self.role, "member": self.member, "resources": self.resources, "mutated": self.mutated,
                       "preexisting": self.preexisting, "snapshots": self.snapshots, "calls": self.calls})
