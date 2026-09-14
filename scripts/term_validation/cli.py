"""Shared CLI body for the per-authority validators.

`conf/oak_config.yaml` names three scripts — validate_mesh.py,
validate_uniprot.py, validate_reactome.py — as the validators for the prefixes
that have no OBO adapter. They are thin by design: all three answer the same
question against the same machinery, differing only in which prefixes they own.

Keeping the body here means adding a fourth authority is a three-line script,
and means there is one place where the audit-vs-gate behaviour is defined.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .audit import audit
from .resolvers import Registry
from .types import TermResult, TermStatus

REPO = Path(__file__).resolve().parent.parent.parent
PATHS_DIR = REPO / "kb" / "paths"


def iter_files(targets: list[str]) -> list[Path]:
    if not targets:
        return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    files: list[Path] = []
    for target in targets:
        path = Path(target)
        if path.is_dir():
            files.extend(sorted(q for q in path.glob("*.yaml") if q.name != "_index.yaml"))
        elif path.is_file():
            files.append(path)
    return files


def restrict_to(registry: Registry, prefixes: set[str]) -> None:
    """Make the registry answer SKIPPED for everything outside `prefixes`."""
    original = registry.resolve

    def scoped(curie: str) -> TermResult:
        prefix = curie.split(":", 1)[0] if ":" in curie else ""
        if prefix not in prefixes:
            return TermResult(curie, TermStatus.SKIPPED, detail="outside this validator's scope")
        return original(curie)

    registry.resolve = scoped  # type: ignore[method-assign]


def run(authority: str, prefixes: set[str], argv: list[str] | None = None) -> int:
    """Validate every node of `prefixes` across the given files.

    Exit: 0 clean (or audit mode) · 1 failures found with --strict · 2 no files.
    Audit by default — reporting a problem and failing a build are different
    decisions, and only the first one is settled.
    """
    ap = argparse.ArgumentParser(
        prog=f"validate_{authority.lower()}",
        description=f"Validate {authority} node identifiers against the {authority} API.")
    ap.add_argument("targets", nargs="*", help="Files or directories. Default: kb/paths/")
    ap.add_argument("--offline", action="store_true",
                    help="Answer only from the committed cache; never touch the network.")
    ap.add_argument("--no-names", action="store_true",
                    help="Check identifiers only; skip the name/label comparison.")
    ap.add_argument("--json", dest="json_out", help="Write the full report as JSON here.")
    ap.add_argument("--limit", type=int, default=None, help="Only the first N files.")
    ap.add_argument("--strict", action="store_true",
                    help="Exit 1 when an identifier does not resolve (gate behaviour). "
                         "Off by default: this is an audit.")
    args = ap.parse_args(argv)

    files = iter_files(args.targets)
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("No files to check.", file=sys.stderr)
        return 2

    registry = Registry(prefer_oak=False, offline=args.offline)
    restrict_to(registry, prefixes)

    def progress(done: int, total: int) -> None:
        print(f"\r  resolving {done}/{total}", end="", file=sys.stderr, flush=True)

    report = audit(files, registry, check_names=not args.no_names, progress=progress)
    print(file=sys.stderr)
    registry.flush()

    data = report.to_dict()
    checked = sum(c for s, c in data["status_counts"].items() if s != "skipped")
    failures = report.existence_failures
    mismatches = report.name_mismatches

    print(f"=== {authority} term validation ===")
    print(f"  files                {data['files_checked']}")
    print(f"  {authority} node occurrences  {checked}")
    print(f"  unresolved (not reached)      {data['status_counts'].get('unresolved', 0)}")
    print(f"  identifiers that do not exist {len(failures)}")
    print(f"  name mismatches               {len(mismatches)}")

    for finding in failures[:30]:
        item = finding.to_dict()
        print(f"    [{item['status']}] {item['curie']}  name={item['record_name']!r}"
              f"  ({Path(item['file']).name})")
    if len(failures) > 30:
        print(f"    …and {len(failures) - 30} more")

    if args.json_out:
        out = Path(args.json_out)
        out.parent.mkdir(parents=True, exist_ok=True)
        out.write_text(json.dumps(data, indent=2) + "\n")
        print(f"  JSON -> {out}")

    return 1 if (args.strict and failures) else 0
