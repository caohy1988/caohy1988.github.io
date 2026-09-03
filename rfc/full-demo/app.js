/* Full-version OKF runtime demo: Catalog finds, BigQuery serves, and where each stops.
   Static viewer of live captures checked into live/ (see live/README.md). Vanilla JS, no build.
   The browser fetches same-origin JSON/text and renders it. It never calls GCP, never hashes,
   never resolves anything. Six beats: Ask → Observe → Catalog path → Sync (CLI) → Serve (BigQuery)
   → Attribution. Every pane carries one honesty label: live · seeded · recorded · prior · stub · RFC text only. */
(function () {
  "use strict";

  var TOTAL = 6;
  var current = 1;
  var D = null;

  var PROJECT = "test-project-0728-467323";
  var TABLE = PROJECT + ".okf_rfc_demo.agent_events";
  var OPERATOR = "raincoatrun@gmail.com";
  var S_OBS = "f21ee192-d989-4c38-894f-66b6b82eaf18";
  var S_CON = "04fa3d56-f2f1-413e-8c2b-ec116835af84";
  var S_OBS2 = "1e6dfed7-27ce-4c4d-b2e7-c45de7c241d1";
  var REF_OBS = "okf:env-observe#674153c572f6";
  var REF_CON = "okf:env-demo#a25e1c0ccbca";
  var PUB = {
    a25: "sha256:a25e1c0ccbcad270bf9e3b7a8f792167795381b6880bdc8a1ccde8df40ea52c5",
    p674: "sha256:674153c572f6be57618a8d769a1a2b21a3e20d98406b3d1e58dd00027bc45905",
    p53b: "sha256:53bd1651c43f69d53f591e4f91e3ccdda4640d8b36cb1dce1ac97328ffa39a77"
  };
  var IDENT = {
    observation_id: "sha256:85ea62a96e5076a292572a996f0408865c4c56aac696bbeb79a73bbc5eda8af6",
    snapshot_id: "sha256:f18befd010ff7e3d1fe140303626a82dc985c986846093f73643e7d0eea92b75",
    publication_id: PUB.p53b
  };
  var NEVER_EMIT = ["concept_version_id", "bundle_path", "source_path", "principal", "query_text", "sql", "parameter_values", "destination_table"];
  var CURRENT_METRIC = "Active-customer revenue";
  var LEGACY_METRIC = "Customer revenue (legacy)";
  var BQ_CONSOLE = "https://console.cloud.google.com/bigquery?project=" + PROJECT + "&ws=!1m5!1m4!4m3!1s" + PROJECT + "!2sokf_rfc_demo!3sagent_events";
  var KC_CONSOLE = "https://console.cloud.google.com/dataplex/search?project=" + PROJECT + "&q=okf-rfc-demo";
  var VERBATIM = "No. The number is unproven.";
  // Honesty label per demo_evidence.source, rendered as a column on beat 6 (checked by tools/check_full_demo.py).
  var EVID_LABELS = { adapter_tape_pr474_476d37dc: ["recorded", "recorded · adapter CLI tape, PR 474"], legacy_catalog_description: ["prior", "prior · okf-derived-germany, no aspect"] };
  function evidLabel(v) { var l = EVID_LABELS[v]; return l ? src(l[0], l[1]) : src("stub", "unlabelled source"); }
  var TRAPS = { 1: "trap · over-claiming trust", 4: "static pack cannot answer · history", 6: "trap · the dead metric", 10: "static pack cannot answer · roll-up", 11: "what would make it attested", 12: "the dead metric, named" };

  var stage = document.getElementById("stage");
  var btnBack = document.getElementById("btn-back");
  var btnNext = document.getElementById("btn-next");
  var stepCount = document.getElementById("step-count");
  var stepButtons = Array.prototype.slice.call(document.querySelectorAll(".step"));

  // ---- helpers -----------------------------------------------------------
  function esc(s) { return String(s === undefined || s === null ? "" : s).replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;"); }
  function short(id, n) { n = n || 18; return id ? String(id).slice(0, n) + "…" : "—"; }
  function shortId(id) { return id ? String(id).slice(0, 8) + "…" : "—"; }
  function parseMaybe(v) { if (typeof v === "string") { try { return JSON.parse(v); } catch (e) { return v; } } return v; }
  function fetchJson(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.json(); }); }
  function fetchText(u) { return fetch(u).then(function (r) { if (!r.ok) throw new Error(u + " → " + r.status); return r.text(); }); }
  function jsonHtml(obj, hlKeys) {
    hlKeys = hlKeys || [];
    var text = JSON.stringify(obj, null, 2);
    return esc(text).replace(/(&quot;(?:[^&]|&(?!quot;))*?&quot;)(\s*:)?|\b(true|false|null)\b|(-?\d+(?:\.\d+)?)/g, function (m, str, colon, bool, num) {
      if (str !== undefined) {
        if (colon !== undefined) {
          var key = str.slice(6, -6);
          return '<span class="' + (hlKeys.indexOf(key) >= 0 ? "k hl" : "k") + '">' + str + "</span>" + colon;
        }
        return '<span class="s">' + str + "</span>";
      }
      if (bool !== undefined) return '<span class="b">' + bool + "</span>";
      return '<span class="n">' + num + "</span>";
    });
  }
  function pre(obj, hlKeys, cls) { return '<pre class="json ' + (cls || "") + '">' + jsonHtml(obj, hlKeys) + "</pre>"; }
  function yaml(text, hl) {
    hl = hl || [];
    var out = esc(text).replace(/^(\s*)([A-Za-z_][A-Za-z0-9_-]*)(:)/gm, function (m, sp, k, c) {
      return sp + '<span class="' + (hl.indexOf(k) >= 0 ? "k hl" : "k") + '">' + k + "</span>" + c;
    });
    return '<pre class="yaml">' + out + "</pre>";
  }
  function src(kind, label) { return '<span class="src ' + kind + '">' + esc(label) + "</span>"; }
  function pane(cls, title, meta, body, tone) {
    return '<div class="pane ' + (tone || "") + '"><div class="pane-h"><span class="t">' + title + '</span><span class="m">' + meta + "</span></div>" + '<div class="pane-b ' + (cls || "") + '">' + body + "</div></div>";
  }
  function check(ok, html) { return '<li class="' + (ok ? "ok" : "no") + '"><span class="ic">' + (ok ? "✓" : "✕") + "</span><span>" + html + "</span></li>"; }
  function info(html) { return '<li class="info"><span class="ic">i</span><span>' + html + "</span></li>"; }
  function beatHead(n, tone, name, headline, lede) {
    return '<div class="beat-head"><span class="beat-num ' + tone + '">' + n + '</span><span class="beat-kicker">Beat ' + n + " of " + TOTAL + " · " + esc(name) + "</span></div>" +
      '<h2 class="beat-headline">' + headline + "</h2>" + '<p class="beat-lede">' + lede + "</p>";
  }
  function must(html) { return '<p class="must"><b>must prove</b> <span>' + html + "</span></p>"; }
  function caption(html) { return '<p class="caption">' + html + "</p>"; }
  function stripText(s) { var m = String(s || "").match(/^text: '([\s\S]*)'$/); return m ? m[1] : String(s || ""); }
  function tsLive(ts) { return String(ts).replace("T", " ").slice(0, 19); }
  function link(href, label) { return '<a class="lk" href="' + esc(href) + '" target="_blank" rel="noopener">' + label + " ↗</a>"; }
  function fileLink(rel, label) { return '<a href="' + esc(rel) + '"><code>' + esc(label || rel) + "</code></a>"; }
  function table(cols, rows, opts) {
    opts = opts || {};
    if (!rows.length) return '<div class="empty"><b>0 rows.</b> ' + (opts.empty || "") + "</div>";
    var head = "<tr>" + cols.map(function (c) { return "<th>" + esc(c.label || c.key) + "</th>"; }).join("") + "</tr>";
    var body = rows.map(function (r) {
      var cls = opts.rowClass ? opts.rowClass(r) : "";
      return '<tr class="' + cls + '">' + cols.map(function (c) {
        var v = r[c.key];
        var html = c.render ? c.render(v, r) : esc(v === null || v === undefined ? "NULL" : v);
        return '<td class="' + (c.cls || "") + '">' + html + "</td>";
      }).join("") + "</tr>";
    }).join("");
    return '<div class="rt-wrap"><table class="rt"><thead>' + head + "</thead><tbody>" + body + "</tbody></table></div>";
  }
  function pubCell(v) { return v ? '<span class="pub" title="' + esc(v) + '">' + esc(short(v, 19)) + "</span>" : "NULL"; }
  function refCell(v) { return v ? '<span class="ref">' + esc(v) + "</span>" : "NULL"; }
  function sidCell(v) { return v ? '<span title="' + esc(v) + '">' + esc(shortId(v)) + "</span>" : "NULL"; }
  function resCell(v) { return '<span class="res ' + esc(v) + '">' + esc(v) + "</span>"; }
  function jobs(ids) {
    return '<p class="jobs">bq job id' + (ids.length > 1 ? "s" : "") + ": " + ids.map(function (j) { return "<code>" + esc(j) + "</code>"; }).join(" · ") + " · user_email on record: <code>" + esc(D.jobUser || OPERATOR) + "</code></p>";
  }
  function aspectOf(entry, suffix) {
    var out = null;
    Object.keys(entry.aspects || {}).forEach(function (k) { if (k.slice(-suffix.length) === suffix) out = entry.aspects[k]; });
    return out;
  }

  // ---- load ----------------------------------------------------------------
  var FILES = {
    obs: "live/session_f21ee192.json", con: "live/session_04fa3d56.json", obs2: "live/session_1e6dfed7.json",
    scan: "live/never_emit_scan.json", v0: "live/sessions_by_context_ref.json",
    attr: "live/beat6_attribution.json", evid: "live/beat6_demo_evidence.json",
    heads: "live/beat5_serve_stmt1.json", hist: "live/beat5_serve_stmt2.json", resol: "live/beat5_serve_stmt3.json", pubs: "live/beat5_serve_stmt4.json", view: "live/beat5_serve_stmt5.json",
    jobs: "live/bq_jobs_identity.json", summary: "live/sessions_summary.json",
    legacy: "live/catalog_entry_okf-derived-germany.json", legacyLc: "live/lookup_context_okf-derived-germany.json", // prior experiment, labelled prior on beat 3
    lc11: "live/lookup_context_11_resources.json", lcMissing: "live/lookup_context_missing_entry.json",
    metric: "live/catalog_shipped_entry_metric_viewALL.json", comp: "live/catalog_shipped_entry_computation_viewALL.json", legMetric: "live/catalog_shipped_entry_legacy_metric_viewALL.json",
    lcMetric: "live/lookup_context_shipped_metric.json", lcComp: "live/lookup_context_shipped_computation.json",
    searchType: "live/search_entries_okf_type_metric.json", searchDep: "live/search_entries_okf_status_deprecated.json",
    entries: "live/catalog_entries_list_after_push.json", iam: "live/catalog_entry_group_iam.json", aspectType: "live/catalog_aspect_type_okf.json",
    matrix: "matrix.json", stories: "stories.json"
  };
  var TEXTS = { setupT: "live/catalog_setup_transcript.txt", pushT: "live/catalog_push_transcript.txt", ddlOut: "live/setup_runtime_tables.out", discovery: "live/lookup_context_discovery.txt" };
  var keys = Object.keys(FILES), tkeys = Object.keys(TEXTS);
  Promise.all(keys.map(function (k) { return fetchJson(FILES[k]); }).concat(tkeys.map(function (k) { return fetchText(TEXTS[k]); }))).then(function (res) {
    D = {};
    keys.forEach(function (k, i) { D[k] = res[i]; });
    tkeys.forEach(function (k, i) { D[k] = res[keys.length + i]; });
    prep();
    renderMatrix();
    renderStories();
    renderIds();
    render();
  }).catch(function (err) {
    stage.innerHTML = '<div class="error-box"><b>Could not load the static files.</b> ' + esc(err.message) +
      '<p style="margin-top:10px">Browsers block <code>fetch()</code> over <code>file://</code>. Serve the repo root instead: <code>python3 -m http.server 8000</code> then open <code>http://localhost:8000/rfc/full-demo/</code>.</p></div>';
  });

  // ---- prep -----------------------------------------------------------------
  function rows(raw) { return raw.map(function (r) { var o = {}; Object.keys(r).forEach(function (k) { o[k] = r[k]; }); o.content = parseMaybe(r.content); o.attributes = parseMaybe(r.attributes); return o; }); }
  function prepSession(raw) {
    var evs = rows(raw);
    var hist = {};
    evs.forEach(function (e) { hist[e.event_type] = (hist[e.event_type] || 0) + 1; });
    var inv = [], byTrace = {};
    evs.forEach(function (e) { if (!byTrace[e.trace_id]) { byTrace[e.trace_id] = { trace_id: e.trace_id, events: [] }; inv.push(byTrace[e.trace_id]); } byTrace[e.trace_id].events.push(e); });
    inv.forEach(function (v, i) {
      v.n = i + 1;
      var q = v.events.filter(function (e) { return e.event_type === "USER_MESSAGE_RECEIVED"; })[0];
      v.question = q && q.content && q.content.text_summary || "";
      v.tools = v.events.filter(function (e) { return e.event_type === "TOOL_COMPLETED"; }).map(function (e) { return e.content; });
      v.retrieve = v.tools.filter(function (t) { return t.tool === "okf_retrieve_context"; })[0] || null;
      v.receipt = v.tools.filter(function (t) { return t.tool === "okf_run_attested_computation"; })[0] || null;
      v.lookup = v.tools.filter(function (t) { return t.tool === "lookup_okf_context"; })[0] || null;
      var finals = v.events.filter(function (e) { return e.event_type === "LLM_RESPONSE" && e.content && typeof e.content.response === "string" && !/^call: /.test(e.content.response); });
      var ar = v.events.filter(function (e) { return e.event_type === "AGENT_RESPONSE"; })[0];
      v.answer = stripText(ar && ar.content && ar.content.response || (finals.length ? finals[finals.length - 1].content.response : ""));
      v.t0 = v.events[0].timestamp; v.t1 = v.events[v.events.length - 1].timestamp;
    });
    var req = evs.filter(function (e) { return e.event_type === "LLM_REQUEST"; })[0];
    var prompts = {};
    evs.forEach(function (e) { if (e.event_type === "LLM_REQUEST" && e.content && e.content.system_prompt) prompts[e.content.system_prompt] = true; });
    var toolRows = evs.filter(function (e) { return e.event_type === "TOOL_COMPLETED"; });
    var contentKeys = {};
    (function walk(o) { if (Array.isArray(o)) o.forEach(walk); else if (o && typeof o === "object") Object.keys(o).forEach(function (k) { contentKeys[k] = true; walk(o[k]); }); })(toolRows.map(function (e) { return e.content; }));
    return {
      rows: evs, hist: hist, count: evs.length, inv: inv, sessionId: evs.length ? evs[0].session_id : "", agent: evs.length ? evs[0].agent : "",
      systemPrompt: req && req.content && req.content.system_prompt || "", promptCount: Object.keys(prompts).length,
      toolRows: toolRows, toolKeys: contentKeys, violations: NEVER_EMIT.filter(function (k) { return contentKeys[k]; }),
      withRef: toolRows.filter(function (e) { return e.content && e.content.result && e.content.result.context_ref; }).length,
      sessionOk: evs.every(function (e) { return e.session_id === evs[0].session_id; }),
      t0: evs.length ? evs[0].timestamp : "", t1: evs.length ? evs[evs.length - 1].timestamp : ""
    };
  }
  function prep() {
    D.F = prepSession(D.obs);    // observe agent, 180 rows, 12 invocations
    D.C = prepSession(D.con);    // consume agent, 14 rows, the overclaim
    D.G = prepSession(D.obs2);   // observe agent, 15 rows, one invocation
    D.F.retrieve = D.F.inv.map(function (v) { return v.retrieve; }).filter(Boolean);
    D.F.receipts = D.F.inv.map(function (v) { return v.receipt; }).filter(Boolean);
    var all = D.F.retrieve.concat(D.G.inv.map(function (v) { return v.retrieve; }).filter(Boolean));
    D.exclusions = { total: all.length, legacy: all.filter(function (r) { return (r.result.okf.excluded || []).some(function (x) { return x.title === LEGACY_METRIC; }); }).length, rank1: all.filter(function (r) { var it = (r.result.okf.items || []).slice().sort(function (a, b) { return a.rank - b.rank; })[0]; return it && it.title === CURRENT_METRIC; }).length };
    D.unproven = D.F.inv.filter(function (v) { return /unproven/i.test(v.answer); }).length;
    D.verbatim = D.F.inv.filter(function (v) { return v.answer.indexOf(VERBATIM) >= 0; }).length;
    D.receiptsIdentical = D.F.receipts.filter(function (r) { return JSON.stringify(r.result) === JSON.stringify(D.F.receipts[0].result); }).length;
    D.tableRows = D.summary.reduce(function (s, r) { return s + Number(r.rows_in_table); }, 0);
    D.fourth = D.summary.filter(function (r) { return [S_OBS, S_CON, S_OBS2].indexOf(r.session_id) < 0; })[0] || null;
    D.overclaim = D.C.inv[0] || null;
    D.scanHits = D.scan.reduce(function (s, r) { return s + Number(r.hits); }, 0);
    D.scanned = D.scan.length ? Number(D.scan[0].tool_rows_scanned) : 0;
    D.scanRef = D.scan.length ? Number(D.scan[0].rows_with_context_ref) : 0;
    D.attrSum = { attributed: 0, receipt_only: 0 };
    D.attr.forEach(function (r) { D.attrSum[r.band] = (D.attrSum[r.band] || 0) + Number(r.n); });
    var seen = {}, dup = false;
    D.attr.forEach(function (r) { var k = [r.session_id, r.tool, r.context_ref, r.publication_id].join("|"); if (seen[k]) dup = true; seen[k] = true; });
    D.attrDup = dup;
    D.jobUser = D.jobs.length && D.jobs.every(function (j) { return j.user_email === D.jobs[0].user_email; }) ? D.jobs[0].user_email : "mixed";
    D.jobIds = {};
    D.jobs.forEach(function (j) { var m = j.job_id.match(/^okf_full_demo_([a-z0-9_]+?)_\d{8}T\d{6}Z$/); if (m) { D.jobIds[m[1]] = D.jobIds[m[1]] || []; D.jobIds[m[1]].push(j.job_id); } });
    D.metricOkf = aspectOf(D.metric, ".okf"); D.metricOverview = aspectOf(D.metric, ".overview");
    D.compOkf = aspectOf(D.comp, ".okf"); D.legMetricOkf = aspectOf(D.legMetric, ".okf");
    D.aspectFields = (D.aspectType.metadataTemplate && D.aspectType.metadataTemplate.recordFields || []).map(function (f) { return f.name; });
    D.lcMetricKeys = ["okf_type", "status", "sources", "extra", "runtime", "parameters", "executor", "attester", "verdict", "publication_id"].filter(function (k) { return new RegExp("(^|\\n)\\s*" + k + ":").test(D.lcMetric.context || ""); });
    D.lcCompKeys = ["runtime", "parameters", "executor", "attester", "verdict"].filter(function (k) { return new RegExp("(^|\\n)\\s*" + k + ":").test(D.lcComp.context || ""); });
    D.shipped = (D.entries || []).filter(function (e) { return /\/entryTypes\/okf-bundle$/.test(e.entryType); });
  }
  function jobsFor(prefix) { return D.jobIds[prefix] || []; }

  // ---- beat 1: ask ----------------------------------------------------------------
  function renderAsk() {
    var F = D.F, C = D.C;
    var ex = (F.retrieve[0] && F.retrieve[0].result.okf.excluded[0]) || { title: LEGACY_METRIC, reason: "superseded" };
    var qs = F.inv.map(function (v) {
      var t = TRAPS[v.n];
      return '<li class="' + (t ? "trap" : "") + '">' + esc(v.question) + (t ? '<span class="tag">' + esc(t) + "</span>" : "") + "</li>";
    }).join("");
    return beatHead(1, "telemetry", "Ask", "A finance agent is asked: “" + esc(F.inv[0] ? F.inv[0].question : "") + "” — and then eleven more.",
      "Twelve real questions from one multi-turn ADK session, read from <code>USER_MESSAGE_RECEIVED</code> rows. Two traps run through them: the dead metric <b>" + esc(ex.title) + "</b> (" + esc(ex.reason) + ") is still on the shelf, and nothing has run as a sanctioned computation, so any confident number is an over-claim. A second, one-question session shows what the over-claim sounds like.") +
      must("nothing is fictional · 12 questions = 12 <code>USER_MESSAGE_RECEIVED</code> rows in session <code>" + esc(shortId(S_OBS)) + "</code> · the ask is hard-path context → derived OKF, not HITL, not sentiment, not BQAA-as-truth") +
      '<div class="src-legend">Labels on this page: ' + src("live", "live GCP") + src("seeded", "seeded by operator") + src("recorded", "recorded run") + src("prior", "prior experiment") + src("stub", "stubbed") + src("rfc", "RFC text only") + "</div>" +
      '<div class="pane ask-what"><div class="pane-h"><span class="t">What this demo is asking</span><span class="m">lock from the four-beat demo · unchanged</span></div><div class="pane-b">' +
      "<p><b>Are we trusting what is in BQAA? Asking a human-in-the-loop or customer sentiment to decide what to promote? Or adding context the agent obtained via the hard path into OKF so it is available for easy discovery?</b> The third one.</p><ul>" +
      "<li><b>Yes: hard path → derived OKF for discovery.</b> Context this agent earned (ranked <code>" + esc(CURRENT_METRIC) + "</code>, excluded <code>" + esc(ex.title) + "</code>, receipt unproven) was observed by BQAA and projected into derived OKF; this page then pushes that derived bundle into shipped Knowledge Catalog types and asks what BigQuery adds.</li>" +
      "<li><b>Not trusting BQAA as knowledge or truth.</b> BQAA is observer-only. Telemetry is not the bundle and not a truth score.</li>" +
      "<li><b>Not human-in-the-loop promotion or customer-sentiment ranking.</b> No such feature exists here.</li>" +
      "<li><b>Trust means process integrity of what was observed.</b> Opaque IDs, fail-closed lookup, no over-claim. The number stays <code>UNVERIFIABLE</code> on every receipt on this page.</li>" +
      "</ul></div></div>" +
      '<p class="beat-kicker" style="margin:18px 0 6px">The twelve questions · session <code>' + esc(S_OBS) + "</code> · " + esc(tsLive(F.t0)) + " → " + esc(tsLive(F.t1)) + " UTC " + src("live", "live · agent_events") + "</p>" +
      '<ol class="qlist">' + qs + "</ol>" +
      '<div class="grid2">' +
      pane("", '<span class="sw" style="background:var(--warn)"></span>Trap 2, as it actually sounded', src("live", "live · session " + shortId(S_CON)),
        '<div class="quote">' + esc(D.overclaim ? D.overclaim.answer : "") + '<span class="cite">' + esc(C.agent) + " · " + esc(S_CON) + " · " + esc(tsLive(C.t1)) + " UTC · tool <code>lookup_okf_context</code> returned <code>ok: true</code> and no verdict</span></div>" +
        caption("No computation ran. No verdict existed. The word “verified” was produced from an <code>ok: true</code>. Beat 3 shows the system prompt and the tool result behind it."), "") +
      pane("", '<span class="sw" style="background:var(--ok)"></span>What a good answer did · one verbatim example', src("live", "live · session " + shortId(S_OBS)),
        '<div class="quote good">' + esc((F.inv.filter(function (v) { return v.answer.indexOf(VERBATIM) >= 0; })[0] || { answer: "" }).answer.split("\n").filter(function (l) { return l.indexOf(VERBATIM) >= 0; })[0] || "(no verbatim sentence found in the captured answers)") + '<span class="cite">' + esc(F.agent) + " · " + esc(S_OBS) + " · invocation 1 of " + F.inv.length + " · receipt <code>UNVERIFIABLE</code></span></div>" +
        caption("Two counts, kept apart: <b>" + D.unproven + " of " + F.inv.length + "</b> final answers in this session contain the word “unproven”, because the receipt tool returned a <code>verdict</code> the prompt had to report; <b>" + D.verbatim + " of " + F.inv.length + "</b> uses the exact four-word sentence quoted above. Beat 5 shows the receipt."), "") +
      "</div>" +
      '<ul class="checklist">' +
      check(F.inv.length === 12 && F.hist.USER_MESSAGE_RECEIVED === 12, "12 invocations, 12 <code>USER_MESSAGE_RECEIVED</code> rows, one session; the list above is read from the rows, not typed") +
      check(F.sessionOk && F.sessionId === S_OBS, "Every one of the " + F.count + " rows carries <code>session_id = " + esc(S_OBS) + "</code>") +
      check(!!D.overclaim && /verified/.test(D.overclaim.answer), "The over-claim quote is the <code>AGENT_RESPONSE</code> row of session <code>" + esc(shortId(S_CON)) + "</code>, verbatim") +
      info("Rows were pulled by <code>session_id</code> with explicit job ids; see “How this was built”. No agent was re-run for this page.") +
      "</ul>";
  }

  // ---- beat 2: observe ------------------------------------------------------------
  function histogramHtml(hist, order) {
    var types = order.filter(function (k) { return k in hist; }).concat(Object.keys(hist).filter(function (k) { return order.indexOf(k) < 0; }));
    var max = Math.max.apply(null, types.map(function (k) { return hist[k]; })), sum = types.reduce(function (s, k) { return s + hist[k]; }, 0);
    return '<div class="hist" role="img" aria-label="Event type histogram, ' + sum + ' rows">' + types.map(function (k) {
      return '<div class="hrow"><span class="hk">' + esc(k) + '</span><span class="hb"><span class="hf" style="width:' + Math.round(100 * hist[k] / max) + '%"></span></span><span class="hn">' + hist[k] + "</span></div>";
    }).join("") + '<div class="hsum"><span>' + types.length + " event types</span><span>Σ = " + sum + "</span></div></div>";
  }
  function renderObserve() {
    var F = D.F;
    var order = ["USER_MESSAGE_RECEIVED", "INVOCATION_STARTING", "AGENT_STARTING", "LLM_REQUEST", "LLM_RESPONSE", "TOOL_STARTING", "TOOL_COMPLETED", "AGENT_COMPLETED", "INVOCATION_COMPLETED"];
    var r0 = F.retrieve[0], rc = F.receipts[0];
    var scanRows = D.scan.map(function (r) { return { key: r.never_emit_key, hits: Number(r.hits) }; });
    var toolList = F.inv.map(function (v) {
      return '<li class="ev"><button type="button" aria-expanded="false" data-ev="t' + v.n + '"><span class="ts">' + esc(tsLive(v.t0).slice(11)) + '</span><span class="ty tool">TOOL_COMPLETED ×' + v.tools.length + '</span><span class="sm">' + v.tools.map(function (t) { return esc(t.tool); }).join(" → ") + ' · <span class="ref">' + esc(v.retrieve && v.retrieve.result.context_ref || "") + "</span></span><span class=\"car\">▸</span></button>" +
        '<div class="raw" hidden>' + pre(v.tools, ["context_ref", "publication_id", "verdict", "verdict_reason"]) + "</div></li>";
    }).join("");
    return beatHead(2, "source", "Observe", "One SQL query. 180 events, 24 tool calls, a <code>context_ref</code> on every result, and 0 hits on the never-emit list.",
      "BigQuery Agent Analytics wrote every event of the twelve-question session into <code>" + esc(TABLE) + "</code>. This beat is a read of that table: the histogram, the twenty-four tool completions, and a live scan of all 27 <code>TOOL_COMPLETED</code> payloads across the four sessions for the eight things an agent-facing payload must never carry.") +
      must("observer-only · telemetry is not the bundle · every tool result carries <code>context_ref</code> and none carries <code>concept_version_id</code>, paths, principal, SQL or parameter values") +
      '<div class="cols">' +
      pane("", '<span class="sw" style="background:var(--source)"></span>' + esc(TABLE) + " · session " + esc(shortId(S_OBS)), src("live", "live · " + F.count + " rows"),
        histogramHtml(F.hist, order) + jobs(jobsFor("session_f21ee192")), "source") +
      pane("", "Never-emit scan · all TOOL_COMPLETED rows, four sessions", src("live", "live · sql/never_emit_scan.sql"),
        table([{ key: "key", label: "never_emit_key", render: function (v) { return "<code>" + esc(v) + "</code>"; } }, { key: "hits", label: "hits", cls: "num" }], scanRows) +
        '<ul class="checklist" style="margin-top:10px">' +
        check(D.scanHits === 0, "0 hits across " + D.scanned + " tool payloads for all " + NEVER_EMIT.length + " keys") +
        check(D.scanRef === D.scanned, D.scanRef + " of " + D.scanned + " payloads carry <code>result.context_ref</code>") +
        check(F.violations.length === 0 && D.C.violations.length === 0, "Browser-side key walk over this page's copies of both sessions agrees: no never-emit key present") +
        info("<code>user_id</code> is a BQAA row column (pseudonym <code>" + esc(F.rows[0] && F.rows[0].attributes && F.rows[0].attributes.session_metadata && F.rows[0].attributes.session_metadata.user_id || "") + "</code>), not an agent-facing field.") +
        "</ul>" + jobs(jobsFor("never_emit_scan")), "") +
      "</div>" +
      '<div class="grid2">' +
      pane("", "The retrieve result the agent saw · invocation 1", src("live", "live · TOOL_COMPLETED"),
        (r0 ? pre(r0.result, ["context_ref", "publication_id", "item_count", "excluded_count"]) : '<div class="empty">no retrieve result</div>') +
        caption("Six items, one exclusion, a <code>context_ref</code> and the in-process pin <code>" + esc(short(PUB.p674, 19)) + "</code>. Titles, types, ranks, one edge. No bodies, no SQL, no paths."), "runtime") +
      pane("", "The receipt the agent saw · invocation 1", src("live", "live · TOOL_COMPLETED"),
        (rc ? pre(rc.result, ["verdict", "verdict_reason", "receipt_id", "parameter_schema"]) : '<div class="empty">no receipt</div>') +
        caption("<code>verdict: UNVERIFIABLE</code>, reason <code>no-execution</code>. The declared <code>parameter_schema</code> is the contract an executor would bind; no values were ever observed."), "runtime") +
      "</div>" +
      '<details class="nn"><summary>All 24 tool completions · 12 invocations · click to expand each pair</summary><div class="nn-b"><ul class="events">' + toolList + "</ul></div></details>";
  }

  // ---- beat 3: catalog path ---------------------------------------------------------
  function renderCatalog() {
    var C = D.C, F = D.F, o = D.overclaim;
    var m = D.metric, mo = D.metricOkf, co = D.compOkf;
    var okfFieldsPresent = mo ? Object.keys(mo.data) : [];
    var compFields = co ? Object.keys(co.data) : [];
    var lc11 = D.lc11 && D.lc11.error ? D.lc11.error : null;
    var hlC = function (s) { return esc(s).replace(/(say the number is produced by the sanctioned computation bound in that context_ref)/, "<mark>$1</mark>"); };
    var hlF = function (s) { return esc(s).replace(/(if the verdict is not ATTESTED, say plainly that the number is unproven)/, "<mark>$1</mark>"); };
    var markVerified = function (s) { return esc(s).replace(/(You can trust the number because it is verified)/, "<mark>$1</mark>"); };
    var searchDep = (D.searchDep.results || []).map(function (r) { return r.dataplexEntry.entrySource.displayName; });
    var searchType = (D.searchType.results || []).map(function (r) { return r.dataplexEntry.entrySource.displayName; });
    return beatHead(3, "catalog", "Catalog path: where it stops", "Discovery works and can show the signal layer. It cannot carry a verdict, compare a pin to a head, or follow links.",
      "The shipped sample (<code>setup.ts</code> + <code>push.ts</code> from <code>GoogleCloudPlatform/knowledge-catalog</code>) was run as the operator against the derived bundle the SDK adapter regenerated from the committed export. Eight <code>okf-bundle</code> entries now exist with the real 13-field <code>okf</code> aspect. Three panes: what <code>entries.get --view=ALL</code> returns, what <code>lookupContext</code> returns for the same entry, and the transcript of the agent that read a Catalog-shaped lookup and said “verified”.") +
      must("shipped OKF-in-KC is real on screen · <code>lookupContext</code> omits the <code>okf</code> aspect · eleven resources → 400 · no <code>verdict</code> field exists in the 13-field template · both system prompts shown · <code>okf-derived-germany</code> labelled prior") +
      '<div class="grid3">' +
      pane("", '<span class="sw" style="background:var(--catalog)"></span>(a) entries.get --view=ALL', src("live", "live · pushed okf-bundle entry"),
        "<p class=\"caption\" style=\"margin:0 0 8px\"><code>" + esc(m.name.split("/entries/")[1]) + "</code> · type <code>okf-bundle</code> · aspect <code>" + esc(Object.keys(m.aspects).filter(function (k) { return /\.okf$/.test(k); })[0] || "") + "</code></p>" +
        (mo ? pre(mo.data, ["okf_type", "status", "sources", "extra"]) : '<div class="empty">no okf aspect on this entry</div>') +
        caption("The <b>okf</b> aspect carries <code>" + okfFieldsPresent.join("</code>, <code>") + "</code> for the metric; on the computation entry it carries <code>" + compFields.join("</code>, <code>") + "</code>. The template has " + D.aspectFields.length + " fields: <code>" + D.aspectFields.join("</code> <code>") + "</code>. <b>None of them is a verdict</b>, and no <code>okf-context-runtime</code> pin exists yet because no sync has run.") +
        '<details class="nn"><summary>Computation entry aspect · runtime, parameters, executor and stop</summary><div class="nn-b">' + (co ? pre(co.data, ["runtime", "parameters", "executor"]) : "") + "</div></details>" +
        '<details class="nn"><summary>Overview aspect · the body Catalog serves to any catalogViewer</summary><div class="nn-b">' + (D.metricOverview ? '<pre class="cli">' + esc(D.metricOverview.data.content) + "</pre>" : "") + "</div></details>", "catalog") +
      pane("", '<span class="sw" style="background:var(--catalog)"></span>(b) lookupContext · same entry', src("live", "live · POST :lookupContext"),
        yaml(D.lcMetric.context || "", ["catalogEntry", "type", "description", "overview", "labels"]) +
        '<ul class="checklist" style="margin-top:10px">' +
        check(D.lcMetricKeys.length === 0, "No <code>okf</code> field in the response: " + ["okf_type", "status", "sources", "extra"].map(function (k) { return "<code>" + k + "</code>"; }).join(" ") + " all absent, although <code>entries.get</code> returns them for this entry") +
        check(D.lcCompKeys.length === 0, "On the computation entry: <code>runtime</code>, <code>parameters</code>, <code>executor</code>, <code>attester</code> absent too, and there is no <code>verdict</code> anywhere to omit") +
        check(!!lc11 && lc11.code === 400 && /ten resources/i.test(lc11.message), "Eleven resources → <code>400</code> “" + esc(lc11 ? lc11.message : "") + "”") +
        check(JSON.stringify(D.lcMissing) === "{}", "A non-existent entry → <code>{}</code>: an empty response, not an error; the caller cannot tell “missing” from “not permitted”") +
        info("Endpoint <code>projects/{project}/locations/{location}:lookupContext</code>: one location per call (discovery document, checked in). <b>No-link-following</b> is Google's documented behaviour; this page did not exercise it, so that row stays " + src("rfc", "RFC text only") + ".") +
        "</ul>" +
        '<details class="nn"><summary>lookupContext on the computation entry</summary><div class="nn-b">' + yaml(D.lcComp.context || "") + "</div></details>", "catalog") +
      pane("", '<span class="sw" style="background:var(--warn)"></span>(c) the agent that read a Catalog-shaped lookup', src("live", "live · session " + shortId(S_CON)),
        '<p class="beat-kicker" style="margin:0 0 4px">system prompt · <code>LLM_REQUEST.system_prompt</code></p><div class="sysprompt">' + hlC(C.systemPrompt) + "</div>" +
        '<p class="beat-kicker" style="margin:10px 0 4px">tool result · <code>lookup_okf_context</code></p>' + (o && o.lookup ? pre(o.lookup.result, ["context_ref", "publication_id", "ok"]) : "") +
        '<p class="beat-kicker" style="margin:10px 0 4px">answer · <code>AGENT_RESPONSE</code></p><div class="quote">' + markVerified(o ? o.answer : "") + '<span class="cite">' + esc(C.agent) + " · " + esc(S_CON) + " · " + esc(tsLive(C.t1)) + " UTC</span></div>" +
        caption("<b>Disclosure:</b> an illustration, not a controlled comparison. The two sessions differ in prompt, tool set and questions. What the pair shows is narrower and still useful: a contract with no verdict field permits an agent to say “verified”, and a prompt that leans on “sanctioned computation” language will do so.") +
        '<details class="nn"><summary>The other system prompt · session ' + esc(shortId(S_OBS)) + " · beat 5 shows its receipts</summary><div class=\"nn-b\"><div class=\"sysprompt\">" + hlF(F.systemPrompt) + "</div></div></details>", "") +
      "</div>" +
      caption("<b>Caption.</b> Discovery works and can show a pin; it cannot carry a verdict, compare the pin to a head, or follow links. The Catalog mapping (entry per concept, <code>okf</code> aspect, <code>overview</code> body, index and log entries, parent hierarchy) is shipped and complete; the runtime sits on it.") +
      '<div class="grid2">' +
      pane("", "searchEntries · the dead metric is still discoverable", src("live", "live · POST :searchEntries"),
        '<pre class="cli">$ POST …/locations/global:searchEntries {"query":"aspect:' + esc(PROJECT) + '.us-central1.okf.status=deprecated"}\n→ ' + esc(searchDep.join(", ") || "(no results)") + '\n\n$ POST …/locations/global:searchEntries {"query":"aspect:' + esc(PROJECT) + '.us-central1.okf.okf_type=\\"Metric\\""}\n→ ' + esc(searchType.join(", ") || "(no results)") + "</pre>" +
        caption("Generic <code>kcmd push</code> creates or patches and never deletes. <code>status</code> is a search predicate, not a retirement. Story 4: the runtime excludes the legacy metric at query time (beat 5)."), "catalog") +
      pane("", "EntryGroup IAM · the enforcement unit", src("live", "live · get-iam-policy"),
        pre(D.iam) + caption("No bindings on <code>okf-rfc-demo</code>; the operator reads it as project Owner. IAM on the EntryGroup cascades to every entry in it, so whoever holds <code>catalogViewer</code> on the group reads the policy body in <code>overview</code> above. Story 5: the BigQuery side (caller-delegated authorization, <code>policy_context_commitment</code>) is " + src("rfc", "RFC text only") + "."), "catalog") +
      "</div>" +
      '<details class="nn fixture"><summary>Prior experiment · <code>okf-derived-germany</code> · type <code>okf-concept</code> · no aspects · not shipped OKF-in-KC · labelled prior</summary><div class="nn-b">' +
      '<p class="fixture-note"><b>Prior, kept for history.</b> Created 2026-09-02 for the consume experiment, before the shipped types existed in this project. Its only pin is prose in <code>entrySource.description</code>. It was re-read after the push and is byte-identical; the push did not touch it.</p>' +
      '<div class="grid2">' + pane("", "entries.get --view=ALL", src("prior", "prior · live read"), pre(D.legacy, ["description", "entryType"]), "") +
      pane("", "lookupContext", src("prior", "prior · live read"), yaml(D.legacyLc.context || ""), "") + "</div></div></details>";
  }

  // ---- beat 4: sync (CLI) ------------------------------------------------------------
  function renderSync() {
    var pushLines = D.pushT.split("\n");
    var setupHead = D.setupT.split("\n").filter(function (l) { return /^\$ |^Using existing|^Created|^exit=/.test(l); });
    var ddl = D.ddlOut.split("\n").filter(function (l) { return /Created|affected rows|Current status/.test(l); }).map(function (l) { return l.replace(/^\[?"|\\n"$|"$|^,$/g, "").replace(/\\n$/, ""); });
    var idRows = D.jobs.map(function (j) { return { job_id: j.job_id, user_email: j.user_email, type: j.statement_type, state: j.state }; });
    return beatHead(4, "split", "Sync (CLI)", "Sync is an external CLI you run. Its direction is bundle → BigQuery commit → Catalog stamp. It has not run yet, and this beat does not pretend it has.",
      "Nothing inside Dataplex or BigQuery performs this step. The RFC specifies <code>okf-context sync</code>, a subcommand of the planned <code>toolbox/okf-context</code> package, run by a person in the demo and by a Cloud Run Job or CI step in production. This page shows the algorithm and the IAM contract as text, and shows what <b>was</b> run for this capture, under the identity that ran it.") +
      must("one-sentence answer: an external CLI I run or schedule; bundle to BigQuery first, Catalog stamp second; Catalog → BigQuery import is not v1 · no <code>BQ_COMMITTED</code> or <code>CATALOG_STAMPED</code> is shown because neither happened · identities captured, not asserted") +
      '<div class="honest"><b>Status on 2026-09-03.</b> The syncer is not built (Phase A). The three service accounts, the custom <code>okfCatalogSearch</code> role, the table-level <code>dataEditor</code> grants, the boundary EntryGroup and the seven negative checks were <b>not</b> created for this capture. Everything below marked ' + src("live", "live") + " or " + src("seeded", "seeded") + " was run by the operator <code>" + esc(OPERATOR) + "</code> in the default gcloud configuration. Everything marked " + src("rfc", "RFC text only") + " is quoted from <code>spec.md</code>.</div>" +
      '<div class="grid2">' +
      pane("", "The algorithm · spec.md §1.1", src("rfc", "RFC text only · not run"),
        '<pre class="algo"><span class="cm">okf-context sync --bundle &lt;root&gt; --deployment okf-rfc-demo --entry-group okf-rfc-demo --dataset okf_rfc_demo</span>\n<span class="cm">  runs as</span> <span class="id">okf-sync-writer-okf-rfc-demo</span> <span class="cm">(table-level dataEditor on nine tables, catalogEditor on one EntryGroup)</span>\n  1. <span class="st">validate</span>   bundle parses; zero new OKF keys required\n  2. <span class="st">observe</span>    source_manifest_hash over every regular file → observation_id\n  3. <span class="st">snapshot</span>   compile concepts, versions, edges, membership → snapshot_id\n  4. <span class="st">plan</span>       diff against deployment_heads; adds / changes / removals (absence = delete)\n  5. <span class="st">commit</span>     MERGE publications ON publication_id (seeded row matched, not duplicated)\n                → <span class="cm">would print</span> BQ_COMMITTED → advance deployment_heads, append history,\n                mint context_ref → publication_id (append-only, never rebound)\n  6. <span class="st">stamp</span>      upsert okf-context-runtime {publication_id, published_snapshot_id, managed_by_*}\n                → <span class="cm">would print</span> CATALOG_STAMPED; unowned entries untouched\n  7. <span class="st">status</span>     lag, entry counts, receipt UNVERIFIABLE until an attester runs\n<span class="cm">  second run: no-op (defined on deployment_heads, not on row existence)</span></pre>' +
        caption("Exit non-zero and leave <code>deployment_heads</code> untouched if step 5 fails. If step 6 fails after 5, status reports <code>BQ_COMMITTED, CATALOG_PENDING</code> and a rerun completes the stamp without a new publication. A Catalog → BigQuery import (<code>sync --from-catalog</code>) is future, lossy, and not v1."), "runtime") +
      pane("", "What was actually run for this page", src("live", "live · operator · default configuration"),
        '<pre class="cli">' + esc(setupHead.join("\n")) + "\n\n" + esc(pushLines.join("\n")) + "</pre>" +
        caption("<b>This is <code>kcmd push</code>, the Catalog side only.</b> It is the shipped distribution mechanism, not the syncer. It registered the shipped types, pushed " + D.shipped.length + " <code>okf-bundle</code> entries, and wrote nothing to BigQuery. The adapter line above is the identity check: the SDK on <code>main</code> reproduced <code>" + esc(short(IDENT.publication_id, 19)) + "</code> from the committed 180-row export before anything was pushed."), "catalog") +
      "</div>" +
      '<div class="grid2">' +
      pane("", "Runtime tables · sql/setup_runtime_tables.sql", src("seeded", "seeded · operator, not yet okf-setup"),
        '<pre class="cli">' + esc(ddl.join("\n")) + "</pre>" +
        caption("Eleven tables and the <code>context_ref_resolution</code> view; three <code>publications</code> rows (<code>source = seeded_pre_phase_a</code>), three legacy bindings, two <code>demo_evidence</code> rows. <code>deployment_heads</code>, <code>deployment_heads_history</code> and <code>context_ref_bindings</code> are <b>empty</b>: only the syncer writes them. <code>agent_events</code> received no DML.") + jobs(jobsFor("setup_runtime_tables")), "runtime") +
      pane("", "Identity behind every BigQuery step · INFORMATION_SCHEMA.JOBS_BY_USER", src("live", "live · " + D.jobs.length + " jobs"),
        table([{ key: "job_id", render: function (v) { return "<code>" + esc(v.replace(/_\d{8}T\d{6}Z$/, "")) + "</code>"; } }, { key: "type" }, { key: "user_email", render: function (v) { return "<code>" + esc(v) + "</code>"; } }], idRows) +
        caption("The tape the RFC asks for shows the active gcloud configuration before every identity switch and the impersonated <code>user_email</code> after each step. Today there is one identity, the operator, and it is on record for every job."), "") +
      "</div>" +
      '<details class="nn"><summary>IAM contract · spec.md §1.3 · three service accounts, resource-specific grants, seven negative checks · RFC text only</summary><div class="nn-b">' +
      '<table class="iam"><thead><tr><th>Principal</th><th>Resource</th><th>Grant</th><th>Status today</th></tr></thead><tbody>' +
      iamRow("operator, this capture (raincoatrun@gmail.com)", "project (Owner) · dataset okf_rfc_demo (OWNER)", "ran every bq, gcloud, curl and sample-script call in the default gcloud configuration; created no service account, granted nothing, revoked nothing", "live", "every job in bq_jobs_identity.json carries this user_email") +
      iamRow("bootstrap operator, Phase A (human Owner)", "project · dataset okf_rfc_demo · each SA", "time-boxed roleAdmin, projectIamAdmin, serviceAccountAdmin, catalogAdmin, aspectTypeOwner, dataset dataOwner; Token Creator per SA; all setup-only roles revoked after the tape", "rfc", "not done; no time-boxing, no SA, no binding yet") +
      iamRow("okf-setup (one-time)", "project · dataset", "catalogEditor + aspectTypeOwner for type/group creation; dataOwner + jobUser for DDL and seeds; then every role revoked (checks 6, 7)", "rfc", "not created; DDL ran as operator") +
      iamRow("okf-sync-writer-okf-rfc-demo", "EntryGroup okf-rfc-demo · EntryType okf-bundle · AspectTypes okf, okf-context-runtime · nine tables", "catalogEditor on the group; entryTypeUser; aspectTypeUser ×2; dataEditor per table (no dataset grant, so agent_events is unreachable); jobUser", "rfc", "not created") +
      iamRow("okf-runtime-reader", "EntryGroup · project · dataset", "catalogViewer on the group; custom okfCatalogSearch = {dataplex.projects.search}; dataViewer; jobUser", "rfc", "not created; reads ran as operator") +
      "</tbody></table>" +
      caption("Positive checks 1–3 and negative checks 1–7 (nine <code>PERMISSION_DENIED</code> calls, including the two post-cleanup checks that prove <code>okf-setup</code> is retired) are the Phase A tape. None appears on this page because none was run.") +
      "</div></details>" +
      '<details class="nn"><summary>Identity chain the syncer would commit · reproduced by the SDK adapter today</summary><div class="nn-b">' +
      pre(IDENT, ["observation_id", "snapshot_id", "publication_id"]) +
      caption("Observation → snapshot → publication, from <code>python3 examples/okf_bqaa_adapter/run.py</code> on SDK <code>main</code> (<code>4f54b5c</code>) over the committed 180-row export. The syncer must reproduce <code>" + esc(short(IDENT.publication_id, 19)) + "</code> before committing anything; the seeded <code>publications</code> row for it would be matched, not duplicated (first-sync contract). " + src("recorded", "recorded · stdlib, no GCP")) +
      "</div></details>";
  }
  function iamRow(p, r, g, kind, note) {
    return "<tr><td><code>" + esc(p) + "</code></td><td>" + esc(r) + "</td><td>" + esc(g) + '</td><td class="st">' + src(kind, kind === "rfc" ? "RFC text only" : "live") + "<br><span style=\"font-size:12px;color:var(--ink-soft)\">" + esc(note) + "</span></td></tr>";
  }

  // ---- beat 5: serve (BigQuery) -----------------------------------------------------
  function renderServe() {
    var F = D.F, r0 = F.retrieve[0], rc = F.receipts[0];
    var hist12 = F.inv[3], q11 = F.inv[10], q12 = F.inv[11];
    var resolRows = D.resol.map(function (r) { return { context_ref: r.context_ref, n: Number(r.n_bindings), bindings: (r.bindings || []).filter(function (b) { return b.publication_id; }).map(function (b) { return short(b.publication_id, 16) + " (" + b.binding_source + ")"; }).join(", ") || "—", head: r.head_publication_id, resolution: r.resolution }; });
    var pubRows = D.pubs.map(function (p) { return { publication_id: p.publication_id, source: p.source, origin: p.origin, seeded_at: p.seeded_at }; });
    return beatHead(5, "runtime", "Serve (BigQuery)", "Pin, history, lifecycle, an honest verdict, and fail-closed. Shown from real queries, including the ones that return nothing yet.",
      "Five <code>SELECT</code>s over the Phase A tables run today. Two of them are empty because no sync has committed a head; the page shows the empty result instead of inventing one. Beside them: the retrieve result and the <code>UNVERIFIABLE</code> receipt the observe agent carried through twelve questions, and its answer.") +
      must("<code>deployment_heads</code> empty and shown empty · junk handle → <code>FAIL_CLOSED</code> · double-bound legacy handle → <code>AMBIGUOUS_LEGACY</code> · <code>FAIL_STALE</code> needs a head and is labelled RFC text only until one exists · receipt <code>UNVERIFIABLE</code>, reason shown · numbers: future executor/attester, RFC text only") +
      '<div class="grid2">' +
      pane("", "deployment_heads · deployment okf-rfc-demo", src("live", "live · sql/serve_probes.sql §1"),
        table([{ key: "deployment_key" }, { key: "publication_id", render: pubCell }, { key: "committed_at" }], D.heads, { empty: "No head exists: <code>okf-context sync</code> has not run. Pin-or-fail-stale has nothing to compare against yet." }) + jobs(jobsFor("serve_stmt1")), "runtime") +
      pane("", "“Which publication was current at T?” · deployment_heads_history as of 2026-06-30", src("live", "live · sql/serve_probes.sql §2"),
        table([{ key: "publication_id", render: pubCell }, { key: "committed_at" }, { key: "sync_id" }], D.hist, { empty: "No history yet. When the syncer commits, this query answers which publication was current for question 4 (“How did Germany compare to the prior quarter?”). It will still hold no revenue values: the numerical comparison is " + src("rfc", "RFC text only") + "." }) +
        caption("Question 4 on record: “" + esc(hist12 ? hist12.question : "") + "” → the tool returned the same six current items and the agent said the comparison is unproven.") + jobs(jobsFor("serve_stmt2")), "runtime") +
      "</div>" +
      pane("", "Pin-or-fail-stale resolution through the one view · three handles", src("live", "live · sql/serve_probes.sql §3"),
        table([{ key: "context_ref", render: refCell }, { key: "n", label: "bindings", cls: "num" }, { key: "bindings", label: "publication (binding_source)", cls: "wrap" }, { key: "head", label: "head_publication_id", render: pubCell }, { key: "resolution", render: resCell }], resolRows) +
        '<ul class="checklist" style="margin-top:10px">' +
        check(D.resol.some(function (r) { return r.context_ref === "okf:env-junk#deadbeef" && r.resolution === "FAIL_CLOSED"; }), "Unbound handle <code>okf:env-junk#deadbeef</code> → <code>FAIL_CLOSED</code>: no binding row, no guess") +
        check(D.resol.some(function (r) { return r.context_ref === REF_OBS && r.resolution === "AMBIGUOUS_LEGACY" && Number(r.n_bindings) === 2; }), "Legacy handle <code>" + esc(REF_OBS) + "</code> is bound to two publications → <code>AMBIGUOUS_LEGACY</code>; it is attributed only when the event also carries the publication (beat 6)") +
        check(D.resol.some(function (r) { return r.context_ref === REF_CON && r.resolution === "NO_HEAD"; }), "Bound handle <code>" + esc(REF_CON) + "</code> → <code>NO_HEAD</code>: bound to one publication, but there is no head to compare it against") +
        info("<code>FAIL_STALE</code> (bound to a non-head publication) and <code>OK</code> (bound to the head) appear only once a head exists. Until then they are " + src("rfc", "RFC text only") + ". Refs minted by <code>sync</code> will be immutable; legacy ones are not.") +
        "</ul>" + jobs(jobsFor("serve_stmt3")), "runtime") +
      '<div class="grid2">' +
      pane("", "The receipt · okf_run_attested_computation", src("live", "live trace · session " + shortId(S_OBS) + " · " + D.receiptsIdentical + " of " + F.receipts.length + " identical") + " " + src("stub", "stubbed attester · no-execution"),
        (rc ? pre(rc.result, ["verdict", "verdict_reason", "receipt_id", "parameter_schema"]) : "") +
        caption("<code>verdict: UNVERIFIABLE</code>, <code>verdict_reason: no-execution; observer-only demo, nothing attested</code>, <code>receipt_id: rcpt-observe-noexec</code>. The declared <code>parameter_schema</code> (<code>region STRING</code>, <code>quarter_start DATE</code>, <code>quarter_end DATE</code>) is the contract an executor would bind. No SQL ran under the demo identity, and nothing on this page calls the result attested. The Phase 4 verdict shape is a labelled, non-normative fixture on the four-beat demo, not here."), "runtime") +
      pane("", "The answer · same invocation", src("live", "live · LLM_RESPONSE"),
        '<div class="quote good">' + esc(F.inv[0] ? F.inv[0].answer : "") + '<span class="cite">' + esc(F.agent) + " · invocation 1 · " + esc(tsLive(F.inv[0] ? F.inv[0].t1 : "")) + " UTC</span></div>" +
        '<details class="nn"><summary>Question 11 · “' + esc(q11 ? q11.question : "") + '”</summary><div class="nn-b"><div class="quote good">' + esc(q11 ? q11.answer : "") + "</div></div></details>" +
        '<details class="nn"><summary>Question 12 · “' + esc(q12 ? q12.question : "") + '”</summary><div class="nn-b"><div class="quote good">' + esc(q12 ? q12.answer : "") + "</div></div></details>", "") +
      "</div>" +
      '<div class="grid2">' +
      pane("", "Lifecycle · the metric that died on 2026-06-20", src("live", "live · " + D.exclusions.total + " retrievals, 2 sessions"),
        (r0 ? pre({ mode: r0.result.okf.mode, items: r0.result.okf.items, excluded: r0.result.okf.excluded }, ["excluded", "reason"]) : "") +
        '<ul class="checklist" style="margin-top:10px">' +
        check(D.exclusions.legacy === D.exclusions.total, "<code>" + esc(LEGACY_METRIC) + "</code> excluded in " + D.exclusions.legacy + " of " + D.exclusions.total + " <code>current</code>-mode retrievals across sessions <code>" + esc(shortId(S_OBS)) + "</code> and <code>" + esc(shortId(S_OBS2)) + "</code>") +
        check(D.exclusions.rank1 === D.exclusions.total, "<code>" + esc(CURRENT_METRIC) + "</code> ranked first in " + D.exclusions.rank1 + " of " + D.exclusions.total) +
        info("Beat 3 showed the same metric still discoverable in Catalog with <code>status: deprecated</code>. The runtime's <code>current</code> mode excludes it at query time; the ledger delete-as-absence is " + src("rfc", "RFC text only") + " until the syncer exists.") +
        "</ul>", "runtime") +
      pane("", "publications · seeded, not committed", src("seeded", "seeded · sql/serve_probes.sql §4"),
        table([{ key: "publication_id", render: pubCell }, { key: "source" }, { key: "origin", cls: "wrap" }], pubRows) +
        caption("Three publications, all <code>seeded_pre_phase_a</code>; <code>committed_at</code>, <code>snapshot_id</code>, <code>observation_id</code> are NULL because no sync committed them. The first real sync would match <code>" + esc(short(PUB.p53b, 19)) + "</code> by id, flip its <code>source</code> to <code>sync</code>, keep <code>seeded_at</code>, and advance the head.") + jobs(jobsFor("serve_stmt4")), "runtime") +
      "</div>";
  }

  // ---- beat 6: attribution --------------------------------------------------------------
  function renderAttribution() {
    var attrRows = D.attr.map(function (r) { return { band: r.band, session_id: r.session_id, agent: r.agent, tool: r.tool, context_ref: r.context_ref, publication_id: r.publication_id, publication_source: r.publication_source, binding_source: r.binding_source, n: Number(r.n) }; });
    var v0Rows = D.v0.map(function (r) { return { session_id: r.session_id, tool: r.tool, context_ref: r.context_ref, publication_id: r.publication_id, verdict: r.verdict, n: Number(r.n) }; });
    var bandCell = function (v) { return '<span class="band ' + esc(v) + '">' + esc(v) + "</span>"; };
    return beatHead(6, "ink", "Attribution", "Which session used which publication: a SQL result, not a slide. 14 attributed, 13 receipt-only, no event twice.",
      "Two tables from the two <code>SELECT</code>s in <code>sql/attribution_two_key.sql</code>. Table (a) matches every <code>TOOL_COMPLETED</code> event on <b>both</b> its event-carried <code>context_ref</code> and its event-carried <code>publication_id</code> against the <code>context_ref_resolution</code> view, then joins <code>publications</code> by id only; the thirteen receipt rows whose event carries no publication are a labelled band, attributed by handle alone, never merged. Table (b) is evidence that is not an event: the adapter tape and the legacy Catalog description.") +
      must("band <code>attributed</code> Σ 14 · band <code>receipt_only</code> Σ 13 · no (session, tool, context_ref, publication) row appears twice despite the double-bound legacy handle · <code>publications</code> joined by id only · non-event evidence kept separate with a source column") +
      pane("", "(a) Event-sourced attribution · two-key match through context_ref_resolution", src("live", "live · attribution_two_key.sql STATEMENT 1"),
        table([{ key: "band", render: bandCell }, { key: "session_id", render: sidCell }, { key: "agent" }, { key: "tool" }, { key: "context_ref", render: refCell }, { key: "publication_id", render: pubCell }, { key: "publication_source" }, { key: "binding_source" }, { key: "n", cls: "num" }], attrRows, { rowClass: function (r) { return "band-" + r.band; } }) +
        '<ul class="checklist" style="margin-top:10px">' +
        check(D.attrSum.attributed === 14, "Band <code>attributed</code> sums to " + D.attrSum.attributed + " (1 lookup + 1 retrieve + 12 retrieves)") +
        check(D.attrSum.receipt_only === 13, "Band <code>receipt_only</code> sums to " + D.attrSum.receipt_only + " <code>okf_run_attested_computation</code> rows with NULL event publication, verdict <code>UNVERIFIABLE</code>") +
        check(!D.attrDup, "No (session, tool, context_ref, publication) row appears twice: the legacy handle <code>" + esc(REF_OBS) + "</code> is bound to two publications in the view, but the event's own <code>publication_id</code> selects exactly one") +
        check(D.attr.filter(function (r) { return r.band === "attributed"; }).every(function (r) { return r.publication_source === "seeded_pre_phase_a" && r.binding_source === "legacy"; }), "Every attributed row resolves through a <code>legacy</code> binding to a <code>seeded_pre_phase_a</code> publication: nothing has been committed by <code>sync</code> yet") +
        "</ul>" + jobs(jobsFor("attr_stmt1")), "") +
      '<div class="grid2">' +
      pane("", "(b) Separately sourced evidence · demo_evidence", src("seeded", "seeded · STATEMENT 2") + " " + src("prior", "prior row labelled") + " " + src("recorded", "recorded row labelled"),
        table([{ key: "source" }, { key: "label", render: evidLabel }, { key: "context_ref", render: refCell }, { key: "publication_id", render: pubCell }, { key: "note", cls: "wrap" }], D.evid.map(function (r) { var o = {}; Object.keys(r).forEach(function (k) { o[k] = r[k]; }); o.label = r.source; return o; })) +
        caption("The adapter tape binds the observe handle to a <b>third</b> publication <code>" + esc(short(PUB.p53b, 19)) + "</code>; the legacy Catalog description names the <b>oldest</b>, <code>" + esc(short(PUB.a25, 19)) + "</code>. Neither is an <code>agent_events</code> row, so neither is in table (a).") + jobs(jobsFor("attr_stmt2")), "") +
      pane("", "v0 · events only · runnable without the Phase A tables", src("live", "live · sql/sessions_by_context_ref.sql"),
        table([{ key: "session_id", render: sidCell }, { key: "tool" }, { key: "context_ref", render: refCell }, { key: "publication_id", render: pubCell }, { key: "verdict", render: function (v) { return v ? resCell(v) : "NULL"; } }, { key: "n", cls: "num" }], v0Rows) +
        caption("Five (session, tool, context_ref, publication) groups. Catalog can display none of them; there is no SQL over Catalog and no join to <code>agent_events</code>.") + jobs(jobsFor("v0_sessions")), "") +
      "</div>" +
      caption("<b>Caption.</b> The legacy handle <code>" + esc(REF_OBS) + "</code> was bound to two publications before Phase A; that is legacy evidence, not the contract. Refs minted by <code>sync</code> are immutable: one <code>context_ref</code> → exactly one <code>publication_id</code>, forever, and a new publication mints a new handle. A visitor can rerun both statements with <code>bq query</code> as any <code>dataViewer</code> on <code>okf_rfc_demo</code>; the DDL lives in the setup-owned file only.");
  }

  // ---- matrix / stories / ids ---------------------------------------------------------------
  function renderMatrix() {
    var el = document.getElementById("matrix-body");
    if (!el) return;
    var rowsHtml = D.matrix.rows.map(function (r) {
      var shown = (r.shown || []).map(function (b) { return '<a href="#beat=' + b + '" data-goto="' + b + '">beat ' + b + "</a>"; }).join("");
      var rfc = r.rfc_text_only ? '<span class="rfc-only" title="' + esc(r.rfc_text_only) + '">RFC text only</span><br><span style="font-family:var(--display);font-size:12px;color:var(--ink-soft)">' + esc(r.rfc_text_only) + "</span>" : "";
      return '<tr><td class="n">' + r.n + '</td><td class="cap">' + esc(r.capability) + '</td><td class="kc">' + esc(r.kc) + '</td><td class="bq">' + esc(r.bq) + "</td><td>" + esc(r.evidence) + '</td><td class="shown">' + shown + (shown && rfc ? "<br>" : "") + rfc + "</td></tr>";
    }).join("");
    el.innerHTML = '<table class="matrix"><thead><tr><th>#</th><th>Capability</th><th>KC-only (shipped)</th><th>BigQuery deployment</th><th>Live evidence</th><th>Shown on</th></tr></thead><tbody>' + rowsHtml + "</tbody></table>";
  }
  function renderStories() {
    var el = document.getElementById("stories-body");
    if (!el) return;
    el.innerHTML = D.stories.stories.map(function (s) {
      return '<article class="story"><div class="sh"><b>' + s.n + " · " + esc(s.title) + '</b><span class="beats">' + s.beats.map(function (b) { return '<a href="#beat=' + b + '" data-goto="' + b + '">beat ' + b + "</a>"; }).join("") + "</span></div>" +
        '<p class="who">' + esc(s.who) + "</p>" +
        "<dl><dt>session</dt><dd><code>" + esc(s.session) + "</code></dd><dt>agent</dt><dd><code>" + esc(s.agent) + "</code></dd><dt>context_ref</dt><dd><code>" + esc(s.context_ref) + "</code></dd><dt>publication</dt><dd><code>" + esc(s.publication_prefix) + "…</code></dd></dl>" +
        '<p class="fm"><b>KC-only failure mode.</b> ' + esc(s.failure) + "</p>" +
        '<p class="fm"><b>What the BigQuery deployment changes.</b> ' + esc(s.changes) + "</p>" +
        '<p class="fm"><b>Status.</b> ' + esc(s.status) + (/RFC text only/.test(s.status) ? " " + src("rfc", "RFC text only") : "") + "</p></article>";
    }).join("");
  }
  function renderIds() {
    var el = document.getElementById("ids-strip");
    if (!el) return;
    el.innerHTML =
      '<section class="identity ids-strip" aria-label="Live captures">' +
      '<div class="idrow live-row"><div class="lbl"><b>Sessions</b>' + esc(TABLE) + '</div><div class="chip deriv"><span class="k">observe · 180 rows</span><span class="v">' + esc(S_OBS) + '</span></div><div class="chip deriv"><span class="k">consume · 14 rows</span><span class="v">' + esc(S_CON) + '</span></div><div class="chip deriv"><span class="k">observe · 15 rows</span><span class="v">' + esc(S_OBS2) + '</span></div><div class="chip deriv"><span class="k">not pulled · ' + (D.fourth ? D.fourth.rows_in_table + " rows · " + D.fourth.tool_completed + " tool calls" : "—") + '</span><span class="v">' + esc(D.fourth ? D.fourth.session_id : "") + '</span></div><span class="status ok">' + (D.F.count + D.C.count + D.G.count) + " rows on this page · " + D.tableRows + " in the table (live count, " + D.summary.length + " sessions)</span></div>" +
      '<div class="idrow live-row"><div class="lbl"><b>Publications</b>three, two kinds of source</div><div class="chip deriv"><span class="k">consume / legacy Catalog</span><span class="v">' + esc(PUB.a25) + '</span></div><div class="chip deriv"><span class="k">in-process pin · observe</span><span class="v">' + esc(PUB.p674) + '</span></div><div class="chip deriv"><span class="k">adapter tape · derived bundle</span><span class="v">' + esc(PUB.p53b) + "</span></div></div>" +
      '<div class="idrow live-row"><div class="lbl"><b>Catalog</b>us-central1 · EntryGroup okf-rfc-demo</div><div class="chip deriv"><span class="k">shipped entries</span><span class="v">' + D.shipped.length + ' okf-bundle · aspect okf (' + D.aspectFields.length + ' fields)</span></div><div class="chip deriv"><span class="k">prior entry</span><span class="v">okf-derived-germany · okf-concept · no aspects · prior</span></div><span class="live-links-inline">' + link(KC_CONSOLE, "Catalog") + link(BQ_CONSOLE, "BigQuery") + "</span></div>" +
      "</section>" +
      '<p class="beat-kicker" style="margin:14px 0 6px">BigQuery jobs behind this page · <code>live/bq_jobs_identity.json</code></p>' +
      table([{ key: "job_id", render: function (v) { return "<code>" + esc(v) + "</code>"; } }, { key: "statement_type" }, { key: "user_email", render: function (v) { return "<code>" + esc(v) + "</code>"; } }, { key: "creation_time" }], D.jobs) +
      caption("Every job ran as <code>" + esc(D.jobUser) + "</code>, the operator. The Phase A identities (<code>okf-setup</code>, <code>okf-sync-writer-okf-rfc-demo</code>, <code>okf-runtime-reader</code>) are a follow-up; the page says so wherever their absence matters. Full capture list: " + fileLink("live/README.md") + ".");
  }

  // ---- stepper ---------------------------------------------------------------------
  function render() {
    if (!D) return;
    var fns = [renderAsk, renderObserve, renderCatalog, renderSync, renderServe, renderAttribution];
    stage.innerHTML = fns[current - 1]();
    stepCount.textContent = current + " / " + TOTAL;
    btnBack.disabled = current === 1;
    btnNext.textContent = current === TOTAL ? "↺ Restart" : "Next →";
    stepButtons.forEach(function (b) { if (Number(b.dataset.beat) === current) b.setAttribute("aria-current", "step"); else b.removeAttribute("aria-current"); });
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

  document.addEventListener("click", function (e) {
    var evBtn = e.target.closest("button[data-ev]");
    if (evBtn) {
      var raw = evBtn.nextElementSibling, open = evBtn.getAttribute("aria-expanded") === "true";
      evBtn.setAttribute("aria-expanded", open ? "false" : "true");
      raw.hidden = open;
      evBtn.parentElement.toggleAttribute("open", !open);
      return;
    }
    var go = e.target.closest("a[data-goto]");
    if (go) { e.preventDefault(); goTo(Number(go.dataset.goto)); }
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
      case "Digit1": case "Digit2": case "Digit3": case "Digit4": case "Digit5": case "Digit6":
        e.preventDefault(); goTo(Number(e.code.slice(-1))); break;
    }
  });
  function hashBeat() { var m = (location.hash || "").match(/^#(?:beat=)?([1-6])$/); return m ? Number(m[1]) : null; }
  window.addEventListener("hashchange", function () { var n = hashBeat(); if (n && n !== current) goTo(n); });
  var initial = hashBeat();
  if (initial) current = initial;
})();
