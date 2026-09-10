// Offline browser check for the five BigQuery product boards (research/board-select-copy-spec.md G2).
// Serves the repository root on a loopback port and drives headless Chromium over every board at 1280px and 375px.
// External links are stubbed so "the source opened" can be observed without the network.
// Also covers Astra's PR 68 P2s: focused controls stay above the fixed tray (1280x740, 375x740) and the manual-copy panel stays accurate after edits.
// --shots writes screenshots to /tmp/board-shots/. Exit 0 = pass; 1 = a check failed; 3 = Playwright unavailable.
import http from "node:http";
import fs from "node:fs";
import path from "node:path";
import { fileURLToPath, pathToFileURL } from "node:url";

const REPO = path.resolve(path.dirname(fileURLToPath(import.meta.url)), "..");
const BOARDS = ["conversational-analytics", "bigquery-search", "bigquery-graph", "bigquery-lakehouse", "bqml-ai-operators"];
const TYPES = { ".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "text/javascript", ".mjs": "text/javascript", ".json": "application/json" };
const SHOTS = process.argv.includes("--shots") ? "/tmp/board-shots" : null;

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
const check = (ok, what) => { console.log(`${ok ? "OK  " : "FAIL"} ${what}`); if (!ok) failures.push(what); };
const stubExternal = (context) => context.route((url) => !String(url).startsWith(base), (route) => route.fulfill({ status: 200, contentType: "text/html", body: "<title>stub</title>stub" }));
const channelOf = (e) => { // mirror of assets/board.js
  const src = String(e.source || "").toLowerCase(), href = String(e.href || "").toLowerCase();
  if (e.kind === "video" || src.includes("youtube") || href.includes("youtube.com") || href.includes("youtu.be")) return "video";
  if (src.includes("medium") || href.includes("medium.com")) return "medium";
  if (e.kind === "docs" || src.includes("google cloud") || src.includes("google codelabs") || href.includes("cloud.google.com/") || href.includes("docs.cloud.google.com/") || href.includes("codelabs.developers.google.com/")) return "google-cloud";
  return "community";
};
const readClipboard = () => navigator.clipboard.read().then(async (items) => {
  const out = {};
  for (const item of items) for (const t of item.types) out[t] = await (await item.getType(t)).text();
  return out;
});

for (const slug of BOARDS) {
  const url = `${base}/research/${slug}/`;
  const file = `research/${slug}/index.html`;
  const html = fs.readFileSync(path.join(REPO, file), "utf8");
  const data = JSON.parse(fs.readFileSync(path.join(REPO, `research/${slug}/entries.json`), "utf8"));
  const entries = data.entries;
  const counts = { video: 0, medium: 0, "google-cloud": 0, community: 0 };
  entries.forEach((e) => { counts[channelOf(e)] += 1; });
  // static contract
  check(!/<script(?![^>]*\ssrc=)[^>]*>/.test(html) && html.includes('src="../../assets/board.js"') && html.includes('src="../../assets/board-format.js"') && html.includes('href="../../assets/board.css"'),
    `${file}: no inline script; shared board assets included`);
  check(html.includes(`data-board="${slug}"`) && html.includes(`data-entries="/research/${slug}/entries.json"`) && html.includes(`data-board-url="https://caohy1988.github.io/research/${slug}/"`), `${file}: main carries data-board, data-entries, data-board-url`);
  check(!/execCommand/.test(fs.readFileSync(path.join(REPO, "assets/board.js"), "utf8")), "assets/board.js: no execCommand");

  // ---- desktop
  let context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  await stubExternal(context);
  let page = await context.newPage();
  const errors = []; page.on("pageerror", (e) => errors.push(String(e)));
  await page.goto(url, { waitUntil: "load" });
  await page.waitForSelector(".card");
  const d = await page.evaluate(() => ({
    cards: document.querySelectorAll(".card").length,
    filters: [...document.querySelectorAll("#filters button")].map((b) => [b.firstChild.textContent, Number(b.querySelector(".count").textContent)]),
    firstHref: document.querySelector(".card h2 a").getAttribute("href"), firstTarget: document.querySelector(".card h2 a").getAttribute("target"),
    firstId: document.querySelector(".card").getAttribute("data-id"), nestedBox: !!document.querySelector("a input"),
    trayHidden: document.getElementById("board-tray").hidden, meta: document.getElementById("meta").textContent,
  }));
  const sorted = entries.slice().sort((a, b) => (b.date || "").localeCompare(a.date || "") || String(b.id).localeCompare(String(a.id)));
  check(d.cards === entries.length && d.meta.startsWith(`${entries.length} resources`), `${slug}: ${d.cards} cards rendered = entries.json`);
  check(JSON.stringify(d.filters) === JSON.stringify([["All", entries.length], ["Video", counts.video], ["Medium", counts.medium], ["Google Cloud", counts["google-cloud"]], ["Community", counts.community]]), `${slug}: four filters with counts ${JSON.stringify(d.filters)}`);
  check(d.firstHref === sorted[0].href && d.firstTarget === "_blank" && d.firstId === sorted[0].id && !d.nestedBox && d.trayHidden, `${slug}: newest card first, title links to source in a new tab, checkbox not nested in a link, tray hidden`);
  // clicking the body opens the source; clicking the checkbox opens nothing
  const bodyBox = await page.locator(".card:first-child .card-body p").boundingBox(); // the stretched title link covers the body, so click by position
  const [popup] = await Promise.all([context.waitForEvent("page", { timeout: 5000 }).catch(() => null), page.mouse.click(bodyBox.x + 12, bodyBox.y + bodyBox.height / 2)]);
  check(popup && popup.url() === sorted[0].href, `${slug}: click on the card body opens the source (${popup && popup.url()})`);
  if (popup) await popup.close();
  let opened = 0; context.on("page", () => { opened += 1; });
  await page.click(".card:first-child .card-select");
  await page.waitForTimeout(300);
  const afterBox = await page.evaluate(() => ({ checked: document.querySelector(".card:first-child input").checked, sel: document.querySelector(".card:first-child").getAttribute("data-selected"), tray: !document.getElementById("board-tray").hidden, count: document.getElementById("board-tray-count").textContent.trim(), status: document.getElementById("board-status").textContent }));
  check(opened === 0 && afterBox.checked && afterBox.sel === "true" && afterBox.tray && afterBox.count.startsWith("1 selected"), `${slug}: checkbox selects without opening a page ${JSON.stringify(afterBox)}`);
  // keyboard: Space on a focused checkbox toggles the second card
  await page.focus(".card:nth-child(2) input"); await page.keyboard.press("Space");
  check(await page.evaluate(() => document.querySelector(".card:nth-child(2) input").checked), `${slug}: Space toggles a focused checkbox`);
  await page.keyboard.press("Space");
  // select visible under a filter, then switch filter: selection kept, hidden count reported
  const filterA = ["video", "medium", "google-cloud", "community"].find((f) => counts[f] > 0);
  const filterB = ["community", "google-cloud", "medium", "video"].find((f) => counts[f] > 0 && f !== filterA);
  await page.click(`#filters button[data-filter="${filterA}"]`);
  await page.click("#board-select-visible");
  const selA = await page.evaluate(() => ({ count: document.getElementById("board-tray-count").textContent.trim(), boxes: [...document.querySelectorAll(".card input")].every((b) => b.checked), all: document.getElementById("board-select-visible").checked }));
  const expectA = counts[filterA] + (channelOf(sorted[0]) === filterA ? 0 : 1);
  check(selA.count.startsWith(`${expectA} selected`) && selA.boxes && selA.all, `${slug}: Select visible under ${filterA} selects ${expectA} ${JSON.stringify(selA)}`);
  await page.click(`#filters button[data-filter="${filterB}"]`);
  const selB = await page.evaluate(() => ({ count: document.getElementById("board-tray-count").textContent.replace(/\s+/g, " ").trim(), url: location.search, ind: document.getElementById("board-select-visible").indeterminate, chk: document.getElementById("board-select-visible").checked }));
  const hiddenB = expectA - (channelOf(sorted[0]) === filterB ? 1 : 0);
  check(selB.count === `${expectA} selected · ${hiddenB} hidden by filter` && selB.url === `?type=${filterB}` && !selB.chk, `${slug}: filter change keeps selection and reports hidden (${selB.count})`);
  // reload restores the selection
  await page.reload({ waitUntil: "load" }); await page.waitForSelector(".card");
  const afterReload = await page.evaluate(() => ({ count: document.getElementById("board-tray-count").textContent.replace(/\s+/g, " ").trim(), url: location.search }));
  check(afterReload.count.startsWith(`${expectA} selected`) && afterReload.url === `?type=${filterB}`, `${slug}: reload restores selection and ?type= (${afterReload.count})`);
  // copy for Google Docs: both flavors on the clipboard
  await page.click("#board-copy-rich");
  await page.waitForFunction(() => /Copied|blocked/.test(document.getElementById("board-status").textContent));
  const status = await page.evaluate(() => document.getElementById("board-status").textContent);
  const clip = await page.evaluate(readClipboard);
  const firstSel = sorted.find((e) => channelOf(e) === filterA || e.id === sorted[0].id);
  check(status === `Copied ${expectA} cards for Google Docs.` && clip["text/html"] && clip["text/plain"], `${slug}: rich copy status and both flavors present (${status}; ${Object.keys(clip)})`);
  check((clip["text/html"] || "").includes("<ol>") && (clip["text/html"] || "").includes(`<h3>${data.title.replace(/&/g, "&amp;")}</h3>`) && (clip["text/html"] || "").includes(`href="${firstSel.href}"`) && (clip["text/html"] || "").includes(`Board: <a href="https://caohy1988.github.io/research/${slug}/">`),
    `${slug}: html flavor has heading, numbered list, source link, board link`);
  check((clip["text/plain"] || "").startsWith(`${data.title}\nSelected product updates\nPrepared `) && (clip["text/plain"] || "").includes(`\n   ${firstSel.href}\n`) && (clip["text/plain"] || "").trim().endsWith(`Board: https://caohy1988.github.io/research/${slug}/`) && !/<[a-z]+>/.test(clip["text/plain"] || ""),
    `${slug}: plain flavor has header, url lines, board line, no tags`);
  check((clip["text/plain"] || "").split("\n").filter((l) => /^\d+\. /.test(l)).length === expectA, `${slug}: plain flavor lists exactly ${expectA} items`);
  // review panel: remove one card
  await page.click("#board-review-toggle");
  await page.click("#board-review-list li:first-child button");
  const afterRemove = await page.evaluate(() => ({ count: document.getElementById("board-tray-count").textContent.replace(/\s+/g, " ").trim(), lines: document.getElementById("board-review-text").value.split("\n").filter((l) => /^\d+\. /.test(l)).length, open: !document.getElementById("board-review").hidden }));
  check(afterRemove.count.startsWith(`${expectA - 1} selected`) && afterRemove.lines === expectA - 1 && afterRemove.open, `${slug}: review panel removes a card and updates the text (${afterRemove.count})`);
  if (SHOTS && slug === BOARDS[0]) { await page.click('#filters button[data-filter="all"]'); await page.screenshot({ path: path.join(SHOTS, "desktop-review.png") }); }
  await page.click("#board-clear");
  check(await page.evaluate(() => document.getElementById("board-tray").hidden && ![...document.querySelectorAll(".card input")].some((b) => b.checked) && sessionStorage.getItem("board-select:" + document.querySelector("main").dataset.board) === "[]"), `${slug}: Clear empties selection and storage`);
  check(errors.length === 0, `${slug}: no page errors ${JSON.stringify(errors)}`);
  await context.close();

  // ---- rich copy blocked: review panel opens, plain copy works
  context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await context.grantPermissions(["clipboard-read", "clipboard-write"], { origin: base });
  await stubExternal(context);
  await context.addInitScript(() => { navigator.clipboard.write = () => Promise.reject(new Error("blocked")); });
  page = await context.newPage();
  await page.goto(url, { waitUntil: "load" }); await page.waitForSelector(".card");
  await page.click(".card:first-child .card-select");
  await page.click("#board-copy-rich");
  await page.waitForFunction(() => /blocked/.test(document.getElementById("board-status").textContent));
  const blocked = await page.evaluate(() => ({ open: !document.getElementById("board-review").hidden, status: document.getElementById("board-status").textContent, text: document.getElementById("board-review-text").value }));
  check(blocked.open && blocked.status.startsWith("Rich copy was blocked") && blocked.text.includes(sorted[0].title.replace(/\s+/g, " ").trim()), `${slug}: blocked rich copy opens the review panel (${blocked.status})`);
  await page.click("#board-copy-plain");
  await page.waitForFunction(() => /plain text/.test(document.getElementById("board-status").textContent));
  const plain = await page.evaluate(() => navigator.clipboard.readText());
  check(plain === blocked.text && plain.includes(`\n   ${sorted[0].href}\n`), `${slug}: Copy plain text writes the review text`);
  if (SHOTS && slug === BOARDS[0]) await page.screenshot({ path: path.join(SHOTS, "desktop-blocked.png") });
  await context.close();

  // ---- keyboard focus stays above the fixed tray (Astra P2 #1): 1280x740 Space + Tab x3, and 375x740 first Tab after selecting
  const focusBox = () => { const el = document.activeElement, r = el.getBoundingClientRect(), t = document.getElementById("board-tray").getBoundingClientRect();
    return { tag: el.tagName, text: (el.textContent || el.getAttribute("aria-label") || "").trim().slice(0, 40), top: Math.round(r.top), bottom: Math.round(r.bottom), trayTop: Math.round(t.top), trayH: Math.round(t.height), inner: innerHeight }; };
  for (const [w, h, mob] of [[1280, 740, false], [375, 740, true]]) {
    context = await browser.newContext({ viewport: { width: w, height: h }, isMobile: mob, hasTouch: mob });
    await stubExternal(context);
    page = await context.newPage();
    await page.goto(url, { waitUntil: "load" }); await page.waitForSelector(".card");
    await page.focus(".card:first-child input"); await page.keyboard.press("Space");
    const presses = mob ? 1 : 3;
    for (let i = 0; i < presses; i++) await page.keyboard.press("Tab");
    await page.waitForTimeout(150);
    const f = await page.evaluate(focusBox);
    check(f.top >= 0 && f.bottom <= f.trayTop && f.trayH > 0, `${slug} ${w}x${h}: after Space + Tab x${presses} the focused ${f.tag} sits above the tray ${JSON.stringify(f)}`);
    // keep tabbing through a few more cards: every focused control stays visible
    let allVisible = true, last = null;
    for (let i = 0; i < 8; i++) { await page.keyboard.press("Tab"); await page.waitForTimeout(60); last = await page.evaluate(focusBox); if (!(last.top >= 0 && last.bottom <= last.trayTop)) { allVisible = false; break; } }
    check(allVisible, `${slug} ${w}x${h}: eight more Tabs keep focus above the tray ${JSON.stringify(last)}`);
    const pad = await page.evaluate(() => ({ sp: document.documentElement.style.scrollPaddingBottom, mp: parseInt(getComputedStyle(document.querySelector("main")).paddingBottom, 10), trayH: Math.round(document.getElementById("board-tray").getBoundingClientRect().height) }));
    check(parseInt(pad.sp, 10) >= pad.trayH && pad.mp >= pad.trayH, `${slug} ${w}x${h}: scroll-padding and reserved space match the measured tray height ${JSON.stringify(pad)}`);
    if (SHOTS && slug === BOARDS[0]) await page.screenshot({ path: path.join(SHOTS, `focus-${w}.png`) });
    await context.close();
  }

  // ---- both clipboard writes denied, then the selection is edited (Astra P2 #2)
  context = await browser.newContext({ viewport: { width: 1280, height: 900 } });
  await stubExternal(context);
  await context.addInitScript(() => { navigator.clipboard.write = () => Promise.reject(new Error("blocked")); navigator.clipboard.writeText = () => Promise.reject(new Error("blocked")); });
  page = await context.newPage();
  await page.goto(url, { waitUntil: "load" }); await page.waitForSelector(".card");
  const manualState = () => { const t = document.getElementById("board-review-text");
    return { focused: document.activeElement === t, full: t.selectionStart === 0 && t.selectionEnd === t.value.length && t.value.length > 0, items: t.value.split("\n").filter((l) => /^\d+\. /.test(l)).length,
      hint: document.getElementById("board-review-hint").textContent, selectBtn: !document.getElementById("board-review-select").hidden, active: document.activeElement.tagName + (document.activeElement.id ? "#" + document.activeElement.id : "") }; };
  await page.click(".card:first-child .card-select");
  await page.click("#board-copy-plain");
  await page.waitForFunction(() => /blocked/.test(document.getElementById("board-status").textContent));
  let ms = await page.evaluate(manualState);
  check(ms.focused && ms.full && ms.items === 1 && /is selected/.test(ms.hint) && ms.selectBtn, `${slug}: both writes denied -> textarea focused and fully selected ${JSON.stringify(ms)}`);
  await page.click(".card:nth-child(2) .card-select");
  ms = await page.evaluate(manualState);
  check(!ms.focused && ms.items === 2 && /no longer selected/.test(ms.hint) && ms.selectBtn && ms.active === "INPUT", `${slug}: selecting another card updates the output, says it is no longer selected, leaves focus on the checkbox ${JSON.stringify(ms)}`);
  await page.click("#board-review-select");
  ms = await page.evaluate(manualState);
  check(ms.focused && ms.full && ms.items === 2 && /is selected/.test(ms.hint), `${slug}: Select all text re-selects the refreshed output ${JSON.stringify(ms)}`);
  await page.click("#board-review-list li:first-child button");
  ms = await page.evaluate(manualState);
  check(ms.focused && ms.full && ms.items === 1 && /is selected/.test(ms.hint), `${slug}: Remove inside Review re-selects the refreshed output and keeps focus in the panel ${JSON.stringify(ms)}`);
  await page.click("#board-review-list li:first-child button");
  const closed = await page.evaluate(() => ({ hidden: document.getElementById("board-review").hidden, tray: document.getElementById("board-tray").hidden, sel: sessionStorage.getItem("board-select:" + document.querySelector("main").dataset.board) }));
  check(closed.hidden && closed.tray && closed.sel === "[]", `${slug}: removing the last card closes the panel and the tray ${JSON.stringify(closed)}`);
  // a later successful plain copy clears manual mode
  await page.evaluate(() => { navigator.clipboard.writeText = (t) => Promise.resolve(); });
  await page.click(".card:first-child .card-select"); await page.click("#board-copy-plain");
  await page.waitForFunction(() => /as plain text/.test(document.getElementById("board-status").textContent));
  await page.click("#board-review-toggle");
  ms = await page.evaluate(manualState);
  check(!ms.selectBtn && /plain-text version/.test(ms.hint), `${slug}: after a successful copy the panel drops the manual-copy state ${JSON.stringify(ms)}`);
  await context.close();

  // ---- mobile
  context = await browser.newContext({ viewport: { width: 375, height: 740 }, isMobile: true, hasTouch: true });
  await stubExternal(context);
  page = await context.newPage();
  await page.goto(url, { waitUntil: "load" }); await page.waitForSelector(".card");
  await page.tap(".card:first-child .card-select");
  const m = await page.evaluate(() => { const t = document.getElementById("board-tray"), r = t.getBoundingClientRect();
    return { tray: !t.hidden, right: Math.round(r.right), bottom: Math.round(r.bottom), overflow: document.documentElement.scrollWidth - window.innerWidth, checked: document.querySelector(".card:first-child input").checked }; });
  check(m.tray && m.checked && m.right <= 375 && m.bottom <= 740 && m.overflow <= 0, `${slug} mobile: tap selects, tray fits, no horizontal overflow ${JSON.stringify(m)}`);
  if (SHOTS && slug === BOARDS[0]) await page.screenshot({ path: path.join(SHOTS, "mobile-selected.png") });
  await context.close();
}
await browser.close(); server.close();
console.log(failures.length ? `${failures.length} check(s) failed` : `all board checks pass over ${BOARDS.length} boards`);
process.exit(failures.length ? 1 : 0);
