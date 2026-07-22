"""
Coverage for the enforced curation gate (scripts/quality/gate.py).

The gate combines the QC gate (Layers 1-4) with the deterministic structural
checks into ONE curator-facing verdict. Tested purely deterministically
(run_critic=False, backend=None) — no LLM, no network. The load-bearing
behaviours:

  1. PASS   — a clean path (QC clean + no structural flags) passes.
  2. RE_CURATE — a HARD structural flag bounces the path even when QC passes.
  3. UNION  — when BOTH a QC layer and a structural check fail, the single
     feedback report carries BOTH sets of problems (no short-circuit): the gate
     runs the structural checks even though QC already failed, so the curator
     sees everything at once.

Everything is crafted under tmp_path; kb/paths is never touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts" / "quality"))

import gate  # noqa: E402

DRUG = "MESH:D001241"
PROT = "UniProt:P1"
PROC = "GO:0000001"
DIS = "MESH:D000999"


def _node(i, label, name="n"):
    return {"id": i, "name": name, "label": label}


def _edge(s, t, k):
    return {"source": s, "target": t, "key": k}


def _write(tmp_path, doc, name="rec.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p


def _doc(nodes, links):
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": "GATE_TEST_1", "drug": "d", "disease": "e",
                  "drug_mesh": DRUG, "disease_mesh": DIS},
        "nodes": nodes, "links": links,
    }


def _clean_doc():
    return _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"),
         _node(PROC, "BiologicalProcess"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, PROC, "positively regulates"),
         _edge(PROC, DIS, "causes")],
    )


def _gate(path):
    return gate.run_gate(str(path), backend=None, run_critic=False, offline=True)


# ─── PASS on a clean path ────────────────────────────────────────────────────

def test_clean_path_passes(tmp_path):
    passed, fb = _gate(_write(tmp_path, _clean_doc()))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.qc_failures == []
    assert fb.hard_structural == []
    assert fb.soft_structural == []
    assert fb.record_id == "GATE_TEST_1"
    assert "No blocking problems" in fb.render()


# ─── RE_CURATE on a HARD structural flag (QC clean) ──────────────────────────

def test_hard_structural_flag_bounces(tmp_path):
    # drug's only target is the disease itself -> direct_drug_disease (HARD).
    # QC still passes: valid schema, canonical MESH prefixes, enum predicate.
    doc = _doc([_node(DRUG, "Drug"), _node(DIS, "Disease")],
               [_edge(DRUG, DIS, "causes")])
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is False
    assert fb.verdict == "RE_CURATE"
    assert fb.qc_failures == [], "QC should be clean; the bounce is purely structural"
    hard_codes = {f["code"] for f in fb.hard_structural}
    assert "direct_drug_disease" in hard_codes
    rendered = fb.render()
    assert "HARD structural failures" in rendered
    assert "BOUNCE" in rendered


# ─── UNION: both a QC failure and a structural failure are reported together ─

def test_union_reports_qc_and_structural_together(tmp_path):
    # A non-enum predicate fails QC (Layers 1 schema-enum + 3 predicate); the same
    # edge duplicated raises the HARD structural duplicate_edge flag. The gate must
    # NOT short-circuit on the QC failure — both must appear in one report.
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "frobnicates wildly"),
         _edge(DRUG, PROT, "frobnicates wildly"),   # duplicate -> HARD structural
         _edge(PROT, DIS, "causes")],
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is False
    assert fb.verdict == "RE_CURATE"

    # QC side present ...
    assert fb.qc_failures, "expected at least one QC layer failure"
    failing_layers = {f.get("layer") for f in fb.qc_failures}
    assert 3 in failing_layers or 1 in failing_layers

    # ... AND structural side present in the SAME report
    hard_codes = {f["code"] for f in fb.hard_structural}
    assert "duplicate_edge" in hard_codes

    rendered = fb.render()
    assert "QC gate failures" in rendered
    assert "HARD structural failures" in rendered

    d = fb.to_dict()
    assert d["verdict"] == "RE_CURATE"
    assert d["qc_failures"] and d["hard_structural"]


# ─── a SOFT-only path is not hard-bounced (deterministic gate) ───────────────

def test_soft_only_is_not_hard_bounced(tmp_path):
    # A net-positive polarity raises the SOFT net_polarity critic flag; QC is clean
    # and no HARD flag fires. With no critic backend the deterministic gate does NOT
    # hard-bounce (SOFT never blocks) — it passes but marks the flag unadjudicated.
    doc = _doc([_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
               [_edge(DRUG, PROT, "increases activity of"),   # +1
                _edge(PROT, DIS, "causes")])                  # +1 -> net positive
    passed, fb = _gate(_write(tmp_path, doc))
    assert fb.qc_failures == []
    assert fb.hard_structural == []
    soft_codes = {f["code"] for f in fb.soft_structural}
    assert "net_polarity" in soft_codes              # a SOFT-critic flag was surfaced
    assert soft_codes <= {"net_polarity", "type_violation"}
    assert fb.verdict == "PASS_SOFT_UNADJUDICATED"
    assert passed is True
