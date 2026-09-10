// Leadership-skim gates for the /rfc/ landing page (rfc/rfc-exec-skim-spec.md §4, G1/G3/G4): headless Chromium,
// document.body.innerText as rendered (folds closed). Prints one JSON object; exit 0 = all gates hold, 1 = a gate
// failed, 3 = Playwright could not be resolved (the caller decides whether to skip).
import path from "node:path";
import { pathToFileURL } from "node:url";

const PAGE = process.argv[2] || "rfc/index.html";
const RENDERED_MAX = 950, WINDOW = 450, WPM = 230, MINUTES_MAX = 5;
const TOKENS = ["proposed", "invented", "Knowledge Publications", "pilot", "2026-09-19"];

async function loadPlaywright() {
  const candidates = ["playwright", process.env.PLAYWRIGHT_MODULE,
    path.join(process.env.HOME || "", ".claude/skills/gstack/node_modules/playwright/index.mjs")].filter(Boolean);
  for (const c of candidates) { try { return await import(c.startsWith("/") ? pathToFileURL(c).href : c); } catch (e) { /* next */ } }
  return null;
}
const pw = await loadPlaywright();
if (!pw) { console.error("playwright unavailable"); process.exit(3); }
const browser = await pw.chromium.launch();
const page = await browser.newPage();
await page.goto(pathToFileURL(path.resolve(PAGE)).href, { waitUntil: "load" });
const text = await page.evaluate(() => document.body.innerText);
await browser.close();
const words = text.match(/\S+/g) || [];
const head = words.slice(0, WINDOW).join(" ").toLowerCase();
const missing = TOKENS.filter((t) => !head.includes(t.toLowerCase())); // case-insensitive: "Proposed:" counts
const minutes = Math.round((words.length / WPM) * 100) / 100;
const result = { page: PAGE, rendered: words.length, renderedMax: RENDERED_MAX, window: WINDOW, missingInWindow: missing, minutes, minutesMax: MINUTES_MAX };
result.ok = words.length <= RENDERED_MAX && missing.length === 0 && minutes <= MINUTES_MAX;
console.log(JSON.stringify(result, null, 2));
process.exit(result.ok ? 0 : 1);
