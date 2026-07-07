#!/usr/bin/env python3
# sdlc-gate v1.0.0 — vendored from platform/labs/lib/sdlc-gate; edit THERE, re-vendor, verify with gate_drift_check.sh
"""log_gate_event.py — append-only writer for the quality ledger (SDLC Tier-0 #6, A3).

The quality ledger (`docs/metrics/gate_events.jsonl`) is the first-class record of
gate outcomes — every failed change, close-gate verdict, revert-check result, and
break-glass event. A `status:failed` change must never be a silent bounce (SDLC §2,
§4 Tier-0 #6); it lands here as a counted, queryable event.

One JSON object per line:
  {ts, repo, issue, type, area, priority, gate, outcome, evidence_ref}

Contract:
  - APPEND ONLY. This script never rewrites or deletes existing lines.
  - BOT-ONLY / SINGLE-WRITER by convention (SDLC §4 Tier-1 K9): the ledger is
    written only by automation, never hand-edited, so it cannot drift.
  - `ts` is supplied by the CALLER (not wall-clock here) so the writer is
    deterministic and the caller controls the event time.

FREE tooling only: pure stdlib, no network, no LLM, no paid API.

Usage:
  python3 scripts/log_gate_event.py \
      --ts 2026-06-19T12:00:00Z \
      --repo platform \
      --issue 42 \
      --type security \
      --area infra \
      --priority P1 \
      --gate close-gate \
      --outcome failed \
      --evidence-ref https://github.com/<gh-owner>/platform/issues/42#comment-1

Exit 0 = one line appended; exit 1 = bad input.
"""
from __future__ import annotations

import argparse
import json
import os
import sys

REPO_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LEDGER_DIR = os.path.join(REPO_ROOT, "docs", "metrics")
LEDGER_PATH = os.path.join(LEDGER_DIR, "gate_events.jsonl")

# Field order is fixed so every line has a stable, scannable shape.
FIELDS = ["ts", "repo", "issue", "type", "area", "priority",
          "gate", "outcome", "evidence_ref"]


def build_event(args: argparse.Namespace) -> dict:
    """Assemble the ordered event dict from parsed args. `issue` is an int when
    numeric, else passed through as-is (some events are not issue-scoped)."""
    issue: object = args.issue
    if isinstance(issue, str) and issue.isdigit():
        issue = int(issue)
    return {
        "ts": args.ts,
        "repo": args.repo,
        "issue": issue,
        "type": args.type,
        "area": args.area,
        "priority": args.priority,
        "gate": args.gate,
        "outcome": args.outcome,
        "evidence_ref": args.evidence_ref,
    }


def append_event(event: dict) -> None:
    """Append one JSON line to the ledger. Creates the dir/file if missing.
    Append mode + a single write is the whole single-writer guarantee here."""
    os.makedirs(LEDGER_DIR, exist_ok=True)
    line = json.dumps(event, ensure_ascii=False, sort_keys=False)
    with open(LEDGER_PATH, "a", encoding="utf-8") as fh:
        fh.write(line + "\n")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--ts", required=True,
                    help="event timestamp, caller-supplied (e.g. 2026-06-19T12:00:00Z)")
    ap.add_argument("--repo", required=True,
                    help="repo slug (platform / app-records / ...)")
    ap.add_argument("--issue", required=True,
                    help="issue number, or a non-issue tag for non-issue events")
    ap.add_argument("--type", required=True,
                    help="issue type (bug·feature·chore·docs·security·spike·plan)")
    ap.add_argument("--area", required=True, help="area label (repo-scoped)")
    ap.add_argument("--priority", required=True, help="P0–P3")
    ap.add_argument("--gate", required=True,
                    help="which gate emitted this (close-gate·revert-check·"
                         "test-floor·reconcile·break-glass·money-gate ...)")
    ap.add_argument("--outcome", required=True,
                    help="pass·fail·failed·blocked·break-glass·drift ...")
    ap.add_argument("--evidence-ref", dest="evidence_ref", required=True,
                    help="URL/SHA/path pointing at the evidence for this event")
    args = ap.parse_args()

    event = build_event(args)
    # Validate it is JSON-serializable and well-shaped before writing.
    try:
        json.dumps(event)
    except (TypeError, ValueError) as exc:
        print(f"FAIL — event is not serializable: {exc}", file=sys.stderr)
        return 1

    append_event(event)
    print(f"OK — appended gate event for {args.repo}#{args.issue} "
          f"({args.gate}={args.outcome}) to {os.path.relpath(LEDGER_PATH, REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
