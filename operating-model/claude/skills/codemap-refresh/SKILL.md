---
name: codemap-refresh
description: >
  Refresh a lab repo's docs/CODE_MAP.md from the material git delta since its
  generated-at stamp, then bump the stamp. Invoke whenever (a) the user types
  /codemap-refresh, (b) check_system_manifest.py prints a "WARN [code-map]"
  staleness advisory (pre-commit, Stop hook, or CI), (c) the SessionStart
  vault-context banner flags the current repo's map as stale, or (d) a closing
  ceremony is about to sync a repo whose map lags the session's code changes.
  Companion tooling to the CODE_MAP convention (Phase-B advisory).
---

# codemap-refresh — patch the code map from the git delta, bump the stamp

CODE_MAP.md is a **curated orientation doc** — an index that tells a session
what to read instead of sweeping the repo. A refresh is a **patch, not a
regeneration**: preserve the map's structure, prose, and canon-vs-historical
judgments; fold in what actually changed.

## Steps

1. **Scope.** Identify the repo (the multi-repo lab each carries
   `docs/CODE_MAP.md`). Read the map's `generated-at:` stamp
   (`generated-at: [<sha> ·] YYYY-MM-DD`, first line of frontmatter/header).

2. **Delta.** List material commits since the stamp:
   `git log --oneline --since=<stamp-date>T23:59:59 -- '*.py' '*.sh' '*.js' '*.html' '*.css' .github/workflows`
   If the delta is large (>15 commits) or spans unfamiliar modules, dispatch
   **code-tracer** (sonnet — never haiku; map synthesis needs judgment) with
   the commit list to summarize per-module what changed: new/removed scripts,
   moved responsibilities, new gates/workflows, retired paths. For small
   deltas, read the touched files' headers directly.

3. **Patch the map.** Edit `docs/CODE_MAP.md` in place:
   - Update sections whose contents changed (scripts inventories, gate lists,
     workflow tables, module descriptions).
   - Remove or mark-historical anything retired; add anything new with a
     one-line purpose.
   - Consolidate any trailing `_Delta YYYY-MM-DD…_` notes (appended by past
     checkpoints) INTO the body sections, then delete the delta notes —
     deltas are a stopgap, not an archive.
   - Do NOT restructure the document or change its conventions.

4. **Stamp.** Set the header to `generated-at: <short-sha-of-HEAD> · <today>`.
   (Some repos' stamp omits the sha — keep each repo's existing stamp style.)

5. **Verify.** Run `python3 scripts/check_system_manifest.py` from the repo
   root — the `WARN [code-map]` line must be gone and exit must be 0.

6. **Sync.** Commit via the repo-sync agent (haiku), message
   `docs(codemap): refresh from <stamp-date> delta` — or, if invoked
   mid-session before a larger checkpoint, fold it into that checkpoint's
   commit for the same repo. Never leave the refresh uncommitted.

## Guardrails

- If another live session owns the repo's checkout (unexpected working-tree
  churn), STOP and report — never patch a moving target.
- WARN thresholds are manifest-tunable (`code_map_advisory` in
  `docs/system_manifest.json`); don't silence a warn by raising thresholds —
  refresh the map instead.
- $0 rule: git + Read/Edit + on-plan agents only. No paid API anywhere.
