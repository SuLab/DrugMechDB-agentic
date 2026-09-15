"""
Layer 3 — Biolink predicate validation.

Read-only check that every edge `key` in each kb/paths/*.yaml file is an
*exact* member of the BiolinkPredicate enum declared in
src/drugmechdb/schema/biolink_predicates.yaml.

The enum is deliberately era-spanning: it still accepts the v1.3.0-era vocabulary the
4,846 legacy records are written in. Which era a given record MAY use is the second
check, and it is profile-dependent (mirroring qc.py's own legacy/ai_curated split):

  legacy      any enum member, current or not — these records are frozen history.
  ai_curated  `status: current` members only. A record curated today must be written in
              the pinned Biolink release, so the removed `positively regulates` /
              `increases <aspect> of` families are rejected with the qualifier form that
              replaces them (see src/drugmechdb/schema/biolink_predicate_status.yaml).

For ai_curated records the qualifiers themselves are checked too: values must be in the
schema's ObjectAspectEnum / ObjectDirectionEnum, and the canonical predicates that carry
polarity (`affects`, `regulates`) must actually carry it.

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
STATUS = REPO / "src" / "drugmechdb" / "schema" / "biolink_predicate_status.yaml"
MODEL = REPO / "src" / "drugmechdb" / "schema" / "drugmechdb.yaml"

# Canonical predicates whose meaning lives in the qualifiers: bare, they assert almost
# nothing, so an ai_curated edge using one must say which way it goes.
NEEDS_DIRECTION = {"affects", "regulates"}
NEEDS_ASPECT = {"affects"}


def load_enum() -> set[str]:
    with SCHEMA.open() as fh:
        doc = yaml.safe_load(fh)
    return set(doc["enums"]["BiolinkPredicate"]["permissible_values"].keys())


def load_status() -> dict:
    """predicate -> {status, replacement, ...} for the pinned Biolink release."""
    with STATUS.open() as fh:
        return yaml.safe_load(fh)["predicates"]


def load_qualifier_values() -> tuple[set[str], set[str]]:
    with MODEL.open() as fh:
        enums = yaml.safe_load(fh)["enums"]
    return (set(enums["ObjectAspectEnum"]["permissible_values"]),
            set(enums["ObjectDirectionEnum"]["permissible_values"]))


def detect_profile(doc: dict) -> str:
    """Same rule qc.py uses: any per-edge evidence -> ai_curated."""
    for link in doc.get("links") or []:
        if isinstance(link, dict) and link.get("evidence"):
            return "ai_curated"
    return "legacy"


def _replacement_hint(entry: dict) -> str:
    why = {"legacy_only": "removed in current Biolink",
           "deprecated": "deprecated in current Biolink"}.get(entry.get("status"),
                                                              "not a current Biolink predicate")
    r = entry.get("replacement")
    if not r:
        return (f"{why} and has no mechanical replacement "
                f"({entry.get('note', 'needs a human decision')})")
    bits = [f"key={r['key']!r}"] + [f"{k}={v!r}" for k, v in r.items() if k != "key"]
    return f"{why} — use " + ", ".join(bits)


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


def validate_file(path: Path, enum: set[str], status: dict,
                  aspects: set[str], directions: set[str],
                  profile: str = "auto") -> list[dict]:
    """Return a list of failure dicts for this file (empty if all keys valid)."""
    with path.open() as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        return [{"file": str(path), "edge_index": None, "key": None, "reason": "not a YAML mapping"}]

    effective = detect_profile(doc) if profile == "auto" else profile
    failures = []
    for i, link in enumerate(doc.get("links") or []):
        if not isinstance(link, dict):
            failures.append({"file": str(path), "edge_index": i, "key": None, "reason": "edge is not a mapping"})
            continue
        key = link.get("key")
        fail = lambda reason: failures.append(
            {"file": str(path), "edge_index": i, "key": key, "profile": effective, "reason": reason})

        if key not in enum:
            fail("key not in BiolinkPredicate enum")
            continue

        aspect = link.get("object_aspect_qualifier")
        direction = link.get("object_direction_qualifier")
        if aspect is not None and aspect not in aspects:
            fail(f"object_aspect_qualifier={aspect!r} not in ObjectAspectEnum")
        if direction is not None and direction not in directions:
            fail(f"object_direction_qualifier={direction!r} not in ObjectDirectionEnum")

        if effective != "ai_curated":
            continue                       # legacy records are frozen in their own era

        entry = status.get(key) or {}
        if entry.get("status") != "current":
            fail(_replacement_hint(entry))
            continue
        if key in NEEDS_DIRECTION and direction is None:
            fail(f"{key!r} carries its polarity in object_direction_qualifier, which is missing")
        if key in NEEDS_ASPECT and aspect is None:
            fail(f"{key!r} requires object_aspect_qualifier (which aspect of the target is affected)")
    return failures


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="Path files or directories. Defaults to kb/paths/.")
    parser.add_argument("--json", action="store_true", help="Output machine-readable JSON.")
    parser.add_argument("--profile", choices=("auto", "legacy", "ai_curated"), default="auto",
                        help="Validation profile. `auto` detects per file (default).")
    args = parser.parse_args()

    enum = load_enum()
    status = load_status()
    aspects, directions = load_qualifier_values()
    files = iter_files(args.targets)

    all_failures: list[dict] = []
    for path in files:
        all_failures.extend(validate_file(path, enum, status, aspects, directions, args.profile))

    summary = {
        "files_checked": len(files),
        "enum_size": len(enum),
        "current_predicates": sum(1 for v in status.values() if v.get("status") == "current"),
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
            n_current = summary["current_predicates"]
            print(f"Layer 3 PASS: {len(files)} files — every edge key is in BiolinkPredicate "
                  f"({len(enum)} accepted; {n_current} current in the pinned Biolink release).")

    return 0 if not all_failures else 1


if __name__ == "__main__":
    sys.exit(main())
