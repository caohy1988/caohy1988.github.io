/* Shared renderer for the BigQuery product boards: entries.json -> filters + cards, plus select-and-copy for leadership.
   Contract: research/board-select-copy-spec.md. Requires assets/board-format.js (BoardFormat). */
(function () {
  "use strict";
  var main = document.querySelector("main[data-board][data-entries]");
  if (!main) return;
  var SLUG = main.getAttribute("data-board");
  var ENTRIES_URL = main.getAttribute("data-entries");
  var BOARD_URL = main.getAttribute("data-board-url") || (location.origin + location.pathname);
  var STORAGE_KEY = "board-select:" + SLUG;
  var FILTERS = [
    { id: "all", label: "All" }, { id: "video", label: "Video" }, { id: "medium", label: "Medium" },
    { id: "google-cloud", label: "Google Cloud" }, { id: "community", label: "Community" }
  ];
  var TYPE_LABEL = { video: "Video", medium: "Medium", "google-cloud": "Google Cloud", community: "Community" };
  var esc = window.BoardFormat.escapeHtml;

  function kindLabel(k) { return ({ customer: "Customer", video: "Video", community: "Community", essay: "Essay", docs: "Docs" })[k] || (k || "Resource"); }
  /** Channel for the type filter: Video / Medium / Google Cloud / Community (unchanged from the inline renderer). */
  function channelOf(e) {
    var src = String(e.source || "").toLowerCase(), href = String(e.href || "").toLowerCase();
    if (e.kind === "video" || src.indexOf("youtube") >= 0 || href.indexOf("youtube.com") >= 0 || href.indexOf("youtu.be") >= 0) return "video";
    if (src.indexOf("medium") >= 0 || href.indexOf("medium.com") >= 0) return "medium";
    if (e.kind === "docs" || src.indexOf("google cloud") >= 0 || src.indexOf("google codelabs") >= 0 ||
        href.indexOf("cloud.google.com/") >= 0 || href.indexOf("docs.cloud.google.com/") >= 0 || href.indexOf("codelabs.developers.google.com/") >= 0) return "google-cloud";
    return "community";
  }

  var allEntries = [], byId = {}, activeFilter = "all", boardTitle = "";
  var selected = new Set();
  var storageOk = true;
  var manualMode = false; // both clipboard writes failed: the review textarea is the copy surface
  var els = {};

  function loadSelection() {
    try { var raw = sessionStorage.getItem(STORAGE_KEY); return raw ? JSON.parse(raw) : []; }
    catch (e) { storageOk = false; return []; }
  }
  function saveSelection() {
    if (!storageOk) return;
    try { sessionStorage.setItem(STORAGE_KEY, JSON.stringify(Array.from(selected))); } catch (e) { storageOk = false; }
  }
  function visibleEntries() {
    return window.BoardFormat.sortEntries(activeFilter === "all" ? allEntries : allEntries.filter(function (e) { return channelOf(e) === activeFilter; }));
  }
  function selectedEntries() { return window.BoardFormat.sortEntries(allEntries.filter(function (e) { return selected.has(e.id); })); }
  function setStatus(msg) { els.status.textContent = msg; }

  function counts() {
    var c = { all: allEntries.length, video: 0, medium: 0, "google-cloud": 0, community: 0 };
    allEntries.forEach(function (e) { c[channelOf(e)] += 1; });
    return c;
  }
  function renderFilters() {
    var c = counts();
    els.filters.innerHTML = FILTERS.map(function (f) {
      return '<button type="button" data-filter="' + f.id + '" aria-pressed="' + (activeFilter === f.id ? "true" : "false") + '">' + esc(f.label) + '<span class="count">' + (c[f.id] || 0) + "</span></button>";
    }).join("");
    Array.prototype.forEach.call(els.filters.querySelectorAll("button"), function (btn) {
      btn.addEventListener("click", function () {
        activeFilter = btn.getAttribute("data-filter");
        renderFilters(); renderList();
        if (selected.size) setStatus(countLine());
        try {
          var url = new URL(window.location.href);
          if (activeFilter === "all") url.searchParams.delete("type"); else url.searchParams.set("type", activeFilter);
          history.replaceState(null, "", url);
        } catch (e) { /* ignore */ }
      });
    });
  }
  function renderList() {
    var filtered = visibleEntries(), n = filtered.length, total = allEntries.length;
    var label = (FILTERS.filter(function (f) { return f.id === activeFilter; })[0] || {}).label || "All";
    els.meta.textContent = (activeFilter === "all" ? total + " resource" + (total === 1 ? "" : "s") : n + " of " + total + " · " + label) + " · newest first";
    if (!n) { els.list.innerHTML = '<p class="empty">No resources in this filter.</p>'; updateTray(); return; }
    els.list.innerHTML = filtered.map(function (e) {
      var tags = (e.tags || []).map(function (t) { return '<span class="tag">' + esc(t) + "</span>"; }).join("");
      var ch = channelOf(e), typeLabel = TYPE_LABEL[ch] || kindLabel(e.kind);
      var link = window.BoardFormat.isHttp(e.href);
      var title = link ? '<a href="' + esc(e.href) + '" rel="noopener noreferrer" target="_blank">' + esc(e.title) + "</a>" : esc(e.title);
      var on = selected.has(e.id);
      return '<article class="card" data-id="' + esc(e.id) + '" data-channel="' + esc(ch) + '"' + (on ? ' data-selected="true"' : "") + ">" +
        '<label class="card-select"><input type="checkbox" aria-label="Select: ' + esc(e.title) + '"' + (on ? " checked" : "") + '><span class="box" aria-hidden="true"></span></label>' +
        '<div class="card-body"><div class="src"><span class="kind">' + esc(typeLabel) + "</span><span>" + esc(e.source || "") + "</span><span>" + esc(e.displayDate || e.date || "") + "</span></div>" +
        "<h2>" + title + "</h2><p>" + esc(e.why || "") + "</p>" + (tags ? '<div class="tags">' + tags + "</div>" : "") + "</div></article>";
    }).join("");
    Array.prototype.forEach.call(els.list.querySelectorAll(".card-select input"), function (box) {
      box.addEventListener("change", function () {
        var card = box.closest(".card"), id = card.getAttribute("data-id");
        if (box.checked) selected.add(id); else selected.delete(id);
        card.setAttribute("data-selected", box.checked ? "true" : "false");
        saveSelection(); updateTray();
        setStatus(box.checked ? "Selected. " + countLine() : "Removed. " + countLine());
      });
    });
    updateTray();
  }

  function countLine() {
    var n = selected.size, hidden = selectedEntries().filter(function (e) { return activeFilter !== "all" && channelOf(e) !== activeFilter; }).length;
    return n + " selected" + (hidden ? " · " + hidden + " hidden by filter" : "");
  }
  function reserveTraySpace() {
    var h = els.tray.hidden ? 0 : Math.ceil(els.tray.getBoundingClientRect().height);
    document.documentElement.style.scrollPaddingBottom = h ? h + 8 + "px" : "";
    main.style.paddingBottom = h ? h + 24 + "px" : "";
  }
  /** The rendered focus indicator: the 22px .box for a card checkbox (its input is clipped to 1px), else the element itself,
      plus the focus outline (3px + offset) so the ring stays visible too. */
  function visibleRect(el) {
    var target = el.matches(".card-select input") && el.nextElementSibling ? el.nextElementSibling : el;
    var r = target.getBoundingClientRect(), pad = 6;
    return { top: r.top - pad, bottom: r.bottom + pad };
  }
  function keepAboveTray(el) {
    el = el || document.activeElement;
    if (els.tray.hidden || !el || !els.list.contains(el)) return;
    var r = visibleRect(el), top = els.tray.getBoundingClientRect().top;
    if (r.bottom > top) window.scrollBy(0, r.bottom - top + 4);
    else if (r.top < 0) window.scrollBy(0, r.top - 4);
  }
  function updateTray() {
    var n = selected.size;
    els.tray.hidden = n === 0;
    document.body.classList.toggle("board-tray-open", n > 0);
    reserveTraySpace();
    keepAboveTray(); // the tray may have just appeared or grown under the focused control (Space on a checkbox)
    var hidden = selectedEntries().filter(function (e) { return activeFilter !== "all" && channelOf(e) !== activeFilter; }).length;
    els.count.innerHTML = n + " selected" + (hidden ? ' <span class="hidden-note">· ' + hidden + " hidden by filter</span>" : "");
    els.copyRich.disabled = n === 0; els.copyPlain.disabled = n === 0;
    var vis = visibleEntries(), selVis = vis.filter(function (e) { return selected.has(e.id); }).length;
    els.selectVisible.checked = vis.length > 0 && selVis === vis.length;
    els.selectVisible.indeterminate = selVis > 0 && selVis < vis.length;
    if (!els.review.hidden) renderReview();
  }

  function payload() {
    var entries = selectedEntries();
    if (!entries.length) return null;
    return window.BoardFormat.format({ board: { title: boardTitle, url: BOARD_URL, preparedDate: window.BoardFormat.preparedDate() }, entries: entries });
  }
  function canRich() {
    return !!(window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.write === "function" && typeof window.ClipboardItem === "function");
  }
  function copyRich() {
    var p = payload(); if (!p) return;
    var n = selected.size;
    if (!canRich()) { richFailed(p); return; }
    var promise;
    try {
      promise = navigator.clipboard.write([new window.ClipboardItem({
        "text/html": new Blob([p.html], { type: "text/html" }),
        "text/plain": new Blob([p.text], { type: "text/plain" })
      })]);
    } catch (e) { richFailed(p); return; }
    promise.then(function () { manualMode = false; els.reviewSelect.hidden = true; setStatus("Copied " + n + " card" + (n === 1 ? "" : "s") + " for Google Docs."); }, function () { richFailed(p); });
  }
  function richFailed(p) {
    setStatus("Rich copy was blocked here. Use Copy plain text, or copy from the review panel.");
    openReview(p);
  }
  function copyPlain() {
    var p = payload(); if (!p) return;
    var n = selected.size;
    if (window.isSecureContext && navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      var promise;
      try { promise = navigator.clipboard.writeText(p.text); } catch (e) { manualCopy(p); return; }
      promise.then(function () { manualMode = false; els.reviewSelect.hidden = true; setStatus("Copied " + n + " card" + (n === 1 ? "" : "s") + " as plain text."); }, function () { manualCopy(p); });
    } else manualCopy(p);
  }
  function selectOutput() {
    els.reviewText.focus(); els.reviewText.select();
    els.reviewHint.textContent = "Clipboard access is blocked here. The text below is selected: press ⌘C or Ctrl+C to copy it.";
  }
  function manualCopy(p) {
    manualMode = true;
    openReview(p);
    els.reviewSelect.hidden = false;
    selectOutput();
    setStatus("Clipboard blocked. Copy the selected text from the review panel.");
  }
  function renderReview(p, opts) {
    opts = opts || {};
    p = p || payload();
    var entries = selectedEntries();
    els.reviewList.innerHTML = entries.map(function (e) {
      return "<li><span>" + esc(e.title) + "</span><button type=\"button\" data-remove=\"" + esc(e.id) + "\" aria-label=\"Remove " + esc(e.title) + "\">Remove</button></li>";
    }).join("");
    Array.prototype.forEach.call(els.reviewList.querySelectorAll("button[data-remove]"), function (b) {
      b.addEventListener("click", function () {
        var id = b.getAttribute("data-remove"); selected.delete(id); saveSelection();
        var box = els.list.querySelector('.card[data-id="' + CSS.escape(id) + '"] input');
        if (box) { box.checked = false; box.closest(".card").setAttribute("data-selected", "false"); }
        setStatus("Removed. " + countLine());
        if (!selected.size) { updateTray(); closeReview(); els.reviewToggle.focus(); return; }
        renderReview(null, { fromReview: true }); updateTray();
      });
    });
    els.reviewText.value = p ? p.text : "";
    if (manualMode) {
      // The output was replaced, so any earlier text selection is gone. Re-select it when the edit came from inside the
      // panel (the Remove button is gone, focus would fall to <body>); otherwise say so and offer Select all text.
      if (opts.fromReview || document.activeElement === els.reviewText) selectOutput();
      else els.reviewHint.textContent = "The list changed and is no longer selected. Press Select all text, then ⌘C or Ctrl+C.";
    } else {
      els.reviewHint.textContent = "This is the plain-text version of what Copy for Google Docs puts on the clipboard.";
      if (opts.fromReview) (els.reviewList.querySelector("button[data-remove]") || els.reviewClose).focus();
    }
  }
  function openReview(p) {
    els.review.hidden = false; els.reviewToggle.setAttribute("aria-expanded", "true");
    renderReview(p);
    els.review.scrollIntoView({ block: "nearest" });
  }
  function closeReview() { els.review.hidden = true; els.reviewToggle.setAttribute("aria-expanded", "false"); els.reviewHint.textContent = ""; manualMode = false; els.reviewSelect.hidden = true; }

  function buildChrome() {
    els.lede = document.getElementById("lede"); els.meta = document.getElementById("meta");
    els.filters = document.getElementById("filters"); els.list = document.getElementById("list");
    var help = document.createElement("p"); help.className = "board-help";
    help.textContent = "Select cards with the checkbox beside each one, then copy them as a list for your leadership document.";
    els.filters.insertAdjacentElement("afterend", help);
    els.status = document.createElement("p"); els.status.className = "board-status"; els.status.id = "board-status"; els.status.setAttribute("aria-live", "polite");
    help.insertAdjacentElement("afterend", els.status);
    var tray = document.createElement("div"); tray.className = "board-tray"; tray.id = "board-tray"; tray.setAttribute("role", "region"); tray.setAttribute("aria-label", "Selection"); tray.hidden = true;
    tray.innerHTML = '<div class="board-tray-inner"><span class="board-tray-count" id="board-tray-count">0 selected</span>' +
      '<label><input type="checkbox" id="board-select-visible"> Select visible</label>' +
      '<button type="button" id="board-review-toggle" aria-expanded="false" aria-controls="board-review">Review</button>' +
      '<button type="button" class="primary" id="board-copy-rich">Copy for Google Docs</button>' +
      '<button type="button" id="board-copy-plain">Copy plain text</button>' +
      '<button type="button" id="board-clear">Clear</button></div>';
    document.body.appendChild(tray);
    var review = document.createElement("section"); review.className = "board-review"; review.id = "board-review"; review.hidden = true; review.setAttribute("aria-labelledby", "board-review-title");
    review.innerHTML = '<h2 id="board-review-title">Review selection</h2><p class="board-review-hint" id="board-review-hint"></p><ul id="board-review-list"></ul>' +
      '<textarea id="board-review-text" readonly aria-label="Plain-text copy"></textarea>' +
      '<button type="button" id="board-review-select" hidden>Select all text</button><button type="button" id="board-review-close">Close</button>';
    els.list.insertAdjacentElement("afterend", review);
    els.tray = tray; els.count = tray.querySelector("#board-tray-count"); els.selectVisible = tray.querySelector("#board-select-visible");
    els.reviewToggle = tray.querySelector("#board-review-toggle"); els.copyRich = tray.querySelector("#board-copy-rich");
    els.copyPlain = tray.querySelector("#board-copy-plain"); els.clear = tray.querySelector("#board-clear");
    els.review = review; els.reviewList = review.querySelector("#board-review-list"); els.reviewText = review.querySelector("#board-review-text");
    els.reviewHint = review.querySelector("#board-review-hint"); els.reviewClose = review.querySelector("#board-review-close");
    els.reviewSelect = review.querySelector("#board-review-select");
    els.reviewSelect.addEventListener("click", selectOutput);
    // Native focus scrolling honours scroll-padding-bottom; this covers browsers that do not, and wrapped tray heights.
    els.list.addEventListener("focusin", function (e) { keepAboveTray(e.target); });
    if (window.ResizeObserver) new ResizeObserver(function () { reserveTraySpace(); keepAboveTray(); }).observe(tray);
    window.addEventListener("resize", function () { reserveTraySpace(); keepAboveTray(); });

    els.selectVisible.addEventListener("change", function () {
      var vis = visibleEntries(), on = els.selectVisible.checked;
      vis.forEach(function (e) { if (on) selected.add(e.id); else selected.delete(e.id); });
      saveSelection(); renderList();
      setStatus((on ? "Selected " + vis.length + " visible card" + (vis.length === 1 ? "" : "s") + ". " : "Cleared visible cards. ") + countLine());
    });
    els.clear.addEventListener("click", function () { selected.clear(); saveSelection(); closeReview(); renderList(); setStatus("Selection cleared."); });
    els.copyRich.addEventListener("click", copyRich);
    els.copyPlain.addEventListener("click", copyPlain);
    els.reviewToggle.addEventListener("click", function () { if (els.review.hidden) openReview(); else closeReview(); });
    els.reviewClose.addEventListener("click", function () { closeReview(); els.reviewToggle.focus(); });
  }

  function boot() {
    buildChrome();
    try {
      var q = new URLSearchParams(window.location.search).get("type");
      if (q && FILTERS.some(function (f) { return f.id === q; })) activeFilter = q;
    } catch (e) { /* ignore */ }
    fetch(ENTRIES_URL + "?v=" + Date.now(), { cache: "no-store" }).then(function (res) { return res.json(); }).then(function (data) {
      if (data.blurb && els.lede) els.lede.textContent = data.blurb;
      boardTitle = data.title || (document.querySelector("h1") || {}).textContent || SLUG;
      allEntries = data.entries || [];
      byId = {}; allEntries.forEach(function (e) { byId[e.id] = e; });
      var stored = loadSelection(), dropped = 0;
      stored.forEach(function (id) { if (byId[id]) selected.add(id); else dropped += 1; });
      saveSelection();
      renderFilters(); renderList();
      if (dropped) setStatus(dropped + " previously selected card" + (dropped === 1 ? " is" : "s are") + " no longer on this board.");
    }).catch(function () {
      els.list.innerHTML = '<p class="empty">Could not load entries.json.</p>';
    });
  }
  boot();
})();
