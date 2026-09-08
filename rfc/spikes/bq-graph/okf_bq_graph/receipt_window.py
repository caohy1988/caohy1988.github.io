"""The receipt child's window bridge (Slice A, U3, KTD3).

`chain.run_receipt` launches the pinned SDK example as a subprocess. `subprocess.run(timeout=900)` bounds the PROCESS,
not the server: killing the child cancels nothing, and every job it submitted keeps running inside paid capacity that
the parent is about to close. The child also builds its own BigQuery clients (`broker.Session.delegated_client`), so
the parent's `WindowJobs` gate never sees them.

This module is the process-local bootstrap that closes that gap WITHOUT editing a single SDK source file. It writes a
private `usercustomize.py` (never `sitecustomize.py`: this interpreter ships one that completes `sys.path`, and a
PYTHONPATH copy shadows it) which installs import hooks in the child:

  * `google.auth.default` - composed with the existing `principal._SCOPE_SHIM` behaviour, adding the `userinfo.email`
    scope the SDK's tokeninfo identity check needs from an impersonated token. Scope only; never identity.
  * `google.auth.transport.requests.AuthorizedSession.send` - the ACTUAL HTTP send, so credential refresh and the
    session's own internal 401 retry each get a fresh admission and time budget. Wrapping `request()` alone does not
    cover the retry (vault: 2026-09-06 graph auth-transport correction).
  * `google.cloud.bigquery.Client.query` - every submission is journaled BEFORE the send with the caller's own job id.
    The SDK's deterministic `execute.job_id_for` id is part of its receipt/recovery contract and is never replaced. A
    submission whose response is lost stays `UNRESOLVED`; it is never relabelled `NOT_SUBMITTED`. Automatic job retry
    is disabled unless the caller asked for it, because in the pinned SDK a retry inside `result()` submits a NEW job
    and replaces the object's id.
  * `google.cloud.bigquery._http.Connection.api_request` - the direct REST reads `verify.BigQueryEvidenceClient` uses.
    A verifier read is bounded work inside the window like anything else.
  * `urllib.request.urlopen` - `broker.open_live_session` reads oauth2 tokeninfo through it before any client exists.

Dry runs are bounded operations, not jobs: `broker._probe_table` and the SDK's own access probe call
`query(dry_run=True)`, which submits nothing. They consume the operation budget and are journaled with
`actual_job: false`, so no phantom id reaches the cleanup or identity union - while a real submission whose outcome is
unknown stays unresolved.

The child is handed a NONSECRET window identity: a label, an ABSOLUTE deadline in `time.time()` epoch seconds (the
clock domain is stated so nothing rebases it onto an earlier sampled start), a stop-file channel and its own private
journal path. No credential material is placed in the window record or the retained diagnostics.

`preflight()` proves the selected pinned entrypoint is covered BEFORE any paid window opens. When the pin does not
carry the seams this bridge needs, the honest Slice A outcome is `SDK_WINDOW_BRIDGE_UNSUPPORTED`: the lifecycle
plumbing still lands and Slice B stays blocked until a separately scoped SDK change and pin update are reviewed.
"""
from __future__ import annotations

import json
import os
import signal
import subprocess
import sys
import time
import uuid
from pathlib import Path
from typing import Any, Optional

from .principal import USERINFO_EMAIL

SUPPORTED, UNSUPPORTED = "SUPPORTED", "SDK_WINDOW_BRIDGE_UNSUPPORTED"
EXAMPLE_REL = "examples/okf_attested_computation"

#: The exact integration seams this bridge covers, at the pinned SDK commit. Each is (relative path, source marker).
SEAMS = (
    ("run.py", "def caller(self)"),
    ("run.py", "def evidence(self, mode"),
    ("broker.py", "def delegated_client(self)"),
    ("broker.py", "google.auth.default("),
    ("broker.py", "urllib.request.urlopen("),
    ("execute.py", "def job_id_for(request: dict)"),
    ("verify.py", "self._client._connection.api_request("),
)

BRIDGE_MODULE = "okf_window_bridge"


# ----------------------------------------------------------------------------- child bootstrap source
_BRIDGE_SOURCE = '''"""Window bridge for the pinned SDK receipt subprocess.

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
USERINFO_EMAIL = "{userinfo_email}"

installed = []
counts = {{"operations": 0, "jobs": 0, "seq": 0}}
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
            fh.write(json.dumps(record, default=str) + "\\n")
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
    return {{"job_id": getattr(job, "job_id", None), "project": getattr(job, "project", None),
            "location": getattr(job, "location", None)}}


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
'''

_USERCUSTOMIZE = '''"""Written by okf_bq_graph.receipt_window. Deliberately `usercustomize`, not `sitecustomize`: this
interpreter already ships a `sitecustomize` that completes sys.path, and a PYTHONPATH copy shadows it. Importing the
bridge has no effect on its own; the guards are installed here, at interpreter start-up, before the SDK example runs."""
import {module} as _bridge

_bridge.install()
'''


def bootstrap_files(directory: str | os.PathLike, email_scope: bool = True) -> dict:
    """Write the child bootstrap into a caller-owned private directory. Returns the paths, no secrets."""
    d = Path(directory)
    d.mkdir(parents=True, exist_ok=True)
    bridge = d / f"{BRIDGE_MODULE}.py"
    bridge.write_text(_BRIDGE_SOURCE.format(userinfo_email=USERINFO_EMAIL), encoding="utf-8")
    customize = d / "usercustomize.py"
    customize.write_text(_USERCUSTOMIZE.format(module=BRIDGE_MODULE), encoding="utf-8")
    return {"dir": str(d), "bridge": str(bridge), "usercustomize": str(customize), "email_scope": bool(email_scope)}


# ----------------------------------------------------------------------------- preflight
def preflight(sdk_root: str | os.PathLike, example_rel: str = EXAMPLE_REL) -> dict:
    """Prove the pinned entrypoint carries every seam this bridge relies on, BEFORE any paid window opens.

    Source inspection only: nothing is imported or executed from the SDK checkout, and no network is touched."""
    root = Path(sdk_root) / example_rel
    entry = root / "run.py"
    covered, missing = [], []
    if not entry.is_file():
        return {"status": UNSUPPORTED, "sdk_root": str(sdk_root), "entrypoint": str(entry),
                "reason": "the pinned SDK entrypoint is not present", "covered": [], "missing": [s[0] for s in SEAMS]}
    sources: dict[str, Optional[str]] = {}
    for rel, marker in SEAMS:
        if rel not in sources:
            try:
                sources[rel] = (root / rel).read_text(encoding="utf-8")
            except OSError:
                sources[rel] = None
        text = sources[rel]
        (covered if text is not None and marker in text else missing).append({"file": rel, "marker": marker})
    status = SUPPORTED if not missing else UNSUPPORTED
    return {"status": status, "sdk_root": str(sdk_root), "entrypoint": str(entry),
            "covered": covered, "missing": missing,
            "reason": None if status == SUPPORTED else
                      "the pinned SDK does not carry the seams this bridge wraps; a separately scoped SDK injection "
                      "hook and an explicit pin update are prerequisites to a live receipt leg",
            "note": "source inspection at the pinned checkout; the SDK is neither imported nor edited"}


# ----------------------------------------------------------------------------- parent-side bridge
class ReceiptBridge:
    """Parent-side owner of one receipt child's window membership."""

    def __init__(self, sdk_root: str | os.PathLike, *, label: str, deadline_epoch: float,
                 directory: str | os.PathLike, email_scope: bool = True, max_ops: int = 0, max_jobs: int = 0,
                 example_rel: str = EXAMPLE_REL):
        self.sdk_root, self.label, self.example_rel = str(sdk_root), label, example_rel
        self.deadline_epoch = float(deadline_epoch)
        self.dir = Path(directory)
        self.email_scope, self.max_ops, self.max_jobs = email_scope, max_ops, max_jobs
        # ONE JOURNAL PER LAUNCH. The child's sequence counter restarts in every interpreter, so a shared file makes
        # two launches collide on `seq` and the second silently replaces the first (Astra PR47 #5).
        self.journal_dir = self.dir / "journal"
        self.launches: list[dict] = []
        self._launch = 0
        self.stop_path = self.dir / "STOP"
        self._process: Any = None
        self.record: dict[str, Any] = {"bridge": "okf_bq_graph.receipt_window/0.2.0", "label": label,
                                       "deadline_epoch": self.deadline_epoch,
                                       "clock_domain": "absolute time.time() epoch seconds, supplied by the parent and "
                                                       "never rebased onto a child-sampled start"}

    # ---------------------------------------------------------------- handshake
    def handshake(self, python: Optional[str] = None, timeout: float = 60) -> dict:
        """Preflight the pin, write the bootstrap, then prove IN A CHILD INTERPRETER that the guards installed."""
        pre = preflight(self.sdk_root, self.example_rel)
        self.record["preflight"] = pre
        if pre["status"] != SUPPORTED:
            self.record["status"] = UNSUPPORTED
            self.record["reason"] = pre["reason"]
            return self.record
        self.record["bootstrap"] = bootstrap_files(self.dir, email_scope=self.email_scope)
        # The probe reports what start-up ACTUALLY installed. It deliberately does not call `install()` itself: the
        # question is whether `usercustomize` ran, which is exactly what a live child depends on.
        probe = ("import json, site, sys\n"
                 "import google.auth, google.auth.transport.requests, google.cloud.bigquery, requests\n"
                 "b = sys.modules.get('" + BRIDGE_MODULE + "')\n"
                 "print(json.dumps({'installed': (b.installed if b else []), 'imported': b is not None,\n"
                 "                  'enable_user_site': bool(site.ENABLE_USER_SITE)}))\n")
        env = dict(os.environ, **self.child_env())
        env.pop("OKF_WINDOW_JOURNAL", None)   # the handshake must not write into the run's own journal
        try:
            proc = subprocess.run([python or sys.executable, "-c", probe], capture_output=True, text=True,
                                  timeout=timeout, env=env)
        except (OSError, subprocess.TimeoutExpired) as e:
            self.record.update(status=UNSUPPORTED, reason=f"the handshake child did not complete: {type(e).__name__}")
            return self.record
        try:
            observed = json.loads((proc.stdout or "").strip().splitlines()[-1])
        except (ValueError, IndexError):
            self.record.update(status=UNSUPPORTED, exit_code=proc.returncode,
                               reason="the handshake child produced no readable bridge report",
                               stderr_tail=(proc.stderr or "")[-800:])
            return self.record
        required = {"google.auth.default", "google.auth.transport.requests.AuthorizedSession.send",
                    "google.cloud.bigquery.Client.query", "google.cloud.bigquery._http.Connection.api_request",
                    "urllib.request.urlopen", "requests.Session.send"}
        if not self.email_scope:
            required.discard("google.auth.default")
        installed = {name.split("(")[0] for name in (observed.get("installed") or [])}
        gaps = sorted(required - installed)
        self.record["child"] = {"exit_code": proc.returncode, "installed": sorted(observed.get("installed") or []),
                                "missing": gaps, "bootstrap_imported": bool(observed.get("imported")),
                                "enable_user_site": observed.get("enable_user_site")}
        if proc.returncode != 0 or gaps:
            if observed.get("enable_user_site") is False:
                # `usercustomize` is only imported when user site-packages are enabled. A virtualenv created with
                # --no-user-site (or PYTHONNOUSERSITE) never runs the bootstrap, so no guard can be installed at
                # start-up. That is a genuine refusal, not a test to relax (Astra PR47 P2).
                self.record.update(status=UNSUPPORTED, bootstrap="USERCUSTOMIZE_DISABLED",
                                   reason="the child interpreter has user site-packages disabled "
                                          "(site.ENABLE_USER_SITE is false), so `usercustomize` never runs and no "
                                          "start-up guard can be installed; a bounded receipt child is unsupported on "
                                          "this interpreter")
            else:
                self.record.update(status=UNSUPPORTED,
                                   reason=f"the child interpreter did not install every guard: missing {gaps}")
            return self.record
        self.record["status"] = SUPPORTED
        return self.record

    # ---------------------------------------------------------------- launches
    @property
    def journal_path(self) -> Path:
        """The CURRENT launch's journal. `ingest()` reconciles every launch, not just this one."""
        return self.journal_dir / f"launch_{self._launch:03d}.jsonl"

    def next_launch(self, name: Optional[str] = None) -> dict:
        self._launch += 1
        self.journal_dir.mkdir(parents=True, exist_ok=True)
        entry = {"launch": self._launch, "name": name or f"launch-{self._launch}",
                 "invocation": f"{self.label}-{self._launch:03d}-{uuid.uuid4().hex[:8]}",
                 "journal": str(self.journal_path), "started_at": time.time()}
        self.launches.append(entry)
        return entry

    def journal_files(self) -> list[Path]:
        if not self.journal_dir.is_dir():
            return []
        return sorted(self.journal_dir.glob("launch_*.jsonl"))

    # ---------------------------------------------------------------- child contract
    def child_env(self) -> dict:
        """Nonsecret window identity for the child, plus the bootstrap on PYTHONPATH."""
        if not self.launches:
            self.next_launch()
        existing = os.environ.get("PYTHONPATH")
        env = {"PYTHONPATH": str(self.dir) + (os.pathsep + existing if existing else ""),
               "OKF_WINDOW_LABEL": self.label,
               "OKF_WINDOW_INVOCATION": self.launches[-1]["invocation"],
               "OKF_WINDOW_DEADLINE_EPOCH": repr(self.deadline_epoch),
               "OKF_WINDOW_STOP_FILE": str(self.stop_path),
               "OKF_WINDOW_JOURNAL": str(self.journal_path),
               "OKF_WINDOW_EMAIL_SCOPE": "1" if self.email_scope else "0"}
        if self.max_ops:
            env["OKF_WINDOW_MAX_OPS"] = str(self.max_ops)
        if self.max_jobs:
            env["OKF_WINDOW_MAX_JOBS"] = str(self.max_jobs)
        return env

    def stop(self) -> None:
        """Close the child's admission. Checked before every dispatch, including retries and result pages."""
        self.dir.mkdir(parents=True, exist_ok=True)
        self.stop_path.write_text(json.dumps({"stopped_at": time.time()}), encoding="utf-8")

    # ---------------------------------------------------------------- ingestion
    def entries(self) -> list[dict]:
        """Every record from every launch journal, tagged with its file. Read errors are RECORDS, not silence."""
        out: list[dict] = []
        files = self.journal_files()
        expected = {str(l["journal"]) for l in self.launches}
        for path in sorted({*files, *(Path(p) for p in expected)}):
            if not path.exists():
                if str(path) in expected:
                    out.append({"event": "journal_missing", "journal": str(path),
                                "error": "a launch journal the parent allocated does not exist"})
                continue
            try:
                lines = path.read_text(encoding="utf-8").splitlines()
            except OSError as e:
                out.append({"event": "journal_unreadable", "journal": str(path),
                            "error": f"{type(e).__name__}: {str(e)[:200]}"})
                continue
            for line in lines:
                try:
                    record = json.loads(line)
                    record["journal"] = str(path)
                    out.append(record)
                except ValueError:
                    out.append({"event": "unparsable", "journal": str(path), "raw": line[:200]})
        return out

    def ingest(self) -> dict:
        """Fold every launch's private journal into the parent's inventory.

        Records are keyed by `(invocation, journal, seq)`: the child's counter restarts in each interpreter, so folding
        on `seq` alone loses every launch but the last. A dry run is a bounded OPERATION with no job id and never
        enters the cleanup or identity union. A submission whose response was lost, or one whose journal cannot be
        read, stays UNRESOLVED - calling either an absence would be inventing one."""
        entries = self.entries()
        by_key: dict[tuple, dict] = {}
        damaged = [e for e in entries if e.get("event") in ("unparsable", "journal_unreadable", "journal_missing")]
        for e in entries:
            seq = e.get("seq")
            if seq is None:
                continue
            key = (e.get("invocation"), e.get("journal"), seq)
            base = by_key.setdefault(key, {})
            base.update({k: v for k, v in e.items() if k != "event"})
            base["event"] = e["event"].replace("_update", "")
        queries = [e for e in by_key.values() if e.get("event") == "query"]
        jobs = [{"job_id": e.get("job_id"), "project": e.get("project"), "location": e.get("location"),
                 "state": e.get("state"), "requested_job_id": e.get("requested_job_id"),
                 "invocation": e.get("invocation"), "id_mutated": bool(e.get("id_mutated"))}
                for e in queries if e.get("actual_job") and e.get("state") == "SUBMITTED" and e.get("job_id")]
        # UNRESOLVED: the send happened and the outcome is unknown. INTENDED: the child died between the journal
        # entry and the dispatch, so the outcome is unknown too. REFUSED is the only known non-submission, because
        # admission was closed before the call was made.
        unresolved = [{"seq": e.get("seq"), "invocation": e.get("invocation"), "journal": e.get("journal"),
                       "requested_job_id": e.get("requested_job_id"), "state": e.get("state"), "error": e.get("error")}
                      for e in queries if e.get("actual_job") and e.get("state") in ("UNRESOLVED", "INTENDED")]
        refused = [e for e in queries if e.get("state") == "REFUSED"]
        for record in damaged:
            # damaged evidence is itself an unresolved lifecycle obligation: what it was hiding cannot be established
            unresolved.append({"seq": None, "journal": record.get("journal"), "state": "JOURNAL_DAMAGED",
                               "error": record.get("error") or f"unparsable record: {record.get('raw', '')[:120]}"})
        launched = len(self.launches)
        seen = {e.get("invocation") for e in by_key.values() if e.get("invocation")}
        silent = [l["invocation"] for l in self.launches if l["invocation"] not in seen]
        for invocation in silent:
            unresolved.append({"seq": None, "invocation": invocation, "state": "LAUNCH_UNJOURNALED",
                               "error": "a launch produced no journal record at all: its submissions are unknown"})
        return {"journal_dir": str(self.journal_dir), "journals": [str(p) for p in self.journal_files()],
                "launches": launched, "entries": len(entries),
                "jobs": jobs, "unresolved": unresolved, "refused": len(refused),
                "damaged": [{"journal": d.get("journal"), "event": d["event"]} for d in damaged],
                "dry_runs": len([e for e in queries if not e.get("actual_job")]),
                "operations": len([e for e in by_key.values() if e.get("event") in ("api_request", "urlopen", "query")]),
                "blocked": [e for e in by_key.values() if e.get("event") == "blocked"],
                "installed": bool(self.record.get("status") == SUPPORTED),
                "complete": not unresolved and not damaged and not silent,
                "note": "dry runs are bounded operations with no job id and never enter the cleanup or identity union; "
                        "a lost real submission, a damaged journal and a silent launch all stay UNRESOLVED"}

    def jobs(self) -> list[dict]:
        """Qualified references the controller adopts into the window's cleanup union."""
        return self.ingest()["jobs"]

    def join(self, timeout: float = 30.0) -> dict:
        """Join the running child before the parent seals its cleanup union.

        Terminating a process cancels no server job, so this closes admission first, waits, and only then terminates -
        and reports what it had to do."""
        proc = self._process
        if proc is None:
            return {"joined": True, "running": False}
        self.stop()
        outcome = {"joined": False, "running": True, "pid": proc.pid, "terminated": False, "killed": False}
        try:
            proc.wait(timeout=timeout)
            outcome.update(joined=True, running=False, returncode=proc.returncode)
            return outcome
        except subprocess.TimeoutExpired:
            pass
        proc.terminate()
        outcome["terminated"] = True
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            proc.kill()
            outcome["killed"] = True
            proc.wait()
        outcome.update(joined=True, running=False, returncode=proc.returncode,
                       note="the child was terminated; terminating a process does not cancel its server jobs, so its "
                            "retained references stay unresolved until they are read back")
        return outcome

    # ---------------------------------------------------------------- runner
    def runner(self, terminate_grace: float = 10.0):
        """A `chain.run_receipt`-compatible runner that keeps the child inside this window.

        The parent's stop reaches the child through the stop file FIRST (closing admission), then the process is
        terminated and joined. Killing a process never cancels a server job, so the retained references from the
        child's journal are what the parent reconciles afterwards."""

        def run(argv, cwd=None, env=None, capture_output=True, text=True, timeout=None):
            self.next_launch()               # a fresh journal per launch: sequence numbers restart in every child
            merged = dict(env or os.environ)
            merged.update(self.child_env())
            budget = max(0.0, self.deadline_epoch - time.time())
            limit = budget if timeout is None else min(timeout, budget)
            proc = subprocess.Popen(argv, cwd=cwd, env=merged, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                                    text=text, start_new_session=True)
            self._process = proc             # so the controller can join this child before sealing cleanup
            try:
                stdout, stderr = proc.communicate(timeout=max(0.001, limit))
                self._process = None
                return subprocess.CompletedProcess(argv, proc.returncode, stdout, stderr)
            except subprocess.TimeoutExpired:
                self.stop()                       # close admission before the process dies
                try:
                    proc.send_signal(signal.SIGTERM)
                    stdout, stderr = proc.communicate(timeout=terminate_grace)
                except subprocess.TimeoutExpired:
                    proc.kill()
                    stdout, stderr = proc.communicate()
                self._process = None
                note = ("\nokf: the receipt child exceeded the window budget; admission was closed and the process was "
                        "terminated. Terminating a process does not cancel its server jobs: the journal's retained "
                        "references are unresolved until they are read back.")
                return subprocess.CompletedProcess(argv, proc.returncode if proc.returncode is not None else -1,
                                                   stdout or "", (stderr or "") + note)

        return run
