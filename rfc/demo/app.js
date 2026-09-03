/* BQAA → derived OKF — static viewer of the SDK CLI path. Vanilla JS, no build.
   Source of truth: one stdlib run of `python examples/okf_bqaa_adapter/run.py`
   (okf-bqaa-adapter:v0, SDK PR 474 HEAD 476d37dc) over the committed export of
   the live ADK observe session f21ee192-… (okf_rfc_observe_agent,
   gemini-3.8-flash, 180 agent_events rows). This page renders the committed
   snapshot, the pinned identities and the CLI transcript. It does not hash,
   adapt or resolve anything for the live identities and never calls GCP.
   hash.js / adapter.js are loaded only for the labelled SYNTHETIC germany
   hashing check, collapsed under beat 1 and never the demo input. */
(function () {
  "use strict";

  var A = window.OkfBqaaAdapter; // synthetic hashing check only
  var H = window.OkfHash;        // synthetic hashing check only
  var TOTAL = 4;
  var current = 1;
  var D = null;   // committed observe snapshot + CLI transcript + golden
  var X = null;   // labelled extras: prior consume experiment, synthetic germany check
  var PR_URL = "https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/474";
  var PR_HEAD = "476d37dc9d4210a335c2f77e78003f6a5ebe2878";
  var BQ_CONSOLE = "https://console.cloud.google.com/bigquery?project=test-project-0728-467323&ws=!1m5!1m4!4m3!1stest-project-0728-467323!2sokf_rfc_demo!3sagent_events";
  var NEVER_EMIT = ["concept_version_id", "bundle_path", "source_path", "principal", "user_id", "query_text", "sql", "parameter_values", "destination_table"];
  var TYPE_BY_DIR = { computations: "Attested Computation", concepts: "Business Concept", metrics: "Metric", policies: "Policy", tables: "BigQuery Table" };

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
    return esc(text).replace(/("(?:[^"\\]|\\.)*")(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g, function (m, str, colon, bool, num) {
      if (str !== undefined) {
        if (colon !== undefined) {
          var key = str.slice(1, -1);
          return '<span class="' + (hlKeys.indexOf(key) >= 0 ? "k hl" : "k") + '">' + str + "</span>" + colon;
        }
        return '<span class="s">' + str + "</span>";
      }
      if (bool !== undefined) return '<span class="b">' + bool + "</span>";
      return '<span class="n">' + num + "</span>";
    });
  }
  function pre(obj, hlKeys, cls) { return '<pre class="json ' + (cls || "") + '">' + jsonHtml(obj, hlKeys) + "</pre>"; }
  function tsLive(ts) { return String(ts).replace("T", " ").slice(11, 19); }
  function link(href, cls, label) { return '<a class="lk ' + (cls || "") + '" href="' + esc(href) + '" target="_blank" rel="noopener">' + label + " ↗</a>"; }
  function fetchJson(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.json(); }); }
  function fetchText(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.text(); }); }
  function fetchBytes(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.arrayBuffer(); }).then(function (b) { return new Uint8Array(b); }); }
  function parseMaybe(v) { if (typeof v === "string") { try { return JSON.parse(v); } catch (e) { return v; } } return v; }
  function keysDeep(obj, out) {
    out = out || {};
    if (Array.isArray(obj)) obj.forEach(function (v) { keysDeep(v, out); });
    else if (obj && typeof obj === "object") Object.keys(obj).forEach(function (k) { out[k] = true; keysDeep(obj[k], out); });
    return out;
  }
  function slug(title) { return String(title).toLowerCase().replace(/\(legacy\)/, "legacy").replace(/[^a-z0-9]+/g, "-").replace(/^-|-$/g, ""); }
  function check(ok, html) { return '<li class="' + (ok ? "ok" : "no") + '"><span class="ic">' + (ok ? "✓" : "✕") + "</span><span>" + html + "</span></li>"; }
  function info(html) { return '<li class="info"><span class="ic">i</span><span>' + html + "</span></li>"; }

  // ---- load: the committed CLI run ------------------------------------------
  Promise.all([
    fetchJson("live/observe/live.json"),
    fetchJson("live/observe/live_identities.json"),
    fetchJson("live/observe/snapshot.json"),
    fetchJson("live/observe/mapping.json"),
    fetchText("cli/okf-bqaa-cli-transcript.txt"),
    fetchJson("fixture/golden/identities.json"),
    fetchJson("fixture/golden/receipt.json"),
    fetchJson("fixture/golden/expected-phase4-receipt.json")
  ]).then(function (res) {
    D = { live: res[0], ident: res[1], snap: res[2], mapping: res[3], transcript: res[4], authored: res[5], receipt: res[6], phase4: res[7] };
    D.cli = parseTranscript(D.transcript);
    D.obs = prepObserve(D.snap, D.live);
    D.bundle = prepBundle(D.ident, D.obs);
    D.checks = crossChecks();
    renderIdentity();
    renderLiveStrip();
    render();
    loadExtras();
  }).catch(function (err) {
    stage.innerHTML =
      '<div class="error-box"><b>Could not load the static files.</b> ' + esc(err.message) +
      '<p style="margin-top:10px">Browsers block <code>fetch()</code> over <code>file://</code>. Serve the repo root instead: <code>python3 -m http.server 8000</code> then open <code>http://localhost:8000/rfc/demo/</code>.</p></div>';
    ["a-status", "d-status", "live-status"].forEach(function (id) { var el = document.getElementById(id); if (el) { el.textContent = "not loaded"; el.className = "status warn"; } });
  });

  // Labelled extras. Neither is the demo input; both render collapsed.
  function loadExtras() {
    var MANIFESTS = ["canonicalization-manifest", "semantic-config", "resolver-manifest", "vocabulary-manifest"];
    X = { prior: null, germany: null };
    var prior = Promise.all([fetchJson("live/live.json"), fetchJson("live/agent_events.json")]).then(function (r) {
      X.prior = prepPrior(r[0], r[1]); // prior live-GCP consume experiment
    }).catch(function () { X.prior = null; });
    var germany = Promise.all([
      fetchJson("traces/bqaa-germany.json"),
      fetchJson("derived/identities.json"),
      Promise.all(MANIFESTS.map(function (n) { return fetchBytes("fixture/golden/manifests/" + n + ".json"); }))
    ]).then(function (r) {
      var manifests = {};
      MANIFESTS.forEach(function (n, i) { manifests[n] = r[2][i]; });
      var adapted = A.adapt(r[0]);
      var hashed = A.computeIdentities(adapted.files, adapted.constants, manifests);
      var pinned = r[1];
      X.germany = { // SYNTHETIC hashing-only
        trace: r[0], adapted: adapted, hashed: hashed, pinned: pinned,
        match: ["observation_id", "snapshot_id", "publication_id"].every(function (k) { return hashed[k] === pinned[k]; })
      };
    }).catch(function () { X.germany = null; });
    Promise.all([prior, germany]).then(function () { if (D) render(); });
  }

  // ---- transcript ---------------------------------------------------------
  function parseTranscript(text) {
    var blocks = [], cur = null, header = [];
    text.split("\n").forEach(function (ln) {
      if (/^\$ /.test(ln)) { cur = { cmd: ln.slice(2), out: [] }; blocks.push(cur); return; }
      if (!cur) { header.push(ln); return; }
      cur.out.push(ln);
    });
    var kv = {};
    (blocks[0] ? blocks[0].out : []).forEach(function (ln) { var m = ln.match(/^([A-Z_]+) (.*)$/); if (m) kv[m[1]] = m[2]; });
    var lookupJson = null;
    if (blocks[1]) { try { lookupJson = JSON.parse(blocks[1].out.join("\n")); } catch (e) { lookupJson = null; } }
    var junk = blocks[2] ? blocks[2].out.filter(function (l) { return l; }) : [];
    return { header: header.filter(function (l) { return l; }), blocks: blocks, kv: kv, lookup: lookupJson, junk: junk };
  }
  function transcriptHtml(blocks, hl) {
    hl = hl || {};
    var out = [];
    blocks.forEach(function (b, i) {
      if (i) out.push("");
      out.push('<span class="cmd">$ ' + esc(b.cmd) + "</span>");
      b.out.forEach(function (ln) {
        if (/^#/.test(ln)) { out.push('<span class="cm">' + esc(ln) + "</span>"); return; }
        if (/^FAIL_CLOSED/.test(ln)) { out.push('<span class="fail">' + esc(ln) + "</span>"); return; }
        var m = ln.match(/^([A-Z_]+) (.*)$/);
        if (m) {
          var v = m[2], cls = hl[m[1]] === v ? "v hl" : "v";
          out.push('<span class="key">' + esc(m[1]) + '</span> <span class="' + cls + '">' + esc(v) + "</span>");
          return;
        }
        out.push(esc(ln).replace(/&quot;(sha256:[0-9a-f]+)&quot;/, '&quot;<span class="v hl">$1</span>&quot;').replace(/&quot;(okf:env-[a-z]+#[0-9a-f]+)&quot;/, '&quot;<span class="v hl">$1</span>&quot;'));
      });
    });
    return '<pre class="cli">' + out.join("\n") + "</pre>";
  }

  // ---- observe snapshot -----------------------------------------------------
  function prepObserve(snap, live) {
    var order = ["USER_MESSAGE_RECEIVED", "INVOCATION_STARTING", "AGENT_STARTING", "LLM_REQUEST", "LLM_RESPONSE", "TOOL_STARTING", "TOOL_COMPLETED", "AGENT_COMPLETED", "INVOCATION_COMPLETED"];
    var hist = snap.histogram || {};
    var types = order.filter(function (k) { return k in hist; }).concat(Object.keys(hist).filter(function (k) { return order.indexOf(k) < 0; }));
    var sum = types.reduce(function (s, k) { return s + hist[k]; }, 0);
    var samples = (snap.sample_events || []).map(function (e) { var o = {}; Object.keys(e).forEach(function (k) { o[k] = e[k]; }); o.content = parseMaybe(e.content); return o; });
    var tool = samples.filter(function (e) { return e.event_type === "TOOL_COMPLETED" && e.content && e.content.result; })[0] || null;
    var result = tool ? tool.content.result : {};
    var contentKeys = keysDeep(samples.map(function (e) { return e.content; }));
    var never = snap.never_emit || NEVER_EMIT;
    var scan = never.filter(function (k) { return k !== "user_id"; });
    var traces = samples.map(function (e) { return e.trace_id; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
    return {
      hist: hist, types: types, sum: sum, max: Math.max.apply(null, types.map(function (k) { return hist[k]; })),
      samples: samples, tool: tool, result: result, okf: result.okf || {},
      never: never, scan: scan,
      violations: scan.filter(function (k) { return contentKeys[k]; }),
      scanned: Object.keys(contentKeys).length,
      sessionOk: samples.length > 0 && samples.every(function (e) { return e.session_id === live.session_id && e.agent === live.agent; }),
      traces: traces,
      userIds: samples.map(function (e) { return e.user_id; }).filter(function (v, i, a) { return a.indexOf(v) === i; }),
      question: (samples.filter(function (e) { return e.event_type === "USER_MESSAGE_RECEIVED"; })[0] || { content: {} }).content.text_summary || "",
      invocations: hist.INVOCATION_STARTING || 0,
      span: samples.length ? { first: samples[0].timestamp, last: samples[samples.length - 1].timestamp } : null
    };
  }

  // The 8 derived files: names + hashes from live_identities.json; titles from the observed OKF envelope.
  function prepBundle(ident, obs) {
    var titles = {};
    (obs.okf.items || []).forEach(function (it) { titles[slug(it.title)] = { title: it.title, type: it.type, status: "draft", rank: it.rank }; });
    (obs.okf.excluded || []).forEach(function (it) { titles[slug(it.title)] = { title: it.title, type: it.type, status: "deprecated", reason: it.reason }; });
    var files = Object.keys(ident.file_sha256).sort().map(function (p) {
      var dir = p.indexOf("/") >= 0 ? p.split("/")[0] : "(root)";
      var name = p.split("/").pop().replace(/\.md$/, "");
      var t = titles[name] || {};
      return {
        path: p, dir: dir, name: name,
        type: p === "log.md" ? "reserved" : (t.type || TYPE_BY_DIR[dir] || ""),
        title: t.title || name, status: t.status || (p === "log.md" ? "" : "draft"), rank: t.rank, reason: t.reason,
        sha256: ident.file_sha256[p], cvid: ident.concept_version_ids[p] || null
      };
    });
    return { files: files, docs: files.filter(function (f) { return f.path !== "log.md"; }) };
  }

  function crossChecks() {
    var kv = D.cli.kv, live = D.live, ident = D.ident, map = D.mapping.mapping || {};
    return {
      session: kv.SESSION === live.session_id && ident.inputs.session_id === live.session_id,
      trace: kv.TRACE === live.trace_id && ident.inputs.trace_id === live.trace_id,
      table: kv.TABLE === live.table,
      model: kv.MODEL === live.model && live.model === "gemini-3.8-flash",
      ref: kv.CONTEXT_REF === live.context_ref && live.receipt_context_ref === live.context_ref,
      obs: kv.OBSERVATION_ID === ident.observation_id,
      snap: kv.SNAPSHOT_ID === ident.snapshot_id,
      pub: kv.PUBLICATION_ID === ident.publication_id && D.snap.identities.publication_id === ident.publication_id,
      files: Number(kv.FILES) === Object.keys(ident.file_sha256).length,
      mapping: map[live.context_ref] === ident.publication_id && Object.keys(map).length === 1,
      lookup: !!D.cli.lookup && D.cli.lookup.context_ref === live.context_ref && D.cli.lookup.publication_id === ident.publication_id && D.cli.lookup.label === "derived/demo",
      junk: D.cli.junk.some(function (l) { return /^FAIL_CLOSED/.test(l) && l.indexOf("okf:env-junk#deadbeef") >= 0; }) && D.cli.junk.some(function (l) { return /exit 2/.test(l); }),
      receipt: /^UNVERIFIABLE rcpt-observe-noexec$/.test(kv.RECEIPT || ""),
      count: live.event_count === 180 && D.obs.sum === 180 && D.snap.event_count === 180,
      distinct: ident.publication_id !== D.authored.publication_id && ident.inputs.bundle_key !== D.authored.inputs.bundle_key,
      adapter: kv.ADAPTER === "okf-bqaa-adapter:v0" && ident.inputs.adapter_version === "okf-bqaa-adapter:v0" && D.mapping.adapter_version === "okf-bqaa-adapter:v0",
      lookupNever: NEVER_EMIT.filter(function (k) { return D.cli.lookup && k in D.cli.lookup; }).length === 0
    };
  }
  function allOk() { var c = D.checks; return Object.keys(c).every(function (k) { return c[k]; }); }

  // ---- strips ---------------------------------------------------------------
  function renderLiveStrip() {
    var st = document.getElementById("live-status");
    if (!st) return;
    var ok = D.checks.count && D.checks.session && D.checks.ref && D.obs.violations.length === 0;
    st.textContent = ok ? "snapshot loaded ✓ · " + D.live.event_count + " events · transcript agrees" : "snapshot mismatch — see beat 1";
    st.className = "status " + (ok ? "ok" : "warn");
  }
  function renderIdentity() {
    var a = D.authored, d = D.ident;
    document.getElementById("a-obs").textContent = a.observation_id;
    document.getElementById("a-snap").textContent = a.snapshot_id;
    document.getElementById("a-pub").textContent = a.publication_id;
    document.getElementById("d-obs").textContent = d.observation_id;
    document.getElementById("d-snap").textContent = d.snapshot_id;
    document.getElementById("d-pub").textContent = d.publication_id;
    var as = document.getElementById("a-status"); as.textContent = "pinned · display only"; as.className = "status ok";
    var ds = document.getElementById("d-status");
    var ok = D.checks.obs && D.checks.snap && D.checks.pub && D.checks.distinct;
    ds.textContent = ok ? "pinned from CLI · okf-bqaa-adapter:v0 · = transcript ✓ · distinct from authored" : "pinned from CLI · MISMATCH vs transcript";
    ds.className = "status " + (ok ? "ok" : "warn");
  }

  // ---- beat 1: observe --------------------------------------------------------
  function sampleSummary(e) {
    var c = e.content || {};
    switch (e.event_type) {
      case "USER_MESSAGE_RECEIVED": return "user asks: “" + esc(c.text_summary || "") + "”";
      case "LLM_RESPONSE": return /call: /.test(c._truncated || "") ? "→ call <b>" + esc((c._truncated.match(/call: ([a-z_]+)/) || [])[1] || "") + "</b> · usage on the row" : "model turn";
      case "TOOL_STARTING": return esc(c.tool) + " starting";
      case "TOOL_COMPLETED": return esc(c.tool) + " completed · <span class=\"ref\">" + esc((c.result || {}).context_ref || "") + "</span> · " + ((c.result || {}).okf ? ((c.result.okf.items || []).length + " items, " + (c.result.okf.excluded || []).length + " excluded") : "");
      case "AGENT_COMPLETED": return "agent completed";
      case "INVOCATION_COMPLETED": return "invocation completed · trace <code>" + esc(short(e.trace_id, 12)) + "</code>";
      default: return esc(e.event_type);
    }
  }
  function evClass(e) {
    if (e.status === "ERROR") return "err";
    if (/^TOOL_/.test(e.event_type)) return "tool";
    if (/^(USER_MESSAGE|AGENT_RESPONSE)/.test(e.event_type)) return "hitl";
    return "";
  }
  function histogramHtml(o) {
    return '<div class="hist" role="img" aria-label="Event type histogram, ' + o.sum + ' rows">' + o.types.map(function (k) {
      var n = o.hist[k], w = Math.round(100 * n / o.max);
      return '<div class="hrow" title="' + esc(k) + " · " + n + ' rows"><span class="hk">' + esc(k) + '</span><span class="hb"><span class="hf" style="width:' + w + '%"></span></span><span class="hn">' + n + "</span></div>";
    }).join("") + '<div class="hsum"><span>' + o.types.length + " event types</span><span>Σ = " + o.sum + "</span></div></div>";
  }
  function renderObserve() {
    var M = D.live, o = D.obs, snap = D.snap;
    var list = o.samples.map(function (e, i) {
      return '<li class="ev"><button type="button" aria-expanded="false" data-ev="' + i + '">' +
        '<span class="ts">' + esc(tsLive(e.timestamp)) + "</span>" +
        '<span class="ty ' + evClass(e) + '">' + esc(e.event_type) + "</span>" +
        '<span class="sm">' + sampleSummary(e) + "</span>" +
        '<span class="car">▸</span></button>' +
        '<div class="raw" hidden><p class="sub-h" style="margin:0 0 6px">sample row from the trimmed snapshot · JSON columns parsed, content_parts dropped · full export on PR 474</p>' + pre(e, ["context_ref", "publication_id", "session_id", "trace_id"]) + "</div></li>";
    }).join("");
    var checks = o.scan.map(function (k) {
      var present = o.violations.indexOf(k) >= 0;
      return check(!present, "<code>" + k + "</code> " + (present ? "present as a key" : "absent from every sample content key"));
    }).join("");
    return beatHead(1, "telemetry", "Observe", "A live ADK agent ran a multi-turn finance session. The observer wrote <b>180</b> rows; the adapter read nothing else.",
      "<code>" + esc(M.agent) + "</code> on <b><code>" + esc(M.model) + "</code></b> (Vertex <code>" + esc(M.vertex_location) + "</code>) answered " + o.invocations + " related questions in one session while the ADK <code>BigQueryAgentAnalyticsPlugin</code> appended <b>" + M.event_count + " rows</b> to <code>" + esc(M.table) + "</code>. The full export (" + Math.round(snap.export_bytes / 1024) + " KB, sha256 <code>" + esc(short(snap.export_sha256, 12)) + "</code>) is committed on SDK PR 474 and is the CLI's only input; this page carries a trimmed snapshot: the histogram, the identities and six sample rows.") +
      must("observer-only · real BQAA rows in <code>okf_rfc_demo</code>, session <code>" + esc(short(M.session_id, 8)) + "</code> · <code>context_ref</code> is the only handle on the tool result · no SQL, no paths, no <code>concept_version_id</code> · not the prior consume session, not the synthetic Germany trace") +
      '<div class="cols">' +
      '<div class="pane telemetry"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--telemetry)"></span>agent_events · ' + esc(M.session_id) + '</span><span class="m">trimmed snapshot · histogram of all 180 rows · six sample rows</span></div>' +
      '<div class="pane-b">' + histogramHtml(o) + '<p class="sub-h">sample rows · click to expand</p><ul class="events">' + list + "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">What the observer wrote</span><span class="m">and what it never wrote</span></div><div class="pane-b">' +
      '<dl class="facts">' +
      "<dt>table</dt><dd><code>" + esc(M.table) + "</code></dd>" +
      "<dt>agent</dt><dd><code>" + esc(M.agent) + "</code> · " + esc(snap.agent.framework) + " · <code>" + esc(M.model) + "</code> · Vertex " + esc(M.vertex_location) + "</dd>" +
      "<dt>session_id</dt><dd><code>" + esc(M.session_id) + "</code></dd>" +
      "<dt>trace_id</dt><dd><code>" + esc(M.trace_id) + "</code> · first of " + o.invocations + " invocations; pinned as the adapter <code>revision</code></dd>" +
      "<dt>event_count</dt><dd><b>" + M.event_count + "</b> · histogram Σ " + o.sum + "</dd>" +
      "<dt>ran_at</dt><dd><code>" + esc(M.ran_at) + "</code></dd>" +
      "<dt>first question</dt><dd>“" + esc(o.question) + "”</dd>" +
      "<dt>tools</dt><dd><code>" + esc((o.tool && o.tool.content.tool) || "okf_retrieve_context") + "</code> · result carries <code>kind</code>, <code>context_ref</code>, <code>okf</code> (titles, types, ranks, one exclusion, one edge)</dd>" +
      "<dt>context_ref</dt><dd><code>" + esc(M.context_ref) + "</code></dd>" +
      "<dt>full export</dt><dd>" + link(PR_URL, "pr", "SDK PR 474 · fixtures/live_observe_agent_events.json") + " <span class=\"sub-h\" style=\"display:inline;margin:0\">· do not merge · not padded · not dumped here</span></dd>" +
      "</dl>" +
      '<div class="live-links">' + link(BQ_CONSOLE, "bq", "Open the table in the BigQuery console") + "</div>" +
      '<p class="beat-kicker" style="margin:12px 0 6px">Never-emit scan · sample content keys</p>' +
      '<ul class="checklist">' + checks +
      check(o.sessionOk, "All " + o.samples.length + " sample rows carry session <code>" + esc(short(M.session_id, 8)) + "</code> and agent <code>" + esc(M.agent) + "</code>") +
      check(D.checks.count, "Histogram sums to 180 = <code>event_count</code> in <code>live.json</code> and <code>snapshot.json</code>") +
      check(!!o.tool && o.result.context_ref === M.context_ref, "Sample <code>TOOL_COMPLETED.result.context_ref</code> = <code>" + esc(M.context_ref) + "</code>") +
      info("<code>user_id</code> is a BQAA row column, not an agent-facing field: the demo pseudonym <code>" + esc(o.userIds.join(", ")) + "</code>. It is not inside any tool result.") +
      info("The same scan over all 180 rows is documented on SDK PR 474 (<code>lookup.never_emit_violations</code>, tests). This page scans the sample it carries; " + o.scanned + " distinct content keys.") +
      info("The tool result's <code>okf.publication_id</code> <code>" + esc(short(o.okf.publication_id || "", 19)) + "</code> is the pin of the in-process demo catalog the agent retrieved from; the adapter records it as <code>observed_publication_id</code> and derives its own publication in beat 2.") +
      "</ul></div></div></div>" +
      renderPriorConsume() + renderGermany();
  }

  // Prior live-GCP consume experiment: labelled, collapsed, never the adapter input.
  function prepPrior(meta, rawRows) {
    var rows = rawRows.map(function (r) { var o = {}; Object.keys(r).forEach(function (k) { o[k] = r[k]; }); o.content = parseMaybe(r.content); o.attributes = parseMaybe(r.attributes); return o; });
    var hist = {};
    rows.forEach(function (r) { hist[r.event_type] = (hist[r.event_type] || 0) + 1; });
    var completed = rows.filter(function (r) { return r.event_type === "TOOL_COMPLETED"; })[0];
    var starting = rows.filter(function (r) { return r.event_type === "TOOL_STARTING"; })[0];
    var user = rows.filter(function (r) { return r.event_type === "USER_MESSAGE_RECEIVED"; })[0];
    var answer = rows.filter(function (r) { return r.event_type === "AGENT_RESPONSE"; })[0];
    var raw = answer && answer.content && answer.content.response || "";
    var m = raw.match(/^text: '([\s\S]*)'$/);
    return { meta: meta, rows: rows, hist: hist, completed: completed, starting: starting, user: user, answerText: m ? m[1] : raw,
      tool: completed && completed.content && completed.content.tool || "lookup_okf_context",
      args: starting && starting.content && starting.content.args || {}, result: completed && completed.content && completed.content.result || {} };
  }
  function renderPriorConsume() {
    if (!X || !X.prior) return "";
    var P = X.prior, M = P.meta;
    var list = P.rows.map(function (e, i) {
      return '<li class="ev"><button type="button" aria-expanded="false" data-ev="p' + i + '"><span class="ts">' + esc(tsLive(e.timestamp)) + '</span><span class="ty ' + evClass(e) + '">' + esc(e.event_type) + '</span><span class="sm">' + esc(e.event_type === "TOOL_COMPLETED" ? P.tool + " (stub) · " + (e.content.result || {}).context_ref : e.event_type === "USER_MESSAGE_RECEIVED" ? "“" + (e.content.text_summary || "") + "”" : "") + '</span><span class="car">▸</span></button><div class="raw" hidden>' + pre({ timestamp: e.timestamp, event_type: e.event_type, agent: e.agent, session_id: e.session_id, status: e.status, content: e.content }, ["context_ref", "publication_id"]) + "</div></li>";
    }).join("");
    return '<details class="nn fixture"><summary>Prior live-GCP consume experiment · <code>' + esc(M.agent) + '</code> · session <code>' + esc(short(M.session_id, 8)) + '</code> · ' + P.rows.length + ' rows · NOT this adapter input</summary><div class="nn-b">' +
      '<p class="fixture-note"><b>Prior experiment, kept for history.</b> Before the observe run, a consume agent on <code>gemini-3.8-flash</code> called a pinned stub tool <code>' + esc(P.tool) + '</code> that echoed its <code>context_ref</code> (<code>' + esc(M.context_ref) + '</code>) and returned a hard-coded publication for the synthetic Germany bundle. Those 14 rows are real BQAA rows in the same table, but they are <b>not retrieve-shaped</b>: the SDK CLI fails closed on that session (<code>--session ' + esc(M.session_id) + '</code> → <code>FAIL_CLOSED not retrieve-shaped</code>). They are not the Observe input and not the source of any identity on this page.</p>' +
      '<div class="cols"><div class="pane telemetry"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--telemetry)"></span>' + esc(M.project + "." + M.dataset + "." + M.table) + ' · ' + esc(M.session_id) + '</span><span class="m">prior consume session · curated field projection</span></div><div class="pane-b"><ul class="events">' + list + "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">Prior run facts</span><span class="m">labelled, not this run</span></div><div class="pane-b"><dl class="facts">' +
      "<dt>agent</dt><dd><code>" + esc(M.agent) + "</code> · prior</dd><dt>session_id</dt><dd><code>" + esc(M.session_id) + "</code> · prior</dd><dt>context_ref</dt><dd><code>" + esc(M.context_ref) + "</code> · prior, bound to the synthetic Germany publication</dd><dt>tool</dt><dd><code>" + esc(P.tool) + "</code> · stub echo, no store lookup, unknown refs not rejected</dd><dt>rows</dt><dd>" + P.rows.length + " · " + Object.keys(P.hist).map(function (k) { return "<code>" + esc(k) + "</code>×" + P.hist[k]; }).join(" ") + "</dd><dt>ran_at</dt><dd><code>" + esc(M.ran_at) + "</code></dd>" +
      "</dl></div></div></div></div></details>";
  }
  function renderGermany() {
    if (!X || !X.germany) return "";
    var G = X.germany, t = G.trace, obs = G.adapted.observation;
    var keyset = keysDeep(t.events);
    var never = NEVER_EMIT.filter(function (k) { return k !== "user_id"; });
    return '<details class="nn fixture"><summary>SYNTHETIC hashing-only · <code>traces/bqaa-germany.json</code> · session <code>' + esc(obs.session_id) + '</code> · not the source of truth</summary><div class="nn-b">' +
      '<p class="fixture-note"><b>Synthetic fixture, hashing regression only.</b> This hand-written 15-event trace was the adapter input of the earlier in-browser version of this page. It is kept so that <code>adapter.js</code> + <code>hash.js</code> can be regression-checked against <code>derived/identities.json</code> (<code>tools/derived_vectors.py</code> re-derives it in Python). It produces publication <code>' + esc(short(G.pinned.publication_id, 19)) + '</code>, which is <b>not</b> the publication of this demo, and it was never written to a table.</p>' +
      '<ul class="checklist">' +
      check(G.match, "Synthetic check: <code>adapter.js</code> + <code>hash.js</code> on the Germany trace = pinned <code>derived/identities.json</code> (<code>" + esc(short(G.hashed.publication_id, 19)) + "</code>)") +
      check(G.hashed.publication_id !== D.ident.publication_id, "That synthetic publication ≠ this demo's CLI publication <code>" + esc(short(D.ident.publication_id, 19)) + "</code>") +
      never.map(function (k) { return check(!keyset[k], "<code>" + k + "</code> absent from every synthetic event key"); }).join("") +
      "</ul></div></details>";
  }

  // ---- beat 2: adapt ------------------------------------------------------------
  var selectedFile = null;
  function bundleList() {
    var byDir = {};
    D.bundle.files.forEach(function (f) { (byDir[f.dir] = byDir[f.dir] || []).push(f); });
    return '<ul class="tree">' + Object.keys(byDir).sort().map(function (dir) {
      return '<li><div class="dir">' + esc(dir) + "/</div><ul>" + byDir[dir].map(function (f) {
        return '<li><button type="button" data-file="' + esc(f.path) + '"' + (f.path === selectedFile ? ' aria-current="true"' : "") + ">" + esc(f.path.split("/").pop()) + '<span class="ty">' + esc(f.type) + "</span></button></li>";
      }).join("") + "</ul></li>";
    }).join("") + "</ul>";
  }
  function fileCard(p) {
    var f = D.bundle.files.filter(function (x) { return x.path === p; })[0];
    if (!f) return "";
    return '<div class="pane-h" style="border-top:1px solid var(--line)"><span class="t"><code>' + esc(f.path) + '</code></span><span class="m">' + (f.cvid ? "concept_version_id (store-only) " + esc(short(f.cvid, 23)) : "reserved §9 file · no frontmatter by design") + "</span></div>" +
      '<dl class="facts" style="padding:10px 12px">' +
      "<dt>title</dt><dd>" + esc(f.title) + (f.rank ? " · rank " + f.rank + " in the observed envelope" : f.reason ? " · excluded: " + esc(f.reason) : "") + "</dd>" +
      "<dt>type</dt><dd>" + esc(f.type) + (f.status ? " · lifecycle <code>" + esc(f.status) + "</code>" : "") + "</dd>" +
      "<dt>sha256</dt><dd><code>" + esc(f.sha256) + "</code></dd>" +
      (f.cvid ? "<dt>concept_version_id</dt><dd><code>" + esc(f.cvid) + "</code> · store-only, never on agent-facing payloads</dd>" : "") +
      "<dt>where</dt><dd>CLI <code>out/bundle/" + esc(f.path) + "</code> on SDK PR 474 · file text not committed to Pages · every stub starts “Derived from BQAA observation, not authored.”</dd>" +
      "</dl>";
  }
  function renderAdapt() {
    var kv = D.cli.kv, d = D.ident, a = D.authored, M = D.live, c = D.checks;
    if (!selectedFile) selectedFile = "computations/active-customer-revenue-by-region-and-quarter.md";
    var hl = {}; hl.SESSION = M.session_id; hl.CONTEXT_REF = M.context_ref; hl.PUBLICATION_ID = d.publication_id; hl.OBSERVATION_ID = d.observation_id; hl.SNAPSHOT_ID = d.snapshot_id;
    return beatHead(2, "source", "Adapt", "One stdlib command. The observer export in, a derived bundle and its identity chain out. Nothing ran in this browser.",
      "<code>python examples/okf_bqaa_adapter/run.py</code> (<code>" + esc(kv.ADAPTER) + "</code>, SDK PR 474 HEAD <code>" + PR_HEAD.slice(0, 8) + "</code>) read the committed 180-row export, required it to be retrieve-shaped, projected the observer's view (titles, types, ranks, one exclusion, one edge, one unattested receipt) into <b>" + esc(kv.FILES) + " files</b> under <code>" + esc(d.inputs.bundle_key) + "</code>, and hashed them with the PROFILE.md rules. The transcript below is the committed proof; the identities on this page are copied from the CLI's <code>live_identities.json</code>. The authored bundle was neither read nor written.") +
      must("CLI transcript, not an in-browser adapter · distinct <code>bundle_key</code> · own observation / snapshot / publication triple · transcript = pinned JSON = identity strip · <code>okf-phase0-mvp/fixture/bundle</code> untouched") +
      '<div class="flow">' +
      '<div class="box t"><b>in · live observe export</b>' + M.event_count + " real rows · session <code>" + esc(short(M.session_id, 13)) + "</code><br>6 retrieved + 1 excluded item · 1 edge · 1 receipt (UNVERIFIABLE)</div>" +
      '<div class="arrow"><b>→</b>python run.py<br>observe · adapt · hash</div>' +
      '<div class="box d"><b>out · derived OKF v0.2 bundle</b><code>' + esc(d.inputs.bundle_key) + "</code> · " + esc(kv.FILES) + " files<br>publication <code>" + short(d.publication_id, 23) + "</code></div>" +
      '<div class="arrow"><b>→</b>mapping.json<br>fail-closed lookup</div>' +
      '<div class="box l"><b>handle · context_ref</b><code>' + esc(M.context_ref) + "</code><br>resolves in beat 4 · junk refs exit 2</div>" +
      "</div>" +
      '<div class="cols">' +
      '<div class="pane source"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--source)"></span>CLI transcript · cli/okf-bqaa-cli-transcript.txt</span><span class="m">recorded 2026-09-02 PT · stdlib, no GCP · highlighted values = pinned identities</span></div>' +
      '<div class="pane-b" style="padding:0">' + transcriptHtml(D.cli.blocks.slice(0, 1), hl) + "</div>" +
      '<div class="cli-links"><a class="lk cli" href="cli/okf-bqaa-cli-transcript.txt">plaintext</a><a class="lk cli" href="cli/okf-bqaa-cli.cast">asciinema .cast</a><a class="lk cli" href="cli/okf-bqaa-cli.gif">gif</a><a class="lk cli" href="#walkthrough">mp4 · walkthrough</a>' + link(PR_URL, "pr", "source · SDK PR 474") + "</div>" +
      '<div class="pane-h" style="border-top:1px solid var(--line)"><span class="t">bundle · CLI out/bundle/ · ' + D.bundle.files.length + ' files</span><span class="m">names + hashes from live_identities.json · click a file</span></div>' +
      '<div class="pane-b" style="padding:8px 10px">' + bundleList() + "</div>" + fileCard(selectedFile) + "</div>" +
      '<div class="pane"><div class="pane-h"><span class="t">Identity chain · pinned from CLI</span><span class="m">live_identities.json · PROFILE.md rules in adapter.py</span></div><div class="pane-b">' +
      '<dl class="facts">' +
      "<dt>bundle_key</dt><dd><code>" + esc(d.inputs.bundle_key) + "</code></dd>" +
      "<dt>source_uri</dt><dd><code>" + esc(d.inputs.source_uri) + "</code></dd>" +
      "<dt>revision</dt><dd><code>" + esc(d.inputs.revision) + "</code></dd>" +
      "<dt>deployment</dt><dd><code>" + esc(d.inputs.deployment_key) + "</code></dd>" +
      "<dt>observation_id</dt><dd><code>" + esc(d.observation_id) + "</code></dd>" +
      "<dt>snapshot_id</dt><dd><code>" + esc(d.snapshot_id) + "</code></dd>" +
      "<dt>publication_id</dt><dd><code>" + esc(d.publication_id) + "</code></dd>" +
      "<dt>source_manifest_hash</dt><dd><code>" + esc(d.source_manifest_hash) + "</code></dd>" +
      "<dt>observed_publication_id</dt><dd><code>" + esc(short(d.inputs.observed_publication_id, 23)) + "</code> · the in-process catalog pin the agent retrieved; <code>context_ref</code> = <code>okf:env-observe#</code> + its first 12 hex</dd>" +
      "<dt>context_ref</dt><dd><code>" + esc(M.context_ref) + "</code></dd>" +
      "</dl>" +
      '<ul class="checklist">' +
      check(c.obs && c.snap && c.pub, "Transcript <code>OBSERVATION_ID</code> / <code>SNAPSHOT_ID</code> / <code>PUBLICATION_ID</code> = <code>live_identities.json</code> = identity strip") +
      check(c.session && c.trace && c.table && c.model, "Transcript <code>SESSION</code> / <code>TRACE</code> / <code>TABLE</code> / <code>MODEL</code> = <code>live.json</code> (<code>gemini-3.8-flash</code>)") +
      check(c.ref, "Transcript <code>CONTEXT_REF</code> = <code>live.json</code> context_ref = receipt context_ref") +
      check(c.files, "Transcript <code>FILES " + esc(kv.FILES) + "</code> = " + Object.keys(d.file_sha256).length + " hashed files in <code>live_identities.json</code>") +
      check(c.mapping, "<code>mapping.json</code> binds exactly one ref, <code>" + esc(M.context_ref) + "</code>, to that publication") +
      check(c.distinct, "Distinct from authored <code>" + esc(a.inputs.bundle_key) + "</code> · pub <code>" + short(a.publication_id, 16) + "</code> stays pinned and unchanged") +
      check(c.receipt, "Transcript <code>RECEIPT UNVERIFIABLE rcpt-observe-noexec</code> · nothing attested") +
      '<li class="ok"><span class="ic">✓</span><span>Adapter read 0 authored files; wrote 0 authored files. This browser hashed 0 bytes for these identities.</span></li>' +
      info("The adapter is Python in the SDK (<code>adapter.py</code>: observe / adapt / compute_identities / project, canonical CBOR + domain-separated SHA-256). <code>adapter.js</code> on this page is only used for the labelled SYNTHETIC Germany hashing check under beat 1.") +
      info("No <code>computation:</code> artifact in the derived stub: the observer never sees SQL. It cites the observed envelope under <code>sources</code>.") +
      "</ul></div></div></div>";
  }

  // ---- beat 3: project ------------------------------------------------------------
  function renderProject() {
    var d = D.ident, M = D.live, pub = d.publication_id, snap = d.snapshot_id, docs = D.bundle.docs, prior = X && X.prior ? X.prior.meta : null;
    var cards = docs.map(function (f) {
      return '<div class="card"><div class="ch"><span class="name">' + esc(f.title) + '</span><span class="etype">okf-concept · derived view</span></div>' +
        '<div class="pins">' +
        '<span class="pin"><b>okf.type</b> ' + esc(f.type) + "</span>" +
        '<span class="pin' + (f.status === "deprecated" ? " dep" : "") + '"><b>okf.lifecycle</b> ' + esc(f.status) + "</span>" +
        '<span class="pin"><b>okf.provenance</b> bqaa observer · derived</span>' +
        '<span class="pin pub"><b>okf.publication_id</b> ' + esc(short(pub, 19)) + "</span>" +
        '<span class="pin"><b>okf.published_snapshot_id</b> ' + esc(short(snap, 15)) + "</span>" +
        (f.type === "Attested Computation" ? '<span class="pin" style="border-color:#F0D9B8;background:var(--runtime-bg);color:var(--runtime)"><b style="color:var(--runtime)">okf-computation</b> runtime bigquery · receipt UNVERIFIABLE</span>' : "") +
        "</div></div>";
    }).join("");
    var pubRow = [{ publication_id: pub, observation_id: d.observation_id, snapshot_id: snap, deployment_key: d.inputs.deployment_key, bundle_key: d.inputs.bundle_key, profile_contract_version: d.inputs.profile_contract_version }];
    var headRow = [{ deployment_key: d.inputs.deployment_key, publication_id: pub, published_at: M.ran_at }];
    var nodes = docs.map(function (f) { return { concept_key: d.inputs.bundle_key + "#" + f.path.slice(0, -3), type: f.type, title: f.title, status: f.status, concept_version_id: f.cvid, publication_id: pub }; });
    var byTitle = {};
    docs.forEach(function (f) { byTitle[f.title] = d.inputs.bundle_key + "#" + f.path.slice(0, -3); });
    var edges = (D.obs.okf.links || []).filter(function (l) { return byTitle[l.from] && byTitle[l.to]; }).map(function (l) {
      return { from_concept_key: byTitle[l.from], to_concept_key: byTitle[l.to], predicate: "producer:" + l.rel, assertion_mode: "inferred", publication_id: pub };
    });
    docs.filter(function (f) { return f.status === "deprecated"; }).forEach(function (f) {
      var active = docs.filter(function (g) { return g.dir === f.dir && g.status !== "deprecated"; })[0];
      if (active) edges.push({ from_concept_key: byTitle[active.title], to_concept_key: byTitle[f.title], predicate: "supersedes", assertion_mode: "explicit", publication_id: pub });
    });
    function table(name, rows, note) {
      var cols = Object.keys(rows[0]);
      return '<div class="tbl-wrap"><table class="tbl"><caption>' + esc(name) + "<span>" + rows.length + " row" + (rows.length === 1 ? "" : "s") + (note ? " · " + esc(note) : "") + "</span></caption><thead><tr>" +
        cols.map(function (c) { return "<th>" + esc(c) + "</th>"; }).join("") + "</tr></thead><tbody>" +
        rows.map(function (r) { return "<tr>" + cols.map(function (c) { var v = r[c]; return "<td" + (c === "publication_id" ? ' class="pub"' : "") + ' title="' + esc(v) + '">' + esc(/^sha256:/.test(String(v)) ? short(v, 19) : v) + "</td>"; }).join("") + "</tr>"; }).join("") +
        "</tbody></table></div>";
    }
    var kcCard =
      '<div class="live-card catalog"><div class="lh"><b>Knowledge Catalog</b><span class="tag">derived view · no write on this CLI path</span></div>' +
      '<div class="pins">' +
      '<span class="pin"><b>entry</b> none created · honesty label</span>' +
      '<span class="pin pub"><b>publication (pinned, CLI)</b> ' + esc(short(pub, 19)) + "</span>" +
      '<span class="pin"><b>provenance</b> bqaa observer · derived / demo</span>' +
      '<span class="pin"><b>kcmd</b> not called · no Catalog aspect read or written by the CLI or this page</span>' +
      "</div>" +
      '<p class="res">The cards below are what a Catalog projection of this bundle would carry. They are rendered from <code>live_identities.json</code>, not read back from Dataplex.</p>' +
      (prior ? '<details class="nn"><summary>Prior leftover · Dataplex entry <code>' + esc(prior.kc_entry_id) + '</code> · from the consume experiment, not this run</summary><div class="nn-b"><p class="fixture-note">Prior experiment leftover. The entry <code>' + esc(prior.kc_entry_id) + '</code> in group <code>' + esc(prior.kc_entry_group) + '</code> (' + esc(prior.kc_location) + ') was created for the earlier consume experiment and its description names the synthetic Germany publication <code>' + esc(short(prior.publication_id, 19)) + '</code>, not this demo\'s <code>' + esc(short(pub, 19)) + '</code>.</p><div class="live-links">' + link(prior.kc_console, "kc", "Find the prior entry in Dataplex") + "</div></div></details>" : "") +
      "</div>";
    var bqCard =
      '<div class="live-card runtime"><div class="lh"><b>' + esc(M.dataset + ".agent_events") + '</b><span class="tag">BigQuery table · live source · read-only</span></div>' +
      '<div class="pins">' +
      '<span class="pin"><b>project</b> ' + esc(M.project) + "</span>" +
      '<span class="pin"><b>writer</b> BigQueryAgentAnalyticsPlugin · observer-only</span>' +
      '<span class="pin"><b>rows · session</b> ' + M.event_count + " · " + esc(short(M.session_id, 8)) + "</span>" +
      '<span class="pin"><b>DML from CLI / page</b> none</span>' +
      "</div>" +
      '<p class="res"><code>' + esc(M.table) + "</code></p>" +
      '<div class="live-links">' + link(BQ_CONSOLE, "bq", "Open the table in BigQuery") + "</div></div>";
    return beatHead(3, "split", "Project", "Two derived views, one publication. The identities are pinned from the CLI; nothing was written to Catalog or BigQuery for them.",
      "<b style=\"color:var(--catalog)\">Knowledge Catalog</b> and <b style=\"color:var(--runtime)\">BigQuery</b> are shown as the two projection targets of the RFC. On this CLI path neither received a write: the Catalog pane is a derived view with an honesty label, and the BigQuery pane shows the live <code>agent_events</code> source table (observer rows, read-only) above the RFC projection shape rendered from the pinned identities. The authored <code>cymbal-finance-core</code> publication stays pinned in the strip above, untouched.") +
      must("identity chips = <code>live_identities.json</code> · Catalog / BQ tables are derived views, not extra DML · no Catalog write claimed for this path · prior Dataplex entry labelled as a leftover · authored publication unchanged") +
      '<div class="idrow" style="margin:0 0 14px">' +
      '<div class="lbl"><b>Derived · pinned from CLI</b>' + esc(d.inputs.bundle_key) + '</div>' +
      '<div class="chip deriv"><span class="k">observation_id</span><span class="v">' + esc(d.observation_id) + '</span></div>' +
      '<div class="chip deriv"><span class="k">snapshot_id</span><span class="v">' + esc(d.snapshot_id) + '</span></div>' +
      '<div class="chip deriv"><span class="k">publication_id</span><span class="v">' + esc(d.publication_id) + '</span></div>' +
      '<span class="status ok">= transcript ✓</span></div>' +
      '<div class="cols even">' +
      '<div class="pane catalog"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--catalog)"></span>Knowledge Catalog · discovery</span><span class="m">derived view · honesty label</span></div>' +
      '<div class="pane-b">' + kcCard + '<p class="sub-h">derived view · projection of the CLI bundle · not written to Catalog</p><div class="cards">' + cards + "</div></div></div>" +
      '<div class="pane runtime"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--runtime)"></span>BigQuery · serving</span><span class="m">live source table first · derived view below</span></div>' +
      '<div class="pane-b">' + bqCard + '<p class="sub-h">derived view · RFC projection shape · not a live table, no DML</p>' + table("publications", pubRow) + table("deployment_heads", headRow, "head advanced") + table("nodes_current", nodes, "one row per concept version") + (edges.length ? table("edges_current", edges, "from the observed envelope") : "") + "</div></div>" +
      '<div class="seam-note"><span>pinned <code>publication_id</code> ' + esc(short(pub, 23)) + '</span><span class="eq">' + (D.checks.pub && D.checks.mapping ? "=" : "≠") + '</span><span>CLI transcript <code class="rt">PUBLICATION_ID</code> = <code class="rt">mapping.json</code> value ' + esc(short(D.cli.kv.PUBLICATION_ID || "", 23)) + "</span><span>· " + (D.checks.pub && D.checks.mapping ? "one publication everywhere on this page ✓" : "MISMATCH") + "</span><span>· Catalog: no entry created on this path; BigQuery: source table only, no DML</span></div>" +
      "</div>";
  }

  // ---- beat 4: consume ---------------------------------------------------------------
  var tryRef = null;
  function localLookup(ref) {
    var map = D.mapping.mapping || {};
    if (typeof ref !== "string" || !(ref in map)) return { ok: false, error: "FAIL_CLOSED context_ref not bound in mapping (fail closed): '" + ref + "'", exit: 2 };
    return { ok: true, result: { context_ref: ref, publication_id: map[ref], label: "derived/demo" }, exit: 0 };
  }
  function renderConsume() {
    var M = D.live, d = D.ident, c = D.checks, cli = D.cli, lk = cli.lookup || {};
    var okNever = c.lookupNever;
    var tried = tryRef === null ? null : localLookup(tryRef);
    var py =
      '<span class="cm"># examples/okf_bqaa_adapter/lookup.py — fail-closed resolver (excerpt, SDK PR 474)</span>\n' +
      '<span class="kw">class</span> UnknownContextRefError(KeyError):\n' +
      '    <span class="cm">"""The context_ref is not bound in mapping.json (fail closed)."""</span>\n\n' +
      '<span class="kw">def</span> lookup(context_ref: str, mapping) -> dict:\n' +
      '    table = load_mapping(mapping)\n' +
      '    <span class="kw">if</span> <span class="kw">not</span> isinstance(context_ref, str) <span class="kw">or</span> context_ref <span class="kw">not in</span> table:\n' +
      '        <span class="kw">raise</span> UnknownContextRefError(\n' +
      '            <span class="st">f"context_ref not bound in mapping (fail closed): {context_ref!r}"</span>)\n' +
      '    <span class="kw">return</span> {<span class="st">"context_ref"</span>: context_ref,\n' +
      '            <span class="st">"publication_id"</span>: table[context_ref],\n' +
      '            <span class="st">"label"</span>: LABEL}   <span class="cm"># "derived/demo" · never concept_version_id, paths, principal, SQL</span>\n\n' +
      '<span class="cm"># run.py: unknown ref → stderr FAIL_CLOSED, exit 2; never-emit keys on a result → exit 2</span>';
    return beatHead(4, "ink", "Consume", "Fail-closed lookup. The known <code>context_ref</code> resolves to the publication; a junk ref exits 2. Nothing is attested.",
      "The consume side of this path is <code>run.py --lookup REF</code> over the CLI's <code>mapping.json</code>, which binds exactly one <code>context_ref</code>. A bound ref returns three keys and nothing from the never-emit list; an unbound ref raises and the process exits 2 with <code>FAIL_CLOSED</code> on stderr. Both tapes below are from the committed transcript. The receipt on the observe run is <code>UNVERIFIABLE</code>: no sanctioned computation ran, so <b>nothing on this page is ATTESTED</b>.") +
      must("known ref → {<code>context_ref</code>, <code>publication_id</code>, <code>label</code>} · junk ref → <code>FAIL_CLOSED</code>, exit 2 · result keys ∩ never-emit = ∅ · receipt UNVERIFIABLE · no ATTESTED claim · browser calls no GCP") +
      '<div class="adk">' +
      '<div class="adk-h"><span class="agent"><span class="fw">SDK CLI · okf-bqaa-adapter:v0</span><b>run.py --lookup</b><span>mapping.json · session ' + esc(M.session_id) + '</span></span>' +
      '<span class="model-badge"><span class="dot"></span>source · <b>' + esc(M.agent) + "</b> · " + esc(M.model) + "</span></div>" +
      '<div class="adk-b"><div class="transcript">' +
      '<div class="term ok"><div class="th">tape 1 · bound ref · exit 0</div>' + transcriptHtml(cli.blocks.slice(1, 2)) + "</div>" +
      '<div class="term fail"><div class="th">tape 2 · junk ref · exit 2</div>' + transcriptHtml(cli.blocks.slice(2, 3)) + "</div>" +
      '<div class="term try"><div class="th">try a ref · static mapping.json in this page · same rule as lookup.py · no store, no network</div>' +
      '<form class="tryform" data-try><input type="text" name="ref" value="' + esc(tryRef === null ? M.context_ref : tryRef) + '" aria-label="context_ref to resolve" spellcheck="false"><button class="btn primary" type="submit">--lookup</button></form>' +
      (tried ? (tried.ok ? '<pre class="cli">' + jsonHtml(tried.result, ["context_ref", "publication_id"]) + '\n<span class="cm"># exit 0</span></pre>' : '<pre class="cli"><span class="fail">' + esc(tried.error) + '</span>\n<span class="cm"># exit 2</span></pre>') : '<p class="fixture-note" style="margin:8px 0 0">Resolves against the committed <code>mapping.json</code> (one binding). Anything else fails closed.</p>') +
      "</div></div>" +
      '<div class="side">' +
      '<div class="tile"><div class="th">resolver · lookup.py on SDK PR 474</div><pre class="py">' + py + "</pre></div>" +
      '<div class="tile"><div class="th">never-emit assertion · lookup result keys</div><div class="big ' + (okNever ? "ok" : "warn") + '">keys ∩ never-emit = ' + (okNever ? "∅ ✓" : "violation") + "</div><p>Result keys: " + Object.keys(lk).map(function (k) { return "<code>" + esc(k) + "</code>"; }).join(" ") + " scanned against " + NEVER_EMIT.map(function (k) { return "<code>" + k + "</code>"; }).join(" ") + ".</p></div>" +
      '<div class="tile"><div class="th">receipt · this run</div><span class="verdict">UNVERIFIABLE · rcpt-observe-noexec</span><p>The observe agent retrieved context; it did not run a sanctioned computation. The receipt the adapter carries is a no-execution specimen bound to <code>' + esc(M.receipt_context_ref) + '</code>. <b>Nothing is ATTESTED.</b> The Phase 4 ATTESTED shape below is non-normative.</p></div>' +
      '<details class="nn"><summary>Fixture receipts · not from this run</summary><div class="nn-b"><span class="verdict">UNVERIFIABLE · ' + esc(D.receipt.verdict_reason) + '</span><p style="font-family:var(--display);font-size:13px;color:var(--ink-soft);margin:8px 0 0">Phase 0 golden specimen <code>' + esc(D.receipt.receipt_id) + "</code>, bound to the authored publication. Integrity proof status <code>" + esc(D.receipt.integrity_proof.status) + '</code>.</p><span class="verdict att" style="margin-top:12px">ATTESTED · expected Phase 4 shape · non-normative</span><p style="font-family:var(--display);font-size:13px;color:var(--ink-soft);margin:8px 0 0">' + esc(D.phase4._fixture_note) + "</p>" + pre({ verdict: D.phase4.verdict, verdict_details_digest: D.phase4.verdict_details_digest, receipt_digest: D.phase4.receipt_digest, integrity_proof: D.phase4.integrity_proof }, [], "rounded") + "</div></details>" +
      "</div></div></div>" +
      renderPriorConsumeTranscript();
  }
  function renderPriorConsumeTranscript() {
    if (!X || !X.prior) return "";
    var P = X.prior, M = P.meta;
    return '<details class="nn fixture"><summary>Prior live-GCP consume experiment · <code>' + esc(P.tool) + '</code> stub · session <code>' + esc(short(M.session_id, 8)) + '</code> · not this adapter, not fail-closed</summary><div class="nn-b">' +
      '<p class="fixture-note"><b>Prior experiment, superseded by the fail-closed lookup above.</b> An earlier consume agent (<code>' + esc(M.agent) + '</code>, prior) called <code>' + esc(P.tool) + '</code>, a pinned stub that echoed any <code>context_ref</code> and returned a hard-coded publication for the synthetic Germany bundle. It did no store lookup and rejected nothing. The model call and the 14 BQAA rows were real; the resolver was not. Kept for history; not this run\'s input.</p>' +
      '<div class="adk"><div class="adk-h"><span class="agent"><span class="fw">google-adk · prior</span><b>' + esc(M.agent) + "</b><span>session " + esc(M.session_id) + ' · prior</span></span><span class="model-badge"><span class="dot"></span>model · <b>' + esc(M.model) + "</b></span></div>" +
      '<div class="adk-b"><div class="transcript">' +
      turn("user", "user", '<div class="bubble user">' + esc(P.user && P.user.content.text_summary || "") + "</div>") +
      turn("model", M.model, '<div class="bubble call">function_call → <b>' + esc(P.tool) + "</b> " + esc(JSON.stringify(P.args)) + "</div>") +
      turn("tool", "tool result · stub echo", result(P.tool, "TOOL_COMPLETED · prior row", P.result)) +
      turn("model", M.model, '<div class="bubble final">' + esc(P.answerText) + "</div>") +
      "</div><div class=\"side\"><div class=\"tile\"><div class=\"th\">why it is not this demo</div><p>Not retrieve-shaped: the SDK CLI fails closed on this session (<code>run.py --session " + esc(M.session_id) + "</code> → <code>FAIL_CLOSED not retrieve-shaped</code>). Its <code>context_ref</code> <code>" + esc(M.context_ref) + "</code> is bound to the synthetic Germany publication, not to <code>" + esc(short(D.ident.publication_id, 19)) + "</code>.</p></div></div>" +
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
    stage.innerHTML = current === 1 ? renderObserve() : current === 2 ? renderAdapt() : current === 3 ? renderProject() : renderConsume();
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
  stage.addEventListener("submit", function (e) {
    var f = e.target.closest("form[data-try]");
    if (!f) return;
    e.preventDefault();
    tryRef = f.elements.ref.value.trim();
    render();
    var inp = stage.querySelector("form[data-try] input");
    if (inp) inp.focus();
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
