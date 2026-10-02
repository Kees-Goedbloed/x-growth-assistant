# X growth dashboard

[![CI](https://github.com/Kees-Goedbloed/x-growth-assistant/actions/workflows/ci.yml/badge.svg)](https://github.com/Kees-Goedbloed/x-growth-assistant/actions/workflows/ci.yml)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

Offline builder for a single-file X (Twitter) growth dashboard. `build.py` uses the Python 3 standard library only: it reads local snapshots and analytics exports and writes one self-contained `index.html` (JSON embedded, Apache ECharts and Inter vendored and inlined at build time). Open it with `file://` or `./serve.sh`.

Built by Kees Goedbloed, AI manager at Lein AI Systems.

English UI is the default (`lang` is always `en` in the built HTML). Full data-format docs: **[README.nl.md](README.nl.md)**.

![Share card for public builds](assets/og-image.png)

The image is the 1200×630 Open Graph / X card used when a public dashboard link is shared. A fresh clone builds bundled demo fixtures for the HTML itself — your own X exports stay on your machine.

## 5-minute quickstart

A fresh clone is safe and shareable. One command for humans and coding agents:

```bash
./scripts/setup.sh
# or: make setup
```

That creates `.venv/`, copies `data/config.example.json` → `data/config.json` and `.env.example` → `.env` if missing, builds **public** demo HTML, and runs the tests. Or, with an empty `data/` directory:

```bash
python3 build.py
# writes ./index.html from bundled demo fixtures, public mode
# open file://…/index.html   or:  ./serve.sh
```

That command generates `test-fixtures/data/` (gitignored, fictional), builds **public** HTML, and runs the leak checker. No X export, token, or password is required.

To use your own exports later:

1. Copy `data/config.example.json` → `data/config.json` and set `account` / `display_name`.
2. Drop your X **content analytics CSV** in `data/analytics-csv/`.
3. Optional: follower snapshots in `data/followers/`, post JSON in `data/posts/`.
4. Build again. Public remains the default until you opt into private (see below).

```bash
cp data/config.example.json data/config.json   # edit account / display_name
python3 build.py                               # public HTML + leak check
python3 build.py --mode private                # local private HTML (keeps other handles)
```

## Get the data collector (Darrel)

Real X exports are collected by a Grok Bot agent. Install the template (one click):

**[Install the X Growth Assistant](https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi)**

The template is named **X Growth Assistant**. Getting started asks for your X handle, language, timezone, X login, this repo path, and `data/config.json`. After that it:

1. Writes follower snapshots as `snapshot-YYYYMMDD-HHMMSS.json` plus `latest.json` into its `--followers-dir` folder. Point that folder at `data/followers/` so `python3 build.py` loads them automatically (no extra flags). `snapshot-YYYY-MM-DD.json` also works.
2. Drops **unmodified** X Analytics CSVs into `data/analytics-csv/`.
3. Runs a daily routine: follower snapshot, CSV export with a hash check (skip rewrite when the file is unchanged), then a **private** dashboard build.

Snapshot JSON fields are documented in [README.nl.md](README.nl.md) (`handles` / `followers`, `captured_at` or `date`, optional `following_handles`, …). Optional extra post JSON can go in `data/posts/`.

Do not commit those files. After the first collection:

```bash
python3 build.py --mode private    # owner view (other handles kept)
python3 build.py                   # shareable public HTML + leak check
```

Explicit fixture rebuild (same data the default empty-`data/` path uses):

```bash
python3 test-fixtures/make_fixtures.py
python3 build.py --data test-fixtures/data --mode public --out /tmp/index.public.html --today 2026-09-25
python3 build.py --data test-fixtures/data --mode private --out /tmp/index.test.html --today 2026-09-25
```

## What stays private, what is public

| Stays on your machine (never git) | Safe to publish / share |
|---|---|
| `data/` snapshots, CSVs, `config.json`, research dumps | This repository: builder, templates, **example** configs, demo fixtures generator |
| `assets/avatar.*`, `.avatar-cache/` | `assets/og-image.png` (public share card) |
| `.env`, Netlify tokens, site IDs, `DASHBOARD_PASSWORD` | `.env.example`, `data/config.example.json` |
| Private HTML (`--mode private`) with other people's handles | Public HTML (default): your growth metrics, stripped of other handles |
| Hosted private site (Basic Auth) | Hosted public site (`DASHBOARD_MODE=public`, no auth) |

**Public is the default** for any shareable build (`python3 build.py`, Netlify HTML when `DASHBOARD_MODE` is unset or `public`). Other accounts' handles are stripped from HTML **and** embedded JSON (`@name` → `@…`). The leak checker runs automatically and **fails the build** if a non-allowlisted handle remains as a handle.

**Private is opt-in.** You need an explicit `--mode private` **or** `"mode": "private"` in `data/config.json`. A hosted private site also requires `DASHBOARD_MODE=private` **plus** `DASHBOARD_USER` and `DASHBOARD_PASSWORD` (the edge function returns HTTP 503 if either credential is missing). See `.env.example` and [DEPLOY.md](DEPLOY.md).

Copy the examples; do not commit the filled-in files:

- [`data/config.example.json`](data/config.example.json) — `"mode": "public"` and fictional `demo_owner`
- [`.env.example`](.env.example) — `DASHBOARD_MODE=public`; private user/password commented out

## Config keys

Copy `data/config.example.json` to `data/config.json` (gitignored). Goals in the example are `null`.

| key | meaning |
|---|---|
| `mode` | `public` (default, shareable) or `private` (keeps other handles). CLI `--mode` wins if set. |
| `account` | X handle (no hardcoded default) |
| `display_name` | Shown in the header; generic title if empty |
| `site_url` | Canonical / Open Graph URL (public mode). Needed for an absolute `og:image` when the link is posted on X. `SITE_URL` / `PUBLIC_SITE_URL` / `URL` are fallbacks if this is empty. |
| `repo_url` | Private-build footer “Built with x-growth-assistant”; hidden if empty |
| `source_repo_url` | Public-page “Free source on GitHub” link (default `https://github.com/Kees-Goedbloed/x-growth-assistant`) |
| `og_image_url` | Override OG image (default `{site_url}/assets/og-image.png`, or `/assets/og-image.png`) |
| `profile_image_url` | Optional owner avatar (local path or `https://`). HTTP `pbs.twimg.com` `_normal`/`_bigger` URLs are upgraded to `_400x400`. If empty, the builder tries an exported owner URL, then `api.fxtwitter.com/<account>` (`user.avatar_url`), then `https://unavatar.io/x/<account>`. Saved as `assets/avatar.png` or `.jpg` from the bytes; never hotlinked at runtime. |
| `avatar_lookup` | Set `false` to skip fxtwitter/unavatar (tests / offline). |
| `avatar_cache` | Persistent cache directory (default `{data}/.avatar-cache`, or `XDASH_AVATAR_CACHE`). Reused across fresh publish temp dirs; refetch at most once per day. Gitignored. |
| `lang` | UI language is English (`en`); this key is ignored for display |
| `csv_timezone` | Timezone for CSV timestamps without an offset (default `UTC`) |
| `goal_followers` | Optional positive integer; must be set together with `goal_date` |
| `goal_date` | Optional `YYYY-MM-DD` |

`data/target_accounts.json` (gitignored; see `data/target_accounts.example.json`) maps `handle → follower count` so the **public** build can group replies by target size. If the file is missing, public mode groups by how often you replied to the same account (`1×`, `2–4×`, `5×+`). Buckets with fewer than 5 distinct accounts are hidden.

Optional `data/public_allowlist.json` (gitignored; copy `data/public_allowlist.example.json`) lists extra handles the leak checker should accept even in `@handle` / profile-URL / structured-field contexts.

## Public vs private (build output)

| | Public (default) | Private (explicit opt-in) |
|---|---|---|
| How to select | omit `--mode`, or `--mode public`, or `"mode": "public"` | `--mode private` or `"mode": "private"` |
| Hosted auth | `DASHBOARD_MODE=public` turns Basic Auth **off** | `DASHBOARD_MODE=private` **and** `DASHBOARD_USER` / `DASHBOARD_PASSWORD` |
| Handles of others | Stripped from HTML **and** embedded JSON | Full lists and reply ROI per account |
| Replies | Size or frequency aggregates only | Per-account tables |
| Robots / OG | `Allow: /`, canonical + Open Graph | `Disallow: /`, `noindex`, `Cache-Control: private, no-store` |
| Leak check | Always runs; build fails on a leak | Not required (private HTML is not shareable) |

Public mode keeps your own follower growth, Follower goal, posts/engagement, heatmaps, “What works best”, “Best time to reply”, and “From profile visit to follower”. `@handles` in post text other than `account` become `@…`.

## Privacy

- **`data/` is never committed** (only `.gitkeep` and `*.example.*` files). The rule is `data/**` plus exceptions for directories, `.gitkeep`, and `*.example.*`. Do **not** use `data/*`: un-ignoring subfolders with `!data/**/` would let `git add -A` stage nested snapshots, CSVs, and research files.
- Do not put tokens or research dumps in this repo. CI runs `scripts/check_no_real_data.sh`, gitleaks on the full git history, and `git check-ignore` on nested `data/` paths. Optional local hook: `git config core.hooksPath .githooks` (see [CONTRIBUTING.md](CONTRIBUTING.md)).
- `scripts/publish.sh` builds on the machine from `SOURCE_DATA_DIR` and `X_FOLLOWERS_DIR`, leak-checks the public HTML, then `netlify deploy --prod --no-build --dir … --site …`. It never `git add` / `commit` / `push` data.
- `scripts/check_public_leaks.py` blocks a public deploy if another account’s handle is still in the output **as a handle**: `@handle`, `x.com/handle` / `twitter.com/handle`, or a structured field (JSON `in_reply_to_handle` / `username` / `data-handle`, …). Bare words in your own post text that happen to equal a handle (e.g. “I asked Grok bot how Karpathy would design this with OpenAI and Google”) are not leaks. The dashboard owner’s `account` is never flagged. Extra exceptions: `data/public_allowlist.json`.

Deploy both sites: **[DEPLOY.md](DEPLOY.md)**. Security: [SECURITY.md](SECURITY.md). Conduct: [CODE_OF_CONDUCT.md](CODE_OF_CONDUCT.md). License: [MIT](LICENSE).

Agent skills (any coding agent): [`skills/`](skills/) — getting started + data collection. Daily routine (tool-agnostic, plus Grok Bot note): [docs/daily-routine.md](docs/daily-routine.md). Vendored licenses: [docs/THIRD_PARTY.md](docs/THIRD_PARTY.md).

## Tests

The suite never creates, modifies, or deletes files under the real `data/` directory (or `dist/`). Git-dependent checks (`git check-ignore`, `publish.sh` origin) use a **temporary** git repo with a fake `origin`, so tests pass both in a git checkout and in a plain folder without `.git`.

```bash
python3 -m unittest discover -s tests -v
```

A session guard snapshots `data/` (paths + hashes) at startup and fails if anything changed. `test-fixtures/make_fixtures.py` only regenerates gitignored `test-fixtures/data/` (fictional). Do not point it at `data/`.
