#!/bin/bash
# Charter §6 compliance check — validates all com.example.lab.* LaunchDaemons
# run as svcadmin non-root. Must be invoked with `sudo` so PlistBuddy can
# read root:wheel 600 plists. Without sudo,
# PlistBuddy silently returns "File Doesn't Exist, Will Create:" — a false-OK.
#
# Usage:
#   sudo ./scripts/charter_compliance_check.sh        # full per-plist output
#   sudo ./scripts/charter_compliance_check.sh -q     # summary line only
#   sudo ./scripts/charter_compliance_check.sh --help

set -euo pipefail

QUIET=0
GLOB="/Library/LaunchDaemons/com.example.lab.*.plist"

usage() {
    cat <<EOF
Usage: sudo $(basename "$0") [-q|--quiet] [-h|--help]

Checks every /Library/LaunchDaemons/com.example.lab.*.plist for
Charter §6 compliance (UserName=svcadmin).

Options:
  -q, --quiet   Suppress per-plist output; print only the summary line.
  -h, --help    Show this help and exit.

Output (without -q):
  PATH | UserName | GroupName | STATUS
  STATUS is COMPLIANT (UserName=svcadmin) or VIOLATION (root/missing/other).

Exit codes:
  0  All plists compliant.
  1  One or more violations detected.
  2  No matching plists found.
EOF
}

for arg in "$@"; do
    case "$arg" in
        -q|--quiet) QUIET=1 ;;
        -h|--help)  usage; exit 0 ;;
        *) echo "Unknown option: $arg" >&2; usage; exit 1 ;;
    esac
done

# shellcheck disable=SC2206
plists=( $GLOB )
if [[ ${#plists[@]} -eq 0 ]] || [[ ! -e "${plists[0]}" ]]; then
    echo "ERROR: No plists matched $GLOB" >&2
    exit 2
fi

compliant=0
violations=0

for plist in "${plists[@]}"; do
    username=$(sudo /usr/libexec/PlistBuddy -c "Print :UserName" "$plist" 2>/dev/null || echo "")
    groupname=$(sudo /usr/libexec/PlistBuddy -c "Print :GroupName" "$plist" 2>/dev/null || echo "")

    if [[ "$username" == "svcadmin" ]]; then
        status="COMPLIANT"
        (( compliant++ )) || true
    else
        status="VIOLATION"
        (( violations++ )) || true
    fi

    if [[ "$QUIET" -eq 0 ]]; then
        printf "%s | %s | %s | %s\n" "$plist" "${username:-<missing>}" "${groupname:-<missing>}" "$status"
    fi
done

echo "Compliant: $compliant | Violations: $violations"

if [[ "$violations" -gt 0 ]]; then
    exit 1
fi
exit 0
