"""Window bridge for the pinned SDK receipt subprocess.

Written by okf_bq_graph.receipt_window. Imported from `usercustomize.py` at interpreter start-up, before the SDK example
runs. Wraps the ACTUAL send/submit/read seams so the parent's window bounds this process too. Edits no SDK source.

Clock domain: OKF_WINDOW_DEADLINE_EPOCH is an ABSOLUTE `time.time()` value supplied by the parent. It is compared to
this process's own `time.time()` and never rebased onto a locally sampled start.
"""
import json
import os
import sys
import threading
import time

LABEL = os.environ.get("OKF_WINDOW_LABEL", "")
INVOCATION = os.environ.get("OKF_WINDOW_INVOCATION", "")   # distinct per child launch: seq numbers restart in each
DEADLINE = float(os.environ.get("OKF_WINDOW_DEADLINE_EPOCH") or 0) or None
STOP_FILE = os.environ.get("OKF_WINDOW_STOP_FILE") or ""
JOURNAL = os.environ.get("OKF_WINDOW_JOURNAL") or ""
MAX_OPS = int(os.environ.get("OKF_WINDOW_MAX_OPS") or 0)
MAX_JOBS = int(os.environ.get("OKF_WINDOW_MAX_JOBS") or 0)
EMAIL_SCOPE = (os.environ.get("OKF_WINDOW_EMAIL_SCOPE") or "1") == "1"
USERINFO_EMAIL = "https://www.googleapis.com/auth/userinfo.email"

installed = []
counts = {"operations": 0, "jobs": 0, "seq": 0}
_lock = threading.Lock()


class WindowStopped(RuntimeError):
    """Admission is closed: the parent stopped the window, or its deadline passed, or a budget is spent."""


def remaining():
    return float("inf") if DEADLINE is None else DEADLINE - time.time()


def stopped():
    return bool(STOP_FILE) and os.path.exists(STOP_FILE)


class JournalUnavailable(RuntimeError):
    """The submission journal could not be written. Nothing may be dispatched: an unjournaled submission is a job
    nobody can reconcile (Astra PR47 #6)."""


def _emit(record):
    """Durable intent. A write failure is NOT swallowed: it is recorded and reported to the caller."""
    if not JOURNAL:
        counts["journal_absent"] = 1
        return False
    try:
        with open(JOURNAL, "a", encoding="utf-8") as fh:
            fh.write(json.dumps(record, default=str) + "\n")
            fh.flush()
            os.fsync(fh.fileno())
        return True
    except (OSError, ValueError) as exc:
        counts["journal_failures"] = counts.get("journal_failures", 0) + 1
        counts["journal_error"] = type(exc).__name__ + ": " + str(exc)[:200]
        return False


def journal(event, **fields):
    with _lock:
        counts["seq"] += 1
        seq = counts["seq"]
    record = dict(fields, event=event, seq=seq, at=time.time(), label=LABEL, invocation=INVOCATION)
    record["journaled"] = _emit(record)
    return record


def require_journal(record):
    """Refuse to dispatch when the intent could not be made durable."""
    if not record.get("journaled"):
        raise JournalUnavailable(
            "the receipt window journal could not be written ("
            + str(counts.get("journal_error", "no journal path was configured"))
            + "); refusing to submit work no one could reconcile")


def update(record, **fields):
    record.update(fields)
    _emit(dict(record, event=record["event"] + "_update", at=time.time()))
    return record


def check(kind="operation"):
    """Admission at the moment of dispatch. Called again for every retry and every result page."""
    if stopped():
        journal("blocked", kind=kind, reason="stopped")
        raise WindowStopped("the parent stopped the receipt window")
    if remaining() <= 0:
        journal("blocked", kind=kind, reason="deadline")
        raise WindowStopped("the receipt window deadline passed")
    with _lock:
        counts["operations"] += 1
        if kind == "job":
            counts["jobs"] += 1
        operations, jobs = counts["operations"], counts["jobs"]
    if MAX_OPS and operations > MAX_OPS:
        journal("blocked", kind=kind, reason="operation_budget", operations=operations)
        raise WindowStopped("the receipt window operation budget is spent")
    if MAX_JOBS and kind == "job" and jobs > MAX_JOBS:
        journal("blocked", kind=kind, reason="job_budget", jobs=jobs)
        raise WindowStopped("the receipt window job budget is spent")


def budget_timeout(requested=None):
    left = remaining()
    if left == float("inf"):
        return requested
    left = max(0.001, left)
    return left if not isinstance(requested, (int, float)) else min(requested, left)


# ------------------------------------------------------------------ import hooks
class _Hook:
    """Meta-path finder that patches one module as it finishes loading (sys.path is incomplete at start-up)."""

    def __init__(self, fullname, apply):
        self.fullname, self.apply = fullname, apply

    def find_spec(self, fullname, path=None, target=None):
        if fullname != self.fullname:
            return None
        try:
            sys.meta_path.remove(self)
        except ValueError:
            return None
        from importlib.machinery import PathFinder
        spec = PathFinder.find_spec(fullname, path, target)
        if spec is None or spec.loader is None or not hasattr(spec.loader, "exec_module"):
            return None
        inner = spec.loader.exec_module

        def exec_module(module):
            inner(module)
            try:
                self.apply(module)
            except Exception as exc:  # the child must fail loudly rather than run unbounded
                journal("hook_failed", module=fullname, error=type(exc).__name__ + ": " + str(exc)[:200])
                raise

        spec.loader.exec_module = exec_module
        return spec


def _patch_auth(module):
    """Scope only: the impersonated token still belongs to the same principal, and tokeninfo still reports it."""
    if not EMAIL_SCOPE:
        installed.append("google.auth(no-scope-shim)")
        return
    inner = module.default

    def default(scopes=None, *args, **kwargs):
        if scopes and USERINFO_EMAIL not in scopes:
            scopes = list(scopes) + [USERINFO_EMAIL]
        return inner(scopes, *args, **kwargs)

    module.default = default
    installed.append("google.auth.default")


def _guard_send(cls):
    """Wrap one Session class's `send`, idempotently. Returns True when this call installed the guard."""
    inner = cls.__dict__.get("send")
    if inner is None:
        return False                       # inherited: the base class guard already covers it
    if getattr(inner, "_okf_guarded", False):
        return False

    def send(self, request, **kwargs):
        # `Session.request()` prepares credentials and may retry a 401 internally; every resulting send is a separate
        # dispatch and gets its own admission and time budget.
        check("http")
        kwargs["timeout"] = budget_timeout(kwargs.get("timeout"))
        return inner(self, request, **kwargs)

    send._okf_guarded = True
    cls.send = send
    return True


def _patch_requests(module):
    """Guard the PLAIN `requests.Session.send`.

    `AuthorizedSession` does not define `send`; it inherits it. More importantly `Credentials.refresh` is handed a
    `google.auth.transport.requests.Request`, which owns its OWN plain `requests.Session` - so a credential refresh
    never touches `AuthorizedSession` at all. Guarding only the subclass leaves the refresh unbounded and admitted
    after stop (Astra PR47 #4)."""
    if _guard_send(module.Session):
        installed.append("requests.Session.send")
    else:
        installed.append("requests.Session.send(already-guarded)")


def _patch_session(module):
    session = module.AuthorizedSession
    if _guard_send(session):
        installed.append("google.auth.transport.requests.AuthorizedSession.send")
    else:
        # it inherits `requests.Session.send`, which the base guard already covers
        installed.append("google.auth.transport.requests.AuthorizedSession.send")


def _job_reference(job):
    return {"job_id": getattr(job, "job_id", None), "project": getattr(job, "project", None),
            "location": getattr(job, "location", None)}


def _patch_bigquery(module):
    client = module.Client
    inner = client.query

    def query(self, *args, **kwargs):
        config = kwargs.get("job_config")
        if config is None and len(args) > 1:
            config = args[1]
        dry = bool(getattr(config, "dry_run", False))
        requested = kwargs.get("job_id")
        entry = journal("query", state="INTENDED", dry_run=dry, actual_job=not dry, job_id=requested,
                        requested_job_id=requested)
        require_journal(entry)               # durable intent BEFORE dispatch, or nothing is dispatched
        try:
            check("operation" if dry else "job")
        except BaseException as exc:
            # admission closed BEFORE the call: nothing was dispatched, so this is a known non-submission
            update(entry, state="REFUSED", error=type(exc).__name__ + ": " + str(exc)[:200])
            raise
        if "job_retry" not in kwargs:
            # in the pinned SDK a default job_retry can submit a NEW job inside result() and replace this object's id
            kwargs["job_retry"] = None
        try:
            job = inner(self, *args, **kwargs)
        except BaseException as exc:
            # the request may or may not have reached the service: unknown is unknown
            update(entry, state="NOT_SUBMITTED" if dry else "UNRESOLVED",
                   error=type(exc).__name__ + ": " + str(exc)[:200])
            raise
        ref = _job_reference(job)
        update(entry, state="DRY_RUN" if dry else "SUBMITTED", **ref,
               id_mutated=bool(requested and ref["job_id"] and ref["job_id"] != requested))
        return job

    client.query = query
    installed.append("google.cloud.bigquery.Client.query")
    try:
        from google.cloud.bigquery import _http as bq_http
    except Exception:
        return
    connection = bq_http.Connection
    raw = connection.api_request

    def api_request(self, *args, **kwargs):
        # the verifier's direct jobs.get / getQueryResults reads
        check("http")
        kwargs["timeout"] = budget_timeout(kwargs.get("timeout"))
        journal("api_request", method=kwargs.get("method") or (args[0] if args else None),
                path=kwargs.get("path") or (args[1] if len(args) > 1 else None), actual_job=False)
        return raw(self, *args, **kwargs)

    connection.api_request = api_request
    installed.append("google.cloud.bigquery._http.Connection.api_request")


def _patch_urlopen():
    import urllib.request
    raw = urllib.request.urlopen

    def urlopen(url, *args, **kwargs):
        check("http")                                   # broker.open_live_session reads tokeninfo before any client
        kwargs["timeout"] = budget_timeout(kwargs.get("timeout"))
        journal("urlopen", host=str(url).split("?", 1)[0][:120], actual_job=False)
        return raw(url, *args, **kwargs)

    urllib.request.urlopen = urlopen
    installed.append("urllib.request.urlopen")


def install():
    """Idempotent: a child that also calls it explicitly must not wrap a seam twice."""
    if counts.get("installed_once"):
        return installed
    counts["installed_once"] = 1
    if "requests" in sys.modules:
        _patch_requests(sys.modules["requests"])
    else:
        sys.meta_path.insert(0, _Hook("requests", _patch_requests))
    sys.meta_path.insert(0, _Hook("google.auth", _patch_auth))
    sys.meta_path.insert(0, _Hook("google.auth.transport.requests", _patch_session))
    sys.meta_path.insert(0, _Hook("google.cloud.bigquery", _patch_bigquery))
    _patch_urlopen()
    journal("bridge_installed", deadline_epoch=DEADLINE, stop_file=STOP_FILE, max_ops=MAX_OPS, max_jobs=MAX_JOBS)
    return installed
