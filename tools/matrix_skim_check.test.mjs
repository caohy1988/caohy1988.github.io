// node --test tools/matrix_skim_check.test.mjs  (PLAN_v2 §8 S1/S2/S3/S6 in headless Chromium; needs Playwright)
// S1 counts readable words: fully clipped accessibility-only text is excluded, thresholds unchanged (900 / 4.0).
import test from "node:test";
import assert from "node:assert/strict";
import { runSkimCheck, evaluateGates, measureReadableHtml, PlaywrightMissing, S1_MAX_WORDS, S1_MAX_MINUTES, S3_TOKENS } from "./matrix_skim_check.mjs";

let report = null;
try {
  report = await runSkimCheck({ engines: ["chromium"] });
} catch (e) {
  if (!(e instanceof PlaywrightMissing)) throw e;
  test("Playwright and Chromium are available for the skim check", () => assert.fail(e.message));
}

if (report) {
  const [{ viewports, gates }] = report.results;
  const by = Object.fromEntries(viewports.map((v) => [v.viewport, v]));
  const s1Values = gates.S1.values.map((v) => `${v.viewport} ${v.words}w/${v.minutes}min`).join(", ");

  test(`S1 reading load ≤ ${S1_MAX_WORDS} words / 4.0 min with folds closed`, () => {
    assert.equal(S1_MAX_WORDS, 900);
    assert.equal(S1_MAX_MINUTES, 4.0);
    assert.ok(gates.S1.pass, s1Values);
  });

  test("S1 counter: clipped accessible names are excluded but stay in the DOM", async () => {
    const fixture = `<!doctype html><style>
      .visually-hidden { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); white-space: nowrap; }
      @media (max-width: 860px) { h2.clip { position: absolute; width: 1px; height: 1px; overflow: hidden; clip: rect(0,0,0,0); } }
    </style><main>
      <h2 class="clip">Short version heading</h2>
      <p>one two three</p>
      <button>Documented inline <span class="visually-hidden">Claude Desktop, Vendor documents: show evidence</span></button>
      <details><summary>Fold summary words</summary><p>closed fold text here</p></details>
    </main>`;
    const phone = await measureReadableHtml(fixture, { width: 375, height: 667 });
    assert.equal(phone.words, 8, "one two three + Documented inline + Fold summary words");
    assert.equal(phone.rawWords, 17, "innerText still includes the clipped heading and the 6-word label");
    assert.equal(phone.clippedWords, 9);
    assert.equal(phone.a11yLabelsInReadable, false);
    const desk = await measureReadableHtml(fixture, { width: 1280, height: 720 });
    assert.equal(desk.words, 11, "the heading is visible at desktop and counts");
    assert.equal(desk.rawWords, 17);
  });

  test("S1 on the page: readable count never includes compact accessible names; B fold closed at load", () => {
    for (const v of viewports) {
      assert.equal(v.a11yLabelsInReadable, false, v.viewport);
      assert.ok(v.words <= v.rawWords, v.viewport);
      assert.equal(v.openFolds, 0, v.viewport);
      assert.ok(v.sections["status-by-product"] <= 10, `${v.viewport} layer B summary only: ${v.sections["status-by-product"]}`);
      assert.ok(v.sections["what-would-change"] <= 150, `${v.viewport} layer C ${v.sections["what-would-change"]}`);
    }
  });

  test("S2 banner, aggregate judgment and shipping action fit the first screen at 1280x720 and 375x667", () => {
    assert.ok(gates.S2.pass, JSON.stringify(gates.S2.values.filter((v) => v.gated)));
  });

  test("S3 first-screen text carries the four brief.md tokens at 1280x720 and 375x667", () => {
    assert.equal(S3_TOKENS.length, 4);
    assert.ok(gates.S3.pass, JSON.stringify(gates.S3.values.filter((v) => v.gated)));
  });

  test("S6 no document overflow at 320 and 375 (and none at 820/1280 either)", () => {
    assert.ok(gates.S6.overflowPass, JSON.stringify(gates.S6.values));
    for (const v of viewports) assert.ok(v.overflowX <= 0, `${v.viewport} overflowX=${v.overflowX}`);
  });

  test("S6 disclosures: status fold opens on Enter/tap; compact Enter opens, Space and Escape close; tap toggles on phones", () => {
    assert.ok(gates.S6.keyboardPass, JSON.stringify(viewports.map((v) => v.disclosure)));
    assert.ok(gates.S6.touchPass);
    for (const v of viewports) assert.ok(v.disclosure.fold.closedAtLoad && v.disclosure.fold.enterOpens && v.disclosure.fold.enterCloses, v.viewport);
    assert.ok(by["375x667"].disclosure.touchPass && by["320x568"].disclosure.touchPass);
    assert.ok(by["375x667"].disclosure.fold.tapOpens && by["320x568"].disclosure.fold.tapOpens);
  });

  test("S6 print emulation opens the evidence fold and the status fold and shows compact panels", () => {
    assert.ok(gates.S6.printPass, JSON.stringify(viewports.map((v) => v.print)));
    for (const v of viewports) assert.ok(v.print.statusClosedBefore && v.print.statusFoldOpen, v.viewport);
  });

  test("fragment entry #takeaways opens the evidence fold; rendered status words stay honest", () => {
    assert.ok(gates.S4_fragment.pass, JSON.stringify(gates.S4_fragment.values));
    assert.ok(gates.S7_rendered.pass, JSON.stringify(gates.S7_rendered.values));
  });

  test("evaluateGates: each gate fails on the matching regression and ignores ungated viewports", () => {
    const mutate = (fn) => { const vs = structuredClone(viewports); fn(Object.fromEntries(vs.map((v) => [v.viewport, v])), vs); return evaluateGates(vs); };

    const atLimit = mutate((_, vs) => vs.forEach((v) => { v.words = S1_MAX_WORDS; v.minutes = 3.91; }));
    assert.equal(atLimit.S1.pass, true);
    assert.equal(mutate((_, vs) => vs.forEach((v, i) => { v.words = i ? S1_MAX_WORDS : S1_MAX_WORDS + 1; v.minutes = 3.9; })).S1.pass, false);
    assert.equal(mutate((_, vs) => vs.forEach((v) => { v.words = 100; v.minutes = 0.4; v.foldOpen = true; })).S1.pass, false, "open fold is not a folds-closed count");
    assert.equal(mutate((b) => { b["820x1180"].openFolds = 1; }).S1.pass, false, "an open status fold is not a folds-closed count");

    assert.equal(mutate((b) => { b["375x667"].boxes["#banner"].fullyVisible = false; }).S2.pass, false);
    assert.equal(mutate((b) => { b["1280x720"].scrollY = 40; }).S2.pass, false);
    assert.equal(mutate((b) => { b["320x568"].boxes["#banner"].fullyVisible = false; }).S2.pass, true, "320x568 is recorded, not gated");

    assert.equal(mutate((b) => { b["1280x720"].tokenHits["receipts are private"] = false; }).S3.pass, false);
    assert.equal(mutate((b) => { b["820x1180"].tokenHits.portable = false; }).S3.pass, true);

    assert.equal(mutate((b) => { b["320x568"].overflowX = 4; }).S6.pass, false);
    assert.equal(mutate((b) => { b["820x1180"].overflowX = 86; }).S6.pass, true, "820 overflow is recorded, not an S6 gate");
    assert.equal(mutate((b) => { b["1280x720"].disclosure.keyboardPass = false; }).S6.pass, false);
    assert.equal(mutate((b) => { b["375x667"].disclosure.touchPass = false; }).S6.pass, false);
    assert.equal(mutate((b) => { b["375x667"].print.pass = false; }).S6.pass, false);

    assert.equal(mutate((b) => { b["820x1180"].fragment.pass = false; }).S4_fragment.pass, false);
    assert.equal(mutate((b) => { b["375x667"].rendered.chips.push("Unsupported"); }).S7_rendered.pass, false);
    assert.equal(mutate((b) => { b["1280x720"].rendered.compactWords.push("Yes"); }).S7_rendered.pass, false);
    assert.equal(mutate((b) => { b["1280x720"].rendered.copilotCompactLabels = ["GitHub Copilot"]; }).S7_rendered.pass, false);
    assert.equal(mutate((b) => { b["1280x720"].rendered.privatePathInMain = true; }).S7_rendered.pass, false);
  });
}
