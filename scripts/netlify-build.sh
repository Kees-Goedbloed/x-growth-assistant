#!/usr/bin/env bash
# Git-linked Netlify builds are not supported: real data must never live in git.
# Fail closed when data/ has no real inputs so an accidental Git-linked site
# never publishes an empty dashboard. Production deploy is scripts/publish.sh.
#
# Shareable default is public. Private HTML requires DASHBOARD_MODE=private
# plus DASHBOARD_USER and DASHBOARD_PASSWORD (same names the edge function uses).
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

has_real=0
if compgen -G "$ROOT/data/analytics-csv/*.csv" > /dev/null; then has_real=1; fi
if compgen -G "$ROOT/data/posts/*.json" > /dev/null; then has_real=1; fi
if compgen -G "$ROOT/data/posts/*.jsonl" > /dev/null; then has_real=1; fi
if compgen -G "$ROOT/data/followers/*.json" > /dev/null; then has_real=1; fi

if [[ "$has_real" -eq 0 ]]; then
  echo "Refuse: data/ has no real inputs (CSV, posts, or follower snapshots)." >&2
  echo "Do not Git-link this site. Build locally and deploy with scripts/publish.sh." >&2
  echo "For a local demo with no data, run: python3 build.py" >&2
  exit 1
fi

MODE="${DASHBOARD_MODE:-public}"
if [[ "$MODE" == "private" ]]; then
  if [[ -z "${DASHBOARD_USER:-}" || -z "${DASHBOARD_PASSWORD:-}" ]]; then
    echo "Refuse: private mode requires DASHBOARD_USER and DASHBOARD_PASSWORD." >&2
    exit 1
  fi
elif [[ "$MODE" != "public" ]]; then
  echo "Refuse: DASHBOARD_MODE must be public or private (got ${MODE})." >&2
  exit 1
fi

mkdir -p dist
python3 build.py --data "$ROOT/data" --mode "$MODE" --out dist/index.html
if [[ -e dist/data || -e dist/test-fixtures || -e dist/build.py ]]; then
  echo "Refuse: raw source leaked into dist/" >&2
  exit 1
fi
if [[ "$MODE" == "public" ]]; then
  python3 "$ROOT/scripts/check_public_leaks.py" dist/index.html "$ROOT/data"
fi
