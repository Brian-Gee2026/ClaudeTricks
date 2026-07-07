#!/usr/bin/env bash
# epic-scope-freeze.sh — Stop hook: enforce SDLC §2.5 rule 1 (epic scope freeze).
#
# Why: multi-session epics never converge when sessions are allowed to file
# mid-flight discoveries INTO the epic. The §2.5 contract freezes an epic's
# sub-issue set at execution start; this hook is the live deterministic control
# for the freeze — it blocks a session stop whose estate contains a scope:frozen
# epic with sub-issues beyond the frozen manifest.
#
# Contract (Claude Code Stop hook):
#   exit 2 -> BLOCK the stop; stderr is fed back to the model, which continues.
#   exit 0 -> allow the stop; stdout (if any) surfaces as an advisory.
#
# Detection, per open issue labeled scope:frozen in each lab repo:
#   frozen set = the `<!-- frozen-sub-issues: N,N,N -->` manifest in the body
#   live set   = GitHub native sub-issues (GraphQL subIssues)
#   live \ frozen != {}  ->  HARD BLOCK naming the epic, the extras, and §2.5.
#   A frozen epic MISSING its manifest is a soft advisory (freeze half-applied).
#
# Safety valves:
#   - scoped: only runs when the session cwd is inside the lab workspace.
#   - fail-open: gh missing / offline / API error => exit 0 (never brick a stop
#     on network state; the Actions-side twin re-checks when enabled).
#   - escape hatch: touch ~/.claude/.skip-scope-freeze (24h self-expiry, same
#     semantics as .skip-ceremony) or CLAUDE_SKIP_SCOPE_FREEZE=1.
#   - loop cap: after 3 consecutive blocks, downgrade to advisory.
#
# Test seams (bypass gh; used by the self-test only):
#   FREEZE_TEST_FROZEN="126,127"  FREEZE_TEST_LIVE="126,127,199"
#   FREEZE_REPOS_OVERRIDE (comma-separated owner/repo), FREEZE_COUNTER_OVERRIDE,
#   FREEZE_SKIP_FILE_OVERRIDE, FREEZE_WORKSPACE_OVERRIDE, FREEZE_CWD_OVERRIDE

set -u

WORKSPACE="${FREEZE_WORKSPACE_OVERRIDE:-$HOME/projects}"
COUNTER="${FREEZE_COUNTER_OVERRIDE:-$HOME/.claude/.scope-freeze-block-count}"
SKIP_FILE="${FREEZE_SKIP_FILE_OVERRIDE:-$HOME/.claude/.skip-scope-freeze}"
REPOS="${FREEZE_REPOS_OVERRIDE:-<gh-owner>/app-records,<gh-owner>/app-finance,<gh-owner>/app-archive,<gh-owner>/platform,<gh-owner>/governance}"

# --- scope: only act inside the lab workspace -------------------------------
CWD="${FREEZE_CWD_OVERRIDE:-$PWD}"
case "$CWD" in
  "$WORKSPACE"*) : ;;
  *) exit 0 ;;
esac

# --- escape hatches ----------------------------------------------------------
if [ "${CLAUDE_SKIP_SCOPE_FREEZE:-0}" = "1" ]; then exit 0; fi
if [ -f "$SKIP_FILE" ]; then
  # 24h self-expiry, same policy as .skip-ceremony: a one-day bypass, not an off-switch.
  if [ -n "$(find "$SKIP_FILE" -mmin +1440 2>/dev/null)" ]; then
    rm -f "$SKIP_FILE"
  else
    exit 0
  fi
fi

# --- violation collection ----------------------------------------------------
violations=""
advisories=""

check_sets() {
  # $1 repo label, $2 epic number, $3 frozen csv, $4 live csv
  local repo="$1" num="$2" frozen="$3" live="$4" extras="" n
  for n in $(echo "$4" | tr ',' ' '); do
    case ",$frozen," in
      *",$n,"*) : ;;
      *) extras="$extras #$n" ;;
    esac
  done
  if [ -n "$extras" ]; then
    violations="${violations}
  ${repo}#${num}: sub-issue(s)${extras} added AFTER the freeze (frozen manifest: ${frozen})."
  fi
}

if [ -n "${FREEZE_TEST_FROZEN:-}" ] || [ -n "${FREEZE_TEST_LIVE:-}" ]; then
  # self-test path: compare the seeded sets, no network
  check_sets "test/repo" "0" "${FREEZE_TEST_FROZEN:-}" "${FREEZE_TEST_LIVE:-}"
else
  command -v gh >/dev/null 2>&1 || exit 0   # fail-open: no gh, no gate
  for repo in $(echo "$REPOS" | tr ',' ' '); do
    owner="${repo%%/*}"; name="${repo##*/}"
    # one call per repo: frozen epics with number+body
    epics_json="$(gh issue list --repo "$repo" --label "scope:frozen" --state open \
                   --json number,body --limit 20 2>/dev/null)" || continue
    [ -z "$epics_json" ] || [ "$epics_json" = "[]" ] && continue
    while IFS=$'\t' read -r num frozen; do
      [ -n "$num" ] || continue
      if [ -z "$frozen" ]; then
        advisories="${advisories}
  ${repo}#${num} is scope:frozen but has NO <!-- frozen-sub-issues --> manifest — freeze is half-applied; add the manifest."
        continue
      fi
      live="$(gh api graphql -f query="query{repository(owner:\"$owner\",name:\"$name\"){issue(number:$num){subIssues(first:100){nodes{number}}}}}" \
               --jq '.data.repository.issue.subIssues.nodes[].number' 2>/dev/null | paste -sd, -)" || continue
      [ -n "$live" ] || continue
      check_sets "$repo" "$num" "$frozen" "$live"
    done <<EOF2
$(printf '%s' "$epics_json" | python3 -c '
import json,re,sys
for e in json.load(sys.stdin):
    m = re.search(r"<!--\s*frozen-sub-issues:\s*([0-9,\s]+?)\s*-->", e.get("body") or "")
    csv = re.sub(r"\s+","",m.group(1)) if m else ""
    print(f"{e[\"number\"]}\t{csv}")
' 2>/dev/null)
EOF2
  done
fi

# --- disposition -------------------------------------------------------------
if [ -n "$violations" ]; then
  count=0
  [ -f "$COUNTER" ] && count="$(cat "$COUNTER" 2>/dev/null || echo 0)"
  count=$((count + 1)); echo "$count" > "$COUNTER"
  msg="⛔ EPIC SCOPE-FREEZE VIOLATION (SDLC §2.5 rule 1 — the anti-loop canon):
${violations}

A scope:frozen epic's sub-issue set is CLOSED. The discovery you just filed belongs on the
epic's parking-lot issue (one line, 'Parking lot — epic #N') or as an unlinked status:draft
issue — never on the epic. Fix now, before stopping:
  1. Detach the added sub-issue(s) from the epic (gh api: remove sub-issue link).
  2. Re-file each as one line on the parking-lot issue (or unlinked draft).
  3. If you believe it genuinely MUST ride the epic, that is a DESCOPE/refreeze decision —
     Director approval required (§2.5 rule 4); do not self-approve.
Escape hatch (Director-sanctioned only): touch ~/.claude/.skip-scope-freeze (24h self-expiry)."
  if [ "$count" -ge 3 ]; then
    echo "⚠️ (advisory after $count consecutive blocks — loop cap) $msg"
    exit 0
  fi
  echo "$msg" >&2
  exit 2
fi

rm -f "$COUNTER" 2>/dev/null
if [ -n "$advisories" ]; then
  echo "⚠️ scope-freeze advisory:${advisories}"
fi
exit 0
