# The SDLC Operating Model — issues as truth, machines as gates

The single playbook for every repo in the estate. Canonical home: the
`governance` repo; an identical copy lives in every repo.

**The short version:** GitHub Issues are the single source of truth for work
state; a plan IS an issue; success criteria are required before work starts;
machines gate by default and the human is a narrow exception-handler; paid API
is NEVER used for development.

---

## 0. The problem this exists to fix

A reconciliation once found five drifted backlog items across the estate —
including two security items pointing in *opposite* directions ("DONE &
PROVEN" in a local file vs OPEN on GitHub). Root cause: **two independently
hand-edited stores of the same truth** (a `BACKLOG.md` file and GitHub Issues)
and **work filed as un-checkable prose**. Separately and just as real:
**unattended paid-API spend** (~$50, twice).

Both are the same failure shape — *a thing that should be gated is only
guided*. This model gates them.

## 0.5 Authority matrix — who can trip each control (agent vs human)

Naming the human-exception set is only half the job; this names its dual, the
**agent-authority set** — without it, a control that's "human-gated" but
writable by an agent's tool surface is theater.

**A** = agent-autonomous (acts + logs). **P** = agent proposes / human
disposes. **H** = human-key-only (a physical human credential the agent's tool
surface cannot produce). **FORBIDDEN** = auto-reverted.

| Gated action | Auth | Mechanism / why |
|---|---|---|
| Create **in-app** issue (`status:draft` + criteria) | **A — the app's own dev session** | created within its repo; criteria *adequacy* is logged+monitored, not gated |
| Create **cross-boundary** issue | **A — governance repo only** | multi-repo / shared-infra / cross-cutting; app devs do not file cross-boundary |
| `backlog → ready` (Definition of Ready) | **A** if DoR passes | cardinality + structured-criteria check; fail → `needs-triage` |
| `ready → in-progress → in-review` | **A** | ordinary flow |
| Close → `status:done` | **A — only via the gate's signature** | the deterministic close-gate's evidence is the authority, not the actor |
| Direct label-stamp to `done` bypassing the gate | **FORBIDDEN** | transition-guard auto-reverts → `needs-triage` |
| `failed → backlog` (rework) | **A** | re-enters flow |
| `failed → wontfix` / drop | **P** | an agent must not bury a failure as wontfix |
| Trigger LLM review on the free lane | **A** | free; no paid spend |
| Any paid API call from a dev / CLI / agent session | **FORBIDDEN** | paid API is never for dev (P3) |
| Paid-API **production-pipeline** run | **H — server-initiated + per-run approval** | the only legitimate paid path |
| Per-run production consent / arm token | **H** | credential-gated; an agent's Bash tool cannot write or spoof it |
| Invoke break-glass close | **H** | human force-close with reason; rate-tracked |
| Shadow → enforce flip (per repo) | **H** | the Director's checkpoint call |
| Operating-model amendment / version bump | **P** | amendment = issue; human ratifies |
| Security-migration 100% audit | **P → H** | agent maps; human audits + signs |
| Tripwire fires → build next heavy component | **P** | agent surfaces evidence; human decides |

**The load-bearing rows are the `H`s and the FORBIDDENs.** Their validity
rests entirely on the human-key artifacts being *physically* outside the
agent's reach — a passkey / password-manager item / interactive-TTY value,
**never an agent-writable file**. If it's an `echo >`-able file, the gate is
theater.

**This operating model is itself under change-control:** amendments are
`type:plan` issues, one writer, version bumps human-ratified. The doc is
exempt from the one-writer rule *as policy, not a work-tracker* — its status
header is policy metadata, not a tracked status.

## 1. Governing principles (the spine — non-negotiable)

- **P1 — One writer.** Work state is *written* only as GitHub Issues. Every
  local artifact — `BACKLOG.md`, plan narratives, and the `CLAUDE.md`
  "current state" status text — is generated or banner-locked and
  machine-checked; never hand-edited as a tracker. One writer ⇒ nothing to
  drift against.
- **P2 — Machines gate by default; the human is an exception-handler.** Gates
  run automatically and proceed on success. The Director is pulled in only on
  a narrow, *named* exception set (§7), each as one bounded decision — never
  "review the whole thing first." A drift fix must not be paid for in
  throughput.
- **P3 — Paid API is NEVER used for development, and never initiated by a dev
  CLI.** Dev tooling, gates, CLI sessions, and agents use **only** the free
  lane (subscription harness models, local inference, CI's built-in token) or
  nothing. Paid API is permitted **only** in the production pipeline,
  server-initiated, with per-run human approval. There is no per-run dev
  exception. Enforcement is default-deny *before* the spend — a cap inside a
  component still spends up to the cap unattended; the refusal must precede
  the spend.
- **P4 — Build the minimum that kills the root cause; earn each heavier
  component with a measured tripwire.** Freeze the full design as the agreed
  destination so it is not re-debated; **sequence by evidence, not by
  completeness.**
- **P5 — Every unit of work has testable success criteria, machine-verified
  before closure; failures are first-class recorded events.** The LLM review
  layer is added assurance on top, never the floor.

## 2. The work model (issue lifecycle)

`status:draft → backlog → ready → in-progress → in-review → deployed-watch →
Closed(status:done)`, with **`status:failed`** as a first-class branch off
in-review/verify — never a silent bounce (a failure that disappears is how
"done but unbuilt" lies get made). **Exits are defined:** `failed → {backlog
(rework) · wontfix (P-authority) · escalated}`; a `failed` issue older than
14 days gets `aging-failed`. **`deployed-watch` exits to `done` on its
success-criteria tick or a defined watch window — never indefinitely.**

- **A plan IS an issue** (`type:plan`); `status:draft` is the earliest state.
  Draft exists *only* as an issue status — never as a draft file or folder.
- **Long-form design prose** may survive as a `PLANS/` doc carrying a
  `<!-- REFERENCE — status lives in issue #N, do not track here -->` banner
  and **zero** status tokens. A checker asserts no `✅`/`DONE`/`Status:`
  strings appear in a banner-locked doc.
- **Success criteria are required and structured:** a checklist of observable
  assertions (command + expected, route + status, query + count) — not free
  prose. No testable criteria ⇒ cannot leave draft, cannot close. For infra,
  the criteria *are* the smoke check ("curl route → 200", "daemon up",
  "row-level security denies cross-tenant reads") — which resolves the "infra
  has no unit tests" gap.
- **Continuous flow, not sprints.** Group by `area:` labels (durable themes);
  milestones only for hard external dates. WIP limit + aging alarm (>14 days
  → `aging`); cycle time tracked passively. Epics are `type:epic` issues with
  GitHub **native sub-issue links**, never prose reference lists — any effort
  spanning more than two issues gets one. Execution of any epic is governed
  by the §2.5 convergence contract.
- **Focus contract (anti-squirrel):** each repo carries **at most 1** open
  issue labeled `focus:current` — the machine-readable answer to "what is
  this repo's primary objective right now." Machine-enforced repo-wide: **≤1
  `focus:current` · ≤3 `status:in-progress` · no in-progress issue untouched
  >7 days.** Violations get `hygiene:wip-violation` + a self-clearing bot
  comment. Moving focus is deliberate: remove the label from the old focus
  first.
- **Intake ownership:** in-app issues are created by that application's own
  dev session, in its repo, the moment a plan/bug/finding is named — in
  `status:draft` with criteria, on-ledger from birth. **The governance repo
  files issues only for cross-boundary work** (multi-repo / shared-infra /
  cross-cutting governance). The repo-sync agent only ever acts on an
  **explicit issue number** in the commit/PR/prompt — never infers (wrong-
  issue-close risk → 0). `backlog → ready` is a human or DoR check, never
  agent self-promotion.

## 2.5 The epic convergence contract — anti-loop canon

**The failure this kills (the "loop"):** on a multi-session epic, each
session completes one part, *discovers* new work, files the discovery into
the epic, and exits with the item still in progress — a well-written deferral
comment reading as a successful session. The finish line recedes at exactly
the speed of work; the epic never converges. This is the default failure mode
of a capable agent left to judgment — partial delivery plus articulate
deferral is always the locally rational exit — so, per §0, it is **gated, not
guided**. From the moment an epic enters execution, judgment is replaced by
contract:

1. **FREEZE — scope closes when execution starts.** When an epic's first
   sub-issue leaves `ready`, the epic is frozen: the `scope:frozen` label
   goes on, and the epic body gains a **finish-line checklist** — every
   remaining item with a *binary* done-check (command+expected /
   route+status / query+count) — plus a machine-readable manifest of the
   frozen sub-issue set (`<!-- frozen-sub-issues: N,N,N -->`). **Nothing is
   ever added to a frozen epic** — no new sub-issues, no new phases, no
   "Phase 1b" spawned mid-flight. A discovery that "belongs" in the epic is
   evidence the epic was underspecified when frozen; it goes to the parking
   lot (rule 3) and waits its turn *after* close.
2. **BINARY EXIT — one item per session; two ways out.** A session working a
   frozen-epic item takes ONE checklist item and ends in exactly one of two
   states: **DONE** (evidence posted per the close-gate) or **`status:failed`**
   (+ why). *"Partially built, follow-up filed" is a FORBIDDEN session exit* —
   partial work is recorded as a failure, never converted into new issues or
   phases. Failing is fine; growing is not. Each frozen item should carry a
   self-contained session prompt in the epic body so a cold session executes
   the contract without exercising scope judgment.
3. **PARKING LOT — discovery is never scope.** Everything found mid-session —
   bugs, gaps, ideas — lands as **one line** on the epic's single parking-lot
   issue (`type:chore`, titled "Parking lot — epic #N", outside the native
   sub-issue set), or as an ordinary `status:draft` issue **not** linked to
   the epic. Parking-lot triage happens **after** the epic closes, never
   during.
4. **DESCOPE is the sanctioned lever.** If an item cannot reach a binary exit
   within a session, the sanctioned move is to *shrink it* — split the
   unfinishable remainder to the parking lot as post-epic work, with the
   Director's one-line approval — never to extend the epic, respawn the item
   as a new phase, or leave it half-open. The question a stuck session asks
   is "what smaller thing closes?", not "what new thing do I file?"
5. **TERMINAL EVENT, not readiness.** Every frozen epic names its terminal
   event in the checklist header — a specific rebuild, deploy, or date. The
   epic **closes AT that event with whatever is DONE**; unfinished frozen
   items exit as `status:failed` or move to the parking lot at close (never
   silently). "When everything's ready" is not a terminal condition — it *is*
   the loop.

**Enforcement:** a Stop hook (`epic-scope-freeze`) compares each open
`scope:frozen` epic's live sub-issue set against its frozen manifest at
session stop and **blocks the stop** on any addition (the loop's signature
move). A CI-side twin applies `hygiene:scope-violation` on divergence.
Binary-exit and parking-lot discipline are canon-floor (session-verifiable)
until machine-checked.

## 3. The single label scheme

Six axes + flags, identical structure in every repo:

- `type:` bug · feature · chore · docs · security · spike · **plan** · **epic**
- `status:` **draft** · backlog · ready · in-progress · in-review ·
  deployed-watch · done, **+ failed** branch
- `P0–P3` priority
- `sev:` (security severity)
- `area:` (repo-scoped durable themes)
- **flags:** failed-change · needs-triage · needs-human · aging · blocked ·
  `gate:mirror-stale` · `gate:break-glass` · `gate:close-pass` (gate PASS
  signature, authorizes done) · `focus:current` (≤1 per repo) ·
  `hygiene:wip-violation` (auto-managed) · `scope:frozen` (epic execution
  freeze) · `hygiene:scope-violation` (auto-managed)

Provisioned by an idempotent scripted `gh label` run; CI asserts the set
exists; label-hygiene enforces cardinality (exactly one `type:`/`status:`/`P*`
per issue).

## 4. The gate stack — tiered by cost and evidence

### Tier 0 — BUILD NOW. Free, deterministic, kills the root cause.

Everything here is CI on the built-in token (free) or local checks — **no
paid API, no LLM in the gating path:**

1. **One-writer mirror** — a regenerator writes `BACKLOG.md` from issues; a
   CI verifier diffs; local hooks checksum. Banner: `GENERATED — DO NOT EDIT`.
2. **Generator-death freshness alarm** — scheduled diff; the mirror banner
   carries `generated_at` + source event SHA; a stale/dead generator raises
   `gate:mirror-stale` at P1. Closes the "stale-but-trusted" hole.
3. **Label-hygiene + Definition-of-Ready** — cardinality + structured-criteria
   testability check; violations auto-`needs-triage`. A second **repo-wide**
   job enforces the focus contract (≤1 focus, ≤3 in-progress, no stale WIP)
   on label events + a daily schedule. Templates structure intake but are not
   counted as enforcement.
4. **Required CI test-floor on every PR/push:** the repo test suite is a
   required check; **red tests block merge, no LLM in the loop.** Definition
   of Done = "tests exist + green in CI + meet the issue's success criteria."
   This is the floor the close-gate later *verifies held*, rather than
   hunting for tests at close time.
5. **Deterministic close-gate** on `deployed-watch → done`: before close, an
   automated check runs the issue's success criteria — tests green in CI,
   **the revert-check** (revert the fix in a throwaway checkout; assert ≥1
   referenced test/smoke goes red; green-after-revert ⇒ FAIL — un-gameable,
   no LLM), and for infra the smoke/health checks run in-session over SSH.
   Then the human or the implementing session ticks each criterion in a
   comment. **This is the machine check that "looks done" lacked.**
   **Duplicate-closure gate:** closing an issue as duplicate/superseded is
   **not** verification of the survivor. The close must (a) name the survivor
   explicitly, (b) move any unique detail onto the survivor verbatim, and
   (c) carry an explicit unverified-survivor caveat when the survivor's own
   work is unbuilt — a dedup must never launder an open risk into "handled."
6. **`status:failed` + ledger event** for any failed criteria / failed
   revert-check / regression — visible on the board, counted in reporting.
7. **Self-testing reconciler** — the drift detector ships a seeded-drift
   self-test in the same CI run; "zero drift" is trusted only if the
   self-test caught its seed. Migrations from prose to issues are checked as
   a bijection (`=`, not `≥`), with 100% human audit of `type:security`.
8. **Demote/generate the `CLAUDE.md` "current state"** — status claims are
   generated from issues (or removed); durable architecture/gotchas are kept
   under a "nothing here asserts done/open" banner. Generalizes P1 to the
   highest-traffic prose store.
9. **Security reads bypass the mirror** — for `type:security`, agents query
   the issue tracker live; the mirror flags those rows `⚠ live-check required`.

### Tier 1 — EARN IT. Heavy / fragile — built only when a tripwire fires.

Freeze these as the agreed destination; do **not** pre-build them. Each is
gated on measured evidence (P4):

| Component | Build it only when (tripwire) | Extra constraint |
|---|---|---|
| **LLM adversarial-review layer** | the deterministic gate demonstrably misses ≥N bad closes the LLM would have caught, over a real window — *measured* | runs on the **free harness lane only**; paid API forbidden. Until automated, it is **human-invoked** for `type:security` P0/P1 |
| **Quality ledger + weekly report** | close volume makes per-issue verdict comments unscannable by one human | bot-only, single-writer append; add false-negative sampling when the LLM layer exists |
| **Cross-repo project board** | a second human joins the estate | per-repo views suffice until then |
| **RCA pipeline** | the ledger shows a real recurring-failure pattern worth clustering | — |

**Precedent discipline:** every gate must earn its keep by catching a real
bug first, then roll out.

## 5. What lane reviews run in

The close-gate is **dev tooling**, so by P3 paid API is categorically
forbidden for it — there is no paid lane to weigh.

- **Free harness lane (target):** the reviewer is a subagent on the
  subscription harness — free because it's the subscription, not metered API.
- **Deterministic-only + human-invoked LLM (interim, ships now):** the
  automatic gate is the free deterministic set (tests, smoke, criteria
  checklist, revert-check); an **adversarial security review skill is
  human-invoked and REQUIRED before closing any `type:security` P0/P1**, its
  ranked short-list (or explicit clean pass) posted as close evidence.
  Scope discrimination: this gates *security* P0/P1 only — a non-security P0
  uses the deterministic gate; a security review there would manufacture
  noise. No wrapper agent runs it — the orchestrator session invokes it and
  fans out leaf agents (a wrapper would carry the Agent tool and violate the
  leaf-safe delegation canon).
- **Paid lane: FORBIDDEN.** Not a fallback. If the free-lane bridge is never
  built, the gate stays deterministic + human-invoked forever; it never
  becomes paid.

The close-gate is **advisory-but-binding-on-the-bot**: a FAIL blocks
auto-close (human can override → logged break-glass); a PASS on
`type:security` is posted to the Director as FYI so a bad PASS is visible
within a day. **The load-bearing parts are the non-LLM ones** (revert-check +
human sign-off on security P0/P1); the LLM verdict is polish, not the gate.

**Where the gate is not yet enforcing** (shadow-mode repos, CI outages): the
gate's signature is the **posted evidence itself** — the success-criteria
checklist run, with command + result recorded in a close comment — not a
green CI check. Manual ≠ optional: no evidence, no close.

## 6. The money gate (independent of the work-gate; ships first)

Paid API is **production-pipeline-only** — server-initiated, human-armed,
per-run approved — and never reachable from a dev/CLI/agent session (P3).
Born of ~$50 of unattended spend, twice:

- **MG-1 — harness deny (dev/CLI/agents):** a `PreToolUse` hook that
  **DENIES** any in-session command referencing the paid API key, the paid
  API host, or a known paid launch script. **No consent override in dev** —
  paid is never for dev, so there is nothing to approve; it just refuses.
- **MG-2 — production arm token (the only paid path):** each paid launch
  script checks a short-TTL **arm token that an actual human set** (authority
  `H` — e.g. a file only a human writes after a credential ceremony) as its
  first act and refuses ($0) otherwise. Scheduled paid triggers ship
  disabled by default.
- **MG-env — the *actual* recurring leak:** a CLI silently falling back from
  an exhausted subscription to metered API billing when the API key sits in
  the process environment — an env/auth property no behavioral rule catches.
  **Primary control:** force subscription-only login in managed settings
  (verified, not assumed — it's the only control that survives
  non-interactive invocation). **Defense-in-depth:** strip API-key variables
  before exec on every box; never source a secrets file in a shell you then
  start the agent CLI in.
- **MG-3 — cap + ledger (backstop):** every paid call site shares one
  rolling-daily hard cap — a pre-call check refuses ($0) when today's spend +
  estimate exceeds the cap; actual usage is appended to an append-only
  ledger. The always-on production surfaces get their only dollar bound here.
- **MG-4 — no CI-launched coding agent, ever:** no workflow/step that
  launches the agent CLI itself in CI, and no self-hosted runner registered
  to run it. A CI-launched agent authenticates with OAuth *and* an API token
  and runs **unbounded** — outside every cap above; it is the worst paid
  vector because there is no ceiling. Plain deterministic CI on the built-in
  token stays fine — the ban is specifically on running the *agent itself*
  in CI. Standing verification: grep all workflows for the agent action = 0
  hits; registered runners = 0, checked at audit points.

## 7. The named human-exception set (the ONLY paths to the Director)

Per P2, routine work self-serves; the Director sees only:

1. **Per-run paid-API consent** (P3)
2. An **architecture-changing preflight failure**
3. The **100% security migration audit**
4. A **needs-human close-gate verdict** on security P0/P1
5. A **fired tripwire** — the decision to build the next heavier component
6. **Break-glass**

Each arrives as one bounded decision with evidence attached — never a review
queue.

## 8. Safety refinements

- **Measure the dangerous direction.** Shadow-mode measures false-*positives*
  (noise); the dangerous failure is a false-*negative* — a bad PASS
  auto-closing broken security work with an automated signature.
  Sample-audit PASS verdicts (**100% for `type:security`**) with an
  independent reviewer; track the false-negative rate next to the
  false-positive rate.
- **Logged break-glass.** When the gate is down or wrong on urgent work: a
  `gate:break-glass` close path with a mandatory reason + ledger event, which
  **auto-opens a follow-up `type:chore`** to run the skipped verification.
  The bypass itself becomes a first-class audited event, **rate-tracked**
  with a tripwire (>X/week → human review of *why* the gate keeps being
  wrong) — the canary that the gate is being routed around.

## 9. Rollout phasing (the shape, reusable)

1. **Phase 0 — stop the bleeding, no work-gate yet:** fix known drift by
   hand; freeze writes to the drifted files so they can't re-drift before the
   gate lands. **Ship the money gate first** — it depends on nothing else.
2. **Phase A — one repo, end-to-end:** run a preflight (account type, project
   scopes, sub-issue availability, token scopes, label inventory); build all
   of Tier 0 including the deterministic close-gate; **dogfood by opening the
   operating model itself as the first `type:plan` issue** with its own
   acceptance criteria (§11) as the success criteria.
3. **Phase B — shadow into the product repos** while sessions are live:
   gates run report-only; flip to **enforce per-repo at each repo's own
   checkpoint, the Director's call** — no global flag day.
4. **Tier 1 components:** built only when their tripwire fires.
5. **Phase E — wire the agent instructions:** root + per-repo `CLAUDE.md`
   updated (issues = source of truth, mirrors generated, current-state
   demoted); repo-sync extended to issue state, bounded by "explicit issue
   number only."

## 10. The proportionality decision (record it; don't re-debate)

The fork: build the full gate system shadow-first, or ship an MVP and earn
each heavy component by tripwire. This model picks the latter — **but be
precise about what gets deferred.** The deferral applies **only to the LLM
review layer**, never to the deterministic close-gate: the founding failure
was a missing *machine check*, not a missing *LLM opinion*. The revert-check,
test-floor, and smoke checks (free, deterministic, the actual root-cause
antidote) ship in Tier 0 on day one. For a one-human estate whose values are
*don't stall* and *don't leak money*, the minimum that kills the root cause
beats the maximum that's correct in the abstract.

## 11. Acceptance criteria (testable — and this doc's own success criteria when dogfooded)

1. Hand-editing a generated `BACKLOG.md`, or putting a status string in a
   banner-locked plans doc or `CLAUDE.md` current-state, is **rejected** by a
   checker.
2. An issue with no structured testable success criteria **cannot** leave
   `status:draft` or close.
3. A PR with red tests **cannot** merge; a close requires tests green + the
   revert-check red-on-revert + the success-criteria checklist ticked.
4. A failed change is visible as `status:failed` + a ledger event, never a
   silent bounce.
5. A fresh reconciliation reports **zero** drift across all repos **and** the
   detector's seeded-drift self-test passed in the same run.
6. Every former prose work item exists as a structured issue; migration is a
   bijection with 100% of `type:security` human-audited.
7. Any paid-API command from a dev/CLI/agent session is **denied outright**;
   a scheduled production paid job without a human-set arm token spends
   **$0**; a fresh CLI with the subscription exhausted **stops** rather than
   billing. The unattended-spend scenario becomes structurally impossible.
8. Every gate proceeds automatically on success; the only paths to the human
   are the §7 named exceptions.
9. The deterministic close-gate ships first; the LLM review layer is not
   built until its tripwire fires — and when built it runs on the free lane
   or human-invoked, never paid API.
10. `type:security` closes carry a posted verdict/evidence record; PASS
    verdicts are sample-audited (100% for security) with the false-negative
    rate tracked.
11. No infinite CI loop occurs on regenerator commits (`[skip ci]` + path
    filter, verified).
12. A second `focus:current`, a fourth `status:in-progress`, or an 8-day
    stale in-progress issue trips the repo-wide hygiene check; a duplicate
    close without a named survivor + moved detail is treated as a bypass.
13. Adding a sub-issue to a `scope:frozen` epic blocks the session stop (Stop
    hook) and trips `hygiene:scope-violation` in CI; a frozen epic with no
    terminal event, or a frozen-epic session exiting neither DONE-with-
    evidence nor `status:failed`, is a §2.5 violation.

## 12. Change control

Amendments to this model are `type:plan` issues in the governance repo; one
writer; the human ratifies; version bump recorded in the decisions log. Where
this doc is silent, the referenced source docs stand.
