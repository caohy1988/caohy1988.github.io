#!/usr/bin/env python3
"""Checks for the OpenCode · GLM-5.3 card (opencode.db reader: missing / empty db, cost sum, windows,
skipped rows, privacy), the opencode.json model reader, and the "default small" label on the OpenCode
and DSH cards.

    python3 test_opencode_usage.py

Builds throwaway opencode.db files with the OpenCode 1.19.4 table layout, uses a temp HOME, a fake
opencode binary, a fake dsh binary and a fake key; never reads the real ~/.local/share/opencode,
~/.config/opencode or ~/.dsh, never touches the network or the real snapshot.json / index.html.
"""
import hashlib
import json
import os
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import collect_and_build as cab  # noqa: E402

PT = cab.PT
TMP = Path(tempfile.mkdtemp())
os.environ["HOME"] = str(TMP)  # collect_opencode resolves ~ per call
OR_KEY = "sk-or-v1-FAKEFAKEFAKE0123456789abcdef0123456789"
PROJECT = "/Users/someone/private-client-repo"
PROMPT = "PRIVATE PROMPT: triage the failing CI run on the client repo"
TITLE = "Private session title for the client repo"
NOW = datetime(2026, 10, 24, 18, 30, tzinfo=PT)  # after both 2026-10-24 smoke sessions (18:05 and 18:10 PT)

# The OpenCode 1.19.4 tables the reader touches, as created by OpenCode itself (copied from its opencode.db).
SCHEMA = """
CREATE TABLE `session` (
  `id` text PRIMARY KEY, `project_id` text NOT NULL, `workspace_id` text, `parent_id` text, `slug` text NOT NULL,
  `directory` text NOT NULL, `path` text, `title` text NOT NULL, `version` text NOT NULL, `share_url` text,
  `summary_additions` integer, `summary_deletions` integer, `summary_files` integer, `summary_diffs` text,
  `metadata` text, `cost` real DEFAULT 0 NOT NULL, `tokens_input` integer DEFAULT 0 NOT NULL,
  `tokens_output` integer DEFAULT 0 NOT NULL, `tokens_reasoning` integer DEFAULT 0 NOT NULL,
  `tokens_cache_read` integer DEFAULT 0 NOT NULL, `tokens_cache_write` integer DEFAULT 0 NOT NULL,
  `revert` text, `permission` text, `agent` text, `model` text, `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL, `time_compacting` integer, `time_archived` integer);
CREATE TABLE `message` (
  `id` text PRIMARY KEY, `session_id` text NOT NULL, `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL, `data` text NOT NULL);
CREATE TABLE `part` (
  `id` text PRIMARY KEY, `message_id` text NOT NULL, `session_id` text NOT NULL, `time_created` integer NOT NULL,
  `time_updated` integer NOT NULL, `data` text NOT NULL);
"""

PRIME, PLAIN = "ses_5f0c1e9a2b3d4c5e6f7a8b9c0d", "ses_5f0c1e9a2b3d4c5e6f7a8b9c0e"
# The 7 assistant rows of the two real 2026-10-24 smoke sessions (OpenCode's own numbers):
# (session, time_created ms, cost, input, output, reasoning, cache read, modelID)
SMOKE = [
    (PRIME, 1792890351204, 0.0593544, 21110, 17, 11, 0, "z-ai/glm-5.3-prime"),
    (PRIME, 1792890356947, 0.01270592, 198, 45, 0, 20992, "z-ai/glm-5.3-prime"),
    (PRIME, 1792890359479, 0.01271632, 252, 2, 27, 20992, "z-ai/glm-5.3-prime"),
    (PLAIN, 1792890620085, 0.001740132, 21060, 17, 34, 64, "z-ai/glm-5.3"),
    (PLAIN, 1792890624392, 0.001778934, 106, 45, 43, 21120, "z-ai/glm-5.3"),
    (PLAIN, 1792890626604, 0.00169539, 74, 22, 1, 21248, "z-ai/glm-5.3"),
    (PLAIN, 1792890627870, 0.002022992, 64, 2, 252, 21312, "z-ai/glm-5.3"),
]
USER_ROWS = [(PRIME, 1792890350774, "z-ai/glm-5.3-prime"), (PLAIN, 1792890619693, "z-ai/glm-5.3")]
# Hand sums of SMOKE; they equal the session table's own totals (cost 0.08477664 + 0.007237448).
SMOKE_ALL = {"sessions": 2, "requests": 7,
             "input_tokens": 42864 + 105728,  # uncached 21560 + 21304, plus cache read 41984 + 63744
             "cached_tokens": 105728, "cache_write_tokens": 0, "output_tokens": 150, "reasoning_tokens": 368,
             "cost_usd": 0.092014}  # 0.092014088 rounded to 6 places


def ms(dt):
    return int(dt.timestamp() * 1000)


def assistant(cost, inp, out, reasoning, read, model="z-ai/glm-5.3", created=0, write=0, **extra):
    """An assistant message's data JSON, shaped like OpenCode 1.19.4 writes it."""
    o = {"parentID": "msg_a1b2c3d4e5f6a7b8c9d0e1f2a3", "role": "assistant", "mode": "build", "agent": "build",
         "variant": "max", "path": {"cwd": PROJECT, "root": PROJECT}, "cost": cost,
         "tokens": {"total": inp + out + reasoning + read + write, "input": inp, "output": out,
                    "reasoning": reasoning, "cache": {"write": write, "read": read}},
         "modelID": model, "providerID": "openrouter", "time": {"created": created, "completed": created + 4000},
         "finish": "tool-calls"}
    o.update(extra)
    return o


def user(model, created):
    return {"role": "user", "time": {"created": created}, "agent": "build",
            "model": {"providerID": "openrouter", "modelID": model, "variant": "max"}, "summary": {"diffs": []}}


def make_db(path, messages=(), sessions=((PRIME, None), (PLAIN, None)), wal=False):
    """messages: (session_id, time_created, data); data is a dict (JSON-encoded here) or raw text.
    wal=True matches OpenCode's own opencode.db, which is in WAL journal mode."""
    con = sqlite3.connect(str(path))
    if wal:
        con.execute("PRAGMA journal_mode=wal")
    con.executescript(SCHEMA)
    for sid, parent in sessions:
        con.execute("INSERT INTO session (id, project_id, parent_id, slug, directory, title, version, time_created,"
                    " time_updated) VALUES (?, 'prj', ?, 'brave-otter', ?, ?, '1.19.4', 1, 1)",
                    (sid, parent, PROJECT, TITLE))
    for i, (sid, created, data) in enumerate(messages):
        text = data if isinstance(data, str) else json.dumps(data)
        con.execute("INSERT INTO message VALUES (?, ?, ?, ?, ?)", (f"msg_{i:026d}", sid, created, created, text))
        con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)", (f"prt_{i:026d}", f"msg_{i:026d}", sid, created,
                                                                  created, json.dumps({"type": "text", "text": PROMPT})))
        if isinstance(data, dict) and data.get("role") == "assistant":
            for kind in ("step-start", "step-finish"):
                con.execute("INSERT INTO part VALUES (?, ?, ?, ?, ?, ?)",
                            (f"prt_{i:026d}-" + kind, f"msg_{i:026d}", sid, created, created, json.dumps({"type": kind})))
    con.commit()
    con.close()
    return path


def smoke_rows():
    rows = [(sid, created, user(model, created)) for sid, created, model in USER_ROWS]
    rows += [(sid, created, assistant(cost, i, o, r, c, model, created)) for sid, created, cost, i, o, r, c, model in SMOKE]
    return rows


def assert_private(label, blob, paths=True):
    """paths=False for whole-page checks: other cards publish their own binary paths (pre-existing)."""
    text = blob if isinstance(blob, str) else json.dumps(blob)
    for s in (PROJECT, PROMPT, TITLE, PRIME, PLAIN, "msg_", "prt_", "brave-otter", OR_KEY, "sk-or", "Bearer") + ((str(TMP),) if paths else ()):
        assert s not in text, f"{label}: leaked {s[:16]}"


def card(db, now=NOW):
    u = cab.summarize_opencode_usage(db, now)
    return u, cab.render_opencode_body({"usage": u})


# 1. missing db: no lookup ran, so usage is unavailable (never zero), and the reader creates nothing
missing = TMP / "nope" / "opencode.db"
u, h = card(missing)
assert u == {"state": "missing"}, u
assert not missing.exists() and not missing.parent.exists()
assert "usage unavailable: opencode.db not found" in h and "no requests yet" not in h and "<table" not in h, h

# 2. empty db (OpenCode's tables, no rows): a lookup that worked and found nothing
u, h = card(make_db(TMP / "empty.db"))
assert u["state"] == "no_requests" and u["requests"] == 0 and u["sessions"] == 0, u
assert u["bad_rows"] == 0 and u["future_records"] == 0 and u["last_run_pt"] is None and u["models"] == [], u
assert u["windows"]["all_time"] == {"sessions": 0, "requests": 0, "input_tokens": 0, "cached_tokens": 0,
                                    "cache_write_tokens": 0, "output_tokens": 0, "reasoning_tokens": 0,
                                    "cost_usd": 0.0}, u
assert "no requests yet" in h and "usage unavailable" not in h and "<table" not in h and ">DATA<" not in h, h
# a session whose prompt never reached the model (user row only) is still no requests
u, h = card(make_db(TMP / "user-only.db", [(PLAIN, ms(NOW) - 60_000, user("z-ai/glm-5.3", ms(NOW) - 60_000))]))
assert u["state"] == "no_requests" and u["requests"] == 0 and u["bad_rows"] == 0, u

# 2b. a zero-byte file and a non-database file are unreadable, not empty
(TMP / "zero.db").write_bytes(b"")
(TMP / "garbage.db").write_bytes(b"this is not a sqlite database at all " * 40)
for name, why in (("zero.db", "database read failed"), ("garbage.db", "database read failed")):
    u, h = card(TMP / name)
    assert u["state"] == "unreadable" and why in u["error"] and u["error"].startswith("opencode.db unreadable: "), u
    assert "windows" not in u and "usage unavailable" in h and "no requests yet" not in h, (u, h)
assert (TMP / "zero.db").read_bytes() == b""  # still zero bytes: nothing was created in it

# 3. cost sum on the real smoke rows: totals, per model, last run in PT, rows read but never published
smoke = make_db(TMP / "smoke.db", smoke_rows(), wal=True)
before = hashlib.sha256(smoke.read_bytes()).hexdigest()
u, h = card(smoke)
assert hashlib.sha256(smoke.read_bytes()).hexdigest() == before  # read-only: the file is unchanged
assert u["state"] == "ok" and u["requests"] == 7 and u["sessions"] == 2 and u["bad_rows"] == 0, u
assert u["windows"]["all_time"] == SMOKE_ALL, u["windows"]["all_time"]
assert u["windows"]["last_24h"] == SMOKE_ALL == u["windows"]["last_7d"]
assert u["last_run_pt"] == "2026-10-24 18:10 PDT", u["last_run_pt"]
assert u["models"] == [
    {"sessions": 1, "requests": 4, "input_tokens": 21304 + 63744, "cached_tokens": 63744, "cache_write_tokens": 0,
     "output_tokens": 86, "reasoning_tokens": 330, "cost_usd": 0.007237, "model": "z-ai/glm-5.3"},
    {"sessions": 1, "requests": 3, "input_tokens": 21560 + 41984, "cached_tokens": 41984, "cache_write_tokens": 0,
     "output_tokens": 64, "reasoning_tokens": 38, "cost_usd": 0.084777, "model": "z-ai/glm-5.3-prime"},
], u["models"]
for want in ("<table", "148,592", "105,728", "368", "$0.0920", "Last run 2026-10-24 18:10 PDT",
             "All time by model: z-ai/glm-5.3 85,048 in / 86 out, $0.0072 · z-ai/glm-5.3-prime 63,544 in / 64 out, $0.0848",
             "not an OpenRouter invoice", "$0.079/M input, $1.40/M output"):
    assert want in h, (want, h)
assert "no requests yet" not in h and ">DATA<" not in h
assert_private("smoke summary", u)
assert_private("smoke card", h)
# cache writes count as input (all prompt tokens) and on their own line in the data
u = cab.summarize_opencode_usage(make_db(TMP / "write.db", [(PLAIN, ms(NOW), assistant(0.5, 10, 1, 0, 20, write=30))]), NOW)
w = u["windows"]["all_time"]
assert (w["input_tokens"], w["cached_tokens"], w["cache_write_tokens"], w["cost_usd"]) == (60, 20, 30, 0.5), w

# 4. the connection the reader opens refuses writes
con = cab._opencode_connect(smoke)
try:
    con.execute("CREATE TABLE probe (x)")
    raise AssertionError("opencode.db connection accepted a write")
except sqlite3.OperationalError as e:
    assert "readonly" in str(e), e
finally:
    con.close()

# 5. windows: 24h / 7d / all time, and the 24h edge
base = ms(NOW)
rows = [(PLAIN, base - 3_600_000, assistant(0.25, 100, 10, 0, 0)),
        (PRIME, base - 2 * 86_400_000, assistant(0.25, 100, 10, 0, 0)),
        (PRIME, base - 30 * 86_400_000, assistant(0.5, 100, 10, 0, 0)),
        (PLAIN, base - 86_400_000, assistant(0.125, 100, 10, 0, 0))]  # exactly 24h old: inside the 24h window
u = cab.summarize_opencode_usage(make_db(TMP / "windows.db", rows), NOW)
ws = u["windows"]
assert [ws[k]["requests"] for k in ("last_24h", "last_7d", "all_time")] == [2, 3, 4], ws
assert [ws[k]["sessions"] for k in ("last_24h", "last_7d", "all_time")] == [1, 2, 2], ws
assert [ws[k]["cost_usd"] for k in ("last_24h", "last_7d", "all_time")] == [0.375, 0.625, 1.125], ws

# 6. skipped rows: user rows silently; unusable assistant rows and unknown roles counted; future rows quarantined
good = (PLAIN, base - 60_000, assistant(0.002022992, 64, 2, 252, 21312))
bad = [
    (PLAIN, base, "not json"),
    (PLAIN, base, "[1, 2]"),
    (PLAIN, base, json.dumps({"role": "system", "cost": 0})),  # a role this reader does not know
    (PLAIN, base, json.dumps({k: v for k, v in assistant(0.1, 1, 1, 0, 0).items() if k != "tokens"})),
    (PLAIN, base, assistant("0.1", 1, 1, 0, 0)),
    (PLAIN, base, assistant(True, 1, 1, 0, 0)),
    (PLAIN, base, assistant(-0.1, 1, 1, 0, 0)),
    (PLAIN, base, assistant(0.1, -5, 1, 0, 0)),
    (PLAIN, base, assistant(0.1, 1.5, 1, 0, 0)),
    (PLAIN, base, assistant(0.1, 1, True, 0, 0)),
    (PLAIN, base, assistant(0.1, 1, 1, 0, 0, tokens={"input": 1, "output": 1, "reasoning": 0})),  # no cache
    (PLAIN, base, json.dumps(assistant(0.1, 1, 1, 0, 0)).replace('"cost": 0.1', '"cost": NaN')),
    (PLAIN, "2026-10-24T18:10:27Z", assistant(0.1, 1, 1, 0, 0)),  # time_created as text (integer affinity keeps it text)
    (PLAIN, 0, assistant(0.1, 1, 1, 0, 0)),
]
future = (PLAIN, base + 1, assistant(9.0, 1000, 1000, 0, 0))  # 1 ms after the collection time
u, h = card(make_db(TMP / "bad.db", [(PLAIN, base - 120_000, user("z-ai/glm-5.3", base - 120_000)), good] + bad + [future]))
assert u["state"] == "ok" and u["requests"] == 1 and u["bad_rows"] == len(bad) == 14 and u["future_records"] == 1, u
assert u["windows"]["all_time"]["cost_usd"] == 0.002023 and u["windows"]["all_time"]["output_tokens"] == 2, u
assert ">DATA<" in h and "Not counted from opencode.db: 14 unreadable rows, 1 future-dated row" in h and "<table" in h, h
u = cab.summarize_opencode_usage(make_db(TMP / "only-bad.db", bad[:1] + [future]), NOW)
assert u["state"] == "unreadable" and u["requests"] == 0 and (u["bad_rows"], u["future_records"]) == (1, 1), u
h = cab.render_opencode_body({"usage": u})
assert "usage unavailable: no readable rows" in h and "no requests yet" not in h and "1 unreadable row, 1 future-dated row" in h, h
u = cab.summarize_opencode_usage(make_db(TMP / "odd-model.db", [(PLAIN, base, assistant(0.1, 1, 1, 0, 0, model=OR_KEY))]), NOW)
assert u["models"][0]["model"] == "unrecognized model id" and u["requests"] == 1, u
assert_private("odd model id", u)
# per-model rows come out sorted by model id, so refreshes do not reshuffle the page
ids = ["z-ai/glm-5.3-flash", "deepseek/deepseek-v4.1-flash-1017", "z-ai/glm-5.3", "m/n", "a/b"]
u = cab.summarize_opencode_usage(make_db(TMP / "order.db", [(PLAIN, base - i, assistant(0.01, 1, 1, 0, 0, model=m))
                                                            for i, m in enumerate(ids)]), NOW)
assert [m["model"] for m in u["models"]] == ["a/b", "deepseek/deepseek-v4.1-flash-1017", "m/n", "z-ai/glm-5.3",
                                             "z-ai/glm-5.3-flash"], u["models"]

# 7. a subagent's child session counts toward its top-level session; a parent cycle still ends
fam = [(PLAIN, base - 5000, assistant(0.01, 1, 1, 0, 0)), ("ses_child", base - 4000, assistant(0.01, 1, 1, 0, 0)),
       ("ses_grandchild", base - 3000, assistant(0.01, 1, 1, 0, 0))]
u = cab.summarize_opencode_usage(make_db(TMP / "family.db", fam, sessions=(
    (PLAIN, None), ("ses_child", PLAIN), ("ses_grandchild", "ses_child"))), NOW)
assert (u["sessions"], u["requests"]) == (1, 3), u
loop = [("ses_a", base - 2000, assistant(0.01, 1, 1, 0, 0)), ("ses_b", base - 1000, assistant(0.01, 1, 1, 0, 0))]
u = cab.summarize_opencode_usage(make_db(TMP / "loop.db", loop, sessions=(("ses_a", "ses_b"), ("ses_b", "ses_a"))), NOW)
assert (u["sessions"], u["requests"]) == (1, 2), u

# 8. opencode.json: provider/model from "model", effort from that model's reasoning options
cfg = TMP / "opencode-test.json"
REAL_CFG = {"$schema": "https://opencode.ai/config.json", "model": "openrouter/z-ai/glm-5.3",
            "small_model": "openrouter/z-ai/glm-5.3-flash", "autoupdate": False, "share": "disabled",
            "provider": {"openrouter": {"options": {"apiKey": "{env:OPENROUTER_API_KEY}"}, "models": {
                "z-ai/glm-5.3": {"options": {"reasoning": {"effort": "xhigh"}, "usage": {"include": True}}}}}}}
NONE = {"provider": None, "model": None, "effort": None}
for doc, want in ((REAL_CFG, {"provider": "openrouter", "model": "z-ai/glm-5.3", "effort": "xhigh"}),
                  (dict(REAL_CFG, provider={}), {"provider": "openrouter", "model": "z-ai/glm-5.3", "effort": None}),
                  (dict(REAL_CFG, model="openrouter/z-ai/glm-5.3-flash"),
                   {"provider": "openrouter", "model": "z-ai/glm-5.3-flash", "effort": None}),
                  (dict(REAL_CFG, model="glm-5.3"), NONE),  # no provider prefix
                  (dict(REAL_CFG, model="open router/z-ai/glm-5.3"), NONE),  # unpublishable provider id
                  (dict(REAL_CFG, model=f"openrouter/{OR_KEY}"), NONE),  # key-shaped id
                  (dict(REAL_CFG, model="openrouter/a b"), NONE),
                  (dict(REAL_CFG, model=7), NONE), ({}, NONE), (["model"], NONE)):
    cfg.write_text(json.dumps(doc))
    assert cab.opencode_config(cfg) == want, (doc, cab.opencode_config(cfg))
bad_effort = json.loads(json.dumps(REAL_CFG))
bad_effort["provider"]["openrouter"]["models"]["z-ai/glm-5.3"]["options"]["reasoning"]["effort"] = "MAX!"
cfg.write_text(json.dumps(bad_effort))
assert cab.opencode_config(cfg)["effort"] is None
cfg.write_text("{ // comments are not JSON\n}")
assert cab.opencode_config(cfg) == NONE and cab.opencode_config(TMP / "missing.json") == NONE

# 9. collect_opencode end to end: fake binary, temp HOME, fake key; nothing private in the result
bindir = TMP / "bin"
bindir.mkdir()
fake = bindir / "opencode"
fake.write_text("#!/bin/sh\necho 1.19.4\n")
fake.chmod(0o755)
(TMP / ".config" / "opencode").mkdir(parents=True)
(TMP / ".config" / "opencode" / "opencode.json").write_text(json.dumps(REAL_CFG, indent=2))
(TMP / ".dsh").mkdir()
(TMP / ".dsh" / ".env").write_text(f"# dsh\nOPENROUTER_API_KEY={OR_KEY}\n")
cab.OPENCODE_BIN = fake
cab.now_pt = lambda: NOW

oc = cab.collect_opencode()  # OpenCode installed, no opencode.db yet
assert oc["ok"] is True and oc["cli_version"] == "1.19.4" and oc["seat"] == "default small", oc
assert (oc["provider"], oc["model"], oc["effort"]) == ("openrouter", "z-ai/glm-5.3", "xhigh"), oc
assert oc["auth_ok"] is True and "error" not in oc and oc["usage"] == {"state": "missing"}, oc
h = cab.render_opencode_body(oc)
assert "usage unavailable: opencode.db not found" in h and "DEFAULT SMALL" in h and "first choice" in h, h
assert "CLI <strong>1.19.4</strong>" in h and "model <strong>z-ai/glm-5.3</strong>" in h and "effort <strong>xhigh</strong>" in h

(TMP / ".local" / "share" / "opencode").mkdir(parents=True)
make_db(TMP / ".local" / "share" / "opencode" / "opencode.db", smoke_rows(), wal=True)
oc = cab.collect_opencode()
assert oc["usage"]["windows"]["all_time"] == SMOKE_ALL and "error" not in oc, oc
h = cab.render_opencode_body(oc)
assert "AUTH OK" in h and "$0.0920" in h and "Last run 2026-10-24 18:10 PDT" in h, h
assert_private("collect_opencode", oc)
assert_private("render_opencode_body", h)

for env_text in ("OPENROUTER_API_KEY=\n", "# OPENROUTER_API_KEY=sk-or-v1-commented-out-0123456789\n", "OTHER=1\n"):
    (TMP / ".dsh" / ".env").write_text(env_text)
    oc = cab.collect_opencode()
    assert oc["auth_ok"] is False and oc["ok"] is False and "OpenRouter key missing" in oc["error"], (env_text, oc)
    assert "sk-or" not in json.dumps(oc)
(TMP / ".dsh" / ".env").write_text(f"OPENROUTER_API_KEY={OR_KEY}\n")

garbage = bindir / "opencode-garbage"
garbage.write_text(f"#!/bin/sh\necho 'Error: key {OR_KEY} rejected'\nexit 3\n")
garbage.chmod(0o755)
cab.OPENCODE_BIN = garbage
oc = cab.collect_opencode()
assert oc["cli_version"] is None and oc["ok"] is False and "printed no version (exit 3)" in oc["error"], oc
assert oc["usage"]["requests"] == 7  # usage is still read
assert_private("garbage --version", oc)

real_run = subprocess.run
seen_env = {}


def timeout_run(cmd, *a, **kw):
    seen_env.update(kw.get("env") or {})
    raise subprocess.TimeoutExpired(list(cmd) + [f"--api-key={OR_KEY}"], kw.get("timeout", 1))


cab.subprocess.run = timeout_run
oc = cab.collect_opencode()
cab.subprocess.run = real_run
assert "opencode version check timed out" in oc["error"] and oc["usage"]["requests"] == 7, oc
assert seen_env.get("OPENCODE_DISABLE_AUTOUPDATE") == "1", "a dashboard refresh must not self-update OpenCode"
assert_private("timeout", oc)

cab.OPENCODE_BIN = TMP / "nope" / "opencode"
oc = cab.collect_opencode()
assert oc["ok"] is False and oc["error"].startswith("opencode binary not found") and oc["usage"]["requests"] == 7, oc
(TMP / ".local" / "share" / "opencode" / "opencode.db").write_bytes(b"")  # unreadable db: an error, not zero
oc = cab.collect_opencode()
assert oc["usage"]["state"] == "unreadable" and "opencode.db unreadable: " in oc["error"] and "error" not in oc["usage"], oc
assert "usage unavailable" in cab.render_opencode_body(oc)
cab.OPENCODE_BIN = fake
(TMP / ".local" / "share" / "opencode" / "opencode.db").unlink()
make_db(TMP / ".local" / "share" / "opencode" / "opencode.db", smoke_rows(), wal=True)

# 10. main(): snapshot.json + index.html carry the OpenCode card, and DSH is labeled default small too
fake_dsh = bindir / "dsh"
fake_dsh.write_text("#!/bin/sh\necho 0.2.1-rc.2\n")
fake_dsh.chmod(0o755)
cab.DSH_BIN = fake_dsh
cab.DSH_DIR = TMP / ".dsh"
(TMP / ".dsh" / "collect-model.patch.yml").write_text(
    "- id: agent-default-model\n  name: '@deepseek-ai/dsh-agent-default-model'\n  config:\n"
    "    provider: openrouter\n    model: deepseek/deepseek-v4.1-flash-1017\n    reasoningEffort: max\n")
cab.HERE = TMP / "out"
for name in [n for n in dir(cab) if n.startswith("collect_") and n not in ("collect_opencode", "collect_dsh")]:
    setattr(cab, name, lambda: {})  # every other collector, so main() runs no other CLI and no network
cab.collect_grok = lambda: {"ok": False, "bots": [], "stale": True, "stale_reason": "test"}
cab.main()
snap_text = (cab.HERE / "snapshot.json").read_text()
snap = json.loads(snap_text)
html = (cab.HERE / "index.html").read_text()
assert snap["opencode"]["usage"]["windows"]["all_time"]["cost_usd"] == 0.092014, snap["opencode"]
assert snap["opencode"]["seat"] == "default small" and snap["dsh"]["seat"] == "default small", snap["dsh"]
assert snap["dsh"]["model"] == "deepseek/deepseek-v4.1-flash-1017"
assert '<section class="card" id="opencode">' in html and "<h2>OpenCode · GLM-5.3</h2>" in html
dsh_card = html.split('<section class="card" id="dsh">', 1)[1].split("</section>", 1)[0]
assert "Default small seat · alternate + fallback" in dsh_card and "DEFAULT SMALL" in dsh_card, dsh_card
assert "model <strong>deepseek/deepseek-v4.1-flash-1017</strong>" in dsh_card, dsh_card
oc_card = html.split('<section class="card" id="opencode">', 1)[1].split("</section>", 1)[0]
assert "Default small seat · first choice" in oc_card and "148,592" in oc_card, oc_card
assert "DSH (default small), OpenCode · GLM-5.3 (default small), Qwen Code (trial)" in html
assert_private("snapshot.json opencode", snap["opencode"])
assert_private("index.html opencode card", oc_card)
assert_private("snapshot.json", snap_text, paths=False)
assert_private("index.html", html, paths=False)

print("ALL CHECKS PASSED")
