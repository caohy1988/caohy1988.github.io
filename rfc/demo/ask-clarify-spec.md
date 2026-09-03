# Spec — the Ask surfaces on /rfc/demo/

Slice of `ask-clarify-intent.md`. Copy only.

## The one sentence (reuse verbatim where a single sentence fits)

> This demo takes context an agent already earned the hard way and, via BQAA
> observation, projects it into derived OKF so the next agent can discover it;
> it is not human-in-the-loop or customer-sentiment promotion, and it is not
> trusting BQAA as truth.

## Surfaces

| Surface | Change | Must keep |
|---|---|---|
| `rfc/demo/index.html` hero | A short callout **under the badges**, before `<main>`: the third option in one sentence, then the two misreads it is not, then "trust = process integrity of what was observed; the number is still unproven". | `<h1>` and `.subtitle` byte-identical (checker); no SHA / 180 / session strings in the hero. |
| `rfc/demo/index.html` walkthrough | Caption 1 keeps the locked sentence and gains one trailing clause that echoes the third option. | The locked caption sentence must remain a substring. |
| `rfc/demo/app.js` beat 1 | A "What this demo is asking" block in `renderAsk()`: the three-way question, the answer (third option), the two "not" lines, the trust definition, "number still unproven". Placed before the traps. | Existing traps, `beatHead(1, "telemetry", "Ask"`, the tape pane. |
| `rfc/demo/README.md` | Same framing in "Four beats → Ask" and a new short "What this demo is asking" section. | Question, session, `context_ref`, publication, PR 474, "did not write Knowledge Catalog". |
| `rfc/demo/WALKTHROUGH.md` | Same framing in "1 · ASK". | The four caption sentences verbatim. |
| `rfc/index.html` Prototype callout | One clause merged into an existing sentence so the RFC pointer matches the demo ask. | Question, "legacy", "unproven", `href="./demo/"`, 2–6 sentences, no feature list. |

## Wording rules

- Say "hard path" for what the first agent did and "derived OKF" for the
  projection. Say "observer-only" for BQAA.
- Name both misreads explicitly: "human-in-the-loop promotion" and
  "customer-sentiment ranking".
- Say "process integrity of what was observed" for trust. Never "trust BQAA".
- Keep "the number is unproven" / "receipt UNVERIFIABLE" next to any trust
  statement.
- No new feature claims. No Catalog write claim.

## Checks

`python3 rfc/demo/tools/check_cli_viewer.py` exits 0. Additionally grep:
`human-in-the-loop` and `sentiment` appear on all five surfaces only as
negations; `hard path` appears on the hero, beat 1, README, WALKTHROUGH.
