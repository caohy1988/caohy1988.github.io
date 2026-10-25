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
LATE = datetime(2026, 10, 28, 12, 0, tzinfo=PT)  # after every trial fixture session


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


def card(text, now):
    """summarize_qwen_usage + render_qwen_body, the way collect_qwen wires them."""
    u = cab.summarize_qwen_usage(text, now)
    t = u.pop("trial")
    return u, t, cab.render_qwen_body({"usage": u, "trial": t})


# 1. no runs: missing / empty / blank file
for text in ("", "\n\n  \n"):
    u, t, h = card(text, BEFORE)
    assert u["state"] == "no_runs" and u["sessions"] == 0 and u["bad_lines"] == 0 and u["future_records"] == 0, u
    assert u["last_session_pt"] is None
    assert u["windows"]["all_time"] == {"sessions": 0, "requests": 0, "input_tokens": 0, "cached_tokens": 0,
                                        "output_tokens": 0, "unpriced_models": 0, "unpriced_tokens": 0,
                                        "est_cost_usd": 0.0}, u
    assert t["status"] == "starts 2026-10-25 (nightly ~3 AM PT; planned window through 2026-10-27); 0/3 runs", t
    assert t["runs_display"] == "0/3" and t["setup_test_sessions"] == 0
    assert "no runs yet" in h and "usage unavailable" not in h and ">DATA<" not in h

# 1b. records present but none readable (corrupt, truncated, unsupported version) is not "no runs"
for text, why in (("not json\n", "1 unreadable line"),
                  ('{"version": 1, "sessionId": "s", "timest\n' + rec(BEFORE, version=2), "2 unreadable lines")):
    u, t, h = card(text, BEFORE)
    assert u["state"] == "unreadable" and u["sessions"] == 0 and u["bad_lines"] == int(why[0]), u
    assert t["runs"] is None and t["runs_display"] is None and t["setup_test_sessions"] is None, t
    assert t["status"] == f"trial status unavailable: no readable records ({why})", t
    assert "no runs yet" not in h and "usage unavailable: no readable records" in h and "0/3" not in h, h
    assert ">DATA<" in h and f"Not counted from usage_record.jsonl: {why}" in h and "TRIAL —" in h

# 2. the real setup-test record: counts, list-price cost, last session in PT, setup test (not a trial run)
u = cab.summarize_qwen_usage(rec(datetime(2026, 10, 24, 10, 30, 52, tzinfo=PT)) + "\n", BEFORE)
w = u["windows"]["all_time"]
assert (w["sessions"], w["requests"], w["input_tokens"], w["cached_tokens"], w["output_tokens"]) == (1, 2, 24755, 4352, 179)
assert abs(SMOKE_USD - 0.042968) < 1e-12 and w["est_cost_usd"] == round(SMOKE_USD, 6) == 0.042968, w
assert u["windows"]["last_24h"] == w == u["windows"]["last_7d"]
assert u["last_session_pt"] == "2026-10-24 10:30 PDT", u["last_session_pt"]
assert u["trial"]["runs"] == 0 and u["trial"]["setup_test_sessions"] == 1
assert u["trial"]["status"] == "starts 2026-10-25 (nightly ~3 AM PT; planned window through 2026-10-27); 0/3 runs"
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
u, t, h = card("\n".join(bad_lines[:6] + [good] + bad_lines[6:] + [""]), BEFORE)
assert u["bad_lines"] == len(bad_lines) == 13 and u["sessions"] == 1 and u["state"] == "ok", u
assert u["windows"]["all_time"]["input_tokens"] == 24755
assert t["status"] == "starts 2026-10-25 (nightly ~3 AM PT; planned window through 2026-10-27); 0/3 runs (not counted: 13 unreadable lines)", t
assert "<table" in h and ">DATA<" in h and "Not counted from usage_record.jsonl: 13 unreadable lines" in h

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
# an unpriced model at zero tokens is still unpriced: no $0.00, alone or next to a priced model
zero = {"other/zero-tokens": usage(1, 0, 0, 0)}
u, t, h = card(rec(BEFORE, models=zero), BEFORE)
w, row = u["windows"]["all_time"], u["models"][0]
assert w["est_cost_usd"] is None and w["unpriced_models"] == 1 and w["unpriced_tokens"] == 0, w
assert row["est_cost_usd"] is None and row["priced"] is False and cab._qwen_cost_cell(row) == "tokens only", row
assert "$0.00" not in h and "tokens only" in h, h
u, t, h = card(rec(BEFORE, models=dict(zero, **{MODEL: SMOKE})), BEFORE)
w = u["windows"]["all_time"]
assert w["est_cost_usd"] == 0.042968 and w["unpriced_models"] == 1 and cab._qwen_cost_cell(w) == "$0.0430 + unpriced", w
assert "$0.0430 + unpriced" in h and "other/zero-tokens 0 in / 0 out, tokens only" in h, h
u = cab.summarize_qwen_usage(rec(BEFORE, models={MODEL: usage(1, 0, 0, 0)}), BEFORE)  # priced, really $0
assert u["windows"]["all_time"]["est_cost_usd"] == 0.0 and u["windows"]["all_time"]["unpriced_models"] == 0
u = cab.summarize_qwen_usage(rec(BEFORE, models={OR_KEY: usage(1, 5, 5, 0), "bad id; rm": usage(1, 5, 5, 0)}), BEFORE)
assert [m["model"] for m in u["models"]] == ["unrecognized model id"] * 2 and u["sessions"] == 1
assert_private("odd model ids", u)

# 6. windows: 24h / 7d / all time
u = cab.summarize_qwen_usage("\n".join(rec(AFTER - d, sid=str(i)) for i, d in enumerate(
    (timedelta(hours=1), timedelta(days=2), timedelta(days=30)))), AFTER)
assert [u["windows"][k]["sessions"] for k in ("last_24h", "last_7d", "all_time")] == [1, 2, 3], u["windows"]
assert u["windows"]["last_7d"]["input_tokens"] == 2 * 24755

def audit_rec(*args, **kwargs):
    return rec(*args, job_type="nightly-mac-harness-audit", **kwargs)


# 7. trial: identified audits from 2026-10-25 00:00 PT count, capped display N/3; earlier ones are setup tests
start = datetime(2026, 10, 25, tzinfo=PT)
lines = [audit_rec(start - timedelta(milliseconds=1), sid="setup"), audit_rec(start, sid="run1"),
         audit_rec(start + timedelta(hours=27), sid="run2")]
u = cab.summarize_qwen_usage("\n".join(lines), AFTER)
assert (u["trial"]["runs"], u["trial"]["runs_display"], u["trial"]["setup_test_sessions"]) == (2, "2/3", 1), u["trial"]
assert u["trial"]["status"] == "2/3 runs since 2026-10-25; planned window through 2026-10-27", u["trial"]
lines += [audit_rec(start + timedelta(hours=h), sid=f"extra{h}") for h in (50, 51, 52)]
u = cab.summarize_qwen_usage("\n".join(lines), LATE)
assert (u["trial"]["runs"], u["trial"]["runs_display"]) == (5, "3/3") and u["trial"]["status"] == "scheduled window elapsed (2026-10-25 to 2026-10-27); 3/3 runs; keep/drop pending review; 5 sessions"
assert u["future_records"] == 0 and u["sessions"] == 6
u = cab.summarize_qwen_usage(audit_rec(start - timedelta(hours=1)), start)  # midnight PT: started, 0 runs
assert u["trial"]["status"] == "0/3 runs since 2026-10-25; planned window through 2026-10-27"
assert (u["trial"]["phase"], u["trial"]["first_day"], u["trial"]["last_day"]) == ("running", "2026-10-25", "2026-10-27")

# 7a. Dates describe the planned window; elapsed dates never finish the trial.
# Ordinary sessions after the window remain excluded; identified makeup audits are tested separately.
end = datetime(2026, 10, 28, tzinfo=PT)  # the window is the PT days 10/25, 10/26 and 10/27
two = [audit_rec(start + timedelta(hours=3), sid="r1"), audit_rec(start + timedelta(hours=27), sid="r2")]
u, t, h = card("\n".join(two + [audit_rec(end - timedelta(milliseconds=1), sid="r3-late"), rec(end, sid="after1"),
                                rec(end + timedelta(days=2), sid="after2")]), end + timedelta(days=3))
assert (t["phase"], t["runs"], t["runs_display"], t["later_sessions"]) == ("window_elapsed", 3, "3/3", 2), t
assert t["status"] == "scheduled window elapsed (2026-10-25 to 2026-10-27); 3/3 runs; keep/drop pending review; 2 later sessions not counted", t
assert "TRIAL PENDING 3/3" in h and "Trial seat · planned window 2026-10-25 to 2026-10-27" in h, h
assert "ended" not in h.lower() and "complete" not in h.lower(), h
u, t, h = card("\n".join(two), end)  # midnight after the last planned night: third recorded run still required
assert (t["phase"], t["status"]) == ("window_elapsed", "scheduled window elapsed (2026-10-25 to 2026-10-27); 2/3 runs; keep/drop pending the third recorded run"), t
assert 'status-chip warn">TRIAL PENDING 2/3' in h, h
# A skipped night supplies no record. Waiting longer cannot turn 0, 1 or 2 recorded runs into completion.
for records in ([], two[:1], two):
    for when in (end, end + timedelta(days=30)):
        u, t, h = card("\n".join(records), when)
        assert (t["phase"], t["runs"], t["runs_display"]) == ("window_elapsed", len(records), f"{len(records)}/3"), t
        assert "scheduled window elapsed" in t["status"] and "keep/drop pending the third recorded run" in t["status"], t
        assert "scheduled window elapsed" in h and "keep/drop pending the third recorded run" in h, h
        assert "ended" not in json.dumps(t).lower() and "complete" not in json.dumps(t).lower(), t
        assert "ended" not in h.lower() and "complete" not in h.lower(), h
u, t, h = card("\n".join(two), end - timedelta(milliseconds=1))  # last instant of 10/27: still running
assert (t["phase"], t["status"]) == ("running", "2/3 runs since 2026-10-25; planned window through 2026-10-27"), t
assert 'status-chip unk">TRIAL 2/3' in h, h
for when in (BEFORE, AFTER, LATE):  # never relative wording, whatever the date
    _, t, h = card("\n".join(two), when)
    for word in ("currently", "this week", "today", "tonight"):
        assert word not in t["status"].lower() and word not in h.lower(), (when, word)

# 7b. records dated after the collection time are quarantined: no usage, no trial run, visible flag
u, t, h = card(audit_rec(start), BEFORE)  # Oct 25 00:00 record read on Oct 24 noon
assert u["future_records"] == 1 and u["sessions"] == 0 and u["state"] == "unreadable", u
assert u["windows"]["last_24h"]["sessions"] == 0 and t["runs"] is None, (u, t)
assert "usage unavailable: no readable records" in h and "1 future-dated record" in h and "1/3" not in h, h
u, t, h = card("\n".join([audit_rec(BEFORE - timedelta(hours=1), sid="past"), audit_rec(start, sid="future"),
                          audit_rec(BEFORE, sid="1ms-late", timestamp=int(BEFORE.timestamp()) * 1000 + 1)]), BEFORE)
assert (u["sessions"], u["future_records"], u["windows"]["last_24h"]["sessions"]) == (1, 2, 1), u
assert t["runs"] == 0 and t["status"] == "starts 2026-10-25 (nightly ~3 AM PT; planned window through 2026-10-27); 0/3 runs (not counted: 2 future-dated records)", t
assert ">DATA<" in h and "2 future-dated records" in h and "<table" in h
u = cab.summarize_qwen_usage(audit_rec(BEFORE), BEFORE)  # stamped exactly at collection time: counted
assert u["sessions"] == 1 and u["future_records"] == 0
u = cab.summarize_qwen_usage(audit_rec(start), start + timedelta(hours=3))  # once the clock passes it, it counts
assert u["sessions"] == 1 and u["trial"]["runs"] == 1 and u["trial"]["runs_display"] == "1/3"

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
assert q["trial"]["status"] == "starts 2026-10-25 (nightly ~3 AM PT; planned window through 2026-10-27); 0/3 runs" and q["note"] == cab.QWEN_NOTE
html = cab.render_qwen_body(q)
assert "no runs yet" in html and "<table" not in html and "starts 2026-10-25 (nightly ~3 AM PT; planned window through 2026-10-27); 0/3 runs" in html
assert_private("collect_qwen (no runs)", q)

(TMP / ".qwen" / "usage_record.jsonl").write_text(rec(datetime(2026, 10, 24, 10, 30, 52, tzinfo=PT)) + "\nnot json\n")
q = cab.collect_qwen()
assert q["usage"]["sessions"] == 1 and q["usage"]["bad_lines"] == 1 and q["trial"]["setup_test_sessions"] == 1
html = cab.render_qwen_body(q)
assert "no runs yet" not in html and "<table" in html and "24,755" in html and "$0.0430" in html, html
assert "1 setup test session before 2026-10-25" in html and "Not counted from usage_record.jsonl: 1 unreadable line " in html
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

# 10. Kimi config.toml: top-level default_model + [thinking] effort, via tomllib and the 3.9 scanner
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
WANT = {"default_model": "kimi-code/k3.1-pro", "effort": "max"}
NONE = {"default_model": None, "effort": None}
TAIL = 'default_model = "kimi-code/k3.1-pro"\n[thinking]\neffort = "max"\n'
VALID = [  # (valid TOML, expected); both parsers must agree on every one
    (KIMI_TOML, WANT),
    (KIMI_TOML.replace("\n", "\r\n"), WANT),
    ('default_model = "kimi-code/k3.1-pro"\n# Example: """multiline"""\n[thinking]\neffort = "max"\n', WANT),
    ('"default_model" = "kimi-code/k3.1-pro"\n["thinking"]\n\'effort\' = "max"\n', WANT),  # quoted keys
    ("default_model = 'kimi-code/k3.1-pro' # literal, comment\n[ thinking ]   # spaced header\neffort='max'#tight\n", WANT),
    ('default_model = "kimi-code/k3\\u002e1-pro"\nthinking.effort = "max"\n', WANT),  # escape; dotted key
    ('default_model = "kimi-code/k3.1-pro"\nthinking = { enabled = true, effort = "max" }\n', WANT),  # inline table
    ('default_model = """\nkimi-code/k3.1-pro"""\n[thinking]\neffort = \'\'\'max\'\'\'\n', WANT),  # one-line multi-line strings
    # look-alike lines inside unrelated values or comments cannot shadow the real keys
    ('notes = """\ndefault_model = "evil/shadow"\n[thinking]\neffort = "low"\n"""\n' + TAIL, WANT),
    ("notes = '''\n[thinking]\neffort = 'low'\n'''\n" + TAIL, WANT),
    ('notes = """an escaped \\""" does not close it\ndefault_model = "evil/shadow"\n"""\n' + TAIL, WANT),
    ('dirs = [\n  "~/a",  # a comment with a " quote\n  \'[thinking]\',\n  [1, [2]],\n  { effort = "low" },\n]\n'
     'esc = "a \\" [thinking] \\\\"\nwhen = 1979-05-27 07:32:00Z\n' + TAIL, WANT),
    ('[thinking]\neffort = "max"\n[thinking.sub]\neffort = "low"\n', dict(NONE, effort="max")),
    ('[thinking.sub]\nx = 1\n[thinking]\neffort = "max"\n', dict(NONE, effort="max")),  # super-table declared later
    ('default_model = "kimi-code/k3.1-pro"\n[[hooks]]\n[hooks.sub]\nx = 1\n[[hooks]]\n[hooks.sub]\nx = 2\n'
     '[thinking]\neffort = "max"\n', WANT),  # a sub-table per array entry
    ('default_model = "kimi-code/k3.1-pro"\nfruit.apple = "red"\n[fruit.texture]\nsmooth = true\n'
     '[thinking]\neffort = "max"\n', WANT),  # a sub-table of a dotted-key table
    (TAIL.replace("[thinking]", '[hooks.sub]\ndefault_model = "evil/in-table"\n[thinking]'), WANT),
    ('default_model = "kimi-code/k3.1-pro"\n[[thinking]]\neffort = "low"\n', dict(WANT, effort=None)),  # array of tables
    ('["thinking.x"]\neffort = "low"\n', NONE),  # a quoted key with a dot is one key
    ('effort = "high"\n[models."kimi-code/k3"]\ndefault_model = "kimi-code/k3"\n', NONE),  # neither key where it counts
    ('default_model = "bad id; rm -rf /"\n[thinking]\neffort = "MAX!"\n', NONE),  # fail the id / effort regex
    ('default_model = """kimi-code/k3\nsecond line"""\n', NONE),
    ("telemetry = false\n", NONE),
    # multi-line basic strings decode like tomllib: escapes, line-ending backslash, first newline trimmed
    ('default_model = """kimi-code/k3\\u002e1-pro"""\n[thinking]\neffort = "max"\n', WANT),  # review r2 repro
    ('default_model = """kimi-code/k3\\U0000002e1-pro"""\n[thinking]\neffort = """\\\n    max"""\n', WANT),
    ('default_model = """\\\n    kimi-code/\\\n    k3.1-pro"""\n' + TAIL[TAIL.index("["):], WANT),
    ('default_model = """kimi-code/\\   \n\n  k3.1-pro"""\n' + TAIL[TAIL.index("["):], WANT),  # spaces, blank line
    ('default_model = """\\\r\n  kimi-code/k3.1-pro"""\r\n[thinking]\r\neffort = "max"\r\n', WANT),  # CRLF
    ('note = """a \\"quoted\\" \\\\ path"""\n' + TAIL, WANT),
    ('default_model = """kimi-code/k3\\n"""\n', NONE),  # decodes to a value with a newline: fails the id regex
    ("default_model = '''kimi-code/k3\\u002e1-pro'''\n", NONE),  # literal: no escapes, so a backslash stays
]
INVALID = [  # both parsers refuse the whole file, so nothing is read from it
    'default_model = "kimi-code/k3"\ndefault_model = "kimi-code/k3.1-pro"\n',
    'default_model = "kimi-code/k3.1-pro" junk\n',
    'default_model = "kimi-code/k3.1-pro\n',
    'notes = """never closed\n' + TAIL,
    '[thinking]\neffort = "max"\n[thinking]\nenabled = true\n',
    "default_model = \n",
    'thinking.effort = "high"\n[thinking]\nenabled = true\n',  # dotted-key table reopened by a header
    'thinking = { enabled = true }\n[thinking]\neffort = "max"\n',  # inline table reopened
    '[thinking]\neffort = "max"\n[[thinking]]\n',  # table, then array of tables
    '[[thinking]]\n[thinking]\neffort = "max"\n',  # array of tables, then table
    'default_model = "kimi-code/k3"\ndefault_model.x = 1\n',  # a value extended by a dotted key
    'thinking.effort.x = 1\nthinking.effort = "max"\n',  # a dotted-key table overwritten by a value
    '[thinking.effort]\nx = 1\n[thinking]\neffort = "max"\n',  # a header table overwritten by a value
    'default_model = "kimi-code/k3.1-pro"\r[thinking]\neffort = "max"\n',  # bare CR
    'default_model = """kimi-code/k3\\q"""\n',  # unknown escape
    'default_model = """kimi-code/k3\\u002"""\n',  # short \u
    'default_model = """\\uD800"""\n',  # surrogate: not a Unicode scalar value
    'default_model = """kimi \\  x"""\n',  # backslash, spaces, then text: not a line ending
    'default_model = "kimi-code/k3\\u 02e1-pro"\n',  # \u needs exactly 4 hex digits (int() would take " 02e")
    'default_model = "kimi-code/k3\\uD800"\n',
]
modes = [False] + ([True] if cab.tomllib is not None else [])  # 3.9: the scanner only
for use_toml in modes:
    for doc, want in VALID:
        got = cab.parse_kimi_config(doc, use_tomllib=use_toml)
        assert got == want, (use_toml, doc, got)
    for doc in INVALID:
        got = cab.parse_kimi_config(doc, use_tomllib=use_toml)
        assert got["default_model"] is None and got["effort"] is None and "config_error" in got, (use_toml, doc, got)

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
for name in ("collect_claude", "collect_codex", "collect_agy", "collect_muse", "collect_dsh", "collect_openrouter",
             "collect_routine_proxy"):
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
