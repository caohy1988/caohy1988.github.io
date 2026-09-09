// Offline browser regression for the /rfc/ restructure (PR 62, Astra P2 #1-#3).
// Serves the repository root on a loopback port with node's http module, drives headless Chromium and checks:
//   * the retired board-pack and bq-vp addresses forward to /rfc/ keeping the section fragment;
//   * the old technical RFC's bookmarks on /rfc/ forward to /rfc/detailed-rfc/ keeping the fragment;
//   * the landing page's own anchors stay on /rfc/;
//   * both demos carry the Detailed RFC nav item.
// Exit 0 = all routes behave; 1 = a route failed; 3 = Playwright could not be resolved (caller decides whether to skip).
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..", "..");
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json", ".md": "text/markdown", ".svg": "image/svg+xml", ".png": "image/png" };

async function loadPlaywright() {
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE,
    path.join(process.env.HOME || "", ".claude/skills/gstack/node_modules/playwright/index.mjs")].filter(Boolean);
  for (const c of candidates) {
    try { return await import(c.startsWith("/") ? pathToFileURL(c).href : c); } catch (e) { /* try the next one */ }
  }
  return null;
}

function serve() {
  return new Promise((resolve) => {
    const server = http.createServer((req, res) => {
      let p = decodeURIComponent(new URL(req.url, "http://x").pathname);
      let file = path.join(REPO, p);
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
const page = await browser.newPage();
const failures = [];
const settle = async (from, to) => {
  await page.goto("about:blank");  // a fresh document per route: a bookmark is a load, not a same-page hash change
  await page.goto(base + from, { waitUntil: "load" });
  await page.waitForURL(base + to, { timeout: 5000 }).catch(() => {});
  await page.waitForLoadState("load");
  return page.url().slice(base.length);
};
const expectRoute = async (from, to, mustScroll = true) => {
  const got = await settle(from, to);
  const hash = to.split("#")[1];
  const target = hash ? await page.evaluate((h) => !!document.getElementById(h), hash) : true;
  // the detailed RFC scrolls smoothly (html{scroll-behavior:smooth}); give the animation a moment to leave the top
  let scrollY = 0;
  for (let i = 0; i < 20 && scrollY === 0; i++) { scrollY = await page.evaluate(() => window.scrollY); if (scrollY === 0) await page.waitForTimeout(100); }
  const ok = got === to && target && (!mustScroll || !hash || scrollY > 0);
  console.log(`${ok ? "OK  " : "FAIL"} ${from} -> ${got} (target ${target}, scrollY ${scrollY})`);
  if (!ok) failures.push(from);
};
await expectRoute("/rfc/board-pack/index.html#sep19-envelope", "/rfc/#sep19-envelope");
await expectRoute("/rfc/board-pack/#sep19-envelope", "/rfc/#sep19-envelope");
await expectRoute("/rfc/board-pack/", "/rfc/");
await expectRoute("/rfc/bq-vp/#sep19-envelope", "/rfc/#sep19-envelope");
await expectRoute("/rfc/bq-vp/", "/rfc/");
for (const h of ["current-evidence", "architecture", "repro", "summary"]) await expectRoute(`/rfc/#${h}`, `/rfc/detailed-rfc/#${h}`);
await expectRoute("/rfc/#sep19-envelope", "/rfc/#sep19-envelope");
await expectRoute("/rfc/#story-title", "/rfc/#story-title", false);
await expectRoute("/rfc/", "/rfc/");
for (const demo of ["/rfc/demo/", "/rfc/full-demo/"]) {
  await page.goto(base + demo, { waitUntil: "load" });
  const nav = await page.evaluate(() => [...document.querySelectorAll("nav.nav-links a")].map((a) => [a.textContent.trim(), a.getAttribute("href")]));
  const ok = nav.some(([t, h]) => t === "Detailed RFC" && h === "/rfc/detailed-rfc/") && nav.some(([t, h]) => t === "RFC" && h === "/rfc/");
  console.log(`${ok ? "OK  " : "FAIL"} ${demo} nav ${JSON.stringify(nav)}`);
  if (!ok) failures.push(demo + " nav");
}
await browser.close();
server.close();
console.log(failures.length ? `${failures.length} route(s) failed` : "all routes behave");
process.exit(failures.length ? 1 : 0);
