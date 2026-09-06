"""One submission gate and durable job inventory for a reservation window.

All query/load clients used by the driver share this gate. Stopping closes admission
before cancelling jobs; bounded result polling lets executor workers unwind even if
cancellation fails. The detached watcher can retry the same journal after driver exit.
"""
from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, TimeoutError
from contextlib import contextmanager
from pathlib import Path

from google.api_core.exceptions import NotFound
from google.cloud import bigquery
from google.cloud.bigquery import Client as BigQueryClient

from . import PROJECT, LOCATION


class WindowStopped(RuntimeError):
    pass


class _ResultHTTP:
    """Recheck at actual HTTP dispatch, after SDK request preparation."""
    def __init__(self, raw, remaining):
        self.raw, self.remaining = raw, remaining

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def request(self, *args, **kwargs):
        remaining = self.remaining()
        requested = kwargs.get("timeout")
        kwargs["timeout"] = min(1, remaining, requested if isinstance(requested, (int, float)) else 1)
        response = self.raw.request(*args, **kwargs)
        self.remaining()
        return response


@contextmanager
def window_executor(client, max_workers):
    """Cancel before executor.__exit__ waits, including interrupts in nested retrieval."""
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        try:
            yield executor
        except BaseException:
            if isinstance(client, WindowClient):
                client.window.stop_and_cancel()
            raise


def cancel_jobs(client, job_ids: list[str]) -> list[dict]:
    return _cancel_pending([(job_id, client) for job_id in job_ids])


def _cancel_one(pair) -> dict:
    job_id, client = pair
    try:
        client.cancel_job(job_id, location=LOCATION, retry=None, timeout=10)
        job = client.get_job(job_id, location=LOCATION, retry=None, timeout=10)
        return {"job_id": job_id, "state": job.state, "verified_done": job.state == "DONE"}
    except NotFound:
        # IDs are journaled before submission; a stopped/failed submission may not exist.
        return {"job_id": job_id, "state": "NOT_FOUND", "verified_done": True}
    except Exception as exc:
        return {"job_id": job_id, "verified_done": False, "error": f"{type(exc).__name__}: {exc}"[:300]}


def _cancel_pending(pending) -> list[dict]:
    if len(pending) < 2:
        return [_cancel_one(pair) for pair in pending]
    # Independent jobs can be cancelled together; map preserves journal order.
    with ThreadPoolExecutor(max_workers=min(8, len(pending))) as executor:
        return list(executor.map(_cancel_one, pending))


class WindowJobs:
    def __init__(self, label: str, deadline: float, journal: str | Path):
        self.label, self.deadline, self.journal = label, deadline, Path(journal)
        self.stop = threading.Event()
        self._lock = threading.RLock()
        self._cancel_lock = threading.Lock()
        self._jobs: dict[str, object] = {}
        self._finished: set[str] = set()
        self._cancelled: dict[str, dict] = {}
        self._save()

    def _save(self):
        tmp = self.journal.with_suffix(".tmp")
        tmp.write_text(json.dumps({"label": self.label, "project": PROJECT, "location": LOCATION,
                                   "job_ids": list(self._jobs), "finished_job_ids": sorted(self._finished)}, indent=2))
        os.replace(tmp, self.journal)

    def check(self):
        if time.monotonic() >= self.deadline:
            self.stop.set()
        if self.stop.is_set():
            raise WindowStopped("reservation window stopped or deadline reached")

    def wait(self, seconds: float):
        self.check()
        self.stop.wait(max(0, min(seconds, self.deadline - time.monotonic())))
        self.check()

    def bind(self, client):
        return WindowClient(client, self)

    def submit(self, client, method, args, kwargs):
        # Lock covers admission + registration + submit, never result waiting.
        # The stop event is set before cancellation takes this lock, closing races.
        with self._lock:
            self.check()
            kwargs = dict(kwargs)
            cfg = copy.deepcopy(kwargs.get("job_config"))
            if cfg is None:
                cfg = bigquery.QueryJobConfig() if method == "query" else bigquery.LoadJobConfig()
            cfg.labels = dict(cfg.labels or {}, okf_spike="bq_graph_20260905", window=self.label)
            job_id = f"okf_graph_{self.label}_{uuid.uuid4().hex}"
            kwargs.update(job_config=cfg, job_id=job_id,
                          timeout=max(.001, min(30, self.deadline - time.monotonic())))
            if method == "query":
                kwargs["retry"] = None
                kwargs["job_retry"] = None  # no invisible resubmissions with new IDs
            else:
                kwargs["num_retries"] = 0
            self._jobs[job_id] = client
            self._save()  # survives a lost submit response or killed driver
            job = getattr(client, method)(*args, **kwargs)
        return WindowJob(job, self, job_id, method == "query")

    def finished(self, job_id):
        with self._lock:
            self._finished.add(job_id)
            self._save()

    def stop_and_cancel(self) -> list[dict]:
        self.stop.set()
        with self._cancel_lock:
            with self._lock:
                pending = [(i, c) for i, c in self._jobs.items() if i not in self._finished]
            for result in _cancel_pending(pending):
                job_id = result["job_id"]
                self._cancelled[job_id] = result
                if result["verified_done"]:
                    self.finished(job_id)
            with self._lock:
                _save_cleanup(self.journal, json.loads(self.journal.read_text()), list(self._cancelled.values()))
            return list(self._cancelled.values())


class WindowClient:
    def __init__(self, client, window):
        self.raw, self.window = client, window

    def query(self, *args, **kwargs):
        return self.window.submit(self.raw, "query", args, kwargs)

    def load_table_from_json(self, *args, **kwargs):
        return self.window.submit(self.raw, "load_table_from_json", args, kwargs)

    def __getattr__(self, name):
        return getattr(self.raw, name)


class WindowJob:
    def __init__(self, job, window, job_id, is_query):
        self.raw, self.window, self.job_id, self.is_query = job, window, job_id, is_query
        self._query_client = job._client if isinstance(job, bigquery.QueryJob) else None

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def _check(self):
        try:
            self.window.check()
        except WindowStopped:
            self.window.stop_and_cancel()  # before callers unwind executor contexts
            raise

    def result(self, **kwargs):
        self._check()
        timeout = kwargs.pop("timeout", None)
        end = min(self.window.deadline, time.monotonic() + (float("inf") if timeout is None else timeout))
        kwargs["retry"] = None
        if self.is_query:
            kwargs["job_retry"] = None
            if self._query_client is not None:
                # QueryJob.result raises getQueryResults RPC timeouts to >=120s.
                # Bind a job-local client AFTER that conversion, at _call_api.
                # RowIterator retains this client for every lazy page. Never
                # mutate the shared client used for other jobs or cancellation.
                client = BigQueryClient(project=self._query_client.project,
                                        location=self._query_client.location,
                                        credentials=self._query_client._credentials,
                                        client_options={"api_endpoint": self._query_client._connection.API_BASE_URL},
                                        _http=_ResultHTTP(self._query_client._http, lambda: self._remaining(end)))
                raw_call = client._call_api

                def call_api(retry, **rpc):
                    remaining = self._remaining(end)
                    requested = rpc.get("timeout")
                    rpc["timeout"] = min(1, remaining, requested if isinstance(requested, (int, float)) else 1)
                    if "/queries/" in rpc.get("path", ""):
                        params = dict(rpc.get("query_params") or {})
                        params["timeoutMs"] = min(params.get("timeoutMs", 1000), int(rpc["timeout"] * 1000))
                        rpc["query_params"] = params
                    response = raw_call(None, **rpc)  # disable hidden retry/backoff on every page
                    self._remaining(end)  # discard a response arriving after stop
                    return response

                client._call_api = call_api
                self.raw._client = client
        while True:
            self._check()
            remaining = end - time.monotonic()
            if remaining <= 0:
                raise TimeoutError("job result timeout")
            try:
                if self.is_query:
                    result = self.raw.result(timeout=min(1, remaining), **kwargs)
                else:
                    # LoadJob.result's polling timeout does not bound its RPC:
                    # done() otherwise defaults get_job transport to 128 seconds.
                    if not self.raw.done(retry=None, timeout=min(1, remaining)):
                        self.window.stop.wait(min(.1, max(0, end - time.monotonic())))
                        continue
                    result = self.raw.result(timeout=0, **kwargs)  # already DONE; preserves SDK job errors
                self.window.finished(self.job_id)
                self._check()
                return self._rows(result, end) if self.is_query else result
            except TimeoutError:
                continue
            except (KeyboardInterrupt, SystemExit):
                self.window.stop_and_cancel()
                raise

    def _remaining(self, end):
        self.window.check()
        remaining = end - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("job result timeout")
        return remaining

    def _rows(self, rows, end):
        # Guard buffered rows too, including the SDK's cached first page.
        iterator = iter(rows)
        while True:
            self._remaining(end)
            try:
                row = next(iterator)
            except StopIteration:
                return
            self._remaining(end)
            yield row


def cancel_journal(client, label: str, path: str | Path) -> list[dict]:
    journal = json.loads(Path(path).read_text())
    if journal["label"] != label or journal["project"] != PROJECT or journal["location"] != LOCATION:
        raise ValueError("job journal does not belong to this reservation window")
    finished = set(journal.get("finished_job_ids", []))
    results = cancel_jobs(client, [i for i in journal["job_ids"] if i not in finished])
    _save_cleanup(Path(path), journal, results)
    return results


def _save_cleanup(path: Path, journal: dict, results: list[dict]):
    """Separate receipt: a late watcher never rewrites the driver's job inventory."""
    done = set(journal.get("finished_job_ids", []))
    done.update(r["job_id"] for r in results if r.get("verified_done"))
    receipt = {"label": journal["label"], "project": journal["project"], "location": journal["location"],
               "job_ids": journal["job_ids"], "verified_done_job_ids": sorted(done), "jobs": results,
               "verified": set(journal["job_ids"]) <= done}
    target = path.with_suffix(".cleanup.json")
    tmp = target.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(receipt, indent=2))
    os.replace(tmp, target)


def job_cleanup_verified(label: str, path: str | Path) -> bool:
    """Missing/legacy/mismatched evidence cannot authorize another paid window."""
    try:
        path = Path(path)
        journal = json.loads(path.read_text())
        receipt = json.loads(path.with_suffix(".cleanup.json").read_text())
        return (all(isinstance(j, dict) and j.get("label") == label and j.get("project") == PROJECT and j.get("location") == LOCATION
                    for j in (journal, receipt)) and receipt.get("verified") is True
                and all(isinstance(ids, list) and all(isinstance(i, str) and i for i in ids)
                        for ids in (journal["job_ids"], receipt["job_ids"], receipt["verified_done_job_ids"]))
                and set(journal["job_ids"]) == set(receipt["job_ids"])
                and set(journal["job_ids"]) <= set(receipt["verified_done_job_ids"]))
    except (OSError, ValueError, KeyError, TypeError):
        return False
