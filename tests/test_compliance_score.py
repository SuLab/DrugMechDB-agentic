"""
Test suite for scripts/compliance_score.py — the deterministic compliance score
+ "good-enough-to-keep" threshold.

Verifies the maintainer's bar exactly:
  * HARD gates (QC Layers 1-4 that ran + no HARD structural flag) must ALL pass, else
    tier=REJECT / score=0.0 / keep=False — even when every QC layer passes (P06).
  * SOFT structural flags (net_polarity / type_violation) grade the score down and drop
    the tier to KEEP_WITH_REVIEW, but NEVER reject (keep stays True).
  * The keep-line IS the hard-gate line: keep == hard_gates_pass.
  * The scorer is fully deterministic: no LLM, no network — identical output across runs.

Canonical fixtures:
  * tests/phase3_eval_outputs/P06.yaml            — passes all 4 QC layers but has HARD
                                                    structural flags (short_circuit +
                                                    clinical_shortcut) => REJECT.
  * kb/paths/DB00002_MESH_D003110_1.yaml (legacy) — fully clean => COMPLIANT.
  * kb/paths/DB00007_MESH_D004715_1.yaml (legacy) — clean-HARD, one net_polarity SOFT
                                                    flag => KEEP_WITH_REVIEW.
These kb files are frozen legacy data (Hard Boundary: no data migration), so the tests
pin them the same way tests/test_validation.py pins specific corpus records.
"""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
SCRIPTS = REPO / "scripts"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"

sys.path.insert(0, str(SCRIPTS))
import compliance_score as cs  # noqa: E402

P06 = REPO / "tests" / "phase3_eval_outputs" / "P06.yaml"
CLEAN_LEGACY = REPO / "kb" / "paths" / "DB00002_MESH_D003110_1.yaml"
SOFT_LEGACY = REPO / "kb" / "paths" / "DB00007_MESH_D004715_1.yaml"

CLI = SCRIPTS / "compliance_score.py"


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ─── REJECT: HARD structural flag beats a perfect QC pass ───────────────────

def test_p06_is_rejected_despite_passing_all_qc_layers():
    r = cs.compliance_score(str(P06))
    # every QC layer passes ...
    assert r["hard_gates"]["layer1"] is True
    assert r["hard_gates"]["layer2"] is True
    assert r["hard_gates"]["layer3"] is True
    assert r["hard_gates"]["layer4"] is True   # ai_curated -> Layer 4 ran
    # ... yet HARD structural flags are present ...
    codes = {f["code"] for f in r["hard_gates"]["structural_hard"]}
    assert codes, "P06 must carry HARD structural flags"
    assert codes <= cs.HARD_STRUCTURAL
    assert "clinical_shortcut" in codes or "short_circuit" in codes
    # ... so the whole path is rejected, score pinned to 0, not keepable.
    assert r["tier"] == "REJECT"
    assert r["score"] == 0.0
    assert r["keep"] is False
    assert r["breakdown"]["hard_gates_pass"] is False


# ─── COMPLIANT: clean legacy path ───────────────────────────────────────────

def test_clean_legacy_is_compliant():
    r = cs.compliance_score(str(CLEAN_LEGACY))
    assert r["profile"] == "legacy"
    assert r["hard_gates"]["layer1"] is True
    assert r["hard_gates"]["layer2"] is True
    assert r["hard_gates"]["layer3"] is True
    assert r["hard_gates"]["layer4"] is None        # legacy -> Layer 4 not applicable
    assert r["hard_gates"]["structural_hard"] == []
    assert r["soft_flags"] == []
    assert r["tier"] == "COMPLIANT"
    assert r["score"] == 1.0
    assert r["keep"] is True


def test_legacy_skipped_layer4_does_not_fail_the_gate():
    """A not-applicable Layer 4 (None) must not count as a hard-gate failure."""
    r = cs.compliance_score(str(CLEAN_LEGACY))
    assert r["hard_gates"]["layer4"] is None
    assert r["keep"] is True


# ─── KEEP_WITH_REVIEW: soft flag grades but never rejects ───────────────────

def test_soft_flag_is_keep_with_review_not_reject():
    r = cs.compliance_score(str(SOFT_LEGACY))
    assert r["hard_gates"]["structural_hard"] == []     # hard gates all pass
    soft_codes = {f["code"] for f in r["soft_flags"]}
    assert soft_codes, "expected >=1 SOFT flag"
    assert soft_codes <= cs.SOFT_STRUCTURAL             # only net_polarity / type_violation
    assert r["tier"] == "KEEP_WITH_REVIEW"
    assert r["keep"] is True                            # SOFT never blocks keeping
    # score = 1.0 - min(0.5, 0.1 * n_soft)
    n = len(r["soft_flags"])
    assert r["score"] == pytest.approx(1.0 - min(0.5, 0.1 * n))
    assert 0.5 <= r["score"] < 1.0


def test_soft_score_formula_and_floor():
    """Deterministic formula: each SOFT flag costs 0.1, floored at 0.5."""
    assert cs._SOFT_PENALTY == 0.1
    assert cs._SCORE_FLOOR == 0.5
    r = cs.compliance_score(str(SOFT_LEGACY))
    n = r["breakdown"]["soft_flag_count"]
    expected = round(1.0 - min(0.5, 0.1 * n), 4)
    assert r["score"] == pytest.approx(expected)


# ─── the keep-line IS the hard-gate line ────────────────────────────────────

@pytest.mark.parametrize("path", [P06, CLEAN_LEGACY, SOFT_LEGACY])
def test_keep_equals_hard_gate_pass(path):
    r = cs.compliance_score(str(path))
    assert r["keep"] == r["breakdown"]["hard_gates_pass"]
    # tier <-> keep coherence
    if r["tier"] == "REJECT":
        assert r["keep"] is False
    else:
        assert r["tier"] in ("COMPLIANT", "KEEP_WITH_REVIEW")
        assert r["keep"] is True


# ─── determinism: identical output across runs ──────────────────────────────

@pytest.mark.parametrize("path", [P06, CLEAN_LEGACY, SOFT_LEGACY])
def test_deterministic_repeated_calls(path):
    a = cs.compliance_score(str(path))
    b = cs.compliance_score(str(path))
    assert a == b, "same input must yield identical output (no LLM / no network)"


def test_no_llm_no_network_imports():
    """Importing the scorer must not pull in any LLM SDK or judge backend — proof the
    keep/reject decision cannot depend on a non-deterministic model. Checked in a fresh
    interpreter so the result is independent of test-collection import order."""
    code = (
        "import sys;"
        f"sys.path.insert(0, r'{SCRIPTS}');"
        "import compliance_score;"
        "banned=[m for m in ('anthropic','openai','judge.backends','critic','quality_profile')"
        " if m in sys.modules];"
        "print('BANNED:'+','.join(banned))"
    )
    proc = subprocess.run([_py(), "-c", code], capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "BANNED:" in proc.stdout
    banned = proc.stdout.split("BANNED:")[1].strip()
    assert banned == "", f"scorer imported non-deterministic module(s): {banned}"


# ─── CLI ────────────────────────────────────────────────────────────────────

def test_cli_json_shape_and_reject_exit():
    proc = subprocess.run([_py(), str(CLI), str(P06), "--json"],
                          capture_output=True, text=True)
    assert proc.returncode == 1, f"REJECT must exit 1.\n{proc.stderr}"
    data = json.loads(proc.stdout)
    for k in ("tier", "score", "keep", "hard_gates", "soft_flags", "breakdown"):
        assert k in data, f"missing key {k}"
    assert set(data["hard_gates"]) == {"layer1", "layer2", "layer3", "layer4", "structural_hard"}
    assert data["tier"] == "REJECT"
    assert data["keep"] is False


def test_cli_keepable_exit_zero():
    proc = subprocess.run([_py(), str(CLI), str(CLEAN_LEGACY)],
                          capture_output=True, text=True)
    assert proc.returncode == 0, proc.stderr
    assert "COMPLIANT" in proc.stdout


def test_cli_missing_file_exit_two():
    proc = subprocess.run([_py(), str(CLI), str(REPO / "kb" / "paths" / "__does_not_exist__.yaml")],
                          capture_output=True, text=True)
    assert proc.returncode == 2


def test_cli_multiple_files_json_is_list():
    proc = subprocess.run([_py(), str(CLI), str(CLEAN_LEGACY), str(SOFT_LEGACY), "--json"],
                          capture_output=True, text=True)
    # one keepable + one keepable -> exit 0
    assert proc.returncode == 0, proc.stderr
    data = json.loads(proc.stdout)
    assert isinstance(data, list) and len(data) == 2
