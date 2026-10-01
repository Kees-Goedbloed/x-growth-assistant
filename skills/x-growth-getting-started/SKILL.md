---
name: x-growth-getting-started
description: First-run setup for the X growth dashboard. Use when a user clones the repo, opens it in an agent, or asks to configure handle, language, timezone, X login, Premium, repo path, config.json, or the daily collection schedule.
---

# X growth dashboard — getting started

You are setting up **this** clone. Stay generic: do not invent an owner handle,
do not copy another person's data, do not hardcode machine paths.

## 1. Locate the repo

Ask for the local path of `x-growth-assistant` if you are not already inside it.
Confirm `build.py` and `data/config.example.json` exist.

## 2. Run setup

```bash
./scripts/setup.sh
# or: make setup
```

Idempotent. Creates `.venv/` when possible, copies example `data/config.json`
and `.env` if missing, builds **public** demo fixtures, runs tests.

## 3. Ask the owner (do not guess)

Collect and write answers into `data/config.json` (gitignored):

| Question | Config / note |
|---|---|
| X handle | `account` (no `@`) |
| Display name | `display_name` |
| UI language | Dashboard UI is English; `lang` is ignored for display |
| Timezone for CSV timestamps | `csv_timezone` (default `UTC`) |
| X login | Used only by the collection skill in a browser; never store the password in git or `config.json` |
| X Premium? | Needed for some Analytics exports; remember it, do not commit it |
| Repo path | This clone |
| Daily schedule | See [docs/daily-routine.md](../../docs/daily-routine.md); default suggestion 07:15 local |

Also set `"mode": "public"` unless they explicitly want local private HTML.

## 4. Point collection at this tree

Followers-dir = `data/followers/` (so `python3 build.py` needs no extra flags).
CSVs = `data/analytics-csv/`.

## 5. Install the daily job

After config is saved, load `skills/x-growth-data-collection` (or tell a Grok
Bot user to install
[X Growth Assistant](https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi)) and schedule the
routine in [docs/daily-routine.md](../../docs/daily-routine.md).

## Guardrails

- Never commit `data/config.json`, `.env`, snapshots, CSVs, or avatars.
- Never run tests against a directory of real exports.
- Public HTML must pass `scripts/check_public_leaks.py`.
