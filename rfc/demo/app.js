/* Why a BQAA trace becomes derived OKF the next agent can look up.
   Static viewer of one SDK CLI run. Vanilla JS, no build.
   Source of truth: one stdlib run of `python examples/okf_bqaa_adapter/run.py`
   (okf-bqaa-adapter:v0, SDK PR 474 pre-merge HEAD 476d37dc; 474 merged 2026-09-03) over the committed export of
   the live ADK observe session f21ee192-… (okf_rfc_observe_agent,
   gemini-3.8-flash, 180 agent_events rows). This page renders the committed
   snapshot, the pinned identities and the CLI transcript. It does not hash,
   adapt or resolve anything for the live identities and never calls GCP.
   hash.js / adapter.js are loaded only for the labelled SYNTHETIC germany
   hashing check, collapsed under beat 1 and never the demo input.
   Four beats: Ask → Observe → Publish → Next agent. */
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
  var CURRENT_METRIC = "Active-customer revenue";
  var LEGACY_METRIC = "Customer revenue (legacy)";

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
    renderIdsHist();
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
  // The tape has four beats; commands are found by shape, not by position.
  function parseTranscript(text) {
    var blocks = [], cur = null, header = [];
    text.split("\n").forEach(function (ln) {
      if (/^\$ /.test(ln)) { cur = { cmd: ln.slice(2), out: [] }; blocks.push(cur); return; }
      if (!cur) { header.push(ln); return; }
      cur.out.push(ln);
    });
    // A block ends before the next beat header; drop trailing blanks / "# N · BEAT" lines.
    blocks.forEach(function (b) { while (b.out.length && (!b.out[b.out.length - 1] || /^# \d+ · /.test(b.out[b.out.length - 1]))) b.out.pop(); });
    function find(re) { return blocks.filter(function (b) { return re.test(b.cmd); })[0] || null; }
    function plain(b) { return b ? b.out.filter(function (l) { return l && !/^#/.test(l); }) : []; }
    var ask = find(/USER_MESSAGE_RECEIVED/);
    var observe = find(/_why_observe/);
    var run = find(/run\.py\s*$/);
    var titles = find(/grep .*title/);
    var lookup = find(/--lookup 'okf:env-observe#/);
    var junk = find(/--lookup 'okf:env-junk#/);
    var kv = {};
    plain(run).forEach(function (ln) { var m = ln.match(/^([A-Z_]+) (.*)$/); if (m) kv[m[1]] = m[2]; });
    var lookupJson = null;
    try { lookupJson = JSON.parse(plain(lookup).join("\n")); } catch (e) { lookupJson = null; }
    var junkLines = junk ? junk.out.filter(function (l) { return l; }) : [];
    var all = text.split("\n");
    var iFail = -1, iPayoff = -1;
    all.forEach(function (l, i) { if (iFail < 0 && /^FAIL_CLOSED/.test(l)) iFail = i; if (/Payoff:/.test(l)) iPayoff = i; });
    var payoffLine = iPayoff >= 0 ? all[iPayoff].replace(/^#\s*/, "") : "";
    return {
      header: header.filter(function (l) { return l; }), blocks: blocks, kv: kv, lookup: lookupJson, junk: junkLines,
      askBlock: ask, observeBlock: observe, runBlock: run, titlesBlock: titles, lookupBlock: lookup, junkBlock: junk,
      askText: plain(ask)[0] || "", observeLines: plain(observe),
      titleLines: plain(titles).filter(function (l) { return /^title:/.test(l); }).map(function (l) { return l.replace(/^title:\s*/, ""); }),
      payoffLine: payoffLine, payoffAfterJunk: iFail >= 0 && iPayoff > iFail
    };
  }
  function transcriptHtml(blocks, hl) {
    hl = hl || {};
    var out = [];
    blocks.forEach(function (b, i) {
      if (!b) return;
      if (i) out.push("");
      out.push('<span class="cmd">$ ' + esc(b.cmd) + "</span>");
      b.out.forEach(function (ln) {
        if (/^#/.test(ln)) { out.push('<span class="cm' + (/Payoff:/.test(ln) ? " payoff" : "") + '">' + esc(ln) + "</span>"); return; }
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
    var okf = result.okf || {};
    var contentKeys = keysDeep(samples.map(function (e) { return e.content; }));
    var never = snap.never_emit || NEVER_EMIT;
    var scan = never.filter(function (k) { return k !== "user_id"; });
    var traces = samples.map(function (e) { return e.trace_id; }).filter(function (v, i, a) { return a.indexOf(v) === i; });
    var items = (okf.items || []).slice().sort(function (a, b) { return a.rank - b.rank; });
    var rank1 = items[0] || null;
    var excluded = (okf.excluded || [])[0] || null;
    var edge = (okf.links || [])[0] || null;
    return {
      hist: hist, types: types, sum: sum, max: Math.max.apply(null, types.map(function (k) { return hist[k]; })),
      samples: samples, tool: tool, result: result, okf: okf,
      items: items, rank1: rank1, excluded: excluded, edge: edge,
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
    var kv = D.cli.kv, live = D.live, ident = D.ident, map = D.mapping.mapping || {}, cli = D.cli, o = D.obs;
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
      lookup: !!cli.lookup && cli.lookup.context_ref === live.context_ref && cli.lookup.publication_id === ident.publication_id && cli.lookup.label === "derived/demo",
      junk: cli.junk.some(function (l) { return /^FAIL_CLOSED/.test(l) && l.indexOf("okf:env-junk#deadbeef") >= 0; }) && cli.junk.some(function (l) { return /exit 2/.test(l); }),
      receipt: /^UNVERIFIABLE rcpt-observe-noexec$/.test(kv.RECEIPT || ""),
      count: live.event_count === 180 && o.sum === 180 && D.snap.event_count === 180,
      distinct: ident.publication_id !== D.authored.publication_id && ident.inputs.bundle_key !== D.authored.inputs.bundle_key,
      adapter: kv.ADAPTER === "okf-bqaa-adapter:v0" && ident.inputs.adapter_version === "okf-bqaa-adapter:v0" && D.mapping.adapter_version === "okf-bqaa-adapter:v0",
      lookupNever: NEVER_EMIT.filter(function (k) { return cli.lookup && k in cli.lookup; }).length === 0,
      // why-slice: the tape says what the trace says
      ask: !!cli.askText && cli.askText === o.question,
      rank1: !!o.rank1 && o.rank1.title === CURRENT_METRIC && cli.observeLines.some(function (l) { return l === "rank 1: " + CURRENT_METRIC; }),
      excluded: !!o.excluded && o.excluded.title === LEGACY_METRIC && cli.observeLines.some(function (l) { return l.indexOf("excluded: " + LEGACY_METRIC) === 0; }),
      unproven: cli.observeLines.some(function (l) { return /^receipt: UNVERIFIABLE/.test(l); }),
      titles: cli.titleLines.length > 0 && cli.titleLines.every(function (t) { return D.bundle.docs.some(function (f) { return f.title === t; }); }),
      payoff: /not legacy/.test(cli.payoffLine) && /unproven/.test(cli.payoffLine) && cli.payoffAfterJunk
    };
  }
  function allOk() { var c = D.checks; return Object.keys(c).every(function (k) { return c[k]; }); }

  // ---- strips (inside the collapsed IDs panel) --------------------------------
  function renderLiveStrip() {
    var st = document.getElementById("live-status");
    if (!st) return;
    var ok = D.checks.count && D.checks.session && D.checks.ref && D.obs.violations.length === 0;
    st.textContent = ok ? "snapshot loaded ✓ · " + D.live.event_count + " events · transcript agrees" : "snapshot mismatch — see beat 2";
    st.className = "status " + (ok ? "ok" : "warn");
  }
  function renderIdentity() {
    var a = D.authored, d = D.ident;
    var set = function (id, v) { var el = document.getElementById(id); if (el) el.textContent = v; };
    set("a-obs", a.observation_id); set("a-snap", a.snapshot_id); set("a-pub", a.publication_id);
    set("d-obs", d.observation_id); set("d-snap", d.snapshot_id); set("d-pub", d.publication_id);
    var as = document.getElementById("a-status"); if (as) { as.textContent = "pinned · display only · untouched"; as.className = "status ok"; }
    var ds = document.getElementById("d-status");
    if (ds) {
      var ok = D.checks.obs && D.checks.snap && D.checks.pub && D.checks.distinct;
      ds.textContent = ok ? "pinned from CLI · okf-bqaa-adapter:v0 · = transcript ✓ · distinct from authored" : "pinned from CLI · MISMATCH vs transcript";
      ds.className = "status " + (ok ? "ok" : "warn");
    }
  }
  function renderIdsHist() {
    var el = document.getElementById("ids-hist");
    if (el) el.innerHTML = histogramHtml(D.obs);
  }

  // ---- shared pieces --------------------------------------------------------------
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
  function sampleRowsHtml() {
    var M = D.live, o = D.obs;
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
    return '<details class="nn"><summary>Six sample rows and the never-emit scan · <code>snapshot.json</code> · not a 180-row dump</summary><div class="nn-b">' +
      '<p class="fixture-note">The trimmed snapshot carries six rows of the 180 (histogram in <a href="#ids">How this was built / IDs</a>; full export on SDK PR 474, merged 2026-09-03). Click a row to see it.</p>' +
      '<ul class="events">' + list + "</ul>" +
      '<p class="beat-kicker" style="margin:12px 0 6px">Never-emit scan · sample content keys</p>' +
      '<ul class="checklist">' + checks +
      check(o.sessionOk, "All " + o.samples.length + " sample rows carry session <code>" + esc(short(M.session_id, 8)) + "</code> and agent <code>" + esc(M.agent) + "</code>") +
      check(D.checks.count, "Histogram sums to 180 = <code>event_count</code> in <code>live.json</code> and <code>snapshot.json</code>") +
      check(!!o.tool && o.result.context_ref === M.context_ref, "Sample <code>TOOL_COMPLETED.result.context_ref</code> = <code>" + esc(M.context_ref) + "</code>") +
      info("<code>user_id</code> is a BQAA row column, not an agent-facing field: the demo pseudonym <code>" + esc(o.userIds.join(", ")) + "</code>. It is not inside any tool result.") +
      info("The same scan over all 180 rows is documented on SDK PR 474 (<code>lookup.never_emit_violations</code>, tests). This page scans the sample it carries; " + o.scanned + " distinct content keys.") +
      info("The tool result's <code>okf.publication_id</code> <code>" + esc(short(o.okf.publication_id || "", 19)) + "</code> is the pin of the in-process demo catalog the agent retrieved from; the adapter records it as <code>observed_publication_id</code> and derives its own publication in beat 3.") +
      "</ul></div></details>";
  }

  // ---- beat 1: ask ----------------------------------------------------------------
  function renderAsk() {
    var o = D.obs, c = D.checks, M = D.live, cli = D.cli;
    var ex = o.excluded || { title: LEGACY_METRIC, type: "Metric", reason: "superseded" };
    var r1 = o.rank1 || { title: CURRENT_METRIC, type: "Metric", rank: 1 };
    var edge = o.edge;
    return beatHead(1, "telemetry", "Ask", "A finance agent is asked: “" + esc(o.question) + "”",
      "There are two easy ways to get this wrong. The agent can answer with <b>" + esc(ex.title) + "</b>, a metric that is still on the shelf but " + esc(ex.reason) + ". Or it can quote the number as if someone had verified it, when no sanctioned computation has run. Both feel fine in the moment. The current metric is <b>" + esc(r1.title) + "</b>, and the honest answer names it and marks the number as unproven.") +
      must("the trap is <code>" + esc(ex.title) + "</code> vs current <code>" + esc(r1.title) + "</code> · the second trap is claiming the number is verified · question as recorded in the trace, not invented") +
      '<div class="pane ask-what"><div class="pane-h"><span class="t">What this demo is asking</span><span class="m">the three-way question, answered</span></div><div class="pane-b">' +
      "<p><b>Are we trusting what is in BQAA? Asking a human-in-the-loop or customer sentiment to decide what to promote? Or adding context the agent obtained via the hard path into OKF so it is available for easy discovery?</b> The third one.</p><ul>" +
      "<li><b>Yes: hard path → derived OKF for discovery.</b> Context this agent earned the hard way (ranked <code>" + esc(r1.title) + "</code>, excluded <code>" + esc(ex.title) + "</code>, receipt unproven) was observed by BQAA; one adapter turn projects it into derived OKF so the next agent discovers it via <code>context_ref</code> instead of re-earning it or picking the dead metric.</li>" +
      "<li><b>Not trusting BQAA as knowledge or truth.</b> BQAA is observer-only. Telemetry is not the authored bundle and not a truth score.</li>" +
      "<li><b>Not human-in-the-loop promotion or customer-sentiment ranking.</b> This slice does not pick winners that way, and no such feature exists here.</li>" +
      "<li><b>Trust here means process integrity of what was observed.</b> Opaque IDs, fail-closed lookup, no overclaim. It does not mean the number is right: the receipt stays <code>UNVERIFIABLE</code>. It does not make BQAA a second wiki.</li>" +
      "</ul></div></div>" +
      '<div class="traps">' +
      '<div class="trap bad"><div class="th">Trap 1 · the dead metric</div><div class="name">' + esc(ex.title) + '</div><p>' + esc(ex.type) + " · " + esc(ex.reason) + ". Still findable. Still wrong.</p></div>" +
      '<div class="trap soft"><div class="th">Trap 2 · over-claiming trust</div><div class="name">“The number is verified.”</div><p>Nothing ran as a sanctioned computation. The receipt on this run is <code>UNVERIFIABLE</code>, so the number is unproven and should be reported that way.</p></div>' +
      '<div class="trap good"><div class="th">What a good answer does</div><div class="name">' + esc(r1.title) + '</div><p>' + esc(r1.type) + " · rank " + r1.rank + (edge ? " · " + esc(edge.rel.replace(/_/g, " ")) + " " + esc(edge.to) : "") + ". Use it, skip legacy, and say the number is unproven.</p></div>" +
      "</div>" +
      '<div class="compare">' +
      '<div class="pane"><div class="pane-h"><span class="t">Without this path</span><span class="m">what can go wrong</span></div><div class="pane-b"><ul>' +
      "<li><b>Picks the superseded metric.</b> " + esc(ex.title) + " still answers to the name “revenue”.</li>" +
      "<li><b>Talks as if verified.</b> A confident number with no receipt behind it.</li>" +
      "<li><b>Nothing to look up next time.</b> What this agent learned stays in a log nobody reads.</li>" +
      "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">With BQAA observe → derived OKF in Knowledge Catalog</span><span class="m">the next three beats</span></div><div class="pane-b"><ul>' +
      "<li><b>Observe.</b> The live trace already ranked " + esc(r1.title) + " first and excluded " + esc(ex.title) + "; the receipt is unproven.</li>" +
      "<li><b>Publish.</b> One command turns that telemetry into derived OKF, the handle a Catalog entry would expose.</li>" +
      "<li><b>Next agent.</b> Looks up that handle, uses the current metric, skips legacy, reports the number as unproven.</li>" +
      "</ul></div></div>" +
      "</div>" +
      '<div class="pane source"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--source)"></span>The question, as recorded</span><span class="m">tape · beat 1 · read from the committed export, not typed for the demo</span></div>' +
      '<div class="pane-b" style="padding:0">' + transcriptHtml([cli.askBlock]) + "</div>" +
      '<div class="pane-b"><ul class="checklist">' +
      check(c.ask, "Tape question = <code>USER_MESSAGE_RECEIVED.text_summary</code> in the snapshot, session <code>" + esc(short(M.session_id, 8)) + "</code>, agent <code>" + esc(M.agent) + "</code>") +
      check(c.excluded, "The snapshot's tool result excludes <code>" + esc(ex.title) + "</code> with reason “" + esc(ex.reason) + "”") +
      check(c.rank1, "The snapshot's tool result ranks <code>" + esc(r1.title) + "</code> first") +
      "</ul></div></div>" +
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

  // ---- beat 2: observe ---------------------------------------------------------------
  function renderObserve() {
    var M = D.live, o = D.obs, c = D.checks, cli = D.cli, snap = D.snap;
    var ex = o.excluded, edge = o.edge;
    var saw = o.items.map(function (it) {
      var top = it.rank === 1;
      return '<li class="' + (top ? "top" : "") + '"><span class="rk">rank ' + it.rank + '</span><span><span class="ti">' + esc(it.title) + '</span><span class="ty">' + esc(it.type) + "</span>" +
        (top ? '<span class="why">the current metric · the answer should use this</span>' : "") +
        (edge && it.title === edge.from ? '<span class="why">' + esc(edge.rel.replace(/_/g, " ")) + " " + esc(edge.to) + "</span>" : "") +
        "</span></li>";
    }).join("") +
      (ex ? '<li class="out"><span class="rk">excluded</span><span><span class="ti">' + esc(ex.title) + '</span><span class="ty">' + esc(ex.type) + '</span><span class="why">' + esc(ex.reason) + " · the observer recorded why it was left out</span></span></li>" : "") +
      '<li class="rcpt"><span class="rk">receipt</span><span><span class="ti">UNVERIFIABLE</span><span class="ty">rcpt-observe-noexec</span><span class="why">no sanctioned computation ran · nothing attested · the number is unproven</span></span></li>';
    return beatHead(2, "source", "Observe", "The live trace ranked <b>" + esc(CURRENT_METRIC) + "</b> first, excluded the legacy metric, and recorded the receipt as unproven.",
      "<code>" + esc(M.agent) + "</code> on <code>" + esc(M.model) + "</code> answered the question in a real session while the BQAA plugin wrote observer rows to <code>" + esc(M.dataset) + "</code>. In the tool result the observer can see the ranked titles, the one exclusion and one governance edge. It never sees SQL, paths or parameter values, and it never writes the authored bundle. These are the titles a later agent needs; this beat is what the observer actually saw, not a row dump.") +
      must("observer-only · rank 1 <code>" + esc(CURRENT_METRIC) + "</code> · <code>" + esc(LEGACY_METRIC) + "</code> excluded, superseded · receipt UNVERIFIABLE · session <code>" + esc(short(M.session_id, 8)) + "</code>, not the prior consume session, not the synthetic Germany trace") +
      '<div class="cols">' +
      '<div class="pane telemetry"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--telemetry)"></span>What the observer saw</span><span class="m">tool result · <code>okf_retrieve_context</code> · <code>' + esc(M.context_ref) + '</code></span></div>' +
      '<div class="pane-b"><ul class="saw">' + saw + "</ul></div></div>" +
      '<div class="pane source"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--source)"></span>The tape says the same</span><span class="m">beat 2 · read from the committed export</span></div>' +
      '<div class="pane-b" style="padding:0">' + transcriptHtml([cli.observeBlock]) + "</div>" +
      '<div class="pane-b"><ul class="checklist">' +
      check(c.rank1, "Tape <code>rank 1: " + esc(CURRENT_METRIC) + "</code> = snapshot tool result rank 1") +
      check(c.excluded, "Tape <code>excluded: " + esc(LEGACY_METRIC) + "</code> = snapshot exclusion, reason “" + esc(ex ? ex.reason : "") + "”") +
      check(c.unproven, "Tape <code>receipt: UNVERIFIABLE</code> · nothing attested") +
      check(c.session && c.count, "Session <code>" + esc(short(M.session_id, 8)) + "</code> · " + M.event_count + " rows, histogram Σ " + o.sum + " · agent <code>" + esc(M.agent) + "</code> · <code>" + esc(M.model) + "</code>") +
      info("Full export (" + Math.round(snap.export_bytes / 1024) + " KB) is on " + link(PR_URL, "pr", "SDK PR 474") + " (merged 2026-09-03; export attached pre-merge) · not padded · not dumped here. Table: " + link(BQ_CONSOLE, "bq", "BigQuery console") + ".") +
      "</ul></div></div></div>" +
      sampleRowsHtml();
  }

  // ---- beat 3: publish ---------------------------------------------------------------
  var selectedFile = null;
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
  function stubCards() {
    return '<div class="stubs">' + D.bundle.files.map(function (f) {
      var dep = f.status === "deprecated";
      var isLog = f.path === "log.md";
      return '<button type="button" class="card stub" data-file="' + esc(f.path) + '"' + (f.path === selectedFile ? ' aria-current="true"' : "") + ' style="text-align:left;cursor:pointer;width:100%">' +
        '<div class="ch"><span class="name">' + esc(isLog ? "log.md" : f.title) + '</span><span class="etype' + (f.type === "Attested Computation" ? " comp" : "") + '">' + esc(isLog ? "reserved" : f.type) + "</span></div>" +
        '<div class="pins">' +
        (isLog ? '<span class="pin">§9 reserved · no frontmatter</span>' :
          '<span class="pin' + (dep ? " dep" : "") + '"><b>lifecycle</b> ' + esc(f.status) + "</span>" +
          (f.rank ? '<span class="pin"><b>rank</b> ' + f.rank + "</span>" : "") +
          (dep ? '<span class="pin dep">' + esc(f.reason) + "</span>" : "")) +
        '<span class="pin"><b>sha256</b> ' + esc(short(f.sha256, 12)) + "</span>" +
        "</div></button>";
    }).join("") + "</div>";
  }
  function renderPublish() {
    var kv = D.cli.kv, d = D.ident, a = D.authored, M = D.live, c = D.checks, cli = D.cli, pub = d.publication_id;
    var prior = X && X.prior ? X.prior.meta : null;
    if (!selectedFile) selectedFile = "metrics/active-customer-revenue.md";
    var hl = {}; hl.SESSION = M.session_id; hl.CONTEXT_REF = M.context_ref; hl.PUBLICATION_ID = pub; hl.OBSERVATION_ID = d.observation_id; hl.SNAPSHOT_ID = d.snapshot_id;
    var dep = D.bundle.docs.filter(function (f) { return f.status === "deprecated"; })[0];
    return beatHead(3, "split", "Publish", "One command turns that telemetry into derived OKF — the handle a Knowledge Catalog entry would expose.",
      "<code>python examples/okf_bqaa_adapter/run.py</code> read the committed export and wrote <b>" + esc(kv.FILES) + " derived stubs</b>: the metric, the computation, the concept, the policy, two tables, the legacy metric marked <code>deprecated</code>, and a log. Each carries a title the next agent can use, and the set has its own identity chain, distinct from the authored bundle. Knowledge Catalog is where a later agent finds that publication by <code>context_ref</code>. <b>This CLI path did not write Catalog</b>: no entry, no DML, no real pin for this publication. What follows is the handle a Catalog entry would expose.") +
      must("8 stubs with titles, not just hashes · <code>" + esc(LEGACY_METRIC) + "</code> carried as deprecated · one handle <code>" + esc(M.context_ref) + "</code> → publication · no Catalog write claimed · authored <code>cymbal-finance-core</code> untouched") +
      '<div class="handle"><div class="th">Knowledge Catalog · the handle a Catalog entry would expose</div>' +
      '<div class="h"><b>context_ref</b> ' + esc(M.context_ref) + ' &nbsp;→&nbsp; <b>publication_id</b> ' + esc(pub) + " &nbsp;·&nbsp; <b>label</b> derived/demo</div>" +
      "<p><b>Honesty, on this beat.</b> No Knowledge Catalog entry was created and no DML ran on this CLI path; the handle above is rendered from the CLI's <code>mapping.json</code> and <code>live_identities.json</code>. There is no real Catalog pin for publication <code>" + esc(short(pub, 15)) + "</code>. A Catalog entry for this publication would expose exactly this: the ref, the publication, the derived/demo label, and the stub titles below.</p>" +
      (prior ? '<details class="nn" style="margin-top:10px"><summary>Prior leftover · Dataplex entry <code>' + esc(prior.kc_entry_id) + '</code> · from the earlier consume experiment, not this run</summary><div class="nn-b"><p class="fixture-note">Prior experiment leftover. The entry <code>' + esc(prior.kc_entry_id) + '</code> in group <code>' + esc(prior.kc_entry_group) + '</code> (' + esc(prior.kc_location) + ') was created for the earlier consume experiment and its description names the synthetic Germany publication <code>' + esc(short(prior.publication_id, 19)) + '</code>, not this demo\'s <code>' + esc(short(pub, 19)) + '</code>. It is not a pin for this publication.</p><div class="live-links">' + link(prior.kc_console, "kc", "Find the prior entry in Dataplex") + "</div></div></details>" : "") +
      "</div>" +
      '<div class="cols">' +
      '<div class="pane catalog"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--catalog)"></span>The 8 derived stubs</span><span class="m">titles from the observed envelope · hashes from <code>live_identities.json</code> · click one</span></div>' +
      '<div class="pane-b">' + stubCards() + "</div>" + fileCard(selectedFile) + "</div>" +
      '<div class="pane source"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--source)"></span>The tape</span><span class="m">beat 3 · <code>run.py</code>, then the stub titles</span></div>' +
      '<div class="pane-b" style="padding:0">' + transcriptHtml([cli.runBlock, cli.titlesBlock], hl) + "</div>" +
      '<div class="pane-b"><ul class="checklist">' +
      check(c.titles, "Every <code>title:</code> on the tape is one of the derived stubs (" + cli.titleLines.length + " titles)") +
      check(!!dep && dep.title === LEGACY_METRIC, "<code>" + esc(LEGACY_METRIC) + "</code> is carried as <code>deprecated</code> with its reason, so the next agent can see why to skip it") +
      check(c.pub && c.mapping, "Transcript <code>PUBLICATION_ID</code> = <code>live_identities.json</code> = the one binding in <code>mapping.json</code>") +
      check(c.files && c.adapter, "Transcript <code>FILES " + esc(kv.FILES) + "</code> = hashed files · adapter <code>" + esc(kv.ADAPTER) + "</code>") +
      check(c.distinct, "Distinct from authored <code>" + esc(a.inputs.bundle_key) + "</code> · pub <code>" + short(a.publication_id, 16) + "</code> stays pinned and unchanged") +
      check(c.receipt, "Transcript <code>RECEIPT UNVERIFIABLE rcpt-observe-noexec</code> · nothing attested") +
      "</ul></div></div></div>" +
      renderIdentityChain() + renderProjectionShape();
  }
  function renderIdentityChain() {
    var d = D.ident, M = D.live, c = D.checks;
    return '<details class="nn"><summary>Identity chain · pinned from CLI · <code>live_identities.json</code></summary><div class="nn-b">' +
      '<p class="fixture-note">The adapter is Python in the SDK (<code>adapter.py</code>: observe / adapt / compute_identities / project, canonical CBOR + domain-separated SHA-256, PROFILE.md rules). This browser hashed 0 bytes for these identities. <code>adapter.js</code> on this page is only used for the labelled SYNTHETIC Germany hashing check under beat 1.</p>' +
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
      "</dl><ul class=\"checklist\">" +
      check(c.obs && c.snap && c.pub, "Transcript <code>OBSERVATION_ID</code> / <code>SNAPSHOT_ID</code> / <code>PUBLICATION_ID</code> = <code>live_identities.json</code> = IDs panel") +
      check(c.session && c.trace && c.table && c.model, "Transcript <code>SESSION</code> / <code>TRACE</code> / <code>TABLE</code> / <code>MODEL</code> = <code>live.json</code> (<code>gemini-3.8-flash</code>)") +
      check(c.ref, "Transcript <code>CONTEXT_REF</code> = <code>live.json</code> context_ref = receipt context_ref") +
      info("No <code>computation:</code> artifact in the derived stub: the observer never sees SQL. It cites the observed envelope under <code>sources</code>.") +
      "</ul></div></details>";
  }
  function renderProjectionShape() {
    var d = D.ident, M = D.live, pub = d.publication_id, snap = d.snapshot_id, docs = D.bundle.docs;
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
    return '<details class="nn"><summary>Projection shape · what a Catalog entry and the BigQuery projection tables would carry · derived views, no write</summary><div class="nn-b">' +
      '<p class="fixture-note">Rendered from the pinned identities, not read back from Dataplex or BigQuery. On this CLI path neither received a write. The live <code>' + esc(M.table) + '</code> table is the observer source (read-only); it is not a projection target.</p>' +
      '<div class="cols even">' +
      '<div class="pane catalog"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--catalog)"></span>Knowledge Catalog · discovery</span><span class="m">derived view · no entry created</span></div><div class="pane-b"><div class="cards">' +
      docs.map(function (f) {
        return '<div class="card"><div class="ch"><span class="name">' + esc(f.title) + '</span><span class="etype">okf-bundle · derived view</span></div><div class="pins">' +
          '<span class="pin"><b>okf.type</b> ' + esc(f.type) + "</span>" +
          '<span class="pin' + (f.status === "deprecated" ? " dep" : "") + '"><b>okf.lifecycle</b> ' + esc(f.status) + "</span>" +
          '<span class="pin"><b>okf.provenance</b> bqaa observer · derived</span>' +
          '<span class="pin pub"><b>okf.publication_id</b> ' + esc(short(pub, 19)) + "</span>" +
          (f.type === "Attested Computation" ? '<span class="pin" style="border-color:#F0D9B8;background:var(--runtime-bg);color:var(--runtime)"><b style="color:var(--runtime)">okf-computation</b> runtime bigquery · receipt UNVERIFIABLE</span>' : "") +
          "</div></div>";
      }).join("") + "</div></div></div>" +
      '<div class="pane runtime"><div class="pane-h"><span class="t"><span class="sw" style="background:var(--runtime)"></span>BigQuery · serving</span><span class="m">RFC projection shape · not a live table, no DML</span></div><div class="pane-b">' +
      table("publications", pubRow) + table("deployment_heads", headRow, "head advanced") + table("nodes_current", nodes, "one row per concept version") + (edges.length ? table("edges_current", edges, "from the observed envelope") : "") +
      "</div></div></div></div></details>";
  }

  // ---- beat 4: next agent ---------------------------------------------------------------
  var tryRef = null;
  function localLookup(ref) {
    var map = D.mapping.mapping || {};
    // Own-property only. The `in` operator is not fail-closed: constructor/toString/__proto__ inherit from Object.prototype.
    if (typeof ref !== "string" || !Object.hasOwn(map, ref) || typeof map[ref] !== "string") {
      return { ok: false, error: "FAIL_CLOSED context_ref not bound in mapping (fail closed): '" + ref + "'", exit: 2 };
    }
    return { ok: true, result: { context_ref: ref, publication_id: map[ref], label: "derived/demo" }, exit: 0 };
  }
  function renderNextAgent() {
    var M = D.live, d = D.ident, c = D.checks, cli = D.cli, lk = cli.lookup || {}, o = D.obs;
    var okNever = c.lookupNever;
    var tried = tryRef === null ? null : localLookup(tryRef);
    var ex = o.excluded || { title: LEGACY_METRIC, reason: "superseded" };
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
    return beatHead(4, "ink", "Next agent", "The next agent looks up the handle, uses <b>" + esc(CURRENT_METRIC) + "</b>, skips legacy, and reports the number as unproven.",
      "<code>run.py --lookup '" + esc(M.context_ref) + "'</code> returns the derived publication and nothing else: three keys, none from the never-emit list. From that publication the next agent reads the same titles the observer saw: <b>" + esc(CURRENT_METRIC) + "</b> at rank 1, <b>" + esc(ex.title) + "</b> marked deprecated with its reason, and a receipt that is <code>UNVERIFIABLE</code>. So it uses the current metric, skips legacy, and says the number is unproven. That is the payoff. Anything else fails closed.") +
      must("lookup → {<code>context_ref</code>, <code>publication_id</code>, <code>label</code>} · agent uses <code>" + esc(CURRENT_METRIC) + "</code>, not legacy · number reported unproven · junk ref → <code>FAIL_CLOSED</code>, exit 2, expected · browser calls no GCP") +
      '<div class="cols">' +
      '<div class="pane"><div class="pane-h"><span class="t">The tape · the lookup and the payoff</span><span class="m">beat 4 · exit 0 · the last frames of the tape</span></div>' +
      '<div class="pane-b" style="padding:0">' + transcriptHtml([cli.lookupBlock]) + "</div>" +
      '<div class="pane-b"><ul class="checklist">' +
      check(c.lookup, "Lookup returns <code>" + esc(M.context_ref) + "</code> → <code>" + esc(short(d.publication_id, 19)) + "</code>, label <code>derived/demo</code> · = <code>mapping.json</code>") +
      check(okNever, "Result keys " + Object.keys(lk).map(function (k) { return "<code>" + esc(k) + "</code>"; }).join(" ") + " ∩ never-emit = ∅") +
      check(c.payoff, "Tape ends on the payoff comment, after the labelled junk-ref exit: “" + esc(cli.payoffLine) + "”") +
      "</ul></div></div>" +
      '<div class="pane"><div class="pane-h"><span class="t">What the next agent does with it</span><span class="m">from the derived publication</span></div><div class="pane-b">' +
      '<ul class="does">' +
      '<li class="use"><span class="ic">✓</span><span><b>Uses ' + esc(CURRENT_METRIC) + '</b><span class="d">rank 1 in the derived publication · the current metric</span></span></li>' +
      '<li class="skip"><span class="ic">✕</span><span><b>Skips ' + esc(ex.title) + '</b><span class="d">carried as deprecated · ' + esc(ex.reason) + "</span></span></li>" +
      '<li class="unproven"><span class="ic">?</span><span><b>Reports the number as unproven</b><span class="d">receipt UNVERIFIABLE · rcpt-observe-noexec · nothing ATTESTED</span></span></li>' +
      "</ul>" +
      '<p class="fixture-note" style="margin-top:10px">Without this path, the next agent starts from the same shelf as the first one, legacy metric included, and with no receipt to point at.</p>' +
      "</div></div></div>" +
      '<div class="adk" style="margin-top:14px">' +
      '<div class="adk-h"><span class="agent"><span class="fw">SDK CLI · okf-bqaa-adapter:v0</span><b>run.py --lookup</b><span>mapping.json · one binding · fail closed on anything else</span></span>' +
      '<span class="model-badge"><span class="dot"></span>source · <b>' + esc(M.agent) + "</b> · " + esc(M.model) + "</span></div>" +
      '<div class="adk-b"><div class="transcript">' +
      '<div class="term fail"><div class="th expected">junk ref · exit 2 · expected fail-closed, not a crash</div>' + transcriptHtml([cli.junkBlock]) + "</div>" +
      '<div class="term try"><div class="th">try a ref · static mapping.json in this page · same rule as lookup.py · no store, no network</div>' +
      '<form class="tryform" data-try><input type="text" name="ref" value="' + esc(tryRef === null ? M.context_ref : tryRef) + '" aria-label="context_ref to resolve" spellcheck="false"><button class="btn primary" type="submit">--lookup</button></form>' +
      (tried ? (tried.ok ? '<pre class="cli">' + jsonHtml(tried.result, ["context_ref", "publication_id"]) + '\n<span class="cm"># exit 0</span></pre>' : '<pre class="cli"><span class="fail">' + esc(tried.error) + '</span>\n<span class="cm"># exit 2</span></pre>') : '<p class="fixture-note" style="margin:8px 0 0">Resolves against the committed <code>mapping.json</code> (one binding). Anything else fails closed, including <code>constructor</code>, <code>toString</code> and <code>__proto__</code>.</p>') +
      "</div></div>" +
      '<div class="side">' +
      '<div class="tile"><div class="th">receipt · this run</div><span class="verdict">UNVERIFIABLE · rcpt-observe-noexec</span><p>The observe agent retrieved context; it did not run a sanctioned computation. The receipt the adapter carries is a no-execution specimen bound to <code>' + esc(M.receipt_context_ref) + '</code>. <b>Nothing is ATTESTED.</b> The number is unproven, and the next agent says so.</p></div>' +
      '<details class="nn"><summary>Resolver · lookup.py on SDK PR 474</summary><div class="nn-b"><pre class="py">' + py + "</pre></div></details>" +
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
    stage.innerHTML = current === 1 ? renderAsk() : current === 2 ? renderObserve() : current === 3 ? renderPublish() : renderNextAgent();
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
