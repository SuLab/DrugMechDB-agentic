"""
Layer 3 — Biolink predicate validation.

Read-only check that every edge `key` in each kb/paths/*.yaml file is an
*exact* member of the BiolinkPredicate enum declared in
src/drugmechdb/schema/biolink_predicates.yaml.

This script does NOT normalize surface forms. Whitespace, case, and CURIE
drift produce failures. Run `scripts/canonicalize_predicates.py --write`
first if needed; that is the data-rewrite path. Layer 3 is the final gate.

Usage:
    python scripts/validate_predicates.py                 # all files
    python scripts/validate_predicates.py kb/paths/X.yaml # specific file(s)
    python scripts/validate_predicates.py --json          # machine-readable output

Exit status: 0 if every key passes, 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "biolink_predicates.yaml"


def load_enum() -> set[str]:
    with SCHEMA.open() as fh:
        doc = yaml.safe_load(fh)
    return set(doc["enums"]["BiolinkPredicate"]["permissible_values"].keys())


def iter_files(targets: Iterable[str]) -> list[Path]:
    targets = list(targets)
    if not targets:
        return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
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


def validate_file(path: Path, enum: set[str]) -> list[dict]:
    """Return a list of failure dicts for this file (empty if all keys valid)."""
    with path.open() as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        return [{"file": str(path), "edge_index": None, "key": None, "reason": "not a YAML mapping"}]
    failures = []
    for i, link in enumerate(doc.get("links") or []):
        if not isinstance(link, dict):
            failures.append({"file": str(path), "edge_index": i, "key": None, "reason": "edge is not a mapping"})
            continue
        key = link.get("key")
        if key not in enum:
            failures.append({"file": str(path), "edge_index": i, "key": key, "reason": "key not in BiolinkPredicate enum"})
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="Path files or directories. Defaults to kb/paths/.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    args = parser.parse_args()

    enum = load_enum()
    files = iter_files(args.targets)

    all_failures: list[dict] = []
    for path in files:
        all_failures.extend(validate_file(path, enum))

    summary = {
        "files_checked": len(files),
        "enum_size": len(enum),
        "failure_count": len(all_failures),
        "failures": all_failures,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if all_failures:
            print(f"Layer 3 FAIL: {len(all_failures)} predicate violations across {len(set(f['file'] for f in all_failures))} files\n")
            for f in all_failures[:50]:
                print(f"  {Path(f['file']).name}: edge[{f['edge_index']}].key={f['key']!r} — {f['reason']}")
            if len(all_failures) > 50:
                print(f"  …and {len(all_failures) - 50} more (re-run with --json for full list)")
        else:
            print(f"Layer 3 PASS: {len(files)} files, every edge key is in BiolinkPredicate ({len(enum)} canonical predicates).")

    return 0 if not all_failures else 1


if __name__ == "__main__":
    sys.exit(main())
