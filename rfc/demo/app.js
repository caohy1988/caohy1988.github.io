/* BQAA → derived OKF prototype — four beats, vanilla JS, no build.
   Loads the synthetic BQAA trace + Phase 0 golden files, runs the one-way
   adapter in the browser, computes the derived identity chain with the
   PROFILE.md rules (hash.js), and renders Observe / Adapt / Project / Consume.
   No network calls beyond Google Fonts and same-origin static files. */
(function () {
  "use strict";

  var A = window.OkfBqaaAdapter;
  var H = window.OkfHash;
  var TOTAL = 4;
  var current = 1;
  var D = null; // loaded data + adapter output

  var stage = document.getElementById("stage");
  var btnBack = document.getElementById("btn-back");
  var btnNext = document.getElementById("btn-next");
  var stepCount = document.getElementById("step-count");
  var stepButtons = Array.prototype.slice.call(document.querySelectorAll(".step"));

  // ---- helpers -----------------------------------------------------------
  function esc(s) {
    return String(s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
  }
  function short(id, n) { n = n || 18; return id ? id.slice(0, n) + "…" : "—"; }
  function jsonHtml(obj, hlKeys) {
    hlKeys = hlKeys || [];
    var text = JSON.stringify(obj, null, 2);
    var html = esc(text).replace(/("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g, function (m, str, colon, bool, num) {
      if (str !== undefined) {
        if (colon !== undefined) {
          var key = str.slice(1, -1);
          var cls = hlKeys.indexOf(key) >= 0 ? "k hl" : "k";
          return '<span class="' + cls + '">' + str + "</span>" + colon;
        }
        return '<span class="s">' + str + "</span>";
      }
      if (bool !== undefined) return '<span class="b">' + bool + "</span>";
      return '<span class="n">' + num + "</span>";
    });
    return html;
  }
  function pre(obj, hlKeys, cls) {
    return '<pre class="json ' + (cls || "") + '">' + jsonHtml(obj, hlKeys) + "</pre>";
  }
  function tsShort(iso) { return iso.slice(11, 23); }
  function fetchJson(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.json(); }); }
  function fetchBytes(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.arrayBuffer(); }).then(function (b) { return new Uint8Array(b); }); }

  // ---- load --------------------------------------------------------------
  var MANIFEST_NAMES = ["canonicalization-manifest", "semantic-config", "resolver-manifest", "vocabulary-manifest"];
  Promise.all([
    fetchJson("traces/bqaa-germany.json"),
    fetchJson("fixture/golden/identities.json"),
    fetchJson("fixture/golden/receipt.json"),
    fetchJson("fixture/golden/expected-phase4-receipt.json"),
    fetchJson("derived/identities.json"),
    Promise.all(MANIFEST_NAMES.map(function (n) { return fetchBytes("fixture/golden/manifests/" + n + ".json"); }))
  ]).then(function (res) {
    var manifests = {};
    MANIFEST_NAMES.forEach(function (n, i) { manifests[n] = res[5][i]; });
    var trace = res[0];
    var adapted = A.adapt(trace);
    var derived = A.computeIdentities(adapted.files, adapted.constants, manifests);
    var pinned = res[4];
    var matchTriple = ["observation_id", "snapshot_id", "publication_id", "source_manifest_hash"].every(function (k) { return derived[k] === pinned[k]; });
    var matchConcepts = Object.keys(pinned.concept_version_ids).every(function (p) { return derived.concept_version_ids[p] === pinned.concept_version_ids[p]; }) &&
      Object.keys(derived.concept_version_ids).length === Object.keys(pinned.concept_version_ids).length;
    var envId = A.demoEnvelopeId(derived.publication_id);
    D = {
      trace: trace, authored: res[1], receipt: res[2], phase4: res[3], pinned: pinned,
      adapted: adapted, derived: derived, envId: envId,
      match: matchTriple && matchConcepts && envId === pinned.demo_envelope_id,
      distinct: derived.publication_id !== res[1].publication_id && adapted.bundle_key !== res[1].inputs.bundle_key
    };
    buildPayloads();
    renderIdentity();
    render();
  }).catch(function (err) {
    stage.innerHTML =
      '<div class="error-box"><b>Could not load the fixture files.</b> ' + esc(err.message) +
      '<p style="margin-top:10px">Browsers block <code>fetch()</code> over <code>file://</code>. Serve the repo root instead: <code>python3 -m http.server 8000</code> then open <code>http://localhost:8000/rfc/demo/</code>.</p></div>';
    ["a-status", "d-status"].forEach(function (id) { var el = document.getElementById(id); el.textContent = "not loaded"; el.className = "status warn"; });
  });

  // ---- agent-facing payloads (beat 4) ------------------------------------
  function buildPayloads() {
    var obs = D.adapted.observation;
    var envRef = "okf:" + D.envId;
    var items = obs.items.map(function (it, i) {
      return { n: i + 1, type: it.type, title: it.title, lifecycle: "draft", citation: "[" + envRef + "#" + (i + 1) + "]" };
    });
    D.retrieveCall = { name: "okf_retrieve_context", args: { mode: "current", token_budget: 8000 } };
    D.retrieveResult = {
      context_ref: envRef,
      profile_contract_version: "okf-context/1",
      mode: "current",
      item_count: items.length,
      excluded_count: obs.excluded.length,
      packing: "okf-context:pack:v0",
      items: items,
      excluded: obs.excluded.map(function (x) { return { type: x.type, title: x.title, reason: x.reason }; }),
      provenance: "derived / demo — observer-derived stubs; authored text unavailable to this publication"
    };
    var r = D.receipt;
    D.computeCall = {
      name: "okf_run_attested_computation",
      args: { context_ref: envRef + "#2", parameter_names: r.parameter_names.slice(), parameter_binding_commitment: r.parameter_binding_commitment }
    };
    D.computeResult = {
      context_ref: envRef + "#2",
      resolved_via: "sources → okf:computation-version:" + r.computation_version_id,
      receipt: {
        receipt_version: r.receipt_version,
        receipt_id: r.receipt_id,
        profile_contract_version: r.profile_contract_version,
        publication_id: r.publication_id,
        computation_version_id: r.computation_version_id,
        envelope_id: r.envelope_id,
        bq_job_id: r.bq_job_id,
        executed_artifact_hash: r.executed_artifact_hash,
        parameter_names: r.parameter_names.slice(),
        parameter_binding_commitment: r.parameter_binding_commitment,
        attester_artifact_hash: r.attester_artifact_hash,
        verdict: r.verdict,
        verdict_reason: r.verdict_reason,
        verdict_details_digest: r.verdict_details_digest,
        job_started_at: r.job_started_at,
        job_ended_at: r.job_ended_at,
        total_bytes_processed: r.total_bytes_processed,
        receipt_digest: r.receipt_digest,
        integrity_proof: r.integrity_proof
      },
      withheld_fields: ["destination_table (raw name)", "attester_identity", "parameter_values", "principal"]
    };
    D.finalText = "The number is whatever the sanctioned computation " + envRef + "#2 produces for that region and quarter. " +
      "It excludes the superseded legacy definition. Trust: the receipt verdict is UNVERIFIABLE (phase0_no_execution_or_integrity_proof) — " +
      "nothing was executed or attested, so treat any figure as unproven.";
    D.violations = A.neverEmitViolations([D.retrieveResult, D.computeResult]);
    D.scannedKeys = Object.keys(A.keysDeep([D.retrieveResult, D.computeResult])).length;
  }

  // ---- identity strip ------------------------------------------------------
  function renderIdentity() {
    var a = D.authored, d = D.derived;
    document.getElementById("a-obs").textContent = a.observation_id;
    document.getElementById("a-snap").textContent = a.snapshot_id;
    document.getElementById("a-pub").textContent = a.publication_id;
    document.getElementById("d-obs").textContent = d.observation_id;
    document.getElementById("d-snap").textContent = d.snapshot_id;
    document.getElementById("d-pub").textContent = d.publication_id;
    var as = document.getElementById("a-status"); as.textContent = "pinned · display only"; as.className = "status ok";
    var ds = document.getElementById("d-status");
    if (D.match && D.distinct) { ds.textContent = "JS = pinned = Python ✓ · distinct from authored"; ds.className = "status ok"; }
    else { ds.textContent = D.match ? "not distinct from authored" : "mismatch vs derived/identities.json"; ds.className = "status warn"; }
  }

  // ---- beat 1: observe -----------------------------------------------------
  function evSummary(e) {
    var c = e.content || {}, at = e.attributes || {};
    switch (e.event_type) {
      case "LLM_REQUEST":
        if (c.role === "user") return "user asks: “" + esc(c.text) + "”";
        return "tool context → model · <span class=\"ref\">" + esc(c.context_ref) + "</span> · " + c.context_tokens + " tokens";
      case "LLM_RESPONSE":
        if (c.function_calls) { var fc = c.function_calls[0]; return "→ call <b>" + esc(fc.name) + "</b> " + esc(JSON.stringify(fc.args).replace(/"/g, "")); }
        return "final answer · cites " + (c.citations || []).map(function (x) { return "<span class=\"ref\">" + esc(x) + "</span>"; }).join(", ");
      case "TOOL_STARTING": return esc(c.tool) + " starting";
      case "TOOL_COMPLETED":
        if (e.status === "ERROR") return esc(c.tool) + " failed closed · <b>" + esc(at.okf.error_code) + "</b> (names only, no values)";
        return esc(c.tool) + " completed · <span class=\"ref\">" + esc(at.context_ref) + "</span> · " + (e.latency_ms.total || 0) + " ms";
      case "HITL_CONFIRMATION_REQUEST": return "human-in-the-loop: “" + esc(c.question) + "”";
      case "HITL_CONFIRMATION_REQUEST_COMPLETED": return "confirmed by caller · principal withheld (user_id null)";
      case "STATE_DELTA": return "state: " + esc(Object.keys(c.delta).map(function (k) { return k + "=" + c.delta[k]; }).join(" · "));
      default: return esc(e.event_type);
    }
  }
  function evClass(e) {
    if (e.status === "ERROR") return "err";
    if (/^TOOL_/.test(e.event_type)) return "tool";
    if (/^HITL_/.test(e.event_type)) return "hitl";
    return "";
  }
  function renderObserve() {
    var t = D.trace, obs = D.adapted.observation;
    var keyset = A.keysDeep(t.events);
    var nullUsers = t.events.every(function (e) { return e.user_id === null; });
    var refSpans = t.events.filter(function (e) { return e.attributes && e.attributes.context_ref; }).length;
    var never = ["concept_version_id", "bundle_path", "source_path", "principal", "query_text", "sql", "parameter_values", "destination_table"];
    var list = t.events.map(function (e, i) {
      return '<li class="ev"><button type="button" aria-expanded="false" data-ev="' + i + '">' +
        '<span class="ts">' + tsShort(e.timestamp) + "</span>" +
        '<span class="ty ' + evClass(e) + '">' + esc(e.event_type) + "</span>" +
        '<span class="sm">' + evSummary(e) + "</span>" +
        '<span class="car">▸</span></button>' +
        '<div class="raw" hidden>' + pre(e, ["context_ref", "user_id"]) + "</div></li>";
    }).join("");
    var checks = never.map(function (k) {
      var present = !!keyset[k];
      return '<li class="' + (present ? "no" : "ok") + '"><span class="ic">' + (present ? "✕" : "✓") + "</span><span><code>" + k + "</code> " + (present ? "present as a key" : "absent from every event key") + "</span></li>";
    }).join("");
    return beatHead(1, "telemetry", "Observe", "The observer saw a question, two tools, one fail-closed error, and a receipt.",
      "<b>" + t.events.length + " events</b> shaped like rows a <code>google-adk-bq-logger</code> writer appends to <code>agent_events</code>. Everything downstream reads only these rows. Synthetic and labelled: nothing was written to a live table.") +
      must("observer-only · principal withheld · no SQL · no bundle paths · no concept_version_id · <code>context_ref</code> is the only correlation handle") +
      '<div class="cols">' +
      '<div class="pane telemetry"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--telemetry)"></span>agent_events · ' + esc(obs.session_id) + '</span><span class="m">BQAA observer · click a row for the raw event</span></div>' +
      '<div class="pane-b"><ul class="events">' + list + "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">What the observer sees</span><span class="m">and what it never sees</span></div><div class="pane-b">' +
      '<dl class="facts">' +
      "<dt>table</dt><dd><code>" + esc(t.table) + "</code></dd>" +
      "<dt>writer</dt><dd><code>" + esc(t.writer.plugin) + "</code> · " + esc(t.writer.mode) + "</dd>" +
      "<dt>agent</dt><dd><code>" + esc(t.agent.name) + "</code> · " + esc(t.agent.framework) + " · <code>" + esc(t.agent.model) + "</code></dd>" +
      "<dt>trace</dt><dd><code>" + esc(obs.trace_id) + "</code></dd>" +
      "<dt>window</dt><dd>" + tsShort(obs.span.first) + " → " + tsShort(obs.span.last) + " UTC</dd>" +
      "<dt>context_ref</dt><dd>on " + refSpans + " tool spans · <code>" + esc(obs.context_ref) + "</code></dd>" +
      "<dt>authored pub</dt><dd>observed on the tool span: <code>" + short(obs.observed_publication_id, 23) + "</code></dd>" +
      "</dl>" +
      '<p class="beat-kicker" style="margin:8px 0 6px">Never-emit scan · every event key</p>' +
      '<ul class="checklist">' + checks +
      '<li class="' + (nullUsers ? "ok" : "no") + '"><span class="ic">' + (nullUsers ? "✓" : "✕") + "</span><span><code>user_id</code> is <code>null</code> on all " + t.events.length + " events — principal withheld</span></li>" +
      '<li class="info"><span class="ic">i</span><span>Parameter <em>names</em> and the HMAC binding commitment appear; parameter <em>values</em> never do.</span></li>' +
      '<li class="info"><span class="ic">i</span><span>The user’s question is BQAA content. The sanctioned SQL template is not, and never appears.</span></li>' +
      "</ul></div></div></div>";
  }

  // ---- beat 2: adapt -----------------------------------------------------
  var selectedFile = null;
  function fileTree() {
    var files = D.adapted.files;
    var byDir = {};
    Object.keys(files).sort().forEach(function (p) {
      var dir = p.indexOf("/") >= 0 ? p.split("/")[0] : "(root)";
      (byDir[dir] = byDir[dir] || []).push(p);
    });
    return '<ul class="tree">' + Object.keys(byDir).sort().map(function (dir) {
      return '<li><div class="dir">' + esc(dir) + "/</div><ul>" + byDir[dir].map(function (p) {
        var name = p.split("/").pop();
        var ty = p === "log.md" ? "reserved" : (D.adapted.files[p].match(/^type: (.+)$/m) || [])[1] || "";
        return '<li><button type="button" data-file="' + esc(p) + '"' + (p === selectedFile ? ' aria-current="true"' : "") + ">" + esc(name) + '<span class="ty">' + esc(ty) + "</span></button></li>";
      }).join("") + "</ul></li>";
    }).join("") + "</ul>";
  }
  function fileView(p) {
    var text = D.adapted.files[p];
    var lines = text.split("\n");
    var inFm = false, out = [];
    lines.forEach(function (ln, i) {
      if (ln === "---" && (i === 0 || inFm)) { inFm = !inFm; out.push('<span class="hr">---</span>'); return; }
      if (inFm) {
        var m = ln.match(/^(\s*)([A-Za-z_]+)(:)(.*)$/);
        if (m) { out.push(m[1] + '<span class="fmk">' + esc(m[2]) + "</span>" + m[3] + '<span class="fm">' + esc(m[4]) + "</span>"); return; }
        out.push('<span class="fm">' + esc(ln) + "</span>"); return;
      }
      out.push(esc(ln).replace(/Derived from BQAA observation, not authored\./g, '<span class="derived">Derived from BQAA observation, not authored.</span>'));
    });
    var meta = p === "log.md" ? "reserved §9 file · no frontmatter by design" : "concept_version_id (store-only) " + short(D.derived.concept_version_ids[p], 23) + " · sha256 " + short(D.derived.file_sha256[p], 12);
    return '<div class="pane-h" style="border-top:1px solid var(--line)"><span class="t"><code>' + esc(p) + '</code></span><span class="m">' + esc(meta) + "</span></div>" +
      '<div class="viewer">' + out.join("\n") + "</div>";
  }
  function renderAdapt() {
    var ad = D.adapted, obs = ad.observation, d = D.derived, a = D.authored;
    if (!selectedFile) selectedFile = "computations/active-customer-revenue-by-region-and-quarter.md";
    if (!ad.files[selectedFile]) selectedFile = Object.keys(ad.files)[0];
    var mdFiles = Object.keys(ad.files).filter(function (p) { return /\.md$/.test(p) && p !== "log.md"; });
    var typed = mdFiles.filter(function (p) { return /^type: \S/m.test(ad.files[p]); }).length;
    var keysUsed = {};
    mdFiles.forEach(function (p) { H.splitFrontmatter(ad.files[p]).frontmatter.split("\n").forEach(function (ln) { var m = ln.match(/^([a-z_]+):/); if (m) keysUsed[m[1]] = true; }); });
    return beatHead(2, "source", "Adapt", "One-way adapter. Observer events in, a derived bundle out, its own identity chain.",
      "<code>" + esc(A.ADAPTER_VERSION) + "</code> reads the " + obs.event_count + " events and emits <b>" + Object.keys(ad.files).length + " files</b> under <code>" + esc(ad.bundle_key) + "</code>: one stub per retrieved or excluded item, one <code>log.md</code> line. Every stub says <em>derived from BQAA observation, not authored</em>. The authored bundle is neither read nor written.") +
      must("banner derived/demo · distinct <code>bundle_key</code> · own observation / snapshot / publication triple · <code>okf-phase0-mvp/fixture/bundle</code> untouched") +
      '<div class="flow">' +
      '<div class="box t"><b>in · BQAA trace</b>' + obs.event_count + " events · session <code>" + esc(obs.session_id) + "</code><br>6 retrieved + 1 excluded item · 1 receipt · 1 edge</div>" +
      '<div class="arrow"><b>→</b>one-way<br>observe · adapt · hash</div>' +
      '<div class="box d"><b>out · derived OKF v0.2 bundle</b><code>' + esc(ad.bundle_key) + "</code> · " + Object.keys(ad.files).length + " files<br>publication <code>" + short(d.publication_id, 23) + "</code></div>" +
      "</div>" +
      '<div class="cols">' +
      '<div class="pane source"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--source)"></span>bundle inspector · ' + esc(ad.bundle_key) + '</span><span class="m">source view · paths are allowed here, never in telemetry</span></div>' +
      '<div class="pane-b" style="padding:8px 10px">' + fileTree() + "</div>" + fileView(selectedFile) + "</div>" +
      '<div class="pane"><div class="pane-h"><span class="t">Identity chain · computed now</span><span class="m">PROFILE.md rules in hash.js</span></div><div class="pane-b">' +
      '<dl class="facts">' +
      "<dt>bundle_key</dt><dd><code>" + esc(ad.constants.bundle_key) + "</code></dd>" +
      "<dt>source_uri</dt><dd><code>" + esc(ad.constants.source_uri) + "</code></dd>" +
      "<dt>revision</dt><dd><code>" + esc(ad.constants.revision) + "</code></dd>" +
      "<dt>deployment</dt><dd><code>" + esc(ad.constants.deployment_key) + "</code></dd>" +
      "<dt>observation_id</dt><dd><code>" + esc(d.observation_id) + "</code></dd>" +
      "<dt>snapshot_id</dt><dd><code>" + esc(d.snapshot_id) + "</code></dd>" +
      "<dt>publication_id</dt><dd><code>" + esc(d.publication_id) + "</code></dd>" +
      "</dl>" +
      '<ul class="checklist">' +
      '<li class="' + (D.match ? "ok" : "no") + '"><span class="ic">' + (D.match ? "✓" : "✕") + '</span><span>Browser hash = pinned <code>derived/identities.json</code> = Python re-derivation (<code>tools/derived_vectors.py</code>)</span></li>' +
      '<li class="ok"><span class="ic">✓</span><span>Same <code>hash.js</code> reproduces the authored golden triple and all 9 authored concept versions (<code>tools/check-authored-identities.mjs</code>)</span></li>' +
      '<li class="' + (D.distinct ? "ok" : "no") + '"><span class="ic">' + (D.distinct ? "✓" : "✕") + "</span><span>Distinct from authored <code>" + esc(a.inputs.bundle_key) + "</code> · pub <code>" + short(a.publication_id, 16) + "</code> stays pinned and unchanged</span></li>" +
      '<li class="ok"><span class="ic">✓</span><span>Adapter reads 0 authored files; writes 0 authored files</span></li>' +
      '<li class="' + (typed === mdFiles.length ? "ok" : "no") + '"><span class="ic">✓</span><span>Frontmatter <code>type</code> on ' + typed + "/" + mdFiles.length + " non-reserved <code>.md</code>; <code>log.md</code> reserved</span></li>" +
      '<li class="info"><span class="ic">i</span><span>Zero new required keys. Keys used: ' + Object.keys(keysUsed).sort().map(function (k) { return "<code>" + k + "</code>"; }).join(" ") + "</span></li>" +
      '<li class="info"><span class="ic">i</span><span>No <code>computation:</code> artifact in the derived stub — the observer never sees SQL. It cites the authored <code>computation_version_id</code> under <code>sources</code>.</span></li>' +
      "</ul></div></div></div>";
  }

  // ---- beat 3: project ---------------------------------------------------
  function renderProject() {
    var ad = D.adapted, d = D.derived, obs = ad.observation;
    var pub = d.publication_id, snap = d.snapshot_id;
    var docs = Object.keys(ad.files).filter(function (p) { return /\.md$/.test(p) && p !== "log.md"; }).sort();
    function fm(p, key) { var m = ad.files[p].match(new RegExp("^" + key + ": (.+)$", "m")); return m ? m[1] : ""; }
    var cards = docs.map(function (p) {
      var type = fm(p, "type"), title = fm(p, "title"), status = fm(p, "status");
      var isComp = type === "Attested Computation";
      var params = isComp ? (obs.receipt ? obs.receipt.parameter_schema.map(function (x) { return x.name; }).join(", ") : "") : "";
      return '<div class="card"><div class="ch"><span class="name">' + esc(title) + '</span><span class="etype">okf-concept</span></div>' +
        '<div class="pins">' +
        '<span class="pin"><b>okf.type</b> ' + esc(type) + "</span>" +
        '<span class="pin' + (status === "deprecated" ? " dep" : "") + '"><b>okf.lifecycle</b> ' + esc(status) + "</span>" +
        '<span class="pin"><b>okf.provenance</b> bqaa observer · derived</span>' +
        '<span class="pin pub"><b>okf.publication_id</b> ' + esc(short(pub, 19)) + "</span>" +
        '<span class="pin"><b>okf.published_snapshot_id</b> ' + esc(short(snap, 15)) + "</span>" +
        (isComp ? '<span class="pin" style="border-color:#F0D9B8;background:var(--runtime-bg);color:var(--runtime)"><b style="color:var(--runtime)">okf-computation</b> runtime bigquery · params [' + esc(params) + "]</span>" : "") +
        "</div></div>";
    }).join("");

    var pubRow = [{ publication_id: pub, observation_id: d.observation_id, snapshot_id: snap, deployment_key: ad.constants.deployment_key, bundle_key: ad.constants.bundle_key, profile_contract_version: ad.constants.profile_contract_version }];
    var headRow = [{ deployment_key: ad.constants.deployment_key, publication_id: pub, published_at: obs.span.last }];
    var nodes = docs.map(function (p) {
      return { concept_key: ad.constants.bundle_key + "#" + p.slice(0, -3), type: fm(p, "type"), title: fm(p, "title"), status: fm(p, "status"), concept_version_id: d.concept_version_ids[p], publication_id: pub };
    });
    var edges = [];
    docs.forEach(function (p) {
      var f = H.splitFrontmatter(ad.files[p]).frontmatter;
      var sup = f.match(/^supersedes:\n((?:  - .+\n?)+)/m);
      if (sup) sup[1].trim().split("\n").forEach(function (ln) { edges.push({ from_concept_key: ad.constants.bundle_key + "#" + p.slice(0, -3), to_concept_key: ad.constants.bundle_key + "#" + ln.replace(/^\s*-\s*/, "").replace(/\.md$/, ""), predicate: "supersedes", assertion_mode: "explicit", publication_id: pub }); });
      var lk = f.match(/^links:\n((?:    .+\n?|  - .+\n?)+)/m);
      if (lk) {
        var target = (lk[1].match(/target: (\S+)/) || [])[1], rel = (lk[1].match(/rel: (\S+)/) || [])[1];
        if (target) edges.push({ from_concept_key: ad.constants.bundle_key + "#" + p.slice(0, -3), to_concept_key: ad.constants.bundle_key + "#" + target.replace(/^\.\.\//, "").replace(/\.md$/, ""), predicate: "producer:" + rel, assertion_mode: "inferred", publication_id: pub });
      }
    });
    function table(name, rows, note) {
      var cols = Object.keys(rows[0]);
      return '<div class="tbl-wrap"><table class="tbl"><caption>' + esc(name) + "<span>" + rows.length + " row" + (rows.length === 1 ? "" : "s") + (note ? " · " + esc(note) : "") + "</span></caption><thead><tr>" +
        cols.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr></thead><tbody>" +
        rows.map(function (r) { return "<tr>" + cols.map(function (c) { var v = r[c]; var cls = c === "publication_id" ? ' class="pub"' : ""; return "<td" + cls + ' title="' + esc(v) + '">' + esc(/^sha256:/.test(String(v)) ? short(v, 19) : v) + "</td>"; }).join("") + "</tr>"; }).join("") +
        "</tbody></table></div>";
    }
    var same = pub === pubRow[0].publication_id && nodes.every(function (n) { return n.publication_id === pub; });
    return beatHead(3, "split", "Project", "Two stores, one publication. Discovery in Knowledge Catalog, serving in BigQuery.",
      "The derived publication is pushed to both projections. <b style=\"color:var(--catalog)\">Catalog</b> gets one <code>okf-concept</code> entry per stub with the <code>okf</code> aspect pinned to the publication; <b style=\"color:var(--runtime)\">BigQuery</b> gets append-only rows in the RFC’s relational shape. Both are client-side views here: no <code>kcmd</code> write, no DML.") +
      must("same <code>publication_id</code> on both panes · Catalog labelled projection/demo · BigQuery rows shaped like the RFC projection") +
      '<div class="cols even">' +
      '<div class="pane catalog"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--catalog)"></span>Knowledge Catalog · discovery</span><span class="m">projection view · demo · no live kcmd</span></div>' +
      '<div class="pane-b"><div class="cards">' + cards + "</div></div></div>" +
      '<div class="pane runtime"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--runtime)"></span>BigQuery · serving</span><span class="m">client-side rows · RFC projection shape · no DML</span></div>' +
      '<div class="pane-b">' + table("publications", pubRow) + table("deployment_heads", headRow, "head advanced") + table("nodes_current", nodes, "one row per concept version") + table("edges_current", edges) + "</div></div>" +
      '<div class="seam-note"><span>Catalog <code>okf.publication_id</code> ' + esc(short(pub, 23)) + '</span><span class="eq">' + (same ? "=" : "≠") + '</span><span>BigQuery <code class="rt">publications.publication_id</code> ' + esc(short(pub, 23)) + "</span><span>· " + (same ? "same publication on both stores ✓" : "MISMATCH") + "</span></div>" +
      "</div>";
  }

  // ---- beat 4: consume ---------------------------------------------------
  function renderConsume() {
    var t = D.trace, obs = D.adapted.observation;
    var ok = D.violations.length === 0;
    var py =
      '<span class="cm"># ADK agent — fixture transcript replay; this page runs no Python and calls no model</span>\n' +
      '<span class="kw">from</span> google.adk.agents <span class="kw">import</span> Agent\n' +
      '<span class="kw">from</span> google.adk.models <span class="kw">import</span> Gemini\n' +
      '<span class="kw">import</span> os\n\n' +
      'DEMO_MODEL_ID = os.environ.get(<span class="st">"DEMO_MODEL_ID"</span>, <span class="st hl">"gemini-3.8-flash"</span>)\n\n' +
      'agent = Agent(\n' +
      '    name=<span class="st">"cymbal-finance-analyst"</span>,\n' +
      '    model=Gemini(model=DEMO_MODEL_ID),\n' +
      '    tools=[okf_retrieve_context, okf_run_attested_computation],\n' +
      '    instruction=<span class="st">"Cite context_ref only. Never state a figure without a receipt."</span>,\n' +
      ')';
    return beatHead(4, "ink", "Consume", "An ADK agent retrieves, asks for the sanctioned computation, and gets an honest receipt.",
      "The agent is <code>google.adk.agents.Agent</code> on <b><code>gemini-3.8-flash</code></b>. Its tool results carry <code>context_ref</code> and RFC-allowed receipt fields — nothing from the never-emit list. The receipt is the Phase 0 golden specimen: <b>UNVERIFIABLE</b>, because nothing was executed or attested.") +
      must("tool JSON contains <code>context_ref</code> · keys ∩ never-emit = ∅ · verdict UNVERIFIABLE / <code>phase0_no_execution_or_integrity_proof</code> · Phase 4 ATTESTED shape non-normative") +
      '<div class="adk">' +
      '<div class="adk-h"><span class="agent"><span class="fw">google-adk</span><b>' + esc(t.agent.name) + "</b><span>session " + esc(obs.session_id) + '</span></span>' +
      '<span class="model-badge"><span class="dot"></span>model · <b>gemini-3.8-flash</b></span></div>' +
      '<div class="adk-b"><div class="transcript">' +
      turn("user", "user", '<div class="bubble user">' + esc(obs.question) + "</div>") +
      turn("model", "gemini-3.8-flash", '<div class="bubble call">function_call → <b>' + esc(D.retrieveCall.name) + "</b> " + esc(JSON.stringify(D.retrieveCall.args)) + "</div>") +
      turn("tool", "tool result", result("okf_retrieve_context", "derived publication · context_ref", D.retrieveResult)) +
      turn("model", "gemini-3.8-flash", '<div class="bubble call">function_call → <b>' + esc(D.computeCall.name) + "</b> " + esc(JSON.stringify(D.computeCall.args)) + "</div>") +
      turn("tool", "tool result", result("okf_run_attested_computation", "golden receipt · UNVERIFIABLE", D.computeResult)) +
      turn("model", "gemini-3.8-flash", '<div class="bubble final">' + esc(D.finalText).replace(esc("okf:" + D.envId + "#2"), '<span class="cite">' + esc("okf:" + D.envId + "#2") + "</span>") + "</div>") +
      "</div>" +
      '<div class="side">' +
      '<div class="tile"><div class="th">agent construction · checked-in default</div><pre class="py">' + py + "</pre></div>" +
      '<div class="tile"><div class="th">never-emit assertion · both tool results</div><div class="big ' + (ok ? "ok" : "warn") + '">keys ∩ never-emit = ' + (ok ? "∅ ✓" : esc(D.violations.join(", "))) + "</div><p>" + D.scannedKeys + " distinct keys scanned at render time against " + A.NEVER_EMIT.map(function (k) { return "<code>" + k + "</code>"; }).join(" ") + ".</p></div>" +
      '<div class="tile"><div class="th">receipt verdict</div><span class="verdict">UNVERIFIABLE · phase0_no_execution_or_integrity_proof</span><p>Golden specimen <code>' + esc(D.receipt.receipt_id) + "</code>, bound to the authored publication and envelope. The derived stub reaches it through its <code>sources</code> reference. No new receipt was minted: nothing ran. Integrity proof status <code>" + esc(D.receipt.integrity_proof.status) + "</code>.</p></div>" +
      '<details class="nn"><summary>Phase 4 ATTESTED shape · non-normative</summary><div class="nn-b"><span class="verdict att">ATTESTED · expected Phase 4 shape</span><p style="font-family:var(--display);font-size:13px;color:var(--ink-soft);margin:8px 0 0">' + esc(D.phase4._fixture_note) + "</p>" + pre({ verdict: D.phase4.verdict, verdict_details_digest: D.phase4.verdict_details_digest, receipt_digest: D.phase4.receipt_digest, integrity_proof: D.phase4.integrity_proof }, [], "rounded") + "</div></details>" +
      "</div></div></div>";
  }
  function turn(cls, who, inner) { return '<div class="turn"><span class="who ' + cls + '">' + esc(who) + "</span>" + inner + "</div>"; }
  function result(name, label, obj) {
    return '<div class="bubble result"><div class="rh"><span>' + esc(name) + "</span><span>" + esc(label) + "</span></div>" + pre(obj, ["context_ref", "verdict", "verdict_reason"]) + "</div>";
  }

  // ---- common ------------------------------------------------------------
  function beatHead(n, tone, name, headline, lede) {
    return '<div class="beat-head"><span class="beat-num ' + tone + '">' + n + '</span><span class="beat-kicker">Beat ' + n + " of " + TOTAL + " · " + esc(name) + "</span></div>" +
      '<h2 class="beat-headline">' + headline + "</h2>" +
      '<p class="beat-lede">' + lede + "</p>";
  }
  function must(html) { return '<p class="must"><b>must prove</b> <span>' + html + "</span></p>"; }

  function render() {
    if (!D) return;
    var html = current === 1 ? renderObserve() : current === 2 ? renderAdapt() : current === 3 ? renderProject() : renderConsume();
    stage.innerHTML = html;
    stepCount.textContent = current + " / " + TOTAL;
    btnBack.disabled = current === 1;
    btnNext.textContent = current === TOTAL ? "↺ Restart" : "Next →";
    stepButtons.forEach(function (b) {
      if (Number(b.dataset.beat) === current) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current");
    });
    var want = "#beat=" + current;
    if (location.hash !== want) history.replaceState(null, "", want);
  }

  function goTo(n) {
    if (n < 1 || n > TOTAL) return;
    current = n;
    render();
    var top = document.querySelector(".stepper").getBoundingClientRect().top + window.scrollY - 70;
    if (window.scrollY > top) window.scrollTo({ top: top, behavior: "smooth" });
  }
  function next() { goTo(current < TOTAL ? current + 1 : 1); }
  function prev() { goTo(current - 1); }

  stage.addEventListener("click", function (e) {
    var evBtn = e.target.closest("button[data-ev]");
    if (evBtn) {
      var raw = evBtn.nextElementSibling;
      var open = evBtn.getAttribute("aria-expanded") === "true";
      evBtn.setAttribute("aria-expanded", open ? "false" : "true");
      raw.hidden = open;
      evBtn.parentElement.toggleAttribute("open", !open);
      return;
    }
    var fBtn = e.target.closest("button[data-file]");
    if (fBtn) { selectedFile = fBtn.dataset.file; render(); }
  });
  stepButtons.forEach(function (b) { b.addEventListener("click", function () { goTo(Number(b.dataset.beat)); }); });
  btnBack.addEventListener("click", prev);
  btnNext.addEventListener("click", next);

  document.addEventListener("keydown", function (e) {
    var t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) return;
    if (e.metaKey || e.ctrlKey || e.altKey) return;
    switch (e.code) {
      case "ArrowRight": case "KeyN": e.preventDefault(); next(); break;
      case "ArrowLeft": case "KeyP": e.preventDefault(); prev(); break;
      case "Home": e.preventDefault(); goTo(1); break;
      case "Digit1": case "Digit2": case "Digit3": case "Digit4":
        e.preventDefault(); goTo(Number(e.code.slice(-1))); break;
    }
  });

  function hashBeat() {
    var m = (location.hash || "").match(/^#(?:beat=)?([1-4])$/);
    return m ? Number(m[1]) : null;
  }
  window.addEventListener("hashchange", function () { var n = hashBeat(); if (n && n !== current) goTo(n); });
  var initial = hashBeat();
  if (initial) current = initial;
})();
