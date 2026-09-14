#!/usr/bin/env python3
"""
Term-existence audit — does every node CURIE in the corpus actually resolve?

This is the check Layer 2 does not do. Layer 2 verifies that a CURIE's *prefix*
matches the canonical ontology for its Biolink type; it never asks the ontology
whether the identifier exists. So a fabricated-but-well-formed id passes the
full QC gate. This script asks.

AUDIT ONLY — it reports, it does not gate. Nothing in `just qc` calls it, and a
failure here does not fail CI. Wiring it into the gate is a separate decision
that needs the numbers this produces first.

Two findings, reported separately:
    existence   ABSENT (does not resolve) or OBSOLETE (deprecated upstream)
    name        resolves, but `name` != the ontology's canonical label

UNRESOLVED (could not reach the authority) is never a failure and is reported
on its own line so a degraded run is obvious rather than silently clean.

Usage:
    python scripts/audit_term_existence.py                      # whole corpus
    python scripts/audit_term_existence.py kb/paths/X.yaml      # specific files
    python scripts/audit_term_existence.py --prefix MESH        # one authority
    python scripts/audit_term_existence.py --offline            # cache only, no network
    python scripts/audit_term_existence.py --json out.json      # machine-readable
    python scripts/audit_term_existence.py --markdown docs/term_existence_audit.md

Exit: 0 always in audit mode (it is a report). Use --fail-on-existence to make
existence failures exit 1, for when this eventually becomes a gate.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
sys.path.insert(0, str(HERE))  # so `term_validation` resolves (scripts/ is not a package)

from term_validation.audit import audit  # noqa: E402
from term_validation.cache import TermCache  # noqa: E402
from term_validation.resolvers import Registry  # noqa: E402

PATHS_DIR = REPO / "kb" / "paths"


def iter_files(targets: list[str]) -> list[Path]:
    if not targets:
        return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
        elif p.is_file():
            files.append(p)
    return files


def render_markdown(report, prefixes: list[str] | None) -> str:
    d = report.to_dict()
    lines = [
        "# Term-existence audit",
        "",
        "Does every node CURIE in the corpus resolve in its source ontology, and does",
        "each record `name` match the canonical label? **This is an audit, not a gate** —",
        "nothing in `just qc` enforces it.",
        "",
        f"- files checked: **{d['files_checked']}**",
        f"- node occurrences: **{d['nodes_checked']}**",
        f"- unique CURIEs resolved: **{d['unique_curies']}**",
        f"- existence failures (distinct CURIEs): **{d['existence_failure_count']}**",
        f"- name mismatches (distinct CURIE+name): **{d['name_mismatch_count']}**",
        "",
        "## Status by prefix",
        "",
    ]
    statuses = ["exists", "absent", "obsolete", "unresolved", "skipped"]
    lines.append("| prefix | " + " | ".join(statuses) + " |")
    lines.append("|---" * (len(statuses) + 1) + "|")
    for prefix, counts in d["prefix_status"].items():
        row = [prefix] + [str(counts.get(s, 0)) for s in statuses]
        lines.append("| " + " | ".join(row) + " |")

    unresolved = d["status_counts"].get("unresolved", 0)
    if unresolved:
        lines += [
            "",
            f"> **{unresolved} node occurrences are UNRESOLVED** — the authority could not be",
            "> reached, or does not serve that ontology. These are *not* failures: nothing was",
            "> established about them either way. Re-run with network access to settle them.",
        ]

    for kind, title, note in (
        ("existence", "Existence failures",
         "The identifier does not resolve (ABSENT) or is deprecated upstream (OBSOLETE). "
         "One row per distinct CURIE."),
        ("name", "Name mismatches",
         "The identifier resolves but the record's `name` differs from the ontology's "
         "canonical label. Weaker signal — ontologies carry synonyms a record may "
         "legitimately prefer."),
    ):
        rows = [f for f in d["findings"] if f["kind"] == kind]
        lines += ["", f"## {title} ({len(rows)})", "", note, ""]
        if not rows:
            lines.append("_None._")
            continue
        if kind == "existence":
            lines.append("| CURIE | status | record name | Biolink type | first seen in |")
            lines.append("|---|---|---|---|---|")
            for r in rows[:400]:
                lines.append("| `{curie}` | {status} | {record_name} | {biolink_label} | `{f}` |".format(
                    f=Path(r["file"]).name, **r))
        else:
            lines.append("| CURIE | record name | canonical label | first seen in |")
            lines.append("|---|---|---|---|")
            for r in rows[:400]:
                lines.append("| `{curie}` | {record_name} | {canonical_label} | `{f}` |".format(
                    f=Path(r["file"]).name, **r))
        if len(rows) > 400:
            lines.append(f"")
            lines.append(f"_…and {len(rows) - 400} more (see the JSON report)._")

    return "\n".join(lines) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("targets", nargs="*", help="Files or directories. Default: kb/paths/")
    ap.add_argument("--prefix", action="append", default=None,
                    help="Only audit CURIEs with this prefix (repeatable).")
    ap.add_argument("--offline", action="store_true",
                    help="Use only the committed cache; never touch the network. "
                         "Uncached terms come back UNRESOLVED.")
    ap.add_argument("--no-oak", action="store_true",
                    help="Skip OAK adapters and go straight to the REST backends.")
    ap.add_argument("--no-names", action="store_true", help="Skip the name/label comparison.")
    ap.add_argument("--json", dest="json_out", help="Write the full report as JSON here.")
    ap.add_argument("--markdown", dest="md_out", help="Write a readable report here.")
    ap.add_argument("--limit", type=int, default=None,
                    help="Audit only the first N files (for a quick sample).")
    ap.add_argument("--fail-on-existence", action="store_true",
                    help="Exit 1 if any existence failure is found (gate behaviour).")
    args = ap.parse_args()

    files = iter_files(args.targets)
    if args.limit:
        files = files[: args.limit]
    if not files:
        print("No files to audit.", file=sys.stderr)
        return 2

    registry = Registry(prefer_oak=not args.no_oak, offline=args.offline)

    if args.prefix:
        wanted = set(args.prefix)
        original = registry.resolve

        def filtered(curie: str):
            prefix = curie.split(":", 1)[0] if ":" in curie else ""
            if prefix not in wanted:
                from term_validation.types import TermResult, TermStatus
                return TermResult(curie, TermStatus.SKIPPED, detail="filtered out by --prefix")
            return original(curie)

        registry.resolve = filtered  # type: ignore[method-assign]

    def progress(done: int, total: int) -> None:
        pct = 100 * done / total if total else 100
        print(f"\r  resolving {done}/{total} ({pct:.0f}%)", end="", file=sys.stderr, flush=True)

    print(f"Auditing {len(files)} file(s)…", file=sys.stderr)
    report = audit(files, registry, check_names=not args.no_names, progress=progress)
    print(file=sys.stderr)
    registry.flush()

    d = report.to_dict()
    counts: Counter = Counter(d["status_counts"])
    print("=== Term-existence audit ===")
    print(f"  files            {d['files_checked']}")
    print(f"  node occurrences {d['nodes_checked']}")
    print(f"  unique CURIEs    {d['unique_curies']}")
    print(f"  cache hits       {registry.stats['cache_hits']}  lookups {registry.stats['lookups']}")
    print("  status (occurrences):")
    for status in ("exists", "absent", "obsolete", "unresolved", "skipped"):
        print(f"    {status:<11} {counts.get(status, 0)}")
    print(f"  existence failures (distinct CURIEs): {d['existence_failure_count']}")
    print(f"  name mismatches (distinct):           {d['name_mismatch_count']}")

    for finding in report.existence_failures[:25]:
        f = finding.to_dict()
        print(f"    [{f['status']}] {f['curie']}  name={f['record_name']!r}  ({Path(f['file']).name})")
    if d["existence_failure_count"] > 25:
        print(f"    …and {d['existence_failure_count'] - 25} more")

    if args.json_out:
        Path(args.json_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.json_out).write_text(json.dumps(d, indent=2, sort_keys=False) + "\n")
        print(f"  JSON  -> {args.json_out}")
    if args.md_out:
        Path(args.md_out).parent.mkdir(parents=True, exist_ok=True)
        Path(args.md_out).write_text(render_markdown(report, args.prefix))
        print(f"  report -> {args.md_out}")

    if args.fail_on_existence and d["existence_failure_count"]:
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
