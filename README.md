# ClaudeTricks

Small, battle-tested hooks for [Claude Code](https://docs.claude.com/en/docs/claude-code) — each one turns a good habit into a **gate the assistant can't skip**.

> A Claude Code *hook* is a script the CLI runs at a lifecycle moment — before a tool
> runs, or when a session tries to stop. Because the runtime enforces it, the assistant
> can't route around it mid-session. That's what makes these useful as guardrails.

## Tricks

| Trick | Hook type | What it does |
|---|---|---|
| [🐕 Leash](leash/) | `PreToolUse` | Stops subagents from spawning subagents — allowlist which agent types a session may launch. Cures runaway token burn, "hung" sessions, and questions trapped in nested subagent windows. |
| [🕛 Closing Time](closing-time/) | `Stop` | Won't let a session end with unpushed commits (or no session note) — so the next session resumes cheaply instead of re-deriving everything from scratch. |

## The full operating model

The tricks above are extracts from a complete, working operating model for
running a multi-repo software estate where Claude Code does the execution and
one human directs. The whole thing — the SDLC with machine gates, the
governance charter, the agent delegation policy, the hooks, skills, and gate
scripts — is published (sanitized) in [**operating-model/**](operating-model/).
Start with its [README](operating-model/README.md).

## What these bind

Every hook here binds the **assistant**, not you. A running session can't disable a
configured hook; you — the config owner — always can. They're guardrails, not handcuffs.

Each trick is self-contained in its own folder with its own README, script, and an
example `settings.json` snippet. Copy what you need.
