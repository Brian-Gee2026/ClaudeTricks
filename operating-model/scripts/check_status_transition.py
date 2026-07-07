#!/usr/bin/env python3
# sdlc-gate v1.0.0 — vendored from platform/labs/lib/sdlc-gate; edit THERE, re-vendor, verify with gate_drift_check.sh
"""check_status_transition.py — the FORBIDDEN-direct-`done` transition guard.

SDLC reference: docs/SDLC_OPERATING_MODEL.md §0.5 authority matrix —
  "Direct label-stamp to `done` bypassing the gate | FORBIDDEN |
   transition-guard Action auto-reverts -> needs-triage"
and §11 AC #3 / the second-adversary finding "PR-centric gate vs mutable label".

The rule it enforces: `status:done` is legitimate ONLY when accompanied by the
close-gate's PASS signature. The close-gate (scripts/close_gate.py) posts a
durable comment carrying the marker `<!-- close-gate:verdict -->` and a verdict.
A `status:done` PASS-signature is therefore:

  (a) a posted close-gate comment whose marker is present AND whose verdict is
      PASS (the gate's own evidence, §0.5 "only via the gate's signature"), OR
  (b) the label `gate:close-pass` that ONLY the gate sets (a label-form marker,
      useful for PR-less issue types), OR
  (c) a logged human break-glass: the `gate:break-glass` label (§8 G5).

If `status:done` was applied WITHOUT any of those markers, it is a FORBIDDEN
direct jump: the guard REVERTS it (removes `status:done`, restores the prior
status if known else applies `status:in-review`) and applies `needs-triage`.

FREE + DETERMINISTIC: shells out only to `gh` (GitHub `GITHUB_TOKEN`). No LLM,
no paid API anywhere.

Usage (live, in the close-gate workflow's guard job):
  python3 scripts/check_status_transition.py --issue 33 [--apply]

  --apply  actually mutate labels via `gh` (default: dry-run, just report+exit).

Offline / test mode (no network) — feed the comments + labels directly:
  python3 scripts/check_status_transition.py --issue 33 \
      --labels-file labels.json --comments-file comments.json

Exit codes (VERDICT-IS-NOT-A-CI-FAILURE):
  A *verdict* — legitimate OR a FORBIDDEN-direct-done that the guard successfully
  HANDLED (reverted -> needs-triage) — is normal operation: the guard SUCCEEDED
  at gating, so it exits 0. The verdict is conveyed via labels + the posted
  comment, never via the process exit status / CI pass-fail (a non-zero here just
  emails the owner pure noise — issue (see your governance issue tracker) was a real, correctly-handled example).

  0 = transition legitimate, OR a forbidden-done was detected and HANDLED:
        - with --apply: reverted -> needs-triage (the guard did its job), or
        - dry-run (no --apply): detection reported (nothing to fail — reporting
          is the whole job in dry-run).
  3 = TRUE ERROR only: usage / gh / network / malformed input / a crash.

  (Legacy note: this script formerly returned 1 on a detected forbidden-done.
  That made GitHub mark the guard run "failed" on perfectly normal operation.
  The verdict now lives in `result["legitimate"]` / the labels, not the rc.)
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys

GATE_MARKER = "<!-- close-gate:verdict -->"   # must match close_gate.py MARKER
PASS_TOKEN = "PASS"
GATE_PASS_LABEL = "gate:close-pass"           # label-form marker; gate-only
BREAK_GLASS_LABEL = "gate:break-glass"        # logged human override (§8 G5)
DONE_LABEL = "status:done"
TRIAGE_LABEL = "needs-triage"
FALLBACK_STATUS = "status:in-review"          # restore target if prior unknown


# ---------------------------------------------------------------------------
# Data acquisition (live `gh` or offline files)
# ---------------------------------------------------------------------------
def get_labels(args) -> list[str]:
    if args.labels_file:
        with open(args.labels_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return [l["name"] if isinstance(l, dict) else str(l) for l in raw]
    out = subprocess.run(
        ["gh", "issue", "view", str(args.issue), "--json", "labels"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [l["name"] for l in json.loads(out).get("labels", [])]


def get_comments(args) -> list[str]:
    if args.comments_file:
        with open(args.comments_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return [c["body"] if isinstance(c, dict) else str(c) for c in raw]
    out = subprocess.run(
        ["gh", "issue", "view", str(args.issue), "--json", "comments"],
        capture_output=True, text=True, check=True,
    ).stdout
    return [c.get("body", "") for c in json.loads(out).get("comments", [])]


# ---------------------------------------------------------------------------
# The legitimacy test
# ---------------------------------------------------------------------------
def has_gate_pass_comment(comments: list[str]) -> bool:
    """A posted close-gate comment whose marker is present AND verdict is PASS."""
    for body in comments:
        if GATE_MARKER in body and _verdict_is_pass(body):
            return True
    return False


def _verdict_is_pass(body: str) -> bool:
    """The gate renders '**PASS**' (badge '✅ PASS') and emits a verdict JSON.

    We accept either the rendered badge line or an explicit verdict token, but
    we DENY if a FAIL/NEEDS-HUMAN verdict is present — a marker comment that is
    not a PASS must never be read as a pass.
    """
    if "NEEDS-HUMAN" in body or "FAIL" in body:
        return False
    # Badge or JSON verdict.
    return ("✅ PASS" in body) or ('"verdict": "PASS"' in body) or \
           ("**PASS**" in body)


def is_legitimate(labels: list[str], comments: list[str]) -> tuple[bool, str]:
    if DONE_LABEL not in labels:
        return True, "issue does not carry status:done — nothing to guard"
    if BREAK_GLASS_LABEL in labels:
        return True, "gate:break-glass present — logged human override (§8 G5)"
    if GATE_PASS_LABEL in labels:
        return True, "gate:close-pass label present — gate-set marker"
    if has_gate_pass_comment(comments):
        return True, "close-gate PASS comment present (marker + PASS verdict)"
    return False, (
        "status:done applied WITHOUT a close-gate PASS marker — FORBIDDEN "
        "direct-done (§0.5). No gate:close-pass label, no gate:break-glass, and "
        "no posted close-gate PASS comment."
    )


# ---------------------------------------------------------------------------
# The revert action
# ---------------------------------------------------------------------------
def prior_status(labels: list[str]) -> str:
    """If a non-done status label already coexists, restore to it; else fallback."""
    for l in labels:
        if l.startswith("status:") and l != DONE_LABEL:
            return l
    return FALLBACK_STATUS


def revert_forbidden_done(issue: int, labels: list[str], apply: bool) -> dict:
    restore = prior_status(labels)
    add = [TRIAGE_LABEL]
    if restore not in labels:
        add.append(restore)
    remove = [DONE_LABEL]

    plan = {
        "action": "revert-forbidden-done",
        "issue": issue,
        "remove_labels": remove,
        "add_labels": add,
        "restored_status": restore,
        "applied": False,
    }
    if not apply:
        return plan

    cmd = ["gh", "issue", "edit", str(issue)]
    for l in add:
        cmd += ["--add-label", l]
    for l in remove:
        cmd += ["--remove-label", l]
    subprocess.run(cmd, check=True, capture_output=True, text=True)

    body = (
        f"{GATE_MARKER}\n"
        "## 🛑 Transition guard — FORBIDDEN direct-`done` reverted\n\n"
        "`status:done` was applied without a close-gate PASS signature "
        "(§0.5 authority matrix). The label was removed, status restored to "
        f"`{restore}`, and `needs-triage` applied. Run the deterministic "
        "close-gate to earn `status:done`."
    )
    subprocess.run(
        ["gh", "issue", "comment", str(issue), "--body", body],
        check=True, capture_output=True, text=True,
    )
    plan["applied"] = True
    return plan


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="FORBIDDEN-direct-done transition guard.")
    p.add_argument("--issue", type=int, required=True)
    p.add_argument("--apply", action="store_true",
                   help="actually mutate labels/comment via gh (default dry-run)")
    p.add_argument("--labels-file", default=None, help="offline: labels JSON")
    p.add_argument("--comments-file", default=None, help="offline: comments JSON")
    p.add_argument("--json-out", default=None)
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    try:
        labels = get_labels(args)
        comments = get_comments(args)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"check_status_transition: gh failed: {e}\n")
        return 3
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"check_status_transition: {e}\n")
        return 3

    ok, why = is_legitimate(labels, comments)
    result = {"issue": args.issue, "legitimate": ok, "reason": why, "labels": labels}

    if ok:
        result["action"] = "none"
    else:
        # A FORBIDDEN direct-done is a VERDICT, not a CI failure. With --apply the
        # guard reverts it (-> needs-triage) — that is the guard SUCCEEDING. A
        # real failure inside the gh mutations (network/auth) IS a true error ->
        # rc=3, distinct from the handled-verdict exit 0.
        try:
            result["plan"] = revert_forbidden_done(args.issue, labels, args.apply)
        except subprocess.CalledProcessError as e:
            sys.stderr.write(
                f"check_status_transition: gh mutation failed during revert: {e}\n"
            )
            return 3

    # Verdict reached (handled or legitimate) => the guard did its job => exit 0.
    rc = 0

    out = json.dumps(result, indent=2)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            fh.write(out + "\n")
    print(out)
    return rc


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
