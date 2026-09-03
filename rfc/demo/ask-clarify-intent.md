# Intent — make the /rfc/demo/ ask unmistakable

Status: accepted from Haiyuan (2026-09-03). Codex and Kimi review on the
GitHub PR; Haiyuan merges. Copy-only slice; no new tape or video.

## The question reviewers were asking

Haiyuan's words: "How do we trust what's in BQAA? Are we asking for
human-in-the-loop or customer sentiment to decide what to promote? Or are we
adding context the agent obtained via the hard path into OKF so it is available
for easy discovery?"

## The answer (normative for this demo)

- **Third option.** Hard-path agent context (ranked Active-customer revenue,
  excluded the legacy metric, receipt unproven) was observed by BQAA; one
  adapter turn projects that into **derived OKF** so the next agent discovers
  it via `context_ref` instead of re-earning it or picking the dead metric.
- **Not** "trust BQAA as knowledge or truth." BQAA is observer-only. Telemetry
  is not the authored bundle and not a truth score.
- **Not** human-in-the-loop promotion or customer-sentiment ranking of what to
  promote. This slice does not pick winners that way.
- Trust here means **process integrity of what was observed**: opaque IDs,
  fail-closed lookup, no overclaim. It does not mean the number is right (the
  receipt stays UNVERIFIABLE) and it does not make BQAA a second wiki.

## Why

A cold reader of beat 1 could not answer the three-way question from the page.
The hero states the trap and the payoff, but nothing says which of the three
readings the demo is, and nothing names the two it is not. Reviewers filled the
gap with the wrong readings.

## Constraints (do not break)

- The locked hero question, the three-sentence subtitle, the four captions, and
  the stepper titles stay byte-identical; `check_cli_viewer.py` asserts them.
- Do not invent HITL or sentiment features, in copy or in code.
- Do not claim Catalog was written on this CLI path.
- Do not merge or touch BigQuery-Agent-Analytics-SDK PR 474.
- Do not re-record `okf-bqaa-cli.mp4` or the poster; edit captions around them.
- Keep the two existing traps (legacy metric, over-claiming trust).
- `rfc/index.html` Prototype callout stays within the checker's 2–6 sentences.

## Success

A cold reader of beat 1 can answer Haiyuan's three-way question correctly
without reading chat: it is the third option, it is not HITL or sentiment
promotion, it is not trusting BQAA as truth, and the number is still unproven.
