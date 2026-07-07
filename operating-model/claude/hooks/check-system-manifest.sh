#!/usr/bin/env bash
# Global doc-sync gate (Stop hook). If the current project ships a
# system-manifest checker, run it and surface any drift between the code and its
# system map (docs/DATA_FLOW.md + docs/system_manifest.json). No-op for projects
# that haven't adopted the pattern. Never blocks the session.
#
# Applies to ALL code sessions. Reference implementation:
# app-records (scripts/check_system_manifest.py).
set -u
DIR="${CLAUDE_PROJECT_DIR:-$PWD}"
CHECKER="$DIR/scripts/check_system_manifest.py"
if [ -f "$CHECKER" ]; then
  if ! out=$(cd "$DIR" && python3 "$CHECKER" 2>&1); then
    echo "system-manifest drift — the code and its system map are out of sync."
    echo "Update docs/system_manifest.json (+ docs/DATA_FLOW.md) in this commit:"
    echo "$out"
  fi
fi

# PHI-column default-deny: advisory surface of the runtime check
# when the project ships it AND a DB is reachable (APP_DSN set — the server).
# Silently skipped on machines without the DSN. Never blocks the session.
GUARD="$DIR/app_core/security_guardrails.py"
if [ -f "$GUARD" ] && [ -n "${APP_DSN:-}" ]; then
  PY="$DIR/venv/bin/python3"; [ -x "$PY" ] || PY=python3
  if ! out=$(cd "$DIR" && "$PY" -m app_core.security_guardrails --enforce --only phi_columns_encrypted 2>&1); then
    echo "PHI-column default-deny FAIL — unclassified plaintext column(s):"
    echo "$out"
  fi
fi
exit 0
