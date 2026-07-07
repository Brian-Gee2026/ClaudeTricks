# Model-Tiering & Delegation Policy — the orchestrator and its leaf agents

The main session is the **orchestrator** (your strongest model): it plans,
decides, synthesizes, and talks to the human. It should NOT burn
top-tier tokens on work a cheaper tier can do. Delegate via subagents:

| Work | Agent | Model tier |
|---|---|---|
| Multi-file reading, grep sweeps, tracing call paths, remote inspection | `code-tracer` | mid (e.g. Sonnet), medium effort |
| Research beyond the repo: web search/fetch, doc lookups, cross-source synthesis | `researcher` | mid, medium effort |
| Hard reasoning: root-cause, architecture, design analysis | `deep-reasoner` | high (e.g. Opus) |
| Fully-specified edits, boilerplate, running given tests | `mechanic` | small (e.g. Haiku) |
| git stage/commit/push, repo↔GitHub sync | `repo-sync` | small |

(Agent definitions for all five, plus three vendored review analyzers, are in
`../claude/agents/`.)

## The leaf-safe rule (the load-bearing constraint)

**Delegate ONLY to named leaf-safe agents — never to a general-purpose or
catch-all agent type.** Catch-all agents carry the Agent tool themselves, so
a cheaper model ends up orchestrating and nesting its own subagents — and a
nested subagent has no channel to the human (prompts auto-resolve, only the
final message returns), so it **fails blind**. The named agents are leaf-safe
by construction: they carry Read/Grep/Bash/Edit-class tools, never the Agent
tool.

**A task too vague for a leaf agent is the orchestrator's signal to decompose
it itself — not to hand decomposition down.**

Enforce this with a hook, not a habit: `claude/hooks/block-unlisted-subagents.py`
is a PreToolUse hook that denies any Agent call whose type isn't on the
allowlist in your settings. The settings allowlist is the enforced source of
truth; the table above is the routing guidance.

## Rules

- Each delegated task must be **bounded and self-contained** — the agent gets
  no conversation history, so the prompt must carry everything it needs.
- Agents return only their final message; the orchestrator keeps
  **conclusions, not transcripts**.
- **All git commits/pushes go through `repo-sync`** — the orchestrator and
  the reasoning agents never run `git commit` themselves. Batch syncs at
  natural checkpoints, but never end a session with unsynced repos.
- Agents that produce findings **write them into the repo's existing docs**
  before finishing; the orchestrator then dispatches repo-sync.
- Inline (orchestrator-level) work is fine for: single-file quick looks,
  conversation, decisions, and synthesis. **When unsure, delegate.**
- Re-check the tier pairings whenever a model alias moves to a new
  generation — "medium effort" on one generation may equal "high" on the
  prior one.

## Why this shape

Three forces, one design:

1. **Cost.** Orchestrator tokens are the most expensive thing in the room;
   grep sweeps are the cheapest. Tiering routes each unit of work to the
   cheapest tier that does it well.
2. **Context.** The orchestrator's context window is the scarce shared
   resource of a long session. Delegation means it holds conclusions, not
   file dumps — a session that reads everything inline dies early.
3. **Blast radius.** Leaf agents can't spawn agents, can't talk to the
   human, and (except mechanic/repo-sync) can't write. A confused leaf agent
   returns a bad answer — it cannot compound.

## Observability

Log subagent completions (agent type, duration, task summary) to a JSONL
file via a SubagentStop hook (`claude/hooks/log-agent.sh`) so you can audit
what got delegated where — and notice when the orchestrator is doing leaf
work inline.
