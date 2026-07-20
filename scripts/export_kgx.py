"""
Export the DrugMechDB corpus to a Biolink KGX knowledge graph (JSON).

KGX (Knowledge Graph Exchange) is the standard interchange format for Biolink / Translator
knowledge graphs. This emits one KGX JSON document: {"nodes": [...], "edges": [...]}.

- Nodes are deduped by CURIE across all records; `category` = `biolink:<node label>`.
- Edges are deduped by (subject, predicate, object); `predicate` = `biolink:<snake_case key>`.
  Each edge records the DrugMechDB record(s) it came from (`source_records`) and a primary
  `knowledge_source` (`infores:drugmechdb`).

Read-only on the corpus — it never modifies kb/paths. Node CURIEs are emitted verbatim
from the corpus; Biolink-standard prefix normalization (e.g. UniProt -> UniProtKB) is a
deliberate separate follow-up, not done here. Dependency-free: no `kgx` package required.

Usage:
    python scripts/export_kgx.py                 # -> exports/drugmechdb_kgx.json
    python scripts/export_kgx.py --out PATH
    python scripts/export_kgx.py --stats          # print counts only, write nothing
Exit 0 on success.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

try:
    from yaml import CSafeLoader as _Loader
except ImportError:  # pragma: no cover
    from yaml import SafeLoader as _Loader

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
KNOWLEDGE_SOURCE = "infores:drugmechdb"


def biolink_category(label) -> str:
    # DrugMechDB's 14 node labels are the Biolink class names, so the category is
    # biolink:<label> (e.g. Protein -> biolink:Protein). Unknown/empty -> NamedThing.
    return f"biolink:{label}" if label else "biolink:NamedThing"


def biolink_predicate(key) -> str:
    # DrugMechDB predicate keys are Biolink predicate labels ("decreases activity of");
    # the Biolink CURIE is biolink:<snake_case> ("biolink:decreases_activity_of").
    return "biolink:" + "_".join(str(key).strip().split()) if key else "biolink:related_to"


def build() -> tuple[list[dict], list[dict], int]:
    nodes: dict[str, dict] = {}
    edges: dict[tuple, dict] = {}
    n_records = 0
    for f in sorted(PATHS_DIR.glob("*.yaml")):
        if f.name == "_index.yaml":
            continue
        doc = yaml.load(f.read_text(encoding="utf-8"), Loader=_Loader) or {}
        n_records += 1
        rid = (doc.get("graph") or {}).get("_id") or f.stem
        for n in (doc.get("nodes") or []):
            nid = n.get("id")
            if not nid:
                continue
            if nid not in nodes:
                nodes[nid] = {"id": nid, "category": biolink_category(n.get("label")),
                              "name": n.get("name")}
        for e in (doc.get("links") or []):
            s, o = e.get("source"), e.get("target")
            if not (s and o):
                continue
            p = biolink_predicate(e.get("key"))
            ed = edges.get((s, p, o))
            if ed is None:
                ed = edges[(s, p, o)] = {"id": f"{s}--{p}--{o}", "subject": s,
                                         "predicate": p, "object": o,
                                         "knowledge_source": KNOWLEDGE_SOURCE,
                                         "source_records": set()}
            ed["source_records"].add(rid)

    node_list = [nodes[k] for k in sorted(nodes)]
    edge_list = []
    for k in sorted(edges):
        ed = edges[k]
        edge_list.append({**ed, "source_records": sorted(ed["source_records"])})
    return node_list, edge_list, n_records


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "exports" / "drugmechdb_kgx.json"))
    ap.add_argument("--stats", action="store_true", help="print counts only; write nothing")
    args = ap.parse_args()

    nodes, edges, n_records = build()

    if args.stats:
        cats: dict[str, int] = {}
        for n in nodes:
            cats[n["category"]] = cats.get(n["category"], 0) + 1
        print(f"{n_records} records -> {len(nodes)} nodes, {len(edges)} edges")
        for c, n in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"  {n:>6}  {c}")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps({"nodes": nodes, "edges": edges}, indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {out} — {len(nodes)} nodes, {len(edges)} edges from {n_records} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
