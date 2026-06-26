"""
Phase 4b — research-agent test suite.

Covers:
  - Cache layer: slugify, write+load round-trip, TTL freshness logic, short-circuit.
  - Provider abstraction: env-var enforcement (Claude), NotImplementedError stubs (Perplexity, Asta), PMID extraction.
  - CLI: list / cache-info / run subcommands work without network.
  - The provider-to-curation safety contract: the existing Layer-4 negative
    fixture (`tests/fixtures/sample_ai_curated_bad_snippet.yaml`) demonstrates
    that a hallucinated provider snippet is caught by Layer 4. This is the
    invariant that lets the research agent be loose while curation stays strict.

No test in this file makes a real network call. The Claude provider's actual
API integration is exercised end-to-end during step 5 of the Phase 4b
rollout (P01 / P15 re-run with the new provider).
"""

from __future__ import annotations

import datetime as dt
import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
VENV_PY = REPO / ".venv-py310" / "bin" / "python"
FIXTURES = REPO / "tests" / "fixtures"

# Make scripts/ importable for in-process tests.
sys.path.insert(0, str(REPO / "scripts"))

from research_providers import cache as cache_mod  # noqa: E402
from research_providers.base import ResearchDossier  # noqa: E402
from research_providers.claude import ClaudeProvider  # noqa: E402
from research_providers.perplexity import PerplexityProvider  # noqa: E402
from research_providers.asta import AstaProvider  # noqa: E402


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ─── Cache layer ────────────────────────────────────────────────────────────


@pytest.mark.parametrize("text,expected", [
    ("Aspirin", "aspirin"),
    ("Myocardial Infarction", "myocardial_infarction"),
    ("HER2-positive Breast Cancer", "her2_positive_breast_cancer"),
    ("  Lots   of  spaces  ", "lots_of_spaces"),
    ("Slashes/and:colons", "slashes_and_colons"),
])
def test_slugify(text: str, expected: str) -> None:
    assert cache_mod.slugify(text) == expected


def test_cache_path_format() -> None:
    p = cache_mod.cache_path("Aspirin", "Myocardial Infarction", "claude")
    assert p.name == "aspirin_myocardial_infarction-claude.md"
    assert p.parent.name == "research"


def test_write_load_roundtrip(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    d = ResearchDossier(
        provider="claude",
        model="claude-opus-4-5",
        drug="Aspirin",
        disease="Myocardial Infarction",
        query="a test query",
        generated_at=dt.datetime.now(dt.timezone.utc),
        markdown_body="## summary\n\nbody text with PMID:12345.",
        candidate_pmids=["PMID:12345", "PMID:67890"],
        notes="input_tokens=42",
    )
    path = cache_mod.write(d)
    assert path.exists()
    loaded = cache_mod.load(path)
    assert loaded is not None
    fm, body = loaded
    assert fm["provider"] == "claude"
    assert fm["drug"] == "Aspirin"
    assert fm["candidate_pmids"] == ["PMID:12345", "PMID:67890"]
    assert fm["notes"] == "input_tokens=42"
    assert "body text with PMID:12345." in body
    assert cache_mod.is_fresh(fm) is True


def test_is_fresh_stale(monkeypatch, tmp_path) -> None:
    """A 60-day-old entry is stale under the default 30-day TTL."""
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    d = ResearchDossier(
        provider="claude", model="m", drug="Aspirin", disease="MI",
        query="q", generated_at=dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=60),
        markdown_body="body", candidate_pmids=[],
    )
    path = cache_mod.write(d)
    loaded = cache_mod.load(path)
    assert loaded is not None
    fm, _ = loaded
    assert cache_mod.is_fresh(fm, ttl_days=30) is False
    assert cache_mod.is_fresh(fm, ttl_days=90) is True


def test_is_fresh_missing_timestamp() -> None:
    """A frontmatter without `generated_at` is treated as stale."""
    assert cache_mod.is_fresh({}) is False
    assert cache_mod.is_fresh({"generated_at": ""}) is False


def test_load_if_fresh_short_circuit(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(cache_mod, "CACHE_DIR", tmp_path)
    # No file → returns None
    assert cache_mod.load_if_fresh("Aspirin", "MI", "claude") is None
    # Fresh write → returns the path
    d = ResearchDossier(
        provider="claude", model="m", drug="Aspirin", disease="MI",
        query="q", generated_at=dt.datetime.now(dt.timezone.utc),
        markdown_body="body", candidate_pmids=[],
    )
    cache_mod.write(d)
    found = cache_mod.load_if_fresh("Aspirin", "MI", "claude")
    assert found is not None
    assert found.exists()


# ─── Provider abstraction ────────────────────────────────────────────────────


def test_claude_requires_api_key(monkeypatch) -> None:
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)
    with pytest.raises(RuntimeError, match="ANTHROPIC_API_KEY"):
        ClaudeProvider().run("Aspirin", "Myocardial Infarction")


def test_perplexity_is_stub() -> None:
    with pytest.raises(NotImplementedError, match="PerplexityProvider"):
        PerplexityProvider().run("Aspirin", "MI")


def test_asta_is_stub() -> None:
    with pytest.raises(NotImplementedError, match="AstaProvider"):
        AstaProvider().run("Aspirin", "MI")


def test_claude_default_model() -> None:
    assert ClaudeProvider().default_model.startswith("claude-")


def test_claude_pmid_extraction_dedup_and_order() -> None:
    body = """
    Aspirin inhibits COX-1 (PMID:23422285) and COX-2 (PMID:36588714).
    See also PMID:23422285 again, and a malformed PMID:abc12 should be ignored.
    Finally, PMID:9876543 is the third unique citation.
    """
    pmids = ClaudeProvider._extract_pmids(body)
    assert pmids == ["PMID:23422285", "PMID:36588714", "PMID:9876543"]


def test_claude_pmid_extraction_empty() -> None:
    assert ClaudeProvider._extract_pmids("no citations here") == []


# ─── CLI ─────────────────────────────────────────────────────────────────────


def test_cli_list_shows_three_providers() -> None:
    proc = subprocess.run(
        [_py(), str(REPO / "scripts" / "research.py"), "list"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 0, proc.stderr
    out = proc.stdout
    assert "claude" in out
    assert "perplexity" in out
    assert "asta" in out
    assert "ready" in out             # claude is implemented
    assert "stub" in out              # perplexity, asta are stubs


def test_cli_cache_info_not_cached() -> None:
    # Use a triple that won't have a cached file.
    proc = subprocess.run(
        [_py(), str(REPO / "scripts" / "research.py"),
         "cache-info", "claude", "TestDrug_DoesNotExist", "TestDisease_DoesNotExist"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 1  # not-cached exits non-zero
    assert "NOT CACHED" in proc.stdout


def test_cli_run_without_key_clean_error(monkeypatch) -> None:
    env = {**__import__("os").environ}
    env.pop("ANTHROPIC_API_KEY", None)
    proc = subprocess.run(
        [_py(), str(REPO / "scripts" / "research.py"),
         "run", "claude", "Aspirin", "Myocardial Infarction"],
        capture_output=True, text=True, env=env,
    )
    assert proc.returncode == 1
    assert "ANTHROPIC_API_KEY" in proc.stderr
    assert "ERROR" in proc.stderr


def test_cli_run_perplexity_stub_error() -> None:
    proc = subprocess.run(
        [_py(), str(REPO / "scripts" / "research.py"),
         "run", "perplexity", "Aspirin", "Myocardial Infarction"],
        capture_output=True, text=True,
    )
    assert proc.returncode == 3                 # NotImplementedError exit code
    assert "PerplexityProvider" in proc.stderr


def test_cli_run_short_circuits_on_fresh_cache(monkeypatch, tmp_path) -> None:
    """Write a fake fresh dossier; `run` should report CACHED without invoking the provider."""
    # Run the CLI with a temp REPO is hard because CACHE_DIR is module-level.
    # Instead, write into the real cache and clean up after.
    real_path = cache_mod.cache_path("StubDrug_XYZ", "StubDisease_XYZ", "claude")
    real_path.parent.mkdir(parents=True, exist_ok=True)
    d = ResearchDossier(
        provider="claude", model="m", drug="StubDrug_XYZ", disease="StubDisease_XYZ",
        query="q", generated_at=dt.datetime.now(dt.timezone.utc),
        markdown_body="body", candidate_pmids=[],
    )
    written = cache_mod.write(d)
    try:
        proc = subprocess.run(
            [_py(), str(REPO / "scripts" / "research.py"),
             "run", "claude", "StubDrug_XYZ", "StubDisease_XYZ"],
            capture_output=True, text=True,
        )
        assert proc.returncode == 0, proc.stderr
        assert "CACHED" in proc.stdout
    finally:
        written.unlink(missing_ok=True)


# ─── Provider-to-curation safety contract ───────────────────────────────────


def test_provider_hallucination_caught_by_layer4() -> None:
    """The Layer-4 negative fixture stands in for "a provider hallucinated a
    snippet that's not in any cached PubMed abstract." Layer 4 must catch it.

    This is the invariant that lets the research agent be loose: any snippet
    not present verbatim in references_cache/PMID_*.md fails before merge.
    Without this gate, a provider could inject fabricated quotes into paths.
    """
    fixture = FIXTURES / "sample_ai_curated_bad_snippet.yaml"
    assert fixture.exists(), "Phase 2 fixture must exist for this contract test"
    proc = subprocess.run(
        [_py(), str(REPO / "scripts" / "validate_references.py"), str(fixture), "--json"],
        capture_output=True, text=True,
    )
    assert proc.returncode != 0, (
        "Layer 4 must reject the non-verbatim snippet — "
        "this is the safety property for research-provider integration"
    )
    try:
        data = json.loads(proc.stdout)
        assert data.get("files_failing", 0) >= 1
    except json.JSONDecodeError:
        # Non-zero exit + stderr containing "not found" is also acceptable.
        assert "not found" in (proc.stdout + proc.stderr).lower()
