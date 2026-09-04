#!/usr/bin/env python3
"""Negative fixtures for check_full_demo.py (stdlib only).

Copies rfc/full-demo/ (and the two sibling files the checker reads: rfc/index.html and
rfc/demo/live/observe/live_identities.json) into a temp directory, applies one mutation at a time,
runs the checker on the copy, and requires a NON-ZERO exit for every mutation and a ZERO exit for
the unmodified copy. Each mutation reproduces a hole a reviewer found:

  m1  ARCHITECTURE.md gains "Phase A was executed; every binding call is made and recorded on tape."
      (Codex r4: bare "Phase A" must not qualify executed language)
  m2  plan.md gains a passive-past claim "The service accounts were created and the denials were proved on tape."
  m3  sql/sessions_summary.sql and provenance executed_query are changed to DIFFERENT quoted '--…' literals
      with recomputed hashes (Codex r4: a comment-stripping normalizer would call them equal)
  m4  the provenance executed_query is replaced by an unrelated GROUP BY 1, 2 query with its own hashes
  m5  bq_jobs_identity.json loses the summary job's row (identity must come only from the inventory)
  m6  beat6 evidence label for okf-derived-germany changed from prior to seeded (r1 label regression)

Usage: python3 rfc/full-demo/tools/mutation_fixture.py   (exit 0 when every fixture behaves)
"""
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
DEMO = HERE.parent
RFC = DEMO.parent
ENV = dict(os.environ, CHECK_FULL_DEMO_NO_MUTATION="1")


def make_copy(tmp):
    root = Path(tmp) / "rfc"
    shutil.copytree(DEMO, root / "full-demo", ignore=shutil.ignore_patterns("__pycache__"))
    (root / "demo" / "live" / "observe").mkdir(parents=True)
    shutil.copy(RFC / "demo" / "live" / "observe" / "live_identities.json", root / "demo" / "live" / "observe" / "live_identities.json")
    shutil.copy(RFC / "index.html", root / "index.html")
    return root / "full-demo"


def run_checker(demo):
    r = subprocess.run([sys.executable, str(demo / "tools" / "check_full_demo.py")], capture_output=True, text=True, env=ENV, timeout=300)
    return r.returncode, r.stdout


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def m1(d):
    p = d / "ARCHITECTURE.md"
    p.write_text(p.read_text("utf-8") + "\n\nPhase A was executed; every binding call is made and recorded on tape.\n", "utf-8")


def m2(d):
    p = d / "plan.md"
    p.write_text(p.read_text("utf-8") + "\n\nThe service accounts were created and the denials were proved on tape.\n", "utf-8")


def m3(d):
    sql = d / "sql" / "sessions_summary.sql"
    prov_p = d / "live" / "provenance_sessions_summary.json"
    prov = json.loads(prov_p.read_text("utf-8"))
    base = sql.read_text("utf-8")
    a = base.replace("SELECT session_id, agent,", "SELECT '--alpha' AS marker, session_id, agent,", 1)
    b = base.replace("SELECT session_id, agent,", "SELECT '--beta' AS marker, session_id, agent,", 1)
    assert a != b and a != base
    sql.write_text(a, "utf-8")
    prov["executed_query"] = b
    prov["sql_file_sha256_raw"] = sha(a)
    prov["executed_query_sha256_raw"] = sha(b)
    prov_p.write_text(json.dumps(prov, indent=1), "utf-8")


def m4(d):
    sql = d / "sql" / "sessions_summary.sql"
    prov_p = d / "live" / "provenance_sessions_summary.json"
    prov = json.loads(prov_p.read_text("utf-8"))
    q = "SELECT 1 AS a, 2 AS b GROUP BY 1, 2;\n"
    sql.write_text(q, "utf-8")
    prov["executed_query"] = q
    prov["sql_file_sha256_raw"] = prov["executed_query_sha256_raw"] = sha(q)
    prov_p.write_text(json.dumps(prov, indent=1), "utf-8")


def m5(d):
    p = d / "live" / "bq_jobs_identity.json"
    rows = json.loads(p.read_text("utf-8"))
    job = (d / "live" / "sessions_summary.jobid").read_text().strip()
    p.write_text(json.dumps([r for r in rows if r["job_id"] != job], indent=1), "utf-8")


def m6(d):
    p = d / "app.js"
    s = p.read_text("utf-8")
    s2 = s.replace('legacy_catalog_description: ["prior",', 'legacy_catalog_description: ["seeded",', 1)
    assert s2 != s
    p.write_text(s2, "utf-8")


MUTATIONS = [("m1 executed-language with bare Phase A", m1), ("m2 passive-past SA claims in plan.md", m2),
             ("m3 quoted-literal SQL collision", m3), ("m4 unrelated GROUP BY 1, 2 query", m4),
             ("m5 summary job missing from inventory", m5), ("m6 prior label regressed to seeded", m6)]

bad = []
with tempfile.TemporaryDirectory() as tmp:
    clean = make_copy(tmp)
    rc, out = run_checker(clean)
    print(("OK   " if rc == 0 else "FAIL ") + "clean copy passes (exit %d)" % rc)
    if rc != 0:
        bad.append("clean")
        print(re.sub(r"(?m)^OK .*\n", "", out)[-1500:])
for name, fn in MUTATIONS:
    with tempfile.TemporaryDirectory() as tmp:
        d = make_copy(tmp)
        fn(d)
        rc, out = run_checker(d)
        caught = rc != 0
        print(("OK   " if caught else "FAIL ") + "%s → checker exit %d (%s)" % (name, rc, "caught" if caught else "NOT caught"))
        if not caught:
            bad.append(name)
if bad:
    print("mutation fixture: %d problem(s): %s" % (len(bad), bad))
    sys.exit(1)
print("mutation fixture: all mutations caught, clean copy passes")
