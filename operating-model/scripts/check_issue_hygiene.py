#!/usr/bin/env python3
# sdlc-gate v1.0.0 — vendored from platform/labs/lib/sdlc-gate; edit THERE, re-vendor, verify with gate_drift_check.sh
"""check_issue_hygiene.py — label-hygiene + Definition-of-Ready gate.

Tier-0 component (SDLC_OPERATING_MODEL.md §4 Tier-0 #3, C1/G6). FREE tooling
only: pure stdlib + `gh` (GitHub `GITHUB_TOKEN`). NO paid Anthropic API, NO LLM.
The model's "Haiku intake assist" is the deferred Tier-1 LLM layer; this gate is
strictly deterministic.

What it asserts about a single issue (labels + body):
  - LABEL CARDINALITY (always): exactly one `type:*`, exactly one `status:*`,
    exactly one priority `P0|P1|P2|P3`.
  - DEFINITION-OF-READY (only at `status:ready` or beyond — ready, in-progress,
    in-review, deployed-watch, done): the body must carry a STRUCTURED
    success-criteria checklist — a `## Success criteria` heading followed by >=1
    markdown checkbox line (`- [ ]` / `- [x]`) whose text reads like an
    observable assertion (contains a command/route/query/number/expected token),
    NOT bare prose like "it works". (SDLC §2 + §11 #2, the G6 testability rule.)

This gate auto-applies `needs-triage` (an `A` action in the §0.5 authority
matrix) on violation; the workflow handles that side. This script only reports
the verdict.

Usage:
  # JSON in via arg or stdin: {"labels": [...], "body": "..."}
  # labels may be a list of strings, or a list of {"name": "..."} (gh shape).
  python3 scripts/check_issue_hygiene.py --json '{"labels":["type:bug",...],"body":"..."}'
  echo '{"labels":[...],"body":"..."}' | python3 scripts/check_issue_hygiene.py

  # Fetch a live issue and check it (needs gh + GITHUB_TOKEN):
  python3 scripts/check_issue_hygiene.py --gh-issue <gh-owner>/platform 42

Output (stdout): a JSON verdict {"ok": bool, "violations": [str, ...]}.
Exit code: 0 if ok, 1 on any violation (so it can gate in CI/hooks).
"""
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys

# Statuses at which Definition-of-Ready (structured success criteria) applies.
# `backlog` and `draft` are pre-ready, so criteria are NOT yet required there.
READY_OR_BEYOND = {"ready", "in-progress", "in-review", "deployed-watch", "done"}

PRIORITIES = {"P0", "P1", "P2", "P3"}

# A `## Success criteria` heading (any heading level, case-insensitive).
CRITERIA_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s+success criteria\s*$",
                                 re.IGNORECASE | re.MULTILINE)
# A markdown checkbox line: `- [ ] text` or `- [x] text` (also * / + bullets).
CHECKBOX_RE = re.compile(r"^\s*[-*+]\s+\[( |x|X)\]\s+(?P<text>.+?)\s*$")

# Heuristic: a checkbox "looks like an observable assertion" if its text carries
# at least one concrete, checkable token — a command, a route/URL, a SQL-ish
# query, a number, a status code, an expectation keyword, code/path tokens — and
# is not just vague prose ("works", "is good", "looks fine").
_OBSERVABLE_SIGNALS = [
    re.compile(r"`[^`]+`"),                              # inline code / command
    re.compile(r"\bhttps?://"),                          # URL
    re.compile(r"(^|\s)/[A-Za-z0-9._/-]+"),              # route / path
    re.compile(r"\b\d+\b"),                              # any number (count, 200, $)
    re.compile(r"\b\d{3}\b"),                            # HTTP-ish status code
    re.compile(r"\b(curl|grep|psql|select|ssh|systemctl|launchctl|"
               r"python3?|pytest|gh|git|caddy|ollama)\b", re.IGNORECASE),
    re.compile(r"\b(returns?|equals?|exit|status|count|==|=>|->|>=|<=|"
               r"expect(?:s|ed)?|assert|denies|rejects?|200|201|204|301|"
               r"302|401|403|404|500)\b", re.IGNORECASE),
    re.compile(r"\$\w+|\$\d"),                           # env var / dollar amount
]
# Vague-only phrases that, ALONE, do not count as observable.
_VAGUE_ONLY_RE = re.compile(
    r"^(it\s+)?(works?|is\s+(good|fine|ok|done|complete)|looks?\s+(good|fine|right)|"
    r"functions?\s+(correctly|properly)|no\s+(issues?|errors?|bugs?))\.?$",
    re.IGNORECASE,
)


def _looks_observable(text: str) -> bool:
    """Heuristic: does this checkbox text read like a checkable assertion?"""
    t = text.strip()
    if not t:
        return False
    if _VAGUE_ONLY_RE.match(t):
        return False
    return any(sig.search(t) for sig in _OBSERVABLE_SIGNALS)


def normalize_labels(labels) -> list[str]:
    """Accept gh's [{'name': ...}] shape or a plain list of strings."""
    out = []
    for item in labels or []:
        if isinstance(item, dict):
            name = item.get("name")
            if name:
                out.append(name)
        elif isinstance(item, str):
            out.append(item)
    return out


def _status_of(labels: list[str]) -> str | None:
    for lab in labels:
        if lab.startswith("status:"):
            return lab.split(":", 1)[1].strip()
    return None


def check_cardinality(labels: list[str], axis: str, pretty: str,
                      violations: list[str]) -> None:
    matches = [lab for lab in labels if lab.startswith(axis)]
    if len(matches) == 0:
        violations.append(f"[label] missing a {pretty} label (need exactly one "
                          f"`{axis}*`)")
    elif len(matches) > 1:
        violations.append(f"[label] {len(matches)} {pretty} labels — exactly one "
                          f"allowed; found: {', '.join(sorted(matches))}")


def check_priority(labels: list[str], violations: list[str]) -> None:
    matches = [lab for lab in labels if lab in PRIORITIES]
    if len(matches) == 0:
        violations.append("[label] missing a priority label (need exactly one of "
                          "P0, P1, P2, P3)")
    elif len(matches) > 1:
        violations.append(f"[label] {len(matches)} priority labels — exactly one "
                          f"allowed; found: {', '.join(sorted(matches))}")


def check_success_criteria(body: str, violations: list[str]) -> None:
    """DoR: a `## Success criteria` heading + >=1 observable checkbox line."""
    body = body or ""
    if not CRITERIA_HEADING_RE.search(body):
        violations.append("[DoR] at status:ready or beyond, the body must contain "
                          "a `## Success criteria` heading (none found)")
        return
    # Collect checkbox lines that appear AFTER the heading.
    heading_pos = CRITERIA_HEADING_RE.search(body).end()
    after = body[heading_pos:]
    checkbox_texts = [m.group("text") for m in
                      (CHECKBOX_RE.match(line) for line in after.splitlines())
                      if m]
    if not checkbox_texts:
        violations.append("[DoR] `## Success criteria` heading has no markdown "
                          "checkbox lines (`- [ ]` / `- [x]`) after it")
        return
    observable = [t for t in checkbox_texts if _looks_observable(t)]
    if not observable:
        violations.append(
            "[DoR] success-criteria checkboxes read as prose, not observable "
            "assertions — each should carry a command/route/query/number/"
            "expected token (e.g. `curl /health` returns 200), not just "
            f"'works'. Found: {checkbox_texts!r}")


def check_issue(labels, body: str) -> dict:
    """Run the full hygiene check. Returns {'ok': bool, 'violations': [...]}"""
    labels = normalize_labels(labels)
    violations: list[str] = []

    check_cardinality(labels, "type:", "type:*", violations)
    check_cardinality(labels, "status:", "status:*", violations)
    check_priority(labels, violations)

    status = _status_of(labels)
    if status in READY_OR_BEYOND:
        check_success_criteria(body, violations)

    return {"ok": not violations, "violations": violations}


# --------------------------------------------------------------------------- #
# Input modes
# --------------------------------------------------------------------------- #
def _from_payload(payload: dict) -> dict:
    return check_issue(payload.get("labels"), payload.get("body") or "")


def _from_gh_issue(repo: str, number: str) -> dict:
    """Fetch labels+body via `gh issue view` and check (needs gh + token)."""
    out = subprocess.run(
        ["gh", "issue", "view", number, "--repo", repo,
         "--json", "labels,body"],
        check=True, capture_output=True, text=True,
    )
    data = json.loads(out.stdout)
    return check_issue(data.get("labels"), data.get("body") or "")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--json", dest="json_arg", metavar="JSON",
                   help='inline payload: {"labels":[...],"body":"..."}')
    g.add_argument("--gh-issue", dest="gh_issue", nargs=2,
                   metavar=("REPO", "NUMBER"),
                   help="fetch the issue via `gh issue view` and check it")
    args = ap.parse_args()

    if args.gh_issue:
        verdict = _from_gh_issue(args.gh_issue[0], args.gh_issue[1])
    else:
        raw = args.json_arg if args.json_arg is not None else sys.stdin.read()
        if not raw.strip():
            ap.error("no input: pass --json, --gh-issue, or pipe JSON on stdin")
        try:
            payload = json.loads(raw)
        except json.JSONDecodeError as exc:
            ap.error(f"input is not valid JSON: {exc}")
        verdict = _from_payload(payload)

    print(json.dumps(verdict, indent=2))
    return 0 if verdict["ok"] else 1


if __name__ == "__main__":
    sys.exit(main())
