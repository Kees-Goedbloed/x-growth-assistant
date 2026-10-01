---
name: x-growth-data-collection
description: Collect X follower snapshots and Analytics CSVs for the growth dashboard, then rebuild. Use when running the daily job, exporting analytics, or writing snapshot-YYYYMMDD-HHMMSS.json. Browser login only; no X API connector.
---

# X growth dashboard — data collection

Generic collector. No X connector, no API token, no hardcoded owner.

## Paths (this clone)

| What | Where |
|---|---|
| Follower snapshots | `--followers-dir`, default **`data/followers/`** |
| Snapshot names | `snapshot-YYYYMMDD-HHMMSS.json` and `latest.json` (same payload) |
| Analytics CSV | `data/analytics-csv/` — **unmodified** X export |
| Config | `data/config.json` |

`build.py` always reads `data/followers/*.json`. If the followers-dir is that
folder, a plain `python3 build.py` picks snapshots up.

## Snapshot JSON

Write UTF-8 JSON. Minimum:

```json
{
  "account": "the_owner_handle",
  "date": "2026-09-26",
  "captured_at": "2026-09-26T09:45:00+02:00",
  "profile_followers": 107,
  "profile_following": 120,
  "handles": ["follower_one", "follower_two"],
  "following_handles": ["follower_one", "someone_else"],
  "following_complete": true,
  "complete": true
}
```

`handles` / `followers` required. `captured_at` or `date` required. Optional:
`unavailable`, `verified_unfollowers`, `collected_count`, `notes`. Full field
list: [README.nl.md](../../README.nl.md).

After writing `snapshot-YYYYMMDD-HHMMSS.json`, copy or write the same object to
`latest.json` in that folder.

## Analytics CSV

1. In a **real browser**, with the owner signed into X, export content analytics.
2. Save the file bytes **unchanged** into `data/analytics-csv/`.
3. Hash the bytes (SHA-256). If any existing file in that folder has the same
   hash, **do not write** a second copy (stale/reload cache).
4. If X shows a cached export, reload the analytics page and export again
   before hashing.

## Build

```bash
python3 build.py --mode private
```

Optional shareable build (strips other handles, leak-checks):

```bash
python3 build.py
```

Pass `--followers-dir DIR` only when snapshots are not in `data/followers/`.

## Must not

- Do not run `python3 -m unittest` (or `make test`) in a tree that contains
  real exports. Tests belong on fixtures / empty clones.
- Do not unfollow, follow, DM, or otherwise mutate the X graph unless the
  owner named that exact account in this session.
- Do not assume an X connector, cookie jar in git, or a password in `config.json`.
- Do not commit snapshots, CSVs, avatars, or `.env`.

Daily overview: [docs/daily-routine.md](../../docs/daily-routine.md).
