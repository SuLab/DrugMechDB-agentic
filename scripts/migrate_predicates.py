"""
Migrate a record's edge predicates from the legacy (v1.3.0-era) Biolink vocabulary
to the pinned current release, using the qualifier model.

WHAT IT DOES
Biolink's v2->v4 refactor removed the `positively/negatively regulates` and
`increases/decreases <aspect> of` predicate families, folding them into
`regulates` / `affects` carried with `object_aspect_qualifier` +
`object_direction_qualifier`. This script applies that mapping to a record:

    - key: decreases activity of        - key: affects
      source: MESH:D000068877     ->      object_aspect_qualifier: activity
      target: UniProt:A9UF07              object_direction_qualifier: decreased
                                          source: MESH:D000068877
                                          target: UniProt:A9UF07

The mapping is NOT defined here — it lives in
`src/drugmechdb/schema/biolink_predicate_status.yaml`, the single source of truth
shared with QC Layer 3 (scripts/validate_predicates.py). Predicates marked
`needs_human_decision` are never rewritten; they are reported and left alone.

WHY A LINE-BASED REWRITE
Round-tripping these files through a YAML dumper would reformat every line and bury
the change in noise. Every edge key in the corpus is written as `- key: <value>` on
its own line, so the transform is applied textually: the record's formatting,
comments, and quoting style survive untouched.

Usage:
    python scripts/migrate_predicates.py --check  DIR_OR_FILE...   # report only, exit 1 if stale
    python scripts/migrate_predicates.py --write  DIR_OR_FILE...   # rewrite in place
    python scripts/migrate_predicates.py --write --diff DIR...     # rewrite + print each change
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
STATUS = REPO / "src" / "drugmechdb" / "schema" / "biolink_predicate_status.yaml"

KEY_LINE = re.compile(r"^(?P<indent>\s*)- key:\s*(?P<key>.+?)\s*$")

# Qualifier keys are emitted in this order, directly under the rewritten key.
QUALIFIER_ORDER = ("object_aspect_qualifier", "object_direction_qualifier", "qualified_predicate")


def load_status() -> dict:
    doc = yaml.safe_load(STATUS.read_text(encoding="utf-8"))
    return doc["predicates"]


def rel(path: Path) -> str:
    """Repo-relative when possible; the given path otherwise."""
    try:
        return str(path.resolve().relative_to(REPO))
    except ValueError:
        return str(path)


def iter_files(targets: list[str]) -> list[Path]:
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
        elif p.is_file():
            files.append(p)
        else:
            print(f"warning: {t} is not a file or directory", file=sys.stderr)
    return files


def migrate_text(text: str, status: dict) -> tuple[str, list[tuple[str, str]], list[str]]:
    """Return (new_text, [(old_key, new_key)...], [blocked_predicates...])."""
    out: list[str] = []
    changed: list[tuple[str, str]] = []
    blocked: list[str] = []

    for line in text.splitlines(keepends=True):
        m = KEY_LINE.match(line.rstrip("\n"))
        if not m:
            out.append(line)
            continue
        key = m.group("key").strip().strip("'\"")
        entry = status.get(key)
        if not entry or entry.get("status") == "current":
            out.append(line)
            continue
        replacement = entry.get("replacement")
        if not replacement:
            blocked.append(key)                     # needs_human_decision — leave untouched
            out.append(line)
            continue

        newline = "\n" if line.endswith("\n") else ""
        indent = m.group("indent")
        child = indent + "  "                       # align with `source:`/`target:`
        out.append(f"{indent}- key: {replacement['key']}{newline}")
        for q in QUALIFIER_ORDER:
            if q in replacement:
                out.append(f"{child}{q}: {replacement[q]}{newline}")
        changed.append((key, replacement["key"]))

    return "".join(out), changed, blocked


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="+", help="Record files or directories to migrate.")
    mode = ap.add_mutually_exclusive_group(required=True)
    mode.add_argument("--check", action="store_true",
                      help="Report what would change; exit 1 if anything is stale.")
    mode.add_argument("--write", action="store_true", help="Rewrite the files in place.")
    ap.add_argument("--diff", action="store_true", help="Print each predicate rewrite.")
    args = ap.parse_args()

    status = load_status()
    files = iter_files(args.targets)
    if not files:
        print("no files matched", file=sys.stderr)
        return 2

    n_files = n_edges = 0
    all_blocked: dict[str, int] = {}
    for path in files:
        text = path.read_text(encoding="utf-8")
        new_text, changed, blocked = migrate_text(text, status)
        for b in blocked:
            all_blocked[b] = all_blocked.get(b, 0) + 1
        if not changed:
            continue
        n_files += 1
        n_edges += len(changed)
        if args.diff or args.check:
            print(rel(path))
            for old, new in changed:
                print(f"    {old}  ->  {new}")
        if args.write:
            path.write_text(new_text, encoding="utf-8")

    verb = "would migrate" if args.check else "migrated"
    print(f"\n{verb} {n_edges} edges across {n_files}/{len(files)} files.")
    if all_blocked:
        print("\nLEFT FOR A HUMAN (no mechanical replacement — see the `note` in "
              f"{rel(STATUS)}):")
        for k, n in sorted(all_blocked.items(), key=lambda kv: -kv[1]):
            print(f"    {n:4d}  {k}")

    return 1 if (args.check and n_edges) else 0


if __name__ == "__main__":
    raise SystemExit(main())
