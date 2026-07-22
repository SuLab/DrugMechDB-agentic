"""
Coverage for scripts/detect_duplicates.py — the exact / near duplicate detector.

Proves it FINDS a real duplicate and IGNORES genuinely distinct records:

  * two records with an identical edge set are grouped as an exact structural
    duplicate (and the same-indication flag is set correctly);
  * a record with a unique edge set is grouped with nothing;
  * two records in the same indication that overlap heavily (Jaccard 0.8) are a
    near-duplicate pair, while an identical pair (Jaccard 1.0) is NOT a near pair
    (it is exact) and a distinct pair is neither.

Scratch corpus via a monkeypatched PATHS_DIR; kb/ is untouched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import detect_duplicates as dd  # noqa: E402


def _e(s, t, k="causes"):
    return {"source": s, "target": t, "key": k}


def _rec(_id, drug_mesh, disease_mesh, links):
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": _id, "drug": "d", "disease": "e",
                  "drug_mesh": drug_mesh, "disease_mesh": disease_mesh},
        "nodes": [{"id": "MESH:D1", "name": "n", "label": "Drug"}],
        "links": links,
    }


# Exact-duplicate pair (same indication, identical 2-edge set).
S1 = [_e("MESH:D1", "UniProt:P1", "decreases activity of"), _e("UniProt:P1", "MESH:D9", "causes")]
# A distinct, unique record (its own indication).
S2 = [_e("MESH:D2", "UniProt:P2", "increases activity of"), _e("UniProt:P2", "MESH:D8", "causes")]
# Near-duplicate pair (same indication): 5-edge vs its 4-edge subset -> Jaccard 4/5 = 0.8.
S3_FULL = [_e("MESH:D3", f"UniProt:Q{i}") for i in range(5)]
S3_SUB = S3_FULL[:4]

RECORDS = {
    "A1": _rec("A1", "MESH:DA", "MESH:D9", list(S1)),
    "A2": _rec("A2", "MESH:DA", "MESH:D9", list(S1)),      # exact dup of A1
    "B":  _rec("B", "MESH:DB", "MESH:D8", list(S2)),       # unique
    "C1": _rec("C1", "MESH:DC", "MESH:D7", list(S3_FULL)),
    "C2": _rec("C2", "MESH:DC", "MESH:D7", list(S3_SUB)),  # near dup of C1
}


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    d = tmp_path / "paths"
    d.mkdir()
    for _id, rec in RECORDS.items():
        (d / f"{_id}.yaml").write_text(yaml.safe_dump(rec, sort_keys=False), encoding="utf-8")
    (d / "_index.yaml").write_text("- id: A1\n", encoding="utf-8")
    monkeypatch.setattr(dd, "PATHS_DIR", d)
    return d


def test_loads_all_but_index(corpus):
    recs = dd.load_records()
    assert {r["id"] for r in recs} == {"A1", "A2", "B", "C1", "C2"}


# ─── exact duplicates ────────────────────────────────────────────────────────

def test_finds_exact_duplicate(corpus):
    groups = dd.find_exact(dd.load_records())
    assert len(groups) == 1                        # only A1/A2 share an edge set
    g = groups[0]
    assert g["ids"] == ["A1", "A2"]
    assert g["same_indication"] is True
    assert g["n_edges"] == 2


def test_unique_record_is_not_an_exact_duplicate(corpus):
    groups = dd.find_exact(dd.load_records())
    all_ids = {i for g in groups for i in g["ids"]}
    assert "B" not in all_ids                       # the distinct record is ignored
    assert "C1" not in all_ids and "C2" not in all_ids   # near, not exact


def test_exact_flags_different_indications(tmp_path, monkeypatch):
    """Same edge set under two different indications -> flagged, same_indication False."""
    d = tmp_path / "paths"; d.mkdir()
    d.joinpath("X.yaml").write_text(yaml.safe_dump(_rec("X", "MESH:DX", "MESH:D1", list(S1))), encoding="utf-8")
    d.joinpath("Y.yaml").write_text(yaml.safe_dump(_rec("Y", "MESH:DY", "MESH:D2", list(S1))), encoding="utf-8")
    monkeypatch.setattr(dd, "PATHS_DIR", d)
    groups = dd.find_exact(dd.load_records())
    assert len(groups) == 1
    assert groups[0]["ids"] == ["X", "Y"]
    assert groups[0]["same_indication"] is False


# ─── near duplicates ─────────────────────────────────────────────────────────

def test_finds_near_duplicate(corpus):
    pairs = dd.find_near(dd.load_records(), threshold=0.80)
    assert len(pairs) == 1
    p = pairs[0]
    assert p["ids"] == ["C1", "C2"]
    assert p["jaccard"] == 0.8


def test_exact_pair_is_not_a_near_pair(corpus):
    """A1/A2 have Jaccard 1.0 -> they are exact, NOT near (near is strictly < 1.0)."""
    pairs = dd.find_near(dd.load_records(), threshold=0.80)
    near_ids = {tuple(p["ids"]) for p in pairs}
    assert ("A1", "A2") not in near_ids


def test_near_threshold_excludes_below_cutoff(corpus):
    # raise the cutoff above 0.8 -> the 0.8 pair drops out
    assert dd.find_near(dd.load_records(), threshold=0.85) == []


# ─── the Jaccard primitive ───────────────────────────────────────────────────

def test_jaccard_values():
    a, b, c = frozenset("ab"), frozenset("ab"), frozenset("cd")
    assert dd.jaccard(a, b) == 1.0
    assert dd.jaccard(a, c) == 0.0
    assert dd.jaccard(frozenset("abcd"), frozenset("abc")) == pytest.approx(0.75)
