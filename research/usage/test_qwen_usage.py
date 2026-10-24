#!/usr/bin/env python3
"""Checks for the Qwen Code card (usage_record.jsonl parser, cost math, trial count, no-runs case)
and the Kimi config.toml parser.

    python3 test_qwen_usage.py

Synthetic records, a temp HOME, a fake qwen binary and a fake curl; never reads the real ~/.qwen,
~/.dsh or ~/.kimi-code, never touches the network or the real snapshot.json / index.html.
"""
import json
import os
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

PT = cab.PT
MODEL = "qwen/qwen3.8-max-0902"
PROJECT = "/Users/someone/private-client-project"
SID = "0b7f3c1e-5d2a-4c39-9e61-7a8b9c0d1e2f"
OR_KEY = "sk-or-v1-FAKEFAKEFAKE0123456789abcdef0123456789"
KIMI_TOKEN = "FAKE-kimi-bearer-fedcba9876543210"
TMP = Path(tempfile.mkdtemp())
os.environ["HOME"] = str(TMP)  # collect_qwen / read_kimi_config / collect_kimi resolve ~ per call
BEFORE = datetime(2026, 10, 24, 12, 0, tzinfo=PT)  # trial not started
AFTER = datetime(2026, 10, 26, 12, 0, tzinfo=PT)


def usage(requests, inp, out, cached, thoughts=0):
    return {"requests": requests, "inputTokens": inp, "outputTokens": out, "cachedTokens": cached,
            "thoughtsTokens": thoughts, "totalTokens": inp + out}


SMOKE = usage(2, 24755, 179, 4352, thoughts=107)  # the real 2026-10-24 setup test, shape and counts
SMOKE_USD = ((24755 - 4352) * 2.00 + 4352 * 0.25 + 179 * 6.00) / 1e6  # 0.042968


def rec(when, sid=SID, models=None, **extra):
    ms = int(when.timestamp() * 1000)
    o = {"version": 1, "sessionId": sid, "timestamp": ms, "startTime": ms - 10820, "project": PROJECT,
         "durationMs": 10820, "models": {MODEL: SMOKE} if models is None else models,
         "tools": {"totalCalls": 0, "totalSuccess": 0, "totalFail": 0, "byName": {}}}
    o.update(extra)
    return json.dumps(o)


def assert_private(label, blob):
    text = blob if isinstance(blob, str) else json.dumps(blob)
    for s in (PROJECT, SID, OR_KEY, KIMI_TOKEN, "sk-or", "Bearer"):
        assert s not in text, f"{label}: leaked {s[:14]}"


# 1. no runs: missing / empty / blank file
for text in ("", "\n\n  \n"):
    u = cab.summarize_qwen_usage(text, BEFORE)
    assert u["sessions"] == 0 and u["bad_lines"] == 0 and u["last_session_pt"] is None, u
    assert u["windows"]["all_time"] == {"sessions": 0, "requests": 0, "input_tokens": 0, "cached_tokens": 0,
                                        "output_tokens": 0, "unpriced_tokens": 0, "est_cost_usd": 0.0}, u
    assert u["trial"]["status"] == "trial starts 10/25 ~3 AM PT; 0/3 runs", u["trial"]
    assert u["trial"]["runs_display"] == "0/3" and u["trial"]["setup_test_sessions"] == 0

# 2. the real setup-test record: counts, list-price cost, last session in PT, setup test (not a trial run)
u = cab.summarize_qwen_usage(rec(datetime(2026, 10, 24, 10, 30, 52, tzinfo=PT)) + "\n", BEFORE)
w = u["windows"]["all_time"]
assert (w["sessions"], w["requests"], w["input_tokens"], w["cached_tokens"], w["output_tokens"]) == (1, 2, 24755, 4352, 179)
assert abs(SMOKE_USD - 0.042968) < 1e-12 and w["est_cost_usd"] == round(SMOKE_USD, 6) == 0.042968, w
assert u["windows"]["last_24h"] == w == u["windows"]["last_7d"]
assert u["last_session_pt"] == "2026-10-24 10:30 PDT", u["last_session_pt"]
assert u["trial"]["runs"] == 0 and u["trial"]["setup_test_sessions"] == 1
assert u["trial"]["status"] == "trial starts 10/25 ~3 AM PT; 0/3 runs"
assert u["models"] == [dict(w, model=MODEL, priced=True)], u["models"]
assert_private("summary", u)

# 3. bad lines are counted and skipped; good lines still count
good = rec(datetime(2026, 10, 24, 9, 0, tzinfo=PT), sid="good")
bad_lines = [
    "not json",
    "[1, 2, 3]",
    '{"version": 1, "sessionId": "x", ',  # truncated write
    json.dumps({"version": 1, "timestamp": 1792863052401, "models": {}}),  # no sessionId
    rec(BEFORE, sid="v2", version=2),  # unknown record version
    rec(BEFORE, sid="ts-bool", timestamp=True),
    rec(BEFORE, sid="ts-str", timestamp="1792863052401"),
    rec(BEFORE, sid="ts-huge", timestamp=10 ** 20),
    rec(BEFORE, sid="neg", models={MODEL: usage(1, -5, 1, 0)}),
    rec(BEFORE, sid="str-count", models={MODEL: dict(SMOKE, inputTokens="24755")}),
    rec(BEFORE, sid="float-count", models={MODEL: dict(SMOKE, outputTokens=1.5)}),
    rec(BEFORE, sid="models-list", models=[SMOKE]),
    rec(BEFORE, sid="model-not-dict", models={MODEL: 7}),
]
u = cab.summarize_qwen_usage("\n".join(bad_lines[:6] + [good] + bad_lines[6:] + [""]), BEFORE)
assert u["bad_lines"] == len(bad_lines) == 13 and u["sessions"] == 1, u
assert u["windows"]["all_time"]["input_tokens"] == 24755

# 4. one record per session: the last record wins (qwen's own dedupBySessionId)
u = cab.summarize_qwen_usage("\n".join([rec(BEFORE - timedelta(hours=2), models={MODEL: usage(1, 10, 1, 0)}),
                                        rec(BEFORE - timedelta(hours=1))]), BEFORE)
assert u["sessions"] == 1 and u["duplicate_records"] == 1 and u["windows"]["all_time"]["requests"] == 2, u

# 5. cost math: cached floor, missing counters, unknown models → tokens only, mixed → priced part only
u = cab.summarize_qwen_usage(rec(BEFORE, models={MODEL: usage(1, 100, 0, 300)}), BEFORE)
assert u["windows"]["all_time"]["est_cost_usd"] == round(300 * 0.25 / 1e6, 6)  # uncached floors at 0
u = cab.summarize_qwen_usage(rec(BEFORE, models={MODEL: {"requests": 1, "inputTokens": 1000}}), BEFORE)
assert u["windows"]["all_time"]["est_cost_usd"] == 0.002 and u["windows"]["all_time"]["output_tokens"] == 0
other = {"other/model-x": usage(1, 1000, 10, 0)}
u = cab.summarize_qwen_usage(rec(BEFORE, models=other), BEFORE)
w = u["windows"]["all_time"]
assert w["est_cost_usd"] is None and w["unpriced_tokens"] == 1010 and w["input_tokens"] == 1000, w
assert u["models"][0]["model"] == "other/model-x" and u["models"][0]["priced"] is False
assert cab._qwen_cost_cell(w) == "tokens only"
u = cab.summarize_qwen_usage(rec(BEFORE, models=dict(other, **{MODEL: SMOKE})), BEFORE)
w = u["windows"]["all_time"]
assert w["est_cost_usd"] == 0.042968 and w["unpriced_tokens"] == 1010 and w["input_tokens"] == 25755, w
assert cab._qwen_cost_cell(w) == "$0.0430 + unpriced"
assert [m["model"] for m in u["models"]] == ["other/model-x", MODEL]
u = cab.summarize_qwen_usage(rec(BEFORE, models={OR_KEY: usage(1, 5, 5, 0), "bad id; rm": usage(1, 5, 5, 0)}), BEFORE)
assert [m["model"] for m in u["models"]] == ["unrecognized model id"] * 2 and u["sessions"] == 1
assert_private("odd model ids", u)

# 6. windows: 24h / 7d / all time
u = cab.summarize_qwen_usage("\n".join(rec(AFTER - d, sid=str(i)) for i, d in enumerate(
    (timedelta(hours=1), timedelta(days=2), timedelta(days=30)))), AFTER)
assert [u["windows"][k]["sessions"] for k in ("last_24h", "last_7d", "all_time")] == [1, 2, 3], u["windows"]
assert u["windows"]["last_7d"]["input_tokens"] == 2 * 24755

# 7. trial: sessions from 2026-10-25 00:00 PT count, capped display N/3; earlier ones are setup tests
start = datetime(2026, 10, 25, tzinfo=PT)
lines = [rec(start - timedelta(milliseconds=1), sid="setup"), rec(start, sid="run1"),
         rec(start + timedelta(hours=27), sid="run2")]
u = cab.summarize_qwen_usage("\n".join(lines), AFTER)
assert (u["trial"]["runs"], u["trial"]["runs_display"], u["trial"]["setup_test_sessions"]) == (2, "2/3", 1), u["trial"]
assert u["trial"]["status"] == "2/3 runs since 10/25", u["trial"]
lines += [rec(start + timedelta(hours=h), sid=f"extra{h}") for h in (50, 51, 52)]
u = cab.summarize_qwen_usage("\n".join(lines), AFTER)
assert (u["trial"]["runs"], u["trial"]["runs_display"]) == (5, "3/3") and u["trial"]["status"] == "3/3 runs since 10/25; 5 sessions"
u = cab.summarize_qwen_usage(rec(start - timedelta(hours=1)), start)  # midnight PT: started, 0 runs
assert u["trial"]["status"] == "0/3 runs since 10/25"

# 8. collect_qwen end to end: fake binary, temp HOME, fake key — the key never leaves openrouter_key_present
bindir = TMP / "bin"
bindir.mkdir()
fake = bindir / "qwen"
fake.write_text("#!/bin/sh\necho 0.26.1\n")
fake.chmod(0o755)
(TMP / ".qwen").mkdir()
(TMP / ".qwen" / "settings.json").write_text(json.dumps({
    "modelProviders": {"openai": [{"id": MODEL, "envKey": "OPENROUTER_API_KEY", "baseUrl": "https://openrouter.ai/api/v1"}]},
    "model": {"name": MODEL}, "$version": 4}))
(TMP / ".dsh").mkdir()
(TMP / ".dsh" / ".env").write_text(f"# dsh\nOPENROUTER_API_KEY={OR_KEY}\n")
cab.QWEN_BIN = fake
cab.now_pt = lambda: BEFORE

q = cab.collect_qwen()  # no usage_record.jsonl yet
assert q["ok"] is True and q["cli_version"] == "0.26.1" and q["model"] == MODEL and q["provider"] == "OpenRouter", q
assert q["auth_ok"] is True and "error" not in q and q["usage"]["sessions"] == 0, q
assert q["trial"]["status"] == "trial starts 10/25 ~3 AM PT; 0/3 runs" and q["note"] == cab.QWEN_NOTE
html = cab.render_qwen_body(q)
assert "no runs yet" in html and "<table" not in html and "trial starts 10/25 ~3 AM PT; 0/3 runs" in html
assert_private("collect_qwen (no runs)", q)

(TMP / ".qwen" / "usage_record.jsonl").write_text(rec(datetime(2026, 10, 24, 10, 30, 52, tzinfo=PT)) + "\nnot json\n")
q = cab.collect_qwen()
assert q["usage"]["sessions"] == 1 and q["usage"]["bad_lines"] == 1 and q["trial"]["setup_test_sessions"] == 1
html = cab.render_qwen_body(q)
assert "no runs yet" not in html and "<table" in html and "24,755" in html and "$0.0430" in html, html
assert "1 setup test session before 10/25" in html and "1 unreadable line(s)" in html
assert "estimated, list price" in html and "Qwen Code system prompt adds ~25k input tokens per request" in html
assert "Last session 2026-10-24 10:30 PDT" in html
assert_private("collect_qwen", q)
assert_private("render_qwen_body", html)

for env_text in ("OPENROUTER_API_KEY=\n", "# OPENROUTER_API_KEY=sk-or-v1-commented-out-0123456789\n", "OTHER=1\n"):
    (TMP / ".dsh" / ".env").write_text(env_text)
    q = cab.collect_qwen()
    assert q["auth_ok"] is False and q["ok"] is False and "OpenRouter key missing" in q["error"], (env_text, q)
    assert "sk-or" not in json.dumps(q)
(TMP / ".dsh" / ".env").write_text(f"export OPENROUTER_API_KEY='{OR_KEY}'\n")
assert cab.collect_qwen()["auth_ok"] is True

garbage = bindir / "qwen-garbage"
garbage.write_text(f"#!/bin/sh\necho 'Error: key {OR_KEY} rejected'\nexit 3\n")
garbage.chmod(0o755)
cab.QWEN_BIN = garbage
q = cab.collect_qwen()
assert q["cli_version"] is None and q["ok"] is False and "printed no version (exit 3)" in q["error"], q
assert_private("garbage --version", q)

real_run = subprocess.run


def timeout_run(cmd, *a, **kw):
    raise subprocess.TimeoutExpired(list(cmd) + [f"--api-key={OR_KEY}"], kw.get("timeout", 1))


cab.subprocess.run = timeout_run
q = cab.collect_qwen()
cab.subprocess.run = real_run
assert "qwen-garbage timeout after 20s" in q["error"] and q["usage"]["sessions"] == 1, q
assert_private("timeout", q)

cab.QWEN_BIN = TMP / "nope" / "qwen"
(TMP / ".qwen" / "usage_record.jsonl").unlink()
q = cab.collect_qwen()
assert q["ok"] is False and q["error"].startswith("qwen binary not found") and q["usage"]["sessions"] == 0, q
assert "no runs yet" in cab.render_qwen_body(q)
(TMP / ".qwen" / "usage_record.jsonl").mkdir()  # unreadable (a directory) is not "no runs"
q = cab.collect_qwen()
assert "usage" not in q and "usage_record.jsonl unreadable" in q["error"], q
html = cab.render_qwen_body(q)
assert "Usage unavailable" in html and "no runs yet" not in html
(TMP / ".qwen" / "usage_record.jsonl").rmdir()
cab.QWEN_BIN = fake
(TMP / ".dsh" / ".env").write_text(f"OPENROUTER_API_KEY={OR_KEY}\n")

# 9. settings.json model: v4 model.name, older bare string, invalid / key-shaped ids rejected
sp = TMP / "settings-test.json"
for doc, want in (({"model": {"name": MODEL}}, MODEL), ({"model": "qwen3-coder-plus"}, "qwen3-coder-plus"),
                  ({"model": {"name": OR_KEY}}, None), ({"model": {"name": "a b"}}, None), ({}, None),
                  (["model"], None)):
    sp.write_text(json.dumps(doc))
    assert cab.qwen_settings_model(sp) == want, (doc, want)
sp.write_text("{ // comments are not JSON\n}")
assert cab.qwen_settings_model(sp) is None and cab.qwen_settings_model(TMP / "missing.json") is None

# 10. Kimi config.toml: top-level default_model, [thinking] effort; tomllib and the 3.9 line-scan fallback
KIMI_TOML = """default_plan_mode = false
default_model = "kimi-code/k3.1-pro"   # 2026-10-24 default
telemetry = false

[loop_control]
max_retries_per_step = 3

[[hooks]]
default_model = "kimi-code/from-array-table"

[[hooks]]
default_model = "kimi-code/from-array-table"

[thinking]
enabled = true
effort = "max"

[models."kimi-code/k3"]
model = "k3"
default_effort = "low"

[models."kimi-code/k3.1-pro"]
model = "k3.1-pro"
support_efforts = [ "low", "high", "max" ]
default_effort = "max"
"""
modes = [False] + ([True] if cab.tomllib is not None else [])
for use_toml in modes:
    def parse(text):
        return cab.parse_kimi_config(text, use_tomllib=use_toml)

    assert parse(KIMI_TOML) == {"default_model": "kimi-code/k3.1-pro", "effort": "max"}, (use_toml, parse(KIMI_TOML))
    assert parse("default_model = 'kimi-code/k3.1-pro'\neffort = \"high\"\n[thinking]\neffort = \"max\"\n") == \
        {"default_model": "kimi-code/k3.1-pro", "effort": "high"}  # top-level effort wins
    assert parse('[models."kimi-code/k3"]\ndefault_model = "kimi-code/k3"\n')["default_model"] is None  # not top-level
    assert parse('default_model = "bad id; rm -rf /"\n[thinking]\neffort = "MAX!"\n') == {"default_model": None, "effort": None}
    assert parse("telemetry = false\n") == {"default_model": None, "effort": None}
    dup = parse('default_model = "kimi-code/k3"\ndefault_model = "kimi-code/k3.1-pro"\n')
    assert dup["default_model"] is None and "config_error" in dup, dup
assert cab.parse_kimi_config('default_model = """kimi-code/k3"""\n', use_tomllib=False)["default_model"] is None
if cab.tomllib is not None:
    assert "config_error" in cab.parse_kimi_config("default_model = \n", use_tomllib=True)

kc = cab.read_kimi_config()
assert kc["default_model"] is None and kc["config_error"] == "~/.kimi-code/config.toml not found", kc
(TMP / ".kimi-code").mkdir()
(TMP / ".kimi-code" / "config.toml").write_text(KIMI_TOML)
kc = cab.read_kimi_config()
assert (kc["default_model"], kc["effort"], kc["config_source"]) == ("kimi-code/k3.1-pro", "max", "~/.kimi-code/config.toml")


# 11. collect_kimi carries the model on the live-API path and on the fallback path
def fake_curl(cmd, *a, **kw):
    if isinstance(cmd, (list, tuple)) and cmd and cmd[0] == "curl":
        body = json.dumps({"usage": {"limit": "100", "remaining": "40", "resetTime": "2026-10-30T00:00:00Z"}, "limits": []})
        return subprocess.CompletedProcess(cmd, 0, stdout=body + "\n__HTTP__200", stderr="")
    return real_run(cmd, *a, **kw)


cab.WIKI_DAILY = cab.HUNT = TMP / "no-vault"
cab.subprocess.run = fake_curl
cred = TMP / ".kimi-code" / "credentials" / "kimi-code.json"
cred.parent.mkdir(parents=True)
cred.write_text(json.dumps({"access_token": KIMI_TOKEN}))
k = cab.collect_kimi()
assert k["status"] == "ok" and k["used_percent"] == 60.0, k
assert (k["default_model"], k["effort"]) == ("kimi-code/k3.1-pro", "max"), k
cred.unlink()
k = cab.collect_kimi()  # no credentials → vault-marker fallback (its status depends on /tmp logs; not asserted)
assert k["source"].startswith("Wiki/Daily") and (k["default_model"], k["effort"]) == ("kimi-code/k3.1-pro", "max"), k
cred.write_text(json.dumps({"access_token": KIMI_TOKEN}))

# 12. main(): snapshot.json + index.html carry the Qwen card and the Kimi model; nothing private leaks
(TMP / ".qwen" / "usage_record.jsonl").write_text(rec(datetime(2026, 10, 24, 10, 30, 52, tzinfo=PT)) + "\n")
cab.HERE = TMP / "out"
for name in ("collect_claude", "collect_codex", "collect_agy", "collect_muse", "collect_dsh", "collect_routine_proxy"):
    setattr(cab, name, lambda: {})
cab.collect_grok = lambda: {"ok": False, "bots": [], "stale": True, "stale_reason": "test"}
cab.main()
cab.subprocess.run = real_run
snap_text = (cab.HERE / "snapshot.json").read_text()
snap = json.loads(snap_text)
html = (cab.HERE / "index.html").read_text()
assert snap["qwen"]["usage"]["windows"]["all_time"]["est_cost_usd"] == 0.042968, snap["qwen"]
assert snap["qwen"]["trial"]["setup_test_sessions"] == 1 and snap["qwen"]["pricing"]["label"] == "estimated, list price"
assert (snap["kimi"]["default_model"], snap["kimi"]["effort"]) == ("kimi-code/k3.1-pro", "max")
assert '<section class="card" id="qwen">' in html and "<h2>Qwen Code</h2>" in html
assert "qwen --version · OpenRouter Qwen3.8-Max" in html and "24,755" in html
assert "model <strong>kimi-code/k3.1-pro</strong> · effort <strong>max</strong>" in html
assert_private("snapshot.json", snap_text)
assert_private("index.html", html)

print("ALL CHECKS PASSED")
