# CODE_MAP convention — per-repo durable orientation layer

## What it is

One `docs/CODE_MAP.md` per repo, sitting between the data-flow doc and the
code (~200–400 lines). It exists so a new session can **orient without
dispatching a repo-wide exploratory sweep** — the repeated token spend this
convention eliminates. It carries slow-drifting, mid-altitude facts only;
detail is what drifts, so detail stays out.

## The operating rule (non-negotiable)

Sessions read `CODE_MAP.md` to **orient** — then dispatch a tracer agent only
for task-specific leaf detail, verified against current code. The map is a
starting index, **never an authority for line-level claims**. Line numbers,
exact SQL, and current values are always re-verified live.

## Required sections (the template)

Header first — the honesty mechanism:

```markdown
# CODE_MAP — <repo>
generated-at: <commit sha> · <YYYY-MM-DD>
```

Any session can run `git log --oneline <sha>..HEAD -- <paths>` and know
exactly how stale the map is and what changed since. The map never has to be
perfectly current to be safe — it has to be **honest about its age**.

| Section | Carries |
|---|---|
| **Module inventory** | Each top-level module/package: one sentence on what it does and its role. Dead/legacy dirs marked as such. |
| **Entry points** | Every daemon, service, script, CLI: what invokes it, what it drives. **Paid-API surfaces flagged inline** (e.g. `ingest.py → llm_extract → paid model ⚠️ PAID`); if a repo has none, say so explicitly — that's a load-bearing fact. |
| **Load-bearing call paths** | The 5–10 flows a session actually needs (ingest, auth, access-control establishment, render, sync) as short arrow chains with `file:symbol` anchors. |
| **Key schemas/contracts** | Tables, roles, ports, env-var **names** (never values). Pointers into `DATA_FLOW.md`/`system_manifest.json` where those already carry the fact — one truth per fact. |
| **Gotchas** | Dead code, retired patterns, misleading names, known traps. Where docs and code disagree, the code wins and the discrepancy is listed here. |

## Regeneration

- Refresh is a **bounded tracer-agent task** (mid-tier model — zero paid
  API). Full regeneration is one dispatched run per repo; small deltas can be
  patched by hand in the same commit as the code change.
- **Closing-ceremony hook:** if a session materially changed a repo's code,
  refresh (or minimally patch) that repo's CODE_MAP — and bump
  `generated-at` — in the same checkpoint, **before** dispatching repo-sync.
  Same commit-coupling logic as the doc-sync gate, at lower resolution.
- Every claim in a regenerated map must come from code the tracer actually
  read, not from other docs. Docs-vs-code disagreements land in Gotchas.

## Optional hardening

The manifest checker (`scripts/check_system_manifest.py`) gains a cheap
**advisory** check: warn when `generated-at` is more than N commits behind
HEAD for mapped paths. Advisory, not blocking — a stale-but-stamped map is
honest; a blocking gate would recreate the skippable-habit problem in
reverse.
