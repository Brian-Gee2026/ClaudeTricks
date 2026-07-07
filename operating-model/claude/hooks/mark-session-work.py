#!/usr/bin/env python3
"""
mark-session-work.py — Claude Code PostToolUse hook (Edit | Write | NotebookEdit).

Why: closing-ceremony.sh (the Stop hook) originally judged "did real work happen
this session" purely from git commit activity in the five named lab repos. That
signal is blind to work done in files git never sees — ~/.claude/agents/*.md,
~/.claude/CLAUDE.md, the hook scripts themselves — which is exactly the kind of
decision-worthy change the session log exists to capture. It also only tracked
"uncommitted changes" as an advisory nudge, with no way to tell freshly-dirtied
files (from THIS session) apart from long-standing WIP a human left dirty on
purpose, so it could never safely upgrade that nudge to a hard block.

This hook fixes both gaps by recording, as edits happen:
  ~/.claude/ceremony-markers/<session_id>.did-work
                                       touch'd the first time any in-scope file
                                       is edited this session (existence-only).
  ~/.claude/ceremony-markers/<session_id>.touched-repos
                                       newline-separated, de-duped names of any
                                       of the five lab repos edited this session.

Markers are per-session files keyed by the session_id every hook envelope
carries. If an envelope has no usable session_id, we fall back to the legacy
global files (~/.claude/.ceremony-did-work / .ceremony-touched-repos) so the
signal degrades to the old behavior rather than disappearing.

closing-ceremony.sh reads its own session's markers to hard-block on:
  - a repo THIS session left dirty (not just any dirty repo — old unrelated WIP
    stays a soft nudge), and
  - real work happened (git commits today OR this marker) with no fresh session
    log yet.

Scope: only file_path/notebook_path values under the lab workspace
($HOME/projects) or the global harness config ($HOME/.claude)
count. An edit to an unrelated personal project elsewhere on disk does not set
either marker — this hook only cares about lab-relevant work, matching what
closing-ceremony.sh itself already scopes to.

This hook never blocks anything — it only records state. Always exits 0, even
on a parse failure or an editor tool it doesn't recognize.
"""

import json
import os
import re
import sys

EDIT_TOOLS = {"Edit", "Write", "NotebookEdit"}

WORKSPACE = os.path.realpath(os.path.expanduser("~/projects"))
CLAUDE_DIR = os.path.realpath(os.path.expanduser("~/.claude"))
MARKERS_DIR = os.path.expanduser("~/.claude/ceremony-markers")
LEGACY_DID_WORK = os.path.expanduser("~/.claude/.ceremony-did-work")
LEGACY_TOUCHED_REPOS = os.path.expanduser("~/.claude/.ceremony-touched-repos")

# session_id becomes a filename component — accept only safe characters, and
# reject anything that could traverse ('.', '..', empty). Anything else → legacy.
SAFE_SID = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$")


def marker_paths(session_id):
    """(did_work, touched_repos) for this session; legacy globals if no sid."""
    if session_id and SAFE_SID.match(session_id) and session_id not in {".", ".."}:
        os.makedirs(MARKERS_DIR, exist_ok=True)
        base = os.path.join(MARKERS_DIR, session_id)
        return base + ".did-work", base + ".touched-repos"
    return LEGACY_DID_WORK, LEGACY_TOUCHED_REPOS


def in_scope(path):
    try:
        real = os.path.realpath(path)
    except Exception:
        return False
    return real.startswith(WORKSPACE + os.sep) or real.startswith(CLAUDE_DIR + os.sep)


def repo_for_path(path):
    """Return the top-level repo dir name under WORKSPACE, or None."""
    real = os.path.realpath(path)
    if not real.startswith(WORKSPACE + os.sep):
        return None
    rest = real[len(WORKSPACE) + 1:]
    if not rest:
        return None
    return rest.split(os.sep, 1)[0]


def mark_did_work(did_work):
    # touch — create if absent, leave mtime alone if present (existence is
    # all that's checked; no need to bump mtime on every subsequent edit).
    if not os.path.exists(did_work):
        open(did_work, "a").close()


def mark_touched_repo(touched_repos, repo):
    existing = set()
    if os.path.exists(touched_repos):
        with open(touched_repos) as f:
            existing = {line.strip() for line in f if line.strip()}
    if repo in existing:
        return
    with open(touched_repos, "a") as f:
        f.write(repo + "\n")


def main():
    raw = sys.stdin.read()
    try:
        event = json.loads(raw)
    except Exception:
        return

    if event.get("tool_name") not in EDIT_TOOLS:
        return

    tool_input = event.get("tool_input") or {}
    path = tool_input.get("file_path") or tool_input.get("notebook_path") or ""
    if not path or not in_scope(path):
        return

    did_work, touched_repos = marker_paths(event.get("session_id") or "")
    mark_did_work(did_work)

    repo = repo_for_path(path)
    if repo:
        mark_touched_repo(touched_repos, repo)


if __name__ == "__main__":
    main()
    sys.exit(0)
