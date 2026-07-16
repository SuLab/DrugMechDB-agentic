"""
Detect exact- and near-duplicate mechanistic-path records in kb/paths/.

Definitions
-----------
- **Exact structural duplicate**: two records with the *same edge set* — the same
  {(source, predicate, target)} multigraph — i.e. the identical mechanism, regardless
  of which indication they sit under. (Node set is implied by the edges.)
- **Near-duplicate** (within one drug+disease indication): two records whose edge sets
  overlap heavily (Jaccard >= threshold) without being identical — usually the same
  mechanism curated twice with a small difference.

Legitimate multiplicity: several records for one (drug, disease) are fine when they
encode *genuinely different* mechanisms. This tool flags only same-mechanism repeats,
so it never penalises real branching coverage.

This is a REPORT-ONLY detector — it never edits, merges, or deletes. The dedupe/merge
policy is a human decision (see the issue); a recommended policy is printed at the end.

Usage:
    python scripts/detect_duplicates.py                  # human-readable report
    python scripts/detect_duplicates.py --json           # machine-readable
    python scripts/detect_duplicates.py --threshold 0.85 # near-dup Jaccard cutoff (default 0.80)
Exit: 0 if no duplicates found, 1 if any exact or near duplicate is reported.
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import defaultdict
from itertools import combinations
from pathlib import Path

import yaml

try:
    from yaml import CSafeLoader as _Loader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader as _Loader

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"


def _edge_set(doc: dict) -> frozenset:
    return frozenset(
        (e.get("source"), e.get("key"), e.get("target"))
        for e in (doc.get("links") or [])
        if isinstance(e, dict)
    )


def _indication(graph: dict) -> tuple:
    # A record's indication identity: the drug (mesh or drugbank) + disease mesh.
    return (graph.get("drug_mesh") or graph.get("drugbank"), graph.get("disease_mesh"))


def load_records() -> list[dict]:
    out = []
    for p in sorted(PATHS_DIR.glob("*.yaml")):
        if p.name == "_index.yaml":
            continue
        doc = yaml.load(p.read_text(encoding="utf-8"), Loader=_Loader) or {}
        graph = doc.get("graph") or {}
        edges = _edge_set(doc)
        out.append({
            "id": graph.get("_id") or p.stem,
            "file": p.name,
            "indication": _indication(graph),
            "edges": edges,
            "n_edges": len(edges),
        })
    return out


def find_exact(records: list[dict]) -> list[dict]:
    """Group records that share an identical (non-empty) edge set."""
    by_sig: dict[frozenset, list[dict]] = defaultdict(list)
    for r in records:
        if r["edges"]:
            by_sig[r["edges"]].append(r)
    groups = []
    for sig, members in by_sig.items():
        if len(members) < 2:
            continue
        indications = {m["indication"] for m in members}
        groups.append({
            "ids": sorted(m["id"] for m in members),
            "n_edges": len(sig),
            "same_indication": len(indications) == 1,
        })
    return sorted(groups, key=lambda g: (-len(g["ids"]), g["ids"][0]))


def jaccard(a: frozenset, b: frozenset) -> float:
    if not a and not b:
        return 1.0
    return len(a & b) / len(a | b)


def find_near(records: list[dict], threshold: float) -> list[dict]:
    """Within each indication, flag pairs with Jaccard in [threshold, 1.0)."""
    by_ind: dict[tuple, list[dict]] = defaultdict(list)
    for r in records:
        if r["edges"]:
            by_ind[r["indication"]].append(r)
    pairs = []
    for members in by_ind.values():
        for a, b in combinations(members, 2):
            j = jaccard(a["edges"], b["edges"])
            if threshold <= j < 1.0:
                pairs.append({
                    "ids": sorted([a["id"], b["id"]]),
                    "jaccard": round(j, 3),
                    "n_edges": [a["n_edges"], b["n_edges"]],
                })
    return sorted(pairs, key=lambda p: -p["jaccard"])


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--threshold", type=float, default=0.80,
                    help="near-duplicate Jaccard cutoff (default 0.80)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    records = load_records()
    exact = find_exact(records)
    near = find_near(records, args.threshold)

    if args.json:
        print(json.dumps({"records": len(records), "exact_duplicate_groups": exact,
                          "near_duplicate_pairs": near}, indent=2))
        return 0 if not (exact or near) else 1

    n_exact_records = sum(len(g["ids"]) for g in exact)
    print(f"=== Duplicate detection over {len(records)} records "
          f"(near-dup threshold Jaccard >= {args.threshold}) ===")
    print(f"\nExact structural duplicates: {len(exact)} group(s) covering {n_exact_records} records")
    for g in exact[:50]:
        tag = "same indication" if g["same_indication"] else "DIFFERENT indications"
        print(f"  [{g['n_edges']} edges, {tag}] {', '.join(g['ids'])}")
    if len(exact) > 50:
        print(f"  …and {len(exact) - 50} more (use --json)")

    print(f"\nNear-duplicates within an indication: {len(near)} pair(s)")
    for p in near[:50]:
        print(f"  [Jaccard {p['jaccard']}, {p['n_edges'][0]} vs {p['n_edges'][1]} edges] {', '.join(p['ids'])}")
    if len(near) > 50:
        print(f"  …and {len(near) - 50} more (use --json)")

    print("\nRecommended policy (NOT applied automatically):")
    print("  - Exact duplicates, same indication: keep one (prefer the record with richer")
    print("    per-edge evidence; otherwise the lowest _n), retire the rest.")
    print("  - Exact duplicates, different indications: likely a copy-paste error in the")
    print("    graph metadata — send to human review, do not auto-merge.")
    print("  - Near-duplicates: human review — they may be a real variant or a stray edit.")
    return 0 if not (exact or near) else 1


if __name__ == "__main__":
    sys.exit(main())
