"""U3: the receipt child's window bridge.

The subprocess tests build a REAL `google.cloud.bigquery.Client` on a REAL `AuthorizedSession` inside the child, and
serve it from a mounted `requests` adapter, so the whole path - `Client.query` -> `Connection.api_request` ->
`AuthorizedSession.request` -> the wrapped `send` -> adapter - is exercised offline. No credential, no ADC and no
network is used: the session carries `AnonymousCredentials` and every host is served by the adapter.

The in-process tests load the generated bridge module WITHOUT calling `install()`, so the guards are applied to fake
modules and never leak into the test interpreter.
"""
import importlib.util
import json
import os
import shutil
import subprocess
import threading
import sys
import time
from pathlib import Path
from types import SimpleNamespace

import pytest

from okf_bq_graph import receipt_window as RW

SDK_ROOT = os.environ.get("OKF_SDK_ROOT", "/Users/haiyuancao/BigQuery-Agent-Analytics-SDK-receipt-spike")


def sdk_available():
    return (Path(SDK_ROOT) / RW.EXAMPLE_REL / "run.py").is_file()


needs_sdk = pytest.mark.skipif(not sdk_available(), reason="pinned SDK receipt-spike checkout not present")


# ----------------------------------------------------------------------------- preflight
@needs_sdk
def test_preflight_covers_every_seam_at_the_pin():
    out = RW.preflight(SDK_ROOT)
    assert out["status"] == RW.SUPPORTED, out["missing"]
    assert {(s["file"], s["marker"]) for s in out["covered"]} == set(RW.SEAMS)
    assert out["missing"] == []


def test_a_missing_entrypoint_is_unsupported(tmp_path):
    out = RW.preflight(tmp_path)
    assert out["status"] == RW.UNSUPPORTED and "not present" in out["reason"]


@needs_sdk
def test_a_pin_without_a_seam_is_unsupported(tmp_path):
    """A future pin that no longer exposes the delegated client is an honest refusal, not a silent bypass."""
    root = tmp_path / "sdk"
    shutil.copytree(Path(SDK_ROOT) / RW.EXAMPLE_REL, root / RW.EXAMPLE_REL)
    broker = root / RW.EXAMPLE_REL / "broker.py"
    broker.write_text(broker.read_text().replace("def delegated_client(self)", "def client_for_caller(self)"))
    out = RW.preflight(root)
    assert out["status"] == RW.UNSUPPORTED
    assert [m["marker"] for m in out["missing"]] == ["def delegated_client(self)"]
    assert "separately scoped SDK injection" in out["reason"]


@needs_sdk
def test_an_unsupported_pin_never_launches_a_child(tmp_path, monkeypatch):
    monkeypatch.setattr(RW.subprocess, "run", lambda *a, **kw: pytest.fail("no child may run without a covered pin"))
    bridge = RW.ReceiptBridge(tmp_path, label="w", deadline_epoch=time.time() + 60, directory=tmp_path / "priv")
    record = bridge.handshake()
    assert record["status"] == RW.UNSUPPORTED
    assert not (tmp_path / "priv").exists()      # nothing was even written


# ----------------------------------------------------------------------------- handshake
def user_site_enabled(python=None):
    """`usercustomize` only runs when user site-packages are enabled. A venv built with --no-user-site never runs the
    bootstrap, and the bridge must then REFUSE rather than pretend the child is bounded."""
    proc = subprocess.run([python or sys.executable, "-c", "import site; print(bool(site.ENABLE_USER_SITE))"],
                          capture_output=True, text=True, timeout=60)
    return proc.stdout.strip() == "True"


@needs_sdk
def test_handshake_matches_what_the_child_interpreter_can_actually_bootstrap(tmp_path):
    """Astra PR47 P2: assert the branch this interpreter is actually in, and never weaken the refusal to pass."""
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 600, directory=tmp_path / "priv")
    record = bridge.handshake()
    assert not bridge.journal_path.exists()          # the handshake writes nothing into the run's own journal
    if user_site_enabled():
        assert record["status"] == RW.SUPPORTED, record
        assert record["child"]["missing"] == []
        assert record["child"]["bootstrap_imported"] is True
        assert set(record["child"]["installed"]) >= {
            "google.auth.default", "google.auth.transport.requests.AuthorizedSession.send",
            "google.cloud.bigquery.Client.query", "google.cloud.bigquery._http.Connection.api_request",
            "urllib.request.urlopen", "requests.Session.send"}
    else:
        assert record["status"] == RW.UNSUPPORTED
        assert record["bootstrap"] == "USERCUSTOMIZE_DISABLED"
        assert record["child"]["enable_user_site"] is False
        assert "site.ENABLE_USER_SITE is false" in record["reason"]


@needs_sdk
def test_a_child_interpreter_without_usercustomize_is_refused(tmp_path, monkeypatch):
    """Forcing the condition on this interpreter: PYTHONNOUSERSITE disables the bootstrap entirely."""
    monkeypatch.setenv("PYTHONNOUSERSITE", "1")
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 600, directory=tmp_path / "priv")
    record = bridge.handshake()
    assert record["status"] == RW.UNSUPPORTED
    assert record["bootstrap"] == "USERCUSTOMIZE_DISABLED"
    assert record["child"]["bootstrap_imported"] is False


@needs_sdk
def test_the_bootstrap_is_usercustomize_not_sitecustomize(tmp_path):
    files = RW.bootstrap_files(tmp_path)
    assert Path(files["usercustomize"]).name == "usercustomize.py"
    assert not (tmp_path / "sitecustomize.py").exists()
    assert "_bridge.install()" in Path(files["usercustomize"]).read_text()
    # importing the module alone must not install anything: the guards are a deliberate call
    assert "install()" not in Path(files["bridge"]).read_text().rsplit("return installed", 1)[1]


def test_child_env_carries_a_nonsecret_identity_and_an_absolute_deadline(tmp_path):
    deadline = time.time() + 300
    bridge = RW.ReceiptBridge(SDK_ROOT, label="chain-gql-1", deadline_epoch=deadline, directory=tmp_path,
                              max_ops=100, max_jobs=50)
    env = bridge.child_env()
    assert env["OKF_WINDOW_LABEL"] == "chain-gql-1"
    assert float(env["OKF_WINDOW_DEADLINE_EPOCH"]) == deadline      # absolute, not a duration
    assert env["OKF_WINDOW_MAX_OPS"] == "100" and env["OKF_WINDOW_MAX_JOBS"] == "50"
    assert env["PYTHONPATH"].split(os.pathsep)[0] == str(tmp_path)
    blob = json.dumps(env).lower()
    for secret in ("private_key", "access_token", "refresh_token", "client_secret", "credentials"):
        assert secret not in blob


# ----------------------------------------------------------------------------- child, real SDK objects, offline
CHILD = r'''
import json, sys, time
import okf_window_bridge as bridge
bridge.install()

import requests
from requests.adapters import HTTPAdapter
from google.auth.credentials import AnonymousCredentials
from google.auth.transport.requests import AuthorizedSession
from google.cloud import bigquery

MODE = sys.argv[1]
RETURNED_ID = sys.argv[2] if len(sys.argv) > 2 else None
seen = []


class Adapter(HTTPAdapter):
    def send(self, request, **kwargs):
        seen.append({"method": request.method, "url": request.url, "timeout": kwargs.get("timeout")})
        if MODE == "lost_response":
            raise requests.exceptions.ConnectionError("connection reset after the request was sent")
        body = json.loads(request.body or "{}") if request.body else {}
        ref = (body.get("jobReference") or {})
        job_id = RETURNED_ID or ref.get("jobId") or "server-assigned"
        payload = {"jobReference": {"projectId": "p", "location": "US", "jobId": job_id},
                   "status": {"state": "DONE"},
                   "configuration": {"query": {"query": "SELECT 1"}, "jobType": "QUERY"},
                   "statistics": {"query": {"totalBytesProcessed": "0"}}}
        response = requests.Response()
        response.status_code = 200
        response._content = json.dumps(payload).encode()
        response.headers["content-type"] = "application/json"
        response.request = request
        response.url = request.url
        return response


session = AuthorizedSession(AnonymousCredentials())
session.mount("https://", Adapter())
session.mount("http://", Adapter())
client = bigquery.Client(project="p", location="US", credentials=AnonymousCredentials(), _http=session)

out = {"mode": MODE, "error": None}
try:
    if MODE == "submit":
        job = client.query("SELECT 1", job_id="okf_rcpt_deadbeef_0123456789abcdef")
        out["job_id"] = job.job_id
    elif MODE == "dry_run":
        cfg = bigquery.QueryJobConfig(dry_run=True, use_query_cache=False)
        client.query("SELECT 1 FROM t WHERE FALSE", job_config=cfg)
    elif MODE == "returned_id_mutation":
        job = client.query("SELECT 1", job_id="okf_rcpt_original")
        out["job_id"] = job.job_id
    elif MODE == "verifier_read":
        client._connection.api_request(method="GET", path="/projects/p/jobs/okf_rcpt_x",
                                       query_params={"location": "US"})
    elif MODE == "tokeninfo":
        import urllib.request
        urllib.request.urlopen("data:text/plain,%7B%22email%22%3A%22sa%40x%22%7D").read()
    elif MODE == "budget":
        for i in range(3):
            try:
                client.query("SELECT 1", job_id="okf_rcpt_%d" % i)
            except bridge.WindowStopped as exc:
                out["error"] = "WindowStopped: " + str(exc)
                break
    elif MODE == "lost_response":
        try:
            client.query("SELECT 1", job_id="okf_rcpt_lost")
        except Exception as exc:
            out["error"] = type(exc).__name__
    elif MODE == "stopped" or MODE == "deadline":
        try:
            client.query("SELECT 1", job_id="okf_rcpt_blocked")
        except bridge.WindowStopped as exc:
            out["error"] = "WindowStopped: " + str(exc)
except bridge.WindowStopped as exc:
    out["error"] = "WindowStopped: " + str(exc)
out["http"] = seen
print("OKF_RESULT " + json.dumps(out))
'''


def child(tmp_path, mode, *, deadline_offset=600, stop=False, max_jobs=0, max_ops=0, returned_id=None, bridge=None):
    """Run one child with the bridge installed and a fully offline transport. Returns (result, bridge)."""
    if bridge is None:
        bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + deadline_offset,
                                  directory=tmp_path / "priv", max_jobs=max_jobs, max_ops=max_ops)
        RW.bootstrap_files(bridge.dir)
    if stop:
        bridge.stop()
    bridge.next_launch()
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    env = dict(os.environ, **bridge.child_env())
    argv = [sys.executable, str(script), mode] + ([returned_id] if returned_id else [])
    proc = subprocess.run(argv, capture_output=True, text=True, timeout=180, env=env)
    assert proc.returncode == 0, proc.stderr[-3000:]
    line = next(l for l in proc.stdout.splitlines() if l.startswith("OKF_RESULT "))
    return json.loads(line[len("OKF_RESULT "):]), bridge


@needs_sdk
def test_a_real_submission_keeps_the_sdk_deterministic_job_id(tmp_path):
    result, bridge = child(tmp_path, "submit")
    assert result["job_id"] == "okf_rcpt_deadbeef_0123456789abcdef"
    ingested = bridge.ingest()
    assert [j["job_id"] for j in ingested["jobs"]] == ["okf_rcpt_deadbeef_0123456789abcdef"]
    assert ingested["jobs"][0]["state"] == "SUBMITTED" and ingested["jobs"][0]["id_mutated"] is False
    assert ingested["unresolved"] == []
    # journaled BEFORE the send: the intended id exists even if the response never comes back
    entries = bridge.entries()
    intended = next(e for e in entries if e["event"] == "query" and e.get("state") == "INTENDED")
    posted = next(e for e in entries if e["event"] == "api_request")
    assert intended["requested_job_id"] == "okf_rcpt_deadbeef_0123456789abcdef"
    assert intended["seq"] < posted["seq"]


@needs_sdk
def test_a_dry_run_is_a_bounded_operation_not_a_job(tmp_path):
    result, bridge = child(tmp_path, "dry_run")
    ingested = bridge.ingest()
    assert ingested["jobs"] == []            # no phantom id reaches the cleanup or identity union
    assert ingested["dry_runs"] == 1
    assert ingested["operations"] >= 2       # the dry run itself plus its HTTP dispatch consume the budget
    entry = next(e for e in bridge.entries() if e["event"].startswith("query") and e.get("state") == "DRY_RUN")
    assert entry["actual_job"] is False


@needs_sdk
def test_a_lost_response_stays_unresolved(tmp_path):
    # a short deadline so the SDK's own transport retry of the failed insert is bounded by the window, not by luck
    result, bridge = child(tmp_path, "lost_response", deadline_offset=8)
    assert result["error"]                   # the SDK raised
    ingested = bridge.ingest()
    assert ingested["jobs"] == []
    assert len(ingested["unresolved"]) == 1
    assert ingested["unresolved"][0]["requested_job_id"] == "okf_rcpt_lost"
    assert ingested["unresolved"][0]["state"] == "UNRESOLVED"     # never NOT_SUBMITTED
    assert result["http"], "the request did reach the transport"


@needs_sdk
def test_a_mutated_returned_id_retains_both_references(tmp_path):
    result, bridge = child(tmp_path, "returned_id_mutation", returned_id="okf_rcpt_replaced_by_retry")
    ingested = bridge.ingest()
    job = ingested["jobs"][0]
    assert job["job_id"] == "okf_rcpt_replaced_by_retry"
    assert job["requested_job_id"] == "okf_rcpt_original"
    assert job["id_mutated"] is True


@needs_sdk
def test_the_stop_channel_closes_admission_before_any_http(tmp_path):
    result, bridge = child(tmp_path, "stopped", stop=True)
    assert result["error"].startswith("WindowStopped")
    assert result["http"] == []              # nothing was dispatched
    ingested = bridge.ingest()
    assert ingested["jobs"] == [] and ingested["unresolved"] == []
    assert ingested["refused"] == 1          # admission closed before the call: a KNOWN non-submission
    assert [b["reason"] for b in ingested["blocked"]] == ["stopped"]


@needs_sdk
def test_a_passed_deadline_closes_admission(tmp_path):
    result, bridge = child(tmp_path, "deadline", deadline_offset=-1)
    assert result["error"].startswith("WindowStopped")
    assert result["http"] == []
    ingested = bridge.ingest()
    assert ingested["unresolved"] == [] and ingested["refused"] == 1
    assert [b["reason"] for b in ingested["blocked"]] == ["deadline"]


@needs_sdk
def test_the_job_budget_stops_further_submissions(tmp_path):
    result, bridge = child(tmp_path, "budget", max_jobs=2)
    ingested = bridge.ingest()
    assert len(ingested["jobs"]) == 2
    assert [b["reason"] for b in ingested["blocked"]] == ["job_budget"]
    assert result["error"].startswith("WindowStopped")


@needs_sdk
def test_the_verifier_direct_read_is_bounded_and_journaled(tmp_path):
    result, bridge = child(tmp_path, "verifier_read")
    entries = bridge.entries()
    read = next(e for e in entries if e["event"] == "api_request" and "/jobs/okf_rcpt_x" in str(e.get("path")))
    assert read["actual_job"] is False
    assert bridge.ingest()["jobs"] == []          # a read is not a submission
    assert result["http"][0]["timeout"] is not None and result["http"][0]["timeout"] > 0


@needs_sdk
def test_the_tokeninfo_read_is_bounded_before_any_client_exists(tmp_path):
    result, bridge = child(tmp_path, "tokeninfo")
    opened = [e for e in bridge.entries() if e["event"] == "urlopen"]
    assert len(opened) == 1 and opened[0]["actual_job"] is False


@needs_sdk
def test_every_http_send_carries_the_remaining_budget(tmp_path):
    result, _ = child(tmp_path, "submit", deadline_offset=30)
    assert result["http"], "no dispatch observed"
    for call in result["http"]:
        assert call["timeout"] is not None and 0 < call["timeout"] <= 30


# ----------------------------------------------------------------------------- in-process wrapper unit tests
def load_bridge(tmp_path, monkeypatch, **env):
    """Load a generated bridge with a chosen environment, WITHOUT installing its global hooks."""
    files = RW.bootstrap_files(tmp_path / "priv")
    for key, value in {"OKF_WINDOW_LABEL": "w", "OKF_WINDOW_DEADLINE_EPOCH": repr(time.time() + 600),
                       "OKF_WINDOW_STOP_FILE": str(tmp_path / "STOP"),
                       "OKF_WINDOW_JOURNAL": str(tmp_path / "journal.jsonl"), **env}.items():
        monkeypatch.setenv(key, str(value))
    spec = importlib.util.spec_from_file_location(f"bridge_{tmp_path.name}_{len(env)}", files["bridge"])
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_job_retry_is_disabled_so_no_new_id_is_submitted_inside_result(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    seen = {}

    class Client:
        def query(self, sql, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(job_id=kwargs.get("job_id"), project="p", location="US")

    module = SimpleNamespace(Client=Client)
    bridge._patch_bigquery(module)
    module.Client().query("SELECT 1", job_id="okf_rcpt_x")
    assert seen["job_retry"] is None
    assert seen["job_id"] == "okf_rcpt_x"     # the caller's deterministic id is never replaced


def test_an_explicit_caller_job_retry_is_preserved(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    seen = {}

    class Client:
        def query(self, sql, **kwargs):
            seen.update(kwargs)
            return SimpleNamespace(job_id="j", project="p", location="US")

    module = SimpleNamespace(Client=Client)
    bridge._patch_bigquery(module)
    sentinel = object()
    module.Client().query("SELECT 1", job_retry=sentinel)
    assert seen["job_retry"] is sentinel


def test_the_scope_shim_adds_the_email_scope_and_changes_nothing_else(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    captured = []
    module = SimpleNamespace(default=lambda scopes=None, *a, **kw: captured.append(scopes) or ("creds", "proj"))
    bridge._patch_auth(module)
    module.default(["https://www.googleapis.com/auth/cloud-platform"])
    assert captured[-1] == ["https://www.googleapis.com/auth/cloud-platform", bridge.USERINFO_EMAIL]
    module.default(None)
    assert captured[-1] is None               # nothing is invented when no scopes were requested


def test_the_scope_shim_can_be_switched_off(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch, OKF_WINDOW_EMAIL_SCOPE="0")
    captured = []
    module = SimpleNamespace(default=lambda scopes=None, *a, **kw: captured.append(scopes) or ("c", "p"))
    bridge._patch_auth(module)
    module.default(["scope"])
    assert captured[-1] == ["scope"]
    assert bridge.installed == ["google.auth(no-scope-shim)"]


def test_the_send_guard_bounds_every_dispatch_including_a_refresh_retry(tmp_path, monkeypatch):
    """AuthorizedSession.request() can send twice: the original and a 401 retry after a credential refresh."""
    bridge = load_bridge(tmp_path, monkeypatch, OKF_WINDOW_DEADLINE_EPOCH=repr(time.time() + 5))
    sends = []

    class AuthorizedSession:
        def send(self, request, **kwargs):
            sends.append(kwargs.get("timeout"))
            return "response"

        def request(self, method, url, **kwargs):
            self.send("first", timeout=None)      # the original dispatch
            self.send("retry", timeout=3600)      # the internal 401 retry after a refresh
            return "done"

    module = SimpleNamespace(AuthorizedSession=AuthorizedSession)
    bridge._patch_session(module)
    AuthorizedSession().request("GET", "https://example.test")
    assert len(sends) == 2
    assert all(t is not None and 0 < t <= 5 for t in sends)


def test_the_send_guard_refuses_after_stop(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    (tmp_path / "STOP").write_text("{}")
    sent = []

    class AuthorizedSession:
        def send(self, request, **kwargs):
            sent.append(request)

    module = SimpleNamespace(AuthorizedSession=AuthorizedSession)
    bridge._patch_session(module)
    with pytest.raises(bridge.WindowStopped):
        AuthorizedSession().send("request")
    assert sent == []


def test_a_dispatch_after_the_deadline_is_refused_even_mid_run(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch, OKF_WINDOW_DEADLINE_EPOCH=repr(time.time() - 1))
    with pytest.raises(bridge.WindowStopped):
        bridge.check("http")


def test_the_deadline_is_absolute_and_is_not_rebased(tmp_path, monkeypatch):
    """A child that started late gets the time that is actually left, not a fresh full budget."""
    bridge = load_bridge(tmp_path, monkeypatch, OKF_WINDOW_DEADLINE_EPOCH=repr(time.time() + 2))
    assert 0 < bridge.remaining() <= 2
    assert bridge.budget_timeout(900) <= 2


# ----------------------------------------------------------------------------- the runner
@needs_sdk
def test_the_runner_closes_admission_before_terminating_an_overrunning_child(tmp_path):
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 1.0, directory=tmp_path / "priv")
    RW.bootstrap_files(bridge.dir)
    script = tmp_path / "slow.py"
    script.write_text("import time\ntime.sleep(30)\n")
    run = bridge.runner(terminate_grace=5)
    started = time.monotonic()
    result = run([sys.executable, str(script)])
    assert time.monotonic() - started < 20
    assert result.returncode != 0
    assert bridge.stop_path.exists(), "admission must close before the process is terminated"
    assert "does not cancel its server jobs" in result.stderr


@needs_sdk
def test_the_runner_returns_a_completed_process_for_a_normal_child(tmp_path):
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 120, directory=tmp_path / "priv")
    RW.bootstrap_files(bridge.dir)
    script = tmp_path / "quick.py"
    script.write_text("print('hello')\n")
    result = bridge.runner()([sys.executable, str(script)])
    assert result.returncode == 0 and "hello" in result.stdout
    assert not bridge.stop_path.exists()


@needs_sdk
def test_two_overlapping_bridges_keep_separate_private_journals(tmp_path):
    a = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 600, directory=tmp_path / "a")
    b = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 600, directory=tmp_path / "b")
    for bridge in (a, b):
        RW.bootstrap_files(bridge.dir)
    assert a.journal_path != b.journal_path and a.stop_path != b.stop_path
    a.stop()
    assert not b.stop_path.exists()          # one invocation's stop never closes another's admission


# =============================================================================== Astra PR47 review fixes
@needs_sdk
def test_the_credential_refresh_transport_is_guarded(tmp_path):
    """Astra PR47 #4: `creds.refresh(Request())` sends through a PLAIN `requests.Session`, never AuthorizedSession."""
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 2, directory=tmp_path / "priv")
    RW.bootstrap_files(bridge.dir)
    bridge.next_launch()
    bridge.stop()
    script = tmp_path / "refresh.py"
    script.write_text(r'''
import json, sys
import okf_window_bridge as bridge
bridge.install()
import requests
from requests.adapters import HTTPAdapter
import google.auth, google.auth.transport.requests
sys.path.insert(0, sys.argv[1] + "/examples/okf_attested_computation")
import broker
seen = []


class Adapter(HTTPAdapter):
    def send(self, request, **kwargs):
        seen.append({"url": request.url, "timeout": kwargs.get("timeout")})
        response = requests.Response()
        response.status_code = 200
        response._content = b'{"email": "sa@example.test"}'
        response.headers["content-type"] = "application/json"
        response.request = request
        return response


class Credentials:
    token = "synthetic-not-a-secret"

    def refresh(self, request):
        request.session.mount("https://", Adapter())
        request(url="https://oauth2.example.test/refresh", method="POST", body="{}")


google.auth.default = lambda *a, **kw: (Credentials(), "p")
error = None
try:
    broker.open_live_session("p", "US")
except Exception as exc:
    error = type(exc).__name__
print("OKF_RESULT " + json.dumps({"seen": seen, "error": error, "stopped": bridge.stopped()}))
''')
    proc = subprocess.run([sys.executable, str(script), SDK_ROOT], env=dict(os.environ, **bridge.child_env()),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode == 0, proc.stderr[-2000:]
    result = json.loads(next(l for l in proc.stdout.splitlines() if l.startswith("OKF_RESULT "))[len("OKF_RESULT "):])
    assert result["stopped"] is True
    assert result["seen"] == [], "the credential refresh dispatched after the window stopped"
    assert result["error"] == "WindowStopped"


def test_the_base_requests_session_send_is_the_guarded_seam(tmp_path, monkeypatch):
    """AuthorizedSession does not define `send`; guarding only the subclass leaves a plain Session unbounded."""
    bridge = load_bridge(tmp_path, monkeypatch)
    sends = []

    class Session:
        def send(self, request, **kwargs):
            sends.append(kwargs.get("timeout"))
            return "response"

    class AuthorizedSession(Session):
        pass

    requests_module = SimpleNamespace(Session=Session)
    bridge._patch_requests(requests_module)
    bridge._patch_session(SimpleNamespace(AuthorizedSession=AuthorizedSession))
    assert "requests.Session.send" in bridge.installed
    Session().send("plain")
    AuthorizedSession().send("authorized")
    assert len(sends) == 2 and all(t is not None for t in sends)
    # the subclass is not double-wrapped: it inherits the one guard
    assert AuthorizedSession.__dict__.get("send") is None


def test_a_guard_is_never_installed_twice(tmp_path, monkeypatch):
    bridge = load_bridge(tmp_path, monkeypatch)
    calls = []

    class Session:
        def send(self, request, **kwargs):
            calls.append(1)
            return "r"

    module = SimpleNamespace(Session=Session)
    bridge._patch_requests(module)
    bridge._patch_requests(module)
    Session().send("x")
    assert calls == [1]                       # one dispatch, and the checks did not stack
    assert bridge.counts["operations"] == 1


@needs_sdk
def test_each_child_launch_keeps_its_own_journal(tmp_path):
    """Astra PR47 #5: the child's sequence counter restarts, so a shared journal loses every launch but the last."""
    result_a, bridge = child(tmp_path, "submit", returned_id=None)
    result_b, _ = child(tmp_path, "submit", bridge=bridge)
    ingested = bridge.ingest()
    assert ingested["launches"] == 2 and len(ingested["journals"]) == 2
    assert len(ingested["jobs"]) == 2, ingested["jobs"]
    assert len({j["invocation"] for j in ingested["jobs"]}) == 2
    assert ingested["unresolved"] == [] and ingested["complete"] is True


@needs_sdk
def test_an_unwritable_journal_refuses_to_dispatch(tmp_path):
    """Astra PR47 #6: durable intent BEFORE dispatch, or nothing is dispatched."""
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    RW.bootstrap_files(bridge.dir)
    bridge.next_launch()
    bridge.journal_path.parent.mkdir(parents=True, exist_ok=True)
    bridge.journal_path.mkdir()                       # the journal path is a directory: unwritable
    script = tmp_path / "child.py"
    script.write_text(CHILD)
    proc = subprocess.run([sys.executable, str(script), "submit"], env=dict(os.environ, **bridge.child_env()),
                          capture_output=True, text=True, timeout=120)
    assert proc.returncode != 0
    assert "JournalUnavailable" in proc.stderr
    ingested = bridge.ingest()
    assert ingested["jobs"] == []
    assert ingested["complete"] is False
    assert any(u["state"] == "JOURNAL_DAMAGED" for u in ingested["unresolved"])
    assert any(u["state"] == "LAUNCH_UNJOURNALED" for u in ingested["unresolved"])


def test_an_unparsable_record_is_an_unresolved_obligation(tmp_path):
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    bridge.next_launch()
    bridge.journal_path.parent.mkdir(parents=True, exist_ok=True)
    bridge.journal_path.write_text('{"event": "query", "seq": 1, "state": "SUBMITTED", "actual_job": true, '
                                   '"job_id": "j1", "invocation": "i1"}\n{truncated write')
    ingested = bridge.ingest()
    assert [j["job_id"] for j in ingested["jobs"]] == ["j1"]
    assert any(u["state"] == "JOURNAL_DAMAGED" for u in ingested["unresolved"])
    assert ingested["complete"] is False


def test_a_launch_that_journaled_nothing_stays_unresolved(tmp_path):
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    bridge.next_launch()
    ingested = bridge.ingest()
    assert ingested["complete"] is False
    assert [u["state"] for u in ingested["unresolved"]] == ["JOURNAL_DAMAGED", "LAUNCH_UNJOURNALED"]


@needs_sdk
def test_join_closes_admission_then_terminates_a_child_that_will_not_exit(tmp_path):
    """Astra PR47 #1: the parent must be able to stop and join the child BEFORE it seals its cleanup union."""
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    RW.bootstrap_files(bridge.dir)
    script = tmp_path / "sleeper.py"
    script.write_text("import time\ntime.sleep(120)\n")
    done = {}
    runner = bridge.runner()
    thread = threading.Thread(target=lambda: done.update(result=runner([sys.executable, str(script)])), daemon=True)
    thread.start()
    for _ in range(400):
        if bridge._process is not None:
            break
        time.sleep(0.01)
    outcome = bridge.join(timeout=1)
    assert bridge.stop_path.exists(), "admission must close before the process is terminated"
    assert outcome["joined"] is True and outcome["terminated"] is True
    assert "does not cancel its server jobs" in outcome["note"]
    thread.join(30)
    assert not thread.is_alive()


def test_join_is_a_noop_when_no_child_is_running(tmp_path):
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    assert bridge.join() == {"joined": True, "running": False}


@needs_sdk
def test_jobs_exposes_the_qualified_references_the_controller_adopts(tmp_path):
    result, bridge = child(tmp_path, "submit")
    refs = bridge.jobs()
    assert [r["job_id"] for r in refs] == ["okf_rcpt_deadbeef_0123456789abcdef"]
    assert refs[0]["project"] == "p" and refs[0]["location"] == "US"


# =============================================================================== Astra PR47 re-review (RR2)
@needs_sdk
def test_the_handshake_allocates_no_workload_launch(tmp_path):
    """RR2 R7: the probe used to consume launch001 and suppress its journal, so ingestion reported that launch
    permanently damaged and every later run was forced CHAIN_INCOMPLETE."""
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    record = bridge.handshake()
    assert bridge.launches == [], bridge.launches
    assert bridge.journal_files() == []
    assert "OKF_WINDOW_JOURNAL" not in bridge.probe_env()
    assert bridge.probe_env()["OKF_WINDOW_INVOCATION"].endswith("-handshake")
    if record["status"] != RW.SUPPORTED:
        pytest.skip("this interpreter cannot bootstrap the child; the launch-accounting claim is unaffected")
    result, _ = child(tmp_path, "submit", bridge=bridge)
    ingested = bridge.ingest()
    assert ingested["launches"] == 1 and len(ingested["jobs"]) == 1
    assert ingested["unresolved"] == [] and ingested["complete"] is True


@needs_sdk
def test_a_pending_submission_is_handed_to_the_controller_as_a_reference(tmp_path):
    """RR2 R1: `jobs()` returned only confirmed submissions, so a lost response never reached the window."""
    result, bridge = child(tmp_path, "lost_response", deadline_offset=8)
    ingested = bridge.ingest()
    assert ingested["jobs"] == [] and len(ingested["unresolved"]) == 1
    refs = bridge.jobs()
    assert [r["job_id"] for r in refs] == ["okf_rcpt_lost"]
    assert refs[0]["confirmed_submitted"] is False and refs[0]["state"] == "UNRESOLVED"
    assert refs[0]["project"] == bridge.project and refs[0]["location"] == bridge.location
    assert bridge.obligations() == []          # it has an id, so it travels as a reference rather than an obligation


def test_evidence_without_a_job_id_becomes_an_obligation(tmp_path):
    """A damaged or silent launch journal hides submissions with no id to adopt."""
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    launch = bridge.next_launch()
    bridge.journal_path.parent.mkdir(parents=True, exist_ok=True)
    bridge.journal_path.write_text(json.dumps({"event": "query", "seq": 1, "state": "SUBMITTED", "actual_job": True,
                                               "job_id": "j1", "invocation": launch["invocation"]}) + "\n{truncated")
    assert [r["job_id"] for r in bridge.jobs()] == ["j1"]
    obligations = bridge.obligations()
    assert [o["state"] for o in obligations] == ["JOURNAL_DAMAGED"]
    assert obligations[0]["ok"] is False


def test_a_confirmed_submission_travels_as_a_confirmed_reference(tmp_path):
    bridge = RW.ReceiptBridge(SDK_ROOT, label="w", deadline_epoch=time.time() + 300, directory=tmp_path / "priv")
    launch = bridge.next_launch()
    bridge.journal_path.parent.mkdir(parents=True, exist_ok=True)
    bridge.journal_path.write_text(json.dumps({"event": "query", "seq": 1, "state": "SUBMITTED", "actual_job": True,
                                               "job_id": "j1", "project": "p", "location": "EU",
                                               "invocation": launch["invocation"]}) + "\n")
    ref = bridge.jobs()[0]
    assert ref["project"] == "p" and ref["location"] == "EU" and ref["state"] == "SUBMITTED"
    assert "confirmed_submitted" not in ref or ref["confirmed_submitted"] is not False
    assert bridge.obligations() == []


# ----------------------------------------------------------------------------- the 2026-09-08 live containment miss
def _bridge(directory, tmp_path, label="rc"):
    return RW.ReceiptBridge(SDK_ROOT, label=label, deadline_epoch=time.time() + 600, directory=directory)


CHILD_REPORT = ("import sys, json, os\n"
                "m = sys.modules.get('okf_window_bridge')\n"
                "print(json.dumps({'imported': m is not None}))\n")


def test_a_relative_bridge_directory_still_reaches_a_child_with_a_different_cwd(tmp_path, monkeypatch):
    """THE ROOT CAUSE of the 2026-09-08 live run: `run_receipt` launches the SDK example with cwd=<sdk_root>, and the
    bridge directory is exported as the child's PYTHONPATH. A relative directory resolved against the SDK checkout
    instead, so `usercustomize` was never importable: no guard installed, no journal was written, and the receipt
    child submitted a real BigQuery job that the window never inventoried - while the handshake said SUPPORTED."""
    monkeypatch.chdir(tmp_path)
    b = _bridge(Path("evidence/chain/receipt-bridge/rel"), tmp_path)   # relative, exactly as chain.py builds it
    assert b.dir.is_absolute(), "the bridge must not depend on the launcher's cwd"
    assert b.handshake()["status"] == RW.SUPPORTED
    cp = b.runner()([sys.executable, "-c", CHILD_REPORT], cwd=SDK_ROOT)
    assert json.loads((cp.stdout or "").strip().splitlines()[-1])["imported"] is True
    assert [p.name for p in b.journal_files()] == ["launch_001.jsonl"]
    assert b.containment()["contained"] is True


def test_the_handshake_probes_the_cwd_the_real_child_will_use(tmp_path, monkeypatch):
    """A handshake run in the PARENT's cwd proved nothing about a child launched in the SDK root: it reported
    SUPPORTED for the very run whose child never imported the bootstrap."""
    monkeypatch.chdir(tmp_path)
    seen = {}
    real = RW.subprocess.run

    def spy(argv, **kw):
        seen["cwd"] = kw.get("cwd")
        return real(argv, **kw)
    monkeypatch.setattr(RW.subprocess, "run", spy)
    _bridge(tmp_path / "bridge", tmp_path).handshake()
    assert seen["cwd"] == SDK_ROOT, "the probe must run where the receipt child runs"


def test_containment_reports_a_launch_that_never_journaled_bridge_installed(tmp_path):
    """A child that exits without `bridge_installed` had no deadline, no admission bound and no journal."""
    b = _bridge(tmp_path / "bridge", tmp_path)
    b.next_launch()
    c = b.containment()
    assert c["contained"] is False and len(c["uncontained"]) == 1
    assert "neither bounded" in c["reason"]
    # a launch nobody allocated is not an accusation: with no launches there is nothing to contain
    assert _bridge(tmp_path / "bridge2", tmp_path).containment()["contained"] is True


def test_containment_since_scopes_the_claim_to_this_invocation(tmp_path):
    """Each `run_receipt` allocates one launch; an earlier launch's failure must not be blamed on a later case."""
    b = _bridge(tmp_path / "bridge", tmp_path)
    assert b.handshake()["status"] == RW.SUPPORTED    # writes the bootstrap the child imports
    b.next_launch()                                   # launch 1: never journals
    before = len(b.launches)
    b.runner()([sys.executable, "-c", "pass"], cwd=SDK_ROOT)   # launch 2: real, journals
    assert b.containment(since=before)["contained"] is True
    assert b.containment()["contained"] is False      # the whole bridge still carries launch 1
