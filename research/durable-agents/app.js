'use strict';
/* Durable running agents: pure rendering and reasoning functions.
   Used twice: by the build (in Node, to pre-render the static and print versions of every explainer) and by the
   browser (to re-render them as the reader changes the controls). Nothing here touches the DOM.
   Every sentence shown comes from the data block, which the build assembles from sourced cells; the only text
   written here is connective wording and the stated placement and filtering rules. */
var Core = (function () {
  'use strict';

  var esc = function (s) {
    return String(s == null ? '' : s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  };
  // Data text is plain; `backticks` mark code.
  var rich = function (s) {
    return esc(s).replace(/`([^`]+)`/g, '<code>$1</code>');
  };
  var cite = function (nums) {
    return (nums || []).map(function (n) { return '<a class="cite" href="#s' + n + '" aria-label="Source ' + n + '">[' + n + ']</a>'; }).join('');
  };
  var byId = function (data, id) {
    for (var i = 0; i < data.systems.length; i++) if (data.systems[i].id === id) return data.systems[i];
    return null;
  };
  var dimById = function (data, id) {
    for (var i = 0; i < data.dims.length; i++) if (data.dims[i].id === id) return data.dims[i];
    return null;
  };
  var famLabel = function (data, fam, which) {
    for (var i = 0; i < data.families.length; i++) if (data.families[i].id === fam) return data.families[i][which || 'one'];
    return fam;
  };
  var joinNames = function (names) {
    if (names.length < 2) return names.join('');
    return names.slice(0, -1).join(', ') + (names.length > 2 ? ',' : '') + ' and ' + names[names.length - 1];
  };
  var NOT_STATED = 'Not stated in the sources we read.';
  // Split a label into lines of at most n characters, at spaces, for SVG text.
  var wrap = function (s, n) {
    var words = String(s).split(' '), lines = [], cur = '';
    words.forEach(function (w) { if (cur && (cur + ' ' + w).length > n) { lines.push(cur); cur = w; } else cur = cur ? cur + ' ' + w : w; });
    if (cur) lines.push(cur);
    return lines;
  };
  var svgLines = function (cls, x, y, lines, lh) {
    return '<text class="' + cls + '" x="' + x + '" y="' + y + '">' + lines.map(function (l, i) { return '<tspan x="' + x + '" dy="' + (i ? lh : 0) + '">' + esc(l) + '</tspan>'; }).join('') + '</text>';
  };

  /* One cell as HTML: the sentence, its sources, and the qualifier; or the not-stated sentence and where we looked. */
  function cellHTML(c) {
    if (!c) return '';
    if (c.ns) return '<span class="ns">' + NOT_STATED + ' Looked for in ' + cite(c.l) + '.</span>';
    var h = rich(c.t) + cite(c.s);
    if (c.q) h += ' <span class="qual">' + rich(c.q) + '</span>';
    return h;
  }
  function cellText(c) {
    if (!c) return '';
    if (c.ns) return NOT_STATED;
    return c.t + (c.q ? ' ' + c.q : '');
  }

  /* ---------------- The comparison table ---------------- */
  function matrixTable(data) {
    var h = [];
    h.push('<table class="matrix-table" id="matrix-table">');
    h.push('<caption class="visually-hidden">' + data.systems.length + ' durable agent systems compared on ' + data.dims.length + ' questions</caption>');
    h.push('<thead><tr><th scope="col" class="m-sys" aria-sort="none">System</th>');
    data.dims.forEach(function (d) {
      h.push('<th scope="col" class="m-dim" data-dim="' + d.id + '"' + (d.def ? '' : ' data-off="1"') + '>' + esc(d.label) + '</th>');
    });
    h.push('</tr></thead><tbody>');
    data.systems.forEach(function (s, i) {
      h.push('<tr data-sys="' + s.id + '" data-family="' + s.family + '" data-order="' + i + '" data-stated="' + statedCount(s) + '">');
      h.push('<th scope="row" class="m-sys"><a class="m-open" href="#sys-' + s.id + '" data-sys="' + s.id + '">' + esc(s.name) + '</a><span class="m-fam">' + esc(famLabel(data, s.family)) + '</span></th>');
      data.dims.forEach(function (d) {
        h.push('<td class="m-dim" data-dim="' + d.id + '" data-label="' + esc(d.label) + '"' + (d.def ? '' : ' data-off="1"') + '>' + cellHTML(s.cells[d.id]) + '</td>');
      });
      h.push('</tr>');
    });
    h.push('</tbody></table>');
    return h.join('');
  }
  function statedCount(s) {
    var n = 0;
    for (var k in s.cells) if (s.cells[k] && !s.cells[k].ns) n++;
    return n;
  }

  /* ---------------- System notes (also the detail panel) ---------------- */
  function noteBody(data, s, headingLevel) {
    var hl = headingLevel || 4;
    var h = [];
    if (s.about) h.push('<p class="sys-about">' + rich(s.about.t) + cite(s.about.s) + '</p>');
    h.push('<dl class="sys-cells">');
    data.dims.forEach(function (d) {
      h.push('<dt>' + esc(d.label) + '</dt><dd>' + cellHTML(s.cells[d.id]) + '</dd>');
    });
    h.push('</dl>');
    if (s.cav && s.cav.length) {
      h.push('<h' + hl + ' class="sys-sub">Caveats</h' + hl + '><ul class="plain sys-cav">');
      s.cav.forEach(function (c) { h.push('<li>' + rich(c.t) + cite(c.s) + '</li>'); });
      h.push('</ul>');
    }
    if (s.extra && s.extra.length) {
      h.push('<h' + hl + ' class="sys-sub">' + esc(s.extraTitle || 'More from the sources') + '</h' + hl + '><dl class="sys-extra">');
      s.extra.forEach(function (c) { h.push('<dt>' + esc(c.k) + '</dt><dd>' + rich(c.t) + cite(c.s) + '</dd>'); });
      h.push('</dl>');
    }
    var nums = sourcesOf(s);
    h.push('<p class="sys-sources">Sources for this system: ' + cite(nums) + '.</p>');
    return h.join('');
  }
  function sourcesOf(s) {
    var seen = {};
    var add = function (arr) { (arr || []).forEach(function (n) { seen[n] = 1; }); };
    if (s.about) add(s.about.s);
    for (var k in s.cells) { var c = s.cells[k]; if (c) { add(c.s); add(c.l); } }
    (s.cav || []).forEach(function (c) { add(c.s); });
    (s.extra || []).forEach(function (c) { add(c.s); });
    return Object.keys(seen).map(Number).sort(function (a, b) { return a - b; });
  }
  function notes(data) {
    var h = ['<div class="sys-notes">'];
    data.families.forEach(function (f) {
      h.push('<h4 class="sys-fam">' + esc(f.many) + '</h4>');
      data.systems.filter(function (s) { return s.family === f.id; }).forEach(function (s) {
        h.push('<details class="sysnote" id="sys-' + s.id + '"><summary>' + esc(s.name) + '</summary><div class="sysnote-body">' + noteBody(data, s, 5) + '</div></details>');
      });
    });
    h.push('</div>');
    return h.join('');
  }

  /* ---------------- Side by side ---------------- */
  // Two answers differ "in kind" when their kind codes differ; a stated answer and a silent one also differ.
  function compare(data, ids) {
    var sys = ids.map(function (id) { return byId(data, id); }).filter(Boolean);
    var rows = data.dims.map(function (d) {
      var cells = sys.map(function (s) { return s.cells[d.id]; });
      var kinds = cells.map(function (c) { return !c || c.ns ? 'ns' : c.k; });
      var differ = kinds.some(function (k) { return k !== kinds[0]; });
      var allSilent = kinds.every(function (k) { return k === 'ns'; });
      return { dim: d, cells: cells, kinds: kinds, differ: differ, allSilent: allSilent };
    });
    var diff = rows.filter(function (r) { return r.differ; });
    var stated = function (r) { return r.kinds.filter(function (k) { return k !== 'ns'; }).length; };
    // Biggest differences: rows where every chosen system states an answer come first, then by the fixed question order.
    var ranked = diff.slice().sort(function (a, b) { return stated(b) - stated(a) || data.dims.indexOf(a.dim) - data.dims.indexOf(b.dim); });
    var names = sys.map(function (s) { return s.name; });
    var sentence;
    if (sys.length < 2) sentence = 'Choose at least two systems.';
    else if (!diff.length) sentence = joinNames(names) + ' give answers of the same kind on all ' + data.dims.length + ' questions, or are silent on the same ones.';
    else {
      var top = ranked.slice(0, 2).map(function (r) {
        return r.dim.label.toLowerCase() + ' (' + sys.map(function (s, i) { return s.name + ': ' + (r.cells[i] && !r.cells[i].ns ? r.cells[i].sh : 'not stated'); }).join('; ') + ')';
      });
      sentence = joinNames(names) + ' differ in kind on ' + diff.length + ' of ' + data.dims.length + ' questions. The biggest differences are in ' + top.join(', and in ') + '.';
      var silent = rows.filter(function (r) { return r.allSilent; });
      if (silent.length) sentence += ' None of them states an answer on ' + joinNames(silent.map(function (r) { return r.dim.label.toLowerCase(); })) + '.';
    }
    return { systems: sys, rows: rows, differ: diff.length, sentence: sentence };
  }
  function pickerTable(data, ids) {
    var r = compare(data, ids);
    var h = [];
    h.push('<div class="table-wrap"><table class="picker-table"><caption class="visually-hidden">Side-by-side comparison of ' + esc(joinNames(r.systems.map(function (s) { return s.name; }))) + '</caption>');
    h.push('<thead><tr><th scope="col">Question</th>' + r.systems.map(function (s) { return '<th scope="col">' + esc(s.name) + '</th>'; }).join('') + '</tr></thead><tbody>');
    r.rows.forEach(function (row) {
      h.push('<tr' + (row.differ ? ' class="differs"' : '') + '><th scope="row">' + esc(row.dim.label) + (row.differ ? '<span class="differs-note">The answers differ.</span>' : '<span class="differs-note">Same kind of answer.</span>') + '</th>');
      row.cells.forEach(function (c, i) { h.push('<td data-label="' + esc(r.systems[i].name) + '">' + cellHTML(c) + '</td>'); });
      h.push('</tr>');
    });
    h.push('</tbody></table></div>');
    return h.join('');
  }

  /* ---------------- The map ---------------- */
  // Placement rules, applied to the cells: across by where the record lives (the state cell's kind), down by who runs
  // the process that advances the run (the hosting cell's kind). Systems whose cell is silent are listed, not placed.
  var MAP_X = [
    { id: 'yours', label: 'Storage you provide or choose', kinds: ['your-database', 'disk-local', 'in-memory'] },
    { id: 'engine', label: 'The engine’s or platform’s service', kinds: ['engine-service'] },
    { id: 'vendor', label: 'The vendor’s product', kinds: ['vendor'] }
  ];
  var MAP_Y = [
    { id: 'library', label: 'Your process runs it', kinds: ['library'] },
    { id: 'engine', label: 'Your code, coordinated by an engine you run or rent', kinds: ['engine-service'] },
    { id: 'platform', label: 'A platform runs your code', kinds: ['serverless-platform'] },
    { id: 'vendor', label: 'A vendor’s product runs the agent', kinds: ['vendor-product'] }
  ];
  function place(s) {
    var st = s.cells.state, ho = s.cells.hosting;
    var x = null, y = null;
    MAP_X.forEach(function (c) { if (st && !st.ns && c.kinds.indexOf(st.k) >= 0) x = c.id; });
    MAP_Y.forEach(function (c) { if (ho && !ho.ns && c.kinds.indexOf(ho.k) >= 0) y = c.id; });
    return { x: x, y: y };
  }
  function mapModel(data) {
    var cells = {}, unplaced = [];
    data.systems.forEach(function (s) {
      var p = place(s);
      if (!p.x || !p.y) { unplaced.push(s); return; }
      var key = p.y + '|' + p.x;
      (cells[key] = cells[key] || []).push(s);
    });
    return { cells: cells, unplaced: unplaced };
  }
  // Layout: columns are the three record homes; rows the four runners. Narrow screens stack the columns.
  function mapSVG(data, narrow) {
    var m = mapModel(data);
    var lineH = 24, padTop = 30, rowGap = 14;
    var colW = narrow ? 300 : 223, labelW = narrow ? 0 : 140;
    var W = narrow ? 340 : labelW + MAP_X.length * colW + 10;
    var y = narrow ? 8 : 62, out = [], focusables = [];
    var pointsOf = function (list) { return list.map(function (s) { return s; }); };
    if (!narrow) {
      out.push('<text class="map-axis-title" x="' + labelW + '" y="16">Where the durable record lives →</text>');
      MAP_X.forEach(function (c, i) {
        out.push(svgLines('map-col-head', labelW + i * colW + 10, 36, wrap(c.label, 24), 15));
      });
    }
    MAP_Y.forEach(function (r) {
      var maxN = 1;
      MAP_X.forEach(function (c) { maxN = Math.max(maxN, (m.cells[r.id + '|' + c.id] || []).length); });
      if (narrow) {
        // One band per runner; within it, one sub-list per record home that has systems. cur is the next baseline.
        var present = MAP_X.filter(function (c) { return (m.cells[r.id + '|' + c.id] || []).length; });
        var cur = y + 20;
        var rh = wrap(r.label, 40);
        out.push(svgLines('map-row-head', 8, cur, rh, 18));
        cur += 18 * (rh.length - 1) + 26;
        if (!present.length) { out.push('<text class="map-empty" x="16" y="' + cur + '">No system in the table.</text>'); cur += 24; }
        present.forEach(function (c) {
          var ch = wrap('Record: ' + c.label, 44);
          out.push(svgLines('map-col-head', 16, cur, ch, 16));
          cur += 16 * (ch.length - 1) + 26;
          (m.cells[r.id + '|' + c.id] || []).forEach(function (s) {
            focusables.push(s.id);
            out.push(point(s, 24, cur, r, c));
            cur += lineH;
          });
          cur += 6;
        });
        out.push('<line class="map-grid" x1="0" y1="' + (cur - 8) + '" x2="' + W + '" y2="' + (cur - 8) + '"/>');
        y = cur;
      } else {
        var rl = wrap(r.label, 19);
        var h = Math.max(padTop + maxN * lineH, 26 + rl.length * 17);
        out.push('<line class="map-grid" x1="0" y1="' + y + '" x2="' + W + '" y2="' + y + '"/>');
        out.push(svgLines('map-row-label', 0, y + 22, rl, 17));
        MAP_X.forEach(function (c, i) {
          var list = m.cells[r.id + '|' + c.id] || [];
          var x0 = labelW + i * colW + 10, yy = y + 22;
          if (!list.length) out.push('<text class="map-empty" x="' + x0 + '" y="' + (yy + 4) + '">none</text>');
          list.forEach(function (s) { focusables.push(s.id); out.push(point(s, x0 + 8, yy, r, c)); yy += lineH; });
        });
        y += h + rowGap;
      }
    });
    if (!narrow) {
      out.push('<line class="map-grid" x1="0" y1="' + y + '" x2="' + W + '" y2="' + y + '"/>');
      out.push('<text class="map-axis-title" x="0" y="' + (y + 22) + '">↑ Who runs the process that advances the run</text>');
      y += 32;
    }
    var H = y + 6;
    return '<svg class="map-svg' + (narrow ? ' narrow' : '') + '" viewBox="0 0 ' + W + ' ' + H + '" role="group" aria-label="Systems placed by where the durable record lives and who runs the process; ' + data.systems.length + ' systems, ' + m.unplaced.length + ' not placed">' + out.join('') + '</svg>';
  }
  function point(s, x, y, r, c) {
    var fam = s.family;
    var shape = fam === 'engine' ? '<rect class="map-dot fam-engine" x="' + (x - 6) + '" y="' + (y - 11) + '" width="11" height="11"/>'
      : fam === 'framework' ? '<circle class="map-dot fam-framework" cx="' + x + '" cy="' + (y - 5.5) + '" r="6"/>'
        : '<path class="map-dot fam-vendor" d="M' + x + ' ' + (y - 12) + ' L' + (x + 6.5) + ' ' + (y + 1) + ' L' + (x - 6.5) + ' ' + (y + 1) + ' Z"/>';
    return '<g class="map-pt" tabindex="0" role="button" data-sys="' + s.id + '" aria-label="' + esc((s.short && s.short !== s.name ? s.short + ' (' + s.name + ')' : s.name) + '. Record: ' + c.label + '. Runs: ' + r.label + '. Press Enter for the cells that placed it.') + '">' + shape + '<text class="map-name" x="' + (x + 12) + '" y="' + y + '">' + esc(s.short || s.name) + '</text></g>';
  }
  function mapLegend() {
    return '<ul class="map-legend" aria-label="Shapes on the map">' +
      '<li><svg viewBox="0 0 14 14" aria-hidden="true" focusable="false"><rect class="map-dot fam-engine" x="1.5" y="1.5" width="11" height="11"/></svg> a durable-execution engine</li>' +
      '<li><svg viewBox="0 0 14 14" aria-hidden="true" focusable="false"><circle class="map-dot fam-framework" cx="7" cy="7" r="6"/></svg> an agent framework or library</li>' +
      '<li><svg viewBox="0 0 14 14" aria-hidden="true" focusable="false"><path class="map-dot fam-vendor" d="M7 1 L13.5 13 L0.5 13 Z"/></svg> a vendor agent or hosted runtime</li></ul>';
  }
  function mapReadout(data, id) {
    var s = byId(data, id);
    if (!s) return '';
    var p = place(s);
    var xl = '', yl = '';
    MAP_X.forEach(function (c) { if (c.id === p.x) xl = c.label; });
    MAP_Y.forEach(function (c) { if (c.id === p.y) yl = c.label; });
    return '<p><strong>' + esc(s.name) + '.</strong> Placed under <em>' + esc(xl || 'not placed') + '</em> because of its answer on where state is stored: ' + cellHTML(s.cells.state) + ' Placed under <em>' + esc(yl || 'not placed') + '</em> because of its hosting answer: ' + cellHTML(s.cells.hosting) + '</p>';
  }
  function mapTable(data) {
    var m = mapModel(data);
    var h = ['<div class="table-wrap"><table class="map-table"><caption>The map as a table: systems by who runs the process (rows) and where the durable record lives (columns)</caption><thead><tr><th scope="col">Who runs the process</th>'];
    MAP_X.forEach(function (c) { h.push('<th scope="col">' + esc(c.label) + '</th>'); });
    h.push('</tr></thead><tbody>');
    MAP_Y.forEach(function (r) {
      h.push('<tr><th scope="row">' + esc(r.label) + '</th>');
      MAP_X.forEach(function (c) {
        var list = m.cells[r.id + '|' + c.id] || [];
        // data-label names the column when narrow screens stack each row into a card.
        h.push('<td data-label="Record: ' + esc(c.label) + '">' + (list.length ? list.map(function (s) { return '<a href="#sys-' + s.id + '">' + esc(s.name) + '</a>'; }).join(', ') : 'none') + '</td>');
      });
      h.push('</tr>');
    });
    h.push('</tbody></table></div>');
    if (m.unplaced.length) h.push('<p class="caption">Not placed, because a placing cell says the sources are silent: ' + m.unplaced.map(function (s) { return '<a href="#sys-' + s.id + '">' + esc(s.name) + '</a>'; }).join(', ') + '.</p>');
    return h.join('');
  }

  /* ---------------- Crash simulator ---------------- */
  var RUNS = [
    { id: 'deploy-first', label: 'Plan, search, deploy, wait for approval, answer', steps: ['plan', 'search', 'deploy', 'wait', 'answer'] },
    { id: 'approve-first', label: 'Plan, search, wait for approval, deploy, answer', steps: ['plan', 'search', 'wait', 'deploy', 'answer'] },
    { id: 'short', label: 'Plan, deploy, answer', steps: ['plan', 'deploy', 'answer'] }
  ];
  var STEP = {
    plan: { label: 'Plan', kind: 'model', what: 'a model request' },
    search: { label: 'Search the issue tracker', kind: 'read', what: 'a read-only tool call' },
    deploy: { label: 'Deploy', kind: 'write', what: 'a tool call with a side effect' },
    wait: { label: 'Wait for a person’s approval', kind: 'wait', what: 'a wait for a person' },
    answer: { label: 'Write the final answer', kind: 'model', what: 'a model request' }
  };
  function crashPoints(run) {
    var pts = [];
    run.steps.forEach(function (st, i) {
      pts.push({ id: 'during-' + i, label: 'During step ' + (i + 1) + ', ' + STEP[st].label.toLowerCase(), during: i });
      if (i < run.steps.length - 1) pts.push({ id: 'after-' + i, label: 'After step ' + (i + 1) + ' finished, before step ' + (i + 2) + ' began', after: i });
    });
    return pts;
  }
  function runById(id) { for (var i = 0; i < RUNS.length; i++) if (RUNS[i].id === id) return RUNS[i]; return RUNS[0]; }
  var BASELINE = { id: 'none', name: 'No durable record', family: 'baseline' };
  var ND_TEXT = function (what) { return 'Not documented in the sources we read' + (what ? ' for ' + what : '') + '.'; };
  // What a system's sources say about the run as a whole after its process dies (sim.run): it continues on its own,
  // continues only under a stated condition (someone resumes it, or a setting is on), stops (it is not picked up again),
  // or is not documented. Steps after the crash point inherit this; a cut-off step whose outcome is undocumented makes
  // everything after it undocumented too.
  function runOf(s) { return (s.sim && s.sim.run) || { o: 'not-documented' }; }
  // The step that was running when the process died. Returns {state, text, src}.
  function duringOutcome(s, stepKey, opts) {
    var st = STEP[stepKey], sim = s.sim || {};
    var nd = function (what) { return { state: 'unknown', text: ND_TEXT(what), src: [] }; };
    if (st.kind === 'model') {
      var m = sim.model;
      if (!m || m.o === 'not-documented') return nd('a model request that was cut off');
      return { state: m.o === 'conditional' ? 'cond' : 'rerun', text: m.t, src: m.s };
    }
    if (st.kind === 'wait') {
      var w = sim.wait;
      if (!w || w.o === 'not-documented') return nd('a wait that was under way');
      return { state: w.o === 'survives' ? 'waits' : 'waits-cond', text: w.t, src: w.s };
    }
    var t = sim.tool, tx;
    if (!t || t.o === 'not-documented') return nd('a tool call that was cut off');
    if (t.o === 'rerun-if-declared-safe') {
      var safe = stepKey === 'search' ? opts.searchSafe : opts.deploySafe;
      tx = (safe ? 'It is declared safe, so it runs again from the start. ' : 'It is not declared safe, so it does not run again, and the model is told it was interrupted. ') + t.t;
      if (safe && st.kind === 'write') tx += ' The deploy can happen twice unless the receiving service honors an idempotency key.';
      return { state: safe ? 'rerun' : 'told', text: tx, src: t.s };
    }
    if (t.o === 'not-rerun-model-told') return { state: 'told', text: t.t, src: t.s };
    if (t.o === 'conditional') return { state: 'cond', text: t.t, src: t.s };
    if (t.o === 'not-recovered-automatically') return { state: 'lost', text: t.t, src: t.s };
    tx = t.t + (st.kind === 'write' ? ' The deploy can happen twice unless the receiving service honors an idempotency key.' : ' A second read is harmless.');
    return { state: 'rerun', text: tx, src: t.s };
  }
  // One column: every step's outcome, and how the run continues past the crash point (cont), one of:
  // next (it continues on its own), wait-next (a wait that survives ends and the run goes on), next-cond (only under the
  // condition the column states), stopped, unknown-step (the cut-off step is undocumented), unknown-run, or restart.
  function simColumn(s, run, cp, opts) {
    var crashAt = cp.during != null ? cp.during : cp.after + 0.5;
    if (s.id === 'none') {
      return { sys: s, cont: 'restart', told: false, steps: run.steps.map(function (k, i) {
        if (i < crashAt || i === cp.during) return { state: 'rerun', text: 'Nothing was saved, so it runs again when someone starts the task over.', src: [] };
        return { state: 'later', text: 'It runs when the task is started over.', src: [] };
      }) };
    }
    var r = runOf(s), sim = s.sim || {};
    var kind = cp.during != null ? STEP[run.steps[cp.during]].kind : null;
    var cut = cp.during != null ? duringOutcome(s, run.steps[cp.during], opts) : null;
    // A run that is not picked up again leaves the cut-off step as it was, whatever kind of step it was.
    if (cut && r.o === 'stops' && kind !== 'wait' && cut.state === 'unknown') cut = { state: 'lost', text: r.t, src: r.s };
    var cont;
    if (kind === 'wait') cont = cut.state === 'waits' ? 'wait-next' : cut.state === 'waits-cond' ? 'next-cond' : 'unknown-step';
    else if (cut && cut.state === 'unknown') cont = 'unknown-step';
    else if (r.o === 'stops') cont = 'stopped';
    else if (r.o === 'conditional') cont = 'next-cond';
    else if (r.o === 'continues') cont = 'next';
    else cont = 'unknown-run';
    var told = !!(cut && cut.state === 'told');
    var steps = run.steps.map(function (k, i) {
      if (i < crashAt) {
        if (cont === 'stopped') return { state: 'stopped', text: 'It ran before the crash. It does not run again, and its result is not used, because the run is not picked up again.', src: r.s || [] };
        var f = sim.finished;
        if (!f || f.o === 'not-documented') return { state: 'unknown', text: ND_TEXT('steps that had finished'), src: [] };
        if (f.o === 'kept') return { state: 'kept', text: 'It had finished. ' + f.t, src: f.s };
        return { state: 'rerun', text: 'It had finished, but ' + lowerFirst(f.t), src: f.s };
      }
      if (i === cp.during) return cut;
      if (cont === 'next') return told ? { state: 'next', text: 'Whether and how it runs depends on what the model decides about the interrupted call.', src: [] }
        : { state: 'next', text: 'It runs after recovery, as the run continues.', src: [] };
      if (cont === 'wait-next') return { state: 'next', text: 'It runs when the wait ends, as the run continues.', src: [] };
      if (cont === 'next-cond') {
        if (kind === 'wait') return { state: 'next-cond', text: 'It runs when the wait ends, if the wait’s state was stored.', src: [] };
        var nx = r.next || 'It runs only if the run is picked up again, as this column states.';
        return { state: 'next-cond', text: nx + (told ? ' Whether and how it runs then depends on what the model decides about the interrupted call.' : ''), src: r.s || [] };
      }
      if (cont === 'stopped') return { state: 'stopped', text: 'It does not run: the run is not picked up again.', src: r.s || [] };
      if (cont === 'unknown-step') return { state: 'unknown', text: 'Not stated: the sources do not say how the step that was cut off is handled, so whether the run gets this far is not stated either.', src: [] };
      return { state: 'unknown', text: 'Not stated in the sources we read whether the run continues after a crash.', src: [] };
    });
    return { sys: s, steps: steps, cont: cont, told: told };
  }
  function lowerFirst(t) { return t ? t.charAt(0).toLowerCase() + t.slice(1) : t; }
  function simulate(data, ids, runId, cpId, opts) {
    var run = runById(runId);
    var cps = crashPoints(run);
    var cp = cps.filter(function (c) { return c.id === cpId; })[0] || cps[0];
    var sys = ids.map(function (id) { return id === 'none' ? BASELINE : byId(data, id); }).filter(Boolean);
    var cols = sys.map(function (s) { return simColumn(s, run, cp, opts || {}); });
    return { run: run, cp: cp, cols: cols };
  }
  var PHASES = ['Before the crash', 'The crash', 'Steps that had finished', 'The step that was running', 'The rest of the run'];
  // Which steps are visible at each phase of the step-through.
  function phaseOf(idx, cp) {
    var crashAt = cp.during != null ? cp.during : cp.after + 0.5;
    if (idx < crashAt) return 2;
    if (idx === cp.during) return 3;
    return 4;
  }
  function simOutput(data, ids, runId, cpId, opts, phase) {
    var r = simulate(data, ids, runId, cpId, opts);
    var ph = phase == null ? 4 : phase;
    var h = [];
    h.push('<div class="sim-cols" data-cols="' + r.cols.length + '">');
    r.cols.forEach(function (col) {
      h.push('<section class="sim-col" aria-label="' + esc(col.sys.name) + '"><h4>' + esc(col.sys.name) + '</h4>');
      h.push(simTimeline(r, col, ph));
      if (ph >= 1) h.push('<p class="sim-run"><strong>After the crash:</strong> ' + runSentence(col) + '</p>');
      var as = (col.sys.sim && col.sys.sim.assume) || [];
      if (as.length) h.push('<p class="sim-assume"><strong>These outcomes assume:</strong> ' + as.map(function (a) { return rich(a.t) + cite(a.s); }).join(' ') + '</p>');
      h.push('<ol class="sim-steps">');
      r.run.steps.forEach(function (k, i) {
        var o = col.steps[i];
        var shown = ph >= phaseOf(i, r.cp);
        var ranBefore = r.cp.during != null ? i < r.cp.during : i <= r.cp.after;
        var status = ph === 0
          ? (ranBefore ? 'It runs.' : (r.cp.during === i ? 'It starts.' : 'It has not started.'))
          : (ranBefore ? 'It ran before the crash.' : (r.cp.during === i ? 'It was running when the process died.' : 'It had not started.'));
        h.push('<li class="sim-step st-' + (shown ? o.state : 'pending') + '"><span class="sim-step-name">' + (i + 1) + '. ' + esc(STEP[k].label) + '.</span> ');
        if (!shown) h.push('<span class="sim-step-text">' + esc(status) + '</span>');
        else h.push('<span class="sim-step-text">' + rich(o.text) + cite(o.src) + '</span>');
        h.push('</li>');
      });
      h.push('</ol></section>');
    });
    h.push('</div>');
    return h.join('');
  }
  function runSentence(col) {
    if (col.sys.id === 'none') return 'Nothing was saved, so someone starts the task over from the beginning.';
    var r = runOf(col.sys);
    return r.t ? rich(r.t) + cite(r.s) : NOT_STATED;
  }
  function simPhaseSentence(data, ids, runId, cpId, opts, phase) {
    var r = simulate(data, ids, runId, cpId, opts);
    var ph = phase == null ? 4 : phase;
    return PHASES[ph] + '. ' + phaseSentence(r, ph);
  }
  // The last stage names each column's outcome, so a run that stops, or one the sources do not cover, is never
  // summed up as continuing.
  function colSummary(r, col) {
    var name = col.sys.short || col.sys.name;
    var crashAt = r.cp.during != null ? r.cp.during : r.cp.after + 0.5;
    if (col.cont === 'restart') return name + ': the task starts over';
    if (!(r.run.steps.length - 1 > crashAt)) return name + ': no step comes after the one that was cut off';
    switch (col.cont) {
      case 'next': return name + (col.told ? ': the run continues, and the model decides what to do about the interrupted call' : ': the run continues');
      case 'wait-next': return name + ': the run continues when the wait ends';
      case 'next-cond': return name + ': the run continues only under the condition its column states';
      case 'stopped': return name + ': the run stops; it is not picked up again';
      case 'unknown-step': return name + ': not stated, because the sources do not say how the cut-off step is handled';
      default: return name + ': not stated in the sources we read';
    }
  }
  function phaseSentence(r, ph) {
    if (ph === 0) return 'The run proceeds normally until the crash point.';
    if (ph === 1) return (r.cp.during != null ? 'The process dies during step ' + (r.cp.during + 1) + '.' : 'The process dies after step ' + (r.cp.after + 1) + ' finished.') + ' Each column says, from its sources, whether and how the run is picked up again.';
    if (ph === 2) return r.cp.during === 0 ? 'No step had finished yet.' : 'What each system does with the steps that had finished.';
    if (ph === 3) return r.cp.during != null ? 'What each system does with step ' + (r.cp.during + 1) + ', which was running.' : 'No step was running, so nothing is in doubt.';
    return r.cols.map(function (col) { return colSummary(r, col); }).join('; ') + '.';
  }
  // A small timeline per column: one mark per step, shaped by outcome; the legend explains each shape.
  function simTimeline(r, col, ph) {
    var n = r.run.steps.length, W = 300, gap = W / n;
    var parts = ['<svg class="sim-tl" viewBox="0 0 ' + W + ' 44" aria-hidden="true" focusable="false"><line class="sim-tl-rail" x1="' + (gap / 2) + '" y1="18" x2="' + (W - gap / 2) + '" y2="18"/>'];
    r.run.steps.forEach(function (k, i) {
      var x = gap / 2 + i * gap, o = col.steps[i];
      var shown = ph >= phaseOf(i, r.cp);
      parts.push(shapeFor(shown ? o.state : 'pending', x, 18));
      parts.push('<text class="sim-tl-num" x="' + x + '" y="40">' + (i + 1) + '</text>');
    });
    if (ph >= 1) {
      var cx = r.cp.during != null ? gap / 2 + r.cp.during * gap : gap / 2 + (r.cp.after + 0.5) * gap;
      parts.push('<path class="sim-tl-crash" d="M' + (cx - 9) + ' 2 L' + (cx - 3) + ' 10 L' + (cx + 3) + ' 2 L' + (cx + 9) + ' 10"/>');
    }
    parts.push('</svg>');
    return parts.join('');
  }
  function shapeFor(state, x, y) {
    switch (state) {
      case 'kept': return '<rect class="sh-kept" x="' + (x - 7) + '" y="' + (y - 7) + '" width="14" height="14"/>';
      case 'rerun': return '<circle class="sh-rerun" cx="' + x + '" cy="' + y + '" r="7"/>';
      case 'told': return '<path class="sh-told" d="M' + x + ' ' + (y - 8) + ' L' + (x + 8) + ' ' + (y + 6) + ' L' + (x - 8) + ' ' + (y + 6) + ' Z"/>';
      case 'waits': return '<rect class="sh-waits" x="' + (x - 7) + '" y="' + (y - 7) + '" width="14" height="14" rx="7"/>';
      case 'waits-cond': return '<rect class="sh-waits-cond" x="' + (x - 7) + '" y="' + (y - 7) + '" width="14" height="14" rx="7"/>';
      case 'lost': return '<path class="sh-lost" d="M' + (x - 6) + ' ' + (y - 6) + ' L' + (x + 6) + ' ' + (y + 6) + ' M' + (x + 6) + ' ' + (y - 6) + ' L' + (x - 6) + ' ' + (y + 6) + '"/>';
      case 'unknown': return '<circle class="sh-unknown" cx="' + x + '" cy="' + y + '" r="7"/>';
      case 'cond': return '<g class="sh-cond"><circle cx="' + x + '" cy="' + y + '" r="7"/><path d="M' + x + ' ' + (y - 7) + ' A7 7 0 0 1 ' + x + ' ' + (y + 7) + ' Z"/></g>';
      case 'next-cond': return '<circle class="sh-next-cond" cx="' + x + '" cy="' + y + '" r="5"/>';
      case 'stopped': return '<path class="sh-stopped" d="M' + (x - 7) + ' ' + y + ' L' + (x + 7) + ' ' + y + '"/>';
      case 'pending': return '<circle class="sh-pending" cx="' + x + '" cy="' + y + '" r="4"/>';
      default: return '<circle class="sh-next" cx="' + x + '" cy="' + y + '" r="5"/>';
    }
  }
  function simLegend() {
    var item = function (st, words) { return '<li><svg viewBox="0 0 20 20" aria-hidden="true" focusable="false">' + shapeFor(st, 10, 10) + '</svg> ' + words + '</li>'; };
    return '<ul class="sim-legend" aria-label="Shapes in the timelines">' +
      item('kept', 'kept: its saved result is used') + item('rerun', 'runs again') + item('cond', 'runs again only under the condition its sentence states') + item('told', 'not rerun; the model is told') +
      item('waits', 'a wait that resumes') + item('waits-cond', 'a wait that resumes only if its state was stored') + item('lost', 'left as it was; recovery is not automatic') + item('unknown', 'not documented') +
      item('next', 'runs next') + item('next-cond', 'runs next only under the condition its column states') + item('stopped', 'does not run, because the run is not picked up again') + '</ul>';
  }

  /* ---------------- Decision tree ---------------- */
  var QUESTIONS = [
    { id: 'embed', text: 'Do you want to embed a library, run or rent an engine, or have a vendor run the agent?', options: [
      { id: 'library', label: 'A library inside my own application' },
      { id: 'engine', label: 'An engine I run or rent, with my code in its workers or functions' },
      { id: 'vendor', label: 'A product that runs the agent for me' },
      { id: 'any', label: 'Not decided' }] },
    { id: 'where', text: 'Where should the agent run?', options: [
      { id: 'own', label: 'On servers, containers, or machines I operate' },
      { id: 'platform', label: 'On a platform that runs my code for me, such as a serverless or managed service' },
      { id: 'vendor', label: 'Inside a vendor’s product that runs the agent' },
      { id: 'any', label: 'Not decided' }] },
    // Each range has a lower and an upper bound in seconds; null means no upper bound.
    { id: 'length', text: 'How long can one run last, from start to finish, waits included?', options: [
      { id: 'hour', label: 'Up to an hour', min: 0, max: 3600 },
      { id: 'day', label: 'From an hour to a day', min: 3600, max: 86400 },
      { id: 'month', label: 'From a day to 30 days', min: 86400, max: 30 * 86400 },
      { id: 'longer', label: 'More than 30 days', min: 30 * 86400, max: null }] },
    { id: 'effects', text: 'What do the agent’s tools do?', options: [
      { id: 'read', label: 'They only read' },
      { id: 'safe', label: 'They write, but repeating a write is harmless' },
      { id: 'once', label: 'They make changes that must happen once, such as payments, deploys, or messages' }] },
    { id: 'human', text: 'Does a run wait for people?', options: [
      { id: 'no', label: 'No' },
      { id: 'yes', label: 'Yes, for approvals or answers in the middle of a run' }] },
    { id: 'stack', text: 'Do you already run one of these?', options: [
      { id: 'none', label: 'None of these' },
      { id: 'temporal', label: 'Temporal' }, { id: 'aws', label: 'AWS' }, { id: 'azure', label: 'Azure' },
      { id: 'cloudflare', label: 'Cloudflare' }, { id: 'vercel', label: 'Vercel' }, { id: 'langchain', label: 'LangChain or LangGraph' }] }
  ];
  // The rules, stated under the result: the first answer keeps systems whose hosting cell is of that kind; the second
  // keeps systems whose hosting cell describes running there (s.hosts, read from that cell); the run length leaves a
  // system out only when every run-length limit its sources state is fixed and shorter than the range's lower bound
  // (s.limit.caps, read from its limits cell); everything else only adds cells as reasons and cautions. Nothing is
  // scored, and matches keep the order of the comparison table.
  var EMBED = { library: ['library'], engine: ['engine-service', 'serverless-platform'], vendor: ['vendor-product'] };
  var STACK = { temporal: ['temporal'], aws: ['aws'], azure: ['azure'], cloudflare: ['cf-workflows', 'cf-agents'], vercel: ['vercel'], langchain: ['langgraph', 'langsmith'] };
  function rangeOf(ans) {
    var b = null;
    QUESTIONS[2].options.forEach(function (o) { if (o.id === ans.length) b = o; });
    return b;
  }
  // caps: [{sec, fixed, on}], one per plan or deployment; sec null means that plan or deployment states no cap.
  function limitCheck(s, b) {
    var caps = (s.limit && s.limit.caps) || [];
    if (!b || !caps.length) return { out: false, short: false };
    var timed = caps.filter(function (c) { return c.sec != null; });
    var out = timed.length === caps.length && caps.every(function (c) { return c.fixed && c.sec < b.min; });
    var short = !out && timed.some(function (c) { return b.max == null || c.sec < b.max; });
    return { out: out, short: short };
  }
  function recommend(data, ans) {
    var out = { families: [], list: [], excluded: [], notThere: [], otherKind: [], onStack: [], cautions: [] };
    var b = rangeOf(ans);
    var asked = function (q) { return ans[q] && ans[q] !== 'any'; };
    data.systems.forEach(function (s) {
      var ho = s.cells.hosting, hk = ho && !ho.ns ? ho.k : null;
      if (asked('embed') && (!hk || EMBED[ans.embed].indexOf(hk) < 0)) { out.otherKind.push(s); return; }
      var where = asked('where') ? ((s.hosts || {})[ans.where] || '') : 'any';
      if (!where) { out.notThere.push(s); return; }
      var lc = limitCheck(s, b), lim = s.cells.limits;
      if (lc.out) { out.excluded.push(s); return; }
      var why = [], caution = [];
      if (asked('stack') && ans.stack !== 'none' && (STACK[ans.stack] || []).indexOf(s.id) >= 0) { why.push({ h: 'Runs on the platform you already use.' }); out.onStack.push(s); }
      if (asked('embed') || asked('where')) why.push({ c: ho });
      if (where === 'sandbox') caution.push({ h: 'Only its sandbox runs on infrastructure you operate; the vendor runs the agent harness, as its hosting cell says.' });
      if (lim && !lim.ns) (lc.short ? caution : why).push(lc.short ? { pre: 'A stated limit may cut a run in this range short: ', c: lim } : { c: lim });
      else caution.push({ h: 'No run-length limit is stated in the sources we read.', l: lim ? lim.l : [] });
      if (ans.human === 'yes') {
        var w = s.cells.waits;
        if (w && !w.ns) why.push({ c: w }); else caution.push({ h: 'Human waits are not described in the sources we read.', l: w ? w.l : [] });
      }
      if (ans.effects === 'once' || ans.effects === 'safe') {
        var e = s.cells.effects, tr = s.cells.tool_rule;
        if (e && !e.ns) why.push({ c: e }); else caution.push({ h: 'What happens to side effects is not stated in the sources we read.', l: e ? e.l : [] });
        if (ans.effects === 'once') { if (tr && !tr.ns) why.push({ c: tr }); else caution.push({ h: 'What happens to a tool call cut off by a crash is not stated in the sources we read.', l: tr ? tr.l : [] }); }
      }
      out.list.push({ s: s, why: why, caution: caution });
    });
    data.families.forEach(function (f) {
      var list = out.list.filter(function (c) { return c.s.family === f.id; });
      if (list.length) out.families.push({ f: f, list: list });
    });
    if (ans.effects === 'once') out.cautions.push({ t: 'Whatever you choose, give every write an idempotency key that the receiving service honors. In a simulated benchmark, frontier models instructed to act exactly once still duplicated a write in 56% of late-commit episodes.', s: data.refs.limbo ? [data.refs.limbo] : [] });
    if (ans.human === 'yes') out.cautions.push({ t: 'A paused run is only as durable as the place its state is stored.', s: [] });
    return out;
  }
  function reasonHTML(w) {
    if (w.c) return (w.pre ? esc(w.pre) : '') + cellHTML(w.c);
    return esc(w.h) + (w.l && w.l.length ? ' Looked for in ' + cite(w.l) + '.' : '');
  }
  function sysLinks(list) { return list.map(function (s) { return '<a href="#sys-' + s.id + '">' + esc(s.name) + '</a>'; }).join(', '); }
  function treeResult(data, ans) {
    var r = recommend(data, ans);
    var n = r.list.length;
    var h = ['<p class="calculation" id="tree-summary">'];
    if (!n) h.push('No system in the table matches these answers together. The reasons are listed below; try “Not decided” for one of the first two questions.');
    else h.push('These answers leave ' + n + ' of the ' + data.systems.length + ' systems, in ' + r.families.length + ' famil' + (r.families.length === 1 ? 'y' : 'ies') + ', listed in the order of the comparison table, not ranked.' + (r.onStack.length ? ' ' + joinNames(r.onStack.map(function (s) { return s.name; })) + (r.onStack.length === 1 ? ' runs' : ' run') + ' on the platform you already use.' : ''));
    h.push('</p>');
    r.families.forEach(function (fam) {
      h.push('<h5 class="tree-fam">' + esc(fam.f.many) + '</h5><ul class="tree-list">');
      fam.list.forEach(function (c) {
        h.push('<li><p class="tree-name"><a href="#sys-' + c.s.id + '"><strong>' + esc(c.s.name) + '</strong></a></p>');
        if (c.caution.length) h.push('<ul class="plain">' + c.caution.map(function (w) { return '<li class="tree-caution">' + reasonHTML(w) + '</li>'; }).join('') + '</ul>');
        if (c.why.length) h.push('<details class="tree-why"><summary>Why ' + esc(c.s.name) + ' is listed</summary><ul class="plain">' + c.why.map(function (w) { return '<li>' + reasonHTML(w) + '</li>'; }).join('') + '</ul></details>');
        h.push('</li>');
      });
      h.push('</ul>');
    });
    if (r.excluded.length) h.push('<p class="tree-excluded">Left out by the run length, because every run-length limit their sources state is fixed and shorter than the shortest run in the range you chose: ' + r.excluded.map(function (s) { return '<a href="#sys-' + s.id + '">' + esc(s.name) + '</a> (' + cellHTML(s.cells.limits) + ')'; }).join('; ') + '.</p>');
    if (r.notThere.length) h.push('<p class="tree-excluded">Left out by where the agent runs, because their hosting cells do not describe running there: ' + sysLinks(r.notThere) + '.</p>');
    if (r.otherKind.length) h.push('<p class="tree-excluded">Left out by the first answer, because their hosting cells describe a different kind of system: ' + sysLinks(r.otherKind) + '.</p>');
    r.cautions.forEach(function (c) { h.push('<p class="tree-note">' + rich(c.t) + cite(c.s) + '</p>'); });
    h.push('<p class="caption">A reading aid derived from the sourced table, not a ranking and not a recommendation of any vendor. How the list is made: the first answer keeps systems whose hosting cell describes that kind of system. The second keeps systems whose hosting cell describes running where you chose; an option a system’s pages do not mention counts as not described. The run length leaves a system out only when every run-length limit its sources state is fixed and shorter than the shortest run in the range you chose; a limit that falls inside the range, or a default you can change, appears as a caution instead. Step, turn, and event caps appear with the limits cell but do not filter. The other answers add the matching cells as reasons and cautions. Nothing is scored: systems are listed family by family, in the order of the comparison table.</p>');
    return h.join('');
  }
  function treeStatic(data) {
    var h = ['<ol class="tree-static">'];
    QUESTIONS.forEach(function (q) {
      h.push('<li><p><strong>' + esc(q.text) + '</strong></p><p>' + q.options.map(function (o) { return esc(o.label); }).join('; ') + '.</p></li>');
    });
    h.push('</ol>');
    return h.join('');
  }

  /* ---------------- Cost chart ---------------- */
  function costSeries(p, N, P0, D) {
    var M = 1e6, rows = [], none = 0, warm = 0, cold = 0;
    for (var k = 1; k <= N; k++) {
      var I = P0 + k * D;
      none += I * p.input / M;
      cold += I * p.write / M;
      warm += k === 1 ? I * p.write / M : ((P0 + (k - 1) * D) * p.read + D * p.write) / M;
      rows.push([k, none, warm, cold]);
    }
    return rows;
  }
  function costSVG(p, N, P0, D) {
    var rows = costSeries(p, N, P0, D);
    var W = 560, H = 230, L = 64, R = 132, T = 14, B = 34;
    var maxY = rows[rows.length - 1][3] || 1;
    var sx = function (k) { return L + (k - 1) / Math.max(1, N - 1) * (W - L - R); };
    var sy = function (v) { return T + (1 - v / maxY) * (H - T - B); };
    var path = function (col) { return rows.map(function (r, i) { return (i ? 'L' : 'M') + sx(r[0]).toFixed(1) + ' ' + sy(r[col]).toFixed(1); }).join(' '); };
    var money = function (d) { return '$' + (d >= 100 ? Math.round(d).toLocaleString('en-US') : d.toFixed(2)); };
    var ticks = [0, 0.5, 1].map(function (f) { return f * maxY; });
    var h = ['<svg class="cost-svg" viewBox="0 0 ' + W + ' ' + H + '" aria-hidden="true" focusable="false">'];
    ticks.forEach(function (v) { h.push('<line class="cost-grid" x1="' + L + '" y1="' + sy(v) + '" x2="' + (W - R) + '" y2="' + sy(v) + '"/><text class="cost-tick" x="' + (L - 6) + '" y="' + (sy(v) + 4) + '" text-anchor="end">' + money(v) + '</text>'); });
    h.push('<text class="cost-tick" x="' + L + '" y="' + (H - 10) + '">turn 1</text><text class="cost-tick" x="' + (W - R) + '" y="' + (H - 10) + '" text-anchor="end">turn ' + N + '</text>');
    var last = rows[rows.length - 1];
    [[3, 'cost-cold', 'Cache expired'], [1, 'cost-none', 'No caching'], [2, 'cost-warm', 'Cache warm']].forEach(function (c) {
      h.push('<path class="cost-line ' + c[1] + '" d="' + path(c[0]) + '"/>');
    });
    // End labels, nudged apart so they never overlap.
    var labs = [[3, 'Cache expired', 'cost-cold'], [1, 'No caching', 'cost-none'], [2, 'Cache warm', 'cost-warm']].map(function (c) { return { y: sy(last[c[0]]), t: c[1] + ' ' + money(last[c[0]]), cls: c[2] }; });
    labs.sort(function (a, b) { return a.y - b.y; });
    for (var i = 1; i < labs.length; i++) if (labs[i].y - labs[i - 1].y < 16) labs[i].y = labs[i - 1].y + 16;
    labs.forEach(function (l) { h.push('<text class="cost-end ' + l.cls + '" x="' + (W - R + 8) + '" y="' + (l.y + 4) + '">' + esc(l.t) + '</text>'); });
    h.push('</svg>');
    return h.join('');
  }


  /* ---------------- Whole explainer blocks, as shipped in the HTML ---------------- */
  function sysOptions(data, sel, withBaseline) {
    var h = [];
    data.families.forEach(function (f) {
      h.push('<optgroup label="' + esc(f.many) + '">');
      data.systems.filter(function (s) { return s.family === f.id; }).forEach(function (s) {
        h.push('<option value="' + s.id + '"' + (s.id === sel ? ' selected' : '') + '>' + esc(s.name) + '</option>');
      });
      h.push('</optgroup>');
    });
    if (withBaseline) h.push('<optgroup label="A reference case"><option value="none"' + (sel === 'none' ? ' selected' : '') + '>No durable record</option></optgroup>');
    return h.join('');
  }
  function mapBlock(data) {
    var rules = '<p>The placement rules. Across: a system goes under <em>' + MAP_X[0].label + '</em> when its state cell says the record is kept in a database or storage the user provides or configures, on the machine running it, or in memory unless storage is configured; under <em>' + MAP_X[1].label + '</em> when the engine’s or platform’s own service keeps it; and under <em>' + MAP_X[2].label + '</em> when the vendor’s product keeps it. Down: by its hosting cell, as a library inside your process, your code coordinated by an engine you run or rent, your code run by a serverless platform, or an agent run by the vendor. A system whose state or hosting cell is silent is listed under the table instead of placed.</p>';
    return '<div class="map-frame"><div class="map-wrap" id="map-wrap">' + mapSVG(data, false) + '</div><div class="map-tip" id="map-tip" hidden></div></div>' +
      mapLegend() +
      '<div class="map-readout" id="map-readout" aria-live="polite"><p>Select a system on the map, with a click, a tap, or Enter, to see the two cells that placed it. Arrow keys move between systems.</p></div>' +
      '<details class="evidence"><summary>The map as a table, and the placement rules</summary>' + mapTable(data) + rules + '</details>';
  }
  function matrixBlock(data) {
    var h = ['<div class="m-controls needs-js">'];
    h.push('<div class="filter" id="m-family" role="group" aria-label="Show systems by family">');
    [['all', 'All'], ['engine', 'Engines'], ['framework', 'Frameworks and libraries'], ['vendor', 'Vendor agents']].forEach(function (f, i) {
      h.push('<button type="button" data-family="' + f[0] + '" aria-pressed="' + (i === 0) + '">' + f[1] + '</button>');
    });
    h.push('</div>');
    h.push('<div class="m-row"><div class="m-search"><label for="m-q">Search the cells</label><input id="m-q" type="search" autocomplete="off" spellcheck="false"></div>');
    h.push('<div class="m-sort"><label for="m-sort">Sort systems by</label><select id="m-sort"><option value="family">Family, then the order used in the text</option><option value="name">Name, A to Z</option><option value="stated">Most questions answered in the sources</option></select></div></div>');
    h.push('<fieldset class="m-cols" id="m-cols"><legend>Questions to show as columns</legend>');
    data.dims.forEach(function (d) { h.push('<label><input type="checkbox" value="' + d.id + '"' + (d.def ? ' checked' : '') + '> <span>' + esc(d.label) + '</span></label>'); });
    h.push('</fieldset></div>');
    var on = data.dims.filter(function (d) { return d.def; }).length;
    h.push('<p id="m-status" class="calculation needs-js" aria-live="polite">Showing all ' + data.systems.length + ' systems and ' + on + ' of ' + data.dims.length + ' questions.</p>');
    h.push('<div class="table-wrap m-wrap">' + matrixTable(data) + '</div>');
    h.push('<p class="caption">Without scripts, and in print, every system shows all ' + data.dims.length + ' answers. A system’s name opens its detail panel, with its sources and caveats.</p>');
    h.push('<dialog id="sys-dialog" class="sys-dialog" aria-labelledby="sys-dialog-h"><div class="sys-dialog-head"><div><p class="small-label" id="sys-dialog-fam"></p><h4 id="sys-dialog-h">System</h4></div><button type="button" class="sys-dialog-close">Close</button></div><div id="sys-dialog-body" class="sys-dialog-body"></div></dialog>');
    return h.join('');
  }
  function pickerBlock(data, ids) {
    var r = compare(data, ids);
    var h = ['<div class="picker-controls needs-js">'];
    ['First system', 'Second system', 'Third system, optional'].forEach(function (lab, i) {
      h.push('<div><label for="pick-' + (i + 1) + '">' + lab + '</label><select id="pick-' + (i + 1) + '">' + (i === 2 ? '<option value="">None</option>' : '') + sysOptions(data, ids[i] || '', false) + '</select></div>');
    });
    h.push('</div>');
    h.push('<p class="calculation" id="picker-summary" aria-live="polite">' + esc(r.sentence) + '</p>');
    h.push('<div id="picker-table">' + pickerTable(data, ids) + '</div>');
    return h.join('');
  }
  function simBlock(data, d) {
    var run = runById(d.run);
    var h = ['<p>An invented run with up to five steps. Pick the run, the moment the process dies, and up to three systems. Each step’s outcome comes from that system’s cited sources; where the sources are silent, the step says it is not documented. Steps after the crash point follow what the sources say about the run as a whole: if it is not picked up again, continues only under a condition, or is not covered, the later steps say so. Each column also names the setup its outcomes assume. The reference case with no durable record assumes someone starts the task over.</p>'];
    h.push('<div class="sim-controls needs-js">');
    h.push('<fieldset><legend>The run</legend>' + RUNS.map(function (r) { return '<label><input type="radio" name="sim-run" value="' + r.id + '"' + (r.id === run.id ? ' checked' : '') + '> <span>' + esc(r.label) + '</span></label>'; }).join('') + '</fieldset>');
    h.push('<fieldset><legend>When the process dies</legend><div id="sim-cps">' + crashPoints(run).map(function (p) { return '<label><input type="radio" name="sim-cp" value="' + p.id + '"' + (p.id === d.cp ? ' checked' : '') + '> <span>' + esc(p.label) + '</span></label>'; }).join('') + '</div></fieldset>');
    h.push('<fieldset class="sim-sys"><legend>Systems side by side</legend>');
    ['First system', 'Second system', 'Third system, optional'].forEach(function (lab, i) {
      h.push('<div><label for="sim-sys-' + (i + 1) + '">' + lab + '</label><select id="sim-sys-' + (i + 1) + '">' + (i === 2 ? '<option value="">None</option>' : '') + sysOptions(data, d.ids[i] || '', true) + '</select></div>');
    });
    h.push('</fieldset>');
    h.push('<fieldset id="sim-decl"><legend>Pi Durable’s replay declarations</legend><label><input type="checkbox" id="sim-search-safe"' + (d.searchSafe ? ' checked' : '') + '> <span>search is declared <code>replay: "safe"</code></span></label><label><input type="checkbox" id="sim-deploy-safe"' + (d.deploySafe ? ' checked' : '') + '> <span>deploy is declared <code>replay: "safe"</code></span></label><p class="fieldnote">Only Pi Durable reads these. Leaving the setting out means unsafe.</p></fieldset>');
    h.push('</div>');
    h.push('<div class="sim-stepper needs-js"><button type="button" id="sim-start">Walk through from the start</button><button type="button" id="sim-prev">Previous stage</button><button type="button" id="sim-next">Next stage</button><span id="sim-step-of" class="sim-step-of">Stage ' + PHASES.length + ' of ' + PHASES.length + ': ' + PHASES[PHASES.length - 1] + '.</span></div>');
    h.push('<p id="sim-phase" class="sim-headline" aria-live="polite">' + esc(simPhaseSentence(data, d.ids, d.run, d.cp, d, 4)) + '</p>');
    h.push('<div id="sim-out">' + simOutput(data, d.ids, d.run, d.cp, d, 4) + '</div>');
    h.push(simLegend());
    h.push('<p class="caption">An illustration, not a test: we did not run any of these systems. Shapes in each timeline follow the legend above; every outcome is also written as a sentence. Change the setup a column assumes and its outcomes can change.</p>');
    return h.join('');
  }
  function treeBlock(data) {
    var q = QUESTIONS[0];
    var h = ['<p>Answer six questions about your agent. The result lists every system that fits your answers, in the order of the comparison table, with the cautions its cells raise and the cells that made it fit, each with its source. It is a reading aid, not a ranking and not a recommendation of any vendor.</p>'];
    h.push('<div class="tree-flow needs-js" id="tree-flow"><p class="tree-progress" id="tree-progress">Question 1 of ' + QUESTIONS.length + '.</p>');
    h.push('<fieldset class="tree-q"><legend id="tree-q-legend">' + esc(q.text) + '</legend><div id="tree-q-opts">' + q.options.map(function (o, i) { return '<label><input type="radio" name="tree-a" value="' + o.id + '"' + (i === 0 ? ' checked' : '') + '> <span>' + esc(o.label) + '</span></label>'; }).join('') + '</div></fieldset>');
    h.push('<div class="tree-nav"><button type="button" id="tree-back" disabled>Back</button><button type="button" id="tree-next">Next question</button><button type="button" id="tree-restart">Start again</button></div></div>');
    h.push('<p id="tree-status" class="visually-hidden" aria-live="polite"></p>');
    h.push('<h4 id="tree-result-h" class="tree-result-h" tabindex="-1" hidden>Systems that fit your answers</h4>');
    h.push('<div id="tree-result"><p>The six questions, and the answers each one offers:</p>' + treeStatic(data) + '</div>');
    return h.join('');
  }
  return {
    esc: esc, rich: rich, cite: cite, cellHTML: cellHTML, cellText: cellText, byId: byId, dimById: dimById,
    matrixTable: matrixTable, statedCount: statedCount, notes: notes, noteBody: noteBody,
    compare: compare, pickerTable: pickerTable, sysOptions: sysOptions,
    mapBlock: mapBlock, matrixBlock: matrixBlock, pickerBlock: pickerBlock, simBlock: simBlock, treeBlock: treeBlock, simPhaseSentence: simPhaseSentence,
    MAP_X: MAP_X, MAP_Y: MAP_Y, place: place, mapModel: mapModel, mapSVG: mapSVG, mapLegend: mapLegend, mapReadout: mapReadout, mapTable: mapTable,
    RUNS: RUNS, STEP: STEP, crashPoints: crashPoints, simulate: simulate, simOutput: simOutput, simLegend: simLegend, PHASES: PHASES,
    QUESTIONS: QUESTIONS, recommend: recommend, limitCheck: limitCheck, treeResult: treeResult, treeStatic: treeStatic,
    costSeries: costSeries, costSVG: costSVG, NOT_STATED: NOT_STATED
  };
})();
if (typeof module !== 'undefined') module.exports = Core;

/* Durable running agents: page behaviour. Every explainer ships pre-rendered in the HTML (the build runs the same
   Core functions in Node), so the page reads fully without scripts and prints its current state; this file adds the
   controls. Results are announced through polite live regions; all controls are native or follow the ARIA patterns. */
(function () {
  'use strict';
  var $ = function (sel, root) { return (root || document).querySelector(sel); };
  var $$ = function (sel, root) { return Array.prototype.slice.call((root || document).querySelectorAll(sel)); };
  var dataEl = $('#study-data');
  var DATA = dataEl ? JSON.parse(dataEl.textContent) : null;
  var reduceMotion = window.matchMedia && window.matchMedia('(prefers-reduced-motion: reduce)').matches;

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

  /* Reading path: the quick path folds chapters marked data-path="full" down to their summary */
  var chooser = $('#path-chooser');
  var pathStatus = $('#path-status');
  var folds = [];
  if (chooser) {
    chooser.hidden = false;
    $$('section.chapter[data-path="full"]').forEach(function (sec) {
      var body = $('.chapter-body', sec);
      var num = $('.chapter-number', sec);
      if (!body) return;
      var btn = document.createElement('button');
      btn.type = 'button';
      btn.className = 'unfold';
      btn.setAttribute('aria-controls', body.id);
      btn.setAttribute('aria-expanded', 'true');
      btn.textContent = 'Read ' + (num ? num.textContent.toLowerCase() : 'this chapter') + ' in full';
      btn.hidden = true;
      body.parentNode.insertBefore(btn, body);
      btn.addEventListener('click', function () {
        body.hidden = false;
        btn.setAttribute('aria-expanded', 'true');
        btn.hidden = true;
        var first = body.querySelector('h3, p, figure');
        if (first) { first.setAttribute('tabindex', '-1'); first.focus({ preventScroll: false }); }
      });
      folds.push({ body: body, btn: btn });
    });
    var applyPath = function (path) {
      folds.forEach(function (f) {
        var fold = path === 'quick';
        f.body.hidden = fold;
        f.btn.hidden = !fold;
        f.btn.setAttribute('aria-expanded', String(!fold));
      });
      if (pathStatus) pathStatus.textContent = path === 'quick'
        ? 'Quick path: ' + folds.length + ' chapters are folded to their summary. Each has a button to open it.'
        : 'Full path: every chapter is open.';
    };
    $$('input[name="reading-path"]', chooser).forEach(function (r) { r.addEventListener('change', function () { if (r.checked) applyPath(r.value); }); });
  }

  if (!DATA || typeof Core === 'undefined') return;
  var dialog = $('#sys-dialog');

  /* ---------------- The map ---------------- */
  var mapWrap = $('#map-wrap');
  var readout = $('#map-readout');
  var tip = $('#map-tip');
  var narrowNow = null;
  function renderMap() {
    if (!mapWrap) return;
    var narrow = mapWrap.clientWidth < 640;
    if (narrow === narrowNow) return;
    narrowNow = narrow;
    mapWrap.innerHTML = Core.mapSVG(DATA, narrow);
    wireMap();
  }
  function showTip(g) {
    if (!tip) return;
    var id = g.getAttribute('data-sys');
    var s = Core.byId(DATA, id);
    var p = Core.place(s);
    var xl = '', yl = '';
    Core.MAP_X.forEach(function (c) { if (c.id === p.x) xl = c.label; });
    Core.MAP_Y.forEach(function (c) { if (c.id === p.y) yl = c.label; });
    tip.innerHTML = '<strong>' + Core.esc(s.name) + '</strong><br>Record: ' + Core.esc(xl) + '<br>Runs: ' + Core.esc(yl);
    tip.setAttribute('aria-hidden', 'true');
    tip.hidden = false;
    var wr = mapWrap.getBoundingClientRect(), r = g.getBoundingClientRect();
    var left = Math.min(Math.max(0, r.left - wr.left), Math.max(0, wr.width - 240));
    tip.style.left = left + 'px';
    tip.style.top = (r.bottom - wr.top + 6) + 'px';
  }
  function hideTip() { if (tip) tip.hidden = true; }
  function selectPoint(g) {
    $$('.map-pt', mapWrap).forEach(function (x) { x.classList.toggle('selected', x === g); x.setAttribute('aria-pressed', String(x === g)); });
    if (readout) readout.innerHTML = Core.mapReadout(DATA, g.getAttribute('data-sys'));
  }
  function wireMap() {
    var pts = $$('.map-pt', mapWrap);
    pts.forEach(function (g, i) {
      g.setAttribute('aria-pressed', 'false');
      g.setAttribute('tabindex', i === 0 ? '0' : '-1');
      g.addEventListener('focus', function () { showTip(g); pts.forEach(function (x) { x.setAttribute('tabindex', x === g ? '0' : '-1'); }); });
      g.addEventListener('blur', hideTip);
      g.addEventListener('mouseenter', function () { showTip(g); });
      g.addEventListener('mouseleave', function () { if (document.activeElement !== g) hideTip(); });
      g.addEventListener('click', function () { g.focus(); selectPoint(g); });
      g.addEventListener('keydown', function (e) {
        var k = e.key, j = pts.indexOf(g);
        if (k === 'Enter' || k === ' ') { e.preventDefault(); selectPoint(g); }
        else if (k === 'ArrowDown' || k === 'ArrowRight') { e.preventDefault(); pts[(j + 1) % pts.length].focus(); }
        else if (k === 'ArrowUp' || k === 'ArrowLeft') { e.preventDefault(); pts[(j - 1 + pts.length) % pts.length].focus(); }
        else if (k === 'Home') { e.preventDefault(); pts[0].focus(); }
        else if (k === 'End') { e.preventDefault(); pts[pts.length - 1].focus(); }
        else if (k === 'Escape') { hideTip(); }
      });
    });
  }
  if (mapWrap) {
    renderMap();
    var rt;
    window.addEventListener('resize', function () { clearTimeout(rt); rt = setTimeout(renderMap, 120); });
  }

  /* ---------------- The comparison table ---------------- */
  var mt = $('#matrix-table');
  if (mt) {
    var rows = $$('tbody tr', mt);
    var mStatus = $('#m-status');
    var family = 'all';
    var query = '';
    var famButtons = $$('#m-family button');
    var colBoxes = $$('#m-cols input[type="checkbox"]');
    var sortSel = $('#m-sort');
    var search = $('#m-q');
    // Replace each system link with a button that opens the detail panel.
    rows.forEach(function (tr, i) {
      var a = $('.m-open', tr);
      if (!a) return;
      var b = document.createElement('button');
      b.type = 'button';
      b.className = 'm-open';
      b.setAttribute('data-sys', a.getAttribute('data-sys'));
      b.setAttribute('aria-haspopup', 'dialog');
      b.textContent = a.textContent;
      b.tabIndex = i === 0 ? 0 : -1;
      a.parentNode.replaceChild(b, a);
    });
    var openers = function () { return rows.filter(function (tr) { return !tr.hidden; }).map(function (tr) { return $('.m-open', tr); }); };
    var shownDims = function () { return colBoxes.filter(function (c) { return c.checked; }).map(function (c) { return c.value; }); };
    var applyCols = function () {
      var on = shownDims();
      $$('[data-dim]', mt).forEach(function (cell) { cell.hidden = on.indexOf(cell.getAttribute('data-dim')) < 0; });
      mt.classList.toggle('few-cols', on.length <= 2);
    };
    var applyRows = function () {
      var q = query.trim().toLowerCase();
      rows.forEach(function (tr) {
        var famOk = family === 'all' || tr.getAttribute('data-family') === family;
        var textOk = !q || tr.textContent.toLowerCase().indexOf(q) >= 0;
        tr.hidden = !(famOk && textOk);
      });
      var vis = openers();
      // Keep exactly one row button in the tab order.
      rows.forEach(function (tr) { var b = $('.m-open', tr); if (b) b.tabIndex = -1; });
      if (vis.length) vis[0].tabIndex = 0;
    };
    var announce = function () {
      var n = rows.filter(function (tr) { return !tr.hidden; }).length;
      var famName = { all: 'all families', engine: 'durable-execution engines', framework: 'agent frameworks and libraries', vendor: 'vendor agents and hosted runtimes' }[family];
      var msg = 'Showing ' + n + ' of ' + rows.length + ' systems (' + famName + (query.trim() ? ', matching “' + query.trim() + '”' : '') + ') and ' + shownDims().length + ' of ' + colBoxes.length + ' questions.';
      if (!n) msg = 'No system matches. Clear the search or choose another family.';
      if (mStatus) mStatus.textContent = msg;
    };
    var sortRows = function (how) {
      var tb = $('tbody', mt);
      var arr = rows.slice();
      var famOrder = DATA.families.map(function (f) { return f.id; });
      arr.sort(function (a, b) {
        if (how === 'name') return a.querySelector('.m-open').textContent.localeCompare(b.querySelector('.m-open').textContent);
        if (how === 'stated') return (+b.getAttribute('data-stated')) - (+a.getAttribute('data-stated')) || (+a.getAttribute('data-order')) - (+b.getAttribute('data-order'));
        return famOrder.indexOf(a.getAttribute('data-family')) - famOrder.indexOf(b.getAttribute('data-family')) || (+a.getAttribute('data-order')) - (+b.getAttribute('data-order'));
      });
      arr.forEach(function (tr) { tb.appendChild(tr); });
      rows = arr;
      var th = $('thead th.m-sys', mt);
      if (th) th.setAttribute('aria-sort', how === 'name' ? 'ascending' : 'none');
      applyRows();
    };
    famButtons.forEach(function (b) {
      b.addEventListener('click', function () {
        family = b.getAttribute('data-family');
        famButtons.forEach(function (x) { x.setAttribute('aria-pressed', String(x === b)); });
        applyRows(); announce();
      });
    });
    colBoxes.forEach(function (c) { c.addEventListener('change', function () { applyCols(); announce(); }); });
    if (search) {
      var st;
      search.addEventListener('input', function () { clearTimeout(st); st = setTimeout(function () { query = search.value; applyRows(); announce(); }, 150); });
    }
    if (sortSel) sortSel.addEventListener('change', function () { sortRows(sortSel.value); announce(); });
    mt.addEventListener('keydown', function (e) {
      var b = e.target.closest ? e.target.closest('.m-open') : null;
      if (!b) return;
      var list = openers(), j = list.indexOf(b), to = null;
      if (e.key === 'ArrowDown') to = list[Math.min(list.length - 1, j + 1)];
      else if (e.key === 'ArrowUp') to = list[Math.max(0, j - 1)];
      else if (e.key === 'Home') to = list[0];
      else if (e.key === 'End') to = list[list.length - 1];
      if (to) { e.preventDefault(); list.forEach(function (x) { x.tabIndex = x === to ? 0 : -1; }); to.focus(); }
    });
    mt.addEventListener('click', function (e) {
      var b = e.target.closest ? e.target.closest('.m-open') : null;
      if (b) openSystem(b.getAttribute('data-sys'), b);
    });
    applyCols(); applyRows(); announce();
    window.addEventListener('beforeprint', function () { rows.forEach(function (tr) { tr.dataset.wasHidden = tr.hidden ? '1' : ''; tr.hidden = false; }); $$('[data-dim]', mt).forEach(function (c) { c.dataset.wasHidden = c.hidden ? '1' : ''; c.hidden = false; }); });
    window.addEventListener('afterprint', function () { rows.forEach(function (tr) { tr.hidden = tr.dataset.wasHidden === '1'; }); $$('[data-dim]', mt).forEach(function (c) { c.hidden = c.dataset.wasHidden === '1'; }); });
  }

  /* The detail panel: a modal dialog with one system's notes; Escape or Close returns focus to the opener. */
  var lastOpener = null;
  function openSystem(id, opener) {
    var s = Core.byId(DATA, id);
    if (!s || !dialog || typeof dialog.showModal !== 'function') {
      var d = document.getElementById('sys-' + id);
      if (d) { d.open = true; d.scrollIntoView(); }
      return;
    }
    lastOpener = opener || null;
    $('#sys-dialog-h', dialog).textContent = s.name;
    $('#sys-dialog-fam', dialog).textContent = DATA.families.filter(function (f) { return f.id === s.family; })[0].one;
    $('#sys-dialog-body', dialog).innerHTML = Core.noteBody(DATA, s, 5);
    dialog.showModal();
    var close = $('.sys-dialog-close', dialog);
    if (close) close.focus();
  }
  if (dialog) {
    $('.sys-dialog-close', dialog).addEventListener('click', function () { dialog.close(); });
    dialog.addEventListener('close', function () { if (lastOpener) lastOpener.focus(); });
    dialog.addEventListener('click', function (e) { if (e.target === dialog) dialog.close(); });
    // A citation inside the panel closes it first so the sourcebook entry is visible.
    dialog.addEventListener('click', function (e) { var a = e.target.closest ? e.target.closest('a[href^="#s"]') : null; if (a) { lastOpener = null; dialog.close(); } });
  }
  // Deep links to a system's notes open its folded panel.
  function openFromHash() {
    var m = /^#sys-([\w-]+)$/.exec(location.hash);
    if (!m) return;
    var d = document.getElementById('sys-' + m[1]);
    if (d && d.tagName === 'DETAILS') { d.open = true; window.requestAnimationFrame(function () { d.scrollIntoView(); }); }
  }
  window.addEventListener('hashchange', openFromHash);
  openFromHash();

  /* ---------------- Side by side ---------------- */
  var pickSel = [$('#pick-1'), $('#pick-2'), $('#pick-3')];
  var pickSummary = $('#picker-summary');
  var pickTable = $('#picker-table');
  function renderPicker() {
    var ids = pickSel.map(function (s) { return s ? s.value : ''; }).filter(Boolean);
    var uniq = ids.filter(function (id, i) { return ids.indexOf(id) === i; });
    if (uniq.length < ids.length) { pickSummary.textContent = 'Choose different systems in each list.'; return; }
    var r = Core.compare(DATA, uniq);
    pickSummary.textContent = r.sentence;
    pickTable.innerHTML = Core.pickerTable(DATA, uniq);
  }
  if (pickSel[0] && pickSummary && pickTable) pickSel.forEach(function (s) { if (s) s.addEventListener('change', renderPicker); });

  /* ---------------- Crash simulator ---------------- */
  var sim = $('#sim');
  if (sim && $('#sim-out')) {
    var phase = 4;
    var simOut = $('#sim-out');
    var simPhase = $('#sim-phase');
    var cpWrap = $('#sim-cps');
    var val = function (name) { var el = $('input[name="' + name + '"]:checked', sim); return el ? el.value : ''; };
    var simIds = function () { return [$('#sim-sys-1'), $('#sim-sys-2'), $('#sim-sys-3')].map(function (s) { return s ? s.value : ''; }).filter(Boolean).filter(function (id, i, a) { return a.indexOf(id) === i; }); };
    var opts = function () { return { searchSafe: $('#sim-search-safe').checked, deploySafe: $('#sim-deploy-safe').checked }; };
    var renderCps = function () {
      var run = Core.RUNS.filter(function (r) { return r.id === val('sim-run'); })[0] || Core.RUNS[0];
      var cur = val('sim-cp');
      var pts = Core.crashPoints(run);
      if (!pts.some(function (p) { return p.id === cur; })) cur = pts.filter(function (p) { return p.during === 2; })[0] ? 'during-2' : pts[0].id;
      cpWrap.innerHTML = pts.map(function (p) { return '<label><input type="radio" name="sim-cp" value="' + p.id + '"' + (p.id === cur ? ' checked' : '') + '> <span>' + Core.esc(p.label) + '</span></label>'; }).join('');
      $$('input', cpWrap).forEach(function (el) { el.addEventListener('change', function () { phase = 4; renderSim(); }); });
    };
    var renderSim = function () {
      var ids = simIds();
      var decl = $('#sim-decl');
      if (decl) decl.disabled = ids.indexOf('pi') < 0;
      simOut.innerHTML = Core.simOutput(DATA, ids, val('sim-run'), val('sim-cp'), opts(), phase);
      if (simPhase) simPhase.textContent = Core.simPhaseSentence(DATA, ids, val('sim-run'), val('sim-cp'), opts(), phase);
      $('#sim-prev').disabled = phase <= 0;
      $('#sim-next').disabled = phase >= Core.PHASES.length - 1;
      $('#sim-step-of').textContent = 'Stage ' + (phase + 1) + ' of ' + Core.PHASES.length + ': ' + Core.PHASES[phase] + '.';
      if (!reduceMotion) { simOut.classList.remove('flash'); void simOut.offsetWidth; simOut.classList.add('flash'); }
    };
    $$('input[name="sim-run"]', sim).forEach(function (el) { el.addEventListener('change', function () { renderCps(); phase = 4; renderSim(); }); });
    [$('#sim-sys-1'), $('#sim-sys-2'), $('#sim-sys-3'), $('#sim-search-safe'), $('#sim-deploy-safe')].forEach(function (el) { if (el) el.addEventListener('change', renderSim); });
    $('#sim-prev').addEventListener('click', function () { if (phase > 0) { phase -= 1; renderSim(); } });
    $('#sim-next').addEventListener('click', function () { if (phase < Core.PHASES.length - 1) { phase += 1; renderSim(); } });
    $('#sim-start').addEventListener('click', function () { phase = 0; renderSim(); $('#sim-next').focus(); });
    renderCps();
    renderSim();
  }

  /* ---------------- Decision tree ---------------- */
  var flow = $('#tree-flow');
  if (flow) {
    var qi = 0;
    var answers = {};
    var legend = $('#tree-q-legend');
    var opts2 = $('#tree-q-opts');
    var progress = $('#tree-progress');
    var back = $('#tree-back');
    var next = $('#tree-next');
    var restart = $('#tree-restart');
    var result = $('#tree-result');
    var treeStatus = $('#tree-status');
    var drawQ = function () {
      var q = Core.QUESTIONS[qi];
      legend.textContent = q.text;
      progress.textContent = 'Question ' + (qi + 1) + ' of ' + Core.QUESTIONS.length + '.';
      var cur = answers[q.id] || q.options[0].id;
      opts2.innerHTML = q.options.map(function (o) { return '<label><input type="radio" name="tree-a" value="' + o.id + '"' + (o.id === cur ? ' checked' : '') + '> <span>' + Core.esc(o.label) + '</span></label>'; }).join('');
      back.disabled = qi === 0;
      next.textContent = qi === Core.QUESTIONS.length - 1 ? 'Show the systems that fit' : 'Next question';
    };
    var save = function () { var el = $('input[name="tree-a"]:checked', opts2); if (el) answers[Core.QUESTIONS[qi].id] = el.value; };
    next.addEventListener('click', function () {
      save();
      if (qi < Core.QUESTIONS.length - 1) { qi += 1; drawQ(); legend.parentNode.querySelector('input').focus(); return; }
      result.innerHTML = Core.treeResult(DATA, answers);
      var sum = $('#tree-summary', result);
      if (treeStatus && sum) treeStatus.textContent = sum.textContent;
      var head = $('#tree-result-h');
      if (head) { head.hidden = false; head.focus(); }
    });
    back.addEventListener('click', function () { save(); if (qi > 0) { qi -= 1; drawQ(); legend.parentNode.querySelector('input').focus(); } });
    restart.addEventListener('click', function () { answers = {}; qi = 0; drawQ(); legend.parentNode.querySelector('input').focus(); if (treeStatus) treeStatus.textContent = 'Started again at question 1.'; });
    drawQ();
  }

  /* ---------------- Cost calculator ---------------- */
  var cost = $('#cost');
  if (cost) {
    var PRICES = { sonnet: { input: 2, write: 2.5, read: 0.2 }, opus: { input: 4, write: 5, read: 0.2 } };
    var WINDOW = 1e6;
    var el = {
      model: $('#cost-model'), turns: $('#cost-turns'), start: $('#cost-start'), delta: $('#cost-delta'),
      turnsV: $('#cost-turns-v'), startV: $('#cost-start-v'), deltaV: $('#cost-delta-v'),
      none: $('#cost-nocache'), warm: $('#cost-warm'), cold: $('#cost-cold'), sum: $('#cost-summary'), prices: $('#cost-prices'),
      win: $('#cost-window'), winTurn: $('#cost-window-turn'), winLast: $('#cost-window-last'), chart: $('#cost-chart')
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
      if (el.chart) el.chart.innerHTML = Core.costSVG(p, N, P0, D);
    };
    [el.model, el.turns, el.start, el.delta].forEach(function (x) { if (x) x.addEventListener('input', update); });
    if (el.model) el.model.addEventListener('change', update);
    update();
  }

  /* Print: open every folded panel and chapter, then restore afterwards */
  var printState = [];
  window.addEventListener('beforeprint', function () {
    printState = $$('details').map(function (d) { var o = d.open; d.open = true; return [d, o]; });
    folds.forEach(function (f) { f.wasHidden = f.body.hidden; f.body.hidden = false; });
  });
  window.addEventListener('afterprint', function () {
    printState.forEach(function (x) { x[0].open = x[1]; });
    folds.forEach(function (f) { f.body.hidden = !!f.wasHidden; });
  });

  /* Arriving on a source link: make sure the target is in view below the sticky bar */
  if (/^#s\d+$/.test(location.hash)) {
    var target = document.getElementById(location.hash.slice(1));
    if (target) window.requestAnimationFrame(function () { target.scrollIntoView(); });
  }
})();
