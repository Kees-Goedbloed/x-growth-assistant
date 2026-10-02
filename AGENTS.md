# Agent guide — x-growth-assistant

This file is the onboarding contract for Cursor, Claude Code, and any other coding agent. Humans can follow it too.

## 1. Setup (do this first)

```bash
./scripts/setup.sh
# or: make setup
```

Idempotent. It creates `.venv/` if missing (stdlib only; no pip packages), copies `data/config.example.json` → `data/config.json` and `.env.example` → `.env` when those files are absent, creates `data/followers/`, `data/posts/`, `data/analytics-csv/`, builds **public** demo HTML from bundled fixtures, runs `scripts/check_no_real_data.sh` when `.git` exists, and runs `python3 -m unittest discover -s tests -v`.

Skip the nested suite only when a test is invoking setup itself:

```bash
XDASH_SETUP_SKIP_TESTS=1 ./scripts/setup.sh
```

Python 3.12+ is enough. Open `index.html` with `file://` or `./serve.sh`.

## 2. Data layout

| Path | Who writes it | Git |
|---|---|---|
| `data/config.json` | you / getting-started skill | **ignored** — copy from `data/config.example.json` |
| `data/followers/snapshot-YYYYMMDD-HHMMSS.json` | X Growth Assistant (Darrel) | **ignored** |
| `data/followers/latest.json` | same (pointer at the newest snapshot) | **ignored** |
| `data/analytics-csv/*.csv` | same — **unmodified** X Analytics exports | **ignored** |
| `data/posts/*.json` | optional extra post metrics | **ignored** |
| `data/target_accounts.json` | optional public-mode size buckets | **ignored** |
| `data/public_allowlist.json` | optional extra leak-check exceptions | **ignored** |
| `.env` | hosted deploy secrets | **ignored** — copy from `.env.example` |
| `test-fixtures/data/` | `make_fixtures.py` / default empty build | **ignored**, fictional |
| `assets/og-image.png` | public share card (1200×630) | committed |
| `assets/avatar.*` | owner photo | **ignored** |

`build.py` always reads `data/followers/*.json` and `data/analytics-csv/*.csv`. Point the collector’s `--followers-dir` at `data/followers/` and a local `python3 build.py` picks snapshots up with **no extra flags**. An extra read-only folder is `--followers-dir DIR` or `publish.sh`’s `X_FOLLOWERS_DIR`. `data/followers/` wins on the same `captured_at`.

Snapshot JSON shape (also in [README.nl.md](README.nl.md)): `account`, `date` or `captured_at`, `handles` (or `followers`), optional `profile_followers`, `following_handles`, `complete`, `unavailable`, `verified_unfollowers`. Filenames `snapshot-YYYYMMDD-HHMMSS.json`, `snapshot-YYYY-MM-DD.json`, and `latest.json` are all valid.

## 3. Public vs private

| | Public (**default**) | Private (**opt-in**) |
|---|---|---|
| How | omit `--mode`, or `--mode public`, or `"mode": "public"` | `--mode private` or `"mode": "private"` |
| Hosted | `DASHBOARD_MODE=public` (turns Basic Auth off) | `DASHBOARD_MODE=private` **and** `DASHBOARD_USER` + `DASHBOARD_PASSWORD` |
| Other handles | stripped; leak check **fails the build** | kept |
| When to use | anything you might share or commit as HTML | owner-only box / Basic Auth site |

CLI `--mode` wins over `config.json` `"mode"`. Empty `./data` (no CSV / posts / snapshots) generates demo fixtures and stays public.

## 4. Commands

```bash
python3 build.py                          # demo or real data; public + leak check
python3 build.py --mode private           # local private HTML
python3 build.py --data DIR --out FILE --today YYYY-MM-DD
python3 build.py --followers-dir DIR      # extra snapshot folder (read-only)
python3 -m unittest discover -s tests -v
bash scripts/check_no_real_data.sh
python3 scripts/check_public_leaks.py index.html data   # or test-fixtures/data
git config core.hooksPath .githooks       # optional local gitleaks
```

Hosted deploy is `scripts/publish.sh` (see [DEPLOY.md](DEPLOY.md)). Do not Git-link Netlify; `scripts/netlify-build.sh` refuses empty `data/`.

## 5. Guardrails (non-negotiable)

- **Never commit** real snapshots, CSVs, `data/config.json`, `.env`, `assets/avatar.*`, `dist/`, or a real-data `index.html`.
- **Always** let public builds run `scripts/check_public_leaks.py`. Do not add `--mode public` bypasses.
- Tests must not write to the real `data/` tree. Do not point `make_fixtures.py` at `data/`.
- UI copy stays English. Do not restore Dutch chrome.
- Do not change repo visibility, force-push, or rewrite history unless the owner explicitly asks.
- Do not put tokens, Netlify site IDs, or other people’s handles in tracked files.
- Unused `sec*` / CI strings, `miniTop`, and `postsExplorer` in the template stay.

## 6. Skills (any agent)

Open Agent Skills (YAML frontmatter `name` + `description`):

| Skill | Path |
|---|---|
| Getting started | [`skills/x-growth-getting-started/SKILL.md`](skills/x-growth-getting-started/SKILL.md) |
| Data collection | [`skills/x-growth-data-collection/SKILL.md`](skills/x-growth-data-collection/SKILL.md) |

The same folders are symlinked at `.claude/skills/` and `.cursor/skills/` so hosts that only search those trees still find them.

Daily routine (cron + Grok Bot note): [docs/daily-routine.md](docs/daily-routine.md).

## 7. Get the data collector (Darrel)

One-click install: **[Install the X Growth Assistant](https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi)** (`https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi`).

That Grok Bot template (“X Growth Assistant”) includes:

1. **Getting started** — asks for X handle, language, timezone, X login, this repo path, and `data/config.json`.
2. **Data collection** — writes `snapshot-YYYYMMDD-HHMMSS.json` and `latest.json` into the configured `--followers-dir` (use `data/followers/` here) and drops **unmodified** Analytics CSVs into `data/analytics-csv/`.
3. **Daily routine** — follower snapshot, CSV export with a hash check (skip rewrite if the file is unchanged), then a **private** dashboard build.

After the first successful collection, rebuild:

```bash
python3 build.py --mode private          # owner dashboard
python3 build.py                         # shareable public HTML + leak check
```

## 8. Docs map

- [README.md](README.md) — human quickstart and **What stays private, what is public**
- [README.nl.md](README.nl.md) — data-format reference (Dutch)
- [docs/daily-routine.md](docs/daily-routine.md) / [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md)
- [SECURITY.md](SECURITY.md) / [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md) / [CONTRIBUTING.md](CONTRIBUTING.md) / [DEPLOY.md](DEPLOY.md)
- [CHANGELOG.md](CHANGELOG.md) — version `0.1.0` in `pyproject.toml` (no tags created here)
