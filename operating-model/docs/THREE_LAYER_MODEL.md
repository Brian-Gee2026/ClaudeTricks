# The Three-Layer Model — how strategy, governance, and execution split

The canonical description of how work is organized across tools. Loaded as
context by agent sessions (so they know which layer they're operating in) and
by the Director (as a stable reference when things start to drift).

## TL;DR

Three layers, named: **Strategy** (brainstorm and plan), **Governance**
(rules and inventory), **Execution** (code and infra ops). All work happens
in **Claude Code CLI on the laptop**. The laptop reaches the server via
**plain SSH** (`ssh labhost`) — Claude Code has the Bash tool, and it uses
that to run commands remotely. There is no bridge plugin, no MCP execution
path, no daemon in the middle.

Web chat is fine for purely conversational work (drafting, research) but is
not part of the execution path.

## The three layers

### Layer 1 — Strategy

**Where:** Claude Code on the laptop, inside the relevant repo, on the
strongest available model.

**What happens here:** brainstorming, architecture, design arguments, plan
drafting, review of significant decisions. The output of strategy is a plan
filed as a GitHub Issue (a plan IS an issue — see the operating model), with
long-form prose optionally landing as a banner-locked reference doc.

**Why on the laptop:** strategy is interactive thinking; it's where the human
is, and the laptop has direct git access so plans land in version control
immediately.

### Layer 2 — Governance

**Where:** version-controlled markdown that rides with the code:

- `CLAUDE.md` per repo — repo-specific rules, scope, conventions
- `PLATFORM.md` in the platform repo — the shared inventory of everything
  running on the server (databases, ports, daemons, proxy routes), referenced
  from every other repo's `CLAUDE.md`
- The charter + operating model in the governance repo

**What it enforces:** the "adult in the room" rule. Before any session
proposes new infrastructure (service, port, database), it checks
`PLATFORM.md`. New infrastructure requires a written proposal and a stop —
no autonomous installs.

**Why version-controlled:** the rules show up in every session automatically,
and rule changes are themselves auditable diffs.

### Layer 3 — Execution

**Where:** the same Claude Code session, using Bash + SSH to reach the server.

**What happens here:** writing code, running tests, hitting the database,
calling the local LLM, running migrations, deploying. The server is just a
remote machine reached over SSH.

## How the laptop reaches the server

- **SSH alias:** `ssh labhost` (via a tunnel hostname, e.g. cloudflared —
  never a hardcoded LAN IP; IPs move, the alias doesn't).
- **PATH gotcha:** non-interactive SSH does not load the interactive shell's
  PATH. Prefix remote commands with the package-manager bin dir
  (`PATH=/opt/homebrew/bin:$PATH`) or use absolute paths.

## Handoff: how the layers talk

There is no bridge component. The handoff between Strategy and Execution
happens **within a single session**, with the repo as the durable record:

1. A plan is drafted and filed as a GitHub Issue (source of truth), with any
   long-form design doc banner-locked in the repo.
2. The same session executes: Bash + `ssh labhost "<command>"`, writing
   outcomes back to the repo and the issue.
3. The issue and the committed changes remain as the audit trail.

**The Director observes. They do not paste between sessions.** If the human
is copy-pasting output from one AI session into another, something has been
bypassed and the standard has been violated — that's the signal to stop and
fix the tooling, not to keep pasting.

## Model routing summary

- **Top-tier model** (Layer 1, laptop): strategy, architecture, plan
  drafting, deep design arguments
- **Mid-tier model** (Layer 3): general code execution, refactors, tests
- **Small/cheap model** (Layer 3): classification, batch triage, mechanical
  edits
- **Local LLM via Ollama** (called from application code): bulk
  standardization inside data pipelines — free, private, small-hardware
- **Paid API from application code**: the escalation path for gold-source
  production moments ONLY — never development (see the operating model's
  money gate)

See `DELEGATION_POLICY.md` for the agent-level version of this routing.

## Retired patterns (do not reintroduce)

Each of these was tried and retired; they are listed so a future session
doesn't reinvent them:

- **A separate orchestration app driving sessions over MCP.** It drifted
  across sessions and produced sprawl. One CLI session with SSH replaced it.
- **A long-running orchestrator daemon / proposal-inbox poller.** Governance
  is ordinary sessions + GitHub Issues, not a resident process.
- **A GitHub PR/issue bot that launches the coding agent in CI.** Banned
  outright — a CI-launched agent bills outside every spending control (see
  the money gate, MG-4).
- **Ad-hoc tunneling / port-forwarding inventions.** Reachability is solved
  once (one tunnel); new relay patterns are not invented per-task.

## Notes to a new session reading this file

- You operate in both Layer 1 and Layer 3 from one laptop session: plan,
  then execute over SSH. There is no separate bridge to call.
- Always read the repo's `CLAUDE.md` and the referenced `PLATFORM.md` before
  making any infrastructure-touching suggestion.
- Do not propose installing new services, opening new ports, or spinning up
  new containers. Use what's in `PLATFORM.md`; if you genuinely need new
  infrastructure, write a proposal and stop.
- The Director is a strong systems thinker but not a hands-on modern
  developer: explain reasoning, don't assume framework familiarity, don't be
  terse with rationale.
