# Security policy

## What this project stores

This builder reads **local** X analytics CSVs, post JSON, and follower snapshots from `data/` (gitignored) and writes a single HTML file. It does not call the X API with a token.

## Reporting a vulnerability

Open a **private GitHub Security Advisory** on this repository
(Security → Advisories → New draft security advisory). That is the
disclosure channel. Do not file a public issue that includes real exports,
passwords, or other people's handles.

## What must never be committed

- `data/config.json`, snapshots, CSVs, research dumps, `assets/avatar.*`
- `.env`, Netlify tokens, `DASHBOARD_PASSWORD`, site IDs
- Built `index.html` / `dist/` from a real-data private build

CI runs `scripts/check_no_real_data.sh`, `scripts/check_public_leaks.py` on public HTML, and gitleaks. Public builds fail if another account's handle remains as a handle (`@name`, profile URL, or structured field).

## Hosted private dashboard

Set `DASHBOARD_MODE=private` together with `DASHBOARD_USER` and `DASHBOARD_PASSWORD`. The Netlify edge function fail-closes (HTTP 503) if credentials are missing. Unset / garbage `DASHBOARD_MODE` keeps Basic Auth **on**.

## History

HEAD is kept free of real exports and secrets. Older commits (before the OSS prep) may still mention an owner handle or example third-party handles. Rewriting history needs an explicit owner decision; this project will not force-push.
