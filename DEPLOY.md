# Deploy the X growth dashboard (public + private)

Two Netlify sites, **same repo / same code**, both deployed by `scripts/publish.sh` with the
Netlify CLI. Sites are **not** Git-linked. Real snapshots and CSVs stay on the build
machine; they never enter git.

Suggested hostnames (replace with your own; nothing here is wired to a specific org):

- Public: `https://dashboard.example.com` — `DASHBOARD_MODE=public`, no Basic Auth
- Private: `https://dashboard-private.example.com` — Basic Auth (fail closed)

You cannot create sites or DNS from this pull request; do the steps below in the Netlify UI.

## Edge functions and CLI deploys (what we checked)

Netlify docs (*Get started with Edge Functions*): **manual CLI deploys of edge functions
need Netlify CLI 12.2.8 or later**. The default directory is
`YOUR_BASE_DIRECTORY/netlify/edge-functions` (overridable with `[build].edge_functions`
in `netlify.toml`). Docs warn that this directory should stay **outside** the publish
folder.

CLI *Get started*: `netlify deploy --dir` sets the **publish** folder. Functions are
resolved from command flags, then `netlify.toml` at the project root, then the UI — not
from inside `--dir`.

This repo therefore:

1. Builds HTML into a temp publish dir (`index.html`, `robots.txt`, `_headers`, `assets/`).
2. Runs `netlify deploy --prod --dir <that-dir> --site <id>` from the **repository root**
   so `netlify.toml` and `netlify/edge-functions/auth.ts` are included.
3. Passes `--no-build` so a newer Netlify CLI that builds by default cannot run
   `scripts/netlify-build.sh` against empty git `data/` (that script is fail-closed
   on purpose). Edge functions are still bundled from `netlify/edge-functions`
   (CLI ≥ 12.2.8; netlify/cli#4562 bundled them even without `--build`).

## 1. Create two Netlify sites (once, not Git-linked)

For **each** site:

1. [Netlify](https://app.netlify.com/) → **Add new site** → **Deploy manually** / import
   without connecting Git (do not enable Git continuous deployment).
2. Note the **Project ID** (still called `site_id` in the CLI): one public, one private.
3. Public domain: **Domain management** → your public hostname (example: `dashboard.example.com`).
4. Private domain: your private hostname (example: `dashboard-private.example.com`).

`scripts/netlify-build.sh` refuses to run when `data/` has no real inputs, so an
accidental Git-linked site cannot publish an empty dashboard. A local demo with no
exports is `python3 build.py` (bundled fixtures, public HTML).

## 2. Environment variables

See `.env.example` for the same names. Never commit `.env`.

### Public site

| Variable | Value |
|---|---|
| `DASHBOARD_MODE` | exactly `public` |
| `SITE_URL` or `PUBLIC_SITE_URL` | optional canonical origin (`https://dashboard.example.com`) so public Open Graph tags get an absolute `og:image`. `data/config.json` `site_url` wins if set. |

Do **not** set `DASHBOARD_USER` / `DASHBOARD_PASSWORD` on the public site (unused when
mode is `public`).

HTML built by `netlify-build.sh` is **public** when `DASHBOARD_MODE` is unset or
`public` (handles stripped + leak check). The edge function still treats anything
other than the exact string `public` as private auth (fail closed). Set `public`
explicitly on the shareable site so auth is off.

### Private site

| Variable | Value |
|---|---|
| `DASHBOARD_MODE` | exactly `private` (required; do not leave this unset) |
| `DASHBOARD_USER` | dashboard username |
| `DASHBOARD_PASSWORD` | strong password, marked **secret**, all deploy contexts |

Private is opt-in: `DASHBOARD_MODE=private` **and** both credentials. Missing/empty
credentials → the build script refuses, and the edge function returns **503** on
every path if a private site is reached without them.

Unset / empty / garbage `DASHBOARD_MODE` → edge auth stays **on** (fail closed).
`netlify-build.sh` refuses a value that is not `public` or `private`.

Redeploy after changing env vars.

## 3. Box environment for `publish.sh`

Required (no machine-specific defaults; the script exits if any is missing):

```bash
export SOURCE_DATA_DIR=/path/to/inputs          # posts/, analytics-csv/, config.json, optional target_accounts.json
export X_FOLLOWERS_DIR=/path/to/follower-json   # snapshot JSON, read-only
export NETLIFY_SITE_ID_PUBLIC=…                 # public Project ID
export NETLIFY_SITE_ID_PRIVATE=…                # private Project ID
export NETLIFY_AUTH_TOKEN=…                     # personal access token; never committed
```

`NETLIFY_SITE_ID_PUBLIC` and `NETLIFY_SITE_ID_PRIVATE` must differ. The script refuses
to deploy a build whose `<meta name="x-dashboard-mode">` does not match the target site.

```bash
cd /path/to/x-growth-assistant
./scripts/publish.sh           # build both modes, leak-check public, netlify deploy --prod
./scripts/publish.sh --dry-run # build + checks, no deploy, no git
```

`publish.sh` never runs `git add` / `git commit` / `git push`.

It only runs from a git checkout whose `origin` is `Kees-Goedbloed/x-growth-assistant`.
On a fork, set `XGA_ALLOWED_REPO=<owner>/<repo>` (your fork) so the origin guard accepts it.

Needs Netlify CLI ≥ 12.2.8 (`netlify` on PATH, or `npx --yes netlify-cli`).

### Cron example

```cron
# Every day at 07:15 in the box timezone
15 7 * * * cd /path/to/x-growth-assistant && ./scripts/publish.sh >> /var/log/x-growth-publish.log 2>&1
```

## 4. Verify

Public (no auth, OG tags, robots allow) — replace the hostname with yours:

```bash
curl -sI https://dashboard.example.com
# Expect: HTTP 200
# No WWW-Authenticate
# No X-Robots-Tag: noindex

curl -s https://dashboard.example.com | grep -E 'og:title|twitter:card|x-dashboard-mode'
# Expect: og:title, twitter:card=summary_large_image, content="public"

curl -s https://dashboard.example.com/robots.txt
# Expect: Allow: /
```

Private (auth required):

```bash
curl -sI https://dashboard-private.example.com
# Expect: HTTP 401 (or 503 if DASHBOARD_USER/PASSWORD unset)
# WWW-Authenticate: Basic realm="X dashboard", charset="UTF-8"
# X-Robots-Tag: noindex, nofollow
# Cache-Control: private, no-store

curl -sI --user "$DASHBOARD_USER:$DASHBOARD_PASSWORD" https://dashboard-private.example.com
# Expect: HTTP 200

curl -sI https://dashboard-private.example.com/robots.txt
# Expect: 401
curl -sI --user "$DASHBOARD_USER:$DASHBOARD_PASSWORD" https://dashboard-private.example.com/robots.txt
# Expect: 200, body Disallow: /
```

Fail closed if `DASHBOARD_MODE` is unset on the private site:

```bash
# With DASHBOARD_MODE empty/missing/garbage and credentials set:
curl -sI https://dashboard-private.example.com
# Expect: 401 (auth still on), not a public 200
```

Raw `data/` must not be reachable (404 with auth on private; 404 on public).

## 5. Rotate the private password

1. Private site → Environment variables → change `DASHBOARD_PASSWORD` (all contexts) →
   run `./scripts/publish.sh` (or trigger a deploy of the last built private dist).
2. Share the new password out-of-band. HTTP Basic has no server-side session.

Never commit `.env`.

## 6. Roll back

**Site (Netlify):** Deploys → open a previous successful production deploy → **Publish deploy**
(do this on the site that went wrong).

**Code:** revert the application commit on `main` and run `publish.sh` again (or restore
an older Netlify deploy). There is no data history in git.

## Local builds

```bash
python3 build.py
# empty ./data → demo fixtures, public HTML, leak check

python3 build.py --data test-fixtures/data --mode public --out index.public.html --today 2026-09-25
python3 build.py --data test-fixtures/data --mode private --out index.test.html --today 2026-09-25
```

`python3 build.py` still writes `index.html` in the repo root for `file://` use.
Netlify publishes only the CLI `--dir` folder (never the repo root).
