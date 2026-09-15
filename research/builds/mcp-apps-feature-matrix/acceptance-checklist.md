# Acceptance checklist — human steps (PLAN_v2 §7 PR4, §8)

Automated §8 values are in `acceptance-results.md`. This file covers only the steps a script cannot do. None has been run. Nothing below may be filled in from memory, a transcript, or an agent's guess.

| Step | Status | Owner |
|---|---|---|
| Safari Reader View pass (real Safari, live URL) | **DEFERRED — requires a human in Safari** | Haiyuan or a delegate with Safari |
| Outside-reader test, one PM | **DEFERRED — requires human PM + UTL, no coaching, folds closed, 5 minutes each** | PM reader (not an author or reviewer of this page) |
| Outside-reader test, one UTL | **DEFERRED — requires human PM + UTL, no coaching, folds closed, 5 minutes each** | UTL reader (not an author or reviewer of this page) |
| Astra review at the exact PR4 HEAD | pending | Astra |

Human acceptance is not complete until every row above is recorded. These rows do not block landing the automated gates in PR4.

## 1. Safari Reader View

A WebKit Playwright render passes the same gates as Chromium (see `acceptance-results.md`). Reader View is Safari chrome, not page rendering, so that run does not show what Reader extracts.

Steps, on the live URL https://caohy1988.github.io/research/builds/mcp-apps-feature-matrix/ :

1. Open the URL in Safari (macOS, and iOS if available). Do not expand anything.
2. Turn on Reader (address bar → Show Reader).
3. Check each item and record yes / no / partly, with a note:
   - a. The aggregate judgment ("Three of nine host surfaces document MCP Apps rendering …") is present.
   - b. The shipping action ("Ship the portable path regardless …") is present.
   - c. The Unknown definition ("'Unknown' means this evidence does not establish the answer; it is not 'unsupported'") is present, and nothing says Unknown means unsupported.
   - d. The host TLDR ("Host status at a glance", nine hosts, Documented / Partial / Unknown) is present and readable.
   - e. The full evidence is still reachable: either Reader shows the v7 matrix, footnotes and takeaways, or leaving Reader and opening "Full evidence (v7, 2026-09-14)" shows them.
   - f. No Reader text implies an observed UI or fallback run.
4. Leave Reader. Load `#takeaways` on the URL and confirm the evidence fold opens at the takeaways.

Record:

```
Date/time (PT):
Safari version / OS:
Device:
Page commit (footer or git HEAD on main):
a judgment:            b action:            c Unknown definition:
d host TLDR:           e evidence reachable: f no observed-run implication:
#takeaways fragment opens fold:
Notes (verbatim oddities, missing sections):
```

## 2. Outside-reader five-question test

Rules (PLAN_v2 §8): one PM and one UTL, separately. No coaching and no explanation of the page beforehand. Start with the page loaded and all folds closed. Each reader uses a device of their choice. After five minutes, ask the questions below verbatim and write the answers down verbatim. Do not correct or prompt.

The five questions, verbatim:

1. Which three hosts document Apps rendering, and what is still required before relying on them?
2. Why is OpenAI Codex Desktop not among them?
3. What should a server ship regardless?
4. What does "Unknown" mean on this page?
5. Name one scoped evidence step that would change one stated Unknown.

Pass rule: each reader must answer all five. A miss on question 4 by either reader blocks calling human acceptance complete, because reading Unknown as unsupported is the overclaim this edition exists to prevent. That block does not block PR4, which lands automated gates only.

Scoring is recorded separately from answers and by someone other than the reader. Judge each answer against the page text, not an answer key written from memory.

### Recording template (copy once per reader)

```
Reader role: PM | UTL
Reader is not an author/reviewer of this page: yes | no
Date/time (PT):
Device:
Browser:
Viewport (CSS px, e.g. from devtools or window.innerWidth × innerHeight):
Folds closed at start: yes | no
Coaching given: none
Elapsed reading time (target 5:00):
Page commit:

Q1 answer (verbatim):
Q2 answer (verbatim):
Q3 answer (verbatim):
Q4 answer (verbatim):
Q5 answer (verbatim):

Scorer:
Q1 pass/miss + reason:
Q2 pass/miss + reason:
Q3 pass/miss + reason:
Q4 pass/miss + reason:
Q5 pass/miss + reason:
Reader result: pass (5/5) | fail
```

### Results

| Reader | Date | Device / viewport | Elapsed | Q1 | Q2 | Q3 | Q4 | Q5 | Result |
|---|---|---|---|---|---|---|---|---|---|
| PM | — not run — | | | | | | | | DEFERRED |
| UTL | — not run — | | | | | | | | DEFERRED |
