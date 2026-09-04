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
  m7  active-past claim "The operator created the three Phase A service accounts." (Codex r5)
  m8  "Every binding was recorded on tape, while future documentation is planned." (Codex r5: trailing qualifier)
  m9  executed claim in one list item / paragraph, qualifier only in the next (Codex r5: block boundaries)
  m10 SQL file rewritten LF → CRLF only (Codex r5: read_text universal newlines hid the byte change)
  m11 constant SELECT with the required tokens only in -- comments, hashes recomputed (Codex r5: comment smuggling)
  m12 "No DML touched agent_events, and the three Phase A service accounts were created." (Codex r6: bare No latch)
  m13 "The operator made every Phase A binding." (Codex r6: verb vocabulary)
  m14 "Check 6 returned PERMISSION_DENIED." (Codex r6: underscore stripping broke the identifier)
  m15 "It is not a secret that the denials were proved on tape." (r6 cousin: negation not bound to the predicate)
  m16 "Without a tape, the operator created the service accounts." (r6 cousin: negation in another clause)
  m17 upper-case executed claim (r6 cousin: case-insensitive matching)
  m18 "The operator created the service accounts as expected." (Codex r7: qualifier after the verb)
  m19 "Future documentation is planned, then the operator created the three service accounts." (Codex r7: then resets)
  m20 "The service account was not created after the operator granted the custom role." (Codex r7: per-predicate negation)
  m21 "The operator granted the custom role, as planned." (r7 cousin: trailing status in a later clause)
  m22 "The operator granted the custom role as planned." (Codex r8: status marker after the predicate, no comma)
  m23 "The documentation will explain the RFC, and the operator created the Phase A service accounts." (Codex r8)
  m24 "The operator will record the tape once the service accounts were created." (Codex r8: once resets)
  m25 "The operator must document the RFC and the service accounts were created by the operator." (r8 cousin)
  m26 "The docs must describe the workflow, and the operator creates the three Phase A service accounts." (Codex r9)
  m27 "The plan must document the workflow, and the operator makes every binding." (Codex r9)
  m28 "As planned the operator created the Phase A service accounts." (Codex r9: status as manner)
  m29 same as m26 with a 15-token subject (r9: the eight-token FINITE_PAST ceiling is gone)
  m30 "The tape will be recorded, and Codex verified that the operator granted the custom role." (r9 cousin)
  m31 "The docs must say that the operator created the three Phase A service accounts." (Codex r10: subordinate)
  m32 "The docs must be updated after service accounts were created." (Codex r10: temporal adjunct clause)
  m33 "Check 6 denied the request with PERMISSION_DENIED." (Codex r10: the generator produced "denyed")
  m34 "The operator grants temporary Phase A roles." (Codex r10: present tense with a modifier before the object)
  m35 "The operator will create the service accounts and revoked the custom role." (Kimi r10: verb-initial finite past)
  m36 "The sync writer must validate the bundle and committed it on tape." (Kimi r10)
  m37 "The plan must document the workflow, and okf-setup created the service accounts." (r10 cousin: identifier subject)
  m38 "In the demo project the operator created the service accounts." (r10 cousin: leading adjunct)
  m39 "The setup job has run on tape." (r10 cousin: ambiguous participle, finite only after an auxiliary)
  m40 "The docs must explain how the operator created the Phase A service accounts." (Codex/Kimi r11: wh-complement)
  m41 "The docs must report the operator created the Phase A service accounts." (Codex r11: null complement)
  m42 "The operator will record the tape once Phase A has been executed." (Codex r11: temporal boundary)
  m43 "The operators grant temporary Phase A roles." (Codex r11: finite base-present with a plural subject)
  m44 "The operator grants very narrowly scoped temporary Phase A roles." (Codex r11: no modifier ceiling)
  m45 "The tape will show how the operator created the service accounts." (Kimi r11)
  m46 / m47 why- and what-complements (r11 cousins)
  m48 "The docs must report okf-setup created the service accounts." (Codex r12: null complement, identifier subject)
  m49 "The docs must report service accounts were created." (Codex r12: bare plural subject)
  m50 "The docs must explain why all IAM calls succeeded on tape." (Codex r12: factive why over a phrase predicate)
  m51 "The planned service account was created." (Codex r12: status modifies the subject, not the predicate)
  m52 / m53 "grants narrow Phase A roles" / "The operators grant new Phase A roles." (Codex r12: plain adjectives)
  m54 "The docs must report the operators grant temporary Phase A roles." (Codex r12: embedded base-present)
  m55 the same claim with the subject written as inline code (r12 cousin)

Positive controls p1-p9 append honest RFC-only prose (shared modal + coordinated participle, "that" as a determiner,
"grants" as a noun, bare-infinitive coordination, the proper noun "Run") and must leave the checker at exit 0.

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


def m7(d):
    # Codex r5: active past + bare "Phase A" (creates? did not match created)
    p = d / "ARCHITECTURE.md"
    p.write_text(p.read_text("utf-8") + "\n\nThe operator created the three Phase A service accounts.\n", "utf-8")


def m8(d):
    # Codex r5: trailing qualifier in the same sentence must not reach back over the executed clause
    p = d / "spec.md"
    p.write_text(p.read_text("utf-8") + "\n\nEvery binding was recorded on tape, while future documentation is planned.\n", "utf-8")


def m9(d):
    # Codex r5: a qualifier in the NEXT list item / paragraph must not cover the previous block
    p = d / "plan.md"
    p.write_text(p.read_text("utf-8") + "\n\n- All seven negative checks returned PERMISSION_DENIED on tape.\n- Future work: the rest of Phase A is planned.\n\nThe operator has revoked every okf-setup role.\n\nThis is RFC text only.\n", "utf-8")


def m10(d):
    # Codex r5: LF → CRLF on the SQL file only; read_text() would hide it, read_bytes() must not
    sql = d / "sql" / "sessions_summary.sql"
    sql.write_bytes(sql.read_bytes().replace(b"\n", b"\r\n"))


def m11(d):
    # Codex r5: comment smuggling — unrelated constant SELECT with every required token only inside comments,
    # SQL file and provenance changed together with recomputed hashes
    sql = d / "sql" / "sessions_summary.sql"
    prov_p = d / "live" / "provenance_sessions_summary.json"
    prov = json.loads(prov_p.read_text("utf-8"))
    q = ("-- FROM `test-project-0728-467323.okf_rfc_demo.agent_events` COUNT(*) TOOL_COMPLETED GROUP BY 1, 2\n"
         "-- session_id agent rows_in_table tool_completed t0 t1\n"
         "SELECT 'x' AS session_id, 'y' AS agent, 1 AS rows_in_table, 0 AS tool_completed, 1 AS t0, 2 AS t1;\n")
    sql.write_text(q, "utf-8")
    prov["executed_query"] = q
    prov["sql_file_sha256_raw"] = prov["executed_query_sha256_raw"] = sha(q)
    prov_p.write_text(json.dumps(prov, indent=1), "utf-8")


def _append(rel, text):
    def fn(d):
        p = d / rel
        p.write_text(p.read_text("utf-8") + "\n\n" + text + "\n", "utf-8")
    return fn


# Codex r6: bare "No" latched forward over ", and …"; 'made' missing from the verb list; "_" stripping broke PERMISSION_DENIED
m12 = _append("ARCHITECTURE.md", "No DML touched agent_events, and the three Phase A service accounts were created.")
m13 = _append("spec.md", "The operator made every Phase A binding.")
m14 = _append("plan.md", "Check 6 returned PERMISSION_DENIED.")
m15 = _append("CUSTOMER_STORIES.md", "It is not a secret that the denials were proved on tape.")
m16 = _append("intent.md", "Without a tape, the operator created the service accounts.")
m17 = _append("README.md", "THE OPERATOR GRANTED THE CUSTOM ROLE okfCatalogSearch AT PROJECT LEVEL.")

# Codex r7: modal after the verb, 'then' scope reset, negation bound to its own predicate
m18 = _append("ARCHITECTURE.md", "The operator created the service accounts as expected.")
m19 = _append("spec.md", "Future documentation is planned, then the operator created the three service accounts.")
m20 = _append("plan.md", "The service account was not created after the operator granted the custom role.")
m21 = _append("CUSTOMER_STORIES.md", "The operator granted the custom role, as planned.")

# Codex r8: status after the predicate without a comma; finite new claim after ", and"; 'once' reset
m22 = _append("ARCHITECTURE.md", "The operator granted the custom role as planned.")
m23 = _append("spec.md", "The documentation will explain the RFC, and the operator created the Phase A service accounts.")
m24 = _append("plan.md", "The operator will record the tape once the service accounts were created.")
m25 = _append("intent.md", "The operator must document the RFC and the service accounts were created by the operator.")

# Codex r9: simple-present finite claims after coordination; status token that describes manner, not deferral; no token ceiling
m26 = _append("ARCHITECTURE.md", "The docs must describe the workflow, and the operator creates the three Phase A service accounts.")
m27 = _append("spec.md", "The plan must document the workflow, and the operator makes every binding.")
m28 = _append("plan.md", "As planned the operator created the Phase A service accounts.")
m29 = _append("intent.md", "The docs must describe the workflow, and the operator responsible for the Phase A bootstrap in the demo project on 2026-09-03 created the three service accounts.")
m30 = _append("CUSTOMER_STORIES.md", "The tape will be recorded, and Codex verified that the operator granted the custom role.")

# Codex r10: subordinate clause, temporal adjunct, past/present inflection. Kimi r10: verb-initial finite coordination.
m31 = _append("ARCHITECTURE.md", "The docs must say that the operator created the three Phase A service accounts.")
m32 = _append("spec.md", "The docs must be updated after service accounts were created.")
m33 = _append("plan.md", "Check 6 denied the request with PERMISSION_DENIED.")
m34 = _append("intent.md", "The operator grants temporary Phase A roles.")
m35 = _append("CUSTOMER_STORIES.md", "The operator will create the service accounts and revoked the custom role.")
m36 = _append("README.md", "The sync writer must validate the bundle and committed it on tape.")
m37 = _append("ARCHITECTURE.md", "The plan must document the workflow, and okf-setup created the service accounts.")
m38 = _append("spec.md", "In the demo project the operator created the service accounts.")
m39 = _append("plan.md", "The setup job has run on tape.")

# Codex r11: wh-complement, null complement, unconditional temporal boundary, finite base-present, no modifier ceiling.
# Kimi r11: how / why complementizers.
m40 = _append("ARCHITECTURE.md", "The docs must explain how the operator created the Phase A service accounts.")
m41 = _append("spec.md", "The docs must report the operator created the Phase A service accounts.")
m42 = _append("plan.md", "The operator will record the tape once Phase A has been executed.")
m43 = _append("intent.md", "The operators grant temporary Phase A roles.")
m44 = _append("CUSTOMER_STORIES.md", "The operator grants very narrowly scoped temporary Phase A roles.")
m45 = _append("README.md", "The tape will show how the operator created the service accounts.")
m46 = _append("ARCHITECTURE.md", "The docs must explain why the operator granted the custom role.")
m47 = _append("spec.md", "The report must record what the operator revoked on tape.")

# Positive controls (Codex r11 #3): honest RFC-only prose that must NOT be flagged. Appending any of these to a clean
# copy must leave the checker at exit 0; a fail here means the guard has started rejecting truthful future-tense text.
POSITIVE_CONTROLS = [
    ("p1 shared modal + coordinated participle", _append("ARCHITECTURE.md", "Every Phase A role must be created and granted on tape.")),
    ("p2 'that' as a determiner, not a complementizer", _append("spec.md", "The operator must record that Phase A binding on tape.")),
    ("p3 'grants' as a noun", _append("plan.md", "BigQuery grants use the table-level IAM policy for the custom role.")),
    ("p4 bare-infinitive coordination", _append("intent.md", "The operator will create the service accounts and revoke the custom role.")),
    ("p5 proper noun 'Run' and infinitive after a modal", _append("README.md", "The Cloud Run Job will run as the sync writer.")),
    ("p6 noun + participle ('The table grant named the custom role.')", _append("ARCHITECTURE.md", "The table grant named the custom role.")),
    ("p7 non-factive complement ('verify whether … were created')", _append("spec.md", "The operator must verify whether the service accounts were created.")),
    ("p8 prepositional 'after another', not a temporal clause", _append("plan.md", "The operator must create one service account after another and record every binding on tape.")),
    ("p9 noun 'grant' with a to-complement", _append("intent.md", "The custom role limits the project grant to one permission.")),
]

# Codex r12: null complements with arbitrary subjects, factive "why" over a phrase predicate, status modifying the
# subject, plain adjectives before the object, embedded base-present under an earlier modal.
m48 = _append("ARCHITECTURE.md", "The docs must report okf-setup created the service accounts.")
m49 = _append("spec.md", "The docs must report service accounts were created.")
m50 = _append("plan.md", "The docs must explain why all IAM calls succeeded on tape.")
m51 = _append("intent.md", "The planned service account was created.")
m52 = _append("CUSTOMER_STORIES.md", "The operator grants narrow Phase A roles.")
m53 = _append("README.md", "The operators grant new Phase A roles.")
m54 = _append("ARCHITECTURE.md", "The docs must report the operators grant temporary Phase A roles.")
m55 = _append("spec.md", "The docs must report `okf-setup` created the service accounts.")

MUTATIONS = [("m1 executed-language with bare Phase A", m1), ("m2 passive-past SA claims in plan.md", m2),
             ("m3 quoted-literal SQL collision", m3), ("m4 unrelated GROUP BY 1, 2 query", m4),
             ("m5 summary job missing from inventory", m5), ("m6 prior label regressed to seeded", m6),
             ("m7 active-past 'created the three Phase A service accounts'", m7),
             ("m8 trailing qualifier after executed clause", m8),
             ("m9 qualifier in next list item / paragraph", m9),
             ("m10 CRLF rewrite of the SQL file only", m10),
             ("m11 comment-smuggled tokens around a constant SELECT", m11),
             ("m12 bare 'No' in an earlier clause, SA creation in the next", m12),
             ("m13 'made every Phase A binding'", m13),
             ("m14 'Check 6 returned PERMISSION_DENIED' (identifier underscore)", m14),
             ("m15 unbound negation 'not a secret that … were proved'", m15),
             ("m16 'Without a tape,' negation in another clause", m16),
             ("m17 upper-case executed claim", m17),
             ("m18 'created the service accounts as expected' (modal after verb)", m18),
             ("m19 'is planned, then the operator created …' (then resets scope)", m19),
             ("m20 'was not created after the operator granted …' (negation bound to its own predicate)", m20),
             ("m21 'granted the custom role, as planned.' (trailing status in another clause)", m21),
             ("m22 'granted the custom role as planned.' (status after the predicate, same clause)", m22),
             ("m23 'will explain the RFC, and the operator created …' (finite claim after coordination)", m23),
             ("m24 'will record the tape once the service accounts were created.' (once resets)", m24),
             ("m25 'must document … and the service accounts were created …' (finite passive after and)", m25),
             ("m26 'must describe …, and the operator creates the three Phase A service accounts' (simple present)", m26),
             ("m27 'must document …, and the operator makes every binding' (simple present)", m27),
             ("m28 'As planned the operator created …' (status describes manner)", m28),
             ("m29 long subject (>8 tokens) after ', and' (no token ceiling)", m29),
             ("m30 proper-noun subject 'Codex verified that the operator granted …'", m30),
             ("m31 subordinate 'must say that the operator created …' (Codex r10)", m31),
             ("m32 temporal adjunct 'must be updated after service accounts were created' (Codex r10)", m32),
             ("m33 'Check 6 denied the request with PERMISSION_DENIED' (past inflection)", m33),
             ("m34 'grants temporary Phase A roles' (present, modifier before object)", m34),
             ("m35 'will create … and revoked the custom role' (Kimi r10: verb-initial finite past)", m35),
             ("m36 'must validate … and committed it on tape' (Kimi r10)", m36),
             ("m37 identifier subject 'and okf-setup created the service accounts'", m37),
             ("m38 leading adjunct 'In the demo project the operator created …'", m38),
             ("m39 'The setup job has run on tape.' (ambiguous participle after an auxiliary)", m39),
             ("m40 'must explain how the operator created …' (Codex/Kimi r11: wh-complement)", m40),
             ("m41 'must report the operator created …' (Codex r11: null complement)", m41),
             ("m42 'will record the tape once Phase A has been executed' (Codex r11: temporal)", m42),
             ("m43 'The operators grant temporary Phase A roles.' (finite base-present)", m43),
             ("m44 'grants very narrowly scoped temporary Phase A roles' (no modifier ceiling)", m44),
             ("m45 'The tape will show how the operator created …' (Kimi r11)", m45),
             ("m46 'must explain why the operator granted …' (r11 cousin: why)", m46),
             ("m47 'must record what the operator revoked on tape' (r11 cousin: what)", m47),
             ("m48 'must report okf-setup created …' (Codex r12: identifier subject, null complement)", m48),
             ("m49 'must report service accounts were created' (Codex r12: bare plural subject)", m49),
             ("m50 'must explain why all IAM calls succeeded on tape' (Codex r12: factive why)", m50),
             ("m51 'The planned service account was created.' (Codex r12: status modifies the subject)", m51),
             ("m52 'grants narrow Phase A roles' (Codex r12: plain adjective)", m52),
             ("m53 'The operators grant new Phase A roles.' (Codex r12: base-present)", m53),
             ("m54 'must report the operators grant temporary Phase A roles' (Codex r12: embedded)", m54),
             ("m55 subject written as inline code (r12 cousin)", m55)]

bad = []
with tempfile.TemporaryDirectory() as tmp:
    clean = make_copy(tmp)
    rc, out = run_checker(clean)
    print(("OK   " if rc == 0 else "FAIL ") + "clean copy passes (exit %d)" % rc)
    if rc != 0:
        bad.append("clean")
        print(re.sub(r"(?m)^OK .*\n", "", out)[-1500:])
for name, fn in POSITIVE_CONTROLS:
    with tempfile.TemporaryDirectory() as tmp:
        d = make_copy(tmp)
        fn(d)
        rc, out = run_checker(d)
        clean = rc == 0
        print(("OK   " if clean else "FAIL ") + "%s → checker exit %d (%s)" % (name, rc, "stays clean" if clean else "FALSE POSITIVE"))
        if not clean:
            bad.append(name)
            print("      " + "\n      ".join([l for l in out.split("\n") if l.startswith("FAIL")][:3]))
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
