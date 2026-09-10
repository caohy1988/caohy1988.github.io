// node --test tools/board_format.test.mjs  (research/board-select-copy-spec.md G1)
import test from "node:test";
import assert from "node:assert/strict";
import { createRequire } from "node:module";
const require = createRequire(import.meta.url);
const { format, sortEntries, isHttp } = require("../assets/board-format.js");

const board = { title: "Conversational Analytics in BigQuery", url: "https://caohy1988.github.io/research/conversational-analytics/", preparedDate: "September 10, 2026" };
const older = { id: "a-old", date: "2026-09-02", displayDate: "Sep 2, 2026", source: "Medium (Google Cloud Community)", title: "Talk to Your Data Where You Work", href: "https://medium.com/google-cloud/talk-805891f239a9", why: "A community implementation connects BigQuery Data Agents to Google Chat.", tags: ["x"], kind: "essay" };
const newer = { id: "b-new", date: "2026-09-06", displayDate: "Feb 2026 · updated Sep 6, 2026", source: "Gunnar Griese", title: "Conversational Analytics for GA Data & <Agents>", href: "https://gunnargriese.com/posts/conversational-analytics/", why: 'End-to-end build that pairs GA→BigQuery "transfers" with Data Agents.', kind: "essay" };

test("html: heading, subtitle, one numbered list, bold linked titles, why verbatim, source line, url line, board link", () => {
  const { html } = format({ board, entries: [older, newer] });
  assert.equal(html,
`<h3>Conversational Analytics in BigQuery</h3>
<p>Selected product updates · Prepared September 10, 2026 · 2 selected sources</p>
<ol>
  <li><b><a href="https://gunnargriese.com/posts/conversational-analytics/">Conversational Analytics for GA Data &amp; &lt;Agents&gt;</a></b><br>End-to-end build that pairs GA→BigQuery &quot;transfers&quot; with Data Agents.<br>Source: Gunnar Griese · Feb 2026 · updated Sep 6, 2026<br><a href="https://gunnargriese.com/posts/conversational-analytics/">https://gunnargriese.com/posts/conversational-analytics/</a></li>
  <li><b><a href="https://medium.com/google-cloud/talk-805891f239a9">Talk to Your Data Where You Work</a></b><br>A community implementation connects BigQuery Data Agents to Google Chat.<br>Source: Medium (Google Cloud Community) · Sep 2, 2026<br><a href="https://medium.com/google-cloud/talk-805891f239a9">https://medium.com/google-cloud/talk-805891f239a9</a></li>
</ol>
<p>Board: <a href="https://caohy1988.github.io/research/conversational-analytics/">https://caohy1988.github.io/research/conversational-analytics/</a></p>
`);
  assert.ok(!html.includes("<table") && !html.includes("<ul") && !html.includes("tags"));
});

test("text: same content, numbered, indented, url line present, no html", () => {
  const { text } = format({ board, entries: [newer, older] });
  assert.equal(text,
`Conversational Analytics in BigQuery
Selected product updates
Prepared September 10, 2026 · 2 selected sources

1. Conversational Analytics for GA Data & <Agents>
   End-to-end build that pairs GA→BigQuery "transfers" with Data Agents.
   Source: Gunnar Griese · Feb 2026 · updated Sep 6, 2026
   https://gunnargriese.com/posts/conversational-analytics/

2. Talk to Your Data Where You Work
   A community implementation connects BigQuery Data Agents to Google Chat.
   Source: Medium (Google Cloud Community) · Sep 2, 2026
   https://medium.com/google-cloud/talk-805891f239a9

Board: https://caohy1988.github.io/research/conversational-analytics/
`);
  assert.ok(!/<(h3|p|ol|li|b|a)\b/.test(text), "no formatter tags in the plain flavor");
});

test("board order (newest first) is independent of selection order", () => {
  const a = format({ board, entries: [older, newer] }).text;
  const b = format({ board, entries: [newer, older] }).text;
  assert.equal(a, b);
  assert.equal(sortEntries([older, newer])[0].id, "b-new");
});

test("non-http href renders the title and url as text, never as a link; date falls back when displayDate is absent", () => {
  const e = { id: "x", date: "2025-01-02", source: "Doc", title: "Odd", href: "javascript:alert(1)", why: "w" };
  const { html, text } = format({ board, entries: [e] });
  assert.ok(!html.includes("<a href=\"javascript"));
  assert.ok(html.includes("<b>Odd</b>") && html.includes("Source: Doc · 2025-01-02"));
  assert.ok(text.includes("   Source: Doc · 2025-01-02\n"));
  assert.equal(isHttp("http://a.b/c"), true);
  assert.equal(isHttp("ftp://a"), false);
});

test("singular count, empty why omitted, whitespace collapsed", () => {
  const e = { id: "x", date: "2025-01-02", source: "  S  ", title: " T\n  T ", href: "https://a.b/", why: "" };
  const { html, text } = format({ board, entries: [e] });
  assert.ok(html.includes("1 selected source</p>") && html.includes("<b><a href=\"https://a.b/\">T T</a></b><br>Source: S · 2025-01-02"));
  assert.ok(text.includes("1. T T\n   Source: S · 2025-01-02\n   https://a.b/\n"));
});
