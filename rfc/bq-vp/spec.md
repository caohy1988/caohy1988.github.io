# Spec — one scroll for the VP of BigQuery

## Must

- Serve a static page at `/rfc/bq-vp/`, with no build or live cloud calls.
- Use three or four short story sections: the Germany ask, the recorded observations, the proposed runtime, and one VP next step.
- At a typical desktop viewport (1280 × 720), show the Germany question, the locked thesis, and no more than three punchline cards above the fold.
- Say **BigQuery is the runtime of Knowledge Catalog + OKF**, immediately distinguishing discoverable context from the accountability the runtime would add.
- Keep the exact takeaways: **Trust you can defend**, **One pinned answer**, **IAM you can explain**.
- Show the recorded “verified” / “unproven” observations with their evidence limitations in the same section. Identify both as local tool paths; the first is Catalog-shaped, not a live Catalog-driven agent comparison.
- Explain the proposed chain: pinned publication → computation receipt → attributable answer. Use conditional language and an explicit RFC-proposal label. Keep the proposed IAM boundary understandable.
- Keep a small persistent honesty sentence visible while scrolling. Source links may be compact; the main argument must not require them.
- End with one concrete next step: prove one governed deployment for the Germany question. Offer one primary deep-dive link to `/rfc/full-demo/`.
- Use short sentences, legible text, semantic headings, visible keyboard focus, and responsive layout. Keep the page usable without JavaScript and free of horizontal overflow on mobile.
- Add a discoverable link near the top of `/rfc/`.

## Must not

- Add a stepper, tabs, evidence drawers, capability matrix, backup stories, or a second walkthrough.
- Invent session IDs, numbers, live traces, attestations, `BQ_COMMITTED` success, deployment heads, completed sync, or Phase A service accounts/grants.
- Present the observations as a controlled A/B, or suggest the stubbed verdict computed or attested a result.
- Turn the honesty line into a large label legend.
- Change `/rfc/full-demo/`, introduce cloud/network dependencies for the new page, or modify site deployment configuration.
- Merge the PR or wait for reviews.

## Evidence sources

| Claim | Checked-in source |
| --- | --- |
| Local Catalog-shaped path says “verified” without computation | `../full-demo/index.html`, `../full-demo/live/session_04fa3d56.json` |
| Verdict path reports “unproven”; attester is stubbed and executes nothing | `../full-demo/index.html`, `../full-demo/live/session_f21ee192.json` |
| Prompts, questions, tools differ; in-process demo pin | `../full-demo/index.html`, `../full-demo/VP_SHOW_NOTES.md` |
| Receipts are `UNVERIFIABLE`; heads, sync, Phase A IAM remain unbuilt | `../full-demo/live/README.md`, `../full-demo/index.html` |
| Proposed publication, receipt, attribution, and IAM opportunity | `../full-demo/index.html`, `../full-demo/VP_SHOW_NOTES.md`, `../index.html` |

The evidence set was already captured for the full demo. No new GCP collection is part of this change.
