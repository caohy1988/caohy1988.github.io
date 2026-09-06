"""Detached retrying closer. Never infer absence from a failed inventory command."""
import json
import sys
import time

from google.cloud import bigquery

from . import PROJECT, LOCATION
from .lifecycle import cancel_journal
from .reservation import close_window


def cleanup(label: str, attempts: int = 3, retry_seconds: float = 15) -> bool:
    for attempt in range(attempts):
        errors = []
        try:
            client = bigquery.Client(project=PROJECT, location=LOCATION)
            jobs = cancel_journal(client, label, f"evidence/jobs_{label}.json")
        except Exception as exc:
            jobs = [{"verified_done": False, "error": f"{type(exc).__name__}: {exc}"[:300]}]
        # Cost control still tears down capacity if cancellation cannot be verified;
        # the outstanding job evidence is retained and this process returns failure.
        try:
            gone = close_window(label, closer="safety-watcher")["verified_gone"]
        except Exception as exc:
            gone = False
            errors.append(f"cleanup raised {type(exc).__name__}: {exc}"[:300])
        receipt = {"label": label, "closer": "safety-watcher", "attempt": attempt + 1,
                   "verified_gone": gone, "jobs": jobs, "errors": errors}
        try:
            # Never rewrite the shared manifest after close: a newer driver may
            # already have opened its window using that same reservation name.
            with open(f"evidence/watcher_{label}.jsonl", "a") as fh:
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
    sys.exit(0 if cleanup(sys.argv[1]) else 1)
