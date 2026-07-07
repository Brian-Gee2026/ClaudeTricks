# Lab Charter — architecture-invariants template

**Owner:** the Director (`<gh-owner>` on GitHub)
**Source of truth:** this file. Everything in here is invariant unless changed
via the charter-change process in §9.

> This is a sanitized template of a real charter. The specific services,
> hostnames, and databases are placeholders — the *structure* is the point:
> a short, versioned document that captures only the invariants every repo
> must conform to, with an explicit change process. If a proposal contradicts
> the charter, either the proposal changes or the charter changes — but never
> silently.

---

## 1. What this is

The lab is a small estate: one server (`labhost`) running a handful of
personal-data applications plus the infrastructure that supports them. This
charter captures the **architecture invariants** that every team (repo) MUST
conform to.

The lab is operated by a **Technical Director** (a human) who delegates
execution to **AI agent sessions** (Claude Code, over `ssh labhost`). **The
Director does not write code or run commands directly.** They design, review,
and approve.

## 2. Hardware budget

- One small server — e.g. 16 GB unified RAM, 256 GB SSD.
- Intentionally constrained: architecture decisions assume **RAM is the
  scarce resource**.
- The GPU is reserved for **local LLM inference** (Ollama). No other service
  may use it.
- **Backup:** a nightly clone to a NAS, preceded by a preflight script that
  dumps every database (`pg_dumpall --globals-only` + per-DB `pg_dump -Fc`)
  into a diagnostics directory the clone then carries off-box. A backup
  story is required for every service (§8).

## 3. The repos (the "Standard Model")

Exactly N repos — one per team, plus governance. Example shape:

| Repo | Team | Scope |
|---|---|---|
| `platform` | Server engineering | Provisioning, reverse-proxy config, install scripts, server-wide inventories (`PLATFORM.md`) |
| `app-records` | App team 1 | A personal-records app: Postgres-backed RAG, web UI, local-LLM enrichment pipeline |
| `app-finance` | App team 2 | A portfolio tracker: CSV import, price refresh, dashboard |
| `app-archive` | App team 3 | A personal-archive app: Postgres-backed search + browse |
| `governance` | The Director + orchestrator sessions | This charter, the SDLC operating model, the decisions log, audit history |

**Every repo is a peer.** The governance repo is not a daemon, an automation
hub, or a dispatcher — it is governance-of-record plus the home for
cross-cutting issues.

## 4. Operating model

**The operating model of record is `docs/OPERATING_MODEL.md`.** Its
essentials, restated as invariants:

- **GitHub Issues are the single source of truth** for work state. A plan IS
  an issue. Per-repo `BACKLOG.md` files are generated, banner-locked mirrors.
- **Machines gate by default; the Director is a narrow exception-handler.**
- **Paid API is NEVER used for development.** Sessions, gates, and agents use
  only the free lane. Paid API is production-pipeline-only, server-initiated,
  per-run approved.
- **Per-repo gates, no central automation hub.** Each repo carries its own
  close-gate, CI, and manifest anti-drift check.

**Retired patterns (do not reintroduce):** long-running orchestrator daemons,
proposal-inbox polling, agent-dispatching bridges, and any CI workflow that
launches the coding agent itself (see the operating model's money gate, MG-4).

## 5. Versioning + naming

- **SemVer** per repo; no synchronized release train. Odd MINOR = alpha, even
  MINOR = stable. Tag the commit you'd be willing to deploy.
- **Conventional commits** (`feat(scope): …`, `fix: …`, `docs: …`, `chore: …`).
- **Repo names** are lowercase-kebab, identical across the laptop folder, the
  server path, and the GitHub remote.
- **Service daemons** use one reverse-DNS prefix (`com.example.lab.<service>`)
  so a compliance script can enumerate them.
- **Databases and DB roles** are all-lowercase; one Postgres instance, one DB
  per app, each with its own owner and least-privilege app roles.

## 6. Deployment model

The server is a server; the OS is the platform. Services run **native**
wherever practical (containers were decommissioned here: on a RAM-constrained
box, N containerized databases cost gigabytes where one native instance costs
megabytes — and a macOS Docker VM denies the GPU to local inference).

| Rule | Why |
|---|---|
| One native Postgres instance, one DB per app | RAM |
| Local LLM server native, never containerized | GPU access |
| One reverse proxy (Caddy) is the front door; per-service ports bind loopback | one auth/TLS surface |
| Every service is a supervised daemon (launchd/systemd) generated from a template by each repo's install script | restart story |
| **No service runs as root** | compliance-checked (see `scripts/charter_compliance_check.sh`) |
| No service is directly internet-facing; remote access via VPN only | attack surface |

## 7. Data + filesystem layout

One canonical tree on the server, owned by the service account (`svcadmin`):

| Path | Contents |
|---|---|
| `~/lab/repos/<repo>/` | Execution copies of the repos (GitHub is authoritative) |
| `~/lab/data/<app>/` | Read-only source data (exports, CSVs, documents). NOT in git |
| `~/lab/cache/<app>/` | Regenerable derived data. Deleting a cache dir must always be safe |
| `~/lab/secrets/.env` | All credentials, mode 0600. NEVER read or print contents; reference env-var names only. NOT in git |
| `~/lab/logs/agents/<team>/` | Per-team agent session logs. Rotated |
| `~/lab/diagnostics/` | Timestamped recon output, DB dumps. Pruned periodically |

Connection strings live in the secrets file as env vars (`RECORDS_DSN`,
`FINANCE_DSN`, …). Code reads them via the environment. **Never hardcode
credentials; a connection helper MUST NOT silently default to the production
database when unconfigured.**

## 8. Cross-cutting infrastructure rules (the invariants)

1. **`platform` owns shared infra.** Other repos do not carry "how to install
   Postgres" instructions — they reference platform.
2. **`governance` owns governance.** No team writes there directly.
3. **No duplicate concerns across team repos.** Each team owns its code in
   its own repo.
4. **The reverse-proxy config is canonical in one place.** No duplicates.
5. **Every service has a backup story.**
6. **Every service has a restart story** (daemon template + install script).
7. **No service runs as root.**
8. **Work is tracked as GitHub Issues** with testable success criteria; the
   SDLC close-gate — not a human stamp — authorizes `done`.
9. **New resources (DB, port, daemon, directory) are recorded in the live
   inventory** (`platform/PLATFORM.md`) and the owning repo's
   `docs/system_manifest.json`; an anti-drift gate enforces it in the same
   commit as the change.
10. **Production data is modified only by production-pipeline scripts;
    testing runs on synthetic data.**
    - (a) Writes to production data go through the sanctioned pipeline —
      no hand-run SQL, no one-off `*_fix.py`. A data error is corrected by
      fixing the pipeline job and re-running it, never by patching data.
    - (b) Data-touching tests run on a synthetic-flagged substrate, an
      ephemeral database, or a rolled-back transaction — never the production
      DSN. Until an app provides an isolated target, its data-touching tests
      are *blocked*, not "carefully run on live."
    - (c) Connection helpers fail loud (no silent production default).
    - (d) No consent is granted on self-asserted safety — "safe" in a code
      comment is not evidence; the isolation or restore path is verified
      independently before any run.

## 9. How to change the charter

1. **Raise a `type:plan` / governance issue** in the governance repo
   describing the change + rationale.
2. **The Director approves** — their explicit "go" is the authority.
3. **Update the charter in-place** with a version bump at the top + an entry
   in the decisions log (and an audit-log line).

Never update casually, and never from inside a per-team session without
Director sign-off.

---

**This charter supersedes anything in per-team `CLAUDE.md` files that
conflicts with it. If you find a contradiction, the charter wins, and the
contradicting file gets a fix proposal.**
