// Compact comparison (PLAN_v2 PR3): rows from judgments.json; disclosure panels from source cells.
import crypto from "node:crypto";
import { parseSourceCells, EXPECTED_PRODUCTS, EXPECTED_QUESTIONS, PRODUCT_SOURCE_COLUMN } from "./matrix_judgments_schema.mjs";

export function sha256(t) {
  return crypto.createHash("sha256").update(t, "utf8").digest("hex");
}

const KIND_LEGEND = {
  Documented: "Documented = the vendor's own page",
  "Source pinned": "Source pinned = a code snapshot, not a shipped build",
  Reported: "Reported = a dated user or staff report, not reproduced",
  "Code found": "Code found = strings or functions in a local install, nothing run",
  Unknown: "Unknown = this evidence does not establish the answer",
  "User setting": "User setting = a documented user control",
  "Internal gate found": "Internal gate found = code gate, not a user control; runtime value may be unknown",
};

const CELL_TOKEN_LEGEND = {
  VD: "VD = vendor documentation",
  HR: "HR = human report (dated)",
  SS: "SS = source snapshot",
  LI: "LI = local inspection (receipts private)",
  REC: "REC = recommendation",
  unk: "unk = unknown in the full matrix cell",
  unpub: "unpub = unpublished in the reviewed guide",
};

export function assertCompactFresh(judgments, sourceMd) {
  const { cells } = parseSourceCells(sourceMd);
  const errors = [];
  const seen = new Set();
  for (const row of judgments.compact_rows) {
    const key = `${row.product}::${row.question}`;
    if (seen.has(key)) errors.push(`duplicate compact row ${key}`);
    seen.add(key);
    if (!EXPECTED_PRODUCTS.includes(row.product)) errors.push(`unknown product ${row.product}`);
    if (!EXPECTED_QUESTIONS.includes(row.question)) errors.push(`unknown question ${row.question}`);
    const col = PRODUCT_SOURCE_COLUMN[row.product];
    if (row.product_source_column !== col) errors.push(`${key}: product_source_column must be ${col}`);
    const cellText = cells[row.source_row]?.[row.product_source_column];
    if (cellText == null) errors.push(`${key}: missing source cell ${row.source_row}/${row.product_source_column}`);
    else if (sha256(cellText) !== row.cell_sha256) errors.push(`${key}: cell_sha256 stale`);
    if (!row.phrase || !row.evidence_kind) errors.push(`${key}: missing phrase/evidence_kind`);
    else if (!row.phrase.startsWith(row.evidence_kind)) errors.push(`${key}: phrase must lead with evidence_kind`);
  }
  for (const p of EXPECTED_PRODUCTS) {
    for (const q of EXPECTED_QUESTIONS) {
      if (!seen.has(`${p}::${q}`)) errors.push(`missing compact row ${p}::${q}`);
    }
  }
  if (errors.length) {
    const err = new Error(`compact freshness failed:\n${errors.join("\n")}`);
    err.errors = errors;
    throw err;
  }
}

function markersIn(text) {
  return [...text.matchAll(/[¹²³⁴⁵⁶⁷⁸⁹]/g)].map((m) => m[0]);
}

function footnoteBlurb(notes, marker) {
  // notes are labelled paragraphs; LI footnotes pack ⁵/⁶/⁷ into one paragraph.
  for (const n of notes) {
    if (n.includes(marker)) {
      // Prefer the segment starting at this marker through the next marker or end.
      const idx = n.indexOf(marker);
      let end = n.length;
      for (const m of "¹²³⁴⁵⁶⁷⁸⁹") {
        if (m === marker) continue;
        const j = n.indexOf(m, idx + 1);
        if (j !== -1 && j < end) end = j;
      }
      return n.slice(idx, end).trim();
    }
  }
  return "";
}

function tokensInCell(md) {
  const found = [];
  for (const t of Object.keys(CELL_TOKEN_LEGEND)) {
    const re = new RegExp(`(?:^|[^A-Za-z])${t}(?:\\b|\\s|\\)|;)`);
    if (re.test(md)) found.push(t);
  }
  return found;
}

function splitPhrase(phrase, kind) {
  if (phrase === kind) return { word: kind, rest: "" };
  if (phrase.startsWith(kind + " · ")) return { word: kind, rest: phrase.slice(kind.length + 3) };
  if (phrase.startsWith(kind + " ·")) return { word: kind, rest: phrase.slice(kind.length + 2).trim() };
  return { word: kind, rest: phrase };
}

/**
 * @param {object} judgments
 * @param {string} sourceMd
 * @param {string[]} notes labelled note paragraphs from parseSource
 * @param {(md: string) => string} inline
 * @param {(s: string) => string} esc
 */
export function renderCompact(judgments, sourceMd, notes, inline, esc) {
  assertCompactFresh(judgments, sourceMd);
  const { cells } = parseSourceCells(sourceMd);
  const fields = judgments.field_definitions;
  const byProduct = new Map(EXPECTED_PRODUCTS.map((p) => [p, {}]));
  for (const row of judgments.compact_rows) {
    byProduct.get(row.product)[row.question] = row;
  }

  const questionOrder = EXPECTED_QUESTIONS;
  const th = ["Product", ...questionOrder.map((q) => fields[q].label)]
    .map((h, i) => `<th scope="col"${i === 0 ? ' class="product"' : ""}>${esc(h)}</th>`)
    .join("");

  const cellHtml = (product, q, idSuffix = "") => {
    const row = byProduct.get(product)[q];
    const { word, rest } = splitPhrase(row.phrase, row.evidence_kind);
    const cellMd = cells[row.source_row][row.product_source_column];
    const marks = markersIn(cellMd);
    const foot = marks.map((m) => footnoteBlurb(notes, m)).filter(Boolean);
    const tokens = tokensInCell(cellMd);
    const legendParts = [KIND_LEGEND[word], ...tokens.map((t) => CELL_TOKEN_LEGEND[t])].filter(Boolean);
    const label = `${product}, ${fields[q].label}: show evidence`;
    const id = `compact-${product.toLowerCase().replace(/[^a-z0-9]+/g, "-")}-${q}${idSuffix}`;
    return `
            <div class="compact-cell" data-compact-cell>
              <button type="button" class="compact-trigger" aria-expanded="false" aria-controls="${id}-panel" id="${id}-btn">
                <span class="compact-word">${esc(word)}</span>${rest ? ` <span class="compact-phrase">${esc(rest)}</span>` : ""}
                <span class="visually-hidden">${esc(label)}</span>
              </button>
              <div class="compact-panel" id="${id}-panel" hidden>
                <p class="compact-panel-label"><strong>${esc(product)}</strong> · ${esc(fields[q].label)}</p>
                <p class="compact-source-cell">${inline(cellMd)}</p>
                <p class="compact-legend">${esc(legendParts.join(" · "))}</p>
                ${foot.map((f) => `<p class="compact-footnote">${inline(f)}</p>`).join("\n                ")}
              </div>
            </div>`;
  };

  const rows = EXPECTED_PRODUCTS.map((product) => {
    const tds = questionOrder.map((q) => `<td>${cellHtml(product, q)}</td>`).join("");
    return `          <tr><th scope="row" class="product">${esc(product)}</th>${tds}</tr>`;
  }).join("\n");

  const cards = EXPECTED_PRODUCTS.map((product) => {
    const lines = questionOrder.map((q) => {
      const row = byProduct.get(product)[q];
      return `        <div class="compact-card-row"><span class="compact-card-q">${esc(fields[q].label)}</span>${cellHtml(product, q, "-card")}</div>`;
    }).join("\n");
    return `      <article class="compact-card" aria-label="${esc(product)}">\n        <h3>${esc(product)}</h3>\n${lines}\n      </article>`;
  }).join("\n");

  const wordLegend = Object.values(KIND_LEGEND).join(" · ");

  return `
    <section class="compact prose" id="status-by-product" aria-label="Status by product">
      <h2>Status by product</h2>
      <p class="compact-hint">Evidence word plus phrase. Activate a cell for the full v7 source cell, legend, and any footnote. Glyphs are not used as a support scale.</p>
      <div class="compact-table-wrap" data-compact-table>
        <table class="compact-matrix">
          <thead><tr>${th}</tr></thead>
          <tbody>
${rows}
          </tbody>
        </table>
      </div>
      <div class="compact-cards" data-compact-cards>
${cards}
      </div>
      <p class="compact-key">${esc(wordLegend)}</p>
      <p class="compact-portable">Every row: recommended portable content path (readable text, optional image).</p>
    </section>`;
}

export const COMPACT_DISCLOSURE_SCRIPT = `
    (function () {
      function closeAll(except) {
        document.querySelectorAll("[data-compact-cell]").forEach(function (cell) {
          if (except && cell === except) return;
          var btn = cell.querySelector(".compact-trigger");
          var panel = cell.querySelector(".compact-panel");
          if (!btn || !panel) return;
          btn.setAttribute("aria-expanded", "false");
          panel.hidden = true;
        });
      }
      document.addEventListener("click", function (e) {
        var btn = e.target.closest && e.target.closest(".compact-trigger");
        if (!btn) return;
        var cell = btn.closest("[data-compact-cell]");
        var panel = cell.querySelector(".compact-panel");
        var open = btn.getAttribute("aria-expanded") === "true";
        closeAll(open ? null : cell);
        btn.setAttribute("aria-expanded", open ? "false" : "true");
        panel.hidden = open;
      });
      document.addEventListener("keydown", function (e) {
        if (e.key !== "Escape") return;
        closeAll(null);
      });
    })();
`;
