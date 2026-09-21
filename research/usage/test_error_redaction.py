#!/usr/bin/env python3
"""Regression: a credential-bearing curl argv must never reach error fields, snapshot.json or index.html.

    python3 test_error_redaction.py

`subprocess.TimeoutExpired` stringifies its full argv, and the Codex / Kimi curl calls carry
`Authorization: Bearer <token>` there. Uses fake tokens, a temp HOME and a temp output dir;
never touches real credentials, the network, or the real snapshot.json.
"""
import json
import os
import subprocess
import sys
import tempfile
import urllib.error
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

TMP = Path(tempfile.mkdtemp())
CODEX_TOKEN = "FAKE-codex-bearer-0123456789abcdef"
KIMI_TOKEN = "FAKE-kimi-bearer-fedcba9876543210"
JWT = "eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiJmYWtlIn0.c2lnbmF0dXJlLWZha2U"
TOKENS = (CODEX_TOKEN, KIMI_TOKEN, JWT)

# --- fake credentials (temp HOME; Kimi resolves Path.home() at call time) ---
os.environ["HOME"] = str(TMP)
cab.CODEX_AUTH = TMP / "codex-auth.json"
cab.CODEX_AUTH.write_text(json.dumps({"tokens": {"access_token": CODEX_TOKEN}}))
kimi_cred = TMP / ".kimi-code" / "credentials" / "kimi-code.json"
kimi_cred.parent.mkdir(parents=True)
kimi_cred.write_text(json.dumps({"access_token": KIMI_TOKEN}))

curl_calls = []
real_run = subprocess.run


def timeout_run(cmd, *a, **kw):
    if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "curl":
        curl_calls.append(cmd)
        raise subprocess.TimeoutExpired(cmd, kw.get("timeout", 1))
    return real_run(cmd, *a, **kw)


def offline_urlopen(req, *a, **kw):
    # worst case: the fallback transport also echoes its request headers
    raise urllib.error.URLError(f"offline; headers={dict(req.header_items())}")


cab.subprocess.run = timeout_run
cab.urllib.request.urlopen = offline_urlopen


def assert_clean(label, blob):
    text = blob if isinstance(blob, str) else json.dumps(blob)
    for tok in TOKENS:
        assert tok not in text, f"{label}: leaked {tok[:12]}…"
    assert "Bearer FAKE" not in text and "Bearer eyJ" not in text, f"{label}: bearer value survived"


# 0. the hazard is real: the raw exception string carries the token
raw = str(subprocess.TimeoutExpired(["curl", "-H", f"Authorization: Bearer {CODEX_TOKEN}"], 45))
assert CODEX_TOKEN in raw

# 1. helpers
assert cab.safe_error(subprocess.TimeoutExpired(["curl", "-H", f"Authorization: Bearer {CODEX_TOKEN}"], 45)) == "curl timeout after 45s"
assert cab.safe_error(subprocess.CalledProcessError(7, ["curl", "-H", f"Authorization: Bearer {CODEX_TOKEN}"])) == "curl failed (exit 7)"
for dirty in (
    f"Authorization: Bearer {CODEX_TOKEN}",
    f"['curl', '-H', 'authorization: bearer {CODEX_TOKEN}', 'https://x']",
    f"token rejected: {JWT}",
    f"{{'Authorization': 'Bearer {KIMI_TOKEN}'}}",
    f"failed for literal {KIMI_TOKEN} with no marker",
):
    cleaned = cab.scrub_secrets(dirty, secrets=(KIMI_TOKEN,))
    assert_clean("scrub_secrets", cleaned)
    assert "[REDACTED]" in cleaned, cleaned
    assert cab.scrub_secrets(cleaned) == cleaned, cleaned  # idempotent: main() re-scrubs collector output
assert cab.scrub_secrets("curl: (28) Operation timed out") == "curl: (28) Operation timed out"  # benign text untouched
assert cab.scrub_tree({"a": [f"Bearer {CODEX_TOKEN}", 3, None]}) == {"a": ["Bearer [REDACTED]", 3, None]}

# 2. Codex failure path
codex = cab.collect_codex()
assert len(curl_calls) == 1 and any(CODEX_TOKEN in part for part in curl_calls[0])  # token really was in argv
assert codex["ok"] is False and "timeout" in codex["error"], codex
assert "curl" in codex["error"] and "urllib" in codex["error"], codex  # still diagnosable
assert_clean("codex", codex)

# 3. Kimi failure path
kimi = cab.collect_kimi()
assert len(curl_calls) == 2 and any(KIMI_TOKEN in part for part in curl_calls[1])
assert "timeout" in kimi["api_error"], kimi
assert_clean("kimi", kimi)

# 4. end to end: main() → snapshot.json + index.html, other collectors stubbed out
cab.HERE = TMP / "out"
cab.collect_claude = lambda: {"ok": False, "error": f"boom Authorization: Bearer {JWT}"}  # any future path
for name in ("collect_agy", "collect_muse", "collect_dsh", "collect_routine_proxy"):
    setattr(cab, name, lambda: {})
cab.collect_grok = lambda: {"ok": False, "bots": [], "stale": True, "stale_reason": "test"}
cab.main()
snap_text = (cab.HERE / "snapshot.json").read_text()
snap = json.loads(snap_text)
assert snap["codex"]["error"] and snap["kimi"]["api_error"], "failure paths must still be reported"
assert_clean("snapshot.json", snap_text)
assert_clean("index.html", (cab.HERE / "index.html").read_text())
assert len(curl_calls) == 4

print("ALL CHECKS PASSED")
