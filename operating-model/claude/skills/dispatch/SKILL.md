---
name: dispatch
description: >
  Delegation playbook for the lab's orchestrator sessions. Invoke when planning
  any multi-step task, when a task is too vague to hand straight to a leaf
  agent, or whenever the orchestrator is about to read more than ~2 files
  inline. Encodes how to decompose work, write bounded leaf-agent prompts, run
  agents in parallel, and keep orchestrator context lean. Companion to the
  model-tiering table in ~/.claude/CLAUDE.md (that table says WHO; this skill
  says HOW).
---

# Dispatch — how to delegate efficiently

The orchestrator's context is the scarcest resource in the lab. Every file read
inline, every transcript held, every re-derivation of "how do I phrase this
delegation" is budget stolen from planning and synthesis. This skill is the
frozen answer.

## 1. Route in ten seconds

| Task shape | Agent | Notes |
|---|---|---|
| "Where/what/how does the code…" — any search, trace, multi-file read, remote `ssh labhost` inspection | `code-tracer` | Default for ANY look at >1 file |
| "What does the world say…" — web, docs, specs, option comparison | `researcher` | Returns conclusions, never decisions |
| "Why is this happening / which design…" — one bounded hard question | `deep-reasoner` | Give it the evidence locations, not the evidence |
| "Apply this exact change / run this command" | `mechanic` | Only when the change is fully specified |
| "Commit and push" | `repo-sync` | ALL git writes go here, batched at checkpoints |

Tie-breakers:
- Search that ends in a judgment call → `code-tracer` gathers, orchestrator
  judges (or a second dispatch to `deep-reasoner` with the tracer's findings
  pasted in). Never ask one agent to both find and decide.
- Too vague for any row → decompose it yourself (§3). Never hand decomposition
  down — general-purpose/catch-all agents are banned (they nest subagents
  blind — see the leaf-safe rule).
- Genuinely one file, one quick look → inline is fine. Two files → delegate.

## 2. The bounded-prompt contract

Leaf agents get NO conversation history. Every delegation prompt must carry all
five of these or the agent fails blind:

1. **Goal** — one sentence, outcome-shaped ("determine X", not "look into X").
2. **Scope** — exact repos/paths/hosts, and explicitly what's OUT of scope.
3. **Context it can't discover** — decisions already made, constraints
   (e.g. "paid API is banned; free paths only"), relevant issue numbers,
   what previous agents already found.
4. **Output contract** — the exact shape of the final message ("return ≤30
   lines: a verdict line, then evidence as file:line bullets") and, for
   finding-producing work, WHICH repo doc to write into (PLANS/, BACKLOG.md,
   the issue) before finishing.
5. **Stop conditions** — when to give up and report instead of thrashing
   ("if the config isn't under X or Y, stop and report what you checked").

An unbounded prompt ("investigate the ingest pipeline") is the #1 token leak:
the agent wanders, returns a wall of text, and the orchestrator re-reads it all.

### Skeletons (copy, fill brackets)

**code-tracer**
```
Goal: [one sentence — the question this answers].
Scope: [repo paths / `ssh labhost` paths]. Do not look at [exclusions].
Context: [decisions/constraints/issue #s the agent can't discover].
Report back ≤[N] lines: verdict first, then evidence as file:line bullets.
If findings are substantial, write them into [repo doc] and say so.
Stop if [condition]; report what you checked instead of guessing.
```

**researcher**
```
Question: [specific, answerable question].
We need this to decide: [the decision — so it knows what evidence matters].
Constraints: [versions, platforms, "must be free-tier", date-sensitivity].
Return: recommendation + 2-3 sentence rationale + sources. ≤[N] lines.
Do not decide [thing reserved for the orchestrator/Director]; present the tradeoff.
```

**deep-reasoner**
```
Question: [one bounded question].
Evidence locations: [files/paths — it reads them itself; don't paste files,
paste only conclusions from earlier agents].
Already ruled out: [dead ends, so it doesn't re-derive them].
Return: answer + reasoning chain + confidence + what evidence would change it.
```

**mechanic**
```
Apply exactly: [diff, or precise before/after per file].
Files: [absolute paths].
Then run: [verification command] and report its full output.
Touch nothing else. If the edit doesn't apply cleanly, STOP and report —
do not improvise.
```

**repo-sync**
```
Repo: [absolute path].
Stage: [explicit file list — never `git add -A` unless stated].
Commit message: [conventional message, provided verbatim].
Pull first, push origin main after. Report the head commit hash.
Reminder: manifest gate — if the change touched a daemon/writer/DB site,
confirm system_manifest.json + DATA_FLOW.md are in the same commit or the
hook will reject; report the rejection rather than bypassing it.
```

## 3. Decomposing vague work

A vague task is a graph of bounded tasks the orchestrator hasn't drawn yet.
Standard shapes:

- **Bug-shaped** ("X is broken"): 1) `code-tracer` — reproduce/locate, return
  symptom + candidate sites; 2) `deep-reasoner` — root-cause from those sites;
  3) orchestrator decides the fix; 4) `mechanic` applies it; 5) verify;
  6) `repo-sync`.
- **Audit-shaped** ("is Y healthy/compliant"): enumerate the checklist YOURSELF
  first (or reuse /lab-audit, /lab-adversarial-review), then one `code-tracer`
  per check area, in parallel. Merge inline.
- **Build-shaped** ("add feature Z"): orchestrator writes the plan/issue with
  DoD criteria FIRST (SDLC gate), then each plan step becomes one mechanic- or
  tracer-sized dispatch. If a step won't compress to one bounded prompt, the
  plan step is too big — split the plan, not the prompt.
- **Research-shaped** ("what should we use for W"): 1-3 parallel `researcher`
  dispatches with disjoint questions, then orchestrator synthesizes. Disjoint
  matters: overlapping scopes = paying twice for the same reading.

Rule of thumb: if you can't state a dispatch's output contract in one sentence,
you haven't finished decomposing.

## 4. Parallelism

- Independent dispatches go in ONE message (they run concurrently). Serialize
  only when a later prompt needs an earlier result pasted in.
- Prefer 3 sharp parallel agents over 1 broad one — wall-clock and context both
  win. But don't shard below ~1 file of scope; spawn overhead dominates.
- Follow-up on returned work via **SendMessage to the same agent** (it keeps
  its context) instead of respawning with re-explained scope. Respawn only for
  genuinely new tasks.
- While agents run in the background, do orchestrator-tier work (plan the next
  phase, draft the issue text) — don't idle-poll.

## 5. Context hygiene (orchestrator side)

- Keep **conclusions, not transcripts**. After reading an agent's return, carry
  forward 1-3 sentences; never re-quote agent output wholesale into later
  prompts or user messages.
- Findings live in **repo docs, not chat**. If a result matters past this
  session, it goes in PLANS/BACKLOG/the issue/CODE_MAP (agents write it, per
  their output contract), and chat carries only the pointer.
- Cap every agent's return length in the prompt. Uncapped returns are how a
  cheap agent spends orchestrator-tier tokens on re-reading.
- Never read a file inline that an agent already summarized, "just to check" —
  if the summary is untrustworthy, fix the prompt contract, not the trust.

## 6. Anti-patterns (each has already cost real money or a real incident)

- ❌ Delegating to a general-purpose/catch-all agent — nests subagents blind
  (enforced by block-unlisted-subagents.py).
- ❌ "Investigate X and fix whatever you find" — unbounded scope + hidden
  decision authority in one prompt. Split: trace → decide → apply.
- ❌ Orchestrator running `git commit` — repo-sync only.
- ❌ Pasting file contents into a deep-reasoner prompt — pass paths; it has
  Read.
- ❌ Anything touching a paid-API surface without the Director's per-run
  consent — if a dispatch could invoke ingest/extract/enrich/vision code
  paths, say so in the ask and WAIT (hard rule).
- ❌ Ending a session with unsynced repos or skipping the closing ceremony to
  "save tokens" — the next session pays 300-800k tokens to re-derive.
