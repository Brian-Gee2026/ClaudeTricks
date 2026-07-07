#!/usr/bin/env python3
# sdlc-gate v1.0.0 — vendored from platform/labs/lib/sdlc-gate; edit THERE, re-vendor, verify with gate_drift_check.sh
"""close_gate.py — the Tier-0 DETERMINISTIC close-gate (antidote to inadequate testing).

SDLC reference: docs/SDLC_OPERATING_MODEL.md §4 Tier-0 #5 (deterministic
close-gate + revert-check), §5 (LANE-C: deterministic auto, NO LLM), §11 AC #3.

This is the machine check that was missing. It is DETERMINISTIC and FREE — it shells
out to `git`, the project's test command, and `gh` (GitHub `GITHUB_TOKEN`). There
is NO paid Anthropic API and NO LLM anywhere in this gate. The LLM adversarial
review layer is explicitly DEFERRED (Tier-1, behind a tripwire + LANE-A bridge);
this file is the deterministic LANE-C set only.

It emits a verdict — PASS / FAIL / NEEDS-HUMAN — as JSON and as a human-readable
issue comment body, and routes the resulting status:

  PASS        -> eligible to close status:done   (the gate's signature is the
                 authority for done — §0.5 authority matrix)
  FAIL        -> status:in-progress + the listed gaps
  NEEDS-HUMAN -> needs-human (security P0/P1, or no automatable check exists)

The four deterministic checks (§4 Tier-0 #5):

  1. AC checklist  — every success-criteria checkbox in the issue body is ticked.
  2. test-floor    — the referenced test(s) are green now (parameterized test cmd).
  3. revert-check  — THE SPINE. In a throwaway `git worktree`, revert the fix
                     commit(s) and re-run the referenced test(s); assert >=1 goes
                     RED. Green-after-revert => FAIL (the test does not exercise
                     the fix). Mechanical, un-gameable, no LLM. This is the catch
                     for the inadequate-testing lie.
  4. infra smoke   — for criteria that name a runtime check (curl-route-200 /
                     daemon-up / RLS-denies), run it. RUNNER-DEPENDENT: cloud
                     runners can't reach the mini, so these require the
                     self-hosted runner. The hook is implemented and clearly
                     marked; it is SKIPPED (not failed) when the env says the
                     runner can't reach the mini.

Usage:
  python3 scripts/close_gate.py \
      --issue 33 \
      --fix-commits <sha>[,<sha>...] \
      [--test-cmd "pytest -q tests/test_rls.py::test_denies_cross_uid"] \
      [--repo .] \
      [--issue-json-file body.json | --issue-body-stdin] \
      [--smoke-cmd "curl -fsS https://.../health"] \
      [--can-reach-mini]            # set on the self-hosted runner
      [--json-out verdict.json] [--comment-out comment.md]

Exit code (VERDICT-IS-NOT-A-CI-FAILURE):
  A *verdict* — PASS, FAIL, or NEEDS-HUMAN — is the gate SUCCEEDING at its job:
  it reached a determination. That determination is conveyed via the posted
  comment + the routed status labels, NEVER via the process exit status. A
  non-zero exit on a normal FAIL/NEEDS-HUMAN verdict only makes GitHub mark the
  run "failed" and email the owner pure noise. So:

    0 = a verdict was reached (PASS, FAIL, or NEEDS-HUMAN) — see verdict.json /
        the comment / the routed label for which one.
    3 = TRUE ERROR only: usage / could not load the issue (gh/network) / a crash.

  (Legacy note: this gate formerly returned 1 on FAIL and 2 on NEEDS-HUMAN. That
  conflated "the gate worked and the answer is FAIL" with "the gate itself
  broke." The verdict now lives in `verdict.json["verdict"]`, not the rc.)
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile

# ---------------------------------------------------------------------------
# Verdicts
# ---------------------------------------------------------------------------
PASS = "PASS"
FAIL = "FAIL"
NEEDS_HUMAN = "NEEDS-HUMAN"

# A reached VERDICT is the gate SUCCEEDING — every verdict exits 0. Non-zero is
# reserved for TRUE errors (rc=3 in main(): could not load the issue / a crash).
# The verdict itself is carried by verdict.json + the comment + the routed label,
# NOT by the exit status (a non-zero on a normal FAIL just emails the owner noise).
EXIT_FOR_VERDICT = {PASS: 0, FAIL: 0, NEEDS_HUMAN: 0}

# Status routing per §4 Tier-0 #5 / §0.5.
STATUS_FOR_VERDICT = {
    PASS: "status:done",          # eligible to close (gate signature = authority)
    FAIL: "status:in-progress",   # bounce back with gaps
    NEEDS_HUMAN: "needs-human",   # the named human-exception set (§7 #4)
}

# A success-criteria line is a GitHub-flavored task-list item.
CHECKED_RE = re.compile(r"^\s*[-*]\s*\[[xX]\]\s+(.*\S)\s*$")
UNCHECKED_RE = re.compile(r"^\s*[-*]\s*\[\s\]\s+(.*\S)\s*$")

# Criteria phrasings that mean "this is a runtime/infra smoke check" (§2: for
# infra the criteria ARE the smoke check). Used to decide whether to expect a
# --smoke-cmd, so that "no automatable check" routes to NEEDS-HUMAN.
SMOKE_HINT_RE = re.compile(
    r"\b(curl|route\s*200|http\s*200|daemon\s*up|launchd|service\s*up|"
    r"rls\s*den|denies|health|smoke|reachable|listens?\s*on|port\s*\d)\b",
    re.IGNORECASE,
)

# Security severity that forces NEEDS-HUMAN even on a clean deterministic PASS
# (§5: a PASS on type:security posts to the Director; §7 #4 NEEDS-HUMAN on security
# P0/P1). We treat P0/P1 type:security as NEEDS-HUMAN regardless of checks.
def _is_security_p01(labels: list[str]) -> bool:
    labs = {l.lower() for l in labels}
    is_sec = "type:security" in labs
    is_p01 = ("p0" in labs) or ("p1" in labs)
    return is_sec and is_p01


# ---------------------------------------------------------------------------
# Issue acquisition
# ---------------------------------------------------------------------------
def load_issue(args) -> dict:
    """Return {number, title, body, labels:[str]} from the chosen source.

    Sources, in priority order:
      --issue-json-file  : a `gh issue view --json number,title,body,labels` blob
      --issue-body-stdin : raw markdown body on stdin (labels via --label, repeated)
      otherwise          : live `gh issue view` (needs GITHUB_TOKEN / gh auth)
    """
    if args.issue_json_file:
        with open(args.issue_json_file, "r", encoding="utf-8") as fh:
            raw = json.load(fh)
        return _normalize_issue(raw, fallback_number=args.issue)
    if args.issue_body_stdin:
        body = sys.stdin.read()
        return {
            "number": args.issue,
            "title": args.title or f"issue #{args.issue}",
            "body": body,
            "labels": list(args.label or []),
        }
    # Live path.
    out = subprocess.run(
        [
            "gh", "issue", "view", str(args.issue),
            "--json", "number,title,body,labels",
        ],
        capture_output=True, text=True, check=True,
    ).stdout
    return _normalize_issue(json.loads(out), fallback_number=args.issue)


def _normalize_issue(raw: dict, fallback_number: int | None) -> dict:
    labels = raw.get("labels") or []
    # gh returns labels as [{"name": ...}]; tolerate plain strings too.
    label_names = [l["name"] if isinstance(l, dict) else str(l) for l in labels]
    return {
        "number": raw.get("number", fallback_number),
        "title": raw.get("title", ""),
        "body": raw.get("body", "") or "",
        "labels": label_names,
    }


# ---------------------------------------------------------------------------
# Check 1 — AC checklist
# ---------------------------------------------------------------------------
def check_ac_checklist(body: str) -> dict:
    """All success-criteria checkboxes ticked? (§2 structured criteria, §11 AC#2.)

    Returns {ok, total, checked, unchecked:[text], detail}.
    No checkboxes at all => not automatable here => ok=None (caller may route to
    NEEDS-HUMAN if nothing else is automatable).
    """
    checked, unchecked = [], []
    for line in body.splitlines():
        m = CHECKED_RE.match(line)
        if m:
            checked.append(m.group(1))
            continue
        m = UNCHECKED_RE.match(line)
        if m:
            unchecked.append(m.group(1))
    total = len(checked) + len(unchecked)
    if total == 0:
        return {
            "ok": None, "total": 0, "checked": 0, "unchecked": [],
            "detail": "no success-criteria checkboxes found in issue body",
        }
    ok = len(unchecked) == 0
    return {
        "ok": ok,
        "total": total,
        "checked": len(checked),
        "unchecked": unchecked,
        "detail": (
            "all success criteria checked"
            if ok else
            f"{len(unchecked)} of {total} criteria still unchecked"
        ),
    }


# ---------------------------------------------------------------------------
# Test runner helpers
# ---------------------------------------------------------------------------
def _run_tests(test_cmd: str, cwd: str) -> tuple[bool, str]:
    """Run the (shell) test command in cwd. Return (green, combined_output)."""
    proc = subprocess.run(
        test_cmd, shell=True, cwd=cwd,
        capture_output=True, text=True,
    )
    out = (proc.stdout or "") + (proc.stderr or "")
    return proc.returncode == 0, out


def _tail(text: str, n: int = 1200) -> str:
    text = text.strip()
    return text if len(text) <= n else "…\n" + text[-n:]


# ---------------------------------------------------------------------------
# Check 2 — test-floor (green now)
# ---------------------------------------------------------------------------
def check_test_floor(test_cmd: str, repo: str) -> dict:
    green, out = _run_tests(test_cmd, repo)
    return {
        "ok": green,
        "cmd": test_cmd,
        "detail": "referenced test(s) green" if green else "referenced test(s) RED",
        "output_tail": _tail(out),
    }


# ---------------------------------------------------------------------------
# Check 3 — revert-check (THE SPINE)
# ---------------------------------------------------------------------------
def check_revert(repo: str, fix_commits: list[str], test_cmd: str) -> dict:
    """Revert the fix commit(s) in a throwaway worktree and re-run the test(s).

    A correct, fix-exercising test goes RED once the fix is gone. So:
        red-after-revert  => PASS (the test actually exercises the fix)
        green-after-revert => FAIL (the test is vacuous — the lie)

    Implementation: `git worktree add --detach` a scratch tree at HEAD, then
    `git revert --no-edit -n <commits>` (no commit needed — we just mutate the
    tree), then run the test command there. The worktree is always removed.
    """
    if not fix_commits:
        return {
            "ok": None,
            "detail": "no --fix-commits provided; cannot run the revert-check",
        }

    scratch = tempfile.mkdtemp(prefix="closegate-revert-")
    wt = os.path.join(scratch, "wt")
    added = False
    try:
        # Create a detached worktree at current HEAD.
        r = subprocess.run(
            ["git", "-C", repo, "worktree", "add", "--detach", wt, "HEAD"],
            capture_output=True, text=True,
        )
        if r.returncode != 0:
            return {
                "ok": None,
                "detail": "could not create git worktree for revert-check",
                "output_tail": _tail(r.stdout + r.stderr),
            }
        added = True

        # Revert the fix commit(s) into the worktree (no commit, -n).
        rv = subprocess.run(
            ["git", "-C", wt, "revert", "--no-edit", "-n", *fix_commits],
            capture_output=True, text=True,
        )
        if rv.returncode != 0:
            # A revert conflict means we cannot cleanly isolate the fix.
            return {
                "ok": None,
                "detail": (
                    "git revert of the fix commit(s) did not apply cleanly; "
                    "revert-check inconclusive — needs human"
                ),
                "reverted": fix_commits,
                "output_tail": _tail(rv.stdout + rv.stderr),
            }

        green_after_revert, out = _run_tests(test_cmd, wt)
        # PASS == the test went RED once the fix was reverted.
        ok = not green_after_revert
        return {
            "ok": ok,
            "reverted": fix_commits,
            "test_went_red_on_revert": (not green_after_revert),
            "detail": (
                "revert-check PASS: >=1 referenced test went RED after reverting "
                "the fix (the test exercises the fix)"
                if ok else
                "revert-check FAIL: test(s) stayed GREEN after reverting the fix "
                "— the test does NOT exercise the fix (vacuous lie)"
            ),
            "output_tail": _tail(out),
        }
    finally:
        if added:
            subprocess.run(
                ["git", "-C", repo, "worktree", "remove", "--force", wt],
                capture_output=True, text=True,
            )
        shutil.rmtree(scratch, ignore_errors=True)


# ---------------------------------------------------------------------------
# Check 4 — infra smoke (RUNNER-DEPENDENT)
# ---------------------------------------------------------------------------
def check_infra_smoke(body: str, smoke_cmd: str | None, can_reach_mini: bool) -> dict:
    """Run the infra/runtime smoke check, if the criteria call for one.

    RUNNER-DEPENDENT (§4 Tier-0 #5): curl-route-200 / daemon-up / RLS-denies all
    need to reach the mini, which cloud GitHub runners cannot. So:
      - criteria name a smoke check + we have --smoke-cmd + --can-reach-mini:
            run it; green => ok, red => not ok.
      - criteria name a smoke check but the runner can't reach the mini:
            SKIPPED (ok=None), clearly marked runner-dependent — the close-gate
            workflow must dispatch this leg to the self-hosted runner.
      - criteria name a smoke check but no --smoke-cmd given:
            ok=None (cannot automate here) — routes toward NEEDS-HUMAN.
      - criteria name no smoke check:
            ok=None, "not applicable".
    """
    wants_smoke = bool(SMOKE_HINT_RE.search(body))
    if not wants_smoke and not smoke_cmd:
        return {"ok": None, "applicable": False, "detail": "no infra smoke criteria"}

    if not can_reach_mini:
        return {
            "ok": None,
            "applicable": True,
            "runner_dependent": True,
            "detail": (
                "infra smoke criteria present but this runner cannot reach the "
                "mini — RUNNER-DEPENDENT. Dispatch this leg to the self-hosted "
                "runner. (cloud runners can't reach the mini.)"
            ),
        }
    if not smoke_cmd:
        return {
            "ok": None,
            "applicable": True,
            "detail": (
                "infra smoke criteria present but no --smoke-cmd provided; "
                "cannot automate — needs human-supplied smoke command"
            ),
        }
    green, out = _run_tests(smoke_cmd, os.getcwd())
    return {
        "ok": green,
        "applicable": True,
        "runner_dependent": True,
        "cmd": smoke_cmd,
        "detail": "infra smoke green" if green else "infra smoke RED",
        "output_tail": _tail(out),
    }


# ---------------------------------------------------------------------------
# Verdict assembly
# ---------------------------------------------------------------------------
def decide(issue: dict, checks: dict) -> tuple[str, list[str]]:
    """Combine check results into a verdict + reasons. (§4 #5, §5, §7 #4.)"""
    reasons: list[str] = []

    # Security P0/P1 always routes to a human (§7 #4), even on a clean pass.
    if _is_security_p01(issue["labels"]):
        reasons.append(
            "type:security P0/P1 — deterministic checks are advisory only; "
            "the Director must sign off (§7 #4 NEEDS-HUMAN)."
        )
        # Fold in any hard determinstic FAIL so the human sees it.
        for name in ("ac", "test_floor", "revert", "smoke"):
            c = checks.get(name) or {}
            if c.get("ok") is False:
                reasons.append(f"{name}: {c.get('detail')}")
        return NEEDS_HUMAN, reasons

    hard_fail = False
    automatable = False

    ac = checks["ac"]
    if ac["ok"] is False:
        hard_fail = True
        reasons.append(f"AC checklist: {ac['detail']}")
    elif ac["ok"] is True:
        automatable = True

    tf = checks["test_floor"]
    if tf.get("ok") is False:
        hard_fail = True
        reasons.append(f"test-floor: {tf['detail']}")
    elif tf.get("ok") is True:
        automatable = True

    rv = checks["revert"]
    if rv.get("ok") is False:
        hard_fail = True
        reasons.append(f"revert-check: {rv['detail']}")
    elif rv.get("ok") is True:
        automatable = True
    elif rv.get("ok") is None:
        # An inconclusive revert-check on a non-security item is a human signal:
        # the spine couldn't run, so we cannot mechanically certify the fix.
        reasons.append(f"revert-check inconclusive: {rv.get('detail')}")

    sm = checks["smoke"]
    smoke_unresolved = False
    if sm.get("ok") is False:
        hard_fail = True
        reasons.append(f"infra smoke: {sm['detail']}")
    elif sm.get("ok") is True:
        automatable = True
    elif sm.get("applicable"):
        # The issue's criteria DEMAND a runtime/infra check, but it could not be
        # run here (wrong runner — can't reach the mini — or no --smoke-cmd). We
        # must NOT certify done while a load-bearing runtime criterion is unverified.
        smoke_unresolved = True
        reasons.append(f"infra smoke: {sm['detail']}")

    if hard_fail:
        return FAIL, reasons

    # An applicable-but-unrun infra smoke check blocks a clean PASS -> needs human
    # (dispatch to the self-hosted runner, or have a human verify the runtime check).
    if smoke_unresolved:
        return NEEDS_HUMAN, reasons

    # No hard fail. If nothing was actually automatable, we can't certify -> human.
    revert_ran = rv.get("ok") is True
    if not automatable or not revert_ran:
        if not reasons:
            reasons.append(
                "no automatable check produced a positive verdict (no green "
                "test-floor + red-on-revert) — cannot mechanically certify done"
            )
        return NEEDS_HUMAN, reasons

    reasons.append("all deterministic checks passed")
    return PASS, reasons


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------
MARKER = "<!-- close-gate:verdict -->"  # durable marker the transition-guard reads


def render_comment(issue: dict, verdict: str, reasons: list[str], checks: dict) -> str:
    badge = {PASS: "✅ PASS", FAIL: "❌ FAIL", NEEDS_HUMAN: "🛑 NEEDS-HUMAN"}[verdict]
    lines = [
        MARKER,
        f"## Deterministic close-gate — **{badge}**",
        "",
        f"Issue #{issue['number']} — *{issue['title']}*",
        "",
        "_Deterministic gate only (LANE-C). No LLM, no paid API "
        "(SDLC §4 Tier-0 #5, §5)._",
        "",
        "### Verdict reasons",
    ]
    lines += [f"- {r}" for r in reasons] or ["- (none)"]
    lines += ["", "### Evidence", ""]

    def block(title: str, c: dict) -> None:
        state = {True: "ok", False: "FAIL", None: "n/a"}[c.get("ok")]
        lines.append(f"- **{title}** — `{state}` — {c.get('detail','')}")
        for key in ("cmd", "reverted", "test_went_red_on_revert"):
            if key in c:
                lines.append(f"  - {key}: `{c[key]}`")

    block("AC checklist", checks["ac"])
    block("test-floor", checks["test_floor"])
    block("revert-check (spine)", checks["revert"])
    block("infra smoke (runner-dependent)", checks["smoke"])

    lines += [
        "",
        f"### Routing → `{STATUS_FOR_VERDICT[verdict]}`",
        {
            PASS: "Eligible to close `status:done`. The gate's signature is the "
                  "authority for done (§0.5).",
            FAIL: "Bounced to `status:in-progress` with the gaps above. A vacuous "
                  "test (green-after-revert) is caught.",
            NEEDS_HUMAN: "Routed to `needs-human` (security P0/P1, or no automatable "
                         "check could certify done).",
        }[verdict],
    ]
    return "\n".join(lines) + "\n"


def build_verdict_json(issue: dict, verdict: str, reasons: list[str], checks: dict) -> dict:
    return {
        "issue": issue["number"],
        "title": issue["title"],
        "labels": issue["labels"],
        "verdict": verdict,
        "status": STATUS_FOR_VERDICT[verdict],
        "marker": MARKER,
        "reasons": reasons,
        "checks": checks,
        "llm_used": False,
        "paid_api_used": False,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def parse_args(argv: list[str]) -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Deterministic close-gate (no LLM).")
    p.add_argument("--issue", type=int, required=True, help="issue number")
    p.add_argument("--fix-commits", default="",
                   help="comma-separated commit SHA(s) that constitute the fix")
    p.add_argument("--test-cmd", default="pytest -q",
                   help="shell command that runs the referenced test(s)")
    p.add_argument("--repo", default=".", help="path to the git repo under test")
    p.add_argument("--smoke-cmd", default=None,
                   help="optional infra smoke command (curl/daemon/RLS)")
    p.add_argument("--can-reach-mini", action="store_true",
                   help="set on the self-hosted runner that can reach the mini")
    p.add_argument("--issue-json-file", default=None,
                   help="path to a `gh issue view --json ...` blob (offline)")
    p.add_argument("--issue-body-stdin", action="store_true",
                   help="read the issue body markdown from stdin (offline)")
    p.add_argument("--title", default=None, help="issue title (with --issue-body-stdin)")
    p.add_argument("--label", action="append", default=None,
                   help="issue label (repeatable; with --issue-body-stdin)")
    p.add_argument("--json-out", default=None, help="write verdict JSON here")
    p.add_argument("--comment-out", default=None, help="write comment body here")
    return p.parse_args(argv)


def main(argv: list[str]) -> int:
    args = parse_args(argv)
    repo = os.path.abspath(args.repo)
    fix_commits = [c.strip() for c in args.fix_commits.split(",") if c.strip()]

    try:
        issue = load_issue(args)
    except subprocess.CalledProcessError as e:
        sys.stderr.write(f"close_gate: failed to load issue: {e}\n")
        return 3
    except (OSError, json.JSONDecodeError) as e:
        sys.stderr.write(f"close_gate: failed to load issue: {e}\n")
        return 3

    checks = {
        "ac": check_ac_checklist(issue["body"]),
        "test_floor": check_test_floor(args.test_cmd, repo),
        "revert": check_revert(repo, fix_commits, args.test_cmd),
        "smoke": check_infra_smoke(issue["body"], args.smoke_cmd, args.can_reach_mini),
    }

    verdict, reasons = decide(issue, checks)
    comment = render_comment(issue, verdict, reasons, checks)
    vjson = build_verdict_json(issue, verdict, reasons, checks)

    if args.comment_out:
        with open(args.comment_out, "w", encoding="utf-8") as fh:
            fh.write(comment)
    if args.json_out:
        with open(args.json_out, "w", encoding="utf-8") as fh:
            json.dump(vjson, fh, indent=2)
            fh.write("\n")

    # Always print both to stdout so a workflow can capture them without files.
    print(comment)
    print("---VERDICT-JSON---")
    print(json.dumps(vjson, indent=2))

    return EXIT_FOR_VERDICT[verdict]


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
