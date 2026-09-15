"""
Crafted VALID-vs-INVALID coverage for the four QC-layer scripts.

test_validation.py already asserts the layers pass on the real corpus + the
committed ai_curated fixtures. This file is the complementary *failing-path*
suite: for every layer it feeds a clean input (must PASS, exit 0) AND a
deliberately-broken input (must FAIL, exit 1) and asserts the layer names the
specific defect. The broken inputs are the point — they prove each layer
actually rejects the class of error it exists to catch:

  Layer 1 (schema)      — a record missing a required top-level key.
  Layer 2 (ontology)    — a mistyped CURIE (right node type, wrong prefix).
  Layer 3 (predicate)   — an edge key that is not a BiolinkPredicate.
  Layer 4 (references)  — a snippet that is not a verbatim substring of its
                          cited source (fabricated), checked against a cache
                          this test writes itself so it depends on no fixture.

Everything runs offline against scratch files; nothing under kb/ or
references_cache/ is read or written.
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


def _enum_size() -> int:
    """Size of the committed BiolinkPredicate enum — read, never hardcoded, because
    the enum spans two Biolink eras and grows when we adopt a new release's predicate."""
    import yaml
    schema = REPO / "src" / "drugmechdb" / "schema" / "biolink_predicates.yaml"
    return len(yaml.safe_load(schema.read_text())["enums"]["BiolinkPredicate"]["permissible_values"])
SCRIPTS = REPO / "scripts"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"

sys.path.insert(0, str(SCRIPTS))
from evidence_sources import common  # noqa: E402


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _run(script: str, *args: str, env: dict | None = None) -> tuple[int, dict, str]:
    cmd = [_py(), str(SCRIPTS / script), "--json", *args]
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    try:
        data = json.loads(proc.stdout)
    except json.JSONDecodeError:
        data = {}
    return proc.returncode, data, proc.stdout + proc.stderr


# A structurally clean, ontology-clean, predicate-clean legacy record. Reused as
# the VALID control for Layers 1-3.
def _clean_doc() -> dict:
    return {
        "directed": True,
        "multigraph": True,
        "graph": {
            "_id": "DBX_MESH_DX_1", "drug": "TestDrug", "disease": "TestDisease",
            "drug_mesh": "MESH:D001241", "disease_mesh": "MESH:D000001",
        },
        "nodes": [
            {"id": "MESH:D001241", "name": "TestDrug", "label": "Drug"},
            {"id": "UniProt:P23219", "name": "TestProtein", "label": "Protein"},
            {"id": "MESH:D000001", "name": "TestDisease", "label": "Disease"},
        ],
        "links": [
            {"key": "decreases activity of", "source": "MESH:D001241", "target": "UniProt:P23219"},
            {"key": "causes", "source": "UniProt:P23219", "target": "MESH:D000001"},
        ],
    }


def _write(tmp_path: Path, doc: dict, name: str = "rec.yaml") -> Path:
    p = tmp_path / name
    p.write_text(yaml.safe_dump(doc, sort_keys=False), encoding="utf-8")
    return p


# ─── Layer 1 — schema ────────────────────────────────────────────────────────

def test_layer1_valid_clean_record_passes(tmp_path):
    f = _write(tmp_path, _clean_doc())
    code, data, _ = _run("validate_schema.py", str(f))
    assert code == 0, data
    assert data["failure_count"] == 0


def test_layer1_rejects_record_missing_required_key(tmp_path):
    doc = _clean_doc()
    del doc["graph"]                       # `graph` is a required MechanisticPath slot
    f = _write(tmp_path, doc)
    code, data, _ = _run("validate_schema.py", str(f))
    assert code == 1, "Layer 1 must reject a record missing a required top-level key"
    assert data["failure_count"] >= 1
    msgs = " ".join(fl["message"] for fl in data["failures"]).lower()
    assert "graph" in msgs and "required" in msgs


def test_layer1_rejects_too_few_nodes(tmp_path):
    """nodes has minimum_cardinality 2 — a single-node record is invalid."""
    doc = _clean_doc()
    doc["nodes"] = [doc["nodes"][0]]
    doc["links"] = []                      # keep it about cardinality, links also required>=1
    f = _write(tmp_path, doc)
    code, data, _ = _run("validate_schema.py", str(f))
    assert code == 1
    assert data["failure_count"] >= 1


# ─── Layer 2 — node ontology (prefix ↔ label) ────────────────────────────────

def test_layer2_valid_clean_record_passes(tmp_path):
    f = _write(tmp_path, _clean_doc())
    code, data, _ = _run("validate_node_ontology.py", str(f))
    assert code == 0, data
    assert data["failure_count"] == 0


def test_layer2_rejects_mistyped_curie(tmp_path):
    """A Protein node carrying a MESH id (should be UniProt) is a mistyped CURIE."""
    doc = _clean_doc()
    doc["nodes"][1]["id"] = "MESH:D099999"       # Protein with a MESH prefix
    doc["links"][0]["target"] = "MESH:D099999"
    doc["links"][1]["source"] = "MESH:D099999"
    f = _write(tmp_path, doc)
    code, data, _ = _run("validate_node_ontology.py", str(f))
    assert code == 1, "Layer 2 must reject a prefix that is not canonical for the label"
    assert data["failure_count"] >= 1
    reasons = " ".join(fl["reason"] for fl in data["failures"]).lower()
    assert "not canonical" in reasons and "protein" in reasons


def test_layer2_rejects_invisible_char_in_id(tmp_path):
    """A zero-width character hidden in an id makes it fail to resolve while looking OK."""
    doc = _clean_doc()
    doc["nodes"][1]["id"] = "UniProt:P23219" + "\u200b"   # trailing zero-width space (U+200B)
    f = _write(tmp_path, doc)
    code, data, _ = _run("validate_node_ontology.py", str(f))
    assert code == 1
    reasons = " ".join(fl["reason"] for fl in data["failures"]).lower()
    assert "invisible" in reasons or "u+200b" in reasons


# ─── Layer 3 — predicate enum ────────────────────────────────────────────────

def test_layer3_valid_clean_record_passes(tmp_path):
    f = _write(tmp_path, _clean_doc())
    code, data, _ = _run("validate_predicates.py", str(f))
    assert code == 0, data
    assert data["failure_count"] == 0
    assert data["enum_size"] == _enum_size()   # not a literal: the enum grows with Biolink


def test_layer3_rejects_non_enum_predicate(tmp_path):
    doc = _clean_doc()
    doc["links"][0]["key"] = "modulates somehow"       # not a BiolinkPredicate
    f = _write(tmp_path, doc)
    code, data, _ = _run("validate_predicates.py", str(f))
    assert code == 1, "Layer 3 must reject a non-enum predicate"
    assert data["failure_count"] == 1
    fl = data["failures"][0]
    assert fl["key"] == "modulates somehow"
    assert "BiolinkPredicate" in fl["reason"]


def test_layer3_rejects_case_and_whitespace_drift(tmp_path):
    """Layer 3 is exact-match — it does not normalize; drift must fail (that is
    canonicalize_predicates' job, run first)."""
    doc = _clean_doc()
    doc["links"][0]["key"] = "Decreases  Activity Of"   # case + double-space drift
    f = _write(tmp_path, doc)
    code, data, _ = _run("validate_predicates.py", str(f))
    assert code == 1
    assert data["failure_count"] == 1


# ─── Layer 4 — reference verbatim check (crafted scratch cache) ───────────────

def _l4_env(cache_dir: Path) -> dict:
    env = os.environ.copy()
    env["DMDB_CACHE_DIR"] = str(cache_dir)
    return env


def _l4_doc(snippet: str) -> dict:
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": "DBX_MESH_DX_9", "drug": "TestDrug", "disease": "TestDisease",
                  "disease_mesh": "MESH:D000001"},
        "nodes": [
            {"id": "MESH:D001241", "name": "TestDrug", "label": "Drug"},
            {"id": "UniProt:P23219", "name": "TestProtein", "label": "Protein"},
        ],
        "links": [{
            "key": "decreases activity of", "source": "MESH:D001241", "target": "UniProt:P23219",
            "evidence": [{"reference": "PMID:12345678", "snippet": snippet,
                          "supports": "SUPPORT", "evidence_source": "IN_VITRO"}],
        }],
    }


@pytest.fixture
def l4_cache(tmp_path):
    cache = tmp_path / "cache"
    common.write_cache(
        "PMID:12345678",
        {"title": "Test source",
         "abstract": "The drug decreases the activity of the target protein in cells."},
        content_type="abstract", cache_dir=cache,
    )
    return cache


def test_layer4_accepts_verbatim_snippet(tmp_path, l4_cache):
    f = _write(tmp_path, _l4_doc("decreases the activity of the target protein"))
    code, data, _ = _run("validate_references.py", "--offline", str(f), env=_l4_env(l4_cache))
    assert code == 0, data
    assert data["files_with_evidence"] == 1
    assert data["files_failing"] == 0


def test_layer4_rejects_fabricated_snippet(tmp_path, l4_cache):
    f = _write(tmp_path, _l4_doc("THIS TEXT IS FABRICATED AND NOT IN THE SOURCE"))
    code, data, log = _run("validate_references.py", "--offline", str(f), env=_l4_env(l4_cache))
    assert code == 1, "Layer 4 must reject a snippet that is not a verbatim substring"
    assert data["files_failing"] == 1
    assert "not found as substring" in log.lower()


def test_layer4_noop_when_no_evidence(tmp_path, l4_cache):
    """A record with no evidence must be a Layer-4 no-op (legacy profile), never a fail."""
    f = _write(tmp_path, _clean_doc())
    code, data, _ = _run("validate_references.py", "--offline", str(f), env=_l4_env(l4_cache))
    assert code == 0
    assert data["files_with_evidence"] == 0
