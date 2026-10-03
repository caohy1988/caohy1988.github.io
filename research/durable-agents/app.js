'use strict';
/* Durable running agents: reading progress, chapter highlighting, copy link, and three explainers.
   Every explainer also works as plain HTML: the markup ships with its default state rendered. */
(function () {
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };

  /* Reading progress and the active chapter in the contents list */
  var bar = $('#progress');
  var links = $$('.contents nav a');
  var sections = $$('article > section[id]');
  function onScroll() {
    var max = document.documentElement.scrollHeight - window.innerHeight;
    if (bar) bar.style.width = (max > 0 ? Math.min(100, Math.max(0, window.scrollY / max * 100)) : 0) + '%';
    var current = sections.length ? sections[0].id : '';
    sections.forEach(function (s) { if (s.getBoundingClientRect().top < 140) current = s.id; });
    links.forEach(function (a) {
      var on = a.hash === '#' + current;
      a.classList.toggle('active', on);
      if (on) a.setAttribute('aria-current', 'location'); else a.removeAttribute('aria-current');
    });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  window.addEventListener('resize', onScroll);
  onScroll();

  /* Copy link */
  var share = $('#share');
  var status = $('#share-status');
  if (share && status) {
    share.addEventListener('click', function () {
      var url = location.origin + location.pathname;
      var done = function (msg) { status.textContent = msg; setTimeout(function () { status.textContent = ''; }, 4000); };
      if (navigator.clipboard && navigator.clipboard.writeText) {
        navigator.clipboard.writeText(url).then(function () { done('Link copied.'); }, function () { done('Could not copy the link.'); });
      } else {
        done('Could not copy the link.');
      }
    });
  }

  /* Explainer 1: crash the run.
     Rules: Pi Durable per its v1.0.0 code (tool.ts, generation.ts, scheduler.ts); step engines per DBOS, Temporal,
     Inngest, and Cloudflare docs (finished steps reuse saved results, an interrupted step is retried); "no durable
     record" assumes the task is started over. The run itself is invented. Every outcome is written as a plain sentence. */
  var sim = $('#crash-sim');
  if (sim) {
    var STEPS = [
      { n: 1, label: 'Model: plan', kind: 'model', name: 'the model request' },
      { n: 2, label: 'Tool: search_issues', kind: 'tool', tool: 'search', name: 'search_issues' },
      { n: 3, label: 'Model: decide', kind: 'model', name: 'the model request' },
      { n: 4, label: 'Tool: deploy', kind: 'tool', tool: 'deploy', name: 'the deploy' },
      { n: 5, label: 'Model: report', kind: 'model', name: 'the model request' }
    ];
    // running: the step in flight when the process died (0 = none); finished: steps already committed.
    var CRASH = {
      c1: { running: 1, finished: 0 },
      c2: { running: 2, finished: 1 },
      c3: { running: 0, finished: 3 },
      c4: { running: 4, finished: 3, reached: false },
      c5: { running: 4, finished: 3, reached: true },
      c6: { running: 5, finished: 4 }
    };
    var INTERRUPTED = '“was interrupted and may have partially run”';
    var rows = $('#sim-rows');
    var headline = $('#sim-headline');
    var summary = $('#sim-summary');
    var decl = $('#sim-decl');
    var note = $('#sim-decl-note');

    var value = function (name) { var el = $('input[name="' + name + '"]:checked', sim); return el ? el.value : ''; };

    var render = function () {
      var mode = value('sim-mode') || 'pi';
      var c = CRASH[value('sim-crash')] || CRASH.c5;
      var safe = { search: $('#sim-search-safe').checked, deploy: $('#sim-deploy-safe').checked };
      if (decl) decl.disabled = mode !== 'pi';
      if (note) note.textContent = mode === 'pi' ? 'Only Pi Durable reads these. Leaving the setting out means unsafe.' : 'Only Pi Durable reads these.';

      var out = [];
      var heldAt = 0; // step number of an unsafe tool the model was told about (Pi only)
      var deploys = 0;
      var deployNote = '';
      var resent = 0;
      var lead = '';

      STEPS.forEach(function (s) {
        var at, after;
        var isRunning = s.n === c.running;
        var isDone = s.n <= c.finished;
        if (isDone) at = 'It had finished.';
        else if (isRunning) at = s.kind === 'model' ? 'It was streaming its answer.' : (s.tool === 'deploy' ? (c.reached ? 'It was running, and CI had already accepted the deploy.' : 'It was running, and CI had not received the deploy yet.') : 'It was running.');
        else at = 'It had not started.';

        if (mode === 'none') {
          if (isDone || isRunning) {
            if (s.kind === 'model') resent += 1;
            after = s.kind === 'model' ? 'Nothing about it was saved, so the model is called again when the task is started over.' : 'Nothing about it was saved, so it runs again when the task is started over.';
            if (s.tool === 'deploy' && (isDone || c.reached)) after = 'Nothing about it was saved, so the restarted task deploys again and CI receives a second deploy.';
          } else {
            after = 'It runs when the task is started over.';
          }
        } else if (isDone) {
          after = mode === 'pi' ? 'Its result is read back from storage, and it is not run again.' : 'The engine reuses its saved result, and it is not run again.';
        } else if (isRunning) {
          if (s.kind === 'model') {
            resent += 1;
            after = mode === 'pi' ? 'The request is sent again. The partial answer stays in the transcript, marked as aborted.' : 'The engine calls the model again from the start. Only finished results were saved.';
            lead = mode === 'pi'
              ? 'Step ' + s.n + ', ' + s.name + ', is sent again because it was cut off; its partial answer stays in the transcript, marked as aborted.'
              : 'Step ' + s.n + ', ' + s.name + ', is retried from the start because the engine retries any step that had not finished.';
          } else if (mode === 'engine' || safe[s.tool]) {
            after = mode === 'pi' ? 'It runs again from the start, because it is declared safe to replay.' : 'The engine retries it from the start.';
            if (s.tool === 'search') after += ' A second read is harmless.';
            else if (c.reached) after += ' CI receives a second deploy unless the call carries an idempotency key that CI honors.';
            else after += ' CI receives the deploy once.';
            lead = mode === 'pi'
              ? 'Step ' + s.n + ', ' + s.name + ', is rerun because it was declared safe to replay.'
              : 'Step ' + s.n + ', ' + s.name + ', is retried from the start because the engine retries any step that had not finished.';
            if (s.tool === 'deploy' && c.reached) lead += ' CI may receive a second deploy.';
          } else {
            heldAt = s.n;
            after = 'It is not run again, because it is not declared safe to replay. The model gets an error result saying the tool ' + INTERRUPTED + '.';
            lead = 'Step ' + s.n + ', ' + s.name + ', is not run again because it was not declared safe to replay. The model is told it ' + INTERRUPTED + '.';
          }
        } else {
          if (heldAt && s.n === heldAt + 1) {
            after = heldAt === 4
              ? 'It runs next. The model decides what to do about the interrupted deploy; checking CI before deploying again would be the careful choice.'
              : 'It runs next. The model decides whether to search again, carry on, or stop.';
          } else if (heldAt && s.n > heldAt + 1) {
            after = 'Whether it runs depends on what the model decides.';
          } else {
            after = 'It runs normally.';
          }
        }
        out.push({ s: s, at: at, after: after });
      });

      if (mode === 'none') lead = 'Nothing was saved, so starting the task over runs every step again from step 1.';
      else if (!c.running) lead = mode === 'pi' ? 'No step was running, so the new process continues with step 4.' : 'No step was running, so the engine continues with step 4.';

      // Deploys that reached CI, for this invented run.
      var reachedOnce = c.reached || c.finished >= 4;
      if (mode === 'none') {
        deploys = reachedOnce ? 2 : 1;
        deployNote = reachedOnce ? 'The restarted task deploys a second time.' : '';
      } else if (c.running === 4) {
        if (mode === 'engine' || safe.deploy) {
          deploys = c.reached ? 2 : 1;
          deployNote = c.reached ? 'Two, unless CI recognizes the repeat.' : '';
        } else {
          deploys = c.reached ? 1 : 0;
          deployNote = c.reached ? 'The model must find out whether it succeeded.' : 'The model decides whether to deploy again.';
        }
      } else if (mode === 'pi' && heldAt === 2) {
        deploys = 0;
        deployNote = 'Whether the run deploys at all now depends on what the model decides.';
      } else {
        deploys = 1;
      }

      if (rows) {
        rows.innerHTML = '';
        out.forEach(function (o) {
          var tr = document.createElement('tr');
          var th = document.createElement('th'); th.scope = 'row'; th.textContent = o.s.n + '. ' + o.s.label;
          var td1 = document.createElement('td'); td1.textContent = o.at;
          var td2 = document.createElement('td'); td2.textContent = o.after;
          tr.appendChild(th); tr.appendChild(td1); tr.appendChild(td2);
          rows.appendChild(tr);
        });
      }
      if (headline) headline.textContent = lead;
      if (summary) {
        var text = 'Deploys that reached CI' + (mode === 'pi' && heldAt === 2 ? ' so far: ' : ': ') + deploys + '.' + (deployNote ? ' ' + deployNote : '') + ' Model requests sent again: ' + resent + '.';
        if (mode === 'none') text += ' This assumes someone starts the task over.';
        summary.textContent = text;
      }
    };
    $$('input', sim).forEach(function (el) { el.addEventListener('change', render); });
    render();
  }

  /* Explainer 2: filter the comparison table by family */
  var explorer = $('#explorer');
  if (explorer) {
    var buttons = $$('.filter button', explorer);
    var trs = $$('tbody tr', explorer);
    var stat = $('#explorer-status');
    var NAMES = { all: 'all', engine: 'engines', library: 'libraries', hosted: 'hosted agents' };
    var apply = function (family) {
      var shown = 0;
      trs.forEach(function (tr) {
        var show = family === 'all' || tr.getAttribute('data-family') === family;
        tr.hidden = !show;
        if (show) shown += 1;
      });
      buttons.forEach(function (b) { b.setAttribute('aria-pressed', String(b.getAttribute('data-family') === family)); });
      if (stat) stat.textContent = family === 'all' ? 'Showing all ' + trs.length + ' systems.' : 'Showing ' + shown + ' of ' + trs.length + ' systems: ' + NAMES[family] + '.';
    };
    buttons.forEach(function (b) { b.addEventListener('click', function () { apply(b.getAttribute('data-family')); }); });
    window.addEventListener('beforeprint', function () { trs.forEach(function (tr) { tr.dataset.wasHidden = tr.hidden ? '1' : ''; tr.hidden = false; }); });
    window.addEventListener('afterprint', function () { trs.forEach(function (tr) { tr.hidden = tr.dataset.wasHidden === '1'; }); });
  }

  /* Explainer 3: input cost of re-sending a growing conversation.
     Request k sends I_k = P0 + k * D tokens. Warm cache: request 1 writes I_1; request k >= 2 reads I_(k-1) and writes D.
     Prices per million tokens from Anthropic's pricing page (read 2 October 2026); 5-minute cache writes.
     The same page gives Claude 4.6 and later models a 1M token context window; past it the figures are extrapolation. */
  var cost = $('#cost');
  if (cost) {
    var PRICES = { sonnet: { input: 2, write: 2.5, read: 0.2 }, opus: { input: 4, write: 5, read: 0.2 } };
    var WINDOW = 1e6;
    var el = {
      model: $('#cost-model'), turns: $('#cost-turns'), start: $('#cost-start'), delta: $('#cost-delta'),
      turnsV: $('#cost-turns-v'), startV: $('#cost-start-v'), deltaV: $('#cost-delta-v'),
      none: $('#cost-nocache'), warm: $('#cost-warm'), cold: $('#cost-cold'), sum: $('#cost-summary'), prices: $('#cost-prices'),
      win: $('#cost-window'), winTurn: $('#cost-window-turn'), winLast: $('#cost-window-last')
    };
    var fmtInt = function (n) { return Math.round(n).toLocaleString('en-US'); };
    var money = function (d) {
      if (d < 0.1) return '$' + d.toFixed(3);
      return '$' + d.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    };
    var update = function () {
      var p = PRICES[el.model.value] || PRICES.sonnet;
      var N = Number(el.turns.value), P0 = Number(el.start.value), D = Number(el.delta.value);
      var total = N * P0 + D * N * (N + 1) / 2;
      var writes = (P0 + D) + (N - 1) * D;
      var reads = (N - 1) * P0 + D * (N - 1) * N / 2;
      var M = 1e6;
      var noCache = total * p.input / M;
      var warm = writes * p.write / M + reads * p.read / M;
      var cold = total * p.write / M;
      var last = P0 + N * D;
      var lastCold = last * p.write / M;
      var lastWarm = N > 1 ? ((P0 + (N - 1) * D) * p.read + D * p.write) / M : lastCold;
      el.turnsV.value = fmtInt(N); el.startV.value = fmtInt(P0); el.deltaV.value = fmtInt(D);
      if (el.prices) el.prices.textContent = 'List prices per million tokens: ' + money(p.input) + ' input, ' + money(p.write) + ' to write the 5-minute cache, ' + money(p.read) + ' to read it.';
      el.none.textContent = money(noCache);
      el.warm.textContent = money(warm);
      el.cold.textContent = money(cold);
      el.sum.textContent = fmtInt(total) + ' input tokens are sent over ' + fmtInt(N) + ' turns. The last turn alone costs ' + money(lastCold) + ' if the cache has expired and ' + money(lastWarm) + ' if it is warm.';
      if (el.win) {
        // Request k holds P0 + k * D tokens; the first one over the window is turn floor((WINDOW - P0) / D) + 1.
        el.win.hidden = last <= WINDOW;
        if (last > WINDOW) {
          el.winTurn.textContent = fmtInt(Math.floor((WINDOW - P0) / D) + 1);
          el.winLast.textContent = fmtInt(last);
        }
      }
    };
    [el.model, el.turns, el.start, el.delta].forEach(function (x) { if (x) x.addEventListener('input', update); });
    if (el.model) el.model.addEventListener('change', update);
    update();
  }

  /* Arriving on a source link: make sure the target is in view below the sticky bar */
  if (/^#s\d+$/.test(location.hash)) {
    var target = document.getElementById(location.hash.slice(1));
    if (target) window.requestAnimationFrame(function () { target.scrollIntoView(); });
  }
})();
