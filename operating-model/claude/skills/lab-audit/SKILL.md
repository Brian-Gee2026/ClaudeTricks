---
name: lab-audit
description: >
  Estate-wide governance audit of the multi-repo lab (governance, platform,
  app-records, app-finance, app-archive). Invoke when the user types /lab-audit,
  asks "are we following our SDLC/governance", or after a major build wave lands.
  Recommended cadence: monthly. Produces a per-check PASS/PARTIAL/FAIL scorecard
  with evidence, files/updates issues for gaps, and ends with the closing
  ceremony. Free: gh CLI + on-plan leaf agents only.
---

# lab-audit — periodic estate governance audit

You are running the lab's recurring governance audit from the governance seat.
Model tier does not matter — the checklist and the leaf agents do the heavy
lifting. Read the operating model documentation on issue status lifecycle +
close-gate if not already familiar. **Everything here is read-only until the
Report step.**

## Checklist (dispatch A–D to code-tracer agents in parallel; E–G inline)

**A. Issue hygiene (per repo, sample — don't exhaust):** open issues missing a
`status:*` label (and their age); `status:in-progress`/`in-review` stale >7
days; issues in `status:draft` with recent commits referencing them (canon
violation: work before criteria). Tool: `gh issue list --json
number,title,labels,updatedAt` + `git log --grep`.

**B. Close-gate compliance (per repo):** the 5 most recent substantive closed
issues — does each have a close-evidence comment (what ran, on what, result)
BEFORE close, and terminal labels `status:done` + `gate:close-pass`? Flag
evidence-without-labels and labels-without-evidence separately.

**C. Gate machinery + freshness:** per repo confirm `.githooks/pre-commit`,
`scripts/check_system_manifest.py`, `docs/system_manifest.json`,
`.github/workflows/` set present; run each repo's checker (expect exit 0; any
`WARN [code-map]` = stale map → queue /codemap-refresh); BACKLOG.md carries the
`GENERATED FILE — DO NOT EDIT` banner + valid content-sha (run
`scripts/check_backlog_banner.py --stdin < BACKLOG.md` where it exists).

**D. Actions budget (free tier, 2,000 min/mo):** `gh run list` per repo — failure
spikes, unexpected run volume, any workflow re-enabled without its trigger diet,
any new cron/issues-trigger added since last audit. If workflows are disabled,
just report that state.

**E. Hooks + plugins health (inline, laptop):** all wired hooks in
`~/.claude/settings.json` exist and pass `bash -n` / `python3 -m py_compile`;
`~/.claude/ceremony-bypass.log` — any unexplained escape-hatch uses since
last audit; installed plugins list vs. expected; re-run the paid-path grep on
any NEWLY installed/updated plugin and confirm no paid-API dependencies are
present in the environment.

**F. Review-ritual adoption (inline):** sample recent close-evidence comments —
are code-review/security-review findings being cited? If consistently absent,
recommend escalating the nudge.

**G. Deferred-work sweep (inline):** open `type:plan` issues with unticked
criteria older than 14 days — anything parked without a blocker stated.

## Report

1. Scorecard: per check PASS/PARTIAL/FAIL with 1–3 lines of evidence.
2. Gaps ranked by severity; each gap gets exactly one disposition — new issue
   (with testable criteria), comment on an existing issue, or dropped with
   stated reason. Cross-boundary gaps → governance issues; in-app gaps →
   note for the app team, don't file (authority matrix).
3. Compare against the previous audit (session-notes system: search for prior
   audit logs; first run baseline from existing session logs). Call out
   regressions explicitly.
4. Closing ceremony: issues updated, vault session log written, repo-sync any
   doc changes. Log the audit in governance `audit_log.md`.

## Guardrails

- Read-only until Report; never "fix while auditing" beyond label corrections
  with an evidence comment.
- No paid API anywhere; no unattended runs — this skill runs supervised in an
  interactive session only.
- Do not run while a known live session owns a repo's checkout — skip that
  repo and say so.
