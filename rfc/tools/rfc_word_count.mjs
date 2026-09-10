// Word counter for the two RFC pages (rfc/rfc-shorten-spec.md): document.body.innerText in headless Chromium,
// split on whitespace, once as rendered and once with every <details> opened. Prints one JSON object keyed by the
// paths given. Exit 0 = counted; 3 = Playwright could not be resolved (the caller decides whether to skip).
import path from "node:path";
import { pathToFileURL } from "node:url";

async function loadPlaywright() {
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE,
    path.join(process.env.HOME || "", ".claude/skills/gstack/node_modules/playwright/index.mjs")].filter(Boolean);
  for (const c of candidates) {
    try { return await import(c.startsWith("/") ? pathToFileURL(c).href : c); } catch (e) { /* try the next one */ }
  }
  return null;
}

const pw = await loadPlaywright();
if (!pw) { console.error("playwright unavailable"); process.exit(3); }
const browser = await pw.chromium.launch();
const page = await browser.newPage();
const result = {};
for (const f of process.argv.slice(2)) {
  await page.goto(pathToFileURL(path.resolve(f)).href, { waitUntil: "load" });
  result[f] = await page.evaluate(() => {
    const words = (t) => (t.match(/\S+/g) || []).length;
    const rendered = words(document.body.innerText);
    document.querySelectorAll("details").forEach((d) => { d.open = true; });
    return { rendered, open: words(document.body.innerText) };
  });
}
await browser.close();
console.log(JSON.stringify(result, null, 2));
