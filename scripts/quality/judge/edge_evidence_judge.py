"""
Edge-evidence judge (Layer 5) — runs the atomic faithfulness ladder per edge.

Builds the input the prompt spec (scripts/quality/prompts/edge_evidence_judge.md)
expects from a path YAML, drives it through a backend with the grounding tools, and
returns one verdict bundle per edge. The judge re-derives EvidenceSupportEnum
independently and cites grounding (or abstains).
"""

from __future__ import annotations

from pathlib import Path

import yaml

from .backends import Backend, Tool
from .grounding import default_tools
from .runner import run_judge

HERE = Path(__file__).resolve().parent
PROMPT = HERE.parent / "prompts" / "edge_evidence_judge.md"


def _node_index(doc: dict) -> dict:
    idx = {}
    for n in doc.get("nodes", []) or []:
        if isinstance(n, dict) and n.get("id"):
            idx[n["id"]] = {"id": n["id"], "name": n.get("name"), "label": n.get("label")}
    return idx


def _path_context(doc: dict, nodes: dict) -> list[str]:
    ctx = []
    for e in doc.get("links", []) or []:
        s = nodes.get(e.get("source"), {}).get("name", e.get("source"))
        t = nodes.get(e.get("target"), {}).get("name", e.get("target"))
        ctx.append(f"{s} --{e.get('key')}--> {t}")
    return ctx


def build_edge_inputs(doc: dict) -> list[dict]:
    """One input object per edge, in the shape edge_evidence_judge.md expects."""
    nodes = _node_index(doc)
    ctx = _path_context(doc, nodes)
    inputs = []
    for e in doc.get("links", []) or []:
        subj = nodes.get(e.get("source"), {"id": e.get("source"), "name": None, "label": None})
        obj = nodes.get(e.get("target"), {"id": e.get("target"), "name": None, "label": None})
        pred = e.get("key")
        inputs.append({
            "edge": {"subject": subj, "predicate": pred, "object": obj},
            "predicate_meaning": f"The subject '{pred}' the object.",
            "path_context": ctx,
            "evidence": [
                {k: ev.get(k) for k in ("reference", "snippet", "supports", "evidence_source", "explanation") if k in ev}
                for ev in (e.get("evidence") or [])
            ],
        })
    return inputs


def judge_edges(
    doc: dict,
    backend: Backend,
    tools: list[Tool] | None = None,
    *,
    max_iters: int = 6,
    use_cache: bool = True,
) -> list[dict]:
    """Return a list of {edge, verdict-bundle} for every edge that has evidence."""
    tools = tools if tools is not None else default_tools()
    out = []
    for inp in build_edge_inputs(doc):
        if not inp["evidence"]:
            out.append({
                "edge": inp["edge"],
                "verdict": {"edge_supported": None, "note": "no evidence attached (legacy edge)"},
                "skipped": True,
            })
            continue
        bundle = run_judge(PROMPT, inp, tools, backend, max_iters=max_iters, use_cache=use_cache)
        bundle["edge"] = inp["edge"]
        out.append(bundle)
    return out


def judge_path_file(path_file: str, backend: Backend, **kw) -> list[dict]:
    doc = yaml.safe_load(Path(path_file).read_text())
    return judge_edges(doc, backend, **kw)
