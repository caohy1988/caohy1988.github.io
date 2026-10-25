# research/usage — agent model usage dashboard

Live page: **https://caohy1988.github.io/research/usage/**

`index.html` + `snapshot.json` here are **generated**. The scripts in this folder are
versioned copies; the Mac source of truth is:

```
/Users/haiyuancao/Documents/agent-analytics-research/usage-dashboard/
  collect_and_build.py            # collects Mac CLI usage + renders index.html / snapshot.json
  collect_grok_box_activity.py    # box-side Grok activity collector (also imported by the above)
  refresh.sh                      # build + copy index.html / snapshot.json into this folder
  test_*.py                       # see Tests below
```

The two Python files here include the installed Mac's routine-proxy parsing and October 12
Manage schedule state (weekday refresh paused), plus the hub's collection and privacy fixes.
To install this version, copy **both** `research/usage/collect_and_build.py` and
`research/usage/collect_grok_box_activity.py` into
`/Users/haiyuancao/Documents/agent-analytics-research/usage-dashboard/`, replacing those two
files together. Keep that folder's `refresh.sh`, caches, inputs and other files. Then run its
`refresh.sh` as usual. The sibling supplies `finite_tree` and the Grok normalization helpers
required by the builder. Until both files are copied, refresh uses the older installed version.

## Tests

Each test file runs on its own, under the Mac's system Python 3.9 (`/usr/bin/python3`, the one
`refresh.sh` picks) and under Python 3.13:

```
cd research/usage
for t in test_*.py; do
  PYTHONDONTWRITEBYTECODE=1 /usr/bin/arch -arm64 /usr/bin/python3 "$t" || exit 1
  PYTHONDONTWRITEBYTECODE=1 /usr/local/bin/python3.13 "$t" || exit 1
done
```

The ARM prefix avoids an `xcrun` architecture error when the shell runs through Rosetta.
Each failure stops the loop and leaves its diagnostic visible.

| File | Covers |
|------|--------|
| `test_grok_stale.py` | 36h STALE rule, box collector schema, every non-room bot listed |
| `test_error_redaction.py` | no Bearer token or argv in error fields, snapshot.json, index.html |
| `test_qwen_usage.py` | Qwen card (usage log parser, cost, dated trial status); Kimi `config.toml` parser, tomllib and the 3.9 fallback agreeing |
| `test_qwen_audit_runs.py` | Native Qwen records through the production collector show unavailable audit status; explicit annotations, deduplication and makeup dates |
| `test_routine_proxy.py` | Installed Mac routine formats, newest Github dumps, paused rows/state and minute-field counting |
| `test_muse_usage.py` | Muse 7-day usage from `session-index.db` + session logs |
| `test_pacing.py` | report-only pacing marks on the quota bars |
| `test_strict_json.py` | snapshot.json is strict JSON: NaN / Infinity become null |
| `test_openrouter_spend.py` | OpenRouter spend card; the key never leaves memory |
| `test_review_fixes_r1.py` | Credential-shaped model keys, finite pacing overflow, tool-result examples, invalid Muse counters, UTC spend reset boundaries |
| `test_review_fixes_r2.py` | Embedded credential identifiers, bounded Muse counters through serialization, rejected runtime envelopes without tool-result counting |

They use temp HOMEs, fake keys and stubbed collectors: no network, no real CLI, and never the
real snapshot.json / index.html.

## Qwen Code (trial seat)

- Model `qwen/qwen3.8-max-0902` via OpenRouter, CLI `/usr/local/bin/qwen` (`~/.qwen/settings.json`).
- Launched through the wrapper `~/.local/bin/qwen-or`, which sources `OPENROUTER_API_KEY` from
  `~/.dsh/.env` (shared by DSH, Qwen Code and OpenCode GLM-5.3). The card checks only that the key is present; it never reads
  it out.
- Usage log: `~/.qwen/usage_record.jsonl`, one line per finished session; the last record per
  sessionId wins, as in qwen's own reader. The card shows sessions, requests and tokens for 24h,
  7d and all time, plus an estimated cost at list price ($2/M uncached input, $0.25/M cached
  input, $6/M output). Session ids and project paths are never published.
- Trial: three recorded nightly audit runs; 2026-10-25 to 2026-10-27 (PT) is the planned
  window. An outage-skipped night does not count. After the window, the status says
  "scheduled window elapsed; keep/drop pending the third recorded run" while fewer than
  three runs are recorded, or "keep/drop pending review" once three are recorded. The
  calendar alone never marks the trial ended or complete; Haiyuan makes the keep/drop decision.
  Native usage records have no job label, and the installed writer/launcher supplies no audit
  annotation. No completed Qwen audit receipt source was found on this Mac during reconciliation;
  without identified audits, JSON reports null runs and the card says
  "audit status unavailable (no audit receipts)", never a definitive zero. The parser can accept
  an explicit `job_type: "nightly-mac-harness-audit"` annotation if a producer supplies one;
  deduplicated makeup audits after 2026-10-27 then count too. Native sessions still count toward
  usage. A run counter needs a real receipt/annotation producer before runtime adoption.
- Actual OpenRouter spend is on the shared-key card (below), covering DSH, Qwen Code and
  OpenCode (GLM-5.3).

## Why Grok activity needs a box step

CLI bars (Fable, Codex/Astra, Kimi, Agy, Muse, DSH, Qwen Code) are collected live on the Mac.
Grok Bots activity comes from `/home/box/agent-data/agents` + `agent-transcripts`, which the
Mac **cannot see**. On the Mac, `collect_and_build.py` falls back to the cached
`grok_box_activity.json` beside it. If nobody refreshes that cache, week-old last-activity
dates used to render as if current.

## Refresh contract (box → Mac → hub)

1. **Box (Agent Manage Bot):** `python3 collect_grok_box_activity.py -o /tmp/grok_box_activity.json`
   (stdout when `-o` is omitted; exit 2 when not on the box).
2. **Copy to Mac:** `…/usage-dashboard/grok_box_activity.json`.
3. **Mac (Collection Bot):** `refresh.sh`, then a usage-only commit + push of this folder.

Output carries counts, sizes and timestamps only — no transcript text, no secrets.
Entries with no transcript dir (e.g. Jev) are listed as empty rows with
`missing_transcript: true`; nothing is invented. Rooms / placeholders in `GROK_SKIP_NAMES` are dropped.
Every other bot under `agents/` is listed after the five `GROK_ORDER` roster rows. Those extra
bots get no stale mark (an idle side bot is not a broken source), so only roster bots can make
the collector exit 1. The fixed collector has to be copied to the box (and to the Mac folder,
because `collect_and_build.py` imports `normalize_bots` from it) before extra bots appear.

## OpenRouter spend (shared-key totals: DSH, Qwen Code and OpenCode GLM-5.3)

`collect_openrouter()` reads `OPENROUTER_API_KEY` from `~/.dsh/.env` on every build and calls
`GET https://openrouter.ai/api/v1/key` with it. The request uses urllib, with the key only in an
unredirected `Authorization` header and redirects refused. The key never goes into argv, the
snapshot, the page, logs or any file. The card shows that key's own usage counters in USD
(OpenRouter credits are US dollars) for the UTC day, week (from Monday) and month of the fetch,
each labelled with its date, plus all time.

DSH, Qwen Code and OpenCode (GLM-5.3) send requests with this key, and DSH keeps no per-request generation ids,
so the figures are **shared-key totals** covering all three, not split per seat. (Qwen's chat logs do record
`gen-…` ids; a per-seat split would need one `/api/v1/generation` call per request.) Any failure
(no key, an HTTP error, a network or TLS error, an unreadable reply) shows "unavailable" on
every row, never $0. `/api/v1/credits` needs a management key, so it is not used.

## 36h STALE rule

`collect_grok()` sets `stale` / `stale_reason` on `snapshot.json → grok` when:

- there is no `grok_box_activity.json`, or it is unreadable;
- `collected_at_utc` (preferred) and `collected_at_pt` are both missing / unparseable;
- the collection is older than **36 hours**.

`ok` stays `true` for a cache with data so the table still renders; the Grok section then opens
with an amber **STALE** banner, and the pill always shows when box activity was collected.
A STALE banner means step 1–2 above did not happen — fix the sync, do not hide the banner.

Locks: vault `Maps/Decisions/2026-09-20-usage-grok-activity-sync.md`,
handoff `Ship/builds/2026-09-20-usage-grok-stale-handoff.md`.
