// /rfc/e2e/ walkthrough (VISUAL_PLAN.md KTD1–KTD4). Progressive enhancement over the generated static record: without
// JavaScript, or when visual-evidence.json does not load or does not match this markup, every recorded step stays
// visible in order and nothing is promoted to a verified state. Choosing a step only changes what is shown; it runs,
// replays or simulates nothing. The CLI tape under Evidence keeps its own chapters and never drives the walkthrough.
(function () {
  "use strict";
  var SCHEMA = "rfc-e2e-visual-evidence/1";
  var reduced = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var behavior = reduced ? "auto" : "smooth";

  // ---- Evidence fold and tape: a deep link into Evidence opens the fold before scrolling or seeking.
  var evidence = document.getElementById("evidence");
  var video = document.getElementById("tape-video");
  var chapters = [].slice.call(document.querySelectorAll(".chapters a[data-t]"));

  function revealHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    var el = id && document.getElementById(id);
    if (!el || !evidence || !evidence.contains(el)) return;
    if (!evidence.open) evidence.open = true;
    if (el !== evidence) el.scrollIntoView({ block: "start" });
  }

  function seek(t) {
    if (!video) return;
    var go = function () {
      try { video.currentTime = t; } catch (err) { /* metadata not loaded yet */ }
      var p = video.play();
      if (p && p.catch) p.catch(function () {});
    };
    if (video.readyState >= 1) go();
    else video.addEventListener("loadedmetadata", go, { once: true });
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest ? e.target.closest("a[data-t]") : null;
    if (!a) return;
    e.preventDefault();
    if (evidence && !evidence.open) evidence.open = true;
    if (!a.classList.contains("chap")) {
      var tape = document.getElementById("tape");
      if (tape) tape.scrollIntoView({ behavior: behavior, block: "start" });
      if (history.pushState && location.hash !== "#tape") history.pushState(null, "", "#tape");
    }
    seek(parseFloat(a.getAttribute("data-t")) || 0);
  });

  if (video) {
    video.addEventListener("timeupdate", function () {
      var now = video.currentTime, current = null;
      chapters.forEach(function (a) { if (parseFloat(a.getAttribute("data-t")) <= now + 0.05) current = a; });
      chapters.forEach(function (a) { if (a === current) a.setAttribute("aria-current", "true"); else a.removeAttribute("aria-current"); });
    });
  }
  window.addEventListener("hashchange", revealHash);
  revealHash();

  // ---- Walkthrough
  var root = document.getElementById("walkthrough");
  if (!root) return;
  var stages = [].slice.call(root.querySelectorAll(".vw-stage"));
  var rail = [].slice.call(root.querySelectorAll(".vw-rail a[data-stage]"));
  var diagram = root.querySelector(".vw-diagram");
  var objs = [].slice.call(root.querySelectorAll(".vw-obj"));
  var links = [].slice.call(root.querySelectorAll(".vw-link"));
  var live = root.querySelector(".vw-live");
  var pager = root.querySelector(".vw-pager");
  var prev = pager && pager.querySelector('[data-dir="-1"]');
  var next = pager && pager.querySelector('[data-dir="1"]');
  var data = null, current = -1;

  function unavailable() {
    var note = root.querySelector(".vw-unavailable");
    if (note) note.hidden = false;
    root.setAttribute("data-mode", "static");
  }

  function valid(d) {
    if (!d || d.schema !== SCHEMA || d.markup_sha256 !== root.getAttribute("data-markup-sha256")) return false;
    if (!Array.isArray(d.stages) || d.stages.length !== stages.length || rail.length !== stages.length) return false;
    return d.stages.every(function (s, i) {
      return s && s.id === stages[i].getAttribute("data-stage") && s.id === rail[i].getAttribute("data-stage") &&
        s.editorial && Array.isArray(s.editorial.highlight) && Array.isArray(s.editorial.links);
    });
  }

  function stageFromHash() {
    var id = decodeURIComponent(location.hash.slice(1));
    for (var i = 0; i < stages.length; i++) if (stages[i].id === id) return i;
    return -1;
  }

  function bringIntoView(el) {
    // Scroll only when the selected step's heading is not already on screen below the pinned site bar.
    var h = el.querySelector("h3") || el;
    var hr = h.getBoundingClientRect();
    if (hr.top >= 60 && hr.bottom <= window.innerHeight) return;
    // Single column (phones, zoom): the diagram sits between the rail and the panel, so show both together when they fit.
    var work = root.querySelector(".vw-work"), railBox = root.querySelector(".vw-rail");
    var single = work && railBox && Math.abs(railBox.getBoundingClientRect().left - work.getBoundingClientRect().left) < 2;
    var target = single && hr.bottom - work.getBoundingClientRect().top + 72 <= window.innerHeight ? work : el;
    target.scrollIntoView({ behavior: behavior, block: "start" });
  }

  function select(i, opts) {
    if (i < 0 || i >= stages.length) return;
    current = i;
    var ed = data.stages[i].editorial;
    stages.forEach(function (el, k) { el.classList.toggle("is-sel", k === i); });
    rail.forEach(function (a, k) { if (k === i) a.setAttribute("aria-current", "step"); else a.removeAttribute("aria-current"); });
    objs.forEach(function (o) { o.classList.toggle("is-lit", ed.highlight.indexOf(o.getAttribute("data-obj")) >= 0); });
    links.forEach(function (l) { l.classList.toggle("is-lit", ed.links.indexOf(l.getAttribute("data-link")) >= 0); });
    if (diagram) diagram.classList.toggle("is-stop", !!ed.stop);
    if (prev) prev.disabled = i === 0;
    if (next) next.disabled = i === stages.length - 1;
    if (opts.announce && live) live.textContent = "Step " + (i + 1) + " of " + stages.length + ": " + ed.title;
    if (opts.scroll) bringIntoView(stages[i]);
  }

  function push(i) {
    var h = "#" + stages[i].id;
    if (history.pushState && location.hash !== h) history.pushState(null, "", h);
  }

  function enhance(d) {
    data = d;
    root.classList.add("vw-on");
    root.setAttribute("data-mode", "interactive");
    if (pager) pager.hidden = false;
    rail.forEach(function (a, k) {
      a.addEventListener("click", function (e) {
        e.preventDefault();
        select(k, { announce: k !== current, scroll: true });
        push(k);
      });
    });
    if (prev) prev.addEventListener("click", function () { select(current - 1, { announce: true, scroll: true }); push(current); });
    if (next) next.addEventListener("click", function () { select(current + 1, { announce: true, scroll: true }); push(current); });
    var fromHistory = function () { var k = stageFromHash(); if (k >= 0 && k !== current) select(k, { announce: true, scroll: true }); };
    window.addEventListener("popstate", fromHistory);
    window.addEventListener("hashchange", fromHistory);
    var start = stageFromHash();
    select(start >= 0 ? start : 0, { announce: false, scroll: false });
    if (start >= 0) stages[start].scrollIntoView({ block: "start" });
    else revealHash(); // collapsing the static panels moves anything below them, e.g. a #tape deep link
  }

  if (!window.fetch) { unavailable(); return; }
  fetch(root.getAttribute("data-evidence"), { cache: "no-cache" })
    .then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); return r.json(); })
    .then(function (d) { if (!valid(d)) throw new Error("evidence does not match this page"); enhance(d); })
    .catch(unavailable);
})();
