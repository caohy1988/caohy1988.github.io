# Which AI hosts document MCP Apps rendering, and what to ship anyway

## Banner
Evidence, not test results. Everything here comes from vendor documentation, dated user or staff reports, one pinned VS Code source snapshot, or local file inspection whose receipts are private and not linked. No cell is an observed UI or fallback run. "Unknown" means this evidence does not establish the answer; it is not "unsupported".

## Aggregate judgment
Three of nine host surfaces document MCP Apps rendering: Claude Desktop, GitHub Copilot in VS Code, and Cursor. That is a documentation-based starting set; build and registration path still need verifying, and no fallback has been verified by a run anywhere.

## Shipping action
Ship the portable path regardless: readable text plus an optional image as ordinary tool content. Do not rely on [app-only tool visibility](https://github.com/modelcontextprotocol/ext-apps/blob/6d9bdc7babf275b759225aa722cbf5510c4c6021/specification/2026-01-26/apps.mdx) to hide a tool from the model; it is unverified on every host.

## Next steps heading
What would change this page

## Next steps
- Host advertisement — capture the Apps advertisement in the host's initialize handshake at the relevant protocol revision. Updates only the advertisement row.
- Mount and fallback — for one named build and registration path, capture the Apps UI handshake, a mount, then the same tool with Apps off or failing; record any stage not reached. Updates "Rendering evidence" and "Without Apps" for that build and path only.
- App-only visibility — check whether an `app`-visibility tool reaches the model; updates that row only.
- Antigravity Desktop — repeat on current build 2.13.0, eleven minor versions past the searched 2.2.1.
- Codex Desktop — capture the gate's runtime value and server-facing handshake; code presence proves neither.
- Documentation gaps close only when the vendor publishes.

## Next steps owner
Proposed owner: whoever has the named build and a test Apps server; effort unestimated.

## Evidence fold summary
Full evidence (v7, 2026-09-14): matrix, legend, columns, footnotes, takeaways, history

## Kicker
Builds · MCP Apps · v7 evidence, readable edition

## Meta
v7 · 2026-09-14 · Readable edition across nine host surfaces.
