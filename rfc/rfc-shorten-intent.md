# Intent — shorten both RFC surfaces

Prepared 2026-09-09. Haiyuan's feedback, verbatim: "current RFC is too long too many words". Both pages are cut, roughly in half.

## Why

- `/rfc/` is the leadership landing page and its masthead promises a 3–4 minute read. Measured in Chromium with every fold open it carries 3,281 words (2,172 with the technical-design fold closed). The same evidence is restated three or four times: in the runtime assessment, in each comparison note, in the decision envelope and again in the technical-design fold.
- `/rfc/detailed-rfc/` is the full technical RFC. It carries 14,102 words with every fold open (10,132 closed). It repeats the board story (motivation, summary, phase intros, recorded-examples note), restates every recorded run's limits in five places, and carries dated lab detail, reviewer and author names, and "what this is not" blocks that no reader of a proposal needs twice.

## Outcome

1. `/rfc/` reads as one leadership story in at most ~1,800 words with every fold open. The hero, the three checks, the decision envelope, the technical-design fold and the two asks stay; repetition, test dates and per-run narration go.
2. `/rfc/detailed-rfc/` keeps its architecture, contracts, identity model, protocol, acceptance, phases and evidence pointers in at most ~7,500 words with every fold open. The restated board story shrinks to a pointer; long example paragraphs that only repeat the landing page are cut; one non-goals list survives.
3. Every claim stays as honest as it is today: nothing that was recorded as partial, single-identity, hand-seeded, success-only, unmeasured or proposed is promoted. Fewer words, same limits.
4. Section ids, redirects, the legacy-bookmark forwarder, the primary nav, the fragment-forwarding stubs and every link target a test asserts stay in place.
5. Reader-facing prose carries no digest, job id, pull-request number or personal name. The invented VP, the blog-post authors and the reviewing agents are no longer named on the detailed page.

## Not in scope

- No change to the board-pack markdown history under `rfc/board-pack/`, the spike README, the baseline card or either demo.
- No new evidence and no live GCP. No merge.
- No redesign: styles, diagrams and page structure are unchanged except where a removed block leaves an empty container.
