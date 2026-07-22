"""
Round-trip coverage for scripts/rebuild_monolith.py — the regenerator of the
consolidated indication_paths.{yaml,json} from the per-record kb/paths files.

The load-bearing guarantee is that the monolith is a pure, deterministic
function of the per-record files: same inputs -> byte-identical output, records
in canonical _id order, content passed through verbatim. Proven here against a
scratch corpus (PATHS_DIR monkeypatched); the real monolith and kb/ are never
written.
"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import rebuild_monolith as rm  # noqa: E402


def _rec(_id, drug):
    return {
        "directed": True, "multigraph": True,
        "graph": {"_id": _id, "drug": drug, "disease": "Dis", "disease_mesh": "MESH:D9"},
        "nodes": [
            {"id": "MESH:D1", "name": drug, "label": "Drug"},
            {"id": "UniProt:P1", "name": "Prot", "label": "Protein"},
            {"id": "MESH:D9", "name": "Dis", "label": "Disease"},
        ],
        "links": [
            {"source": "MESH:D1", "target": "UniProt:P1", "key": "decreases activity of"},
            {"source": "UniProt:P1", "target": "MESH:D9", "key": "causes"},
        ],
    }


# Written to disk out of _id order to prove canonical sorting on rebuild.
RECS = {
    "C_MESH_D9_1": _rec("C_MESH_D9_1", "DrugC"),
    "A_MESH_D9_1": _rec("A_MESH_D9_1", "DrugA"),
    "B_MESH_D9_1": _rec("B_MESH_D9_1", "DrugB"),
}
SORTED_RECS = [RECS[k] for k in ["A_MESH_D9_1", "B_MESH_D9_1", "C_MESH_D9_1"]]


@pytest.fixture
def corpus(tmp_path, monkeypatch):
    d = tmp_path / "paths"
    d.mkdir()
    for _id, rec in RECS.items():
        (d / f"{_id}.yaml").write_text(yaml.safe_dump(rec, sort_keys=False), encoding="utf-8")
    (d / "_index.yaml").write_text("- id: A_MESH_D9_1\n", encoding="utf-8")  # must be ignored
    monkeypatch.setattr(rm, "PATHS_DIR", d)
    return d


def test_load_records_sorted_by_id_and_index_ignored(corpus):
    records = rm.load_records()
    assert len(records) == 3                       # _index.yaml excluded
    assert [r["graph"]["_id"] for r in records] == ["A_MESH_D9_1", "B_MESH_D9_1", "C_MESH_D9_1"]


def test_yaml_roundtrip_is_faithful(corpus):
    records = rm.load_records()
    parsed = yaml.safe_load(rm.render_yaml(records))
    assert parsed == SORTED_RECS                   # content preserved verbatim, in _id order


def test_json_roundtrip_is_faithful(corpus):
    records = rm.load_records()
    parsed = json.loads(rm.render_json(records))
    assert parsed == SORTED_RECS


def test_render_is_deterministic(corpus):
    records = rm.load_records()
    assert rm.render_yaml(records) == rm.render_yaml(records)
    assert rm.render_json(records) == rm.render_json(records)


# ─── --check disposition ─────────────────────────────────────────────────────

def _run_check(monkeypatch, yaml_path, json_path):
    argv = ["rebuild_monolith.py", "--check", "--yaml", str(yaml_path), "--json", str(json_path)]
    monkeypatch.setattr(sys, "argv", argv)
    return rm.main()


def test_check_passes_when_artifacts_match(corpus, tmp_path, monkeypatch):
    records = rm.load_records()
    y = tmp_path / "out.yaml"; y.write_text(rm.render_yaml(records), encoding="utf-8")
    j = tmp_path / "out.json"; j.write_text(rm.render_json(records), encoding="utf-8")
    assert _run_check(monkeypatch, y, j) == 0


def test_check_flags_stale_artifact(corpus, tmp_path, monkeypatch):
    records = rm.load_records()
    y = tmp_path / "out.yaml"; y.write_text(rm.render_yaml(records), encoding="utf-8")
    j = tmp_path / "out.json"; j.write_text("[]\n", encoding="utf-8")   # deliberately stale
    assert _run_check(monkeypatch, y, j) == 1
