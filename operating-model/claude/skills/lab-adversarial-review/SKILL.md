---
name: lab-adversarial-review
description: >
  Targeted adversarial security review of the multi-repo lab, scoped by the
  lab's real trust model so it returns a ranked SHORT LIST (not a 100-finding
  flood). Invoke when the user types /lab-adversarial-review, asks for a
  security / adversarial / red-team review of a repo or change, or after a
  security-relevant build lands. Encodes the severity discrimination that
  separates the ~5 findings that matter from the noise. Free: gh CLI + on-plan
  leaf agents + local only — never paid API. Companion to /lab-audit
  (governance) — this one is security.
---

# lab-adversarial-review — targeted, trust-model-scoped security review

You are running an adversarial security review from the governance seat. The
goal is **not** to enumerate everything that could theoretically be hardened —
that produces a flood no one burns down. The goal is the **short ranked list
of findings that are real within the lab's actual trust model**, each with a
concrete kill chain and fix.

**The whole skill is severity discrimination.** Finding candidate issues is easy
and any model does it. The value is the filter below — apply it ruthlessly.

## 1. The trust model IS the severity filter (read first)

The lab is a **single-operator home lab**: one human (the Director), personal
data (records / financial / social archive), **VPN-only WAN ingress** (no
service is internet-facing), **no untrusted LAN users**, one admin account.

Two actor classes, and the lab has a STANDING decision on each:

- **T1 — defended.** Bug-class, SQL-path, DB-dump, cross-user/cross-owner data
  bleed, parser/injection from untrusted *input data*, and **unattended paid-API
  spend**. A finding is **in scope only if it is exploitable assuming the
  attacker does NOT already have host/shell access.**
- **T2 — risk-accepted (NOT defended), per Director decision.** Deliberate host
  compromise — an attacker with shell/root on the compute host. Encryption and
  RLS are one wall (the keys and the enforcer live on the same host); host
  compromise defeats both, and that is **accepted**. **Any finding whose kill
  chain requires host access is OUT OF SCOPE — do not report it.**

> The filter in one line: *"Does this work without assuming the attacker already
> owns the box?"* No → drop it. Yes → keep it and write the kill chain.

## 2. Standing exclusions — NEVER re-raise these (they are decided)

Re-surfacing a risk-accepted item as a "finding" is the noise that makes a
review worthless. These are closed by Director decision — do not report them,
ever:

| Excluded item | Authority |
|---|---|
| Encryption-at-rest off | risk-accepted |
| Laptop plaintext archives | risk-accepted, standing |
| Home VLAN WAN allowlist | struck / risk-accepted |
| Host-access trust domain (passwordless-admin interim) | risk-accepted |
| Cross-VLAN management-plane hardening | deferred |
| Database default auth (interim) | deferred as T2 defense |
| Temporary passwordless paths (interim) | interim, scheduled review |
| Wearable data plaintext-at-rest | scheduled follow-up |

Before reporting anything, check it against this list AND against the live
governance decision log — decisions may have been added since. If a candidate
is on the list, it is not a finding.

## 3. The attack surfaces that actually matter here (where to look)

Dispatch one leaf agent per surface (code-tracer for mapping, deep-reasoner for
the hard "is this exploitable in T1" calls). These are the surfaces where a T1
kill chain is plausible — spend effort here, not on generic hardening:

1. **Access control / authorization** — cross-user reads and writes (the T1
   high-value surface: cross-owner data bleed, a role that is enforcement-exempt,
   a gate that can be bypassed, a query path that disregards access control).
   This exposes sensitive data directly.
2. **Spend gates** — a bypass is real dollars. Can a scheduled job reach a paid
   surface without the arm token? Does a launch script fail the guard? Is there
   a paid call site not behind the gate? Is any agent step present in CI that
   should be blocked? A **disabled-but-loadable** paid-trigger daemon counts
   (footgun even if currently neutralized).
3. **Sensitive data at-rest completeness** — an encryption check: a column that
   should be encrypted but a write path still puts plaintext into it. Encryption
   existing ≠ every write path using it.
4. **Untrusted input ingestion** — documents, data exports, wearable syncs are
   attacker-influenceable *data* (T1): parser crashes, XXE/entity expansion,
   path traversal on extract, prompt-injection into classification paths.
5. **Auth / session** — portal auth, multi-factor flow, per-user session
   isolation, any role confusion.
6. **Secrets handling in code** — a script that echoes environment vars, a log
   line that prints a key, a world-readable secret file (perms), a credential
   in a git-tracked file. (The environment-var *trust domain* is excluded per
   §2; a key *leaking into a log or repo* is a live T1 finding.)
7. **Service run-as-user escalation** — any daemon running elevated beyond the
   known/tracked web-server. New elevated-run services are in scope.

## 4. Method

1. **Scope.** Confirm target (a repo, a diff, or the estate). Read the operating
   model documentation on money-gate + the target repo's system_manifest.json
   (authorization-required tables, connection sites) for the authoritative
   surface map.
2. **Fan out.** One leaf agent per §3 surface relevant to the target, in
   parallel. Each returns *candidate* findings with the concrete code path — no
   severity yet.
3. **Filter (the skill's core).** For each candidate, in order: (a) on the §2
   exclusion list or in the decision log as accepted? → drop. (b) kill chain
   requires host access (T2)? → drop. (c) survives → write the **T1 kill chain**
   explicitly (who, starting from what access, reaches what data/spend).
4. **Adversarially verify survivors.** For each, spawn an independent skeptic
   prompted to *refute* the kill chain ("assume no host access — show this does
   NOT work"). Kill anything that can't survive refutation. Prefer false
   negatives over noise: when unsure it's real, it's not a finding.
5. **Rank + cap.** Order by (data sensitivity × exploitability in T1). **Cap the
   report at ~10.** If more than 10 survive, that itself is the headline —
   report the top ones and say how many more of the same class exist.
6. **Report + file.** Output contract below. File confirmed CRITICAL/HIGH as
   issues in the owning repo (in-app) or governance (cross-boundary) with
   `type:security` + `sev:*` + structured criteria, per the SDLC. Close with the
   ceremony.

## 5. Output contract

A **ranked short list**, not an enumeration. Each finding, one block:

- **Surface + location** (`file:line`)
- **T1 kill chain** — concrete: starting access → steps → data/spend reached.
  If you can't write a host-access-free kill chain, it isn't a finding.
- **Severity** — CRITICAL (T1-exploitable sensitive data exposure, cross-user
  bleed, or unattended paid spend) / HIGH (T1 data-integrity or auth gap) /
  noted-only.
- **The fix** — specific and minimal.
- **Issue** — filed # or "inline-only."

**A clean pass is a valid, valuable result.** If nothing survives §3 filtering,
say exactly that — "N candidates examined, all either risk-accepted (§2) or
require host access (T2); 0 live T1 findings" — and stop. Do not manufacture
findings to look thorough.

## 6. Constraints

- **Free lane only.** `gh` + on-plan leaf agents (code-tracer / deep-reasoner)
  + local tools. **Never paid API** (P3). Local sensitive data inspection is
  fine.
- **Leaf agents only** — never general-purpose/multi-agent configurations (they
  nest and fail blind). Read-only until the Report/file step.
- **Read-only on the compute host** over `ssh labhost`; never read sensitive
  configuration contents (var names / file perms only).
- This is the **security** counterpart to `/lab-audit` (governance). Run it on
  a security-relevant change, or estate-wide at most quarterly — its value is
  precision, not frequency.
