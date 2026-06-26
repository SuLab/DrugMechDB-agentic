"""
Path-coherence judge (Layers 6/7) — judges the chain as a whole.

Builds the input the prompt spec (scripts/quality/prompts/path_coherence_judge.md)
expects: the graph, the ordered path, the deterministic structural report, the
per-edge verdicts from the edge judge, and the gold path (if any). Returns one
verdict bundle (accepted MoA, net-effect, missing/wrong step, primacy, gold cmp).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .backends import Backend, Tool
from .edge_evidence_judge import _node_index, _path_context
from .grounding import default_tools
from .runner import run_judge

HERE = Path(__file__).resolve().parent
PROMPT = HERE.parent / "prompts" / "path_coherence_judge.md"


def build_path_input(
    doc: dict,
    structural_report: dict | None,
    edge_verdicts: list[dict] | None,
    gold_path: dict | None = None,
) -> dict:
    nodes = _node_index(doc)
    g = doc.get("graph", {}) or {}
    sr = structural_report or {}
    # Compact the per-edge verdicts to what the path judge needs.
    compact = []
    for ev in (edge_verdicts or []):
        v = ev.get("verdict", {})
        edge = ev.get("edge", {})
        compact.append({
            "edge": f"{edge.get('subject', {}).get('name')} --{edge.get('predicate')}--> {edge.get('object', {}).get('name')}",
            "edge_supported": v.get("edge_supported"),
            "verdicts": v.get("verdicts"),
        })
    return {
        "graph": {
            "drug": g.get("drug"), "disease": g.get("disease"),
            "drug_mesh": g.get("drug_mesh"), "disease_mesh": g.get("disease_mesh"),
        },
        "path": _path_context(doc, nodes),
        "structural_report": {
            "polarity": sr.get("polarity"),
            "flags": sr.get("flags", []),
        },
        "edge_verdicts": compact,
        "gold_path": gold_path,
    }


def judge_path(
    doc: dict,
    structural_report: dict | None,
    edge_verdicts: list[dict] | None,
    backend: Backend,
    *,
    gold_path: dict | None = None,
    tools: list[Tool] | None = None,
    max_iters: int = 6,
    use_cache: bool = True,
) -> dict:
    tools = tools if tools is not None else default_tools()
    inp = build_path_input(doc, structural_report, edge_verdicts, gold_path)
    return run_judge(PROMPT, inp, tools, backend, max_iters=max_iters, use_cache=use_cache)
