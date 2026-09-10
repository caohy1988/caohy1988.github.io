// Offline browser check for the shared site navigation (research/site-nav-spec.md acceptance list).
// Serves the repository root on a loopback port, drives headless Chromium over every page in tools/site_nav.mjs and checks:
//   * the block is present, the primary nav exists once, every IA link is present with its href;
//   * exactly one link carries aria-current="page" and it is the page's own (or /rfc/ for the demos);
//   * desktop (1280px): folders start closed; click opens one and sets aria-expanded; a second folder closes the first;
//     Escape closes and returns focus to the button; ArrowDown opens and focuses the first item; the toggle is hidden;
//   * mobile (375px): the toggle is visible, the nav is hidden until the toggle opens it, folders expand inline,
//     Escape closes the menu, nothing overflows the viewport horizontally.
// With --shots it also writes screenshots to /tmp/site-nav-shots/. Exit 0 = pass; 1 = a check failed; 3 = no Playwright.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";
import { NAV, PAGES, CURRENT } from "./site_nav.mjs";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".svg": "image/svg+xml", ".png": "image/png" };
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
const check = (ok, what) => { console.log(`${ok ? "OK  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };

for (const [pagePath, file] of Object.entries(PAGES)) {
  const current = CURRENT[pagePath] || pagePath;
  // desktop
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
  const btn1 = page.locator(".site-nav-folder-button").nth(0), btn2 = page.locator(".site-nav-folder-button").nth(1);
  await btn1.click();
  check(await btn1.getAttribute("aria-expanded") === "true" && await page.locator("#site-nav-menu-bigquery").isVisible(), `${file} desktop: click opens BigQuery`);
  if (SHOTS && pagePath === "/research/") await page.screenshot({ path: path.join(SHOTS, "desktop-research-open.png") });
  await btn2.click();
  check(await btn1.getAttribute("aria-expanded") === "false" && await btn2.getAttribute("aria-expanded") === "true", `${file} desktop: opening Builds closes BigQuery`);
  await page.keyboard.press("Escape");
  const afterEsc = await page.evaluate(() => [document.querySelector(".site-nav-folder-button[aria-controls=site-nav-menu-builds]").getAttribute("aria-expanded"), document.activeElement && document.activeElement.textContent.trim()]);
  check(afterEsc[0] === "false" && afterEsc[1] === "Builds", `${file} desktop: Escape closes and refocuses ${JSON.stringify(afterEsc)}`);
  await page.keyboard.press("ArrowDown");
  const afterArrow = await page.evaluate(() => [document.querySelector(".site-nav-folder-button[aria-controls=site-nav-menu-builds]").getAttribute("aria-expanded"), document.activeElement && document.activeElement.textContent.trim()]);
  check(afterArrow[0] === "true" && afterArrow[1] === "RFC", `${file} desktop: ArrowDown opens and focuses first item ${JSON.stringify(afterArrow)}`);
  await page.keyboard.press("Tab"); await page.keyboard.press("Tab"); await page.keyboard.press("Tab");
  check(await btn2.getAttribute("aria-expanded") === "false", `${file} desktop: tabbing out closes the folder`);
  await page.mouse.click(640, 600);
  check(await page.evaluate(() => [...document.querySelectorAll(".site-nav-folder-button")].every((b) => b.getAttribute("aria-expanded") === "false")), `${file} desktop: outside click leaves every folder closed`);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `desktop-${file.replace(/\//g, "_")}.png`) });
  check(errors.length === 0, `${file} desktop: no page errors ${JSON.stringify(errors)}`);
  await page.close();

  // mobile
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
  if (SHOTS && pagePath === "/research/") await page.screenshot({ path: path.join(SHOTS, "mobile-research-open.png") });
  await page.keyboard.press("Escape"); // closes the folder
  await page.keyboard.press("Escape"); // closes the menu
  check(await page.evaluate(() => getComputedStyle(document.querySelector(".site-nav")).display === "none"), `${file} mobile: Escape twice collapses the menu`);
  if (SHOTS) await page.screenshot({ path: path.join(SHOTS, `mobile-${file.replace(/\//g, "_")}.png`) });
  await page.close();
}
await browser.close();
server.close();
console.log(failures.length ? `${failures.length} check(s) failed` : `all site-nav checks pass over ${Object.keys(PAGES).length} pages`);
process.exit(failures.length ? 1 : 0);
