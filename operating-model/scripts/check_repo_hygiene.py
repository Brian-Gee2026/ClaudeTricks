#!/usr/bin/env python3
# sdlc-gate v1.0.0 — vendored from platform/labs/lib/sdlc-gate; edit THERE, re-vendor, verify with gate_drift_check.sh
"""
check_repo_hygiene.py — repo-WIDE WIP/focus hygiene (see your governance issue tracker, SDLC focus contract).

The per-issue gate (check_issue_hygiene.py) can't see cross-issue state, so it
can't enforce the anti-squirrel limits. This script checks the whole repo:

  1. ≤ 1 open issue labeled `focus:current`   (the repo's single primary objective)
  2. ≤ 3 open issues labeled `status:in-progress`  (WIP limit)
  3. no `status:in-progress` issue untouched for > N days (default 7 — stale WIP)

Offender selection is deterministic:
  - focus overflow → every focus:current issue EXCEPT the lowest-numbered
    (the standing focus keeps legitimacy; newcomers trip until the old focus
    label is removed).
  - WIP overflow → every status:in-progress issue except the 3 lowest-numbered.
  - staleness → each individually stale issue.

--apply mode marks each offender with the `hygiene:wip-violation` label plus a
single marker comment (updated in place), and CLEARS label+comment on open
issues that are no longer offenders. It deliberately does NOT use
`needs-triage` — that label belongs to the per-issue gate, and two writers on
one label fight each other.

FREE tooling only: stdlib + `gh` (GITHUB_TOKEN). No LLM, no paid API.
Exit: 0 = clean verdict (pass or violations reported/applied), 3 = true error.
Verdict JSON on stdout: {"ok": bool, "violations": [...], "offenders": [...]}.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timedelta, timezone

VIOLATION_LABEL = "hygiene:wip-violation"
MARKER = "<!-- repo-hygiene-bot -->"

FOCUS_LABEL = "focus:current"
INPROG_LABEL = "status:in-progress"
FOCUS_MAX = 1
INPROG_MAX = 3


def gh(*args: str) -> str:
    res = subprocess.run(["gh", *args], check=True, capture_output=True, text=True)
    return res.stdout


def list_open_issues(repo: str) -> list[dict]:
    out = gh("issue", "list", "--repo", repo, "--state", "open", "--limit", "500",
             "--json", "number,labels,updatedAt")
    issues = json.loads(out)
    for i in issues:
        i["label_names"] = {l["name"] for l in i.get("labels") or []}
    return issues


def last_human_activity(repo: str, number: int) -> datetime:
    """Latest non-bot signal on the issue: the newest comment whose body does
    NOT contain our marker, else the issue's creation time. Deliberately NOT
    `updatedAt`: the bot's own marker comment (and label writes) bump
    updatedAt, so a staleness flag would reset its own clock and self-clear on
    the next run — flag/clear oscillation, observed live on the first canary."""
    out = gh("issue", "view", str(number), "--repo", repo,
             "--json", "createdAt,comments")
    data = json.loads(out)
    ts = [data["createdAt"]]
    for c in data.get("comments") or []:
        if MARKER not in (c.get("body") or ""):
            ts.append(c["createdAt"])
    latest = max(ts)
    return datetime.fromisoformat(latest.replace("Z", "+00:00"))


def find_offenders(repo: str, issues: list[dict], stale_days: int, now: datetime):
    violations: list[str] = []
    offenders: dict[int, list[str]] = {}

    def add(n: int, why: str):
        offenders.setdefault(n, []).append(why)

    focus = sorted(i["number"] for i in issues if FOCUS_LABEL in i["label_names"])
    if len(focus) > FOCUS_MAX:
        violations.append(
            f"{len(focus)} open issues carry `{FOCUS_LABEL}` (max {FOCUS_MAX}): "
            + ", ".join(f"#{n}" for n in focus))
        for n in focus[FOCUS_MAX:]:
            add(n, f"`{FOCUS_LABEL}` overflow — #{focus[0]} is the standing focus; "
                   "move the label deliberately (remove it there first) or drop it here")

    inprog = [i for i in issues if INPROG_LABEL in i["label_names"]]
    inprog_nums = sorted(i["number"] for i in inprog)
    if len(inprog_nums) > INPROG_MAX:
        violations.append(
            f"{len(inprog_nums)} open issues are `{INPROG_LABEL}` (WIP limit {INPROG_MAX}): "
            + ", ".join(f"#{n}" for n in inprog_nums))
        for n in inprog_nums[INPROG_MAX:]:
            add(n, f"`{INPROG_LABEL}` WIP-limit overflow — finish or park one of "
                   + ", ".join(f"#{m}" for m in inprog_nums[:INPROG_MAX]) + " first")

    cutoff = now - timedelta(days=stale_days)
    for i in inprog:
        # Cheap pre-filter: updatedAt is an upper bound on last human activity,
        # so a fresh updatedAt only *might* be bot noise — fetch comments to
        # decide. A stale updatedAt is definitively stale (no fetch needed).
        upd = datetime.fromisoformat(i["updatedAt"].replace("Z", "+00:00"))
        act = upd if upd < cutoff else last_human_activity(repo, i["number"])
        if act < cutoff:
            days = (now - act).days
            violations.append(f"#{i['number']} has been `{INPROG_LABEL}` with no human "
                              f"activity for {days} days (limit {stale_days})")
            add(i["number"], f"stale WIP — no human activity for {days} days; "
                             "update it, park it (status:backlog), or close it")
    return violations, offenders


def upsert_marker_comment(repo: str, number: int, body: str):
    cid = ""
    try:
        out = gh("api", f"repos/{repo}/issues/{number}/comments", "--paginate",
                 "--jq", f'.[] | select(.body | contains("{MARKER}")) | .id')
        cid = out.strip().splitlines()[-1] if out.strip() else ""
    except subprocess.CalledProcessError:
        pass
    if cid:
        gh("api", "-X", "PATCH", f"repos/{repo}/issues/comments/{cid}", "-f", f"body={body}")
    else:
        gh("issue", "comment", str(number), "--repo", repo, "--body", body)


def apply_verdict(repo: str, issues: list[dict], offenders: dict[int, list[str]]):
    flagged_now = set(offenders)
    flagged_before = {i["number"] for i in issues if VIOLATION_LABEL in i["label_names"]}
    for n in sorted(flagged_now):
        reasons = "\n".join(f"- {r}" for r in offenders[n])
        body = (f"{MARKER}\n## Repo-hygiene / focus-contract gate: WIP violation\n\n"
                f"{reasons}\n\n_Deterministic repo-wide check (≤1 `focus:current`, "
                f"≤3 `status:in-progress`, no stale WIP) — no LLM. "
                f"Source: `scripts/check_repo_hygiene.py`. Clears automatically once resolved._")
        if n not in flagged_before:
            gh("issue", "edit", str(n), "--repo", repo, "--add-label", VIOLATION_LABEL)
        upsert_marker_comment(repo, n, body)
    for n in sorted(flagged_before - flagged_now):
        gh("issue", "edit", str(n), "--repo", repo, "--remove-label", VIOLATION_LABEL)
        upsert_marker_comment(
            repo, n,
            f"{MARKER}\n## Repo-hygiene / focus-contract gate: resolved\n\n"
            f"This issue no longer violates the WIP/focus limits. `{VIOLATION_LABEL}` cleared.\n\n"
            f"_Deterministic repo-wide check — no LLM. Source: `scripts/check_repo_hygiene.py`._")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--repo", required=True, help="owner/name")
    ap.add_argument("--stale-days", type=int, default=7)
    ap.add_argument("--apply", action="store_true",
                    help="mark/clear offenders (label + marker comment)")
    args = ap.parse_args()

    try:
        issues = list_open_issues(args.repo)
        now = datetime.now(timezone.utc)
        violations, offenders = find_offenders(args.repo, issues, args.stale_days, now)
        if args.apply:
            apply_verdict(args.repo, issues, offenders)
    except subprocess.CalledProcessError as e:
        print(json.dumps({"ok": False, "error": (e.stderr or str(e)).strip()}))
        return 3

    print(json.dumps({"ok": not violations, "violations": violations,
                      "offenders": sorted(offenders)}))
    return 0


if __name__ == "__main__":
    sys.exit(main())
