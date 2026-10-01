# Daily collection routine (any agent)

Tool-agnostic steps for keeping the dashboard fed. Same contract as
`skills/x-growth-data-collection/`. Load that skill (or the Grok Bot template)
instead of inventing a parallel flow.

## Inputs the owner must provide once

- X handle, UI language (dashboard UI is English), timezone for CSV timestamps
- Whether the X account is Premium (needed for some Analytics exports)
- Path to this git clone
- `data/config.json` (from `data/config.example.json`)
- A followers-dir: **`data/followers/`** inside this clone so `python3 build.py`
  picks snapshots up with no extra flags. Any other folder must be passed as
  `--followers-dir`.

## Every day

1. Sign in to X in a real browser (no X API connector is assumed).
2. Capture a follower snapshot →
   `data/followers/snapshot-YYYYMMDD-HHMMSS.json` and overwrite
   `data/followers/latest.json` with the same JSON (or a copy).
3. Export X **content analytics** CSV **unmodified** into `data/analytics-csv/`.
   Compute a hash of the new bytes. If a file with the same hash already exists,
   do **not** write a duplicate.
4. Rebuild the **private** owner dashboard:
   `python3 build.py --mode private`
5. Optionally also build public HTML (`python3 build.py`) and confirm the leak
   checker passes.

Never run the unit test suite against a tree that holds real `data/` exports.
Never unfollow anyone unless the owner just asked for that specific account.

## Cron example (owner box)

```cron
# 07:15 in the box timezone — invoke your agent/skill, or a wrapper script
15 7 * * * cd /path/to/x-growth-assistant && python3 build.py --mode private >> /var/log/x-growth-daily.log 2>&1
```

Cron only rebuilds. Collection still needs a browser session (human or agent).

## Grok Bot users

One-click template (same data contract):
**[Install the X Growth Assistant](https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi)**
