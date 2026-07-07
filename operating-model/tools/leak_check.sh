#!/usr/bin/env bash
# leak_check.sh — gate: no private identifier ever lands in this public tree.
#
# The pattern list is INTENTIONALLY external: a leak checker whose pattern
# list ships in the repo IS the leak. Keep your real list outside the repo
# (e.g. ~/.config/leak_patterns.txt), one extended-regex pattern per line,
# comments with '#'. Point at it with LEAK_PATTERNS_FILE.
#
# Usage:
#   LEAK_PATTERNS_FILE=~/.config/leak_patterns.txt ./tools/leak_check.sh [dir]
#
# Exit 0 = clean; exit 1 = hits found (printed); exit 2 = setup error.
# Wire it as a pre-commit hook and/or CI check on the public repo.
set -euo pipefail

TARGET_DIR="${1:-$(cd "$(dirname "$0")/.." && pwd)}"
PATTERNS_FILE="${LEAK_PATTERNS_FILE:-}"

# Built-in generic floor: things that are never OK in a sanitized public tree,
# regardless of whose tree it is.
BUILTIN_PATTERNS=(
  '/Users/[a-z][a-z0-9_-]+'            # macOS home dirs carry usernames
  '/home/[a-z][a-z0-9_-]+'             # ditto Linux
  '192\.168\.[0-9]+\.[0-9]+'           # real RFC1918 LAN addresses (use 192.0.2.x TEST-NET in docs)
  '10\.[0-9]+\.[0-9]+\.[0-9]+'         # ditto
  '[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.(com|net|org|io|me)'  # email addresses
  'sk-ant-[A-Za-z0-9-]+'               # Anthropic API keys
  'ghp_[A-Za-z0-9]+|github_pat_[A-Za-z0-9_]+'              # GitHub tokens
  'AKIA[0-9A-Z]{16}'                   # AWS access key ids
  'BEGIN (RSA|OPENSSH|EC) PRIVATE KEY' # private keys
)

fail=0
run_grep() {
  local pattern="$1" label="$2"
  # -I skips binaries; exclude .git and this script's own pattern docs
  if hits=$(grep -rInE --exclude-dir=.git "$pattern" "$TARGET_DIR" 2>/dev/null | grep -v 'tools/leak_check.sh' || true); [ -n "$hits" ]; then
    echo "LEAK [$label]:"
    echo "$hits" | sed 's/^/  /'
    fail=1
  fi
}

for p in "${BUILTIN_PATTERNS[@]}"; do
  run_grep "$p" "builtin"
done

if [ -n "$PATTERNS_FILE" ]; then
  if [ ! -f "$PATTERNS_FILE" ]; then
    echo "ERROR: LEAK_PATTERNS_FILE=$PATTERNS_FILE not found" >&2
    exit 2
  fi
  while IFS= read -r line; do
    [ -z "$line" ] && continue
    case "$line" in \#*) continue ;; esac
    run_grep "$line" "private-list"
  done < "$PATTERNS_FILE"
else
  echo "NOTE: no LEAK_PATTERNS_FILE set — only the generic builtin floor was checked." >&2
fi

if [ "$fail" -eq 0 ]; then
  echo "leak_check: CLEAN ($TARGET_DIR)"
fi
exit "$fail"
