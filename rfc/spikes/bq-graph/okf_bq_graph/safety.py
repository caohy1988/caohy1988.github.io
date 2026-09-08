"""Detached retrying closer. Never infer absence from a failed inventory command."""
import json
import sys
import time
from pathlib import Path
from typing import Optional

from google.cloud import bigquery

from . import PROJECT, LOCATION
from .lifecycle import cancel_journal
from .reservation import close_window

EVIDENCE_DIR = "evidence"


def cleanup(label: str, attempts: int = 3, retry_seconds: float = 15,
            evidence_dir: Optional[str | Path] = None) -> bool:
    """`evidence_dir` is the window's OWN evidence directory, and must be the one it journaled into.

    The watcher is a separate process that is handed a label, so a journal resolved against a directory the window
    never used makes every owned job unreadable and cancels nothing, while capacity deletion proceeds regardless -
    capacity deletion is not job cleanup. Omitting it keeps the historical `evidence/` location."""
    d = Path(evidence_dir) if evidence_dir is not None else Path(EVIDENCE_DIR)
    for attempt in range(attempts):
        errors = []
        # Capacity deletion must not wait for job cancellation I/O. The separate
        # job-cleanup gate prevents reopening until cancellation is verified.
        try:
            gone = close_window(label, closer="safety-watcher")["verified_gone"]
        except Exception as exc:
            gone = False
            errors.append(f"cleanup raised {type(exc).__name__}: {exc}"[:300])
        try:
            client = bigquery.Client(project=PROJECT, location=LOCATION)
            jobs = cancel_journal(client, label, d / f"jobs_{label}.json")
        except Exception as exc:
            jobs = [{"verified_done": False, "error": f"{type(exc).__name__}: {exc}"[:300]}]
        receipt = {"label": label, "closer": "safety-watcher", "attempt": attempt + 1,
                   "verified_gone": gone, "jobs": jobs, "errors": errors}
        try:
            # Never rewrite the shared manifest after close: a newer driver may
            # already have opened its window using that same reservation name.
            with open(d / f"watcher_{label}.jsonl", "a") as fh:
                fh.write(json.dumps(receipt) + "\n")
        except Exception as exc:
            errors.append(f"receipt write raised {type(exc).__name__}: {exc}"[:300])
        verified = gone and all(j["verified_done"] for j in jobs) and not errors
        # The log remains a failure receipt even when the manifest cannot be written.
        print(json.dumps(receipt), flush=True)
        if verified:
            return True
        if attempt + 1 < attempts:
            time.sleep(retry_seconds)
    return False


if __name__ == "__main__":
    # argv[2] is the window's own evidence directory. The watcher is detached and knows only what it was spawned
    # with, so a window that journaled outside `evidence/` has to hand that directory across the process boundary.
    sys.exit(0 if cleanup(sys.argv[1], evidence_dir=sys.argv[2] if len(sys.argv) > 2 else None) else 1)
