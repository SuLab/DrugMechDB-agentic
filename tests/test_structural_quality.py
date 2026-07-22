"""
Per-check coverage for scripts/quality/structural_quality.py.

structural_quality is the deterministic post-QC scorer whose flags drive the
enforced gate (HARD_BLOCKING_CHECKS vs SOFT_CRITIC_CHECKS). Every check gets:

  * a POSITIVE case — a crafted path that SHOULD raise the flag, asserting the
    exact `code` and `severity`; and
  * a NEGATIVE control — a clean path that must NOT raise it.

The negative controls are load-bearing: they prove a check is *specific*, not a
constant "always fires". The clean base (`_clean`) below is flag-free (verified),
so an absent flag in a control is meaningful, and a spurious flag would fail.

All crafted; no corpus file is read.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "quality"))

import structural_quality as sq  # noqa: E402

LEX = sq.load_lexicon()

DRUG = "MESH:D001241"
PROT = "UniProt:P1"
PROT2 = "UniProt:P2"
PROC = "GO:0000001"
CHEM = "MESH:C000001"
DIS = "MESH:D000999"


def _node(i, label, name="n"):
    return {"id": i, "name": name, "label": label}


def _edge(s, t, k):
    return {"source": s, "target": t, "key": k}


def _doc(nodes, links, drug=DRUG, disease=DIS):
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": "X_1", "drug": "d", "disease": "e",
                  "drug_mesh": drug, "disease_mesh": disease},
        "nodes": nodes, "links": links,
    }


def _analyze(tmp_path, doc, name="p.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc), encoding="utf-8")
    return sq.analyze(p, LEX)


def _codes(res) -> set:
    return {(f["severity"], f["code"]) for f in res["flags"]}


def _flag(res, code):
    for f in res["flags"]:
        if f["code"] == code:
            return f
    return None


# The clean, coherent, in-range mechanism used as every negative control.
def _clean_doc():
    return _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"),
         _node(PROC, "BiologicalProcess"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, PROC, "positively regulates"),
         _edge(PROC, DIS, "causes")],
    )


def test_clean_base_is_flag_free(tmp_path):
    """Guard on the negative control itself — if this ever flags, every 'absent'
    assertion below would be meaningless."""
    res = _analyze(tmp_path, _clean_doc())
    assert res["flags"] == []
    assert res["clean"] is True and res["clean_hard"] is True
    assert res["polarity"] == "coherent"


# ─── connectivity (HARD) ─────────────────────────────────────────────────────

def test_connectivity_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "decreases activity of")])   # never reaches disease
    res = _analyze(tmp_path, doc)
    assert ("HARD", "connectivity") in _codes(res)
    assert res["n_paths"] == 0


def test_connectivity_negative(tmp_path):
    assert ("HARD", "connectivity") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── cycle (HARD) ────────────────────────────────────────────────────────────

def test_cycle_positive(tmp_path):
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(PROT2, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, PROT2, "positively regulates"),
         _edge(PROT2, DIS, "causes"),
         _edge(PROT2, PROT, "positively regulates")],   # PROT <-> PROT2 cycle
    )
    assert ("HARD", "cycle") in _codes(_analyze(tmp_path, doc))


def test_cycle_negative(tmp_path):
    assert ("HARD", "cycle") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── duplicate_edge (HARD) ───────────────────────────────────────────────────

def test_duplicate_edge_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "decreases activity of"),
                _edge(DRUG, PROT, "decreases activity of"),   # identical repeat
                _edge(PROT, DIS, "causes")])
    res = _analyze(tmp_path, doc)
    assert ("HARD", "duplicate_edge") in _codes(res)
    assert "repeated" in _flag(res, "duplicate_edge")["msg"]


def test_duplicate_edge_negative(tmp_path):
    assert ("HARD", "duplicate_edge") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── short_circuit (HARD) ────────────────────────────────────────────────────

def test_short_circuit_positive(tmp_path):
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(PROC, "BiologicalProcess"), _node(DIS, "Disease")],
        [_edge(DRUG, DIS, "causes"),                       # 1-edge bypass
         _edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, PROC, "positively regulates"),
         _edge(PROC, DIS, "causes")],                      # 3-edge full mechanism
    )
    res = _analyze(tmp_path, doc)
    assert ("HARD", "short_circuit") in _codes(res)
    assert res["n_paths"] >= 2


def test_short_circuit_negative(tmp_path):
    assert ("HARD", "short_circuit") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── clinical_shortcut (HARD) ────────────────────────────────────────────────

def test_clinical_shortcut_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "decreases activity of"),
                _edge(PROT, DIS, "causes"),
                _edge(DRUG, DIS, "treats")])   # clinical-outcome edge drug->disease
    res = _analyze(tmp_path, doc)
    assert ("HARD", "clinical_shortcut") in _codes(res)
    assert "treats" in _flag(res, "clinical_shortcut")["msg"]


def test_clinical_shortcut_negative(tmp_path):
    assert ("HARD", "clinical_shortcut") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── direct_drug_disease (HARD) ──────────────────────────────────────────────

def test_direct_drug_disease_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(DIS, "Disease")],
               [_edge(DRUG, DIS, "causes")])   # drug's only target IS the disease
    res = _analyze(tmp_path, doc)
    assert ("HARD", "direct_drug_disease") in _codes(res)


def test_direct_drug_disease_negative(tmp_path):
    # clean base begins drug -> Protein, so the drug has a molecular entry point
    assert ("HARD", "direct_drug_disease") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── type_violation (SOFT) ───────────────────────────────────────────────────

def test_type_violation_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "decreases activity of"),
                _edge(PROT, DIS, "increases activity of")])   # object is a Disease, not activity-bearing
    res = _analyze(tmp_path, doc)
    assert ("SOFT", "type_violation") in _codes(res)
    assert "Disease" in _flag(res, "type_violation")["msg"]


def test_type_violation_negative(tmp_path):
    assert ("SOFT", "type_violation") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── net_polarity (SOFT) ─────────────────────────────────────────────────────

def test_net_polarity_incoherent_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "increases activity of"),   # +1
                _edge(PROT, DIS, "causes")])                  # +1 -> net POSITIVE
    res = _analyze(tmp_path, doc)
    assert ("SOFT", "net_polarity") in _codes(res)
    assert res["polarity"] == "incoherent"
    assert "POSITIVE" in _flag(res, "net_polarity")["msg"]


def test_net_polarity_indeterminate_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "is metabolite of"),   # role: reverse -> indeterminate
                _edge(PROT, DIS, "causes")])
    res = _analyze(tmp_path, doc)
    assert ("SOFT", "net_polarity") in _codes(res)
    assert res["polarity"] == "indeterminate"


def test_net_polarity_negative(tmp_path):
    # clean base nets negative (coherent) -> no net_polarity flag
    assert ("SOFT", "net_polarity") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── noncanonical_start (INFO) ───────────────────────────────────────────────

def test_noncanonical_start_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(CHEM, "ChemicalSubstance"), _node(DIS, "Disease")],
               [_edge(DRUG, CHEM, "decreases abundance of"),   # first target not a Protein
                _edge(CHEM, DIS, "causes")])
    assert ("INFO", "noncanonical_start") in _codes(_analyze(tmp_path, doc))


def test_noncanonical_start_negative(tmp_path):
    assert ("INFO", "noncanonical_start") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── length_out_of_range (SOFT) ──────────────────────────────────────────────

def test_length_out_of_range_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "decreases activity of"),
                _edge(PROT, DIS, "causes")])   # 2 links, below the 3-7 window
    res = _analyze(tmp_path, doc)
    assert ("SOFT", "length_out_of_range") in _codes(res)
    assert "2 links" in _flag(res, "length_out_of_range")["msg"]


def test_length_out_of_range_negative(tmp_path):
    # clean base has 3 links (in range)
    assert ("SOFT", "length_out_of_range") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── dangling_node (SOFT) ────────────────────────────────────────────────────

def test_dangling_node_positive(tmp_path):
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(PROC, "BiologicalProcess"),
         _node(DIS, "Disease"), _node(PROT2, "Protein")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, PROC, "positively regulates"),
         _edge(PROC, DIS, "causes"),
         _edge(PROT, PROT2, "positively regulates")],   # PROT2 leads nowhere -> dangling
    )
    res = _analyze(tmp_path, doc)
    assert ("SOFT", "dangling_node") in _codes(res)
    assert PROT2 in _flag(res, "dangling_node")["msg"]


def test_dangling_node_negative(tmp_path):
    assert ("SOFT", "dangling_node") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── unknown_predicate (SOFT) ────────────────────────────────────────────────

def test_unknown_predicate_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(PROC, "BiologicalProcess"),
                _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "frobnicates wildly"),   # not in the polarity lexicon
                _edge(PROT, PROC, "positively regulates"),
                _edge(PROC, DIS, "causes")])
    res = _analyze(tmp_path, doc)
    assert ("SOFT", "unknown_predicate") in _codes(res)
    assert "frobnicates wildly" in _flag(res, "unknown_predicate")["msg"]


def test_unknown_predicate_negative(tmp_path):
    assert ("SOFT", "unknown_predicate") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── review_predicate (INFO) ─────────────────────────────────────────────────

def test_review_predicate_positive(tmp_path):
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "decreases response to"),   # confidence: review, sign -1
                _edge(PROT, DIS, "causes")])
    res = _analyze(tmp_path, doc)
    assert ("INFO", "review_predicate") in _codes(res)


def test_review_predicate_negative(tmp_path):
    # clean base composes only high-confidence predicates
    assert ("INFO", "review_predicate") not in _codes(_analyze(tmp_path, _clean_doc()))


# ─── severity taxonomy is internally consistent with the gate's classifier ───

def test_positive_flags_agree_with_gate_severity_sets(tmp_path):
    """Every HARD flag code this module emits must be in HARD_BLOCKING_CHECKS, and
    the two SOFT-critic codes must be in SOFT_CRITIC_CHECKS — the sets gate.py keys
    its disposition off. A drift between severity label and set membership would be
    a real bug; this pins them together."""
    # one doc that triggers a representative HARD + SOFT + INFO mix
    hard_doc = _doc([_node(DRUG, "Drug"), _node(DIS, "Disease")],
                    [_edge(DRUG, DIS, "causes")])   # direct_drug_disease HARD
    res = _analyze(tmp_path, hard_doc)
    for f in res["flags"]:
        if f["severity"] == "HARD":
            assert f["code"] in sq.HARD_BLOCKING_CHECKS
    # net_polarity / type_violation are the SOFT-critic set
    assert sq.SOFT_CRITIC_CHECKS == {"net_polarity", "type_violation"}
    tv = _analyze(tmp_path, _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"), _edge(PROT, DIS, "increases activity of")]))
    assert _flag(tv, "type_violation")["severity"] == "SOFT"
    assert "type_violation" in sq.SOFT_CRITIC_CHECKS
