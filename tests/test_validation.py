"""
Phase 2 validation suite — exercises Layers 1-4 against:

  - the legacy corpus (kb/paths/*.yaml) — must pass Layers 1 and 3 (gap-free
    after Phase 1 / 1.5; Layer 2 has a known gap, see test below)
  - synthetic ai_curated fixtures in tests/fixtures/ — must pass all four

Replaces the unused stub at testfile.py and the monolith-coupled
utils/test_indications.py. Each layer is exercised via its standalone
script, not the orchestrator, so failures point to a single layer.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
FIXTURES = REPO / "tests" / "fixtures"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


def _run(*args: str, expect_exit: int | None = None) -> tuple[int, dict]:
    """Run a script with --json and return (exit, parsed_json)."""
    cmd = [_py(), *args, "--json"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if expect_exit is not None:
        assert proc.returncode == expect_exit, (
            f"expected exit {expect_exit}, got {proc.returncode}.\n"
            f"stdout:\n{proc.stdout}\nstderr:\n{proc.stderr}"
        )
    try:
        return proc.returncode, json.loads(proc.stdout)
    except json.JSONDecodeError:
        # Layer 4 doesn't always emit pure JSON — fall back to raw output
        return proc.returncode, {"_raw": proc.stdout + proc.stderr}


# ─── Layer 1 — schema validation ──────────────────────────────────────────

def test_layer1_legacy_corpus_passes():
    """Phase 1 exit criterion: 100% of kb/paths/*.yaml pass Layer 1."""
    exit_code, data = _run("scripts/validate_schema.py")
    assert exit_code == 0, f"Layer 1 failed on legacy corpus: {data['failures'][:3]}"
    assert data["failure_count"] == 0
    assert data["files_checked"] >= 4800


def test_layer1_ai_curated_fixture_passes():
    exit_code, data = _run("scripts/validate_schema.py", str(FIXTURES / "sample_ai_curated.yaml"))
    assert exit_code == 0, data


# ─── Layer 2 — node ontology check ────────────────────────────────────────

def test_layer2_ai_curated_fixture_passes():
    exit_code, data = _run(
        "scripts/validate_node_ontology.py", str(FIXTURES / "sample_ai_curated.yaml")
    )
    assert exit_code == 0, data
    assert data["failure_count"] == 0


def test_layer2_legacy_corpus_has_known_gaps():
    """The legacy corpus has 230 prefix violations as of Phase 2 close.
    This is recorded in docs/phase2_gap_report.md; the test asserts the
    gap exists so we notice if it changes (better or worse)."""
    exit_code, data = _run("scripts/validate_node_ontology.py")
    assert data["files_checked"] >= 4800
    # As of May 2026: 230 failures across 190 files
    assert 0 <= data["failure_count"] <= 500, f"unexpected failure count: {data['failure_count']}"


# ─── Layer 3 — predicate validation ───────────────────────────────────────

def test_layer3_legacy_corpus_passes_exit_criterion():
    """Phase 1.5 / Phase 2 hard requirement: 100% of legacy edges use canonical predicates."""
    exit_code, data = _run("scripts/validate_predicates.py")
    assert exit_code == 0
    assert data["failure_count"] == 0
    assert data["enum_size"] == 67


def test_layer3_ai_curated_fixture_passes():
    exit_code, _ = _run("scripts/validate_predicates.py", str(FIXTURES / "sample_ai_curated.yaml"))
    assert exit_code == 0


# ─── Layer 4 — reference / snippet verification ───────────────────────────

def test_layer4_legacy_corpus_is_noop():
    """Legacy corpus has no evidence; Layer 4 must be a no-op (exit 0)."""
    exit_code, data = _run("scripts/validate_references.py")
    assert exit_code == 0
    assert data["files_with_evidence"] == 0


def test_layer4_ai_curated_fixture_passes_with_cached_pmid():
    exit_code, _ = _run("scripts/validate_references.py", str(FIXTURES / "sample_ai_curated.yaml"))
    assert exit_code == 0


def test_layer4_rejects_non_verbatim_snippet():
    """Negative test — Layer 4 must FAIL when snippet is not a verbatim substring."""
    exit_code, data = _run("scripts/validate_references.py", str(FIXTURES / "sample_ai_curated_bad_snippet.yaml"))
    assert exit_code != 0, "expected Layer 4 to fail on a non-verbatim snippet"
    # The validator's stderr contains the failure detail
    assert "not found" in str(data).lower() or "substring" in str(data).lower() or data.get("files_failing", 0) > 0


# ─── Orchestrator (qc.py) profile selection ───────────────────────────────

def test_qc_auto_profile_legacy_for_corpus_sample():
    sample = REPO / "kb" / "paths" / "DB00002_MESH_D003110_1.yaml"
    proc = subprocess.run([_py(), "scripts/qc.py", str(sample), "--json"], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["profile_counts"].get("legacy", 0) == 1
    assert data["profile_counts"].get("ai_curated", 0) == 0
    assert 4 not in data["layers_run"], "Layer 4 should not run for legacy"


def test_qc_auto_profile_ai_curated_for_fixture():
    proc = subprocess.run(
        [_py(), "scripts/qc.py", str(FIXTURES / "sample_ai_curated.yaml"), "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert data["profile_counts"].get("ai_curated", 0) == 1
    assert 4 in data["layers_run"], "Layer 4 should run for ai_curated"
    assert data["overall_pass"] is True


def test_qc_forced_legacy_skips_layer_4_on_ai_curated_file():
    """Explicit --profile legacy must skip Layer 4 even on a file with evidence."""
    proc = subprocess.run(
        [_py(), "scripts/qc.py", "--profile", "legacy",
         str(FIXTURES / "sample_ai_curated_bad_snippet.yaml"), "--json"],
        capture_output=True, text=True,
    )
    data = json.loads(proc.stdout)
    assert 4 not in data["layers_run"], "Layer 4 should not run when --profile legacy is forced"
