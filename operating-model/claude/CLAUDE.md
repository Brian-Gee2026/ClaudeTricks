# User-level Claude Code instructions (all projects) — template

This is the `~/.claude/CLAUDE.md` that binds the operating model at session
level. Everything here is generic; tune the names to your estate.

## ⛔ PAID API — explicit per-run human consent required (HARD RULE, read first)

**No component, script, job, agent, or pipeline run may consume metered
API tokens without the Director's explicit, in-the-moment consent for THAT
run.** This rule exists because unattended runs cost real money before the
gates existed — it is a money/trust issue, not a style preference.

- **Default-off.** Treat every paid-API path as off unless the human just
  said "yes, run it" for this specific invocation. Consent is **per-run,
  never standing** — prior approval of a similar job does NOT carry forward.
- **The line is free vs paid.** Free is fine without asking: local LLMs via
  Ollama, subscription-harness models (the orchestrator + subagents), CI on
  the built-in token. **Paid = anything that hits the metered API with an
  API key.**
- **⛔ NEVER run the coding agent itself in CI.** A CI-launched agent
  authenticates with OAuth and an API token and runs **unbounded** — outside
  every cap. No agent-launching Action in any workflow; no runner registered
  to run one. Plain deterministic CI on the built-in token stays fine.
- **Before running ANY command that exports the API key or invokes a paid
  path, STOP and get explicit consent.** Name the cost risk in the ask.
- Assume any "ingest/extract/enrich/vision" job in an application repo is
  paid until proven otherwise.
- If a task seems to require a paid run: **describe the run + its rough
  cost, ask, and wait.** Never infer consent from the task being assigned.

(Machine gates back this rule — a PreToolUse deny hook, a production arm
token, a shared cap + ledger — but the rule binds regardless of them.)

## Model-tiering & delegation policy

The main session is the **orchestrator** (top-tier model): it plans, decides,
synthesizes, and talks to the human. It does NOT burn orchestrator tokens on
work a cheaper tier can do. Delegate via the Agent tool:

| Work | Agent | Model |
|---|---|---|
| Multi-file reading, grep sweeps, tracing, remote inspection | `code-tracer` | mid-tier, medium effort |
| Research beyond the repo: web search, doc lookups, synthesis | `researcher` | mid-tier, medium effort |
| Hard reasoning: root-cause, architecture, design analysis | `deep-reasoner` | high-tier |
| Fully-specified edits, boilerplate, running given tests | `mechanic` | small |
| git stage/commit/push, repo↔GitHub sync | `repo-sync` | small |

**Delegate ONLY to named leaf-safe agents — never a general-purpose /
catch-all type.** Catch-alls carry the Agent tool, so a cheaper model ends up
orchestrating and nesting subagents — and a nested subagent has no channel to
the human, so it fails blind. **A task too vague for a leaf agent is the
orchestrator's signal to decompose it itself, not to hand decomposition
down.** (The settings allowlist + `block-unlisted-subagents.py` hook are the
enforced source of truth; this table is the routing guidance.)

Rules:
- Each delegated task must be **bounded and self-contained** — the agent gets
  no conversation history; the prompt must carry everything it needs.
- Agents return only their final message; the orchestrator keeps conclusions,
  not transcripts.
- **All git commits/pushes go through `repo-sync`** — the orchestrator and
  reasoning agents never run git commit themselves. Batch at natural
  checkpoints; never end a session with unsynced repos.
- Agents that produce findings write them into the repo's existing docs
  before finishing; the orchestrator then dispatches repo-sync.
- Inline work is fine for: single-file quick looks, conversation, decisions,
  synthesis. When unsure, delegate.

## Documentation-sync enforcement (ALL code projects)

Docs drift when updating them is a separate, skippable step — so it's a
**machine gate, not a habit**, in every code repo: `docs/DATA_FLOW.md`
(human map) + `docs/system_manifest.json` (machine spine) +
`scripts/check_system_manifest.py` (exits non-zero on drift), gated by the
repo pre-commit hook, CI, and a global Stop hook.

**The rule (non-negotiable):** changing a daemon/service, DB-connection
site, writer, or access-control coverage requires updating the manifest +
data-flow doc in the **SAME commit** — the hook rejects it otherwise. A code
repo lacking this gate: set it up; don't leave it undocumented.

## ⛔ CLOSING-CEREMONY canon — end every effort with durable artifacts (machine-gated)

Skipped end-of-effort artifacts tax the NEXT session enormous token counts
of re-derivation — so this is a gate, not a habit. **Before yielding at the
end of an effort (or a pause/handoff), run the ceremony — never defer it:**

1. **Issues** — state + evidence posted, criteria verified, status moved
   (this IS the SDLC close-gate).
2. **Session log** — a short digest to your notes system: decisions, what
   changed, results, next steps.
3. **CODE_MAP refresh** — if the session materially changed a repo with a
   `docs/CODE_MAP.md`, patch it + bump `generated-at` before repo-sync.
4. **Sync** — `repo-sync` commits + pushes every touched repo.

**Enforcement:** a Stop hook (`closing-ceremony.sh`) hard-blocks the stop
while any repo has unpushed commits; soft-nudges on a missing session log or
uncommitted changes. An escape hatch exists (a marker file that self-expires
after 24h) — a one-day bypass, not a standing off-switch; a loop-cap
auto-downgrades the gate to advisory after repeated blocks.

## ⛔ SDLC CLOSE-GATE canon — no issue closes on judgment alone

Born of a real incident: work marked COMPLETED while unbuilt, caught by
human eyes rather than a gate. A plan IS an issue; the issue is the gate:

1. **Before starting:** explicit **testable success criteria** on the issue;
   no structured criteria ⇒ cannot leave `status:draft`.
2. **In flight:** one status lifecycle — `draft → backlog → ready →
   in-progress → in-review → deployed-watch → done`, with `status:failed` as
   a first-class branch (never a silent bounce).
3. **Before close:** verify **each** criterion and **post the evidence**
   (what ran, where, result) as a comment, then tick. QC is against
   criteria, not vibes.
4. **Direct-stamping `status:done` is FORBIDDEN.** No criteria or no
   evidence ⇒ no close. "Looks done" is not done.

Machine enforcement is the deterministic close-gate (test-floor +
revert-check + transition-guard; free, no LLM); where it isn't wired yet,
**this canon is the floor.** Paid API is never used to enforce it.
