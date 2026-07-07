#!/usr/bin/env bash
# reset-ceremony-markers.sh — SessionStart hook.
#
# Clears the closing-ceremony work-markers for THIS session only, so a fresh
# start (or /clear) never inherits "did work" / "touched repo" state — while
# leaving other live sessions' markers alone. Markers are per-session files
# under ~/.claude/ceremony-markers/<session_id>.* ; the old behavior (unconditionally
# deleting two GLOBAL marker files) cross-wiped concurrent sessions' state every
# time any session started. Marker files older than 7 days are garbage-collected
# (dead sessions), as are the legacy global files once stale. The unpushed-commits
# loop-cap counter (.ceremony-block-count) is intentionally NOT cleared here —
# that one tracks consecutive hard-block failures across stops within the same
# stuck session, not per-session state, and closing-ceremony.sh already self-clears
# it once the underlying condition resolves.
#
# The escape hatches for the ceremony gate used to be silent. `.skip-ceremony`
# sat armed for a full day no-op'ing the whole gate and nothing announced it.
# Now, at every session start:
#   - an armed `.skip-ceremony` is announced loudly with its age, and
#     AUTO-EXPIRED (deleted, with notice) once older than 24h — a disaster
#     hatch for a stuck loop, not a standing off-switch;
#   - an armed `.skip-mini-sync-once` is announced (it is already one-shot /
#     self-consuming, so no expiry needed);
#   - every detection/expiry event is appended to the bypass ledger
#     ~/.claude/ceremony-bypass.log (timestamp, event, file mtime).
# SessionStart stdout lands in the model's context, so the notice reaches the
# session that must act on it, not just a human tail-ing a log.
#
# Test seams (override defaults; used by the test harness only):
#   CEREMONY_SKIP_FILE_OVERRIDE, CEREMONY_MINI_SKIP_OVERRIDE,
#   CEREMONY_BYPASS_LOG_OVERRIDE, CEREMONY_SESSION_ID_OVERRIDE,
#   CEREMONY_MARKERS_DIR_OVERRIDE
set -u

MARKERS_DIR="${CEREMONY_MARKERS_DIR_OVERRIDE:-$HOME/.claude/ceremony-markers}"

# Current session's id from the SessionStart JSON envelope on stdin (same
# defensive parse as closing-ceremony.sh; empty → only GC + legacy cleanup).
SID="${CEREMONY_SESSION_ID_OVERRIDE:-$(python3 -c '
import json, re, sys
try:
    sid = json.load(sys.stdin).get("session_id") or ""
except Exception:
    sid = ""
print(sid if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", sid) else "")
' 2>/dev/null || true)}"

# 1. Reset THIS session's markers only (fresh start / post-/clear).
#    Includes the loop-cap block counter, per-session (it was global — concurrent
#    blocked sessions burned each other's cap and downgraded the gate early; same
#    bug class as the markers).
if [ -n "$SID" ]; then
  rm -f "$MARKERS_DIR/$SID.did-work" "$MARKERS_DIR/$SID.touched-repos" \
        "$MARKERS_DIR/$SID.block-count"
fi

# 2. GC: marker files older than 7 days belong to dead sessions; the legacy
#    GLOBAL marker files (pre-session-markers, or written by the no-session_id
#    fallback) get the same treatment instead of the old unconditional delete —
#    an unconditional delete here is the cross-wipe bug.
[ -d "$MARKERS_DIR" ] && find "$MARKERS_DIR" -maxdepth 1 -type f -mtime +7 -delete 2>/dev/null
find "$HOME/.claude" -maxdepth 1 \( -name .ceremony-did-work -o -name .ceremony-touched-repos \) -mtime +7 -delete 2>/dev/null

SKIP_FILE="${CEREMONY_SKIP_FILE_OVERRIDE:-$HOME/.claude/.skip-ceremony}"
MINI_SKIP_FILE="${CEREMONY_MINI_SKIP_OVERRIDE:-$HOME/.claude/.skip-mini-sync-once}"
BYPASS_LOG="${CEREMONY_BYPASS_LOG_OVERRIDE:-$HOME/.claude/ceremony-bypass.log}"

ledger() { # ledger <event> <file> <mtime-epoch|->
  printf '%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" "$3" >> "$BYPASS_LOG"
}

if [ -f "$SKIP_FILE" ]; then
  now=$(date +%s)
  mt=$(stat -f %m "$SKIP_FILE" 2>/dev/null || stat -c %Y "$SKIP_FILE" 2>/dev/null || echo "$now")
  age=$(( now - mt ))
  age_h=$(( age / 3600 )); age_m=$(( (age % 3600) / 60 ))
  if [ "$age" -gt 86400 ]; then
    rm -f "$SKIP_FILE"
    ledger "expired-removed" "$SKIP_FILE" "$mt"
    echo "🚨 CEREMONY BYPASS EXPIRED: $SKIP_FILE was armed for ${age_h}h ${age_m}m (>24h) — removed at session start. The closing-ceremony gate is ACTIVE again. (logged to $BYPASS_LOG)"
  else
    ledger "detected-armed" "$SKIP_FILE" "$mt"
    echo "⚠️  CEREMONY BYPASS ARMED: $SKIP_FILE exists (age ${age_h}h ${age_m}m) — the closing-ceremony gate is currently a NO-OP for every stop. It self-expires at 24h. If this session doesn't need it, delete it now: rm $SKIP_FILE  (logged to $BYPASS_LOG)"
  fi
fi

if [ -f "$MINI_SKIP_FILE" ]; then
  now=$(date +%s)
  mt=$(stat -f %m "$MINI_SKIP_FILE" 2>/dev/null || stat -c %Y "$MINI_SKIP_FILE" 2>/dev/null || echo "$now")
  ledger "detected-armed" "$MINI_SKIP_FILE" "$mt"
  echo "⚠️  MINI-SYNC OVERRIDE ARMED: $MINI_SKIP_FILE exists — the next server-DIVERGED hard block will be waived (one-shot; it self-consumes). If not intended, delete it: rm $MINI_SKIP_FILE  (logged to $BYPASS_LOG)"
fi

exit 0
