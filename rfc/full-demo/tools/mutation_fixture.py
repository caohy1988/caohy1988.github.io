#!/usr/bin/env python3
"""Negative fixtures for check_full_demo.py (stdlib only).

Copies rfc/full-demo/ (and the two sibling files the checker reads: rfc/index.html and
rfc/demo/live/observe/live_identities.json) into a temp directory, applies one mutation at a time,
runs the checker on the copy, and requires a NON-ZERO exit for every mutation and a ZERO exit for
the unmodified copy.

Since round 20 the honesty gate is the audited claim register (tools/audited_claims.tsv), so the
mechanism behind most of these is the same one: prose that names a Phase A artefact and is not
registered fails, whatever words it uses. The historical entries are kept because each must still
fail, and because together they record what nineteen rounds of review actually asked for. The
positive controls append honest prose AND its register row, which is the authoring workflow the
register defines; appending prose alone is precisely what the gate must reject.

Each mutation reproduces a hole a reviewer found:

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
  m56 "The docs must explain the RFC and record that the operator created the service accounts." (Codex r13)
  m57 "No one realizes the operator created the service accounts." (Codex r13: negation across a second subject)
  m58 / m59 "Check 6 returns PERMISSION_DENIED." / "All seven positive checks returned OK." (Codex r13: return lemma)
  m60 / m61 "grants narrowly scoped …" / "Both grant temporary Phase A roles." (Codex r13: -ly adverb, quantifier)
  m62 "The operator granted the `custom role` at project scope." (Codex r13: multiword inline code kept readable)
  m63 "The docs must explain why an operator audited the Phase A service accounts on tape." (Codex r14)
  m64 "The docs must explain the RFC and record the operator succeeded on tape." (Codex r14)
  m65 "No reviewer realized okf-setup created the service accounts." (Codex r14: negation across a clause)
  m66 / m67 "grants access to the custom role" / "All positive checks return success." (Codex r14: bare-noun objects)
  m68 twelve modifiers before "Phase A roles" (Codex r14: the 12-modifier scan ceiling is gone)
  m69 "granted the `custom role (okfCatalogSearch)` at project scope." (Codex r14: punctuation in inline code)
  m70 a claim in an app.js string literal under a "Future" comment (Codex r14: real source boundaries)
  m71 "The docs must explain the operator audited the bindings on tape." (Kimi r15: null complement, unlisted -ed verb)
  m72 / m73 "must report operators were on tape" / "The planned operator was on tape." (Codex r15: phrase claims)
  m74 / m75 unlisted present ("reviewers audit …") and irregular past ("No reviewer knew …") (Codex r15)
  m76 / m77 "Operators grant temporary Phase A roles." / "okf-setup returns PERMISSION_DENIED." (Codex r15: subjects)
  m78 inline code with an equals sign keeps its object (Codex r15)
  m79 a claim split across concatenated literals, and a claim wrapped in inline HTML (Codex r15)
  m80 a punctuation-free comment beside a dishonest literal (Codex r15)
  m81 "The docs must explain the operator quietly audited the bindings on tape." (Kimi r16: adverb between subject/verb)
  m82 / m83 an adverb before the auxiliary and inside a negation span (Codex r16)
  m84 "The planned operator spoke on tape." (Codex r16: irregular verb in a bare subject+verb span)
  m85 / m86 ", and operators grant …" / ", and operators routinely record …" (Codex r16: coordinated bare subjects)
  m87 a claim split across a one-word concatenated literal (Codex r16)
  m88 a regex literal holding a quote must not desynchronise the lexer (Codex r16)
  m89 a \\u escape is decoded, so the claim it spells is visible (Codex r16)
  m90 "The docs must report the operator quietly spoke on tape." (Codex r17: irregular verb after a reporting head)
  m91 "throw /'/" before a dishonest literal must not desynchronise the lexer (Codex r17)
  m92 an escaped line continuation inside a claim is joined, not lost (Codex r17)
  m93 a hidden span cannot qualify the claim the reader actually sees (Codex r17)
  m94 "The docs must report the operator spoke softly on tape." (Kimi r18: post-verbal adverb)
  m95 "… the experienced operator quietly spoke on tape." (Codex r18: adjective inside the subject phrase)
  m96 "The operator grants narrowly constrained Phase A roles." (Codex r18: attributive participle after an adverb)
  m97 "holder.throw / '/' / 2" is property access and division, not a regex (Codex r18)
  m98 a regex after a control-flow head does not desynchronise the lexer (Codex r18)
  m99 "style = 'display:none'" hides its content whatever the spacing (Codex r18)
  m100 "data-hidden='false'" is a visible element and its claim is read (Codex r18)
  m101 "The docs must report the operator quit on tape." (Codex r19: invariant irregular past)
  m102 "… and most record every binding on tape." (Codex r19: quantifier pronoun subject)
  m103 "holder.if(ready) / '/' / 2" is member access and division, not a regex (Codex r19)
  m104 a regex after a nested condition ("if ((ready)) /'/") does not desynchronise (Codex r19)
  m105 "display:none; display:inline" renders, because the last declaration wins (Codex r19)
  m106 unquoted "style=display:none" hides its element too (Codex r19)
  m107 a nested same-tag hidden element is removed whole, not up to the inner tag (Codex r19)
  m108 "title='hidden'" is an attribute value, not the hidden attribute (Codex r19)

Positive controls p1-p39 append honest RFC-only prose (shared modal + coordinated participle, "that" as a determiner,
"grants" as a noun, bare-infinitive coordination, the proper noun "Run") and must leave the checker at exit 0.

Usage: python3 rfc/full-demo/tools/mutation_fixture.py   (exit 0 when every fixture behaves)
"""
import hashlib
import html
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


def _append_js(rel, code):
    def fn(d):
        p = d / rel
        p.write_text(p.read_text("utf-8") + "\n" + code + "\n", "utf-8")
    return fn


def _append(rel, text):
    def fn(d):
        p = d / rel
        p.write_text(p.read_text("utf-8") + "\n\n" + text + "\n", "utf-8")
    return fn


# The register's own sentence splitter and readers, loaded out of the checker rather than copied, so this fixture
# cannot drift from the gate it is testing.
def _gate():
    src = (HERE / "check_full_demo.py").read_text("utf-8")
    seg = (src[src.index("PHASE_A_OBJECT = re.compile"):src.index("# ---- the register:")]
           + src[src.index("def regulated_sentences("):src.index("def load_register(")])
    g = {"re": re, "json": json, "html": html, "DEMO": DEMO}
    exec(seg, g)
    return g


GATE = _gate()


def _rows_for(rel, text, verdict, evidence):
    """The register rows the appended prose needs: one per regulated sentence, with the licence spans a PENDING row
    must carry. A sentence whose completion language has no qualifier before it cannot be registered PENDING at all,
    so a fixture that tries is a fixture error, not a silent pass."""
    rows = []
    for _, s in GATE["regulated_sentences"](text):
        licence = "-"
        if verdict == "PENDING":
            spans = GATE["derive_licences"](s)
            if spans is None:
                raise SystemExit("fixture error: %r cannot be registered PENDING" % s[:70])
            licence = "~".join(spans) or "-"
        rows.append("\t".join((verdict, rel, evidence, licence, s)))
    return rows


def _audit(d, rows):
    p = d / "tools" / "audited_claims.tsv"
    p.write_text(p.read_text("utf-8") + "".join(r + "\n" for r in rows), "utf-8")


def _append_audited(rel, text, verdict="PENDING", evidence="-"):
    """Append prose AND audit it. This is the authoring workflow INV-1 defines: adding a sentence that touches this
    project without adding its register row is exactly what the gate must reject, so a positive control does both."""
    def fn(d):
        p = d / rel
        p.write_text(p.read_text("utf-8") + "\n\n" + text + "\n", "utf-8")
        _audit(d, _rows_for(rel, text, verdict, evidence))
    return fn


def _append_audited_js(rel, code, verdict="PENDING", evidence="-"):
    def fn(d):
        p = d / rel
        p.write_text(p.read_text("utf-8") + "\n" + code + "\n", "utf-8")
        _audit(d, _rows_for(rel, GATE["extract_js_prose"](code), verdict, evidence))
    return fn


def _new_pinned_capture(d):
    """The authoring workflow INV-6 defines: a new pane fetches a new capture, and the capture is pinned."""
    rel = "live/beat7_new_capture.json"
    (d / rel).write_text('[{"note": "not yet run"}]\n', "utf-8")
    p = d / "app.js"
    p.write_text(p.read_text("utf-8").replace('matrix: "matrix.json"', 'extra: "' + rel + '", matrix: "matrix.json"', 1), "utf-8")
    _pin(d, rel)


def _append_audited_css(rel, css, verdict="PENDING", evidence="-"):
    def fn(d):
        p = d / rel
        p.write_text(p.read_text("utf-8") + "\n" + css + "\n", "utf-8")
        _audit(d, _rows_for(rel, GATE["extract_css_prose"](css), verdict, evidence))
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
    ("p1 shared modal + coordinated participle", _append_audited("ARCHITECTURE.md", "Every Phase A role must be created and granted on tape.")),
    ("p2 'that' as a determiner, not a complementizer", _append_audited("spec.md", "The operator must record that Phase A binding on tape.")),
    ("p3 'grants' as a noun", _append_audited("plan.md", "BigQuery grants use the table-level IAM policy for the custom role.")),
    ("p4 bare-infinitive coordination", _append_audited("intent.md", "The operator will create the service accounts and revoke the custom role.")),
    ("p5 proper noun 'Run' and infinitive after a modal", _append_audited("README.md", "The Cloud Run Job will run as the sync writer.")),
    ("p6 noun + participle ('The table grant named the custom role.')", _append_audited("ARCHITECTURE.md", "The table grant named the custom role.")),
    ("p7 non-factive complement ('verify whether … were created')", _append_audited("spec.md", "The operator must verify whether the service accounts were created.")),
    ("p8 prepositional 'after another', not a temporal clause", _append_audited("plan.md", "The operator must create one service account after another and record every binding on tape.")),
    ("p9 noun 'grant' with a to-complement", _append_audited("intent.md", "The custom role limits the project grant to one permission.")),
    ("p10 adverb between modal and verb ('must eventually create')", _append_audited("ARCHITECTURE.md", "The operator must eventually create the Phase A service accounts.")),
    ("p11 noun 'grants' with an unlisted predicate ('Project grants govern …')", _append_audited("spec.md", "Project grants govern access to the custom role.")),
    ("p12 determiner 'that' + attributive participle", _append_audited("plan.md", "The operator must record that scoped Phase A binding on tape.")),
    ("p13 modal reaching a coordinated head verb and its complement", _append_audited("intent.md", "The docs must explain the RFC and record every binding on tape.")),
    ("p14 honest denial with a Titlecase subject ('No Phase A service account was created.')", _append_audited("ARCHITECTURE.md", "No Phase A service account was created.")),
    ("p15 compound-noun subject with an unlisted verb ('Project grants govern …')", _append_audited("spec.md", "Project grants govern Phase A access to the custom role.")),
    ("p16 adverb before a coordinated continuation head ('and carefully record …')", _append_audited("plan.md", "The operator must create the service accounts and carefully record every binding on tape.")),
    ("p17 executable app.js code is not prose", _append_audited_js("app.js", "function r14Control() { return roles; }")),
    ("p18 honest app.js literal stays clean", _append_audited_js("app.js", 'var r14Ok = "The operator must create the Phase A service accounts.";')),
    ("p19 honest passive future ('The operator must be recorded on tape.')", _append_audited("ARCHITECTURE.md", "The operator must be recorded on tape.")),
    ("p20 modal over a coordinated head and its object phrase", _append_audited("spec.md", "The docs must explain the RFC and record the Phase A binding on tape.")),
    ("p21 attributive participle inside the object", _append_audited("plan.md", "The docs must explain the RFC and record the previously scoped Phase A binding on tape.")),
    ("p22 denial whose subject carries a prepositional phrase", _append_audited("intent.md", "No service account in the Phase A project was created.")),
    ("p23 determiner-headed compound noun with an unlisted verb", _append_audited("CUSTOMER_STORIES.md", "The project grants govern Phase A access to the custom role.")),
    ("p24 non-ly adverb before a coordinated continuation head", _append_audited("README.md", "The operator must create the service accounts and always record every binding on tape.")),
    ("p25 three adverbs before a coordinated continuation head", _append_audited("ARCHITECTURE.md", "The operator must create the service accounts and very carefully always record every binding on tape.")),
    ("p26 compound noun with an unlisted governance verb ('Project grants constrain …')", _append_audited("spec.md", "Project grants constrain Phase A access to the custom role.")),
    ("p27 unrelated neighbouring literals are not merged", _append_audited_js("app.js", 'var r16e = "This is future work.";\nvar r16f = "The tape will show every binding.";')),
    ("p28 non-ly adverb 'often' before a continuation head", _append_audited("spec.md", "The operator must create the service accounts and often record every binding on tape.")),
    ("p29 non-ly adverb 'sometimes' before a continuation head", _append_audited("plan.md", "The operator must create the service accounts and sometimes record every binding on tape.")),
    ("p30 adverb between a noun and its governance verb", _append_audited("intent.md", "Project grants narrowly constrain Phase A access to the custom role.")),
    ("p31 object noun phrase ending in a noun ('must record the custom role on tape')", _append_audited("ARCHITECTURE.md", "The operator must record the custom role on tape.")),
    ("p32 'more carefully' before a continuation head", _append_audited("spec.md", "The operator must create the service accounts and more carefully record every binding on tape.")),
    ("p33 'often' between a noun and its governance verb", _append_audited("plan.md", "Project grants often constrain Phase A access to the custom role.")),
    ("p34 compound noun ending in an invariant irregular ('the Phase A cache hit')", _append_audited("ARCHITECTURE.md", "The operator must record the Phase A cache hit on tape.")),
    ("p35 'must often record' keeps the modal's reach", _append_audited("spec.md", "The operator must often record every binding on tape.")),
    ("p36 reduced relative ('grants narrowly constrained by policy')", _append_audited("plan.md", "Project grants narrowly constrained by policy are Phase A requirements.")),
    ("p37 the same reduced relative under a modal", _append_audited("intent.md", "Future documentation must list project grants narrowly constrained by policy.")),
    ("p38 an honest literal after a nested-condition regex", _append_audited_js("app.js", "var r19p = function () { if ((ready)) /'/.test(x); };\nvar r19q = 'Every binding is a future requirement.';")),
    ("p39 a hidden element with nested inline markup is dropped whole", _append_audited_js("app.js", 'var r19r = "<span hidden>The operator <em>created</em> the Phase A service accounts.</span>";')),
    ("p40 comparative adverb between a modal and its verb (Codex r20)", _append_audited("ARCHITECTURE.md", "The operator must better record every binding on tape.")),
    ("p41 'much better record' after a coordinated modal (Codex r20)", _append_audited("spec.md", "The operator must create the service accounts and much better record every binding on tape.")),
    ("p42 an irregular participle modifying a noun (Codex r20)", _append_audited("plan.md", "Project grants widely known to reviewers are Phase A requirements.")),
    ("p43 an adverb between a participle and its by-phrase (Codex r20)", _append_audited("intent.md", "Project grants narrowly constrained only by policy are Phase A requirements.")),
    ("p44 a compound object ending in a noun (Codex r20)", _append_audited("README.md", "The operator must record the service account binding on tape.")),
    ("p45 an audited CAPTURED row with its evidence", _append_audited("live/README.md", "The summary query ran once as the operator and its job id is on record.", "CAPTURED", "live/bq_jobs_identity.json")),
    ("p46 aria-hidden prose is visible, and audited like any other (Codex r21)", _append_audited_js("app.js", 'var r21p = "<span aria-hidden=\'true\'>Every Phase A binding must be recorded on tape.</span>";')),
    ("p47 audited generated content in the stylesheet (Codex r21)", _append_audited_css("styles.css", 'body::after { content: "Phase A must still be recorded on tape."; }')),
    ("p48 a CAPTURED row citing two evidence files (Codex r21)", _append_audited("live/README.md", "The attribution bands were read once as the operator.", "CAPTURED", "live/beat6_attribution.json,live/bq_jobs_identity.json")),
    ("p49 audited generated content with a semicolon inside it (Codex r22)", _append_audited_css("styles.css", 'body::after { content: "Note; Phase A must still be recorded on tape."; }')),
    ("p50 a negation on the subject of a passive is a licence frame (Codex r22)", _append_audited("spec.md", "No Phase A service account was created for this capture.")),
    ("p51 a modal over a coordinated verb phrase is one frame (Codex r22)", _append_audited("ARCHITECTURE.md", "Every Phase A role must be created and granted on tape.")),
    ("p52 a negation on a passive subject with a prepositional modifier (Codex r23)", _append_audited("spec.md", "No service account in the Phase A project was created.")),
    ("p53 audited generated content behind a property comment (Codex r23)", _append_audited_css("styles.css", 'body::after { content/**/: "Phase A must still be recorded on tape."; }')),
    ("p54 a new capture, fetched by the viewer and pinned", _new_pinned_capture),
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

# Codex r13: per-predicate inheritance and negation, restored "return", -ly / quantifier noun misclassification,
# multiword inline-code objects.
m56 = _append("ARCHITECTURE.md", "The docs must explain the RFC and record that the operator created the service accounts.")
m57 = _append("spec.md", "No one realizes the operator created the service accounts.")
m58 = _append("plan.md", "Check 6 returns PERMISSION_DENIED.")
m59 = _append("intent.md", "All seven positive checks returned OK.")
m60 = _append("CUSTOMER_STORIES.md", "The operator grants narrowly scoped temporary Phase A roles.")
m61 = _append("README.md", "Both grant temporary Phase A roles.")
m62 = _append("ARCHITECTURE.md", "The operator granted the `custom role` at project scope.")

# Codex r14: unlisted finite verbs in complements, embedded clauses under an inherited modal, negation across an
# embedded clause, bare-noun objects, no modifier ceiling, inline code with punctuation, and real app.js boundaries.
MODS = " ".join(["alpha", "beta", "gamma", "delta", "epsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu"])
m63 = _append("ARCHITECTURE.md", "The docs must explain why an operator audited the Phase A service accounts on tape.")
m64 = _append("spec.md", "The docs must explain the RFC and record the operator succeeded on tape.")
m65 = _append("plan.md", "No reviewer realized okf-setup created the service accounts.")
m66 = _append("intent.md", "The operator grants access to the custom role.")
m67 = _append("CUSTOMER_STORIES.md", "All positive checks return success.")
m68 = _append("README.md", "The operator grants " + MODS + " Phase A roles.")
m69 = _append("ARCHITECTURE.md", "The operator granted the `custom role (okfCatalogSearch)` at project scope.")


def m70(d):
    """A claim inside an app.js string literal must be caught, and a "Future" comment above it must not qualify it."""
    p = d / "app.js"
    p.write_text(p.read_text("utf-8") + '\n// Future work is planned here.\nvar r14Claim = "The operator created the Phase A service accounts.";\n', "utf-8")


# Codex / Kimi r15: null-complement claims reached by a direct modal or status marker, unlisted present and irregular
# verbs, bare-plural and identifier subjects, inline code with an equals sign, and real JavaScript source shapes.
m71 = _append("ARCHITECTURE.md", "The docs must explain the operator audited the bindings on tape.")
m72 = _append("spec.md", "The docs must report operators were on tape.")
m73 = _append("plan.md", "The planned operator was on tape.")
m74 = _append("intent.md", "The docs must explain why reviewers audit the service accounts on tape.")
m75 = _append("CUSTOMER_STORIES.md", "No reviewer knew okf-setup created the service accounts.")
m76 = _append("README.md", "Operators grant temporary Phase A roles.")
m77 = _append("ARCHITECTURE.md", "okf-setup returns PERMISSION_DENIED.")
m78 = _append("spec.md", "The operator granted the `custom role = okfCatalogSearch` at project scope.")


def m79(d):
    """A claim split across concatenated string literals, with a code-only line between them, is still a claim; and a
    claim wrapped in inline HTML must survive tag removal."""
    p = d / "app.js"
    p.write_text(p.read_text("utf-8") +
                 '\nvar r15a = "The operator created " +\n  D.pad +\n  "the Phase A service accounts.";\n'
                 '\nvar r15b = "The service <strong>accounts</strong> were created for this capture.";\n', "utf-8")


def m80(d):
    """A punctuation-free comment must not qualify a claim in the literal next to it."""
    p = d / "app.js"
    p.write_text(p.read_text("utf-8") + '\n// Future work is planned here\nvar r15c = "All seven negative checks are on tape.";\n', "utf-8")


# Codex / Kimi r16: an adverb between subject and verb, coordinated bare subjects, and JavaScript source shapes that
# the hand lexer used to mis-read (concatenated one-word literals, a regex literal holding a quote, \u escapes).
m81 = _append("ARCHITECTURE.md", "The docs must explain the operator quietly audited the bindings on tape.")
m82 = _append("spec.md", "The docs must report operators definitely were on tape.")
m83 = _append("plan.md", "No reviewer clearly knew okf-setup created the service accounts.")
m84 = _append("intent.md", "The planned operator spoke on tape.")
m85 = _append("CUSTOMER_STORIES.md", "The docs must explain the RFC, and operators grant temporary Phase A roles.")
m86 = _append("README.md", "The docs must explain the RFC, and operators routinely record every binding on tape.")
m87 = _append_js("app.js", 'var r16a = "The operator " + "created" + " the Phase A service accounts.";')
m88 = _append_js("app.js", "var r16b = function () { return /'/; };\nvar r16c = 'The operator created the Phase A service accounts.';")
m89 = _append_js("app.js", 'var r16d = "The operator cr\\u0065ated the Phase A service accounts.";')

# Codex r17: an irregular verb after a reporting head, and three JavaScript / HTML shapes the lexer mis-read.
m90 = _append("ARCHITECTURE.md", "The docs must report the operator quietly spoke on tape.")
m91 = _append_js("app.js", "var r17a = function () { throw /'/; };\nvar r17b = 'The operator created the Phase A service accounts.';")
m92 = _append_js("app.js", 'var r17c = "The operator crea\\\nted the Phase A service accounts.";')
m93 = _append_js("app.js", 'var r17d = "The service <span hidden>not yet</span> accounts were created for this capture.";')

# Kimi / Codex r18: a post-verbal adverb after an intransitive verb, an adjective inside the subject phrase, an
# attributive participle after an adverb, and three JavaScript / HTML readings.
m94 = _append("ARCHITECTURE.md", "The docs must report the operator spoke softly on tape.")
m95 = _append("spec.md", "The docs must report the experienced operator quietly spoke on tape.")
m96 = _append("plan.md", "The operator grants narrowly constrained Phase A roles.")
m97 = _append_js("app.js", "var r18a = holder.throw / '/' / 2;\nvar r18b = 'The operator created the Phase A service accounts.';")
m98 = _append_js("app.js", "var r18c = function () { if (ready) /'/.test(x); };\nvar r18d = 'The operator created the Phase A service accounts.';")
m99 = _append_js("app.js", 'var r18e = "<span style = \'display:none\'>not yet</span> The service accounts were created for this capture.";')
m100 = _append_js("app.js", 'var r18f = "<span data-hidden=\'false\'>The operator created the Phase A service accounts.</span>";')

# Codex r19: an invariant irregular past, a quantifier pronoun subject, a member-access division, a nested control-flow
# condition, and four readings of what the browser actually renders.
m101 = _append("ARCHITECTURE.md", "The docs must report the operator quit on tape.")
m102 = _append("spec.md", "The operator must create the service accounts, and most record every binding on tape.")
m103 = _append_js("app.js", "var r19a = holder.if(ready) / '/' / 2;\nvar r19b = 'The operator created the Phase A service accounts.';")
m104 = _append_js("app.js", "var r19c = function () { if ((ready)) /'/.test(x); };\nvar r19d = 'The operator created the Phase A service accounts.';")
m105 = _append_js("app.js", 'var r19e = "<span style = \'display:none; display:inline\'>The operator created the Phase A service accounts.</span>";')
m106 = _append_js("app.js", 'var r19f = "<span style=display:none>not yet</span> The service accounts were created for this capture.";')
m107 = _append_js("app.js", 'var r19g = "<span hidden><span>deferred</span> not yet</span> The service accounts were created for this capture.";')
m108 = _append_js("app.js", 'var r19h = "<span title=\'hidden\'>The operator created the Phase A service accounts.</span>";')

# Codex r20. The gate is now the audited claim register, so prose that names a Phase A artefact and is not audited
# fails whatever its morphology (m109-m111); a falsified or inconsistent register row fails on its own terms
# (m112-m116); and the extraction readers stay load-bearing, because a claim they drop is never regulated at all
# (m117-m121).
m109 = _append("ARCHITECTURE.md", "The docs must report the operator froze on tape.")
m110 = _append("spec.md", "The docs must report the Phase A operator quit on tape.")
m111 = _append("plan.md", "The operator must record the service account binding on tape and the denials were proved.")
def m112(d):
    """A PENDING row that records no licence span at all leaves its completion language unbound."""
    p = d / "intent.md"
    p.write_text(p.read_text("utf-8") + "\n\nPhase A was executed; every binding call is made and recorded on tape.\n", "utf-8")
    _audit(d, ["PENDING\tintent.md\t-\t-\tPhase A was executed;",
               "PENDING\tintent.md\t-\t-\tevery binding call is made and recorded on tape."])
m113 = _append_audited("README.md", "The operator created the three Phase A service accounts.", "CAPTURED", "live/bq_jobs_identity.json")
m114 = _append_audited("CUSTOMER_STORIES.md", "The operator must create the three Phase A service accounts on tape.", "CAPTURED", "live/no_such_file.json")


def m115(d):
    """A register row for prose that is not in the copy: the register must audit what ships, not license what might."""
    _audit(d, ["PENDING\t-\tThe operator must create the three Phase A service accounts on tape."])


def m116(d):
    """Dropping a row leaves shipped prose unaudited."""
    p = d / "tools" / "audited_claims.tsv"
    lines = p.read_text("utf-8").split("\n")
    keep = [ln for ln in lines if not ln.startswith("CAPTURED\t")]
    assert len(keep) < len(lines)
    p.write_text("\n".join(keep), "utf-8")


m117 = _append_js("app.js", "var r20a = holder . if(ready) / '/' / 2;\nvar r20b = 'The operator created the Phase A service accounts.';")
m118 = _append_js("app.js", "var r20c = function () { if (((ready))) /'/.test(x); };\nvar r20d = 'The operator created the Phase A service accounts.';")
m119 = _append_js("app.js", "var r20e = function () { if (%s) /'/.test(x); };\nvar r20f = 'The operator created the Phase A service accounts.';" % " && ".join("flag%02d" % i for i in range(1, 26)))
m120 = _append_js("app.js", 'var r20g = "<span style=\'--x:display:none\'>The operator created the Phase A service accounts.</span>";')
m121 = _append_js("app.js", 'var r20h = "<span hidden><!-- <span> --></span> The operator created the Phase A service accounts.";')

# Codex r21. The regulation trigger is now four over-broad tests, three of them pure shape, so an artefact nobody
# listed is still regulated (m122-m125); a register row is bound to its own file, evidence and qualifier scope
# (m126-m129); and the readers stay load-bearing for postfix operators, aria-hidden and stylesheets (m130-m134).
m122 = _append("ARCHITECTURE.md", "The sync stamped okf-context-runtime and advanced deployment_heads.")
m123 = _append("spec.md", "The IAM bootstrap completed successfully.")
m124 = _append("plan.md", "`okf-context sync` committed successfully.")
m125 = _append("intent.md", "`BQ_COMMITTED` happened.")
m126 = _append("README.md", "Runtime tables were created and seeded by the operator, not yet by the Phase A service accounts.")
m127 = _append_audited("CUSTOMER_STORIES.md", "The operator ran every capture query for this page.", "CAPTURED", "live/../../index.html")
m128 = _append_audited("ARCHITECTURE.md", "The Phase A service accounts were created although no unrelated query was run.", "CAPTURED", "live/bq_jobs_identity.json")


def m129(d):
    """A licence span that does not open with a qualifier licenses nothing."""
    p = d / "spec.md"
    p.write_text(p.read_text("utf-8") + "\n\nThe operator created the service accounts as expected.\n", "utf-8")
    _audit(d, ["PENDING\tspec.md\t-\tthe operator created\tThe operator created the service accounts as expected."])


m130 = _append_js("app.js", "var r21a = 1; r21a++ / '/' / 2;\nvar r21b = 'The operator created the Phase A service accounts.';")
m131 = _append_js("app.js", "var r21c = 1; r21c-- / '/' / 2;\nvar r21d = 'The operator created the Phase A service accounts.';")
m132 = _append_js("app.js", 'var r21e = "<span aria-hidden=\'true\'>The operator created the Phase A service accounts.</span>";')
m133 = _append("styles.css", 'body::after { content: "The Phase A service accounts were created."; }')
m134 = _append("styles.css", '/* The operator created the Phase A service accounts. */')

# Codex r22. Coverage is total, so an ordinary claim about anything is regulated (m135-m136); a verdict is bound by a
# licence or disclaimer FRAME rather than by position (m137-m139); and the readers meet the copy the way a reader does
# — decoded JSON, decoded entities, quote-aware CSS that follows attr() (m140-m143).
m135 = _append("README.md", "The IAM bootstrap succeeded.")
m136 = _append("plan.md", "The sync finished successfully.")


def m137(d):
    """A licence that is not a frame licenses nothing: the negation belongs to another clause."""
    p = d / "spec.md"
    p.write_text(p.read_text("utf-8") + "\n\nNo reviewer knew okf-setup created the service accounts.\n", "utf-8")
    _audit(d, ["PENDING\tspec.md\t-\tNo reviewer knew okf-setup created\tNo reviewer knew okf-setup created the service accounts."])


def m138(d):
    """A CAPTURED row needs a disclaimer sitting ON the artefact, not a negation elsewhere in the sentence."""
    p = d / "ARCHITECTURE.md"
    p.write_text(p.read_text("utf-8") + "\n\nNo unrelated query ran, and the service accounts were created.\n", "utf-8")
    _audit(d, ["CAPTURED\tARCHITECTURE.md\tlive/bq_jobs_identity.json\t-\tNo unrelated query ran, and the service accounts were created."])


def m139(d):
    """NOT_PHASE_A is decided by naming, not distance, so padding the sentence buys nothing."""
    sent = "The Phase A service accounts in the isolated demonstration environment for later operator validation were created."
    p = d / "intent.md"
    p.write_text(p.read_text("utf-8") + "\n\n" + sent + "\n", "utf-8")
    _audit(d, ["NOT_PHASE_A\tintent.md\t-\t-\t" + sent])


m140 = _append("styles.css", 'body::after { content: "Note; The Phase A service accounts were created."; }')


def m141(d):
    """content: attr(x) prints the attribute onto the screen, where an HTML scan of tags would never see it."""
    idx = d / "index.html"
    idx.write_text(idx.read_text("utf-8").replace("<body>", '<body data-claim="The operator created the Phase A service accounts.">', 1), "utf-8")
    css = d / "styles.css"
    css.write_text(css.read_text("utf-8") + "\nbody::before { content: attr(data-claim); }\n", "utf-8")


def m142(d):
    """JSON source bytes are not what the viewer renders: \\u005f is an underscore on the screen."""
    p = d / "stories.json"
    raw = p.read_text("utf-8")
    marker = '"status": "'
    at = raw.index(marker) + len(marker)
    p.write_text(raw[:at] + 'BQ\\u005fCOMMITTED happened. ' + raw[at:], "utf-8")
    _audit(d, ["NOT_PHASE_A\tstories.json\t-\t-\tBQ\\u005fCOMMITTED happened."])


def m143(d):
    """HTML entities are decoded before the reader sees them, so the source spelling is not the audited sentence."""
    p = d / "index.html"
    p.write_text(p.read_text("utf-8").replace("</body>", "<p>BQ&#95;COMMITTED happened.</p></body>", 1), "utf-8")
    _audit(d, ["NOT_PHASE_A\tindex.html\t-\t-\tBQ&#95;COMMITTED happened."])


# Codex r23. Everything the viewer fetches is either audited copy or a byte pin (m144-m146); no verdict is reachable
# for a claim it does not fit (m147-m150); JSON is audited as esc() renders it (m151); and generated content is read
# the way a browser reads it (m152-m153).
def _pin(d, rel):
    """Re-pin a capture after an honest edit, the way the workflow expects."""
    p = d / "tools" / "live_manifest.tsv"
    lines = [ln for ln in p.read_text("utf-8").split("\n") if not ln.endswith("\t" + rel)]
    lines.append("%s\t%s" % (hashlib.sha256((d / rel).read_bytes()).hexdigest(), rel))
    p.write_text("\n".join(lines) + "\n", "utf-8")


def m144(d):
    """A claim written into a live capture the viewer renders on beat 6."""
    p = d / "live" / "beat6_demo_evidence.json"
    rows = json.loads(p.read_text("utf-8"))
    rows[0]["note"] = "The Phase A service accounts were created. " + str(rows[0].get("note", ""))
    p.write_text(json.dumps(rows, indent=1), "utf-8")


def m145(d):
    """The same, in a session capture beat 1 renders."""
    p = d / "live" / "session_f21ee192.json"
    rows = json.loads(p.read_text("utf-8"))
    rows[0]["text_summary"] = "The Phase A service accounts were created."
    p.write_text(json.dumps(rows, indent=1), "utf-8")


def m146(d):
    """A new pane fetching a file that is neither audited copy nor a pinned capture."""
    (d / "live" / "beat7_new_capture.json").write_text('[{"note": "The Phase A service accounts were created."}]\n', "utf-8")
    p = d / "app.js"
    p.write_text(p.read_text("utf-8").replace('matrix: "matrix.json"', 'extra: "live/beat7_new_capture.json", matrix: "matrix.json"', 1), "utf-8")


def _register_claim(d, verdict, evidence, licence, sentence, rel="README.md"):
    p = d / rel
    p.write_text(p.read_text("utf-8") + "\n\n" + sentence + "\n", "utf-8")
    _audit(d, ["\t".join((verdict, rel, evidence, licence, sentence))])


def m147(d):
    _register_claim(d, "CAPTURED", "live/bq_jobs_identity.json", "-", "The IAM bootstrap succeeded.")


def m148(d):
    _register_claim(d, "NOT_PHASE_A", "-", "-", "The IAM bootstrap succeeded.")


def m149(d):
    _register_claim(d, "PENDING", "-", "-", "The IAM bootstrap succeeded.")


def m150(d):
    sent = "No reviewer knew the Phase A service accounts were created."
    _register_claim(d, "PENDING", "-", sent[:-1], sent)


def m151(d):
    """A story status that renders as literal text, because app.js escapes it before innerHTML."""
    p = d / "stories.json"
    raw = p.read_text("utf-8")
    marker = '"status": "'
    at = raw.index(marker) + len(marker)
    p.write_text(raw[:at] + '<span hidden>The Phase A service accounts were created.</span> ' + raw[at:], "utf-8")


m152 = _append("styles.css", 'body::after { content/**/: "The Phase A service accounts were created."; }')


def m153(d):
    """attr() prints an unquoted attribute onto the screen; an HTML scan of tags never sees it."""
    idx = d / "index.html"
    idx.write_text(idx.read_text("utf-8").replace("<body>", "<body data-claim=Phase-A-service-accounts-were-created>", 1), "utf-8")
    css = d / "styles.css"
    css.write_text(css.read_text("utf-8") + "\nbody::before { content: attr(data-claim); }\n", "utf-8")


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
             ("m55 subject written as inline code (r12 cousin)", m55),
             ("m56 'must explain the RFC and record that the operator created …' (Codex r13: per-predicate inheritance)", m56),
             ("m57 'No one realizes the operator created …' (Codex r13: negation across a second subject)", m57),
             ("m58 'Check 6 returns PERMISSION_DENIED.' (Codex r13: restored return lemma)", m58),
             ("m59 'All seven positive checks returned OK.' (Codex r13: past returned)", m59),
             ("m60 'grants narrowly scoped temporary Phase A roles' (Codex r13: -ly adverb)", m60),
             ("m61 'Both grant temporary Phase A roles.' (Codex r13: quantifier subject)", m61),
             ("m62 'granted the `custom role` at project scope.' (Codex r13: multiword inline code)", m62),
             ("m63 'must explain why an operator audited …' (Codex r14: unlisted finite in a complement)", m63),
             ("m64 'and record the operator succeeded on tape' (Codex r14: embedded clause under inheritance)", m64),
             ("m65 'No reviewer realized okf-setup created …' (Codex r14: negation across a clause)", m65),
             ("m66 'grants access to the custom role' (Codex r14: bare-noun object)", m66),
             ("m67 'All positive checks return success.' (Codex r14: base-present, bare object)", m67),
             ("m68 twelve modifiers before 'Phase A roles' (Codex r14: no scan ceiling)", m68),
             ("m69 inline code with punctuation keeps the object (Codex r14)", m69),
             ("m70 claim in an app.js string literal, 'Future' comment above it (Codex r14)", m70),
             ("m71 'must explain the operator audited …' (Kimi r15: null complement, unlisted -ed)", m71),
             ("m72 'must report operators were on tape' (Codex r15: null-complement phrase claim)", m72),
             ("m73 'The planned operator was on tape.' (Codex r15: status on the subject)", m73),
             ("m74 'why reviewers audit the service accounts' (Codex r15: unlisted present verb)", m74),
             ("m75 'No reviewer knew okf-setup created …' (Codex r15: irregular past)", m75),
             ("m76 'Operators grant temporary Phase A roles.' (Codex r15: bare plural subject)", m76),
             ("m77 'okf-setup returns PERMISSION_DENIED.' (Codex r15: identifier subject)", m77),
             ("m78 inline code with an equals sign keeps the object (Codex r15)", m78),
             ("m79 claim split across literals; claim inside inline HTML (Codex r15)", m79),
             ("m80 punctuation-free comment beside a dishonest literal (Codex r15)", m80),
             ("m81 'the operator quietly audited …' (Kimi r16: adverb between subject and verb)", m81),
             ("m82 'operators definitely were on tape' (Codex r16: adverb before the auxiliary)", m82),
             ("m83 'No reviewer clearly knew okf-setup created …' (Codex r16)", m83),
             ("m84 'The planned operator spoke on tape.' (Codex r16: irregular verb)", m84),
             ("m85 ', and operators grant temporary Phase A roles' (Codex r16: coordinated bare subject)", m85),
             ("m86 ', and operators routinely record every binding on tape' (Codex r16)", m86),
             ("m87 claim split across a one-word concatenated literal (Codex r16)", m87),
             ("m88 regex literal holding a quote does not desynchronise the lexer (Codex r16)", m88),
             ("m89 \\u escape decoded, so the claim is visible (Codex r16)", m89),
             ("m90 'must report the operator quietly spoke on tape' (Codex r17: irregular verb)", m90),
             ("m91 'throw /\'/' before a dishonest literal (Codex r17: regex after throw)", m91),
             ("m92 escaped line continuation inside a claim (Codex r17)", m92),
             ("m93 hidden span cannot qualify the visible claim (Codex r17)", m93),
             ("m94 'the operator spoke softly on tape' (Kimi r18: post-verbal adverb)", m94),
             ("m95 'the experienced operator quietly spoke on tape' (Codex r18)", m95),
             ("m96 'grants narrowly constrained Phase A roles' (Codex r18: attributive participle)", m96),
             ("m97 'holder.throw / \'/\' / 2' is property access and division (Codex r18)", m97),
             ("m98 regex after a control-flow head does not desynchronise (Codex r18)", m98),
             ("m99 'style = \'display:none\'' is hidden, spaces and all (Codex r18)", m99),
             ("m100 'data-hidden=\'false\'' is visible and its claim is read (Codex r18)", m100),
             ("m101 'the operator quit on tape' (Codex r19: invariant irregular past)", m101),
             ("m102 'and most record every binding' opens its own subject (Codex r19)", m102),
             ("m103 'holder.if(ready) / \'/\' / 2' is member access and division (Codex r19)", m103),
             ("m104 a regex after a nested condition does not desynchronise (Codex r19)", m104),
             ("m105 'display:none; display:inline' renders, so its claim is read (Codex r19)", m105),
             ("m106 unquoted 'style=display:none' still hides its qualifier (Codex r19)", m106),
             ("m107 a nested same-tag hidden element is removed whole (Codex r19)", m107),
             ("m108 'title=\'hidden\'' is a visible element, not a hidden one (Codex r19)", m108),
             ("m109 'the operator froze on tape' is unaudited prose (Codex r20)", m109),
             ("m110 'the Phase A operator quit on tape' is unaudited prose (Codex r20)", m110),
             ("m111 an unaudited claim beside honest wording (Codex r20)", m111),
             ("m112 INV-4: a PENDING row with completion language and no qualifier", m112),
             ("m113 INV-3: a CAPTURED row claiming a deferred artefact", m113),
             ("m114 INV-2: a CAPTURED row citing evidence that does not exist", m114),
             ("m115 INV-5: a register row for prose that does not ship", m115),
             ("m116 INV-1: dropping a row leaves shipped prose unaudited", m116),
             ("m117 'holder . if(ready)' is member access whatever the spacing (Codex r20)", m117),
             ("m118 a regex after a triple-nested condition does not desynchronise (Codex r20)", m118),
             ("m119 a long condition has no lookback ceiling (Codex r20)", m119),
             ("m120 '--x:display:none' is a custom property, not a display (Codex r20)", m120),
             ("m121 a tag inside an HTML comment opens no element (Codex r20)", m121),
             ("m122 'stamped okf-context-runtime … deployment_heads' is unaudited (Codex r21)", m122),
             ("m123 'The IAM bootstrap completed successfully.' is unaudited (Codex r21)", m123),
             ("m124 'okf-context sync committed successfully.' is unaudited (Codex r21)", m124),
             ("m125 'BQ_COMMITTED happened.' is unaudited by shape alone (Codex r21)", m125),
             ("m126 INV-1: an audited sentence moved to another file is unaudited there (Codex r21)", m126),
             ("m127 INV-2: 'live/../../index.html' is not evidence (Codex r21)", m127),
             ("m128 INV-3: a distant 'no' does not disclaim the artefact (Codex r21)", m128),
             ("m129 INV-4: a licence span that does not open with a qualifier (Codex r21)", m129),
             ("m130 postfix ++ leaves a value, so the next slash divides (Codex r21)", m130),
             ("m131 postfix -- likewise (Codex r21)", m131),
             ("m132 aria-hidden text is on the screen and is audited (Codex r21)", m132),
             ("m133 a stylesheet that prints prose is copy (Codex r21)", m133),
             ("m134 a stylesheet comment is read like any other comment (Codex r21)", m134),
             ("m135 'The IAM bootstrap succeeded.' is regulated because everything is (Codex r22)", m135),
             ("m136 'The sync finished successfully.' likewise (Codex r22)", m136),
             ("m137 INV-4: a licence that is not a frame licenses nothing (Codex r22)", m137),
             ("m138 INV-3: a disclaimer must sit on the artefact it disclaims (Codex r22)", m138),
             ("m139 INV-3: NOT_PHASE_A is naming, not distance (Codex r22)", m139),
             ("m140 a semicolon inside a quoted CSS content value (Codex r22)", m140),
             ("m141 content: attr(x) prints an attribute onto the screen (Codex r22)", m141),
             ("m142 JSON is audited after JSON.parse, not as source bytes (Codex r22)", m142),
             ("m143 HTML entities are decoded before the reader sees them (Codex r22)", m143),
             ("m144 INV-6: a claim written into a rendered live capture (Codex r23)", m144),
             ("m145 INV-6: the same in a session capture (Codex r23)", m145),
             ("m146 INV-6: a new pane fetching an unpinned file (Codex r23)", m146),
             ("m147 'The IAM bootstrap succeeded.' cannot be CAPTURED (Codex r23)", m147),
             ("m148 … nor NOT_PHASE_A: the spec declares that piece undone (Codex r23)", m148),
             ("m149 … nor PENDING: the verb stands straight after the artefact (Codex r23)", m149),
             ("m150 a negation cannot reach across a second noun phrase (Codex r23)", m150),
             ("m151 an escaped JSON value is literal text on the screen (Codex r23)", m151),
             ("m152 'content/**/:' is still a content declaration (Codex r23)", m152),
             ("m153 attr() prints an unquoted attribute (Codex r23)", m153)]

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
