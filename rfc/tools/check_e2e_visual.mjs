// Offline acceptance check for the /rfc/e2e/ human walkthrough (rfc/e2e/VISUAL_PLAN.md, U2/U3 verification contract).
// Serves the repository root on a loopback port (HTTP Range capable, so the tape can seek) and drives headless Chromium:
//   * static: builder --check, relative links resolve, no local machine paths, caption cues monotonic, evidence and tape
//     bytes unchanged against the merge base with origin/main;
//   * 1280x800: first viewport shows problem, Alder/Acme bridge, both planes, run label and the walkthrough start;
//     every chapter by rail, Previous/Next and direct link shows its own generated facts (checked against
//     visual-evidence.json) and diagram highlight; keyboard selection; #tape opens Evidence; a step's tape link seeks;
//   * reading load: the complete primary path counted twice, (a) with JavaScript off (all six panels in flow) and
//     (b) interactive, as the text outside the panel plus every panel selected once; Evidence and Source details closed;
//   * no-JS, evidence fetch failure and a mismatched evidence file keep the static record and show no selection;
//   * reduced motion, 390x844 and 375x667 phones, and 200% zoom (640px CSS viewport): no horizontal overflow.
// Flags: --shots DIR writes screenshots. Exit 0 = pass; 1 = a check failed; 3 = no Playwright.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { spawnSync } from "node:child_process";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const PAGE = "/rfc/e2e/";
const args = process.argv.slice(2);
const shotsAt = args.indexOf("--shots");
const SHOTS = shotsAt >= 0 ? path.resolve(args[shotsAt + 1] || "/tmp/e2e-visual-shots") : null;
const WORD_TARGET = 850, WORD_CAP = 950;
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".jsonl": "text/plain", ".md": "text/markdown", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain", ".vtt": "text/vtt", ".mp4": "video/mp4", ".cast": "text/plain" };

const failures = [];
const results = {};
const check = (ok, what, detail) => { console.log(`${ok ? "OK  " : "FAIL"} ${what}${detail !== undefined ? " " + JSON.stringify(detail) : ""}`); if (!ok) failures.push(what); };
const words = (t) => (String(t).match(/\S+/g) || []).length;

// ---------------------------------------------------------------- static checks
{
  const r = spawnSync(process.execPath, [path.join(REPO, "rfc/tools/build_e2e_visual_evidence.mjs"), "--check"], { cwd: REPO, encoding: "utf8" });
  check(r.status === 0, "builder --check", r.stdout.trim());
  const html = fs.readFileSync(path.join(REPO, "rfc/e2e/index.html"), "utf8");
  const shipped = ["rfc/e2e/index.html", "rfc/e2e/visual-evidence.json", "rfc/e2e/visual-walkthrough.js", "rfc/e2e/styles.css"].map((f) => fs.readFileSync(path.join(REPO, f), "utf8"));
  check(shipped.every((t) => !/\/Users\/|~\/|[A-Z]:\\\\Users/.test(t)), "no local machine path in shipped page assets");
  const refs = [...html.matchAll(/\s(?:href|src)="([^"]+)"/g)].map((m) => m[1]).filter((u) => !/^(https?:|mailto:|#|data:)/.test(u));
  const missing = [];
  for (const u of new Set(refs)) {
    const clean = u.split("#")[0].split("?")[0];
    if (!clean) continue;
    let file = clean.startsWith("/") ? path.join(REPO, clean) : path.resolve(REPO, "rfc/e2e", clean);
    if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
    if (!fs.existsSync(file)) missing.push(u);
  }
  check(missing.length === 0, `relative links resolve (${new Set(refs).size} unique)`, missing);
  const vtt = fs.readFileSync(path.join(REPO, "rfc/e2e/okf-publish-connected.en.vtt"), "utf8");
  const toS = (t) => { const [h, m, s] = t.split(":"); return +h * 3600 + +m * 60 + +s; };
  const cues = [...vtt.matchAll(/(\d\d:\d\d:\d\d\.\d{3}) --> (\d\d:\d\d:\d\d\.\d{3})/g)].map((m) => [toS(m[1]), toS(m[2])]);
  const mono = cues.every(([a, b], i) => a < b && (i === 0 || a >= cues[i - 1][1]));
  check(vtt.startsWith("WEBVTT") && cues.length > 0 && mono && cues[cues.length - 1][1] <= 92.75, "captions parse, cues monotonic, end ≤ 92.75 s", { cues: cues.length });
  const mb = spawnSync("git", ["merge-base", "HEAD", "origin/main"], { cwd: REPO, encoding: "utf8" }).stdout.trim();
  const diff = mb ? spawnSync("git", ["diff", "--name-only", mb, "--", "rfc/spikes", "rfc/demo"], { cwd: REPO, encoding: "utf8" }).stdout.trim() : "no merge base";
  const untracked = spawnSync("git", ["status", "--porcelain", "--", "rfc/spikes", "rfc/demo"], { cwd: REPO, encoding: "utf8" }).stdout.trim();
  check(mb && diff === "" && untracked === "", "evidence, MP4, cast and transcript bytes unchanged vs merge base", { base: mb.slice(0, 7), diff, untracked });
}

// ---------------------------------------------------------------- browser
async function loadPlaywright() {
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE, path.join(process.env.HOME || "", ".claude/skills/gstack/node_modules/playwright/index.mjs")].filter(Boolean);
  for (const c of candidates) { try { return await import(c.startsWith("/") ? pathToFileURL(c).href : c); } catch (e) { /* next */ } }
  return null;
}
function serve() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let file = path.join(REPO, decodeURIComponent(new URL(req.url, "http://x").pathname));
      if (!file.startsWith(REPO)) { res.writeHead(403); return res.end(); }
      if (fs.existsSync(file) && fs.statSync(file).isDirectory()) file = path.join(file, "index.html");
      if (!fs.existsSync(file)) { res.writeHead(404); return res.end("not found"); }
      const size = fs.statSync(file).size;
      const type = TYPES[path.extname(file)] || "application/octet-stream";
      const m = /^bytes=(\d*)-(\d*)$/.exec(req.headers.range || "");
      if (m) {
        const start = m[1] ? Number(m[1]) : Math.max(0, size - Number(m[2]));
        const end = m[1] && m[2] ? Math.min(Number(m[2]), size - 1) : size - 1;
        res.writeHead(206, { "content-type": type, "accept-ranges": "bytes", "content-range": `bytes ${start}-${end}/${size}`, "content-length": end - start + 1 });
        return fs.createReadStream(file, { start, end }).pipe(res);
      }
      res.writeHead(200, { "content-type": type, "accept-ranges": "bytes", "content-length": size });
      fs.createReadStream(file).pipe(res);
    });
    server.listen(0, "127.0.0.1", () => resolve(server));
  });
}

const pw = await loadPlaywright();
if (!pw) { console.error("playwright unavailable"); process.exit(3); }
const server = await serve();
const base = `http://127.0.0.1:${server.address().port}`;
const browser = await pw.chromium.launch();
if (SHOTS) fs.mkdirSync(SHOTS, { recursive: true });
const shot = (page, name, opts = {}) => SHOTS ? page.screenshot({ path: path.join(SHOTS, name), ...opts }) : Promise.resolve();
const evidence = JSON.parse(fs.readFileSync(path.join(REPO, "rfc/e2e/visual-evidence.json"), "utf8"));
const ids = evidence.stages.map((s) => s.id);

async function open(opts = {}, hash = "") {
  const { route, ...ctxOpts } = opts;
  const context = await browser.newContext({ viewport: { width: 1280, height: 800 }, ...ctxOpts });
  const page = await context.newPage();
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  if (route) await page.route("**/rfc/e2e/visual-evidence.json", route);
  await page.goto(base + PAGE + hash, { waitUntil: "load" });
  if (ctxOpts.javaScriptEnabled !== false) await page.waitForFunction(() => document.getElementById("walkthrough").hasAttribute("data-mode"), null, { timeout: 8000 }).catch(() => {});
  return { context, page, errors };
}
// wait for smooth scrolling to finish before measuring positions
const settle = (page) => page.evaluate(async () => {
  let last = -1, same = 0;
  for (let i = 0; i < 60 && same < 3; i++) { await new Promise((r) => setTimeout(r, 80)); const y = window.scrollY; same = y === last ? same + 1 : 0; last = y; }
});
const overflow = (page) => page.evaluate(() => document.documentElement.scrollWidth - window.innerWidth);
const state = (page) => page.evaluate(() => {
  const root = document.getElementById("walkthrough");
  const shown = [...root.querySelectorAll(".vw-stage")].filter((a) => a.offsetHeight > 0).map((a) => a.dataset.stage);
  const current = [...root.querySelectorAll(".vw-rail a[aria-current]")].map((a) => a.dataset.stage);
  const lit = [...root.querySelectorAll(".vw-obj.is-lit")].map((o) => o.dataset.obj);
  const litLinks = [...root.querySelectorAll(".vw-link.is-lit")].map((o) => o.dataset.link);
  const facts = [...root.querySelectorAll(".vw-stage [data-fact], .vw-outcomes [data-fact]")].filter((e) => e.offsetParent !== null || e.closest("details:not([open])") === null && e.getClientRects().length).map((e) => [e.dataset.fact, e.textContent]);
  return { mode: root.dataset.mode, shown, current, lit, litLinks, facts, hash: location.hash, live: (root.querySelector(".vw-live") || {}).textContent || "",
    notice: !root.querySelector(".vw-unavailable").hidden, pager: !root.querySelector(".vw-pager").hidden };
});
const factsMatch = (facts) => facts.every(([k, t]) => evidence.facts[k] && evidence.facts[k].display === t);

// ---- desktop, interactive
{
  const { context, page, errors } = await open();
  let s = await state(page);
  check(s.mode === "interactive", "1280: evidence loads and matches markup → interactive", s.mode);
  const top = await page.evaluate(() => {
    const r = (sel) => { const e = document.querySelector(sel); if (!e) return null; const b = e.getBoundingClientRect(); return { top: Math.round(b.top), bottom: Math.round(b.bottom) }; };
    const bridge = document.querySelector(".bridge").textContent;
    return { h1: r("h1"), bridge: r(".bridge"), roles: r(".masthead .roles"), badges: r(".badges"), go: r(".cta a.go"), teaser: r(".teaser"), path: r("#path"),
      illustrative: /illustrative\s+118% versus 96%/.test(bridge), acme: /Acme’s January 2026 gross margin, using synthetic data/.test(bridge),
      planes: /Open Knowledge Format/.test(document.querySelector(".masthead .roles").textContent) && /BigQuery Knowledge Publish/.test(document.querySelector(".masthead .roles").textContent) };
  });
  check(["h1", "bridge", "roles", "badges", "go"].every((k) => top[k] && top[k].bottom <= 800) && top.illustrative && top.acme && top.planes, "1280x800 first viewport: problem, labelled Alder bridge, Acme, both planes, run label, walkthrough start", top);
  await shot(page, "desktop-1280-first-viewport.png");
  check(s.shown.length === 1 && s.shown[0] === "publish" && s.current[0] === "publish", "1280: initial view shows step 1 only", s);
  check(errors.length === 0, "1280: no page errors", errors);

  // rail traversal
  const panelWords = {};
  for (const id of ids) {
    await page.click(`.vw-rail a[data-stage="${id}"]`);
    s = await state(page);
    const want = evidence.stages.find((x) => x.id === id).editorial;
    const ok = s.shown.length === 1 && s.shown[0] === id && s.current[0] === id && s.hash === `#stage-${id}` &&
      JSON.stringify([...s.lit].sort()) === JSON.stringify([...want.highlight].sort()) && JSON.stringify(s.litLinks) === JSON.stringify(want.links) &&
      s.facts.length > 0 && factsMatch(s.facts);
    check(ok, `rail → ${id}: one panel, aria-current, hash, diagram highlight, ${s.facts.length} generated facts match visual-evidence.json`, ok ? undefined : s);
    panelWords[id] = await page.evaluate((i) => document.getElementById(`stage-${i}`).innerText, id).then(words);
    if (SHOTS) { await page.waitForTimeout(300); await page.locator("#walkthrough").screenshot({ path: path.join(SHOTS, `desktop-1280-stage-${id}.png`) }); }
  }
  check(/Step 6 of 6: Remove access, then recheck/.test(s.live), "selection announced politely", s.live);

  // previous / next
  await page.click(`.vw-rail a[data-stage="publish"]`);
  const order = [];
  for (let i = 0; i < ids.length; i++) { order.push((await state(page)).shown[0]); if (i < ids.length - 1) await page.click('.vw-pager [data-dir="1"]'); }
  const nextDisabled = await page.$eval('.vw-pager [data-dir="1"]', (b) => b.disabled);
  await page.click('.vw-pager [data-dir="-1"]');
  const back = (await state(page)).shown[0];
  check(JSON.stringify(order) === JSON.stringify(ids) && nextDisabled && back === "receipt", "Next walks 1→6, disabled at the end; Previous goes back", { order, nextDisabled, back });
  await page.goBack();
  check((await state(page)).shown[0] === "revoke", "browser Back restores the previous step");

  // reading load, interactive: text outside the panel + every panel once (Evidence and Source details closed)
  await page.click(`.vw-rail a[data-stage="publish"]`);
  const outside = await page.evaluate(() => {
    const all = document.body.innerText;
    const sel = document.querySelector(".vw-stage.is-sel").innerText;
    const nav = document.querySelector(".site-topbar").innerText;
    return { all, sel, nav, evidenceOpen: document.getElementById("evidence").open, srcOpen: document.querySelectorAll(".vw-src[open]").length };
  });
  const interactiveTotal = words(outside.all) - words(outside.sel) + Object.values(panelWords).reduce((a, b) => a + b, 0);
  results.words = { interactive_all_panels_once: interactiveTotal, site_nav: words(outside.nav), panels: panelWords };

  // keyboard
  await page.focus('.vw-rail a[data-stage="publish"]');
  await page.keyboard.press("Tab");
  const focused = await page.evaluate(() => ({ stage: document.activeElement.dataset.stage, outline: getComputedStyle(document.activeElement).outlineStyle }));
  await page.keyboard.press("Enter");
  s = await state(page);
  check(focused.stage === "catalog" && focused.outline !== "none" && s.shown[0] === "catalog", "keyboard: Tab reaches the next chapter with a visible focus outline; Enter selects it", { focused, shown: s.shown });

  // source details do not change the selection; Evidence opening does not block the walkthrough
  await page.click("#stage-catalog .vw-src > summary");
  await page.click("#evidence > summary");
  await page.click(`.vw-rail a[data-stage="receipt"]`);
  s = await state(page);
  check(s.shown[0] === "receipt", "with Source details and Evidence open, chapter selection still works", s.shown);

  // captions track
  const track = await page.evaluate(async () => {
    const v = document.getElementById("tape-video"); const t = v.textTracks[0];
    for (let i = 0; i < 40 && !(t.cues && t.cues.length); i++) await new Promise((r) => setTimeout(r, 100));
    return { mode: t.mode, cues: t.cues ? t.cues.length : 0, label: t.label };
  });
  check(track.cues > 0, "caption track loads in the browser", track);

  // tape seek from a step
  await page.evaluate(() => {
    document.getElementById("evidence").open = false;
    const v = document.getElementById("tape-video");
    v.addEventListener("seeked", () => { window.__seekedAt = v.currentTime; }, { once: true });
  });
  await page.click("#stage-receipt a.seek");
  await settle(page);
  const seekState = await page.evaluate(async () => {
    const v = document.getElementById("tape-video");
    for (let i = 0; i < 80 && window.__seekedAt === undefined; i++) await new Promise((r) => setTimeout(r, 100));
    v.pause();
    const r = document.getElementById("tape").getBoundingClientRect();
    return { open: document.getElementById("evidence").open, readyState: v.readyState, t: Math.round((window.__seekedAt ?? -1) * 10) / 10, hash: location.hash, tapeTop: Math.round(r.top), error: v.error && v.error.code };
  });
  check(seekState.open && seekState.hash === "#tape" && seekState.tapeTop < 800 && seekState.tapeTop > -50, "step tape link opens Evidence and scrolls to the tape", seekState);
  check(seekState.readyState >= 1 && Math.abs(seekState.t - 48.8) <= 1, "compressed-time seek lands at 0:49 over a Range-capable server", seekState);
  await context.close();
}

// ---- direct links
{
  const { context, page } = await open({}, "#stage-revoke");
  const s = await state(page);
  const inView = await page.evaluate(() => { const r = document.getElementById("stage-revoke").getBoundingClientRect(); return r.top >= 0 && r.top < window.innerHeight; });
  check(s.shown[0] === "revoke" && s.current[0] === "revoke" && inView, "direct link #stage-revoke selects and shows step 6", { shown: s.shown, inView });
  await context.close();
}
{
  const { context, page } = await open({}, "#tape");
  await page.waitForTimeout(300);
  await settle(page);
  const t = await page.evaluate(() => ({ open: document.getElementById("evidence").open, top: Math.round(document.getElementById("tape").getBoundingClientRect().top) }));
  check(t.open && t.top >= -5 && t.top < 800, "direct link #tape opens Evidence and scrolls to the tape", t);
  await context.close();
}
{
  const { context, page } = await open({}, "#path");
  const s = await state(page);
  check(s.shown[0] === "publish", "#path keeps step 1 selected");
  await context.close();
}

// ---- no JavaScript: all six panels in flow; this is also the complete primary reading path
{
  const { context, page } = await open({ javaScriptEnabled: false });
  const n = await page.evaluate(() => {
    const root = document.getElementById("walkthrough");
    return { shown: [...root.querySelectorAll(".vw-stage")].filter((a) => a.offsetHeight > 0).length, current: root.querySelectorAll("[aria-current]").length, lit: root.querySelectorAll(".is-lit").length,
      pagerHidden: root.querySelector(".vw-pager").hidden, notice: !root.querySelector(".vw-unavailable").hidden, text: document.body.innerText, nav: document.querySelector(".site-topbar").innerText,
      evidenceOpen: document.getElementById("evidence").open, srcOpen: document.querySelectorAll(".vw-src[open]").length };
  });
  check(n.shown === 6 && n.current === 0 && n.lit === 0 && n.pagerHidden && !n.evidenceOpen && n.srcOpen === 0, "no-JS: six recorded steps visible in order, no selection or highlight, folds closed", { shown: n.shown, current: n.current, lit: n.lit });
  results.words.static_no_js = words(n.text);
  results.words.static_no_js_without_nav = words(n.text) - words(n.nav);
  const honest = !/production[- ]ready|ready for production|readiness achieved|all jobs succeeded|hermetic/i.test(n.text);
  check(honest, "honesty: no readiness / all-succeeded / hermetic wording in the rendered page");
  await page.setViewportSize({ width: 1280, height: 800 });
  await shot(page, "nojs-1280-full.png", { fullPage: true });
  await context.close();
}

// ---- evidence fetch failure and mismatched evidence
for (const [label, route] of [
  ["fetch failure (404)", (r) => r.fulfill({ status: 404, body: "gone" })],
  ["mismatched evidence file", async (r) => { const res = await r.fetch(); const j = await res.json(); j.markup_sha256 = "0".repeat(64); await r.fulfill({ response: res, body: JSON.stringify(j) }); }],
]) {
  const { context, page, errors } = await open({ route });
  const s = await state(page);
  const text = await page.evaluate(() => document.querySelector(".vw-unavailable").innerText);
  check(s.mode === "static" && s.notice && s.shown.length === 6 && s.current.length === 0 && s.lit.length === 0 && !s.pager && factsMatch(s.facts) && /Interactive details unavailable/.test(text) && errors.length === 0,
    `${label}: "Interactive details unavailable", static dated record kept, no selection or promoted state`, { mode: s.mode, shown: s.shown.length, errors });
  if (label.startsWith("fetch")) await shot(page, "fetch-failure-1280.png");
  await context.close();
}

// ---- reduced motion
{
  const { context, page } = await open({ reducedMotion: "reduce" });
  const anim = await page.evaluate(() => getComputedStyle(document.querySelector(".vw-stage.is-sel")).animationName);
  check(anim === "none", "reduced motion removes the panel transition", anim);
  await context.close();
}

// ---- phones and 200% zoom
for (const [w, h, name] of [[390, 844, "phone-390"], [375, 667, "phone-375"], [640, 400, "zoom-200"]]) {
  const { context, page, errors } = await open({ viewport: { width: w, height: h }, isMobile: w < 640, hasTouch: w < 640, deviceScaleFactor: 2 });
  const o1 = await overflow(page);
  const pos = await page.evaluate(() => { const b = (sel) => Math.round(document.querySelector(sel).getBoundingClientRect().bottom); return { h1: b("h1"), bridge: b(".bridge"), roles: b(".masthead .roles"), badges: b(".badges"), go: b(".cta a.go"), railLeft: Math.round(document.querySelector(".vw-rail").getBoundingClientRect().left), workLeft: Math.round(document.querySelector(".vw-work").getBoundingClientRect().left) }; });
  if (name === "phone-390") check(pos.go <= Math.round(h * 1.35), "390x844: problem, bridge, both planes, run label and walkthrough start within the first short scroll", pos);
  await shot(page, `${name}-top.png`);
  let maxOverflow = o1, allOk = true;
  const perStep = {};
  for (const id of ids) {
    await page.click(`.vw-rail a[data-stage="${id}"]`);
    await settle(page);
    const s = await state(page);
    allOk = allOk && s.shown[0] === id && factsMatch(s.facts);
    maxOverflow = Math.max(maxOverflow, await overflow(page));
    // the panel heading is on screen (and, on phones, the diagram above it)
    const inView = await page.evaluate((i) => { const r = document.getElementById(`stage-${i}-h`).getBoundingClientRect(); return { top: Math.round(r.top), bottom: Math.round(r.bottom), ok: r.top >= 0 && r.bottom <= window.innerHeight }; }, id);
    perStep[id] = inView.ok ? "ok" : inView;
    allOk = allOk && inView.ok && s.shown[0] === id;
  }
  await page.click("#evidence > summary");
  maxOverflow = Math.max(maxOverflow, await overflow(page));
  check(allOk && maxOverflow <= 0 && pos.railLeft === pos.workLeft && errors.length === 0, `${name} ${w}x${h}: single column, every step selectable and brought into view, no horizontal overflow (Evidence open too)`, { maxOverflow, perStep });
  if (SHOTS) { await page.click("#evidence > summary"); await page.click(`.vw-rail a[data-stage="revoke"]`); await page.click(`.vw-rail a[data-stage="receipt"]`); await settle(page); await page.waitForTimeout(300); await page.screenshot({ path: path.join(SHOTS, `${name}-receipt.png`) }); }
  await context.close();
}

await browser.close();
server.close();

const w = results.words;
w.target = WORD_TARGET; w.cap = WORD_CAP;
w.primary_path = Math.max(w.interactive_all_panels_once, w.static_no_js);
check(w.primary_path <= WORD_CAP, `reading load: complete primary path ${w.primary_path} words incl. site nav (target ${WORD_TARGET}, cap ${WORD_CAP}); ≈${(w.primary_path / 230).toFixed(1)} min at 230 wpm`, w);
console.log(JSON.stringify({ results, failures }, null, 2));
console.log(failures.length ? `${failures.length} check(s) failed` : "all checks pass");
process.exit(failures.length ? 1 : 0);
