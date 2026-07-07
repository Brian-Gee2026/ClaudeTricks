#!/usr/bin/env python3
"""check_system_manifest.py — anti-drift gate for the governance repo's
docs/DATA_FLOW.md + docs/system_manifest.json (doc-sync canon, ~/.claude/CLAUDE.md).

Static, repo-only checks (safe in pre-commit / CI / a Claude hook — NO DB, NO ssh):
  1. connection-site inventory — every file in THIS repo that opens a DB
     connection must be listed in the manifest. The governance repo is a
     governance repo, so the expected inventory is empty; any new connection
     site is drift and fails the gate.
  2. launch-script roles — any scripts/launch_*.sh must export the DSN role
     the manifest declares. None are expected in this repo (the pattern is
     inherited from the app-records reference implementation).
  3. forbidden patterns (ratchet) — manifest-declared patterns are allowed
     ONLY in grandfathered files listed in the manifest; any NEW occurrence
     fails.
  4. CODE_MAP freshness (WARN-only) — advises when docs/CODE_MAP.md's
     generated-at stamp lags material code commits (see your governance issue tracker).

Adapted from the app-records reference checker; driven by
docs/system_manifest.json (real manifest tracked in (see your governance issue tracker)).

Usage:
  python scripts/check_system_manifest.py            # check; exit 1 on drift
  python scripts/check_system_manifest.py --init      # refresh discovered lists
                                                       # (intentional baseline bump)
Manifest: docs/system_manifest.json
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys

REPO = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
MANIFEST = os.path.join(REPO, "docs", "system_manifest.json")

SKIP_DIRS = {".git", "venv", ".venv", "__pycache__", "node_modules",
             ".mypy_cache", ".pytest_cache", "chroma_db", "None"}

# A file "connects" if it calls psycopg2.connect(...) or get_conn(...).
CONNECTION_RE = re.compile(r"psycopg2\.connect\(|get_conn\(")
# Launch-script role: export APP_DSN="... user=<role>"
LAUNCH_ROLE_RE = re.compile(r"export\s+APP_DSN=.*user=([A-Za-z0-9_]+)")


def _read(path: str) -> str:
    try:
        with open(os.path.join(REPO, path), "r", errors="ignore") as fh:
            return fh.read()
    except OSError:
        return ""


def _walk(exts: tuple[str, ...]):
    for root, dirs, files in os.walk(REPO):
        dirs[:] = [d for d in dirs if d not in SKIP_DIRS]
        for f in files:
            if f.endswith(exts):
                yield os.path.relpath(os.path.join(root, f), REPO)


def discover_connection_files() -> list[str]:
    return sorted(p for p in _walk((".py",)) if CONNECTION_RE.search(_read(p)))


def discover_launch_roles() -> dict[str, str]:
    out = {}
    for p in _walk((".sh",)):
        if "/launch_" not in p and not os.path.basename(p).startswith("launch_"):
            continue
        m = LAUNCH_ROLE_RE.search(_read(p))
        if m:
            out[p] = m.group(1)
    return out


def load_manifest() -> dict:
    with open(MANIFEST) as fh:
        return json.load(fh)


# CODE_MAP freshness (Phase-B advisory — see your governance issue tracker). WARN-only by design:
# a stale map misleads sessions but must never block a commit or fail CI.
CODE_MAP = os.path.join(REPO, "docs", "CODE_MAP.md")
CODE_MAP_STAMP_RE = re.compile(
    r"generated-at:\s*(?:[0-9a-f]{7,40}\s*·\s*)?(\d{4}-\d{2}-\d{2})")
CODE_MAP_MATERIAL = ["*.py", "*.sh", "*.js", "*.html", "*.css",
                     ".github/workflows"]


def code_map_advisories() -> list[str]:
    """Warn when docs/CODE_MAP.md's generated-at stamp lags material code
    commits. Thresholds from manifest key "code_map_advisory"
    ({"max_commits": N, "max_age_days": D}), defaults 10 / 5."""
    import datetime
    import subprocess
    if not os.path.exists(CODE_MAP):
        return []  # repo not on the CODE_MAP convention
    m = CODE_MAP_STAMP_RE.search(_read(os.path.join("docs", "CODE_MAP.md")))
    if not m:
        return ["docs/CODE_MAP.md has no parsable 'generated-at:' stamp "
                "(expected 'generated-at: [<sha> ·] YYYY-MM-DD')"]
    stamp = m.group(1)
    cfg = {}
    try:
        cfg = load_manifest().get("code_map_advisory", {})
    except Exception:
        pass
    max_commits = int(cfg.get("max_commits", 10))
    max_age_days = int(cfg.get("max_age_days", 5))
    try:
        out = subprocess.run(
            ["git", "-C", REPO, "log", "--oneline",
             f"--since={stamp}T23:59:59", "--", *CODE_MAP_MATERIAL],
            capture_output=True, text=True, timeout=15)
        if out.returncode != 0:
            return []  # not a git checkout / shallow env — advisory only, skip
        commits = [ln for ln in out.stdout.splitlines() if ln.strip()]
        age_days = (datetime.date.today()
                    - datetime.date.fromisoformat(stamp)).days
    except Exception:
        return []
    warns = []
    if len(commits) >= max_commits:
        warns.append(
            f"docs/CODE_MAP.md stamp {stamp} lags {len(commits)} material "
            f"commit(s) (threshold {max_commits}) — refresh the map + bump "
            f"the stamp (CODE_MAP_CONVENTION.md, (see your governance issue tracker))")
    elif age_days > max_age_days and commits:
        warns.append(
            f"docs/CODE_MAP.md stamp {stamp} is {age_days} days old with "
            f"{len(commits)} material commit(s) since — refresh the map + "
            f"bump the stamp (CODE_MAP_CONVENTION.md, (see your governance issue tracker))")
    return warns


def cmd_init() -> int:
    man = load_manifest() if os.path.exists(MANIFEST) else {}
    man["connection_files"] = discover_connection_files()
    # launch role discovery is informational; the manifest's launch_scripts holds
    # the INTENDED roles (hand-authored), so don't clobber it here.
    man.setdefault("launch_scripts", {})
    man.setdefault("forbidden_patterns", [])
    man.setdefault("rls_required_tables", [])
    man.setdefault("daemons", [])
    with open(MANIFEST, "w") as fh:
        json.dump(man, fh, indent=2)
        fh.write("\n")
    print(f"manifest refreshed: {len(man['connection_files'])} connection files")
    print("discovered launch roles (verify against manifest.launch_scripts):")
    for s, r in discover_launch_roles().items():
        print(f"  {s} -> {r}")
    return 0


def cmd_check() -> int:
    man = load_manifest()
    fails: list[str] = []

    # 1. connection-site inventory
    actual = set(discover_connection_files())
    declared = set(man.get("connection_files", []))
    for p in sorted(actual - declared):
        fails.append(f"[connection] UNDOCUMENTED db connection in {p} "
                     f"— add it to docs/DATA_FLOW.md §3 + manifest.connection_files")
    for p in sorted(declared - actual):
        fails.append(f"[connection] STALE manifest entry {p} no longer connects "
                     f"— remove from manifest.connection_files")

    # 2. launch-script roles
    discovered = discover_launch_roles()
    for script, expected in man.get("launch_scripts", {}).items():
        got = discovered.get(script)
        if got is None:
            fails.append(f"[launch] {script} sets no APP_DSN role "
                         f"(manifest expects {expected})")
        elif got != expected:
            fails.append(f"[launch] {script} connects as '{got}' "
                         f"but manifest expects '{expected}'")

    # 3. forbidden patterns (ratchet — allowed only in grandfathered files)
    for fp in man.get("forbidden_patterns", []):
        rx = re.compile(fp["pattern"])
        allow = set(fp.get("allow_files", []))
        for p in _walk((".py", ".sh")):
            if p in allow:
                continue
            if rx.search(_read(p)):
                fails.append(f"[forbidden] {p}: {fp['reason']} "
                             f"(pattern /{fp['pattern']}/)")

    print("=== system manifest check ===")
    for w in code_map_advisories():
        print("WARN [code-map] " + w)
    if not fails:
        print(f"PASS — {len(actual)} connection files, "
              f"{len(man.get('launch_scripts', {}))} launch roles, "
              f"{len(man.get('forbidden_patterns', []))} forbidden patterns clean")
        return 0
    for f in fails:
        print("FAIL " + f)
    print(f"\n{len(fails)} drift issue(s). Update docs/DATA_FLOW.md + "
          f"docs/system_manifest.json in the same commit, or fix the code.")
    return 1


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--init", action="store_true",
                    help="refresh discovered lists into the manifest")
    args = ap.parse_args()
    return cmd_init() if args.init else cmd_check()


if __name__ == "__main__":
    sys.exit(main())
