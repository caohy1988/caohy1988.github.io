/* BQAA → derived OKF demo — four beats, vanilla JS, no build.
   Primary trace: the committed live snapshot of okf_rfc_demo.agent_events
   (14 real BQAA rows, session 04fa3d56-…) written while an ADK agent on
   gemini-3.8-flash consumed the derived publication by context_ref only.
   The synthetic Germany trace is still the adapter input for the derived
   bundle; the browser recomputes the derived identity chain with hash.js.
   No network calls beyond Google Fonts and same-origin static files:
   BigQuery, Dataplex and the model are reached only via console deep links. */
(function () {
  "use strict";

  var A = window.OkfBqaaAdapter;
  var H = window.OkfHash;
  var TOTAL = 4;
  var current = 1;
  var D = null; // loaded data + adapter output + live snapshot

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
  function tsLive(ts) { return String(ts).replace("T", " ").slice(11, 19); }
  function link(href, cls, label) { return '<a class="lk ' + (cls || "") + '" href="' + esc(href) + '" target="_blank" rel="noopener">' + label + " ↗</a>"; }
  function fetchJson(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.json(); }); }
  function fetchBytes(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.arrayBuffer(); }).then(function (b) { return new Uint8Array(b); }); }
  function parseMaybe(v) { if (typeof v === "string") { try { return JSON.parse(v); } catch (e) { return v; } } return v; }

  // ---- load --------------------------------------------------------------
  var MANIFEST_NAMES = ["canonicalization-manifest", "semantic-config", "resolver-manifest", "vocabulary-manifest"];
  Promise.all([
    fetchJson("traces/bqaa-germany.json"),
    fetchJson("fixture/golden/identities.json"),
    fetchJson("fixture/golden/receipt.json"),
    fetchJson("fixture/golden/expected-phase4-receipt.json"),
    fetchJson("derived/identities.json"),
    Promise.all(MANIFEST_NAMES.map(function (n) { return fetchBytes("fixture/golden/manifests/" + n + ".json"); })),
    fetchJson("live/live.json"),
    fetchJson("live/agent_events.json")
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
    D.live = prepLive(res[6], res[7], derived);
    buildFixturePayloads();
    renderIdentity();
    renderLiveStrip();
    render();
  }).catch(function (err) {
    stage.innerHTML =
      '<div class="error-box"><b>Could not load the static files.</b> ' + esc(err.message) +
      '<p style="margin-top:10px">Browsers block <code>fetch()</code> over <code>file://</code>. Serve the repo root instead: <code>python3 -m http.server 8000</code> then open <code>http://localhost:8000/rfc/demo/</code>.</p></div>';
    ["a-status", "d-status", "live-status"].forEach(function (id) { var el = document.getElementById(id); if (el) { el.textContent = "not loaded"; el.className = "status warn"; } });
  });

  // ---- live snapshot -------------------------------------------------------
  function prepLive(meta, rawRows, derived) {
    var rows = rawRows.map(function (r, i) {
      var o = {};
      Object.keys(r).forEach(function (k) { o[k] = r[k]; });
      o.attributes = parseMaybe(r.attributes);
      o.content = parseMaybe(r.content);
      o._i = i;
      return o;
    });
    function first(type) { return rows.filter(function (r) { return r.event_type === type; })[0] || null; }
    var starting = first("TOOL_STARTING"), completed = first("TOOL_COMPLETED"), user = first("USER_MESSAGE_RECEIVED"), answer = first("AGENT_RESPONSE"), req = first("LLM_REQUEST");
    var llmRes = rows.filter(function (r) { return r.event_type === "LLM_RESPONSE"; });
    var hist = {};
    rows.forEach(function (r) { hist[r.event_type] = (hist[r.event_type] || 0) + 1; });
    var toolArgs = starting && starting.content && starting.content.args || {};
    var toolResult = completed && completed.content && completed.content.result || {};
    var answerRaw = answer && answer.content && answer.content.response || "";
    var m = answerRaw.match(/^text: '([\s\S]*)'$/);
    var answerText = m ? m[1] : answerRaw;
    var rowKeys = A.keysDeep(rows.map(function (r) { return { attributes: r.attributes, content: r.content }; }));
    var never = A.NEVER_EMIT.filter(function (k) { return k !== "user_id"; });
    var pub = derived.publication_id;
    var usage = llmRes.map(function (r) { return r.content && r.content.usage || {}; });
    var totalTokens = usage.reduce(function (s, u) { return s + (u.total || 0); }, 0);
    return {
      meta: meta, rows: rows, starting: starting, completed: completed, user: user, answer: answer, req: req, llmRes: llmRes,
      hist: hist, toolArgs: toolArgs, toolResult: toolResult, answerText: answerText,
      toolName: completed && completed.content && completed.content.tool || meta.tool || "lookup_okf_context",
      question: user && user.content && user.content.text_summary || "",
      model: req && req.attributes && req.attributes.model || meta.model,
      toolsDeclared: req && req.attributes && req.attributes.tools || [],
      violations: A.neverEmitViolations([toolArgs, toolResult]),
      rowViolations: never.filter(function (k) { return rowKeys[k]; }),
      never: never,
      scannedKeys: Object.keys(A.keysDeep([toolArgs, toolResult])).length,
      userIds: rows.map(function (r) { return r.user_id; }).filter(function (v, i, a) { return a.indexOf(v) === i; }),
      sessionOk: rows.length > 0 && rows.every(function (r) { return r.session_id === meta.session_id && r.trace_id === meta.trace_id; }),
      pubMatch: toolResult.publication_id === pub,
      refMatch: !!toolResult.context_ref && toolResult.context_ref === meta.context_ref && toolResult.context_ref === "okf:env-demo#" + pub.slice(7, 19) && toolArgs.context_ref === toolResult.context_ref,
      argsOnlyRef: Object.keys(toolArgs).join(",") === "context_ref",
      modelOk: llmRes.length > 0 && llmRes.every(function (r) { return r.attributes && r.attributes.model_version === "gemini-3.8-flash"; }),
      usage: usage, totalTokens: totalTokens,
      span: rows.length ? { first: rows[0].timestamp, last: rows[rows.length - 1].timestamp } : null,
      table: meta.project + "." + meta.dataset + "." + meta.table
    };
  }

  function renderLiveStrip() {
    var L = D.live, st = document.getElementById("live-status");
    if (!st) return;
    var ok = L.sessionOk && L.pubMatch && L.refMatch && L.violations.length === 0 && L.modelOk;
    st.textContent = ok ? "snapshot verified in-browser ✓ · " + L.rows.length + " rows" : "snapshot mismatch — see beat 1";
    st.className = "status " + (ok ? "ok" : "warn");
  }

  // ---- fixture payloads (prior replay, kept for the collapsed comparison) ----
  function buildFixturePayloads() {
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
        receipt_version: r.receipt_version, receipt_id: r.receipt_id, profile_contract_version: r.profile_contract_version,
        publication_id: r.publication_id, computation_version_id: r.computation_version_id, envelope_id: r.envelope_id,
        bq_job_id: r.bq_job_id, executed_artifact_hash: r.executed_artifact_hash, parameter_names: r.parameter_names.slice(),
        parameter_binding_commitment: r.parameter_binding_commitment, attester_artifact_hash: r.attester_artifact_hash,
        verdict: r.verdict, verdict_reason: r.verdict_reason, verdict_details_digest: r.verdict_details_digest,
        job_started_at: r.job_started_at, job_ended_at: r.job_ended_at, total_bytes_processed: r.total_bytes_processed,
        receipt_digest: r.receipt_digest, integrity_proof: r.integrity_proof
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
    if (D.match && D.distinct) { ds.textContent = "JS = pinned = Python ✓ · distinct from authored" + (D.live.pubMatch ? " · = live tool result ✓" : ""); ds.className = "status ok"; }
    else { ds.textContent = D.match ? "not distinct from authored" : "mismatch vs derived/identities.json"; ds.className = "status warn"; }
  }

  // ---- beat 1: observe (live) ---------------------------------------------
  function liveSummary(e) {
    var c = e.content || {}, at = e.attributes || {};
    switch (e.event_type) {
      case "USER_MESSAGE_RECEIVED": return "user asks: “" + esc(c.text_summary || "") + "”";
      case "INVOCATION_STARTING": return "invocation starts · app <code>" + esc((at.adk || {}).app_name || "") + "</code>";
      case "INVOCATION_COMPLETED": return "invocation completed";
      case "AGENT_STARTING": return "agent starts · instruction captured by the observer (no SQL, no paths in it)";
      case "AGENT_COMPLETED": return "agent completed";
      case "WORKFLOW_NODE_STARTING": return "workflow node <code>" + esc(((at.adk || {}).node || {}).path || "") + "</code> starts";
      case "WORKFLOW_NODE_COMPLETED": return "workflow node completed · " + esc((at.adk || {}).workflow_node_status || "");
      case "LLM_REQUEST": return "prompt → <b>" + esc(at.model || "") + "</b> · tools declared [" + esc((at.tools || []).join(", ")) + "]";
      case "LLM_RESPONSE":
        if (/^call: /.test(c.response || "")) return "→ call <b>" + esc(String(c.response).slice(6)) + "</b> · " + ((c.usage || {}).total || 0) + " tokens";
        return "final text · " + ((c.usage || {}).total || 0) + " tokens · cites <span class=\"ref\">" + esc(D.live.meta.context_ref) + "</span>";
      case "TOOL_STARTING": return esc(c.tool) + " starting · args <span class=\"ref\">" + esc(JSON.stringify(c.args)) + "</span>";
      case "TOOL_COMPLETED":
        if (e.status === "ERROR") return esc(c.tool) + " failed";
        return esc(c.tool) + " completed · <span class=\"ref\">" + esc((c.result || {}).context_ref || "") + "</span> · pub " + esc(short((c.result || {}).publication_id || "", 19));
      case "AGENT_RESPONSE": return "agent answer · cites <span class=\"ref\">" + esc(D.live.meta.context_ref) + "</span>";
      default: return esc(e.event_type);
    }
  }
  function evClass(e) {
    if (e.status === "ERROR") return "err";
    if (/^TOOL_/.test(e.event_type)) return "tool";
    if (/^HITL_/.test(e.event_type) || /^(USER_MESSAGE|AGENT_RESPONSE)/.test(e.event_type)) return "hitl";
    return "";
  }
  function check(ok, html) { return '<li class="' + (ok ? "ok" : "no") + '"><span class="ic">' + (ok ? "✓" : "✕") + "</span><span>" + html + "</span></li>"; }
  function info(html) { return '<li class="info"><span class="ic">i</span><span>' + html + "</span></li>"; }

  function renderObserve() {
    var L = D.live, M = L.meta;
    var list = L.rows.map(function (e, i) {
      return '<li class="ev"><button type="button" aria-expanded="false" data-ev="' + i + '">' +
        '<span class="ts">' + esc(tsLive(e.timestamp)) + "</span>" +
        '<span class="ty ' + evClass(e) + '">' + esc(e.event_type) + "</span>" +
        '<span class="sm">' + liveSummary(e) + "</span>" +
        '<span class="car">▸</span></button>' +
        '<div class="raw" hidden>' + pre({ timestamp: e.timestamp, event_type: e.event_type, agent: e.agent, session_id: e.session_id, trace_id: e.trace_id, span_id: e.span_id, status: e.status, user_id: e.user_id, attributes: e.attributes, content: e.content }, ["context_ref", "publication_id", "session_id", "trace_id"]) + "</div></li>";
    }).join("");
    var histHtml = Object.keys(L.hist).map(function (k) { return "<code>" + esc(k) + "</code>×" + L.hist[k]; }).join(" ");
    var checks = L.never.map(function (k) {
      var present = L.rowViolations.indexOf(k) >= 0;
      return check(!present, "<code>" + k + "</code> " + (present ? "present as a key" : "absent from every row, attribute and content key"));
    }).join("");
    return beatHead(1, "telemetry", "Observe", "The observer logged a real session: one question, one tool call carrying <code>context_ref</code>, one Gemini answer.",
      "<b>" + L.rows.length + " rows</b> read back from <code>" + esc(L.table) + "</code> (" + esc(M.dataset_location) + "), appended by the ADK <code>BigQueryAgentAnalyticsPlugin</code> while <code>" + esc(M.agent) + "</code> ran on <b><code>" + esc(L.model) + "</code></b>. They are committed here as a snapshot; the browser never queries BigQuery.") +
      must("observer-only · real BQAA rows, dataset <code>okf_rfc_demo</code> not <code>adk_logs</code> · <code>context_ref</code> is the only handle on the tool span · no SQL, no paths, no <code>concept_version_id</code>") +
      '<div class="cols">' +
      '<div class="pane telemetry"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--telemetry)"></span>agent_events · ' + esc(M.session_id) + '</span><span class="m">live snapshot · click a row for the raw BQ row</span></div>' +
      '<div class="pane-b"><ul class="events">' + list + "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">What the observer wrote</span><span class="m">and what it never wrote</span></div><div class="pane-b">' +
      '<dl class="facts">' +
      "<dt>dataset</dt><dd><code>" + esc(M.project + "." + M.dataset) + "</code> · " + esc(M.dataset_location) + "</dd>" +
      "<dt>table</dt><dd><code>" + esc(M.table) + "</code> · " + L.rows.length + " rows for this session</dd>" +
      "<dt>agent</dt><dd><code>" + esc(M.agent) + "</code> · google-adk · <code>" + esc(L.model) + "</code> · Vertex " + esc(M.vertex_location) + "</dd>" +
      "<dt>session_id</dt><dd><code>" + esc(M.session_id) + "</code></dd>" +
      "<dt>trace_id</dt><dd><code>" + esc(M.trace_id) + "</code></dd>" +
      "<dt>window</dt><dd>" + (L.span ? esc(tsLive(L.span.first)) + " → " + esc(tsLive(L.span.last)) + " UTC · " + esc(M.ran_at.slice(0, 10)) : "—") + "</dd>" +
      "<dt>event types</dt><dd>" + histHtml + "</dd>" +
      "<dt>tool</dt><dd><code>" + esc(L.toolName) + "</code> · TOOL_STARTING + TOOL_COMPLETED · args <code>context_ref</code> only</dd>" +
      "<dt>context_ref</dt><dd><code>" + esc(M.context_ref) + "</code></dd>" +
      "<dt>publication</dt><dd>on the tool result: <code>" + esc(short(L.toolResult.publication_id || "", 23)) + "</code> · derived, not authored</dd>" +
      "</dl>" +
      '<div class="live-links">' + link(M.bq_console, "bq", "Open the table in the BigQuery console") + "</div>" +
      '<p class="beat-kicker" style="margin:12px 0 6px">Never-emit scan · every live row</p>' +
      '<ul class="checklist">' + checks +
      check(L.sessionOk, "All " + L.rows.length + " rows carry session <code>" + esc(short(M.session_id, 8)) + "</code> and trace <code>" + esc(short(M.trace_id, 8)) + "</code>") +
      check(L.argsOnlyRef && L.violations.length === 0, "Tool args = {<code>context_ref</code>} only; tool result keys ∩ never-emit = ∅") +
      info("<code>user_id</code> is a BQAA row column, not an agent-facing field. In this run it is the demo pseudonym <code>" + esc(L.userIds.join(", ")) + "</code>; it never appears on the tool args or result.") +
      info("The observer captured the prompt and the agent instruction as content. Neither contains SQL, parameter values, bundle paths or <code>concept_version_id</code>.") +
      "</ul></div></div></div>" +
      renderFixtureTrace();
  }

  // The synthetic fixture trace: still the adapter input, no longer the proof.
  function fixtureSummary(e) {
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
  function renderFixtureTrace() {
    var t = D.trace, obs = D.adapted.observation;
    var keyset = A.keysDeep(t.events);
    var nullUsers = t.events.every(function (e) { return e.user_id === null; });
    var never = ["concept_version_id", "bundle_path", "source_path", "principal", "query_text", "sql", "parameter_values", "destination_table"];
    var list = t.events.map(function (e, i) {
      return '<li class="ev"><button type="button" aria-expanded="false" data-ev="f' + i + '">' +
        '<span class="ts">' + tsShort(e.timestamp) + "</span>" +
        '<span class="ty ' + evClass(e) + '">' + esc(e.event_type) + "</span>" +
        '<span class="sm">' + fixtureSummary(e) + "</span>" +
        '<span class="car">▸</span></button>' +
        '<div class="raw" hidden>' + pre(e, ["context_ref", "user_id"]) + "</div></li>";
    }).join("");
    var checks = never.map(function (k) { return check(!keyset[k], "<code>" + k + "</code> " + (keyset[k] ? "present as a key" : "absent from every event key")); }).join("");
    return '<details class="nn fixture"><summary>Adapter input · synthetic fixture trace <code>traces/bqaa-germany.json</code> · ' + t.events.length + ' events · not live</summary><div class="nn-b">' +
      '<p class="fixture-note">This is the labelled synthetic observation the one-way adapter reads in beat 2 to emit the derived bundle. It was never written to a table. The live session above consumed the publication that this fixture produced.</p>' +
      '<div class="cols"><div class="pane telemetry"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--telemetry)"></span>' + esc(t.table) + ' · ' + esc(obs.session_id) + '</span><span class="m">synthetic · ' + esc(t.writer.plugin) + "</span></div>" +
      '<div class="pane-b"><ul class="events">' + list + "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">Never-emit scan · fixture</span><span class="m">every event key</span></div><div class="pane-b"><ul class="checklist">' + checks +
      check(nullUsers, "<code>user_id</code> is <code>null</code> on all " + t.events.length + " fixture events") +
      "</ul></div></div></div></div></details>";
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
    var ad = D.adapted, obs = ad.observation, d = D.derived, a = D.authored, L = D.live;
    if (!selectedFile) selectedFile = "computations/active-customer-revenue-by-region-and-quarter.md";
    if (!ad.files[selectedFile]) selectedFile = Object.keys(ad.files)[0];
    var mdFiles = Object.keys(ad.files).filter(function (p) { return /\.md$/.test(p) && p !== "log.md"; });
    var typed = mdFiles.filter(function (p) { return /^type: \S/m.test(ad.files[p]); }).length;
    var keysUsed = {};
    mdFiles.forEach(function (p) { H.splitFrontmatter(ad.files[p]).frontmatter.split("\n").forEach(function (ln) { var m = ln.match(/^([a-z_]+):/); if (m) keysUsed[m[1]] = true; }); });
    return beatHead(2, "source", "Adapt", "One-way adapter. Observer events in, a derived bundle out, its own identity chain. The live session consumed exactly that publication.",
      "<code>" + esc(A.ADAPTER_VERSION) + "</code> reads the " + obs.event_count + "-event fixture observation and emits <b>" + Object.keys(ad.files).length + " files</b> under <code>" + esc(ad.bundle_key) + "</code>. The browser recomputes the derived triple now, and the live tool result in <code>okf_rfc_demo.agent_events</code> carries the same <code>publication_id</code>. The authored bundle is neither read nor written.") +
      must("banner derived/demo · distinct <code>bundle_key</code> · own observation / snapshot / publication triple · live tool result binds to this publication · <code>okf-phase0-mvp/fixture/bundle</code> untouched") +
      '<div class="flow">' +
      '<div class="box t"><b>in · fixture observation</b>' + obs.event_count + " synthetic events · session <code>" + esc(obs.session_id) + "</code><br>6 retrieved + 1 excluded item · 1 receipt · 1 edge</div>" +
      '<div class="arrow"><b>→</b>one-way<br>observe · adapt · hash</div>' +
      '<div class="box d"><b>out · derived OKF v0.2 bundle</b><code>' + esc(ad.bundle_key) + "</code> · " + Object.keys(ad.files).length + " files<br>publication <code>" + short(d.publication_id, 23) + "</code></div>" +
      '<div class="arrow"><b>→</b>consumed live<br>by context_ref</div>' +
      '<div class="box l"><b>live · BQAA session</b><code>' + esc(short(L.meta.session_id, 13)) + "</code> · " + L.rows.length + " real rows<br><code>" + esc(L.meta.context_ref) + "</code></div>" +
      "</div>" +
      '<p class="fixture-note">The leadership proof is the live session, not the synthetic Germany fixture. The fixture is the adapter’s input and stays labelled synthetic; the publication it yields is what the real agent looked up.</p>' +
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
      "<dt>live context_ref</dt><dd><code>" + esc(L.meta.context_ref) + "</code> = <code>okf:env-demo#</code> + first 12 hex of the publication</dd>" +
      "</dl>" +
      '<ul class="checklist">' +
      check(D.match, "Browser hash = pinned <code>derived/identities.json</code> = Python re-derivation (<code>tools/derived_vectors.py</code>)") +
      check(L.pubMatch, "Live <code>TOOL_COMPLETED.result.publication_id</code> = the publication computed in this browser") +
      check(L.refMatch, "Live <code>context_ref</code> on args and result = <code>okf:env-demo#</code> + prefix of that publication (<code>tools/check_live_trace.py</code>)") +
      '<li class="ok"><span class="ic">✓</span><span>Same <code>hash.js</code> reproduces the authored golden triple and all 9 authored concept versions (<code>tools/check-authored-identities.mjs</code>)</span></li>' +
      check(D.distinct, "Distinct from authored <code>" + esc(a.inputs.bundle_key) + "</code> · pub <code>" + short(a.publication_id, 16) + "</code> stays pinned and unchanged") +
      '<li class="ok"><span class="ic">✓</span><span>Adapter reads 0 authored files; writes 0 authored files. The live agent read 0 files at all: one tool, one <code>context_ref</code>.</span></li>' +
      check(typed === mdFiles.length, "Frontmatter <code>type</code> on " + typed + "/" + mdFiles.length + " non-reserved <code>.md</code>; <code>log.md</code> reserved") +
      info("Zero new required keys. Keys used: " + Object.keys(keysUsed).sort().map(function (k) { return "<code>" + k + "</code>"; }).join(" ")) +
      info("No <code>computation:</code> artifact in the derived stub — the observer never sees SQL. It cites the authored <code>computation_version_id</code> under <code>sources</code>.") +
      "</ul></div></div></div>";
  }

  // ---- beat 3: project ---------------------------------------------------
  function renderProject() {
    var ad = D.adapted, d = D.derived, obs = ad.observation, L = D.live, M = L.meta;
    var pub = d.publication_id, snap = d.snapshot_id;
    var docs = Object.keys(ad.files).filter(function (p) { return /\.md$/.test(p) && p !== "log.md"; }).sort();
    function fm(p, key) { var m = ad.files[p].match(new RegExp("^" + key + ": (.+)$", "m")); return m ? m[1] : ""; }
    var cards = docs.map(function (p) {
      var type = fm(p, "type"), title = fm(p, "title"), status = fm(p, "status");
      var isComp = type === "Attested Computation";
      var params = isComp ? (obs.receipt ? obs.receipt.parameter_schema.map(function (x) { return x.name; }).join(", ") : "") : "";
      return '<div class="card"><div class="ch"><span class="name">' + esc(title) + '</span><span class="etype">okf-concept · derived view</span></div>' +
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
    var kcCard =
      '<div class="live-card catalog"><div class="lh"><b>' + esc(M.kc_entry_id) + '</b><span class="tag">Dataplex entry · live</span></div>' +
      '<div class="pins">' +
      '<span class="pin"><b>entry group</b> ' + esc(M.kc_entry_group) + "</span>" +
      '<span class="pin"><b>location</b> ' + esc(M.kc_location) + "</span>" +
      '<span class="pin"><b>project</b> ' + esc(M.project) + "</span>" +
      '<span class="pin pub"><b>okf.publication_id</b> ' + esc(short(pub, 19)) + "</span>" +
      '<span class="pin"><b>okf.provenance</b> bqaa observer · derived / demo</span>' +
      "</div>" +
      '<p class="res"><code>' + esc(M.kc_entry) + "</code></p>" +
      '<div class="live-links">' + link(M.kc_console, "kc", "Find the entry in Dataplex") + "</div></div>";
    var bqCard =
      '<div class="live-card runtime"><div class="lh"><b>' + esc(M.dataset + "." + M.table) + '</b><span class="tag">BigQuery table · live</span></div>' +
      '<div class="pins">' +
      '<span class="pin"><b>project</b> ' + esc(M.project) + "</span>" +
      '<span class="pin"><b>location</b> ' + esc(M.dataset_location) + "</span>" +
      '<span class="pin"><b>writer</b> BigQueryAgentAnalyticsPlugin</span>' +
      '<span class="pin"><b>rows · session</b> ' + L.rows.length + " · " + esc(short(M.session_id, 8)) + "</span>" +
      '<span class="pin pub"><b>publication on tool result</b> ' + esc(short(L.toolResult.publication_id || "", 19)) + "</span>" +
      "</div>" +
      '<p class="res"><code>' + esc(L.table) + "</code></p>" +
      '<div class="live-links">' + link(M.bq_console, "bq", "Open the table in BigQuery") + "</div></div>";
    return beatHead(3, "split", "Project", "Two stores, one publication. A real Dataplex entry for discovery, a real BigQuery table for serving.",
      "The derived publication is what both stores point at. <b style=\"color:var(--catalog)\">Knowledge Catalog</b> holds the live entry <code>okf-derived-germany</code> in entry group <code>okf-rfc-demo</code>; <b style=\"color:var(--runtime)\">BigQuery</b> holds the live <code>okf_rfc_demo.agent_events</code> rows whose tool result names the publication. Below each live card, the in-browser projection of the derived bundle is shown as a labelled derived view: no <code>kcmd</code> write, no DML from this page.") +
      must("real Dataplex entry + console link · real BigQuery table + console link · same <code>publication_id</code> on both panes · in-browser views labelled derived") +
      '<div class="cols even">' +
      '<div class="pane catalog"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--catalog)"></span>Knowledge Catalog · discovery</span><span class="m">live entry first · derived view below</span></div>' +
      '<div class="pane-b">' + kcCard + '<p class="sub-h">derived view · in-browser projection of the bundle · not written to Catalog</p><div class="cards">' + cards + "</div></div></div>" +
      '<div class="pane runtime"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--runtime)"></span>BigQuery · serving</span><span class="m">live table first · derived view below</span></div>' +
      '<div class="pane-b">' + bqCard + '<p class="sub-h">derived view · RFC projection shape · not a live table</p>' + table("publications", pubRow) + table("deployment_heads", headRow, "head advanced") + table("nodes_current", nodes, "one row per concept version") + table("edges_current", edges) + "</div></div>" +
      '<div class="seam-note"><span>Catalog <code>okf.publication_id</code> ' + esc(short(pub, 23)) + '</span><span class="eq">' + (same && L.pubMatch ? "=" : "≠") + '</span><span>BigQuery <code class="rt">tool result publication_id</code> ' + esc(short(L.toolResult.publication_id || "", 23)) + "</span><span>· " + (same && L.pubMatch ? "same publication on both stores ✓" : "MISMATCH") + "</span></div>" +
      "</div>";
  }

  // ---- beat 4: consume (live) ---------------------------------------------
  function renderConsume() {
    var L = D.live, M = L.meta;
    var ok = L.violations.length === 0;
    var ref = M.context_ref;
    var call = L.llmRes[0] && L.llmRes[0].content || {};
    var fin = L.llmRes[L.llmRes.length - 1] && L.llmRes[L.llmRes.length - 1].content || {};
    var py =
      '<span class="cm"># live/run_okf_agent.py — the agent that wrote the rows above (excerpt)</span>\n' +
      '<span class="kw">from</span> google.adk.agents <span class="kw">import</span> Agent\n' +
      '<span class="kw">from</span> google.adk.models <span class="kw">import</span> Gemini\n' +
      '<span class="kw">from</span> google.adk.plugins.bigquery_agent_analytics_plugin <span class="kw">import</span> BigQueryAgentAnalyticsPlugin\n\n' +
      'MODEL = os.environ.get(<span class="st">"DEMO_MODEL_ID"</span>, <span class="st hl">"gemini-3.8-flash"</span>)\n\n' +
      '<span class="kw">def</span> lookup_okf_context(context_ref: str) -> dict:\n' +
      '    <span class="cm"># never returns concept_version_id, paths, principal or query text</span>\n' +
      '    <span class="kw">return</span> {<span class="st">"ok"</span>: True, <span class="st">"context_ref"</span>: context_ref, <span class="st">"publication_id"</span>: PUBLICATION_ID,\n' +
      '            <span class="st">"note"</span>: <span class="st">"derived/demo bundle; not canonical authoring"</span>}\n\n' +
      'root_agent = Agent(name=<span class="st">"okf_rfc_consume_agent"</span>, model=Gemini(model=MODEL),\n' +
      '                   tools=[lookup_okf_context], instruction=<span class="st">"Cite only context_ref. …"</span>)\n' +
      'bq_plugin = BigQueryAgentAnalyticsPlugin(project_id=PROJECT, dataset_id=<span class="st">"okf_rfc_demo"</span>,\n' +
      '                                        table_id=<span class="st">"agent_events"</span>, location=<span class="st">"US"</span>)';
    var answerHtml = esc(L.answerText).split(esc(ref)).join('<span class="cite">' + esc(ref) + "</span>");
    return beatHead(4, "ink", "Consume", "A real ADK agent on <code>gemini-3.8-flash</code> looked up the derived context by <code>context_ref</code> and answered. This is the live transcript, not a replay.",
      "Every turn below is reconstructed from the live <code>agent_events</code> rows for session <code>" + esc(short(M.session_id, 13)) + "</code>. The agent declared one tool, <code>" + esc(L.toolName) + "</code>, called it with <code>context_ref</code> only, and received a result that names the derived publication and nothing from the never-emit list. No receipt was minted in this run and nothing here is attested.") +
      must("real model call, real BQAA rows · tool args = {<code>context_ref</code>} · result keys ∩ never-emit = ∅ · no ATTESTED claim · model stays <code>gemini-3.8-flash</code>") +
      '<div class="adk">' +
      '<div class="adk-h"><span class="agent"><span class="fw">google-adk · live</span><b>' + esc(M.agent) + "</b><span>session " + esc(M.session_id) + '</span></span>' +
      '<span class="model-badge"><span class="dot"></span>model · <b>' + esc(L.model) + "</b> · Vertex " + esc(M.vertex_location) + "</span></div>" +
      '<div class="adk-b"><div class="transcript">' +
      turn("user", "user", '<div class="bubble user">' + esc(L.question) + "</div>") +
      turn("model", L.model, '<div class="bubble call">function_call → <b>' + esc(L.toolName) + "</b> " + esc(JSON.stringify(L.toolArgs)) + '<span class="usage">LLM_RESPONSE · ' + esc((call.usage || {}).prompt || 0) + " prompt / " + esc((call.usage || {}).completion || 0) + " completion tokens</span></div>") +
      turn("tool", "tool result", result(L.toolName, "TOOL_COMPLETED · live row", L.toolResult)) +
      turn("model", L.model, '<div class="bubble final">' + answerHtml + '<span class="usage">LLM_RESPONSE · ' + esc((fin.usage || {}).prompt || 0) + " prompt / " + esc((fin.usage || {}).completion || 0) + " completion tokens</span></div>") +
      "</div>" +
      '<div class="side">' +
      '<div class="tile"><div class="th">agent construction · <a href="live/run_okf_agent.py">live/run_okf_agent.py</a></div><pre class="py">' + py + "</pre></div>" +
      '<div class="tile"><div class="th">never-emit assertion · live tool args + result</div><div class="big ' + (ok ? "ok" : "warn") + '">keys ∩ never-emit = ' + (ok ? "∅ ✓" : esc(L.violations.join(", "))) + "</div><p>" + L.scannedKeys + " distinct keys on the live payload scanned at render time against " + A.NEVER_EMIT.map(function (k) { return "<code>" + k + "</code>"; }).join(" ") + ".</p></div>" +
      '<div class="tile"><div class="th">receipt · this run</div><span class="verdict">NO RECEIPT · nothing executed, nothing attested</span><p>The agent retrieved context; it did not run a sanctioned computation, so no receipt exists for this session. The model’s own phrase “you can trust the number because it is verified” overstates: <b>nothing on this page is ATTESTED</b>. The only receipt in the demo is the Phase 0 golden specimen (<code>UNVERIFIABLE</code>, <code>phase0_no_execution_or_integrity_proof</code>), a fixture, shown below.</p></div>' +
      '<details class="nn"><summary>Fixture receipts · not from this run</summary><div class="nn-b"><span class="verdict">UNVERIFIABLE · phase0_no_execution_or_integrity_proof</span><p style="font-family:var(--display);font-size:13px;color:var(--ink-soft);margin:8px 0 0">Golden specimen <code>' + esc(D.receipt.receipt_id) + "</code>, bound to the authored publication. Integrity proof status <code>" + esc(D.receipt.integrity_proof.status) + '</code>.</p><span class="verdict att" style="margin-top:12px">ATTESTED · expected Phase 4 shape · non-normative</span><p style="font-family:var(--display);font-size:13px;color:var(--ink-soft);margin:8px 0 0">' + esc(D.phase4._fixture_note) + "</p>" + pre({ verdict: D.phase4.verdict, verdict_details_digest: D.phase4.verdict_details_digest, receipt_digest: D.phase4.receipt_digest, integrity_proof: D.phase4.integrity_proof }, [], "rounded") + "</div></details>" +
      "</div></div></div>" +
      renderFixtureReplay();
  }
  function renderFixtureReplay() {
    var t = D.trace, obs = D.adapted.observation;
    var ok = D.violations.length === 0;
    return '<details class="nn fixture"><summary>Prior fixture replay · synthetic transcript of <code>' + esc(t.agent.name) + '</code> · superseded by the live session above</summary><div class="nn-b">' +
      '<p class="fixture-note">Kept for comparison. This transcript was a fixture replay: no model was called and no rows were written. Its two-tool shape (<code>okf_retrieve_context</code>, <code>okf_run_attested_computation</code>) is the RFC target; the live run above exercised a single lookup tool.</p>' +
      '<div class="adk"><div class="adk-h"><span class="agent"><span class="fw">google-adk · fixture</span><b>' + esc(t.agent.name) + "</b><span>session " + esc(obs.session_id) + '</span></span><span class="model-badge"><span class="dot"></span>model · <b>gemini-3.8-flash</b> · replay</span></div>' +
      '<div class="adk-b"><div class="transcript">' +
      turn("user", "user", '<div class="bubble user">' + esc(obs.question) + "</div>") +
      turn("model", "gemini-3.8-flash", '<div class="bubble call">function_call → <b>' + esc(D.retrieveCall.name) + "</b> " + esc(JSON.stringify(D.retrieveCall.args)) + "</div>") +
      turn("tool", "tool result", result("okf_retrieve_context", "derived publication · context_ref", D.retrieveResult)) +
      turn("model", "gemini-3.8-flash", '<div class="bubble call">function_call → <b>' + esc(D.computeCall.name) + "</b> " + esc(JSON.stringify(D.computeCall.args)) + "</div>") +
      turn("tool", "tool result", result("okf_run_attested_computation", "golden receipt · UNVERIFIABLE", D.computeResult)) +
      turn("model", "gemini-3.8-flash", '<div class="bubble final">' + esc(D.finalText).replace(esc("okf:" + D.envId + "#2"), '<span class="cite">' + esc("okf:" + D.envId + "#2") + "</span>") + "</div>") +
      "</div>" +
      '<div class="side"><div class="tile"><div class="th">never-emit assertion · fixture tool results</div><div class="big ' + (ok ? "ok" : "warn") + '">keys ∩ never-emit = ' + (ok ? "∅ ✓" : esc(D.violations.join(", "))) + "</div><p>" + D.scannedKeys + " distinct keys scanned.</p></div></div>" +
      "</div></div></div></details>";
  }
  function turn(cls, who, inner) { return '<div class="turn"><span class="who ' + cls + '">' + esc(who) + "</span>" + inner + "</div>"; }
  function result(name, label, obj) {
    return '<div class="bubble result"><div class="rh"><span>' + esc(name) + "</span><span>" + esc(label) + "</span></div>" + pre(obj, ["context_ref", "publication_id", "verdict", "verdict_reason"]) + "</div>";
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
