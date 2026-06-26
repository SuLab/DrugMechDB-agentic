"""
Quality profile orchestrator — the single entry point for "how good is this path?".

Merges the three layers of the validation funnel (docs/path_quality_framework.md) into
one profile per record:

  1. Syntactic gate          — scripts/qc.py Layers 1-4 (schema/ontology/predicate/verbatim)
  2. Deterministic structural — scripts/quality/structural_quality.py (polarity/topology/...)
  3. Semantic LLM judges      — edge-evidence (Layer 5) + path-coherence (Layers 6/7)

The semantic layer runs only when a judge backend is available (an LLM API key). It is
chosen to be a DIFFERENT model family than the curator for independence; absent a key, the
deterministic profile is still produced and the semantic section is marked "not run".

Usage:
    python scripts/quality/quality_profile.py kb/paths/<file>.yaml
    python scripts/quality/quality_profile.py <file> --json
    python scripts/quality/quality_profile.py <file> --no-llm
    python scripts/quality/quality_profile.py <file> --provider openai
Exit: 0 = no hard-gate failure across inputs · 1 = >=1 hard-gate failure.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent          # scripts/quality
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))                    # so `import structural_quality` / `import judge.*` work

import structural_quality  # noqa: E402
from judge.backends import Backend  # noqa: E402

VENV_PY = REPO / ".venv-py310" / "bin" / "python"
QC = REPO / "scripts" / "qc.py"
LEX = structural_quality.load_lexicon()


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ── backend selection (independence: different family than the curator) ─────────

def make_backend(provider: str | None = None) -> tuple[Backend | None, str]:
    """Pick a judge backend. Returns (backend, note). Curator defaults to Claude, so we
    prefer OpenAI for cross-family independence; fall back to a non-Opus Claude model with
    a reduced-independence note; None when no key is available."""
    from judge.backends import AnthropicBackend, OpenAIBackend
    prov = provider or os.environ.get("DMDB_JUDGE_PROVIDER")
    has_a = bool(os.environ.get("ANTHROPIC_API_KEY"))
    has_o = bool(os.environ.get("OPENAI_API_KEY"))

    if prov == "openai" or (prov is None and has_o):
        if not has_o:
            return None, "OPENAI_API_KEY not set"
        return OpenAIBackend(os.environ.get("DMDB_JUDGE_MODEL", "gpt-5")), "judge=openai (cross-family vs Claude curator)"
    if prov == "anthropic" or (prov is None and has_a):
        if not has_a:
            return None, "ANTHROPIC_API_KEY not set"
        model = os.environ.get("DMDB_JUDGE_MODEL", "claude-sonnet-4-6")
        note = ("judge=anthropic; shares the curator's family — independence reduced. "
                "Set OPENAI_API_KEY + DMDB_JUDGE_PROVIDER=openai for cross-family checking.")
        return AnthropicBackend(model), note
    return None, "no judge API key (ANTHROPIC_API_KEY / OPENAI_API_KEY) — semantic layers not run"


# ── syntactic gate ──────────────────────────────────────────────────────────

def run_qc(path_file: Path) -> dict:
    """Run the 4-layer gate offline; return {layers:{n:bool|None}, overall_pass:bool}."""
    proc = subprocess.run([_py(), str(QC), "--json", "--offline", str(path_file)],
                          capture_output=True, text=True)
    layers: dict[int, bool] = {}
    overall = None
    try:
        data = json.loads(proc.stdout)
        for r in data.get("results", []):
            layers[r["layer"]] = (r["exit_code"] == 0)
        overall = data.get("overall_pass")
    except Exception:
        overall = (proc.returncode == 0)
    return {"layers": layers, "overall_pass": overall, "raw_exit": proc.returncode}


# ── semantic scoring helpers ──────────────────────────────────────────────────

def edge_faithfulness(edge_verdicts: list[dict] | None) -> dict:
    """Aggregate per-evidence re-derived labels into a faithfulness score."""
    if not edge_verdicts:
        return {"status": "not_run"}
    n_ev = n_support = n_agree = n_abstain = 0
    flagged = []
    for ev in edge_verdicts:
        if ev.get("skipped"):
            continue
        v = ev.get("verdict", {}) or {}
        for verd in (v.get("verdicts") or []):
            n_ev += 1
            red = (verd.get("rederived_supports") or "").upper()
            if red == "SUPPORT":
                n_support += 1
            if verd.get("agrees_with_curator") is True:
                n_agree += 1
            checks = verd.get("checks", {}) or {}
            if any((c or {}).get("result") == "abstain" for c in checks.values()):
                n_abstain += 1
            if red and red != "SUPPORT":
                flagged.append({
                    "edge": f"{ev.get('edge', {}).get('subject', {}).get('name')} --"
                            f"{ev.get('edge', {}).get('predicate')}--> "
                            f"{ev.get('edge', {}).get('object', {}).get('name')}",
                    "reference": verd.get("reference"),
                    "rederived_supports": red,
                    "note": verd.get("note"),
                })
    return {
        "status": "run",
        "n_evidence": n_ev,
        "n_support": n_support,
        "support_fraction": round(n_support / n_ev, 3) if n_ev else None,
        "n_agree_with_curator": n_agree,
        "agreement_fraction": round(n_agree / n_ev, 3) if n_ev else None,
        "n_with_abstain": n_abstain,
        "flagged_edges": flagged,
    }


# ── the profile ────────────────────────────────────────────────────────────────

def quality_profile(path_file: str, *, run_llm: bool = True, backend: Backend | None = None,
                    max_iters: int = 6, use_cache: bool = True) -> dict:
    p = Path(path_file)
    doc = yaml.safe_load(p.read_text())
    qc = run_qc(p)
    struct = structural_quality.analyze(p, LEX)

    flags = struct.get("flags", [])
    has = lambda code: any(f["code"] == code for f in flags)
    L = qc["layers"]
    hard_gates = {
        "schema": L.get(1),
        "ontology": L.get(2),
        "predicate_enum": L.get(3),
        "verbatim_evidence": L.get(4),                 # None for legacy (Layer 4 not run)
        "connectivity": (not has("connectivity")),
        "net_polarity_negative": (struct.get("polarity") == "coherent"),
    }
    hard_fail = any(v is False for v in hard_gates.values())

    semantic: dict = {"status": "not_run"}
    edge_verdicts = None
    path_verdict = None
    if run_llm and backend is not None:
        from judge.edge_evidence_judge import judge_edges
        from judge.path_coherence_judge import judge_path
        edge_verdicts = judge_edges(doc, backend, max_iters=max_iters, use_cache=use_cache)
        path_verdict = judge_path(doc, struct, edge_verdicts, backend, max_iters=max_iters, use_cache=use_cache)
        semantic = {
            "status": "run",
            "backend": backend.name,
            "model": getattr(backend, "model", None),
            "edge_faithfulness": edge_faithfulness(edge_verdicts),
            "path_coherence": path_verdict.get("verdict"),
            "edge_verdicts": edge_verdicts,
        }
    else:
        semantic["edge_faithfulness"] = {"status": "not_run"}

    # overall verdict. The 5 framework hard gates reject; non-gate structural HARD
    # flags (type_violation, short_circuit, ...) are high-precision "act on these"
    # errors that warrant review even before the semantic layer runs.
    struct_hard = (struct.get("severity_counts") or {}).get("HARD", 0)
    if hard_fail:
        overall = "reject"
    elif semantic["status"] == "run":
        pv = (path_verdict or {}).get("verdict", {}) or {}
        overall = (pv.get("overall", {}) or {}).get("verdict", "review")
    elif struct_hard > 0:
        overall = "review_structural"
    else:
        overall = "syntactic_pass_semantic_pending"

    return {
        "file": struct.get("file"),
        "id": struct.get("id"),
        "hard_gates": hard_gates,
        "hard_gate_failed": hard_fail,
        "structural": {
            "polarity": struct.get("polarity"),
            "severity_counts": struct.get("severity_counts"),
            "flags": flags,
            "n_nodes": struct.get("n_nodes"), "n_edges": struct.get("n_edges"),
        },
        "semantic": semantic,
        "overall": overall,
    }


# ── CLI ──────────────────────────────────────────────────────────────────────

def _iter_files(targets):
    out = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            out.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
        elif p.is_file():
            out.append(p)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", nargs="+", help="path YAML file(s) or directory")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--no-llm", action="store_true", help="deterministic layers only")
    ap.add_argument("--provider", choices=("anthropic", "openai"), help="force judge provider")
    ap.add_argument("--max-iters", type=int, default=6)
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    backend, note = (None, "disabled (--no-llm)") if args.no_llm else make_backend(args.provider)
    files = _iter_files(args.targets)
    profiles = [quality_profile(str(f), run_llm=not args.no_llm, backend=backend,
                                max_iters=args.max_iters, use_cache=not args.no_cache) for f in files]

    if args.json:
        print(json.dumps({"judge": note, "profiles": profiles}, indent=2, default=str))
    else:
        print(f"judge backend: {note}\n")
        for pr in profiles:
            verdict = pr["overall"].upper()
            print(f"[{verdict}] {pr['id']}  (polarity={pr['structural']['polarity']}, "
                  f"HARD={pr['structural']['severity_counts'].get('HARD', 0)})")
            for k, v in pr["hard_gates"].items():
                mark = {True: "pass", False: "FAIL", None: "n/a"}[v]
                print(f"    gate {k:<22} {mark}")
            ef = pr["semantic"].get("edge_faithfulness", {})
            if ef.get("status") == "run":
                print(f"    edge-faithfulness: {ef['n_support']}/{ef['n_evidence']} re-derived SUPPORT "
                      f"(agreement {ef.get('agreement_fraction')})")
                for fe in ef.get("flagged_edges", []):
                    print(f"      ⚑ {fe['edge']}  -> {fe['rederived_supports']}  ({fe.get('note')})")
            elif pr["semantic"]["status"] != "run":
                print("    semantic layers: not run")
    return 1 if any(pr["hard_gate_failed"] for pr in profiles) else 0


if __name__ == "__main__":
    sys.exit(main())
