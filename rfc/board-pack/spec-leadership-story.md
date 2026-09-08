# Spec — leadership story

Files: `rfc/board-pack/index.html` (the story), `rfc/board-pack/STORY.md` (slimmed to match), and the board-pack
mirror sentences in `rfc/index.html`.

## Arc

Problem → what the product would do → what we already know works → what is still open → the decision and the ask.
Told once, in that order. Sections may keep their structure and the diagram; the copy is rewritten.

## Bans (visible prose only; link targets are not prose)

- **S1 — no personal names or handles.** Ownership is a role: "the project owner", "a Finance owner". Repository
  URLs behind evidence links are unavoidable and are not prose.
- **S2 — no lab calendar.** No dated run chronology. Describe what the system can do and what has not been shown,
  never on which day it happened. A single forward-looking decision checkpoint may be named as an event; prefer
  "the upcoming decision checkpoint" to a date.
- **S3 — no test detail.** No job counts, attempt inventories, per-case blow-by-blow, teardown or readback
  mechanics, fixture plumbing, or commit and pull-request decoration. One friendly evidence link where a claim needs
  backing.
- **S4 — no scoreboard labels.** No internal verdicts, gate codes or severity labels in visible prose.

## Honesty that must survive, as capabilities and limits

- **S5 — the data is invented.** Demonstration material throughout; no customer cohort data has been used.
- **S6 — what is known to work.** Graph retrieval can select a definition together with the rules it links to. A
  receipt can bind a query to its result and withhold the number when they disagree. A connected path has run end to
  end — retrieval into a checked computation into a consumer that enforces the check — including one run whose
  retrieval went through graph queries on Enterprise capacity.
- **S7 — the limits on that connected run, stated wherever it is claimed.** It carried a single identity on both
  legs. Its starting point was chosen rather than discovered through the catalog. Only the case expected to succeed
  was exercised, so the refusal behaviour has not been shown through graph queries.
- **S8 — the combined bar.** Catalog discovery, a separate restricted identity and graph queries have never been
  combined in one run, on real data. That is what the pilot is for, and it is unchanged.
- **S9 — access.** A separate restricted identity was denied where it should be, on the ordinary SQL retrieval path.
  Those same checks have not run inside graph queries.
- **S10 — the envelope.** Speed benchmarks are unfinished. No operating envelope has been accepted by anyone; the
  numbers are proposed. The version of the fact rows has not been chosen, and nothing pins a snapshot or cut-off for
  them, so two runs can compute different numbers from the same declaration and both check out.
- **S11 — capacity.** Graph walks need Enterprise or Enterprise Plus capacity; ordinary SQL and vector retrieval do
  not.

## Verification

A claim checklist over the rendered visible text, phrased as capabilities rather than dates, plus the three bans.
HTML parses; ids unique; same-document fragments resolve.
