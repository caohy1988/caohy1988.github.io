/* Leadership copy formatter for the BigQuery product boards (research/board-select-copy-spec.md §4).
   Pure: { board: { title, url, preparedDate }, entries } -> { html, text }. Browser global `BoardFormat`; CommonJS export for node tests. */
(function (root, factory) {
  var api = factory();
  if (typeof module === "object" && module && module.exports) module.exports = api;
  root.BoardFormat = api;
})(typeof window !== "undefined" ? window : globalThis, function () {
  "use strict";
  function esc(s) {
    return String(s == null ? "" : s)
      .replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;").replace(/'/g, "&#39;");
  }
  function isHttp(u) { return /^https?:\/\/\S+$/i.test(String(u || "")); }
  function clean(s) { return String(s == null ? "" : s).replace(/\s+/g, " ").trim(); }
  function sortEntries(entries) {
    return entries.slice().sort(function (a, b) {
      var da = a.date || "", db = b.date || "";
      if (db !== da) return db.localeCompare(da);
      return String(b.id || "").localeCompare(String(a.id || ""));
    });
  }
  function preparedDate(d) {
    return new Intl.DateTimeFormat("en-US", { month: "long", day: "numeric", year: "numeric" }).format(d || new Date());
  }
  function sourceLine(e) {
    return [clean(e.source), clean(e.displayDate || e.date)].filter(Boolean).join(" · ");
  }
  function format(input) {
    var board = (input && input.board) || {};
    var entries = sortEntries((input && input.entries) || []);
    var n = entries.length;
    var title = clean(board.title);
    var url = clean(board.url);
    var subtitle = "Selected product updates · Prepared " + clean(board.preparedDate) + " · " + n + " selected source" + (n === 1 ? "" : "s");
    var html = "<h3>" + esc(title) + "</h3>\n<p>" + esc(subtitle) + "</p>\n<ol>\n";
    var text = title + "\nSelected product updates\nPrepared " + clean(board.preparedDate) + " · " + n + " selected source" + (n === 1 ? "" : "s") + "\n\n";
    entries.forEach(function (e, i) {
      var t = clean(e.title), why = clean(e.why), src = sourceLine(e), href = clean(e.href), link = isHttp(href);
      html += "  <li><b>" + (link ? '<a href="' + esc(href) + '">' + esc(t) + "</a>" : esc(t)) + "</b>";
      if (why) html += "<br>" + esc(why);
      if (src) html += "<br>Source: " + esc(src);
      if (href) html += "<br>" + (link ? '<a href="' + esc(href) + '">' + esc(href) + "</a>" : esc(href));
      html += "</li>\n";
      text += (i + 1) + ". " + t + "\n";
      if (why) text += "   " + why + "\n";
      if (src) text += "   Source: " + src + "\n";
      if (href) text += "   " + href + "\n";
      text += "\n";
    });
    html += "</ol>\n";
    if (url) {
      html += "<p>Board: " + (isHttp(url) ? '<a href="' + esc(url) + '">' + esc(url) + "</a>" : esc(url)) + "</p>\n";
      text += "Board: " + url + "\n";
    }
    return { html: html, text: text };
  }
  return { format: format, sortEntries: sortEntries, preparedDate: preparedDate, escapeHtml: esc, isHttp: isHttp };
});
