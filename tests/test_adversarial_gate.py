"""
Adversarial / red-team coverage for the enforced gate and the evidence layer.

This is a deliberate attack suite, split into two halves that together lock in
the two properties the gate promises:

#51 — GATE INTEGRITY (negative + positive controls).
    For EACH of the four HARD structural invariants
    (structural_quality.HARD_BLOCKING_CHECKS = connectivity / cycle /
    duplicate_edge / clinical_shortcut) a minimal crafted path is built that
    triggers exactly that invariant, and the gate is asserted to BOUNCE
    (verdict RE_CURATE). A clean minimal path is asserted to PASS.

    Crucially, the suite also proves the demotion refactor holds: paths that
    trigger the FOUR DEMOTED checks (short_circuit, net_polarity,
    type_violation, direct_drug_disease) — the ones found to over-fire on the
    gold-standard legacy corpus — must NOT bounce. They may only appear as
    advisory INFO while the verdict stays PASS. This is the regression guard
    that keeps the four noisy checks out of the gate. The contraindication
    special-case (a 'contraindicated for' drug->disease edge must NOT fire
    clinical_shortcut) is checked too.

#52 — SNIPPET-FABRICATION RED-TEAM (evidence layer / QC Layer 4).
    An ai_curated path with a per-edge EvidenceItem is checked against a
    scratch reference cache this test writes itself (via
    evidence_sources.common.write_cache / cache_filename, with DMDB_CACHE_DIR
    pointed at the scratch dir). A snippet that is a VERBATIM substring of the
    cached source PASSES; a FABRICATED snippet and a PARAPHRASED snippet (both
    absent from the source) FAIL. This proves Layer 4 cannot be fooled by an
    agent inventing or rewording evidence text.

Everything is crafted under tmp_path / a scratch cache and runs OFFLINE — no
network, no API, and nothing under kb/ or references_cache/ is read or written.
"""

from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"

# gate.py lives in scripts/quality and imports its siblings by that path.
sys.path.insert(0, str(REPO / "scripts" / "quality"))
sys.path.insert(0, str(SCRIPTS))

import gate  # noqa: E402
import structural_quality  # noqa: E402
from evidence_sources import common  # noqa: E402


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ── CURIEs (canonical prefix per Biolink label so QC Layers 1-3 stay clean) ───
DRUG = "MESH:D001241"
PROT = "UniProt:P1"
PROT2 = "UniProt:P2"
PROC = "GO:0000001"
DIS = "MESH:D000999"


def _node(i, label, name="n"):
    return {"id": i, "name": name, "label": label}


def _edge(s, t, k):
    return {"source": s, "target": t, "key": k}


def _doc(nodes, links, _id="ADV_TEST"):
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": _id, "drug": "d", "disease": "e",
                  "drug_mesh": DRUG, "disease_mesh": DIS},
        "nodes": nodes, "links": links,
    }


def _write(tmp_path, doc, name="rec.yaml"):
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p


def _gate(path):
    """Purely deterministic gate: no LLM critic, no network (offline QC)."""
    return gate.run_gate(str(path), backend=None, run_critic=False, offline=True)


def _codes(flags):
    return {f["code"] for f in flags}


# =============================================================================
# #51 — GATE INTEGRITY: the four HARD invariants each bounce (negative control)
# =============================================================================

def test_hard_connectivity_bounces(tmp_path):
    # Drug reaches only PROT (dead end); DIS is reachable only from PROT2, which
    # the drug never reaches -> NO drug->disease path -> connectivity (HARD).
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"),
         _node(PROT2, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT2, DIS, "causes")],
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is False
    assert fb.verdict == "RE_CURATE"
    assert "connectivity" in _codes(fb.hard_structural)
    # purely structural: schema / prefixes / predicates are all valid.
    assert fb.qc_failures == []


def test_hard_cycle_bounces(tmp_path):
    # A self-loop on PROT is a directed cycle -> cycle (HARD). A clean
    # drug->disease route still exists, so connectivity does NOT fire.
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, DIS, "causes"),
         _edge(PROT, PROT, "positively regulates")],   # self-loop -> cycle
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is False
    assert fb.verdict == "RE_CURATE"
    assert "cycle" in _codes(fb.hard_structural)
    assert fb.qc_failures == []


def test_hard_duplicate_edge_bounces(tmp_path):
    # The exact same (source, predicate, object) triple twice -> duplicate_edge (HARD).
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(DRUG, PROT, "decreases activity of"),   # duplicate triple
         _edge(PROT, DIS, "causes")],
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is False
    assert fb.verdict == "RE_CURATE"
    assert "duplicate_edge" in _codes(fb.hard_structural)
    assert fb.qc_failures == []
    assert "remove the duplicated edge" in fb.render()


def test_hard_clinical_shortcut_bounces(tmp_path):
    # A therapeutic Drug --treats--> Disease edge laid on top of a longer
    # mechanism chain is a clinical shortcut -> clinical_shortcut (HARD).
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, DIS, "causes"),
         _edge(DRUG, DIS, "treats")],                  # shortcut over the chain
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is False
    assert fb.verdict == "RE_CURATE"
    assert "clinical_shortcut" in _codes(fb.hard_structural)
    assert "remove the redundant drug -> disease" in fb.render()


# ─── positive control: a clean minimal path PASSES ───────────────────────────

def test_clean_minimal_path_passes(tmp_path):
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"),
         _node(PROC, "BiologicalProcess"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, PROC, "positively regulates"),
         _edge(PROC, DIS, "causes")],
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.qc_failures == []
    assert fb.hard_structural == []
    assert fb.advisory == []


# =============================================================================
# #51 — the refactor holds: the FOUR DEMOTED checks must NOT gate.
# Each triggers exactly its (now advisory) INFO flag; the gate still PASSES.
# =============================================================================

def test_demoted_short_circuit_does_not_bounce(tmp_path):
    # Convergent-branch shape: a 2-edge branch (Drug->PROT->DIS) beside a 3-edge
    # branch (Drug->PROT->PROC->DIS). Legitimate convergence over-fires the old
    # short_circuit heuristic; it is now advisory INFO only.
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"),
         _node(PROC, "BiologicalProcess"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, DIS, "causes"),                     # short 2-edge branch
         _edge(PROT, PROC, "positively regulates"),
         _edge(PROC, DIS, "causes")],                    # long 3-edge branch
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.hard_structural == []
    assert "short_circuit" in _codes(fb.advisory)


def test_demoted_net_polarity_does_not_bounce(tmp_path):
    # Every determinable branch nets POSITIVE (drug appears NOT to suppress the
    # disease). net_polarity is advisory INFO now, never a bounce.
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "increases activity of"),     # +1
         _edge(PROT, DIS, "causes")],                    # +1 -> net positive
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.hard_structural == []
    assert "net_polarity" in _codes(fb.advisory)


def test_demoted_type_violation_does_not_bounce(tmp_path):
    # 'decreases activity of' requires an activity-bearing object; pointing it at
    # a Disease node violates the predicate's domain/range. type_violation is
    # advisory INFO now, never a bounce.
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, DIS, "decreases activity of")],     # activity predicate -> Disease
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.hard_structural == []
    assert "type_violation" in _codes(fb.advisory)


def test_demoted_direct_drug_disease_does_not_bounce(tmp_path):
    # The drug's only target is the disease itself (no molecular entry point).
    # direct_drug_disease is advisory INFO now, never a bounce. (A non-therapeutic
    # predicate is used so clinical_shortcut is not in play.)
    doc = _doc(
        [_node(DRUG, "Drug"), _node(DIS, "Disease")],
        [_edge(DRUG, DIS, "causes")],                    # drug -> disease, molecular-free
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.hard_structural == []
    assert "direct_drug_disease" in _codes(fb.advisory)


def test_contraindicated_edge_does_not_fire_clinical_shortcut(tmp_path):
    # A 'contraindicated for' drug->disease edge is a documented special-case, NOT
    # a therapeutic shortcut. clinical_shortcut (which fires only on
    # treats/prevents/ameliorates) must NOT fire, and the path must PASS.
    doc = _doc(
        [_node(DRUG, "Drug"), _node(PROT, "Protein"), _node(DIS, "Disease")],
        [_edge(DRUG, PROT, "decreases activity of"),
         _edge(PROT, DIS, "causes"),
         _edge(DRUG, DIS, "contraindicated for")],       # special-case, not a shortcut
    )
    passed, fb = _gate(_write(tmp_path, doc))
    assert passed is True
    assert fb.verdict == "PASS"
    assert fb.hard_structural == []
    # clinical_shortcut appears NOWHERE — not as a bounce and not even as advisory.
    all_codes = _codes(fb.hard_structural) | _codes(fb.advisory)
    assert "clinical_shortcut" not in all_codes


def test_hard_blocking_set_is_exactly_the_four_invariants():
    # Locks the single point of truth: only these four structural checks gate.
    assert structural_quality.HARD_BLOCKING_CHECKS == frozenset(
        {"connectivity", "cycle", "duplicate_edge", "clinical_shortcut"}
    )


# =============================================================================
# #52 — SNIPPET-FABRICATION RED-TEAM (QC Layer 4, offline against a scratch cache)
# =============================================================================

# A tiny cached "source". The verbatim snippet below is an exact substring of it.
_SOURCE_ABSTRACT = (
    "Aspirin irreversibly inhibits cyclooxygenase-1 by acetylation of a serine "
    "residue, which decreases the synthesis of prostaglandins and thereby reduces "
    "platelet aggregation."
)
_VERBATIM_SNIPPET = "decreases the synthesis of prostaglandins"
_FABRICATED_SNIPPET = "aspirin activates the mTOR signaling cascade in neurons"
_PARAPHRASED_SNIPPET = "prostaglandin synthesis is lowered"   # reworded; not a substring
_REF_ID = "PMID:11111111"


def _ai_curated_doc(snippet: str) -> dict:
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": "ADV_L4_1", "drug": "TestDrug", "disease": "TestDisease",
                  "disease_mesh": DIS},
        "nodes": [
            _node(DRUG, "Drug", "TestDrug"),
            _node(PROT, "Protein", "TestProtein"),
        ],
        "links": [{
            "key": "decreases activity of", "source": DRUG, "target": PROT,
            "evidence": [{"reference": _REF_ID, "snippet": snippet,
                          "supports": "SUPPORT", "evidence_source": "IN_VITRO"}],
        }],
    }


@pytest.fixture
def scratch_cache(tmp_path):
    """A reference cache this test writes itself: DMDB_CACHE_DIR points here.

    The cache file is named by evidence_sources.common.cache_filename (the exact
    name QC Layer 4 recomputes), and its body is written by common.write_cache
    (the one sanctioned cache-shape writer) — so nothing under references_cache/
    is touched and the source text is never authored by the thing citing it."""
    cache = tmp_path / "cache"
    common.write_cache(
        _REF_ID,
        {"title": "Adversarial test source", "abstract": _SOURCE_ABSTRACT},
        content_type="abstract", cache_dir=cache,
    )
    # The file lands exactly where Layer 4 will look for this CURIE.
    assert (cache / common.cache_filename(_REF_ID)).is_file()
    return cache


def _l4_env(cache_dir: Path) -> dict:
    env = os.environ.copy()
    env["DMDB_CACHE_DIR"] = str(cache_dir)
    return env


def _run_validate_references(path: Path, env: dict) -> tuple[int, dict, str]:
    cmd = [_py(), str(SCRIPTS / "validate_references.py"), "--json", "--offline", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {}
    return proc.returncode, data, proc.stdout + proc.stderr


def _run_qc_layer4(path: Path, env: dict) -> tuple[int, dict, str]:
    cmd = [_py(), str(SCRIPTS / "qc.py"), "--json", "--layer", "4", "--offline", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {}
    return proc.returncode, data, proc.stdout + proc.stderr


def test_layer4_accepts_verbatim_snippet(tmp_path, scratch_cache):
    f = _write(tmp_path, _ai_curated_doc(_VERBATIM_SNIPPET))
    code, data, log = _run_validate_references(f, _l4_env(scratch_cache))
    assert code == 0, log
    assert data["files_with_evidence"] == 1
    assert data["files_failing"] == 0


def test_layer4_rejects_fabricated_snippet(tmp_path, scratch_cache):
    f = _write(tmp_path, _ai_curated_doc(_FABRICATED_SNIPPET))
    code, data, log = _run_validate_references(f, _l4_env(scratch_cache))
    assert code == 1, "a snippet absent from the cited source must FAIL Layer 4"
    assert data["files_failing"] == 1
    assert "not found as substring" in log.lower()


def test_layer4_rejects_paraphrased_snippet(tmp_path, scratch_cache):
    # Semantically faithful but reworded -> not a verbatim substring -> must FAIL.
    f = _write(tmp_path, _ai_curated_doc(_PARAPHRASED_SNIPPET))
    code, data, log = _run_validate_references(f, _l4_env(scratch_cache))
    assert code == 1, "a paraphrase that is not a verbatim substring must FAIL Layer 4"
    assert data["files_failing"] == 1
    assert "not found as substring" in log.lower()


def test_qc_orchestrator_layer4_verbatim_passes(tmp_path, scratch_cache):
    # Same verbatim snippet, but exercised through the QC orchestrator entry point
    # (qc.py --layer 4 --offline) to prove the source-agnostic cache lookup works
    # end-to-end from the gate's QC side, not just the layer script.
    f = _write(tmp_path, _ai_curated_doc(_VERBATIM_SNIPPET))
    code, data, log = _run_qc_layer4(f, _l4_env(scratch_cache))
    assert code == 0, log
    assert data["overall_pass"] is True


def test_qc_orchestrator_layer4_fabricated_fails(tmp_path, scratch_cache):
    f = _write(tmp_path, _ai_curated_doc(_FABRICATED_SNIPPET))
    code, data, log = _run_qc_layer4(f, _l4_env(scratch_cache))
    assert code == 1, "the QC orchestrator must fail Layer 4 on a fabricated snippet"
    assert data["overall_pass"] is False
