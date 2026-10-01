#!/usr/bin/env bash
# Snapshot default-prefix temp dirs (/tmp/tmp* and $TMPDIR/tmp*), run a
# command, and fail if any new tmp* directories remain.
set -euo pipefail

if [ "$#" -lt 1 ]; then
  echo "usage: $0 command [args...]" >&2
  exit 2
fi

list_tmp_dirs() {
  local roots=("/tmp")
  local r
  if [ -n "${TMPDIR:-}" ]; then
    roots+=("${TMPDIR%/}")
  fi
  for r in "${roots[@]}"; do
    [ -d "$r" ] || continue
    find "$r" -maxdepth 1 -type d -name 'tmp*' 2>/dev/null || true
  done | sort -u
}

before_file="$(mktemp /tmp/xdash-hygiene-before-XXXXXX)"
after_file="$(mktemp /tmp/xdash-hygiene-after-XXXXXX)"
cleanup_lists() { rm -f "$before_file" "$after_file"; }
trap cleanup_lists EXIT

list_tmp_dirs > "$before_file"

set +e
"$@"
status=$?
set -e

list_tmp_dirs > "$after_file"
new="$(comm -13 "$before_file" "$after_file" || true)"

if [ -n "$new" ]; then
  echo "check_tmp_hygiene: new leftover /tmp/tmp* directories after: $*" >&2
  printf '%s\n' "$new" >&2
  if [ "$status" -eq 0 ]; then
    exit 1
  fi
  exit "$status"
fi

exit "$status"
