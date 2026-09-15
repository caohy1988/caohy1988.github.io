# Host TLDR (above the fold)

## Heading
Host status at a glance

## Summary
Chips rate **feature parity** (advertisement, mount, fallback, switch evidence), not documentation. **Full**: GitHub Copilot in VS Code and Cursor. **Partial**: Claude Desktop, Claude Cowork, OpenAI Codex Desktop. The other four are **Unknown** — too little evidence to judge, which is **not** the same as unsupported. **No row below is an observed UI or fallback run.**

## Official matrix
**Yes — this differs from the official MCP Apps matrix, intentionally.**

| | Official [client extension matrix](https://modelcontextprotocol.io/extensions/client-matrix) | This page |
|---|---|---|
| Question | Does the client implement `io.modelcontextprotocol/ui` ([MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview))? | What is the capability / registration-path / fallback gap for shipping Glance-style UI on these nine hosts? |
| Grain | Community-maintained CHECK per client | Full / Partial / Unknown feature parity per host, with evidence links |
| Observed UI runs | N/A | None; we do not invent them |

Overlap: Claude Desktop, GitHub Copilot, Cursor. An official CHECK means the client claims the extension, not a verified Glance UI journey.

## Table
| Host | Status | Why |
|---|---|---|
| Claude Desktop | Partial | Inline mount documented ([guide](https://claude.com/docs/connectors/building/mcp-apps/getting-started)) but reports mixed ([issue #165](https://github.com/anthropics/claude-ai-mcp/issues/165)); fallbacks reported as a [blank gap](https://github.com/anthropics/claude-ai-mcp/issues/165#issuecomment-4747962829) and an [error card](https://github.com/anthropics/claude-ai-mcp/issues/165#issuecomment-5301835548); version, checklist, switch unknown. |
| Claude Cowork | Partial | Reports split by path: first-party mounts, gateway text fallback ([issue #236](https://github.com/anthropics/claude-ai-mcp/issues/236)), plugin raw JSON ([issue #274](https://github.com/anthropics/claude-ai-mcp/issues/274)); version, checklist unknown. |
| Claude Code | Unknown | Advertisement, mount, fallback unknown; [guide](https://code.claude.com/docs/en/mcp#mcp-client-runtimes) covers standard MCP only. Unknown ≠ unsupported. |
| OpenAI Codex CLI | Unknown | Advertisement, mount, fallback unknown; [docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) silent on Apps. Unknown ≠ unsupported. |
| OpenAI Codex Desktop | Partial | Inspected bundle has code for a UI-extension handshake, sandboxed mount, fallback branch and a gate defaulting to `false` (receipts private, not linked); advertisement and UI not captured; [docs](https://learn.chatgpt.com/docs/extend/mcp?surface=desktop) silent. |
| GitHub Copilot | Full | [Docs](https://code.visualstudio.com/blogs/2026/01/26/mcp-apps-support) plus pinned source for [Apps version](https://github.com/microsoft/vscode/blob/c48e5e4a36448a6788d234ac510cf0985a08e10b/src/vs/platform/mcp/common/modelContextProtocolApps.ts#L86), [inline mount](https://github.com/microsoft/vscode/blob/c48e5e4a36448a6788d234ac510cf0985a08e10b/src/vs/workbench/contrib/chat/browser/widget/chatContentParts/toolInvocationParts/chatMcpAppModel.ts#L568), [off](https://github.com/microsoft/vscode/blob/c48e5e4a36448a6788d234ac510cf0985a08e10b/src/vs/workbench/contrib/mcp/common/mcpLanguageModelToolContribution.ts#L245) and [error](https://github.com/microsoft/vscode/blob/c48e5e4a36448a6788d234ac510cf0985a08e10b/src/vs/workbench/contrib/chat/browser/widget/chatContentParts/toolInvocationParts/chatMcpAppSubPart.ts#L182) fallbacks, and a [toggle](https://code.visualstudio.com/docs/agents/reference/ai-settings). App-only visibility unknown. Not a released build or observed run. |
| Cursor | Full | [Docs](https://cursor.com/docs/context/mcp) claim Apps; dated reports show mounts [restored in 3.12](https://forum.cursor.com/t/mcp-apps-stopped-rendering-in-3-10-20-worked-in-3-9-16/165167/19), a [plain-text fallback](https://forum.cursor.com/t/mcp-apps-stopped-rendering-in-3-10-20-worked-in-3-9-16/165167/10) and [no toggle or enablement](https://forum.cursor.com/t/mcp-apps-stopped-rendering-in-3-10-20-worked-in-3-9-16/165167/22) (staff). Version, checklist unpublished; unreproduced, not an observed run. |
| Antigravity CLI | Unknown | Advertisement, mount, fallback unknown; [docs](https://antigravity.google/docs/mcp) silent on Apps. Unknown ≠ unsupported. |
| Antigravity Desktop | Unknown | Inspected 2.2.1 slice has no named Apps literals; [docs](https://antigravity.google/docs/mcp) and [changelog](https://antigravity.google/changelog) through 2.13.0 silent. Unknown ≠ unsupported. |
