# research/usage — agent model usage dashboard

Live page: **https://caohy1988.github.io/research/usage/**

`index.html` + `snapshot.json` here are **generated**. The scripts in this folder are
versioned copies; the Mac source of truth is:

```
/Users/haiyuancao/Documents/agent-analytics-research/usage-dashboard/
  collect_and_build.py            # collects Mac CLI usage + renders index.html / snapshot.json
  collect_grok_box_activity.py    # box-side Grok activity collector (also imported by the above)
  test_grok_stale.py              # python3 test_grok_stale.py  → ALL CHECKS PASSED
  test_error_redaction.py         # python3 test_error_redaction.py → no Bearer/argv in error fields, snapshot.json, index.html
  refresh.sh                      # build + copy index.html / snapshot.json into this folder
```

After changing a script on the Mac, copy it here in the same PR so the hub history tracks it.

## Why Grok activity needs a box step

CLI bars (Claude/Fable, Codex/Astra, Kimi, Agy, Muse, DSH) are collected live on the Mac.
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
