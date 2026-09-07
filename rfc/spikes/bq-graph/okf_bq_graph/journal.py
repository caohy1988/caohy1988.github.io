"""Invocation-owned evidence journal (plan KTD5).

Allocated before any external operation. Every intended job is appended before it is waited on; submission adds the
actual job identity; the terminal state (DONE / ERROR / EMPTY / NOT_SUBMITTED) is appended afterwards. Raw responses
are retained under the run directory with their SHA-256. Nothing here copies to a shared name or deletes an original:
the run directory is the only place this journal writes, and the final chain record references these paths/hashes.
"""
from __future__ import annotations

import datetime as _dt
import hashlib
import json
import os
import threading
from pathlib import Path
from typing import Any, Optional

TERMINAL = ("DONE", "ERROR", "EMPTY", "NOT_SUBMITTED", "CANCELLED", "APPLIED", "NOT_APPLIED", "MOOT")
# MOOT: an UNKNOWN write whose target resource was afterwards deleted and its absence read back; its own outcome no longer matters
UNKNOWN = "UNKNOWN"   # a local exception left the server-side state unverified: NOT terminal until reconciled


def _now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class Journal:
    def __init__(self, run_dir: str | os.PathLike, run_id: str):
        self.run_dir = Path(run_dir)
        self.run_dir.mkdir(parents=True, exist_ok=True)
        self.run_id = run_id
        self.path = self.run_dir / "journal.jsonl"
        self.entries: list[dict] = []
        self.retained: list[dict] = []
        self._lock = threading.Lock()
        self._seq = 0
        self._append({"event": "opened", "run_id": run_id, "at": _now()})

    # -- append-only line log
    def _append(self, rec: dict) -> None:
        with self._lock:
            with self.path.open("a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec, sort_keys=True, default=str) + "\n")

    # -- jobs
    def intend(self, role: str, description: str, engine: str, **meta: Any) -> dict:
        """Record a job before it is submitted or waited on. Returns the mutable entry (the caller keeps it)."""
        with self._lock:
            self._seq += 1
            entry = {"seq": self._seq, "role": role, "description": description, "engine": engine, "state": "INTENDED",
                     "intended_at": _now(), "job_id": None, "project": None, "location": None, "terminal": False, **meta}
            self.entries.append(entry)
        self._append(dict(entry, event="intended"))
        return entry

    def submitted(self, entry: dict, job_id: Optional[str], project: Optional[str] = None, location: Optional[str] = None) -> dict:
        entry.update(state="SUBMITTED", job_id=job_id, project=project, location=location, submitted_at=_now())
        self._append(dict(entry, event="submitted"))
        return entry

    def terminal(self, entry: dict, state: str, rows: Optional[int] = None, error: Optional[str] = None, **stats: Any) -> dict:
        if state not in TERMINAL:
            raise ValueError(f"not a terminal state: {state}")
        entry.update(state=state, terminal=True, rows=rows, error=error, terminal_at=_now(), **stats)
        self._append(dict(entry, event="terminal"))
        return entry

    def unknown(self, entry: dict, error: str, **stats: Any) -> dict:
        """A local failure (timeout, transport, interrupted write) whose server-side outcome is unverified. The entry
        stays unresolved; only `reconcile` (after an actual state readback) or `terminal` can close it."""
        entry.update(state=UNKNOWN, terminal=False, error=error, unknown_at=_now(), **stats)
        self._append(dict(entry, event="unknown"))
        return entry

    def reconcile(self, entry: dict, state: str, observed: Optional[str] = None, **stats: Any) -> dict:
        """Close an UNKNOWN entry after reading the actual resource/job state (`observed` is what was read back)."""
        if state not in TERMINAL:
            raise ValueError(f"not a terminal state: {state}")
        entry.update(state=state, terminal=True, reconciled=True, observed=observed, reconciled_at=_now(), **stats)
        self._append(dict(entry, event="reconciled"))
        return entry

    def note(self, event: str, **fields: Any) -> None:
        self._append({"event": event, "at": _now(), **fields})

    # -- raw retention
    def retain(self, name: str, raw: bytes, subdir: str = "catalog") -> dict:
        d = self.run_dir / subdir
        d.mkdir(parents=True, exist_ok=True)
        p = d / f"{name}.json"
        with p.open("xb") as fh:           # never overwrite: a name collision inside one run is a bug, not a merge
            fh.write(raw)
        rec = {"name": name, "path": str(p), "sha256": hashlib.sha256(raw).hexdigest(), "bytes": len(raw), "retained_at": _now()}
        self.retained.append(rec)
        self._append(dict(rec, event="retained"))
        return rec

    # -- views
    def jobs(self) -> list[dict]:
        return [dict(e) for e in self.entries]

    def job_ids(self, roles: Optional[tuple] = None) -> list[str]:
        return [e["job_id"] for e in self.entries if e.get("job_id") and (roles is None or e["role"] in roles)]

    def unresolved(self) -> list[dict]:
        return [dict(e) for e in self.entries if not e.get("terminal")]

    def summary(self) -> dict:
        by_state: dict[str, int] = {}
        for e in self.entries:
            by_state[e["state"]] = by_state.get(e["state"], 0) + 1
        return {"path": str(self.path), "entries": len(self.entries), "by_state": by_state,
                "unresolved": len(self.unresolved()), "retained_files": len(self.retained),
                "with_job_id": len(self.job_ids()), "actual_jobs": len([e for e in self.entries if e.get("actual")])}

    def record(self) -> dict:
        return {"summary": self.summary(), "jobs": self.jobs(), "retained": list(self.retained)}
