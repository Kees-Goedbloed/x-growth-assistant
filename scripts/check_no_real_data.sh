#!/usr/bin/env bash
# Fail if git-tracked files look like real dashboard inputs or secrets.
# Run from the repository root (CI does).
set -euo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

fail() { echo "check_no_real_data: $*" >&2; exit 1; }

# Nested data files must be ignored. `data/*` + `!data/**/` re-includes
# subfolders, so git add -A would stage followers/posts/CSV/research.
for p in data/followers/snapshot-2026-01-01.json data/followers/latest.json \
         data/posts/posts-1.json data/analytics-csv/x.csv \
         data/research/reply_targets.json data/research/README-onderzoek.md \
         data/config.json data/target_accounts.json data/public_allowlist.json; do
  git check-ignore -q -- "$p" || fail "expected gitignore to ignore $p (use data/** not data/*)"
done
for p in data/followers/.gitkeep data/config.example.json \
         data/.gitkeep data/posts/.gitkeep data/analytics-csv/.gitkeep \
         data/target_accounts.example.json data/public_allowlist.example.json \
         assets/og-image.png .env.example; do
  if git check-ignore -q -- "$p"; then
    fail "gitignore must not ignore $p"
  fi
done
for p in assets/avatar.jpg assets/avatar.jpeg assets/avatar.webp assets/avatar.png \
         .avatar-cache/meta.json data/.avatar-cache/avatar.png; do
  git check-ignore -q -- "$p" || fail "expected gitignore to ignore $p"
done

mapfile -t TRACKED < <(git ls-files -z | tr '\0' '\n' | sed '/^$/d')

is_keep_data() {
  local rel="$1" base
  base="$(basename "$rel")"
  [[ "$base" == ".gitkeep" ]] && return 0
  [[ "$base" == *.example.* ]] && return 0
  [[ "$base" == *.example ]] && return 0
  return 1
}

for f in "${TRACKED[@]}"; do
  case "$f" in
    data|/*data/*|data/*)
      if [[ "$f" == data/* ]] || [[ "$f" == data ]]; then
        if ! is_keep_data "$f"; then
          fail "tracked file under data/ is not a .gitkeep or example: $f"
        fi
      fi
      ;;
  esac
done

# Real-data filenames outside test-fixtures/ (generated fixtures are gitignored).
# .env.example is the committed template; .env / .env.local stay ignored.
pat_real='(^|/)(snapshot-[^/]*\.json|latest\.json|posts-[^/]*\.jsonl?|reply_targets\.json|README-onderzoek\.md|x-followers[^/]*|\.env(\..+)?)$'
pat_csv='\.csv$'

for f in "${TRACKED[@]}"; do
  case "$f" in
    test-fixtures/*) continue ;;
  esac
  base="$(basename "$f")"
  if [[ "$base" == ".env.example" ]]; then
    continue
  fi
  if [[ "$f" =~ $pat_real || "$base" == "latest.json" || "$base" == "reply_targets.json" ]]; then
    fail "tracked real-data filename outside test-fixtures/: $f"
  fi
  if [[ "$f" =~ $pat_csv ]]; then
    fail "tracked CSV outside test-fixtures/: $f"
  fi
  if [[ "$base" == posts-*.json || "$base" == posts-*.jsonl || "$base" == snapshot-*.json ]]; then
    fail "tracked snapshot/posts file outside test-fixtures/: $f"
  fi
  if [[ "$base" == avatar.jpg || "$base" == avatar.jpeg || "$base" == avatar.webp || "$base" == avatar.png ]]; then
    fail "tracked owner avatar (do not commit the real photo): $f"
  fi
done

# Token-like strings in tracked text files. Exclude this script so the
# pattern itself is not a false positive.
token_pat='ghp_|github_pat_|nfp_|xox[baprs]-|AKIA[0-9A-Z]{8}|BEGIN [A-Z ]*PRIVATE KEY'
tmp="$(mktemp)"
trap 'rm -f "$tmp"' EXIT
git grep -I -n -E "$token_pat" -- . ':!scripts/check_no_real_data.sh' >"$tmp" && true
if [[ -s "$tmp" ]]; then
  echo "check_no_real_data: token-like string in tracked files:" >&2
  cat "$tmp" >&2
  exit 1
fi

echo "check_no_real_data: OK (${#TRACKED[@]} tracked files)"
