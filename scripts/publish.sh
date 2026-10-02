#!/usr/bin/env bash
# Build on this machine from SOURCE_DATA_DIR + X_FOLLOWERS_DIR, then deploy
# finished dist folders with the Netlify CLI. Never stages, commits, or pushes data.
#
# Required env (no machine-specific defaults):
#   SOURCE_DATA_DIR          posts/, analytics-csv/, config.json, optional target_accounts.json
#   X_FOLLOWERS_DIR          follower snapshot JSON (read-only)
#   NETLIFY_SITE_ID_PUBLIC
#   NETLIFY_SITE_ID_PRIVATE
#   NETLIFY_AUTH_TOKEN
#
# Edge functions (Netlify CLI docs, Get started with Edge Functions):
#   Manual deploys of edge functions need Netlify CLI 12.2.8+. Functions live in
#   netlify/edge-functions (or [build].edge_functions) at the project root, NOT
#   inside --dir. `netlify deploy --prod --dir <publish> --site <id>` from this
#   repo root picks up netlify.toml + netlify/edge-functions. CLI 12.2.8+ also
#   bundles edge functions without --build (netlify/cli#4562). We pass
#   --no-build so a newer CLI that builds by default cannot run
#   scripts/netlify-build.sh against empty git data/.
set -euo pipefail

# Origin guard: publish only from a checkout of the code repo (never from a
# data repo). Default is the canonical public repo; a fork sets
# XGA_ALLOWED_REPO=<owner>/<repo> (case-insensitive) to allow its own origin.
DEFAULT_ALLOWED_REPO="kees-goedbloed/x-growth-assistant"

allowed_repo() {
  local repo="${XGA_ALLOWED_REPO:-$DEFAULT_ALLOWED_REPO}"
  printf '%s\n' "${repo,,}"
}

origin_repo() {
  local url="${1:-}"
  url="${url%.git}"
  url="${url%/}"
  if [[ "$url" =~ [Gg]ithub\.com[:/]+([^/]+/[^/[:space:]]+)$ ]]; then
    printf '%s\n' "${BASH_REMATCH[1]}"
  fi
}

origin_allowed() {
  local repo
  repo="$(origin_repo "${1:-}")"
  [[ -n "$repo" && "${repo,,}" == "$(allowed_repo)" ]]
}

require_origin() {
  local url repo
  if ! url="$(git remote get-url origin 2>/dev/null)"; then
    echo "Weiger: geen git-remote 'origin'. Clone de repo met git (zip-downloads hebben geen origin)." >&2
    exit 1
  fi
  repo="$(origin_repo "$url")"
  if ! origin_allowed "$url"; then
    echo "Weiger: origin is niet $(allowed_repo) (gevonden: ${repo:-onbekend}). Fork? Zet XGA_ALLOWED_REPO=<owner>/<repo>." >&2
    exit 1
  fi
}

require_env() {
  local missing=0 name
  for name in SOURCE_DATA_DIR X_FOLLOWERS_DIR NETLIFY_SITE_ID_PUBLIC NETLIFY_SITE_ID_PRIVATE NETLIFY_AUTH_TOKEN; do
    if [[ -z "${!name:-}" ]]; then
      echo "Ontbrekende variabele: $name" >&2
      missing=1
    fi
  done
  if [[ "$missing" -eq 1 ]]; then
    echo "Zet SOURCE_DATA_DIR, X_FOLLOWERS_DIR, NETLIFY_SITE_ID_PUBLIC, NETLIFY_SITE_ID_PRIVATE en NETLIFY_AUTH_TOKEN." >&2
    exit 1
  fi
  if [[ "${NETLIFY_SITE_ID_PUBLIC}" == "${NETLIFY_SITE_ID_PRIVATE}" ]]; then
    echo "Weiger: NETLIFY_SITE_ID_PUBLIC en NETLIFY_SITE_ID_PRIVATE moeten verschillen." >&2
    exit 1
  fi
  if [[ ! -d "$SOURCE_DATA_DIR" ]]; then
    echo "SOURCE_DATA_DIR is geen map: $SOURCE_DATA_DIR" >&2
    exit 1
  fi
  if [[ ! -d "$X_FOLLOWERS_DIR" ]]; then
    echo "X_FOLLOWERS_DIR is geen map: $X_FOLLOWERS_DIR" >&2
    exit 1
  fi
}

copy_matching() {
  local src="$1" dest="$2"
  shift 2
  mkdir -p "$dest"
  if [[ ! -d "$src" ]]; then
    echo "Bronmap ontbreekt (overgeslagen): $src"
    return 0
  fi
  local f copied=0
  shopt -s nullglob
  for f in "$src"/*; do
    [[ -f "$f" ]] || continue
    local base="${f##*/}" ok=0 pat
    for pat in "$@"; do
      # shellcheck disable=SC2254
      if [[ "$base" == $pat ]]; then
        ok=1
        break
      fi
    done
    if [[ "$ok" -eq 1 ]]; then
      cp -p "$f" "$dest/"
      copied=$((copied + 1))
    fi
  done
  shopt -u nullglob
  echo "Gekopieerd: $copied bestand(en) $src -> $dest"
}

meta_mode() {
  python3 - "$1" <<'PY'
import re, sys
html = open(sys.argv[1], encoding="utf-8").read()
m = re.search(r'name=["\']x-dashboard-mode["\']\s+content=["\']([^"\']+)["\']', html)
if not m:
    m = re.search(r'content=["\']([^"\']+)["\']\s+name=["\']x-dashboard-mode["\']', html)
print(m.group(1) if m else "")
PY
}

netlify_cmd() {
  if command -v netlify >/dev/null 2>&1; then
    printf '%s\n' netlify
  else
    printf '%s\n' "npx --yes netlify-cli"
  fi
}

stage_inputs() {
  local work="$1"
  mkdir -p "$work/data/followers" "$work/data/posts" "$work/data/analytics-csv"
  copy_matching "$X_FOLLOWERS_DIR" "$work/data/followers" "*.json"
  copy_matching "$SOURCE_DATA_DIR/posts" "$work/data/posts" "*.json" "*.jsonl"
  copy_matching "$SOURCE_DATA_DIR/analytics-csv" "$work/data/analytics-csv" "*.csv"
  copy_matching "$SOURCE_DATA_DIR/followers" "$work/data/followers" "*.json"
  if [[ -f "$SOURCE_DATA_DIR/config.json" ]]; then
    cp -p "$SOURCE_DATA_DIR/config.json" "$work/data/config.json"
    echo "Gekopieerd: config.json"
  fi
  if [[ -f "$SOURCE_DATA_DIR/target_accounts.json" ]]; then
    cp -p "$SOURCE_DATA_DIR/target_accounts.json" "$work/data/target_accounts.json"
    echo "Gekopieerd: target_accounts.json"
  fi
  if [[ -f "$SOURCE_DATA_DIR/public_allowlist.json" ]]; then
    cp -p "$SOURCE_DATA_DIR/public_allowlist.json" "$work/data/public_allowlist.json"
    echo "Gekopieerd: public_allowlist.json"
  fi
}

build_mode() {
  local work="$1" mode="$2" dest="$3"
  mkdir -p "$dest"
  python3 "$ROOT/build.py" --data "$work/data" --mode "$mode" --out "$dest/index.html"
  local got
  got="$(meta_mode "$dest/index.html")"
  if [[ "$got" != "$mode" ]]; then
    echo "Weiger: build mode is '$got', verwacht '$mode'." >&2
    exit 1
  fi
}

deploy_dir() {
  local dir="$1" site="$2" label="$3"
  local bin
  bin="$(netlify_cmd)"
  # Run from repo root so netlify.toml + netlify/edge-functions are included.
  # --dir is the publish directory only (index.html, robots.txt, _headers, assets).
  echo "Deploy $label -> site $site (dir=$dir)"
  # shellcheck disable=SC2086
  (cd "$ROOT" && $bin deploy --prod --no-build --dir "$dir" --site "$site" --message "x-growth-assistant $label")
}

main() {
  local dry=0
  if [[ "${1:-}" == "--dry-run" ]]; then
    dry=1
  elif [[ -n "${1:-}" ]]; then
    echo "Onbekende optie: $1 (alleen --dry-run is toegestaan)" >&2
    exit 2
  fi

  ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
  cd "$ROOT"

  require_origin
  require_env

  python3 test-fixtures/make_fixtures.py
  local tmp_test_dir tmp_test
  tmp_test_dir="$(mktemp -d /tmp/xdash-test.XXXXXX)"
  tmp_test="$tmp_test_dir/index.html"
  python3 build.py --data test-fixtures/data --no-followers --out "$tmp_test" --today 2026-09-25 --mode private
  grep -q TESTFIXTURE "$tmp_test"
  rm -rf "$tmp_test_dir"

  local work pub priv
  work="$(mktemp -d /tmp/xdash-publish.XXXXXX)"
  pub="$work/public"
  priv="$work/private"
  trap 'rm -rf "$work"' EXIT

  echo "Kopieer inputs naar tijdelijke map (niet naar git data/)"
  export XDASH_AVATAR_CACHE="${XDASH_AVATAR_CACHE:-$SOURCE_DATA_DIR/.avatar-cache}"
  if [[ -n "${PUBLIC_SITE_URL:-}" && -z "${SITE_URL:-}" ]]; then
    export SITE_URL="$PUBLIC_SITE_URL"
  fi
  stage_inputs "$work"
  build_mode "$work" private "$priv"
  build_mode "$work" public "$pub"

  python3 "$ROOT/scripts/check_public_leaks.py" "$pub/index.html" "$work/data" --followers-dir "$X_FOLLOWERS_DIR"

  if [[ "$(meta_mode "$pub/index.html")" != "public" ]]; then
    echo "Weiger: publieke build heeft geen meta mode=public." >&2
    exit 1
  fi
  if [[ "$(meta_mode "$priv/index.html")" != "private" ]]; then
    echo "Weiger: privé-build heeft geen meta mode=private." >&2
    exit 1
  fi

  if [[ "$dry" -eq 1 ]]; then
    echo "Dry-run: builds + leak-check OK. Geen netlify deploy, geen git."
    exit 0
  fi

  deploy_dir "$pub" "$NETLIFY_SITE_ID_PUBLIC" "public"
  deploy_dir "$priv" "$NETLIFY_SITE_ID_PRIVATE" "private"
  echo "Gepubliceerd (CLI deploy, geen git data-push)."
}

if [[ "${BASH_SOURCE[0]}" == "$0" ]]; then
  main "$@"
fi
