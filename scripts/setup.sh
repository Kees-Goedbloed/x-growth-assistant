#!/usr/bin/env bash
# Idempotent first-run setup for a fresh clone (humans and coding agents).
# Creates a local venv, example config, gitignored data dirs, a public demo
# build, and (unless XDASH_SETUP_SKIP_TESTS=1) the unit test suite.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

echo "==> x-growth-assistant setup ($ROOT)"

if ! command -v python3 >/dev/null 2>&1; then
  echo "Refuse: python3 is required." >&2
  exit 1
fi

if [[ ! -x .venv/bin/python ]]; then
  echo "==> creating .venv (stdlib only; --without-pip)"
  if python3 -m venv --without-pip .venv; then
    :
  else
    echo "warn: python3 -m venv failed; using python3 on PATH"
    rm -rf .venv
  fi
fi
if [[ -x .venv/bin/python ]]; then
  PY=".venv/bin/python"
else
  echo "warn: venv missing; using python3 on PATH"
  PY="python3"
fi
echo "    interpreter: $PY ($($PY --version 2>&1))"

mkdir -p data/followers data/posts data/analytics-csv
if [[ ! -f data/config.json ]]; then
  cp data/config.example.json data/config.json
  echo "==> wrote data/config.json from example (gitignored; edit account / display_name)"
else
  echo "==> keeping existing data/config.json"
fi
if [[ ! -f .env ]]; then
  cp .env.example .env
  echo "==> wrote .env from example (gitignored; public mode by default)"
else
  echo "==> keeping existing .env"
fi

echo "==> public demo build (empty data/ → bundled fixtures + leak check)"
"$PY" build.py --out "$ROOT/index.html"

if [[ -d .git ]] && [[ -f scripts/check_no_real_data.sh ]]; then
  echo "==> real-data guard"
  bash scripts/check_no_real_data.sh
fi

if [[ "${XDASH_SETUP_SKIP_TESTS:-}" == "1" ]]; then
  echo "==> tests skipped (XDASH_SETUP_SKIP_TESTS=1)"
else
  echo "==> unit tests"
  "$PY" -m unittest discover -s tests -v
fi

echo
echo "Setup complete."
echo
echo "  Demo dashboard:  file://${ROOT}/index.html   (or ./serve.sh)"
echo "  Mode:            public (other people's handles stripped)"
cat <<'EOF'

Next steps
  1. Install the X Growth Assistant (Darrel) — one-click:
     https://x.ai/bot/GV9QXOW5kYS9o8Rq6MFFi
     Getting started asks for handle, language, timezone, X login, this repo
     path, and data/config.json.
  2. Point its followers-dir at data/followers/ so snapshots land on:
       data/followers/snapshot-YYYYMMDD-HHMMSS.json
       data/followers/latest.json
     Unmodified X Analytics CSVs go in data/analytics-csv/.
     Then python3 build.py picks them up with no extra flags.
  3. Edit data/config.json (account, display_name). Never commit it, .env,
     snapshots, CSVs, or assets/avatar.*.
  4. Private HTML: python3 build.py --mode private
     Hosted private: DASHBOARD_MODE=private plus DASHBOARD_USER and
     DASHBOARD_PASSWORD (see .env.example).
  5. Public builds always run scripts/check_public_leaks.py and must pass.

See AGENTS.md and README.md (What stays private, what is public).
EOF
