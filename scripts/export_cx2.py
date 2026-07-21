"""
Export the DrugMechDB corpus to a Cytoscape CX2 network (JSON).

CX2 is the Cytoscape Exchange format used by Cytoscape / NDEx to interchange networks. A
CX2 document is an ordered JSON array of "aspect" objects (descriptor, metadata, attribute
declarations, nodes, edges, status). This emits one such array for the whole corpus.

- Nodes are deduped by CURIE across all records; the Biolink `category` = `biolink:<node label>`
  and the original CURIE is kept as the `curie` attribute.
- Edges are deduped by (source, predicate, target); the `interaction` = `biolink:<snake_case key>`.
- CX2 requires **integer** node/edge ids, so each CURIE is assigned a stable integer id (a
  CURIE -> int map, ordered by sorted CURIE) and edges reference nodes by those integers.

Read-only on the corpus — it never modifies kb/paths. Node CURIEs are emitted verbatim
from the corpus; Biolink-standard prefix normalization (e.g. UniProt -> UniProtKB) is a
deliberate separate follow-up, not done here. Dependency-free: no `cx2`/`ndex` package required.

Usage:
    python scripts/export_cx2.py                 # -> exports/drugmechdb_cx2.cx2
    python scripts/export_cx2.py --out PATH
    python scripts/export_cx2.py --stats          # print counts only, write nothing
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
        for n in (doc.get("nodes") or []):
            nid = n.get("id")
            if not nid:
                continue
            if nid not in nodes:
                nodes[nid] = {"curie": nid, "category": biolink_category(n.get("label")),
                              "name": n.get("name")}
        for e in (doc.get("links") or []):
            s, o = e.get("source"), e.get("target")
            if not (s and o):
                continue
            p = biolink_predicate(e.get("key"))
            if (s, p, o) not in edges:
                edges[(s, p, o)] = {"source": s, "predicate": p, "target": o}

    # CX2 requires integer ids: assign a stable int to each CURIE (sorted for determinism).
    id_map = {curie: i for i, curie in enumerate(sorted(nodes))}
    node_list = []
    for curie in sorted(nodes):
        nd = nodes[curie]
        node_list.append({"id": id_map[curie],
                           "v": {"name": nd["name"], "category": nd["category"],
                                 "curie": nd["curie"]}})
    edge_list = []
    for i, k in enumerate(sorted(edges)):
        ed = edges[k]
        edge_list.append({"id": i, "s": id_map[ed["source"]], "t": id_map[ed["target"]],
                          "v": {"interaction": ed["predicate"]}})
    return node_list, edge_list, n_records


def to_cx2(node_list: list[dict], edge_list: list[dict]) -> list[dict]:
    # CX2 = ordered array of aspect objects: descriptor, metadata, attribute declarations,
    # nodes, edges, status.
    return [
        {"CXVersion": "2.0", "hasFragments": False},
        {"metaData": [{"name": "nodes", "elementCount": len(node_list)},
                      {"name": "edges", "elementCount": len(edge_list)}]},
        {"attributeDeclarations": [{"nodes": {"name": {"d": "string"},
                                              "category": {"d": "string"},
                                              "curie": {"d": "string"}},
                                    "edges": {"interaction": {"d": "string"}}}]},
        {"nodes": node_list},
        {"edges": edge_list},
        {"status": [{"error": "", "success": True}]},
    ]


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(REPO / "exports" / "drugmechdb_cx2.cx2"))
    ap.add_argument("--stats", action="store_true", help="print counts only; write nothing")
    args = ap.parse_args()

    nodes, edges, n_records = build()

    if args.stats:
        cats: dict[str, int] = {}
        for n in nodes:
            c = n["v"]["category"]
            cats[c] = cats.get(c, 0) + 1
        print(f"{n_records} records -> {len(nodes)} nodes, {len(edges)} edges")
        for c, n in sorted(cats.items(), key=lambda x: -x[1]):
            print(f"  {n:>6}  {c}")
        return 0

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(to_cx2(nodes, edges), indent=2, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"Wrote {out} — {len(nodes)} nodes, {len(edges)} edges from {n_records} records.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
