#!/usr/bin/env bash
# closing-ceremony.sh — Stop hook: enforce end-of-effort closing ceremony.
#
# Why: end-of-effort artifacts (GitHub issue updates + a session-log digest)
# were prose-in-CLAUDE.md = a habit, so they kept getting skipped. When a later
# session resumes with nothing durable to read, it re-derives context from
# transcripts/code at a 300-800k-token tax. This makes the write-half a gate.
#
# Contract (Claude Code Stop hook):
#   exit 2  -> BLOCK the stop; stderr is fed back to the model, which continues.
#   exit 0  -> allow the stop; stdout is surfaced as an advisory.
#
# Policy:
#   HARD BLOCK (exit 2) on any of:
#     - unpushed commits in a lab repo — self-clearing on push.
#     - uncommitted changes in a repo THIS session edited (see mark-session-work.py)
#       — self-clearing on commit+push.
#     - real work happened this session (a commit landed today, or an in-scope
#       file was edited) with no fresh session log yet — self-clearing on
#       writing the digest.
#   The block message carries the full ceremony checklist either way.
#   SOFT NUDGE (exit 0 + stdout) on uncommitted changes in a repo NOT touched
#     this session (old/unrelated WIP), or server checkout drift.
#   SILENT PASS (exit 0) otherwise.
#
# Safety valves against a global lock-out:
#   - scoped: only acts when the session cwd is inside the lab workspace.
#   - escape hatch: `touch ~/.claude/.skip-ceremony` or export CLAUDE_SKIP_CEREMONY=1.
#   - loop cap: after 3 consecutive hard blocks (any reason below), downgrade to advisory.
#
# Per-session markers (ceremony-markers/<sid>.did-work, .touched-repos)
# let this script tell freshly-dirtied-by-THIS-session state apart from old
# unrelated WIP a human left dirty on purpose.
#
# Test seams (override defaults; used by the test harness only):
#   CEREMONY_WORKSPACE_OVERRIDE, CEREMONY_VAULT_DIR_OVERRIDE,
#   CEREMONY_REPOS_OVERRIDE (comma-separated), CEREMONY_COUNTER_OVERRIDE,
#   CEREMONY_DID_WORK_OVERRIDE, CEREMONY_TOUCHED_REPOS_OVERRIDE,
#   CEREMONY_SKIP_FILE_OVERRIDE, CEREMONY_MINI_SKIP_OVERRIDE,
#   CEREMONY_BYPASS_LOG_OVERRIDE, CEREMONY_SESSION_ID_OVERRIDE

set -u

WORKSPACE="${CEREMONY_WORKSPACE_OVERRIDE:-$HOME/projects}"
SESSION_LOG_DIR="${CEREMONY_VAULT_DIR_OVERRIDE:-$HOME/session-logs}"
COUNTER="${CEREMONY_COUNTER_OVERRIDE:-$HOME/.claude/.ceremony-block-count}"

# --- session identity: work-markers are PER-SESSION ---
# Parse session_id defensively — on any failure fall back to legacy global files
# rather than breaking the gate.
SID="${CEREMONY_SESSION_ID_OVERRIDE:-$(python3 -c '
import json, re, sys
try:
    sid = json.load(sys.stdin).get("session_id") or ""
except Exception:
    sid = ""
print(sid if re.match(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$", sid) else "")
' 2>/dev/null || true)}"
MARKERS_DIR="$HOME/.claude/ceremony-markers"
if [ -n "$SID" ]; then
  DID_WORK_DEFAULT="$MARKERS_DIR/$SID.did-work"
  TOUCHED_DEFAULT="$MARKERS_DIR/$SID.touched-repos"
else
  DID_WORK_DEFAULT="$HOME/.claude/.ceremony-did-work"
  TOUCHED_DEFAULT="$HOME/.claude/.ceremony-touched-repos"
fi
DID_WORK_FILE="${CEREMONY_DID_WORK_OVERRIDE:-$DID_WORK_DEFAULT}"
TOUCHED_REPOS_FILE="${CEREMONY_TOUCHED_REPOS_OVERRIDE:-$TOUCHED_DEFAULT}"
# Loop-cap counter — per-session: a GLOBAL counter lets two concurrently-blocked
# sessions increment each other's cap and downgrade the gate to advisory early.
if [ -n "$SID" ]; then
  mkdir -p "$MARKERS_DIR" 2>/dev/null
  COUNTER_DEFAULT="$MARKERS_DIR/$SID.block-count"
else
  COUNTER_DEFAULT="$HOME/.claude/.ceremony-block-count"
fi
COUNTER="${CEREMONY_COUNTER_OVERRIDE:-$COUNTER_DEFAULT}"
if [ -n "${CEREMONY_REPOS_OVERRIDE:-}" ]; then
  IFS=',' read -ra REPOS <<< "$CEREMONY_REPOS_OVERRIDE"
else
  REPOS=(governance app-records app-finance app-archive platform)
fi

touched_repos=()
if [ -f "$TOUCHED_REPOS_FILE" ]; then
  while IFS= read -r line; do
    [ -n "$line" ] && touched_repos+=("$line")
  done < "$TOUCHED_REPOS_FILE"
fi
is_touched() {
  local r="$1" t
  for t in "${touched_repos[@]:-}"; do
    [ "$t" = "$r" ] && return 0
  done
  return 1
}

# --- escape hatch (every consumption is written to the bypass ledger) ---
SKIP_FILE="${CEREMONY_SKIP_FILE_OVERRIDE:-$HOME/.claude/.skip-ceremony}"
MINI_SKIP_FILE="${CEREMONY_MINI_SKIP_OVERRIDE:-$HOME/.claude/.skip-mini-sync-once}"
BYPASS_LOG="${CEREMONY_BYPASS_LOG_OVERRIDE:-$HOME/.claude/ceremony-bypass.log}"
ledger() { # ledger <event> <file> <mtime-epoch|->
  printf '%s\t%s\t%s\t%s\n' "$(date '+%Y-%m-%dT%H:%M:%S%z')" "$1" "$2" "$3" >> "$BYPASS_LOG"
}
if [ -n "${CLAUDE_SKIP_CEREMONY:-}" ]; then
  ledger "used-env" "CLAUDE_SKIP_CEREMONY" "-"
  exit 0
fi
if [ -f "$SKIP_FILE" ]; then
  ledger "used-skip" "$SKIP_FILE" "$(stat -f %m "$SKIP_FILE" 2>/dev/null || stat -c %Y "$SKIP_FILE" 2>/dev/null || echo -)"
  exit 0
fi

# --- scope: only inside the lab workspace ---
case "$PWD" in
  "$WORKSPACE"*) ;;
  *) exit 0 ;;
esac

TODAY="$(date +%F)"
unpushed=""
uncommitted=""    # soft-only: dirty repos NOT touched by this session
hard_dirty=""     # hard-block: dirty repos this session itself edited
shipped_today=0

for r in "${REPOS[@]}"; do
  d="$WORKSPACE/$r"
  [ -d "$d/.git" ] || continue
  # unpushed commits on the CURRENT branch — genuinely not on a remote (no network).
  # Count commits ahead of the branch's OWN upstream; if it has no upstream, count
  # commits on HEAD that are on no remote at all. Being ahead of origin/main on a
  # pushed feature branch is NOT unpushed — comparing against origin/main false-positives.
  if git -C "$d" rev-parse --verify -q '@{u}' >/dev/null 2>&1; then
    n=$(git -C "$d" rev-list --count '@{u}..HEAD' 2>/dev/null || echo 0)
  else
    n=$(git -C "$d" rev-list --count HEAD --not --remotes 2>/dev/null || echo 0)
  fi
  [ "${n:-0}" -gt 0 ] && unpushed="${unpushed}  - ${r}: ${n} unpushed commit(s)\n"
  # uncommitted working-tree changes — split hard vs soft by whether THIS
  # session is the one that dirtied it (mark-session-work.py's marker).
  if [ -n "$(git -C "$d" status --porcelain 2>/dev/null)" ]; then
    if is_touched "$r"; then
      hard_dirty="${hard_dirty}  - ${r}: uncommitted changes (edited this session)\n"
    else
      uncommitted="${uncommitted}  - ${r}\n"
    fi
  fi
  # commits authored today = material work happened
  if [ -n "$(git -C "$d" log --since="${TODAY} 00:00" --oneline 2>/dev/null)" ]; then
    shipped_today=1
  fi
done

# did_work is broader than shipped_today: it also covers edits to files git
# never tracks (agent definitions, global CLAUDE.md, hook scripts) via the
# PostToolUse marker, not just commits landed in the five named repos.
did_work=0
[ -f "$DID_WORK_FILE" ] && did_work=1

# --- session-log for today present & fresh? ---
vault_log=0
if [ -d "$SESSION_LOG_DIR" ]; then
  if find "$SESSION_LOG_DIR" -maxdepth 1 -name "*Session Log ${TODAY}*.md" -mtime -1 2>/dev/null | grep -q .; then
    vault_log=1
  fi
fi
missing_vault_log=0
if { [ "$shipped_today" -eq 1 ] || [ "$did_work" -eq 1 ]; } && [ "$vault_log" -eq 0 ]; then
  missing_vault_log=1
fi

# --- Server freshness: human-heal backstop ---
# Offline-tolerant: if the server is unreachable, skip silently (never trap a session).
# HARD-block only on DIVERGED (the one state the self-heal job cannot fix); behind /
# ahead / dirty are SOFT (self-heal fast-forwards 'behind' and pushes 'ahead' next cycle).
mini_soft=""
mini_diverged=""
mini_out=$(ssh -o BatchMode=yes -o ConnectTimeout=4 labhost '
  for r in '"${REPOS[*]}"'; do
    d="$LAB_HOME/repos/$r"; [ -d "$d/.git" ] || continue; cd "$d" || continue
    br=$(git symbolic-ref --quiet --short HEAD 2>/dev/null) || continue
    up="origin/$br"; git rev-parse --verify -q "$up" >/dev/null 2>&1 || continue
    L=$(git rev-parse @); R=$(git rev-parse "$up"); B=$(git merge-base @ "$up")
    if [ "$L" = "$R" ]; then s=level; elif [ "$L" = "$B" ]; then s=behind; elif [ "$R" = "$B" ]; then s=ahead; else s=diverged; fi
    dty=clean; [ -n "$(git status --porcelain --untracked-files=no)" ] && dty=dirty
    printf "%s %s %s\n" "$r" "$s" "$dty"
  done' 2>/dev/null)
if [ -n "$mini_out" ]; then
  while read -r mr ms md; do
    [ -z "$mr" ] && continue
    [ "$ms" = diverged ] && mini_diverged="${mini_diverged}  - ${mr} (server): DIVERGED from origin — needs manual resolve\n"
    [ "$ms" = behind ]   && mini_soft="${mini_soft}  - ${mr} (server): behind origin (self-heal will ff)\n"
    [ "$ms" = ahead ]    && mini_soft="${mini_soft}  - ${mr} (server): unpushed local commits (self-heal will push)\n"
    [ "$md" = dirty ]    && mini_soft="${mini_soft}  - ${mr} (server): uncommitted WIP\n"
  done <<< "$mini_out"
fi

# --- HARD BLOCK: unpushed commits, session-dirtied repos, or missing session
# log with real work done = ending without the ceremony actually happening ---
if [ -n "$unpushed" ] || [ -n "$hard_dirty" ] || [ "$missing_vault_log" -eq 1 ]; then
  c=$(cat "$COUNTER" 2>/dev/null || echo 0); c=$((c + 1)); echo "$c" > "$COUNTER"
  if [ "$c" -le 3 ]; then
    {
      echo "⛔ CLOSING CEREMONY NOT DONE:"
      if [ -n "$unpushed" ]; then
        echo "Unpushed commits:"
        printf "%b" "$unpushed"
      fi
      if [ -n "$hard_dirty" ]; then
        echo "Uncommitted changes in repos edited THIS session:"
        printf "%b" "$hard_dirty"
      fi
      if [ "$missing_vault_log" -eq 1 ]; then
        echo "No session log for today yet, and real work happened this session"
        echo "(commits today, and/or edits to files outside the five tracked repos)."
      fi
      echo "Run the closing ceremony BEFORE you stop:"
      echo "  1. Code changed? Run /code-review on the diff first (SEC-labeled work: also"
      echo "     /security-review) and cite the findings in the close-gate evidence."
      echo "  2. Update the relevant GitHub issue(s) with state + evidence."
      echo "  3. Write the session-log digest in your notes system."
      echo "  4. Dispatch repo-sync to commit + push all lab repos."
      echo "Then stopping is safe. (Disaster escape: touch ~/.claude/.skip-ceremony)"
    } >&2
    exit 2
  fi
  # loop cap reached — downgrade to advisory so a stuck condition can't trap the session
  echo "⚠️  closing-ceremony hook has blocked ${c}× — downgrading to advisory to avoid a loop."
  echo "    Resolve manually, then it will reset."
fi

# reached only when nothing above triggered, or the loop cap tripped — reset
rm -f "$COUNTER"

# --- HARD BLOCK: server DIVERGED (self-heal can't auto-resolve) — with one-shot override ---
if [ -n "$mini_diverged" ]; then
  if [ -f "$MINI_SKIP_FILE" ]; then
    ledger "consumed" "$MINI_SKIP_FILE" "$(stat -f %m "$MINI_SKIP_FILE" 2>/dev/null || stat -c %Y "$MINI_SKIP_FILE" 2>/dev/null || echo -)"
    rm -f "$MINI_SKIP_FILE"   # consume: override is one-shot, auto-clears
    echo "🛰️  Server-divergence override accepted (one-shot) — allowing stop. Resolve when you can:"
    printf "%b" "$mini_diverged"
  else
    {
      echo "⛔ SERVER DIVERGED — a server checkout has BOTH local and origin commits; the self-heal"
      echo "   job won't auto-merge/force, so it needs you:"
      printf "%b" "$mini_diverged"
      echo "Resolve on the server:  ssh labhost 'cd \$LAB_HOME/repos/<repo> && git pull --rebase && git push'"
      echo "…or approve an override to stop now (one-shot, auto-clears — no need to undo it):"
      echo "    touch $MINI_SKIP_FILE"
    } >&2
    exit 2
  fi
fi

# --- SOFT NUDGE: uncommitted changes in repos NOT touched this session ---
# (dirty repos this session itself edited are a HARD BLOCK above, not here)
if [ -n "$uncommitted" ]; then
  echo "🔄 Uncommitted changes (pre-existing, not from this session) — sync before ending the effort:"
  printf "%b" "$uncommitted"
fi

# --- SOFT NUDGE: server checkout drift (self-heal reconciles; surfaced for visibility) ---
if [ -n "${mini_soft:-}" ]; then
  echo "🛰️  Server checkout drift (self-heal LaunchAgent auto-reconciles behind/ahead each cycle):"
  printf "%b" "$mini_soft"
fi

# --- SOFT NUDGE: built-in review skills before ending a code session ---
touched_code=""
for r in "${REPOS[@]}"; do
  is_touched "$r" && touched_code="${touched_code}  - ${r}\n"
done
if [ -n "$touched_code" ]; then
  echo "🧪 Review ritual: this session changed code in:"
  printf "%b" "$touched_code"
  echo "   If not already done, run /code-review on the diff (SEC work: also /security-review)"
  echo "   and cite the result in the issue's close-gate evidence."
fi

exit 0
