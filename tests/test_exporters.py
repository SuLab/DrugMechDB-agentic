"""
Coverage for the KGX and CX2 exporters (scripts/export_kgx.py, export_cx2.py).

Both build a whole-corpus graph by globbing kb/paths/. The tests point each
exporter's PATHS_DIR at a scratch corpus of crafted records (monkeypatched) so
the assertions are exact and hermetic. What is proven:

  * dedup — a node shared across records collapses to ONE node; an edge shared
    across records collapses to ONE edge that records BOTH source records.
  * Biolink mapping — node label -> biolink:<Category>, predicate key ->
    biolink:<snake_case>, with the documented fallbacks.
  * malformed-input guard — a node with no id and an edge with a missing
    endpoint are dropped, not exported as null-keyed junk.
  * CX2 shape — integer node ids, edges referencing them, the aspect wrapper.

Nothing is written to the repo; --stats/build() only read the scratch dir.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import export_kgx  # noqa: E402
import export_cx2  # noqa: E402

# Two well-formed records + one malformed record, sharing node MESH:D1/UniProt:P1
# and the edge MESH:D1 --decreases activity of--> UniProt:P1.
REC1 = {
    "graph": {"_id": "R1"},
    "nodes": [
        {"id": "MESH:D1", "name": "Drug1", "label": "Drug"},
        {"id": "UniProt:P1", "name": "Prot1", "label": "Protein"},
        {"id": "MESH:D2", "name": "Dis1", "label": "Disease"},
    ],
    "links": [
        {"source": "MESH:D1", "target": "UniProt:P1", "key": "decreases activity of"},
        {"source": "UniProt:P1", "target": "MESH:D2", "key": "causes"},
    ],
}
REC2 = {
    "graph": {"_id": "R2"},
    "nodes": [
        {"id": "MESH:D1", "name": "Drug1", "label": "Drug"},        # dup node
        {"id": "UniProt:P1", "name": "Prot1", "label": "Protein"},  # dup node
        {"id": "MESH:D3", "name": "Dis2", "label": "Disease"},
    ],
    "links": [
        {"source": "MESH:D1", "target": "UniProt:P1", "key": "decreases activity of"},  # dup edge
        {"source": "UniProt:P1", "target": "MESH:D3", "key": "contributes to"},
    ],
}
REC_MALFORMED = {
    "graph": {"_id": "R3"},
    "nodes": [
        {"name": "NoId", "label": "Protein"},                        # missing id -> dropped
        {"id": "UniProt:P9", "name": "Prot9", "label": "Protein"},
    ],
    "links": [
        {"source": "UniProt:P9", "key": "causes"},                   # missing target -> dropped
        {"source": "UniProt:P9", "target": "MESH:D2", "key": "causes"},
    ],
}


@pytest.fixture
def corpus(tmp_path):
    d = tmp_path / "paths"
    d.mkdir()
    for name, rec in (("R1", REC1), ("R2", REC2), ("R3", REC_MALFORMED)):
        (d / f"{name}.yaml").write_text(yaml.safe_dump(rec), encoding="utf-8")
    # a generated index file that both exporters must ignore
    (d / "_index.yaml").write_text("- id: R1\n", encoding="utf-8")
    return d


# ─── pure Biolink-mapping functions (both exporters share the same contract) ──

@pytest.mark.parametrize("mod", [export_kgx, export_cx2])
def test_biolink_category_mapping(mod):
    assert mod.biolink_category("Protein") == "biolink:Protein"
    assert mod.biolink_category("Drug") == "biolink:Drug"
    assert mod.biolink_category("") == "biolink:NamedThing"       # empty fallback
    assert mod.biolink_category(None) == "biolink:NamedThing"


@pytest.mark.parametrize("mod", [export_kgx, export_cx2])
def test_biolink_predicate_mapping(mod):
    assert mod.biolink_predicate("decreases activity of") == "biolink:decreases_activity_of"
    assert mod.biolink_predicate("causes") == "biolink:causes"
    assert mod.biolink_predicate("") == "biolink:related_to"      # empty fallback
    assert mod.biolink_predicate(None) == "biolink:related_to"


# ─── KGX ─────────────────────────────────────────────────────────────────────

def test_kgx_counts_and_dedup(corpus, monkeypatch):
    monkeypatch.setattr(export_kgx, "PATHS_DIR", corpus)
    nodes, edges, n_records = export_kgx.build()

    assert n_records == 3   # _index.yaml excluded
    # nodes: MESH:D1, UniProt:P1, MESH:D2, MESH:D3, UniProt:P9  (the no-id node dropped)
    ids = {n["id"] for n in nodes}
    assert ids == {"MESH:D1", "UniProt:P1", "MESH:D2", "MESH:D3", "UniProt:P9"}
    assert len(nodes) == 5

    edge_keys = {(e["subject"], e["predicate"], e["object"]) for e in edges}
    assert ("MESH:D1", "biolink:decreases_activity_of", "UniProt:P1") in edge_keys
    assert ("UniProt:P9", "biolink:causes", "MESH:D2") in edge_keys
    # the edge missing a target is dropped
    assert len(edges) == 4


def test_kgx_category_and_shared_edge_records(corpus, monkeypatch):
    monkeypatch.setattr(export_kgx, "PATHS_DIR", corpus)
    nodes, edges, _ = export_kgx.build()
    by_id = {n["id"]: n for n in nodes}
    assert by_id["UniProt:P1"]["category"] == "biolink:Protein"
    assert by_id["MESH:D1"]["category"] == "biolink:Drug"

    shared = next(e for e in edges
                  if (e["subject"], e["object"]) == ("MESH:D1", "UniProt:P1"))
    # the deduped edge remembers BOTH records it came from
    assert shared["source_records"] == ["R1", "R2"]
    assert shared["knowledge_source"] == export_kgx.KNOWLEDGE_SOURCE


def test_kgx_no_null_keyed_junk(corpus, monkeypatch):
    monkeypatch.setattr(export_kgx, "PATHS_DIR", corpus)
    nodes, edges, _ = export_kgx.build()
    assert all(n["id"] for n in nodes)                    # no id=None node
    assert all(e["subject"] and e["object"] for e in edges)


# ─── CX2 ─────────────────────────────────────────────────────────────────────

def test_cx2_counts_and_integer_ids(corpus, monkeypatch):
    monkeypatch.setattr(export_cx2, "PATHS_DIR", corpus)
    nodes, edges, n_records = export_cx2.build()

    assert n_records == 3
    assert len(nodes) == 5 and len(edges) == 4
    # CX2 requires integer node ids, contiguous from 0
    node_ids = sorted(n["id"] for n in nodes)
    assert node_ids == list(range(5))
    assert all(isinstance(n["id"], int) for n in nodes)

    # every edge references real integer node ids
    valid = set(node_ids)
    for e in edges:
        assert e["s"] in valid and e["t"] in valid
        assert isinstance(e["s"], int) and isinstance(e["t"], int)

    # curie + category preserved on nodes; interaction is the biolink predicate
    curie_to_cat = {n["v"]["curie"]: n["v"]["category"] for n in nodes}
    assert curie_to_cat["UniProt:P1"] == "biolink:Protein"
    interactions = {e["v"]["interaction"] for e in edges}
    assert "biolink:decreases_activity_of" in interactions


def test_cx2_aspect_wrapper(corpus, monkeypatch):
    monkeypatch.setattr(export_cx2, "PATHS_DIR", corpus)
    nodes, edges, _ = export_cx2.build()
    doc = export_cx2.to_cx2(nodes, edges)
    assert doc[0]["CXVersion"] == "2.0"
    meta = {m["name"]: m["elementCount"] for m in doc[1]["metaData"]}
    assert meta == {"nodes": 5, "edges": 4}
    names = set().union(*[set(a) for a in doc])
    assert {"nodes", "edges", "attributeDeclarations", "status"} <= names
    assert doc[-1]["status"][0]["success"] is True
