# Registry Patterns — "check before you build"

Two registries prevent an agent estate from re-solving solved problems or
stepping on shared infrastructure. Both follow the same law: **a narrative
doc for humans + a machine-checkable twin for gates.** A registry that is
only prose is guidance; guidance drifts.

## 1. The platform inventory (`PLATFORM.md`) — "the adult in the room"

Lives in the `platform` repo; referenced from every other repo's `CLAUDE.md`.

**What it lists:** every database (+ owner, roles, extensions), every port
and what listens on it, every daemon (+ label, run-as user, plist/unit path),
every reverse-proxy route, every external dependency, and the hardware
budget assumptions (what's scarce: RAM, GPU).

**The rule it enforces:** before any session proposes new infrastructure —
a service, port, database, user, scheduled job — it MUST check this file.
If what's needed exists, use it. If not, the session writes a short
`INFRA_PROPOSAL.md` (what, why, resource cost, alternatives considered)
and **stops**. No autonomous installs.

**Triggers that require the check:** new DB / DB user / extension · new port ·
new daemon or scheduled job · new external service · schema migrations that
drop or rename.

**The machine twin:** an approved-inventory file (`APPROVED_INVENTORY.md` or
JSON) diffed against live host state by a checker script on a schedule —
anything running that isn't approved, or approved that isn't running, is a
finding. Plus each repo's `docs/system_manifest.json`, which the doc-sync
gate keeps honest per-repo: changing a daemon, DB connection site, or writer
requires updating the manifest in the **same commit**, enforced by
pre-commit hook and CI.

## 2. The capability registry (`CAPABILITIES.md`)

Lives with the shared-library code (e.g. `platform/labs/`).

**What it lists:** every shared, reusable capability — a UI kit, a nav
component, an auth helper, the SDLC gate library itself — one row each:
name, what it does, where it lives, how to consume it.

**The rule it enforces:** before building a feature that feels generic
(upload, sharing, review, navigation, theming), **check here first**. If you
build something shared-worthy, **add it here** in the same change.

**Why it exists:** in a multi-repo estate where different sessions (or
different people) work different repos, the same generic feature otherwise
gets built twice, differently, with two bug surfaces.

## 3. Closing the loop: from guidance to gate

Both registries start as conventions — and conventions are exactly the
"guided, not gated" failure the operating model warns about. The upgrade
path:

1. **Intake field:** the issue template gets a "cross-repo check" section —
   links to the searched registries and the other repos' issues, or "none
   found." Cheap, but non-binding alone.
2. **Definition-of-Ready extension:** the repo-hygiene gate, on
   `backlog → ready`, searches the *other* repos' open issues for
   title/keyword overlap and consults the capability manifest; a hit applies
   a `hygiene:cross-repo-conflict` label + `needs-triage` for the governance
   session to triage. Advisory first; enforce once it proves itself.
3. **Machine-diffable registries:** the checker scripts above, so the gate
   compares against *built reality*, not just prose claims.

The general lesson: **an inventory nobody is forced to consult will
eventually be wrong, and an inventory that's wrong is worse than none** —
sessions learn to distrust it. The doc-sync gate (same-commit manifest
updates) is what keeps the machine twins alive.
