"""
Coverage for the re-curation campaign framework (scripts/campaign_runner.py):
enumeration, the resumable/idempotent status store, and the runner's dispatch —
all offline via the StubBackend, no API, no real curation.

test_curate_engine.py already covers the live AgenticBackend (parallel isolation)
and the backend registry; this file covers the orchestration around it:

  * enumerate_work reads the index, yields one WorkItem per entry, sorted by id;
  * StatusStore.pending() skips finished records (resume);
  * a second run over an already-done corpus dispatches nothing (idempotency);
  * a backend failure lands the record in `failed`, not `done`.

INDEX and the status file are pointed at scratch; nothing under kb/ is touched.
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest
import yaml

REPO = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO / "scripts"))

import campaign_runner as cr  # noqa: E402
from campaign_runner import WorkItem, StatusStore, StubBackend, CampaignRunner  # noqa: E402

# Deliberately out of id order, to prove enumerate_work sorts.
INDEX_ENTRIES = [
    {"id": "C_MESH_D3_1", "file": "C_MESH_D3_1.yaml", "drug": "DrugC",
     "disease": "DisC", "disease_mesh": "MESH:D3", "drug_mesh": "MESH:D30"},
    {"id": "A_MESH_D1_1", "file": "A_MESH_D1_1.yaml", "drug": "DrugA",
     "disease": "DisA", "disease_mesh": "MESH:D1", "drug_mesh": "MESH:D10"},
    {"id": "B_MESH_D2_1", "file": "B_MESH_D2_1.yaml", "drug": "DrugB",
     "disease": "DisB", "disease_mesh": "MESH:D2", "drugbank": "DB:DB0002"},
]


@pytest.fixture
def scratch_index(tmp_path, monkeypatch):
    idx = tmp_path / "_index.yaml"
    idx.write_text(yaml.safe_dump(INDEX_ENTRIES), encoding="utf-8")
    monkeypatch.setattr(cr, "INDEX", idx)
    return idx


@pytest.fixture
def deterministic_provenance(monkeypatch):
    # keep the runner hermetic: no git subprocess, stable prompt fingerprint
    monkeypatch.setattr(cr, "git_sha", lambda: "testsha")
    monkeypatch.setattr(cr, "prompt_version", lambda: "testprompt")


# ─── enumeration ─────────────────────────────────────────────────────────────

def test_enumerate_work_count_and_sort(scratch_index):
    items = cr.enumerate_work()
    assert len(items) == len(INDEX_ENTRIES)
    assert [w.id for w in items] == ["A_MESH_D1_1", "B_MESH_D2_1", "C_MESH_D3_1"]
    a = items[0]
    assert isinstance(a, WorkItem)
    assert a.drug == "DrugA" and a.disease_mesh == "MESH:D1" and a.drug_mesh == "MESH:D10"


# ─── status store: resume ────────────────────────────────────────────────────

def test_status_store_pending_skips_done(tmp_path):
    store = StatusStore.load(tmp_path / "status.yaml")
    items = [WorkItem(id="x"), WorkItem(id="y"), WorkItem(id="z")]
    assert store.pending(items) == items          # nothing done yet
    store.mark("y", "done")
    pending_ids = [w.id for w in store.pending(items)]
    assert pending_ids == ["x", "z"]              # y skipped


def test_status_store_counts_and_persistence(tmp_path):
    path = tmp_path / "status.yaml"
    store = StatusStore.load(path)
    store.mark("a", "done")
    store.mark("b", "failed", error="boom")
    store.save()
    assert store.counts()["done"] == 1
    assert store.counts()["failed"] == 1
    # reload from disk: state survives (resumable across process restarts)
    reloaded = StatusStore.load(path)
    assert reloaded.state("a") == "done"
    assert reloaded.state("b") == "failed"
    assert reloaded.records["b"]["error"] == "boom"


def test_status_store_default_state_is_pending(tmp_path):
    store = StatusStore.load(tmp_path / "status.yaml")
    assert store.state("never-seen") == "pending"


# ─── runner: dispatch, idempotency, failure routing ──────────────────────────

def test_run_marks_done_and_is_idempotent(tmp_path, scratch_index, deterministic_provenance):
    status_path = tmp_path / "status.yaml"

    runner = CampaignRunner(status=StatusStore.load(status_path))
    results = runner.run(StubBackend())
    assert set(results) == {"A_MESH_D1_1", "B_MESH_D2_1", "C_MESH_D3_1"}
    assert all(r.ok for r in results.values())
    assert runner.status.counts()["done"] == 3

    # A fresh runner loading the persisted status must see NOTHING pending, and a
    # re-run must dispatch nothing (idempotent / resumable).
    runner2 = CampaignRunner(status=StatusStore.load(status_path))
    _all, pending = runner2.plan()
    assert pending == []
    results2 = runner2.run(StubBackend())
    assert results2 == {}


def test_run_routes_backend_failure_to_failed(tmp_path, scratch_index, deterministic_provenance):
    status_path = tmp_path / "status.yaml"
    runner = CampaignRunner(status=StatusStore.load(status_path))
    runner.run(StubBackend(fail_ids={"B_MESH_D2_1"}))
    assert runner.status.state("A_MESH_D1_1") == "done"
    assert runner.status.state("B_MESH_D2_1") == "failed"
    assert runner.status.records["B_MESH_D2_1"]["error"] == "stub-forced-failure"
    # the failed record is still pending on the next plan -> it will be retried
    _all, pending = runner.plan()
    assert "B_MESH_D2_1" in {w.id for w in pending}
    assert "A_MESH_D1_1" not in {w.id for w in pending}


def test_run_limit_caps_dispatch(tmp_path, scratch_index, deterministic_provenance):
    runner = CampaignRunner(status=StatusStore.load(tmp_path / "status.yaml"))
    results = runner.run(StubBackend(), limit=2)
    assert len(results) == 2
    assert runner.status.counts()["done"] == 2
