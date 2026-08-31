/* EvalBench team demo — six acts, one real session.
   Native-path span-G1 story (PRs 464 + 467 + 468).
   All facts are hardcoded fixture data. This page makes no network calls
   beyond Google Fonts and same-origin static files. */
(function () {
  "use strict";

  var ACTS = [
    {
      headline: "The customer asked. The agent went silent.",
      body:
        '<dl class="facts">' +
        "<dt>agent</dt><dd><code>support_agent</code></dd>" +
        "<dt>system prompt</dt><dd>“You are a terse support agent. Use tools when asked about inventory or tickets. Keep answers to one sentence.”</dd>" +
        "<dt>user</dt><dd><code>real-user-0</code></dd>" +
        "<dt>asked</dt><dd>“How many widgets are in stock?”</dd>" +
        "<dt>session_id</dt><dd><code>7e352c34-4c1c-4395-acd5-fb3c8f215346</code></dd>" +
        "<dt>eval_id</dt><dd><code>7e352c34</code></dd>" +
        "<dt>real trace</dt><dd><code>test-project-0728-467323.bqaa_e2e_real.agent_events</code></dd>" +
        "</dl>",
      note: "This is a real ADK session, not a toy. The customer asked a stock question. Then nothing."
    },
    {
      headline: "What the trace shows.",
      body:
        '<ol class="timeline">' +
        "<li>USER_MESSAGE_RECEIVED</li>" +
        "<li>INVOCATION_STARTING</li>" +
        "<li>AGENT_STARTING · <code>b7ad6b7169203331</code></li>" +
        '<li class="broken">…silence.</li>' +
        "</ol>" +
        '<ul class="missing">' +
        "<li>no TOOL_STARTING</li>" +
        "<li>no check_inventory</li>" +
        "<li>no AGENT_COMPLETED</li>" +
        "</ul>" +
        '<div class="sibling"><p>Sibling session <code>ab7535a5</code> answered: “There are 0 widgets in stock.” ' +
        "The agent <em>can</em> do this; this session just never did.</p></div>" +
        '<p class="loud">Last real span: <code>AGENT_STARTING</code> <code>b7ad6b7169203331</code>. The trace died there.</p>',
      note: "These events live in agent_events — the source of truth. The sibling proves the tool works."
    },
    {
      headline: "Read agent_events. Write a BQAA snapshot.",
      body:
        '<span class="codeblock-label">CLI — static sample, not executed</span>' +
        '<div class="codeblock">$ bq-agent-sdk evalbench-native-import \\\n' +
        "    --source-table test-project-0728-467323.bqaa_e2e_real.agent_events \\\n" +
        "    --job-id mvp-e2e-real-traces \\\n" +
        "    --target-dataset bqaa \\\n" +
        "    --session-id 7e352c34-4c1c-4395-acd5-fb3c8f215346 \\\n" +
        "    --location US \\\n" +
        "    --snapshot-at 2026-08-30T08:00:00Z \\\n" +
        "    --import-version v1 \\\n" +
        "    --min-score goal_completion=1.0</div>" +
        '<span class="codeblock-label">Sample output — hardcoded</span>' +
        '<div class="codeblock">{\n' +
        '  <span class="key">"job"</span>: <span class="val">"mvp-e2e-real-traces"</span>,\n' +
        '  <span class="key">"import_version"</span>: <span class="val">"v1"</span>,\n' +
        '  <span class="key">"status"</span>: <span class="val">"imported"</span>,\n' +
        '  <span class="key">"event_row_count"</span>: <span class="val">27</span>,\n' +
        '  <span class="key">"score_row_count"</span>: <span class="val">7</span>,\n' +
        '  <span class="key">"failed_sessions_view"</span>: <span class="val">"analytics-project.bqaa.evalbench_failed_sessions"</span>\n' +
        "}</div>" +
        '<p class="loud">Source is production <code>agent_events</code>. Destination is BQAA-owned snapshot tables. ' +
        "EvalBench configs/results/scores are not read.</p>",
      note: "Sample output. This page does not call BigQuery. Native writer: PR 464."
    },
    {
      headline: "failed_sessions finds the one of 7.",
      body:
        '<p class="loud">1 of 7 sessions failed. Flags: <code>process_failed</code>, <code>missing_completion</code>, <code>score_failed</code>. ' +
        "Failing score: <code>goal_completion 0.0</code>.</p>" +
        '<span class="codeblock-label">Failed row — frozen fixture, array order preserved</span>' +
        '<div class="codeblock">{\n' +
        '  <span class="key">"import_identity"</span>: <span class="val">"evalbench-native-import:mvp-e2e-real-traces:v1:7e352c34"</span>,\n' +
        '  <span class="key">"taxonomy_categories"</span>: [<span class="val">"task/planning"</span>, <span class="val">"finalization"</span>, <span class="val">"tool blockers"</span>],\n' +
        '  <span class="key">"process_failed"</span>: <span class="val">true</span>,\n' +
        '  <span class="key">"missing_completion"</span>: <span class="val">true</span>,\n' +
        '  <span class="key">"score_failed"</span>: <span class="val">true</span>,\n' +
        '  <span class="key">"failing_scores"</span>: { <span class="key">"goal_completion"</span>: <span class="val">0.0</span> },\n' +
        '  <span class="key">"session_count"</span>: <span class="val">7</span>,\n' +
        '  <span class="key">"failed_count"</span>: <span class="val">1</span>\n' +
        "}</div>" +
        '<ul class="plain">' +
        "<li><b>task/planning</b> — never decided to look up stock</li>" +
        "<li><b>tool blockers</b> — never called check_inventory</li>" +
        "<li><b>finalization</b> — never produced an answer</li>" +
        "</ul>" +
        '<p class="loud">This is still the session-level denominator. Span labels localize; they never replace <code>failed_sessions</code> + G1.</p>',
      note: "JSON format, not table — table omits taxonomy_categories. Denominator unchanged."
    },
    {
      headline: "Span-G1 says where it died.",
      body:
        '<p class="loud">The three frozen G1 names localize onto that span — not a new taxonomy. ' +
        "<code>span_id b7ad6b7169203331</code> · <code>target_kind gap_after_span</code>.</p>" +
        '<span class="codeblock-label">Library call — static sample, not executed</span>' +
        '<div class="codeblock">from bigquery_agent_analytics.span_taxonomy import label_native_run\n' +
        "policy = EvalScorePolicy({\"goal_completion\": 1.0})\n" +
        "labels = label_native_run(run, policy=policy)</div>" +
        '<span class="codeblock-label">Three SpanFailureLabel rows — same real span, frozen order</span>' +
        '<div class="codeblock">[\n' +
        '  { <span class="key">"span_id"</span>: <span class="val">"b7ad6b7169203331"</span>, <span class="key">"failure_category"</span>: <span class="val">"task/planning"</span>, <span class="key">"target_kind"</span>: <span class="val">"gap_after_span"</span> },\n' +
        '  { <span class="key">"span_id"</span>: <span class="val">"b7ad6b7169203331"</span>, <span class="key">"failure_category"</span>: <span class="val">"finalization"</span>, <span class="key">"target_kind"</span>: <span class="val">"gap_after_span"</span> },\n' +
        '  { <span class="key">"span_id"</span>: <span class="val">"b7ad6b7169203331"</span>, <span class="key">"failure_category"</span>: <span class="val">"tool blockers"</span>, <span class="key">"target_kind"</span>: <span class="val">"gap_after_span"</span> }\n' +
        "]</div>" +
        "<p>No subsequent <code>TOOL_STARTING</code> / <code>check_inventory</code> / <code>AGENT_COMPLETED</code>. " +
        "No synthetic span ids. No <code>turn_index</code>. Drawn from the native snapshot, not persisted span-label BQ rows.</p>" +
        '<div class="scores">' +
        '<div class="score-tile trap"><b>correctness</b><span>1.0</span></div>' +
        '<div class="score-tile"><b>llm_feedback</b><span>null</span></div>' +
        '<div class="score-tile trap"><b>pass_rate</b><span>1.0</span></div>' +
        '<div class="score-tile"><b>pinned_sessions</b><span>7</span></div>' +
        "</div>" +
        '<p class="loud">A live judge would still miss this — nothing to judge. ' +
        "<code>failed_sessions</code> is the denominator. Span-G1 is the ticket: which span to open.</p>",
      note: "Library localization on the native snapshot (PRs 467 + 468). Correctness 1.0 is a trap when the agent never answered."
    },
    {
      headline: "Punchline.",
      body:
        '<p class="loud">This widget-stock session failed because the agent never answered (goal_completion=0.0). ' +
        "Session-level G1 still names it task/planning, tool blockers, and finalization. " +
        "Span-level G1 localizes all three to AGENT_STARTING span <code>b7ad6b7169203331</code> " +
        "(<code>gap_after_span</code>) — it died before check_inventory was ever called. " +
        "Next debugging action: inspect that span.</p>" +
        '<p class="loud">We did not need EvalBench tables to see this. Native <code>agent_events</code> was enough; span-G1 tells you <em>where</em> in the trace.</p>' +
        "<p>" +
        '<a href="https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/464">PR 464</a> native writer · ' +
        '<a href="https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/467">PR 467</a> span_taxonomy library · ' +
        '<a href="https://github.com/GoogleCloudPlatform/BigQuery-Agent-Analytics-SDK/pull/468">PR 468</a> span-G1 e2e' +
        "</p>" +
        "<p>Facts on this page are hardcoded fixtures. The page does not call BigQuery. The clock has not started.</p>",
      note: "That next action is the debugging start, not a funding rec."
    }
  ];

  var TOTAL = ACTS.length;
  var current = 1;
  var autoplayTimer = null;
  var AUTOPLAY_MS = 8000;

  var stage = document.getElementById("stage");
  var btnBack = document.getElementById("btn-back");
  var btnNext = document.getElementById("btn-next");
  var btnPlay = document.getElementById("btn-play");
  var stepCount = document.getElementById("step-count");
  var dotsWrap = document.getElementById("dots");

  for (var i = 1; i <= TOTAL; i++) {
    var dot = document.createElement("button");
    dot.type = "button";
    dot.dataset.act = String(i);
    dot.setAttribute("aria-label", "Act " + i);
    dot.addEventListener("click", function () {
      goTo(Number(this.dataset.act));
    });
    dotsWrap.appendChild(dot);
  }

  function render() {
    var act = ACTS[current - 1];
    stage.innerHTML =
      '<div class="act-head">' +
      '<span class="act-num">' + current + "</span>" +
      '<span class="act-kicker">Act ' + current + " of " + TOTAL + "</span>" +
      "</div>" +
      '<h2 class="act-headline">' + act.headline + "</h2>" +
      '<div class="act-body">' + act.body + "</div>" +
      '<p class="presenter-note">' + act.note + "</p>";

    stepCount.textContent = current + " / " + TOTAL;
    btnBack.disabled = current === 1;
    btnNext.textContent = current === TOTAL ? "↺ Restart" : "Next →";
    var dots = dotsWrap.querySelectorAll("button");
    for (var j = 0; j < dots.length; j++) {
      if (j + 1 === current) dots[j].setAttribute("aria-current", "step");
      else dots[j].removeAttribute("aria-current");
    }
    if (String(current) !== (location.hash || "").replace(/^#/, "")) {
      history.replaceState(null, "", "#" + current);
    }
  }

  function goTo(n, keepAutoplay) {
    if (n < 1 || n > TOTAL) return;
    current = n;
    if (!keepAutoplay) stopAutoplay();
    render();
  }

  function next(keepAutoplay) {
    if (current < TOTAL) {
      goTo(current + 1, keepAutoplay);
    } else if (!keepAutoplay) {
      goTo(1);
    }
  }

  function prev() { goTo(current - 1); }

  function stopAutoplay() {
    if (autoplayTimer) {
      clearInterval(autoplayTimer);
      autoplayTimer = null;
      btnPlay.textContent = "Play all";
    }
  }

  function toggleAutoplay() {
    if (autoplayTimer) { stopAutoplay(); return; }
    goTo(1, true);
    btnPlay.textContent = "■ Stop";
    autoplayTimer = setInterval(function () {
      if (current >= TOTAL) { stopAutoplay(); return; }
      next(true);
    }, AUTOPLAY_MS);
  }

  btnBack.addEventListener("click", prev);
  btnNext.addEventListener("click", function () { next(); });
  btnPlay.addEventListener("click", toggleAutoplay);

  document.addEventListener("keydown", function (e) {
    var t = e.target;
    if (t && (t.tagName === "INPUT" || t.tagName === "TEXTAREA" || t.tagName === "SELECT" || t.isContentEditable)) {
      return;
    }
    if (t && t.tagName === "VIDEO") return;
    switch (e.code) {
      case "ArrowRight":
      case "KeyN":
        e.preventDefault();
        next();
        break;
      case "Space":
        if (t && (t.tagName === "BUTTON" || t.tagName === "SUMMARY" || t.tagName === "A")) return;
        e.preventDefault();
        next();
        break;
      case "ArrowLeft":
      case "KeyP":
        e.preventDefault();
        prev();
        break;
      case "Home":
        e.preventDefault();
        goTo(1);
        break;
      case "KeyA":
        e.preventDefault();
        toggleAutoplay();
        break;
    }
  });

  window.addEventListener("hashchange", function () {
    var n = Number((location.hash || "").replace(/^#/, ""));
    if (n >= 1 && n <= TOTAL && n !== current) goTo(n);
  });

  var initial = Number((location.hash || "").replace(/^#/, ""));
  if (initial >= 1 && initial <= TOTAL) current = initial;
  render();
})();
