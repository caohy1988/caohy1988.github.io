// Offline browser check for the shared site navigation (research/site-nav-spec.md acceptance list).
// Serves the repository root on a loopback port, drives headless Chromium over every page in tools/site_nav.mjs and checks:
//   * the block is present, the primary nav exists once, every IA link is present with its href;
//   * exactly one link carries aria-current="page" and it is the page's own (or /rfc/ for the demos);
//   * desktop (1280px): folders start closed; each folder opened in turn stays inside the viewport with no horizontal
//     overflow; opening one closes the other; Escape closes and returns focus to the button; ArrowDown opens and
//     focuses the first item; tabbing out closes; an outside click closes an open folder; the toggle is hidden;
//   * desktop without the script: hovering a folder button, then crossing the gap into its panel, keeps it open;
//   * the board pack's skip link is the first Tab stop and is not covered by the bar;
//   * both demos: Home/End inside a folder menu move focus without firing the page's beat shortcuts (1280 + 375);
//   * mobile (375px): the toggle is visible, the nav is hidden until the toggle opens it, folders expand inline,
//     Escape closes the menu, nothing overflows the viewport horizontally;
//   * short landscape (667x375) on the sticky pages: the expanded bar fits the viewport and scrolls so every top-level
//     control is reachable; without the script the list is ordinary page flow (Usage reachable by scrolling).
// With --shots it also writes screenshots to /tmp/site-nav-shots/. Exit 0 = pass; 1 = a check failed; 3 = no Playwright.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { NAV, PAGES, CURRENT, STICKY } from "./site_nav.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png", ".txt": "text/plain", ".md": "text/markdown" };
const SHOTS = process.argv.includes("--shots") ? "/tmp/site-nav-shots" : null;

async function loadPlaywright() {
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE,
    path.join(process.env.HOME || "", ".claude/skills/gstack/node_modules/playwright/index.mjs")].filter(Boolean);
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
      res.writeHead(200, { "content-type": TYPES[path.extname(file)] || "application/octet-stream" });
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
const failures = [];
const expected = NAV.flatMap((e) => e.items ? e.items : [e]).map((i) => [i.label, i.href]);
const folderCount = NAV.filter((e) => e.items).length;
const check = (ok, what) => { console.log(`${ok ? "OK  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };
const shot = (page, name) => SHOTS ? page.screenshot({ path: path.join(SHOTS, name) }) : Promise.resolve();
const pageOverflow = () => document.documentElement.scrollWidth - window.innerWidth;
const focusedText = () => document.activeElement && document.activeElement.textContent.trim();
const expandedOf = (idx) => document.querySelectorAll(".site-nav-folder-button")[idx].getAttribute("aria-expanded");

for (const [pagePath, file] of Object.entries(PAGES)) {
  const current = CURRENT[pagePath] || pagePath;
  // ---- desktop, script on
  let page = await browser.newPage({ viewport: { width: 1280, height: 800 } });
  const errors = [];
  page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(base + pagePath, { waitUntil: "load" });
  const d = await page.evaluate(() => {
    const bar = document.querySelector(".site-topbar[data-site-nav]");
    const navs = document.querySelectorAll("nav.nav-links");
    const links = [...bar.querySelectorAll("nav a")].map((a) => [a.textContent.trim(), a.getAttribute("href")]);
    const cur = [...bar.querySelectorAll("[aria-current]")].map((a) => a.getAttribute("href"));
    const toggle = bar.querySelector(".site-nav-toggle");
    const btns = [...bar.querySelectorAll(".site-nav-folder-button")];
    return { js: bar.classList.contains("site-nav-js"), navs: navs.length, links, cur,
      toggleHidden: getComputedStyle(toggle).display === "none",
      expanded: btns.map((b) => b.getAttribute("aria-expanded")), haspopup: btns.every((b) => b.getAttribute("aria-haspopup") === "true"),
      menusHidden: [...bar.querySelectorAll(".site-nav-menu")].every((m) => getComputedStyle(m).display === "none"),
      barH: bar.getBoundingClientRect().height };
  });
  check(d.js && d.navs === 1, `${file} desktop: script ran, one primary nav`);
  check(JSON.stringify(d.links) === JSON.stringify(expected), `${file} desktop: IA links ${JSON.stringify(d.links)}`);
  check(d.cur.length === 1 && d.cur[0] === current, `${file} desktop: aria-current ${JSON.stringify(d.cur)} (want ${current})`);
  check(d.toggleHidden && d.haspopup && d.expanded.every((x) => x === "false") && d.menusHidden, `${file} desktop: folders closed, toggle hidden`);
  check(d.barH >= 56 && d.barH <= 64, `${file} desktop: bar height ${d.barH}`);
  // every folder, opened in turn, stays inside the viewport (Astra P2 #1)
  for (let i = 0; i < folderCount; i++) {
    const btn = page.locator(".site-nav-folder-button").nth(i);
    await btn.click();
    const r = await page.evaluate((i) => {
      const f = document.querySelectorAll(".site-nav-folder")[i], m = f.querySelector(".site-nav-menu"), rect = m.getBoundingClientRect();
      return { open: f.querySelector("button").getAttribute("aria-expanded") === "true" && getComputedStyle(m).display !== "none",
        left: Math.round(rect.left), right: Math.round(rect.right), overflow: document.documentElement.scrollWidth - window.innerWidth,
        others: [...document.querySelectorAll(".site-nav-folder-button")].filter((b, j) => j !== i).every((b) => b.getAttribute("aria-expanded") === "false") };
    }, i);
    check(r.open && r.left >= 0 && r.right <= 1280 && r.overflow <= 0 && r.others, `${file} desktop: folder ${i} open inside viewport ${JSON.stringify(r)}`);
    if (SHOTS && pagePath === "/research/") await shot(page, `desktop-research-folder-${i}.png`);
  }
  // the last folder is open now: Escape closes it and returns focus (its button has focus after the click)
  await page.keyboard.press("Escape");
  const afterEsc = await page.evaluate((i) => [document.querySelectorAll(".site-nav-folder-button")[i].getAttribute("aria-expanded"), document.activeElement && document.activeElement.textContent.trim()], folderCount - 1);
  check(afterEsc[0] === "false" && afterEsc[1] === NAV.filter((e) => e.items).pop().label, `${file} desktop: Escape closes and refocuses ${JSON.stringify(afterEsc)}`);
  await page.keyboard.press("ArrowDown");
  const afterArrow = await page.evaluate((i) => [document.querySelectorAll(".site-nav-folder-button")[i].getAttribute("aria-expanded"), document.activeElement && document.activeElement.textContent.trim()], folderCount - 1);
  check(afterArrow[0] === "true" && afterArrow[1] === "RFC", `${file} desktop: ArrowDown opens and focuses first item ${JSON.stringify(afterArrow)}`);
  await page.keyboard.press("End");
  check(await page.evaluate(focusedText) === "EvalBench", `${file} desktop: End focuses the last item`);
  await page.keyboard.press("Home");
  check(await page.evaluate(focusedText) === "RFC", `${file} desktop: Home focuses the first item`);
  await page.keyboard.press("Tab"); await page.keyboard.press("Tab"); await page.keyboard.press("Tab");
  check(await page.evaluate(expandedOf, folderCount - 1) === "false", `${file} desktop: tabbing out closes the folder`);
  await page.locator(".site-nav-folder-button").nth(0).click();
  check(await page.evaluate(expandedOf, 0) === "true", `${file} desktop: folder reopened for the outside-click case`);
  await page.mouse.click(640, 600);
  check(await page.evaluate(() => [...document.querySelectorAll(".site-nav-folder-button")].every((b) => b.getAttribute("aria-expanded") === "false")), `${file} desktop: outside click closes the open folder`);
  if (pagePath === "/rfc/") { // skip link is the first Tab stop and sits above the bar (Astra P2 #2)
    await page.goto(base + pagePath, { waitUntil: "load" });
    await page.keyboard.press("Tab");
    const s = await page.evaluate(() => { const a = document.activeElement, r = a.getBoundingClientRect();
      const hit = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
      return { cls: a.className, text: a.textContent.trim(), covered: !(hit === a || a.contains(hit)), top: Math.round(r.top) }; });
    check(s.cls === "skip-link" && !s.covered && s.top >= 0, `${file} desktop: first Tab focuses the skip link above the bar ${JSON.stringify(s)}`);
    await shot(page, "desktop-rfc-skip-link.png");
  }
  await shot(page, `desktop-${file.replace(/\//g, "_")}.png`);
  check(errors.length === 0, `${file} desktop: no page errors ${JSON.stringify(errors)}`);
  await page.close();

  // ---- desktop, script off: hover path across the gap (Astra P2 #5)
  page = await browser.newPage({ viewport: { width: 1280, height: 800 }, javaScriptEnabled: false });
  await page.goto(base + pagePath, { waitUntil: "load" });
  const b0 = await page.locator(".site-nav-folder-button").nth(0).boundingBox();
  await page.mouse.move(b0.x + b0.width / 2, b0.y + b0.height / 2);
  const hoverOpen = await page.evaluate(() => getComputedStyle(document.querySelector("#site-nav-menu-bigquery")).display !== "none");
  await page.mouse.move(b0.x + b0.width / 2, b0.y + b0.height + 3); // inside the 6px gap
  const gapOpen = await page.evaluate(() => getComputedStyle(document.querySelector("#site-nav-menu-bigquery")).display !== "none");
  const l0 = await page.locator("#site-nav-menu-bigquery a").nth(0).boundingBox();
  await page.mouse.move(l0.x + l0.width / 2, l0.y + l0.height / 2);
  const linkOpen = await page.evaluate(() => { const m = document.querySelector("#site-nav-menu-bigquery"); const a = m.querySelector("a"), r = a.getBoundingClientRect();
    return getComputedStyle(m).display !== "none" && document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2) === a; });
  check(hoverOpen && gapOpen && linkOpen, `${file} desktop no-JS: hover opens, gap keeps open, link reachable (${hoverOpen}/${gapOpen}/${linkOpen})`);
  await page.close();

  // ---- mobile
  page = await browser.newPage({ viewport: { width: 375, height: 740 }, isMobile: true, hasTouch: true });
  await page.goto(base + pagePath, { waitUntil: "load" });
  const m = await page.evaluate(() => ({ toggleVisible: getComputedStyle(document.querySelector(".site-nav-toggle")).display !== "none",
    navHidden: getComputedStyle(document.querySelector(".site-nav")).display === "none",
    overflow: document.documentElement.scrollWidth - window.innerWidth, barRight: Math.round(document.querySelector(".site-topbar").getBoundingClientRect().right) }));
  check(m.toggleVisible && m.navHidden, `${file} mobile: toggle shown, nav collapsed`);
  check(m.overflow <= 0 && m.barRight <= 375, `${file} mobile: no horizontal overflow (page ${m.overflow}px, bar right ${m.barRight}px)`);
  await page.locator(".site-nav-toggle").click();
  check(await page.locator(".site-nav").isVisible() && await page.locator(".site-nav-toggle").getAttribute("aria-expanded") === "true", `${file} mobile: toggle opens the menu`);
  await page.locator(".site-nav-folder-button").nth(0).click();
  const mm = await page.evaluate(() => { const menu = document.querySelector("#site-nav-menu-bigquery"); const r = menu.getBoundingClientRect();
    return { visible: getComputedStyle(menu).display !== "none", inside: r.right <= window.innerWidth && r.left >= 0,
      overflow: document.documentElement.scrollWidth - window.innerWidth }; });
  check(mm.visible && mm.inside && mm.overflow <= 0, `${file} mobile: folder expands inline ${JSON.stringify(mm)}`);
  if (SHOTS && pagePath === "/research/") await shot(page, "mobile-research-open.png");
  await page.keyboard.press("Escape"); // closes the folder
  await page.keyboard.press("Escape"); // closes the menu
  check(await page.evaluate(() => getComputedStyle(document.querySelector(".site-nav")).display === "none"), `${file} mobile: Escape twice collapses the menu`);
  await shot(page, `mobile-${file.replace(/\//g, "_")}.png`);
  await page.close();

  // ---- demos: menu Home/End must not fire the page's beat shortcuts (Astra P2 #3)
  if (pagePath === "/rfc/demo/" || pagePath === "/rfc/full-demo/") {
    for (const [w, h, mob] of [[1280, 800, false], [375, 740, true]]) {
      page = await browser.newPage({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
      await page.goto(base + pagePath + "#beat=3", { waitUntil: "load" });
      await page.waitForFunction(() => location.hash === "#beat=3");
      if (mob) await page.locator(".site-nav-toggle").click();
      const builds = page.locator(".site-nav-folder-button").nth(folderCount - 1);
      await builds.focus();
      await page.keyboard.press("ArrowUp"); // opens Builds and focuses EvalBench
      const before = await page.evaluate(focusedText);
      await page.keyboard.press("Home");
      const afterHome = await page.evaluate(() => [document.activeElement.textContent.trim(), location.hash]);
      await page.keyboard.press("End");
      const afterEnd = await page.evaluate(() => [document.activeElement.textContent.trim(), location.hash]);
      check(before === "EvalBench" && afterHome[0] === "RFC" && afterHome[1] === "#beat=3" && afterEnd[0] === "EvalBench" && afterEnd[1] === "#beat=3",
        `${file} ${w}px: menu Home/End keep #beat=3 ${JSON.stringify([before, afterHome, afterEnd])}`);
      await page.close();
    }
  }

  // ---- short landscape on the sticky pages (Astra P2 #4)
  if (STICKY.has(pagePath)) {
    page = await browser.newPage({ viewport: { width: 667, height: 375 }, isMobile: true, hasTouch: true });
    await page.goto(base + pagePath, { waitUntil: "load" });
    await page.evaluate(() => window.scrollTo(0, 600));
    await page.locator(".site-nav-toggle").click();
    await page.locator(".site-nav-folder-button").nth(0).click();
    const s = await page.evaluate(() => { const bar = document.querySelector(".site-topbar"); const r = bar.getBoundingClientRect();
      const last = document.querySelector(".site-nav-folder:last-child > .site-nav-folder-button"); last.scrollIntoView({ block: "nearest" });
      const lr = last.getBoundingClientRect();
      return { top: Math.round(r.top), height: Math.round(r.height), sticky: getComputedStyle(bar).position, lastTop: Math.round(lr.top), lastBottom: Math.round(lr.bottom), scrollY: window.scrollY }; });
    check(s.sticky === "sticky" && s.top === 0 && s.height <= 375 && s.lastTop >= 0 && s.lastBottom <= 375, `${file} 667x375: expanded pinned bar fits and scrolls to Builds ${JSON.stringify(s)}`);
    await shot(page, `short-${file.replace(/\//g, "_")}.png`);
    await page.close();
    page = await browser.newPage({ viewport: { width: 667, height: 375 }, isMobile: true, hasTouch: true, javaScriptEnabled: false });
    await page.goto(base + pagePath, { waitUntil: "load" });
    const n = await page.evaluate(() => { const bar = document.querySelector(".site-topbar");
      document.documentElement.style.scrollBehavior = "auto"; // the RFC pages scroll smoothly; measure after an instant scroll
      const usage = [...bar.querySelectorAll("a")].find((a) => a.textContent.trim() === "Usage"); usage.scrollIntoView({ block: "center" });
      const ur = usage.getBoundingClientRect();
      const h1 = document.querySelector("h1"); h1.scrollIntoView({ block: "center" }); const hr = h1.getBoundingClientRect();
      const hit = document.elementFromPoint(Math.min(hr.left + 10, 660), hr.top + 5);
      return { position: getComputedStyle(bar).position, usageTop: Math.round(ur.top), usageBottom: Math.round(ur.bottom),
        h1Top: Math.round(hr.top), h1Uncovered: !!hit && !hit.closest(".site-topbar") }; });
    check(n.position !== "sticky" && n.usageTop >= 0 && n.usageBottom <= 375 && n.h1Top >= 0 && n.h1Uncovered, `${file} 667x375 no-JS: list is page flow, Usage and content reachable ${JSON.stringify(n)}`);
    await page.close();
  }
}
await browser.close();
server.close();
console.log(failures.length ? `${failures.length} check(s) failed` : `all site-nav checks pass over ${Object.keys(PAGES).length} pages`);
process.exit(failures.length ? 1 : 0);
