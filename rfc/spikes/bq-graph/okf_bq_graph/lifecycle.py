"""One submission gate and durable job inventory for a reservation window.

All query/load clients used by the driver share this gate. Stopping closes admission
before cancelling jobs; bounded result polling lets executor workers unwind even if
cancellation fails. The detached watcher can retry the same journal after driver exit.
"""
from __future__ import annotations

import copy
import datetime as _dt
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


def _dt_now() -> str:
    return _dt.datetime.now(_dt.timezone.utc).isoformat()


class WindowStopped(RuntimeError):
    pass


class _ResultHTTP:
    """Guard a job-local session, including sends after auth preparation/retries."""
    def __init__(self, raw, remaining):
        self.raw, self.remaining = copy.copy(raw), remaining
        # Session's pickle-based copy omits AuthorizedSession's auth fields.
        # Retain credentials, auth transport and caller configuration, but put
        # the send override only on this copy, never the cancellation client.
        self.raw.__dict__.update(raw.__dict__)
        self._send = self.raw.send
        self.raw.send = self.send
        self.guarded_auth_transport = self._guard_auth_transport()

    def _guard_auth_transport(self) -> bool:
        """A 401 DURING RESULT READS refreshes the credential through `AuthorizedSession._auth_request`, which owns a
        separate plain `requests.Session`. `__dict__.update` carries the caller's shared one straight onto this copy,
        so overriding only the copied AuthorizedSession's `send` leaves the refresh unbounded and admitted after stop
        (Astra PR47 RR3 N3).

        The guard is installed on a COPY of that session, mounted on a new `Request` belonging to this job-local
        transport only, so the caller's own refresh path is never mutated."""
        request = self.raw.__dict__.get("_auth_request")
        session = getattr(request, "session", None)
        if request is None:
            return False
        if session is not None:
            guarded = copy.copy(session)
            guarded.__dict__.update(session.__dict__)
            inner = guarded.send

            def auth_send(prepared, **kwargs):
                kwargs["timeout"] = self._timeout(kwargs.get("timeout"))
                return inner(prepared, **kwargs)

            guarded.send = auth_send
            try:
                self.raw._auth_request = type(request)(guarded)
                return True
            except Exception:  # noqa: BLE001 - an unusual Request type: fall through to the callable guard
                pass

        def guarded_request(url, method="GET", body=None, headers=None, timeout=None, **kwargs):
            return request(url, method=method, body=body, headers=headers,
                           timeout=self._timeout(timeout), **kwargs)

        self.raw._auth_request = guarded_request
        return True

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def _timeout(self, requested):
        remaining = self.remaining()
        return min(1, remaining, requested if isinstance(requested, (int, float)) else 1)

    def send(self, request, **kwargs):
        # AuthorizedSession prepares credentials and may retry a 401 inside
        # request(). Every resulting send needs a fresh admission/time budget.
        kwargs["timeout"] = self._timeout(kwargs.get("timeout"))
        return self._send(request, **kwargs)

    def request(self, *args, **kwargs):
        kwargs["timeout"] = self._timeout(kwargs.get("timeout"))
        response = self.raw.request(*args, **kwargs)
        self.remaining()
        return response


_MISSING = object()


def _transport_sessions(client) -> list:
    """Every session one submission can dispatch through.

    `AuthorizedSession.request` handles a 401 by refreshing the credential, and that refresh goes through the
    session's OWN `_auth_request`, a separate plain `requests.Session`. Guarding only `client._http` leaves that
    refresh unbounded and admitted after stop (Astra PR47 re-review R4)."""
    session = getattr(client, "_http", None)
    if session is None:
        return []
    sessions = [session]
    auth_request = getattr(session, "_auth_request", None)
    inner = getattr(auth_request, "session", None)
    if inner is not None and inner is not session:
        sessions.append(inner)
    return sessions


@contextmanager
def _guarded_send(client, window, cleanup: bool):
    """Guard the ACTUAL HTTP send for the duration of one submission (Astra PR47 #4).

    `submit()` checks admission, then calls `client.query(...)`. Inside that call google-auth may refresh the
    credential, and a refresh that outlives the stop lets the job POST leave after the window closed. Re-checking at
    the moment of dispatch closes that race, and the session's own internal 401 retry gets a fresh budget too.

    The override is installed and removed inside `submit`'s lock, so the caller's transport is unchanged before and
    after: cancellation and terminal readbacks, which run after stop by design, keep working on it."""
    sessions = _transport_sessions(client)
    if not sessions:
        yield False
        return

    def guard(inner):
        def send(request, **kwargs):
            window.check(cleanup=cleanup)      # a refresh that crossed stop cannot be followed by a submission
            remaining = window.remaining(cleanup)
            requested = kwargs.get("timeout")
            # the refresh must get a FRESH budget, not the timeout copied from the original submission
            kwargs["timeout"] = min(remaining, requested) if isinstance(requested, (int, float)) else remaining
            return inner(request, **kwargs)
        return send

    restore = []
    try:
        for session in sessions:
            previous = session.__dict__.get("send", _MISSING)
            try:
                session.send = guard(session.send)
            except (AttributeError, TypeError):   # a frozen transport: report it rather than pretend
                yield False
                return
            restore.append((session, previous))
        yield True
    finally:
        for session, previous in restore:
            if previous is _MISSING:
                session.__dict__.pop("send", None)
            else:
                session.send = previous


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


def cancel_jobs(client, job_ids: list[str], refs: Optional[dict] = None) -> list[dict]:
    """`refs` maps job_id -> the qualified reference it must be read back with. Dropping it makes every job read under
    the module defaults, where an absent job then certifies completion (Astra PR47 RR3 N1)."""
    refs = refs or {}
    return _cancel_pending([(job_id, client, refs.get(job_id)) for job_id in job_ids])


def _cancel_one(pair) -> dict:
    """Cancel and read back ONE job under its own qualified reference.

    `ref` carries the (project, location) the job was actually submitted under: a worker's job in another
    project/location read under the module defaults returns NotFound while the real job keeps running.
    `notfound_is_done` is true only for ids THIS window journaled before submitting - for those an absent job really
    is a submission that never happened. An adopted id whose submission was never confirmed cannot borrow that
    reasoning (Astra PR47 re-review R1)."""
    job_id, client, ref = pair
    ref = ref or {}
    project, location = ref.get("project") or PROJECT, ref.get("location") or LOCATION
    base = {"job_id": job_id, "project": project, "location": location}
    if ref.get("adopted"):
        base["adopted"] = True
    if client is None:
        return dict(base, state="NO_CLIENT", verified_done=False,
                    error="no client can read this reference back; the obligation is unresolved")
    try:
        client.cancel_job(job_id, project=project, location=location, retry=None, timeout=10)
        job = client.get_job(job_id, project=project, location=location, retry=None, timeout=10)
        return dict(base, state=job.state, verified_done=job.state == "DONE")
    except TypeError:   # a client whose cancel/get does not take `project` (the driver's own fakes and older paths)
        try:
            client.cancel_job(job_id, location=location, retry=None, timeout=10)
            job = client.get_job(job_id, location=location, retry=None, timeout=10)
            return dict(base, state=job.state, verified_done=job.state == "DONE")
        except NotFound:
            return dict(base, state="NOT_FOUND", verified_done=bool(ref.get("notfound_is_done", True)),
                        error=None if ref.get("notfound_is_done", True) else
                        "absent under this reference, and this window never confirmed its submission")
        except Exception as exc:  # noqa: BLE001
            return dict(base, verified_done=False, error=f"{type(exc).__name__}: {exc}"[:300])
    except NotFound:
        # IDs are journaled before submission; a stopped/failed submission may not exist. An ADOPTED id whose
        # submission was never confirmed gets no such benefit of the doubt.
        return dict(base, state="NOT_FOUND", verified_done=bool(ref.get("notfound_is_done", True)),
                    error=None if ref.get("notfound_is_done", True) else
                    "absent under this reference, and this window never confirmed its submission")
    except Exception as exc:  # noqa: BLE001
        return dict(base, verified_done=False, error=f"{type(exc).__name__}: {exc}"[:300])


def _cancel_pending(pending) -> list[dict]:
    if len(pending) < 2:
        return [_cancel_one(pair) for pair in pending]
    # Independent jobs can be cancelled together; map preserves journal order.
    with ThreadPoolExecutor(max_workers=min(8, len(pending))) as executor:
        return list(executor.map(_cancel_one, pending))


class WindowJobs:
    def __init__(self, label: str, deadline: float, journal: str | Path, clock=None):
        self.label, self.deadline, self.journal = label, deadline, Path(journal)
        # injected so a controller and its gate share one clock. `None` keeps resolving `time.monotonic` through the
        # module at call time, which is what the existing driver regressions monkeypatch.
        self._clock = clock or (lambda: time.monotonic())
        self.cleanup_deadline: float | None = None   # a SEPARATE bounded channel, opened only after workload stop
        self.cleanup_jobs = 0
        self.cleanup_max_jobs = 0
        self.adopted: dict[str, dict] = {}
        self.refs: dict[str, dict] = {}          # job_id -> the qualified reference it must be read back with
        self.dry_runs: list[dict] = []           # bounded operations that create no server job
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
                                   "job_ids": list(self._jobs), "finished_job_ids": sorted(self._finished),
                                   "job_refs": {i: dict(r) for i, r in self.refs.items()},
                                   "dry_run_operations": len(self.dry_runs)}, indent=2))
        os.replace(tmp, self.journal)

    def end(self, cleanup: bool = False) -> float:
        return self.cleanup_deadline if (cleanup and self.cleanup_deadline is not None) else self.deadline

    def remaining(self, cleanup: bool = False) -> float:
        return max(0.001, self.end(cleanup) - self._clock())

    def check(self, cleanup: bool = False):
        """Admission. `cleanup=True` uses the separate bounded cleanup channel, which exists so a resource restoration
        (row-policy DDL, ACL repair) can still be SUBMITTED and journaled after workload admission closed. Without it,
        stopping the only channel makes every restore raise, and the obligation is silently lost (Astra PR47 #3)."""
        if cleanup and self.cleanup_deadline is not None:
            if self._clock() >= self.cleanup_deadline:
                raise WindowStopped("the cleanup channel deadline passed")
            if self.cleanup_max_jobs and self.cleanup_jobs >= self.cleanup_max_jobs:
                raise WindowStopped("the cleanup channel job budget is spent")
            return
        if self._clock() >= self.deadline:
            self.stop.set()
        if self.stop.is_set():
            raise WindowStopped("reservation window stopped or deadline reached")

    def open_cleanup(self, seconds: float, max_jobs: int = 20) -> float:
        """Open the bounded cleanup channel. Called only after workload admission is closed."""
        self.cleanup_deadline = self._clock() + seconds
        self.cleanup_max_jobs = max_jobs
        return self.cleanup_deadline

    def close_cleanup(self) -> None:
        self.cleanup_deadline = None

    def wait(self, seconds: float):
        self.check()
        self.stop.wait(max(0, min(seconds, self.deadline - self._clock())))
        self.check()

    def bind(self, client, cleanup: bool = False):
        return WindowClient(client, self, cleanup=cleanup)

    def adopt(self, job_id: str, client=None, project: Optional[str] = None, location: Optional[str] = None,
              state: Optional[str] = None, **meta) -> dict:
        """Take responsibility for a job this process did not submit - a receipt child's, say.

        The FULL reference is kept: a child job in another project or location read back under the module defaults
        returns NotFound while the real job keeps running. A reference whose submission the worker never confirmed
        (`state` is not SUBMITTED) is unresolved, so an absent job cannot close it."""
        with self._lock:
            confirmed = state in (None, "SUBMITTED", "DONE")
            entry = {"job_id": job_id, "adopted_at": _dt_now(), "project": project or PROJECT,
                     "location": location or LOCATION, "state": state, "confirmed_submitted": confirmed, **meta}
            self.adopted[job_id] = entry
            self.refs[job_id] = {"project": entry["project"], "location": entry["location"], "adopted": True,
                                 "notfound_is_done": confirmed}
            self._jobs.setdefault(job_id, client)
            self._save()
        return entry

    def submit(self, client, method, args, kwargs):
        # Lock covers admission + registration + submit, never result waiting.
        # The stop event is set before cancellation takes this lock, closing races.
        cleanup = bool(kwargs.pop("okf_cleanup", False))
        with self._lock:
            self.check(cleanup=cleanup)
            kwargs = dict(kwargs)
            cfg = copy.deepcopy(kwargs.get("job_config"))
            if cfg is None:
                cfg = bigquery.QueryJobConfig() if method == "query" else bigquery.LoadJobConfig()
            cfg.labels = dict(cfg.labels or {}, okf_spike="bq_graph_20260905", window=self.label,
                              **({"okf_stage": "cleanup"} if cleanup else {}))
            # A DRY RUN creates no server job: BigQuery returns no jobReference at all. Inventing an id for it puts a
            # phantom into the cleanup union, whose 404 then reads as `verified_done`. It is a bounded OPERATION, the
            # same way the receipt child already treats one (Astra PR47 re-review P2).
            dry = bool(getattr(cfg, "dry_run", False))
            job_id = None if dry else f"okf_graph_{self.label}_{'cleanup_' if cleanup else ''}{uuid.uuid4().hex}"
            kwargs.update(job_config=cfg, timeout=max(.001, min(30, self.remaining(cleanup))))
            if not dry:
                kwargs["job_id"] = job_id
            if method == "query":
                kwargs["retry"] = None
                kwargs["job_retry"] = None  # no invisible resubmissions with new IDs
            else:
                kwargs["num_retries"] = 0
            if dry:
                self.dry_runs.append({"at": _dt_now(), "method": method, "cleanup": cleanup, "actual_job": False})
            else:
                self._jobs[job_id] = client
                self.refs[job_id] = {"project": PROJECT, "location": LOCATION, "notfound_is_done": True}
                if cleanup:
                    self.cleanup_jobs += 1
            self._save()  # survives a lost submit response or killed driver
            # the send guard re-checks admission at the ACTUAL dispatch, including after a credential refresh
            with _guarded_send(client, self, cleanup):
                job = getattr(client, method)(*args, **kwargs)
        return WindowJob(job, self, job_id, method == "query", cleanup=cleanup, dry_run=dry)

    def finished(self, job_id):
        if job_id is None:      # a dry run created no job: there is nothing to finish or clean up
            return
        with self._lock:
            self._finished.add(job_id)
            self._save()

    def stop_and_cancel(self) -> list[dict]:
        self.stop.set()
        with self._cancel_lock:
            with self._lock:
                pending = [(i, c, self.refs.get(i)) for i, c in self._jobs.items() if i not in self._finished]
            for result in _cancel_pending(pending):
                job_id = result["job_id"]
                self._cancelled[job_id] = result
                if result["verified_done"]:
                    self.finished(job_id)
            with self._lock:
                _save_cleanup(self.journal, json.loads(self.journal.read_text()), list(self._cancelled.values()))
            return list(self._cancelled.values())


class WindowClient:
    def __init__(self, client, window, cleanup: bool = False):
        self.raw, self.window, self.cleanup = client, window, cleanup
        # a transport we cannot guard is reported, never assumed safe
        self.submission_guarded = getattr(client, "_http", None) is not None

    def query(self, *args, **kwargs):
        return self.window.submit(self.raw, "query", args, dict(kwargs, okf_cleanup=self.cleanup))

    def load_table_from_json(self, *args, **kwargs):
        return self.window.submit(self.raw, "load_table_from_json", args, dict(kwargs, okf_cleanup=self.cleanup))

    def __getattr__(self, name):
        return getattr(self.raw, name)


class WindowJob:
    def __init__(self, job, window, job_id, is_query, cleanup: bool = False, dry_run: bool = False):
        self.raw, self.window, self.job_id, self.is_query, self.cleanup = job, window, job_id, is_query, cleanup
        self.dry_run = dry_run
        self._query_client = job._client if isinstance(job, bigquery.QueryJob) else None

    def __getattr__(self, name):
        return getattr(self.raw, name)

    def _check(self):
        try:
            # a cleanup submission waits on the cleanup channel: the workload stop that preceded it is not its deadline
            self.window.check(cleanup=self.cleanup)
        except WindowStopped:
            self.window.stop_and_cancel()  # before callers unwind executor contexts
            raise

    def result(self, **kwargs):
        self._check()
        timeout = kwargs.pop("timeout", None)
        end = min(self.window.end(self.cleanup), time.monotonic() + (float("inf") if timeout is None else timeout))
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
        self.window.check(cleanup=self.cleanup)
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
    """Detached recovery over a retained journal.

    The journal's `job_refs` travel with it: the project/location each job was submitted under, and whether this
    window ever confirmed the submission. Without them the detached watcher reads an adopted other-project job under
    the module defaults, gets NotFound, and rewrites the receipt as verified while the real job is still RUNNING
    (Astra PR47 RR3 N1)."""
    journal = json.loads(Path(path).read_text())
    if journal["label"] != label or journal["project"] != PROJECT or journal["location"] != LOCATION:
        raise ValueError("job journal does not belong to this reservation window")
    finished = set(journal.get("finished_job_ids", []))
    refs = journal.get("job_refs") or {}
    results = cancel_jobs(client, [i for i in journal["job_ids"] if i not in finished], refs=refs)
    _save_cleanup(Path(path), journal, results)
    return results


def _save_cleanup(path: Path, journal: dict, results: list[dict]):
    """Separate receipt: a late watcher never rewrites the driver's job inventory."""
    done = set(journal.get("finished_job_ids", []))
    done.update(r["job_id"] for r in results if r.get("verified_done"))
    receipt = {"label": journal["label"], "project": journal["project"], "location": journal["location"],
               "job_ids": journal["job_ids"], "verified_done_job_ids": sorted(done), "jobs": results,
               # the references travel INTO the receipt too, so a later reader still knows where each job lives and
               # which ids this window never confirmed it submitted
               "job_refs": journal.get("job_refs") or {},
               "verified": set(journal["job_ids"]) <= done}
    target = path.with_suffix(".cleanup.json")
    tmp = target.with_suffix(f".{os.getpid()}.{threading.get_ident()}.tmp")
    tmp.write_text(json.dumps(receipt, indent=2))
    os.replace(tmp, target)


RESTORES = "restores"


def restore_obligations_path(label: str, evidence_dir: str | Path) -> Path:
    return Path(evidence_dir) / f"restores_{label}.json"


def record_restore_obligations(label: str, evidence_dir: str | Path, obligations: list[dict]) -> Path:
    """Persist this window's resource-restoration obligations so a FAILED restore survives the process.

    Capacity deletion and job cleanup each have a receipt; a row policy or dataset ACL this window changed and could
    not put back is a third, independent obligation. Written BEFORE the restores are attempted (as pending) and
    rewritten afterwards, so a crash mid-restore also leaves the blocker behind (Astra PR47 #3)."""
    path = restore_obligations_path(label, evidence_dir)
    path.parent.mkdir(parents=True, exist_ok=True)
    outstanding = [o for o in obligations if not o.get("ok")]
    body = {"label": label, "project": PROJECT, "location": LOCATION, "at": _dt_now(),
            "obligations": obligations, "outstanding": outstanding,
            "note": "a resource this window changed and could not restore. Capacity deletion and job cleanup do not "
                    "cover it; another window stays prohibited until it is cleared by an owned recovery."}
    tmp = path.with_suffix(f".{os.getpid()}.tmp")
    tmp.write_text(json.dumps(body, indent=2, default=str))
    os.replace(tmp, path)
    return path


def restores_clear(label: str, evidence_dir: str | Path) -> bool:
    """True when this window declares no outstanding restoration. A missing file means nothing was ever changed;
    an unreadable or malformed one is NOT clear."""
    path = restore_obligations_path(label, evidence_dir)
    if not path.exists():
        return True
    try:
        body = json.loads(path.read_text())
        return body.get("label") == label and isinstance(body.get("outstanding"), list) and not body["outstanding"]
    except (OSError, ValueError, TypeError):
        return False


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
