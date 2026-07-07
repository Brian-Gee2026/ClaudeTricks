# An Operating Model for Running Software Development with AI Agents

This is a complete, working operating model for running a multi-repo software
estate where **AI agents (Claude Code) do the execution** and **one human acts
as Director** — designing, reviewing, and approving, but not typing the code.

It is sanitized from a real, live environment: a single operator running five
repos (three personal-data applications, a platform repo, and a governance
repo) on a small home server, with every rule below born from an actual
failure that rule now prevents. Names, hosts, and domains have been
genericized (`app-records`, `labhost`, `<gh-owner>`, `192.0.2.x`); the
mechanics are exactly what runs in production.

## The one-paragraph version

**GitHub Issues are the single source of truth for work state. Every unit of
work has testable success criteria before it starts and machine-verified
evidence before it closes. Machines gate by default; the human is a narrow
exception-handler, not a review queue. Paid API is never used for development.
Agents are tiered by cost and delegated to by role. Every session ends with
durable artifacts — enforced by hooks, not habits.**

The recurring design principle: **"a thing that should be gated is only
guided" is a bug.** Anywhere the model says an agent *should* do something, a
deterministic check exists (or is planned) that *makes* it happen. Habits
drift; gates don't.

## What's in here

| Path | What it is |
|---|---|
| [`docs/OPERATING_MODEL.md`](docs/OPERATING_MODEL.md) | The SDLC: issue lifecycle, authority matrix (agent vs human), label scheme, the tiered gate stack, the epic convergence (anti-loop) contract, the money gate |
| [`docs/CHARTER_TEMPLATE.md`](docs/CHARTER_TEMPLATE.md) | Architecture-invariants charter: the durable rules every repo must conform to, plus the change-control process for the charter itself |
| [`docs/THREE_LAYER_MODEL.md`](docs/THREE_LAYER_MODEL.md) | How strategy / governance / execution split across tools, and how a laptop session drives a remote server over SSH |
| [`docs/DELEGATION_POLICY.md`](docs/DELEGATION_POLICY.md) | Model tiering: which agent (and which model tier) gets which work, and why subagents must be "leaf-safe" |
| [`docs/CODE_MAP_CONVENTION.md`](docs/CODE_MAP_CONVENTION.md) | A per-repo orientation doc that lets a fresh session skip the repo-wide exploratory sweep |
| [`docs/REGISTRY_PATTERNS.md`](docs/REGISTRY_PATTERNS.md) | The shared-infrastructure inventory and capability registry patterns ("check before you build") |
| [`claude/CLAUDE.md`](claude/CLAUDE.md) | The user-level Claude Code instructions file that binds it all at session level |
| [`claude/agents/`](claude/agents/) | The leaf-safe subagent definitions (tracer, researcher, reasoner, mechanic, repo-sync, plus three review analyzers) |
| [`claude/hooks/`](claude/hooks/) | The enforcement hooks: paid-API deny, subagent allowlist, doc-drift check, closing ceremony, epic scope-freeze, session-work markers |
| [`claude/skills/`](claude/skills/) | Skills: governance audit, adversarial security review, code-map refresh |
| [`scripts/`](scripts/) | The deterministic SDLC gate scripts: issue hygiene, repo hygiene (WIP/focus), status-transition guard, close gate with revert-check, doc-sync manifest check |
| [`tools/leak_check.sh`](tools/leak_check.sh) | This kit's own gate: a grep-based check that no private identifier ever lands in this public tree |

## How to adopt it

1. **Read `docs/OPERATING_MODEL.md` first.** Everything else hangs off it.
2. **Start with the two rules that pay immediately:** issues-as-single-writer
   (stop hand-editing backlog files) and testable-success-criteria-before-work.
   They need no tooling, only discipline — then add the gates so discipline
   stops being required.
3. **Add the money gate before any other automation** if you use paid API
   anywhere. The deny-hook (`claude/hooks/block-paid-api.sh`) plus a
   subscription-only login setting kills the "agent silently bills the API"
   failure class.
4. **Adopt the gate scripts per repo** (`scripts/`), shadow-mode first:
   report-only until they prove themselves, then enforce. Every gate here
   earned its place by catching a real failure first.
5. **Install the hooks** (`claude/hooks/`) in `~/.claude/hooks/` and wire them
   in `settings.json` (PreToolUse for the deny-hooks, Stop for the ceremony
   and scope-freeze, SessionStart for marker resets).
6. **Tune the delegation policy** (`docs/DELEGATION_POLICY.md`) to whatever
   model tiers you have. The shape matters more than the models: an expensive
   orchestrator that plans, cheap leaf agents that execute, and **no agent
   that can recursively spawn agents.**

## The failures this model exists to prevent (all real)

- Work marked "DONE & PROVEN" locally that was never built — caught by a
  human's eyes, not a gate. → the **deterministic close-gate** (tests green +
  revert-check + evidence comment; direct-stamping `done` is auto-reverted).
- Two hand-edited copies of the same backlog drifting in opposite directions.
  → **one writer**: issues are truth; every local mirror is generated and
  banner-locked.
- ~$50 of unattended paid-API spend, twice. → the **money gate**: default-deny
  hook, per-run human arming, shared spend cap with a ledger.
- A capable agent on a long effort discovering new work faster than it closes
  old work, forever. → the **epic convergence contract**: scope freezes when
  execution starts; discoveries go to a parking lot; every session exits
  binary (done-with-evidence or failed).
- Session endings that skip the write-up, taxing the next session hundreds of
  thousands of tokens of re-derivation. → the **closing ceremony**, enforced
  by a Stop hook.

## License

Same license as the parent repository. Use freely; attribution appreciated.
