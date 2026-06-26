"""
Rebuild kb/paths/_index.yaml from the current per-file YAML in kb/paths/.

Phase 1 made `drugbank` and `drug_mesh` optional and dropped null entries
from the per-file YAML. The index, originally generated from the monolith,
must be re-derived from the source of truth (the per-file YAML) so the two
stay consistent.

Usage:
    python scripts/rebuild_index.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
INDEX = PATHS_DIR / "_index.yaml"


class _IndentDumper(yaml.Dumper):
    def increase_indent(self, flow=False, indentless=False):
        return super().increase_indent(flow, indentless=False)


def _str_representer(dumper, data):
    if "\n" in data:
        return dumper.represent_scalar("tag:yaml.org,2002:str", data, style="|")
    return dumper.represent_scalar("tag:yaml.org,2002:str", data)


_IndentDumper.add_representer(str, _str_representer)


def main() -> int:
    files = sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    print(f"Rebuilding index from {len(files)} files in {PATHS_DIR}")

    entries = []
    for path in files:
        with path.open() as fh:
            doc = yaml.safe_load(fh)
        if not isinstance(doc, dict):
            continue
        graph = doc.get("graph", {})
        entry = {
            "id": graph.get("_id", path.stem),
            "file": path.name,
            "drug": graph.get("drug"),
            "drug_mesh": graph.get("drug_mesh"),
            "drugbank": graph.get("drugbank"),
            "disease": graph.get("disease"),
            "disease_mesh": graph.get("disease_mesh"),
        }
        # Strip keys whose value is None so the index doesn't carry nulls
        entry = {k: v for k, v in entry.items() if v is not None}
        entries.append(entry)

    with INDEX.open("w", encoding="utf-8") as fh:
        yaml.dump(
            entries,
            fh,
            Dumper=_IndentDumper,
            allow_unicode=True,
            default_flow_style=False,
            sort_keys=False,
        )

    print(f"Wrote {len(entries)} entries to {INDEX}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
