#!/bin/bash
# MG-1 — deny paid Anthropic API usage from any dev/CLI/agent session.
# SDLC operating model §6 / P3: paid API is NEVER for dev. Block BEFORE the spend; no dev override.
# This is defense-in-depth; the primary control is managed-settings forceLoginMethod=claudeai.
# Conservative patterns — only real paid-invocation vectors, not benign reads/greps.
input=$(cat)
cmd=$(printf '%s' "$input" | python3 -c 'import sys,json
try: print(json.load(sys.stdin).get("tool_input",{}).get("command",""))
except Exception: print("")' 2>/dev/null || true)
[ -z "$cmd" ] && exit 0

deny() {
  echo "MG-1 BLOCKED — paid API is never for dev (SDLC §6 / P3): $1." >&2
  echo "Production paid runs are server-initiated + human-armed only. If this is a false positive, contact the Director." >&2
  exit 2
}

# 1. Assigning/exporting the paid credentials (the env-injection that triggers metered billing)
printf '%s' "$cmd" | grep -Eq '(^|[;&|(`[:space:]])(export[[:space:]]+)?ANTHROPIC_API_KEY[[:space:]]*=' && deny "sets ANTHROPIC_API_KEY"
printf '%s' "$cmd" | grep -Eq '(^|[;&|(`[:space:]])(export[[:space:]]+)?ANTHROPIC_AUTH_TOKEN[[:space:]]*=' && deny "sets ANTHROPIC_AUTH_TOKEN"
printf '%s' "$cmd" | grep -Eq '(^|[;&|(`[:space:]])(export[[:space:]]+)?ANTHROPIC_OCR_KEY[[:space:]]*=' && deny "sets ANTHROPIC_OCR_KEY (paid OCR credential)"

# 2. Direct calls to the metered API endpoint
printf '%s' "$cmd" | grep -Eq '(curl|wget|https?_proxy|nc|httpie|http)[^|]*api\.anthropic\.com' && deny "calls api.anthropic.com"

# 3. Known paid launch surfaces (audit): these scripts read
#    ANTHROPIC_API_KEY internally from $LAB_HOME/secrets/.env, so patterns 1-2 never
#    fire — locally or via `ssh labhost 'bash …'`. Block EXECUTION (command
#    position or interpreter-prefixed), not mere mentions: cat/grep/vim of these
#    filenames stays allowed.
PAID_SH='(ingest_source|launch_app_overnight|launch_app_reprocess|launch_ingest_worker)\.sh'
printf '%s' "$cmd" | grep -Eq "(^|[;&|(])[[:space:]]*([^[:space:]]*/)?${PAID_SH}" && deny "invokes a paid launch script"
printf '%s' "$cmd" | grep -Eq "(^|[[:space:];&|('\"])(bash|sh|zsh|nohup|caffeinate|exec|source)([[:space:]]+-[^[:space:]]+)*[[:space:]]+([^[:space:]]*/)?${PAID_SH}" && deny "invokes a paid launch script"
printf '%s' "$cmd" | grep -Eq "(^|[[:space:];&|(])(python3?[[:space:]]+|uv[[:space:]]+run[[:space:]]+)[^|;&]*enrich_corpus\.py" && deny "runs enrich_corpus.py (paid enrichment)"

# 4. Direct `python -m` invocation of paid pipeline modules (bypasses the .sh
#    wrappers pattern 3 catches). Module names verified against app_core/
#    audit. May over-block a legitimate free/local test run of these
#    modules — that is intentional; route real local tests through the Director.
PAID_MOD='app_core\.(overnight_runner|reprocess_stale|ingest_worker|ingest_pdf|ingest_ccda|llm_extract|vision_extract|jobs\.enrich_card)'
printf '%s' "$cmd" | grep -Eq "python3?[[:space:]]+(-[A-Za-z]+[[:space:]]+)*-m[[:space:]]+${PAID_MOD}" && deny "invokes a paid pipeline module directly"

exit 0
