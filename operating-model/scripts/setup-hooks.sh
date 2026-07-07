#!/usr/bin/env bash
# One-time per clone: enable the committed git hooks (the anti-drift pre-commit
# gate). Run this on the laptop AND the mini after cloning/pulling.
set -euo pipefail
ROOT="$(git rev-parse --show-toplevel)"
git -C "$ROOT" config core.hooksPath .githooks
chmod +x "$ROOT"/.githooks/* 2>/dev/null || true
echo "git hooks enabled (core.hooksPath=.githooks)."
echo "Test:  python3 scripts/check_system_manifest.py"
