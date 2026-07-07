#!/bin/zsh
# SubagentStop hook: append one JSONL record per completed subagent.
# Receives the hook payload on stdin. Never blocks (always exits 0).
python3 -c '
import json, sys, os
from datetime import datetime, timezone
try:
    d = json.load(sys.stdin)
except Exception:
    d = {}
rec = {
    "ts": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    "agent": d.get("agent_type"),
    "id": d.get("agent_id"),
    "cwd": d.get("cwd"),
    "session": d.get("session_id"),
}
with open(os.path.expanduser("~/.claude/agent-activity.jsonl"), "a") as f:
    f.write(json.dumps(rec) + "\n")
' 2>/dev/null
exit 0
