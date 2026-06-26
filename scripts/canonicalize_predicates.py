"""
Rewrite every edge `key` in kb/paths/*.yaml to its canonical BiolinkPredicate
form, using the alias map in data/predicate_aliases.yaml.

Normalization pipeline (applied in order, per edge key):
  1. Coerce to string; strip leading/trailing whitespace.
  2. Collapse internal whitespace (any run of spaces/tabs/newlines -> one space).
  3. Strip a leading 'biolink:' CURIE prefix.
  4. Replace underscores with spaces.
  5. Lowercase.
  6. If the result is a key in data/predicate_aliases.yaml, replace it with
     the mapped canonical form.
  7. Assert the final value is a member of the BiolinkPredicate enum.

The script is idempotent — running it twice produces no further changes.
Defaults to --dry-run; pass --write to apply changes in place.

Usage:
    python scripts/canonicalize_predicates.py            # dry-run (default)
    python scripts/canonicalize_predicates.py --write    # apply changes
    python scripts/canonicalize_predicates.py --report-only  # no scanning of files; just print enum/alias info

Outputs (always written, even on dry-run):
    docs/phase1_5_canonicalization_summary.json
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path
from typing import Any

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
ALIASES = REPO / "data" / "predicate_aliases.yaml"
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "biolink_predicates.yaml"
SUMMARY = REPO / "docs" / "phase1_5_canonicalization_summary.json"


_WS_RE = re.compile(r"\s+")


class _IndentDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_IndentDumper.add_representer(str, _str_representer)


def dump_yaml(data: Any, stream: Any = None):
    return yaml.dump(
        data,
        stream=stream,
        Dumper=_IndentDumper,
        allow_unicode=True,
        default_flow_style=False,
        sort_keys=False,
    )


def load_enum() -> set[str]:
    with SCHEMA.open() as fh:
        doc = yaml.safe_load(fh)
    return set(doc["enums"]["BiolinkPredicate"]["permissible_values"].keys())


def load_aliases() -> dict[str, str]:
    with ALIASES.open() as fh:
        doc = yaml.safe_load(fh)
    return (doc or {}).get("aliases") or {}


def normalize(raw: Any) -> str:
    """Apply the deterministic surface-form normalization pipeline."""
    if raw is None:
        return ""
    s = str(raw).strip()
    s = _WS_RE.sub(" ", s)
    if s.lower().startswith("biolink:"):
        s = s[len("biolink:"):]
    s = s.replace("_", " ")
    s = s.lower()
    return s


def canonicalize(raw: Any, aliases: dict[str, str]) -> str:
    """Return the canonical predicate string for a raw input."""
    norm = normalize(raw)
    return aliases.get(norm, norm)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "targets", nargs="*",
        help="Path files or directories. Defaults to kb/paths/.",
    )
    parser.add_argument(
        "--write", action="store_true",
        help="Apply rewrites in place. Default is dry-run.",
    )
    parser.add_argument(
        "--report-only", action="store_true",
        help="Print enum + alias info and exit without touching path files.",
    )
    args = parser.parse_args()

    enum = load_enum()
    aliases = load_aliases()
    print(f"BiolinkPredicate enum size: {len(enum)}")
    print(f"Lexical aliases in {ALIASES.relative_to(REPO)}: {len(aliases)}")

    if args.report_only:
        print("\n--report-only: not scanning path files.")
        return 0

    if args.targets:
        files = []
        for t in args.targets:
            p = Path(t)
            if p.is_dir():
                files.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
            elif p.is_file():
                files.append(p)
            else:
                print(f"warning: {t} is not a file or directory", file=sys.stderr)
    else:
        files = sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    print(f"Scanning {len(files)} path files (dry-run={not args.write})…")

    rewrite_counts: Counter[tuple[str, str]] = Counter()
    unmapped: Counter[str] = Counter()
    unmapped_files: dict[str, set[str]] = {}
    files_touched = 0
    edges_seen = 0

    for i, path in enumerate(files, start=1):
        if i % 1000 == 0:
            print(f"  …{i}/{len(files)}")
        with path.open() as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue

        changed = False
        for link in doc.get("links", []) or []:
            if not isinstance(link, dict):
                continue
            edges_seen += 1
            raw = link.get("key")
            canonical = canonicalize(raw, aliases)
            if canonical not in enum:
                unmapped[str(raw)] += 1
                unmapped_files.setdefault(str(raw), set()).add(path.name)
                continue
            if canonical != raw:
                rewrite_counts[(str(raw), canonical)] += 1
                link["key"] = canonical
                changed = True

        if changed and args.write:
            with path.open("w", encoding="utf-8") as fh:
                dump_yaml(doc, fh)
            files_touched += 1
        elif changed:
            files_touched += 1

    summary = {
        "edges_seen": edges_seen,
        "files_touched": files_touched,
        "rewrites": [
            {"from": k[0], "to": k[1], "count": v}
            for k, v in rewrite_counts.most_common()
        ],
        "unmapped": [
            {"raw": raw, "count": cnt, "files_affected": sorted(unmapped_files[raw])[:5]}
            for raw, cnt in unmapped.most_common()
        ],
        "dry_run": not args.write,
    }
    SUMMARY.parent.mkdir(parents=True, exist_ok=True)
    SUMMARY.write_text(json.dumps(summary, indent=2))

    print()
    print(f"Edges scanned       : {edges_seen}")
    print(f"Files touched       : {files_touched}{' (dry-run, not written)' if not args.write else ''}")
    print(f"Rewrite types       : {len(rewrite_counts)}")
    print(f"Unmapped predicates : {len(unmapped)}")
    if rewrite_counts:
        print("\nTop rewrites:")
        for (frm, to), c in rewrite_counts.most_common(10):
            print(f"  {c:6d}  {frm!r} -> {to!r}")
    if unmapped:
        print("\nUnmapped (need curator decision):")
        for raw, c in unmapped.most_common(20):
            print(f"  {c:6d}  {raw!r}")
        print("\nFix by adding an entry to data/predicate_aliases.yaml or by")
        print("adding the predicate to src/drugmechdb/schema/biolink_predicates.yaml")
        print("(with a Biolink Model citation), then re-run.")
    print(f"\nSummary: {SUMMARY}")
    return 0 if not unmapped else 1


if __name__ == "__main__":
    sys.exit(main())
