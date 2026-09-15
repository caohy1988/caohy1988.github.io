// Skim gates for research/builds/mcp-apps-feature-matrix/ (PLAN_v2 §8, PR4 acceptance).
// Serves the repository root on a loopback port (or loads --url) and drives headless browsers at the PR70 viewports
// 320x568, 375x667, 820x1180 and 1280x720, folds closed:
//   * S1 rendered words inside <main> (≤ 900 words, ≤ 4.0 min at 230 wpm) at every viewport;
//   * S2 #banner, #aggregate-judgment and #shipping-action fully inside the first screen at 1280x720 and 375x667;
//   * S3 the four brief.md tokens inside the visible-without-scrolling text at the same two viewports;
//   * S6 no document horizontal overflow at 320 and 375; a compact disclosure opens on Enter, closes on Space and
//     Escape at every viewport and on tap at phone widths; print emulation opens the evidence fold and shows panels;
//   * fragment entry (#takeaways opens the evidence fold) and rendered status words (chips and compact words never
//     Yes/No/Supported/Unsupported; no private paths; compact row and card labels spell out "GitHub Copilot in VS Code").
// Recorded, never gated: overflow at 820/1280, first-screen geometry at 320/820, reader-structure heuristics, fonts.
// Usage: node tools/matrix_skim_check.mjs [--check] [--engine chromium|webkit|all] [--url URL] [--offline]
//                                         [--json FILE] [--shots DIR]
// Exit 0 = pass (or no --check); 1 = a gate failed under --check; 3 = Playwright or a browser is missing.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import crypto from "node:crypto";
import { fileURLToPath, pathToFileURL } from "node:url";
import { HOST_TLDR_STATUSES } from "./build_mcp_apps_matrix.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const PAGE_DIR = "research/builds/mcp-apps-feature-matrix";

export const VIEWPORTS = [
  { name: "320x568", width: 320, height: 568 },
  { name: "375x667", width: 375, height: 667 },
  { name: "820x1180", width: 820, height: 1180 },
  { name: "1280x720", width: 1280, height: 720 },
];
export const S1_MAX_WORDS = 900;
export const S1_MAX_MINUTES = 4.0;
export const WPM = 230;
export const FIRST_SCREEN_VIEWPORTS = ["1280x720", "375x667"];
export const OVERFLOW_VIEWPORTS = ["320x568", "375x667"];
export const S2_TARGETS = ["#banner", "#aggregate-judgment", "#shipping-action"];
export const S3_TOKENS = JSON.parse(fs.readFileSync(path.join(REPO, PAGE_DIR, "copy-map.json"), "utf8")).brief_tokens_S3;
const FORBIDDEN_STATUS_WORD = /^(yes|no|supported|unsupported)$/i;

export class PlaywrightMissing extends Error {}

async function loadPlaywright() {
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE,
    path.join(process.env.HOME || "", ".claude/skills/gstack/node_modules/playwright/index.mjs")].filter(Boolean);
  for (const c of candidates) { try { return await import(c.startsWith("/") ? pathToFileURL(c).href : c); } catch (e) { /* next */ } }
  return null;
}

const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };
function serve() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let file = path.join(REPO, decodeURIComponent(new URL(req.url, "http://x").pathname));
      if (!file.startsWith(REPO)) { res.writeHead(403); return res.end(); }
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
      if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
      res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

// Runs inside the page. Folds must be closed when called.
function measureInPage({ targets, tokens, privatePathSource }) {
  const countWords = (t) => (t.match(/\S+/g) || []).filter((x) => /[\p{L}\p{N}]/u.test(x)).length;
  const vw = window.innerWidth, vh = window.innerHeight;
  const main = document.querySelector("main");
  const fold = document.getElementById("full-evidence");
  const round = (x) => Math.round(x * 10) / 10;

  const sections = {};
  for (const el of main.children) sections[el.id || String(el.className) || el.tagName.toLowerCase()] = countWords(el.innerText);

  const boxes = {};
  for (const sel of targets) {
    const el = document.querySelector(sel);
    const r = el ? el.getBoundingClientRect() : null;
    boxes[sel] = r ? { top: round(r.top), bottom: round(r.bottom), fullyVisible: r.height > 0 && r.top >= 0 && r.bottom <= vh } : null;
  }

  // Visible-without-scrolling words: each word's box must sit inside the viewport and every clipping ancestor.
  const clipOf = (el) => {
    let L = 0, T = 0, R = vw, B = vh;
    for (let e = el; e && e !== document.documentElement; e = e.parentElement) {
      const cs = getComputedStyle(e);
      if (cs.overflowX !== "visible" || cs.overflowY !== "visible") {
        const r = e.getBoundingClientRect();
        L = Math.max(L, r.left); T = Math.max(T, r.top); R = Math.min(R, r.right); B = Math.min(B, r.bottom);
      }
    }
    return { L, T, R, B };
  };
  const seen = [];
  const range = document.createRange();
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let n = walker.nextNode(); n; n = walker.nextNode()) {
    const parent = n.parentElement;
    if (!parent || /^(SCRIPT|STYLE|NOSCRIPT)$/.test(parent.tagName)) continue;
    const pr = parent.getBoundingClientRect();
    if (pr.bottom <= 0 || pr.top >= vh) continue;
    if (parent.checkVisibility && !parent.checkVisibility({ visibilityProperty: true, opacityProperty: true })) continue;
    const c = clipOf(parent);
    for (const m of n.data.matchAll(/\S+/g)) {
      range.setStart(n, m.index);
      range.setEnd(n, m.index + m[0].length);
      const r = range.getBoundingClientRect();
      if (r.width > 0 && r.height > 0 && r.top >= c.T - 0.5 && r.bottom <= c.B + 0.5 && r.left >= c.L - 0.5 && r.right <= c.R + 0.5) seen.push(m[0]);
    }
  }
  const visibleText = seen.join(" ").replace(/[“”]/g, '"').replace(/[‘’]/g, "'");
  const tokenHits = Object.fromEntries(tokens.map((t) => [t, visibleText.includes(t)]));

  // Closed <details> content still has client rects in Chromium, so prefer checkVisibility.
  const shown = (e) => (e.checkVisibility ? e.checkVisibility({ visibilityProperty: true, opacityProperty: true }) : e.getClientRects().length > 0);
  const visibleTexts = (sel) => [...document.querySelectorAll(sel)].filter(shown).map((e) => e.textContent.trim());
  const privatePath = new RegExp(privatePathSource, "i");

  return {
    innerWidth: vw, innerHeight: vh, scrollY: window.scrollY,
    foldOpen: fold ? fold.open : null,
    panelsOpen: [...document.querySelectorAll(".compact-panel")].filter((p) => !p.hidden).length,
    words: countWords(main.innerText),
    bodyWords: countWords(document.body.innerText),
    sections,
    overflowX: document.documentElement.scrollWidth - document.documentElement.clientWidth,
    boxes,
    firstScreenWords: seen.length,
    firstScreenText: visibleText,
    tokenHits,
    webFontsLoaded: document.fonts ? [...new Set([...document.fonts].filter((f) => f.status === "loaded").map((f) => f.family.replace(/"/g, "")))].sort() : [],
    rendered: {
      chips: [...new Set(visibleTexts(".chip"))],
      compactWords: [...new Set(visibleTexts(".compact-word"))],
      copilotCompactLabels: [...visibleTexts(".compact-matrix tbody th"), ...visibleTexts(".compact-card h3")].filter((t) => /Copilot/.test(t)),
      copilotHostTldrLabels: visibleTexts(".host-tldr-table tbody th").filter((t) => /Copilot/.test(t)),
      privatePathInMain: privatePath.test(main.textContent),
    },
    reader: {
      title: document.title,
      lang: document.documentElement.lang,
      canonical: document.querySelector('link[rel="canonical"]')?.href || null,
      metaDescription: document.querySelector('meta[name="description"]')?.content || null,
      mainCount: document.querySelectorAll("main").length,
      h1: [...document.querySelectorAll("h1")].map((h) => h.textContent.trim()),
      visibleH2: [...main.querySelectorAll("h2")].filter(shown).map((h) => h.textContent.trim()),
      visibleParagraphsOver80Chars: [...main.querySelectorAll("p")].filter((p) => shown(p) && p.innerText.trim().length >= 80).length,
      evidenceSummary: fold?.querySelector("summary")?.textContent.trim() || null,
      idsPresent: ["aggregate-judgment", "shipping-action", "banner", "host-tldr", "by-product", "status-by-product", "what-would-change", "full-evidence", "matrix", "notes", "takeaways"].filter((id) => document.getElementById(id)),
    },
  };
}

const PRIVATE_PATH = String.raw`/Users/|/private/tmp/|(^|[\s"'\x60(>])/tmp/[A-Za-z0-9._/-]+|links to a receipt`;

async function disclosureCheck(page, touch) {
  const btn = page.locator(".compact-trigger:visible").first();
  await btn.scrollIntoViewIfNeeded();
  const panel = page.locator(`#${await btn.getAttribute("aria-controls")}`);
  const state = async () => ({ expanded: await btn.getAttribute("aria-expanded"), panelVisible: await panel.isVisible() });
  const opened = (s) => s.expanded === "true" && s.panelVisible;
  const closed = (s) => s.expanded === "false" && !s.panelVisible;
  const out = { button: (await btn.textContent()).replace(/\s+/g, " ").trim() };
  await btn.focus();
  await page.keyboard.press("Enter"); out.enter = await state();
  await page.keyboard.press("Space"); out.space = await state();
  await page.keyboard.press("Enter"); await page.keyboard.press("Escape"); out.escape = await state();
  out.keyboardPass = opened(out.enter) && closed(out.space) && closed(out.escape);
  if (touch) {
    await btn.tap(); out.tapOpen = await state();
    await btn.tap(); out.tapClose = await state();
    out.touchPass = opened(out.tapOpen) && closed(out.tapClose);
  }
  return out;
}

async function printCheck(page) {
  await page.emulateMedia({ media: "print" });
  await page.waitForTimeout(150);
  const r = await page.evaluate(() => {
    const fold = document.getElementById("full-evidence");
    const hiddenPanel = document.querySelector(".compact-panel[hidden]");
    return {
      foldOpen: fold.open,
      summaryDisplay: getComputedStyle(fold.querySelector("summary")).display,
      hiddenPanelDisplay: hiddenPanel ? getComputedStyle(hiddenPanel).display : null,
      printCss: [...document.querySelectorAll("style")].some((s) => /@media print[\s\S]*details\.evidence > summary \{ display: none; \}/.test(s.textContent)),
      openOnPrintScript: [...document.scripts].some((s) => /matchMedia\("print"\)/.test(s.textContent) && /fold\.open = true/.test(s.textContent)),
    };
  });
  await page.emulateMedia({ media: "screen" });
  r.pass = r.foldOpen && r.hiddenPanelDisplay !== "none" && r.printCss && r.openOnPrintScript;
  return r;
}

async function settle(page, url) {
  await page.goto(url, { waitUntil: "load", timeout: 45000 });
  await page.evaluate(() => (document.fonts ? document.fonts.ready.then(() => true) : true));
  await page.waitForTimeout(100);
}

async function runEngine(pw, engine, { url, offline, shots }) {
  let browser;
  try { browser = await pw[engine].launch(); } catch (e) { throw new PlaywrightMissing(`${engine} browser unavailable: ${e.message.split("\n")[0]}`); }
  const viewports = [];
  try {
    for (const vp of VIEWPORTS) {
      const touch = vp.width < 700;
      const context = await browser.newContext({ viewport: { width: vp.width, height: vp.height }, hasTouch: touch, deviceScaleFactor: 1 });
      if (offline) await context.route("**/*", (route) => (/^https?:\/\/127\.0\.0\.1[:/]/.test(route.request().url()) || route.request().url().startsWith("file:") ? route.continue() : route.abort()));
      const page = await context.newPage();
      await settle(page, url);
      const m = await page.evaluate(measureInPage, { targets: S2_TARGETS, tokens: S3_TOKENS, privatePathSource: PRIVATE_PATH });
      if (shots) {
        fs.mkdirSync(shots, { recursive: true });
        await page.screenshot({ path: path.join(shots, `${engine}-${vp.name}-first-screen.png`) });
      }
      m.disclosure = await disclosureCheck(page, touch);
      m.print = await printCheck(page);
      const frag = await context.newPage();
      await settle(frag, url.replace(/#.*$/, "") + "#takeaways");
      m.fragment = await frag.evaluate(() => {
        const t = document.getElementById("takeaways").getBoundingClientRect();
        return { foldOpen: document.getElementById("full-evidence").open, takeawaysTop: Math.round(t.top), visible: t.bottom > 0 && t.top < window.innerHeight };
      });
      m.fragment.pass = m.fragment.foldOpen && m.fragment.visible;
      viewports.push({ viewport: vp.name, touch, minutes: Math.round((m.words / WPM) * 100) / 100, ...m });
      await context.close();
    }
  } finally {
    await browser.close();
  }
  return { engine, viewports, gates: evaluateGates(viewports) };
}

export function evaluateGates(viewports) {
  const by = Object.fromEntries(viewports.map((v) => [v.viewport, v]));
  const S1 = {
    threshold: `≤ ${S1_MAX_WORDS} words and ≤ ${S1_MAX_MINUTES} min at ${WPM} wpm, folds closed`,
    values: viewports.map((v) => ({ viewport: v.viewport, words: v.words, minutes: v.minutes, foldOpen: v.foldOpen, panelsOpen: v.panelsOpen })),
  };
  S1.pass = viewports.every((v) => v.foldOpen === false && v.panelsOpen === 0 && v.words <= S1_MAX_WORDS && v.minutes <= S1_MAX_MINUTES);

  const S2 = {
    threshold: `${S2_TARGETS.join(", ")} fully visible without scrolling at ${FIRST_SCREEN_VIEWPORTS.join(" and ")}`,
    values: viewports.map((v) => ({ viewport: v.viewport, gated: FIRST_SCREEN_VIEWPORTS.includes(v.viewport), scrollY: v.scrollY, innerHeight: v.innerHeight, boxes: v.boxes })),
  };
  S2.pass = FIRST_SCREEN_VIEWPORTS.every((n) => by[n] && by[n].scrollY === 0 && by[n].foldOpen === false && S2_TARGETS.every((t) => by[n].boxes[t]?.fullyVisible));

  const S3 = {
    threshold: `first-screen text contains ${S3_TOKENS.map((t) => JSON.stringify(t)).join(", ")} at ${FIRST_SCREEN_VIEWPORTS.join(" and ")}`,
    values: viewports.map((v) => ({ viewport: v.viewport, gated: FIRST_SCREEN_VIEWPORTS.includes(v.viewport), firstScreenWords: v.firstScreenWords, tokenHits: v.tokenHits })),
  };
  S3.pass = FIRST_SCREEN_VIEWPORTS.every((n) => by[n] && S3_TOKENS.every((t) => by[n].tokenHits[t]));

  const S6 = {
    threshold: `no document overflow at ${OVERFLOW_VIEWPORTS.join(" and ")}; disclosure Enter/Space/Escape at every viewport, tap at phone widths; print opens the fold and shows panels`,
    values: viewports.map((v) => ({ viewport: v.viewport, overflowX: v.overflowX, overflowGated: OVERFLOW_VIEWPORTS.includes(v.viewport), keyboardPass: v.disclosure.keyboardPass, touchPass: v.disclosure.touchPass ?? null, printPass: v.print.pass })),
  };
  S6.overflowPass = OVERFLOW_VIEWPORTS.every((n) => by[n] && by[n].overflowX <= 0);
  S6.keyboardPass = viewports.every((v) => v.disclosure.keyboardPass);
  S6.touchPass = viewports.filter((v) => v.touch).every((v) => v.disclosure.touchPass);
  S6.printPass = viewports.every((v) => v.print.pass);
  S6.pass = S6.overflowPass && S6.keyboardPass && S6.touchPass && S6.printPass;

  const fragment = { threshold: "loading #takeaways opens #full-evidence and shows the target", values: viewports.map((v) => ({ viewport: v.viewport, ...v.fragment })) };
  fragment.pass = viewports.every((v) => v.fragment.pass);

  const rendered = {
    threshold: `chips ⊆ ${HOST_TLDR_STATUSES.join("/")}; no Yes/No/Supported/Unsupported chip or compact word; no private path in <main>; compact row and card labels spell out "GitHub Copilot in VS Code"`,
    values: viewports.map((v) => ({ viewport: v.viewport, ...v.rendered })),
  };
  rendered.pass = viewports.every((v) => {
    const r = v.rendered;
    return r.chips.every((c) => HOST_TLDR_STATUSES.includes(c))
      && ![...r.chips, ...r.compactWords].some((w) => FORBIDDEN_STATUS_WORD.test(w))
      && !r.privatePathInMain
      && r.copilotCompactLabels.length > 0 && r.copilotCompactLabels.every((t) => t === "GitHub Copilot in VS Code");
  });

  return { S1, S2, S3, S6, S4_fragment: fragment, S7_rendered: rendered };
}

export async function runSkimCheck({ engines = ["chromium"], url = null, offline = false, shots = null } = {}) {
  const pw = await loadPlaywright();
  if (!pw) throw new PlaywrightMissing("Playwright not found (tried 'playwright', $PLAYWRIGHT_MODULE, ~/.claude/skills/gstack/node_modules/playwright)");
  const html = fs.readFileSync(path.join(REPO, PAGE_DIR, "index.html"), "utf8");
  const server = url ? null : await serve();
  const target = url || `http://127.0.0.1:${server.address().port}/${PAGE_DIR}/`;
  try {
    const results = [];
    for (const engine of engines) results.push(await runEngine(pw, engine, { url: target, offline, shots }));
    return {
      tool: "tools/matrix_skim_check.mjs",
      generatedAt: new Date().toISOString(),
      target: url ? url : `local loopback server: /${PAGE_DIR}/`,
      localIndexSha256: crypto.createHash("sha256").update(html, "utf8").digest("hex"),
      offline,
      results,
    };
  } finally {
    if (server) server.close();
  }
}

function summarize(report) {
  const lines = [];
  for (const r of report.results) {
    for (const [name, g] of Object.entries(r.gates)) lines.push(`${g.pass ? "PASS" : "FAIL"} ${r.engine} ${name}: ${g.threshold}`);
    for (const v of r.viewports) {
      const b = (s) => v.boxes[s] ? `${v.boxes[s].bottom}${v.boxes[s].fullyVisible ? "" : "!"}` : "missing";
      lines.push(`     ${r.engine} ${v.viewport}: words=${v.words} min=${v.minutes} overflowX=${v.overflowX} bottoms banner=${b("#banner")} judgment=${b("#aggregate-judgment")} action=${b("#shipping-action")} tokens=${Object.values(v.tokenHits).filter(Boolean).length}/${S3_TOKENS.length} kbd=${v.disclosure.keyboardPass} tap=${v.disclosure.touchPass ?? "-"} print=${v.print.pass} frag=${v.fragment.pass} webFonts=${v.webFontsLoaded.length}`);
    }
  }
  return lines.join("\n");
}

if (process.argv[1] && path.resolve(process.argv[1]) === fileURLToPath(import.meta.url)) {
  const argv = process.argv.slice(2);
  const opt = (name) => { const i = argv.indexOf(name); return i >= 0 ? argv[i + 1] : null; };
  const engineArg = opt("--engine") || "chromium";
  const engines = engineArg === "all" ? ["chromium", "webkit"] : engineArg.split(",");
  try {
    const report = await runSkimCheck({ engines, url: opt("--url"), offline: argv.includes("--offline"), shots: opt("--shots") });
    const json = opt("--json");
    if (json) { fs.mkdirSync(path.dirname(path.resolve(json)), { recursive: true }); fs.writeFileSync(json, JSON.stringify(report, null, 2) + "\n"); }
    console.log(summarize(report));
    const failed = report.results.flatMap((r) => Object.entries(r.gates).filter(([, g]) => !g.pass).map(([n]) => `${r.engine} ${n}`));
    console.log(failed.length ? `${failed.length} gate(s) failed: ${failed.join(", ")}` : "all gates pass");
    if (argv.includes("--check") && failed.length) process.exit(1);
  } catch (e) {
    if (e instanceof PlaywrightMissing) { console.error(`SKIM CHECK UNAVAILABLE: ${e.message}`); process.exit(3); }
    throw e;
  }
}
