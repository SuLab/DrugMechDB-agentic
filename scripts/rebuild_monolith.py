"""
Rebuild the consolidated indication_paths.{yaml,json} from the per-record files
in kb/paths/ — the inverse of split_monolith.py.

The per-record YAML files are the source of truth; the shipped monolith is a
consumable consolidation of them (the classic DrugMechDB distribution format).
Over time the monolith drifts from the per-record files (edits land per-record).
This regenerates the monolith deterministically so it can never silently drift.

Determinism: records are emitted in a canonical order (sorted by graph._id) and
each record's content and key order are taken verbatim from its per-record file,
so the output is a pure function of kb/paths/ — reproducible on any machine and
a faithful round-trip with split_monolith.py.

Usage:
    python scripts/rebuild_monolith.py                     # write indication_paths.{yaml,json}
    python scripts/rebuild_monolith.py --check             # exit 1 if the on-disk artifacts are stale
    python scripts/rebuild_monolith.py --yaml P --json Q   # write to alternate paths (for testing)
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
PATHS_DIR = REPO / "kb" / "paths"

# Reuse split_monolith.py's YAML style so the consolidated file matches the
# house format exactly (the two scripts are inverses of each other).
sys.path.insert(0, str(HERE))
from split_monolith import dump_yaml  # noqa: E402


def load_records() -> list[dict]:
    """Load every per-record file (except the generated _index) in canonical
    _id order. Content is passed through verbatim — no mutation."""
    files = sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    records = [yaml.safe_load(p.read_text(encoding="utf-8")) for p in files]
    records.sort(key=lambda r: ((r or {}).get("graph") or {}).get("_id") or "")
    return records


def render_yaml(records: list[dict]) -> str:
    return dump_yaml(records)


def render_json(records: list[dict]) -> str:
    return json.dumps(records, indent=2, ensure_ascii=False) + "\n"


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--yaml", default=str(REPO / "indication_paths.yaml"))
    ap.add_argument("--json", default=str(REPO / "indication_paths.json"))
    ap.add_argument("--check", action="store_true",
                    help="verify the on-disk artifacts match a fresh rebuild; exit 1 if stale")
    args = ap.parse_args()

    records = load_records()
    y, j = render_yaml(records), render_json(records)

    if args.check:
        stale = []
        for path, fresh in ((Path(args.yaml), y), (Path(args.json), j)):
            current = path.read_text(encoding="utf-8") if path.exists() else None
            if current != fresh:
                stale.append(path.name)
        if stale:
            print(f"STALE: {', '.join(stale)} differ from a fresh rebuild "
                  f"({len(records)} records) — run scripts/rebuild_monolith.py.")
            return 1
        print(f"OK: consolidated artifacts are up to date ({len(records)} records).")
        return 0

    Path(args.yaml).write_text(y, encoding="utf-8")
    Path(args.json).write_text(j, encoding="utf-8")
    print(f"Wrote {args.yaml} and {args.json} ({len(records)} records, sorted by _id).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
