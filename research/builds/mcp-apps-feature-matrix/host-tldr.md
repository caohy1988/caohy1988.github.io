# Host TLDR (above the fold)

## Heading
Host status at a glance

## Summary
Three hosts **document** MCP Apps rendering today: Claude Desktop, GitHub Copilot in VS Code, and Cursor. Two look **partial** (Claude Cowork has mixed dated reports by path; OpenAI Codex Desktop has Apps-related code in the inspected bundle but no captured UI). The rest stay **Unknown** — we checked their guides and found nothing adequate, which is **not** the same as unsupported. **No row below is an observed UI or fallback run.**

## Official matrix
This page answers a different question from the official [MCP Apps overview](https://modelcontextprotocol.io/extensions/apps/overview) / [client extension matrix](https://modelcontextprotocol.io/extensions/client-matrix). Official CHECK marks mean a client advertises the `io.modelcontextprotocol/ui` extension. Our table tracks capability / path / fallback evidence for the nine Glance-relevant hosts. Overlap: Claude Desktop, GitHub Copilot, Cursor. Official CHECK ≠ verified Glance UI journey.

## Table
| Host | Status | Why |
|---|---|---|
| Claude Desktop | Documented | Vendor docs claim Apps support ([Claude Apps getting started](https://claude.com/docs/connectors/building/mcp-apps/getting-started)); mixed historical failures exist ([issue #165](https://github.com/anthropics/claude-ai-mcp/issues/165)). Not an observed run here. |
| Claude Cowork | Partial | Dated reports: first-party path yes / gateway & plugin no ([issue #236](https://github.com/anthropics/claude-ai-mcp/issues/236), [issue #274](https://github.com/anthropics/claude-ai-mcp/issues/274)). Not current observed. |
| Claude Code | Unknown | Reviewed [Claude Code MCP guide](https://code.claude.com/docs/en/mcp#mcp-client-runtimes) is silent on Apps; handshake uncaptured. Unknown ≠ unsupported. |
| OpenAI Codex CLI | Unknown | Reviewed [Codex CLI MCP docs](https://learn.chatgpt.com/docs/extend/mcp?surface=cli) silent on Apps. Unknown ≠ unsupported. |
| OpenAI Codex Desktop | Partial | Local inspection finds Apps-related sandbox/schema/gate code in `ChatGPT.app` (receipts private, not linked); vendor [Desktop MCP docs](https://learn.chatgpt.com/docs/extend/mcp?surface=desktop) silent; one historical [“Codex” iframe report](https://github.com/anthropics/claude-ai-mcp/issues/165#issuecomment-5127235678) leaves surface unstated. UI not captured. |
| GitHub Copilot | Documented | [VS Code MCP Apps blog](https://code.visualstudio.com/blogs/2026/01/26/mcp-apps-support) + [v1.109 notes](https://code.visualstudio.com/updates/v1_109); Apps version pinned in [VS Code source](https://github.com/microsoft/vscode/blob/c48e5e4a36448a6788d234ac510cf0985a08e10b/src/vs/platform/mcp/common/modelContextProtocolApps.ts#L86). Not an observed run. |
| Cursor | Documented | [Cursor MCP docs](https://cursor.com/docs/context/mcp) claim support; a mount regression was reported fixed in 3.12 ([forum thread](https://forum.cursor.com/t/mcp-apps-stopped-rendering-in-3-10-20-worked-in-3-9-16/165167/19), unreproduced here). Not observed. |
| Antigravity CLI | Unknown | Reviewed [Antigravity MCP docs](https://antigravity.google/docs/mcp) silent on Apps. Unknown ≠ unsupported. |
| Antigravity Desktop | Unknown | Reviewed [Antigravity MCP docs](https://antigravity.google/docs/mcp) and [changelog](https://antigravity.google/changelog) (through 2.13.0) do not establish Apps; inspected 2.2.1 slice had no named Apps literals. Unknown ≠ unsupported. |
