"""
Edge-evidence judge (Layer 5) — runs the atomic faithfulness ladder per edge.

Builds the input the prompt spec (scripts/quality/prompts/edge_evidence_judge.md)
expects from a path YAML, drives it through a backend with the grounding tools, and
returns one verdict bundle per edge. The judge re-derives EvidenceSupportEnum
independently and cites grounding (or abstains).
"""

from __future__ import annotations

import hashlib
import json
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


def _edge_label(subj: dict, pred: str | None, obj: dict) -> str:
    """The human edge string the critic uses when it records a flag — so a prior
    round's edge flag can be matched back to the edge it was raised on."""
    s = subj.get("name") or subj.get("id")
    o = obj.get("name") or obj.get("id")
    return f"{s} --{pred}--> {o}"


def _prior_flags_for_edge(edge_label: str, prior_flags: list[dict] | None) -> list[dict]:
    """The subset of prior-round edge flags raised on THIS edge (matched by label)."""
    return [{"issue": f.get("issue")} for f in (prior_flags or [])
            if f.get("edge") == edge_label]


def build_edge_inputs(doc: dict, prior_flags: list[dict] | None = None) -> list[dict]:
    """One input object per edge, in the shape edge_evidence_judge.md expects.

    When `prior_flags` (the previous round's agent-facing edge flags) are supplied,
    each edge that was flagged last round carries its prior flag(s) as
    `prior_round_flags` so the judge can independently re-verify (re-grounded) whether
    the issue is now resolved / partially resolved / unresolved."""
    nodes = _node_index(doc)
    ctx = _path_context(doc, nodes)
    inputs = []
    for e in doc.get("links", []) or []:
        subj = nodes.get(e.get("source"), {"id": e.get("source"), "name": None, "label": None})
        obj = nodes.get(e.get("target"), {"id": e.get("target"), "name": None, "label": None})
        pred = e.get("key")
        inp = {
            "edge": {"subject": subj, "predicate": pred, "object": obj},
            "predicate_meaning": f"The subject '{pred}' the object.",
            "path_context": ctx,
            "evidence": [
                {k: ev.get(k) for k in ("reference", "snippet", "supports", "evidence_source", "explanation") if k in ev}
                for ev in (e.get("evidence") or [])
            ],
        }
        prior = _prior_flags_for_edge(_edge_label(subj, pred, obj), prior_flags)
        if prior:
            inp["prior_round_flags"] = prior
        inputs.append(inp)
    return inputs


def edge_content_hash(inp: dict) -> str:
    """Stable hash of an edge's OWN content (subject/predicate/object + evidence) — NOT
    its path_context. A byte-identical edge hashes the same across rounds, so an unchanged
    edge's prior verdict can be carried forward instead of re-grounded."""
    payload = {"edge": inp.get("edge"), "evidence": inp.get("evidence")}
    return hashlib.sha256(
        json.dumps(payload, sort_keys=True, default=str).encode("utf-8")).hexdigest()[:16]


def judge_edges(
    doc: dict,
    backend: Backend,
    tools: list[Tool] | None = None,
    *,
    prior_flags: list[dict] | None = None,
    reuse_map: dict | None = None,
    max_iters: int = 6,
    use_cache: bool = True,
) -> list[dict]:
    """Return a list of {edge, verdict-bundle} for every edge that has evidence.

    `prior_flags` (previous round's edge flags) enables fix-tracking: a flagged edge
    receives its prior flag(s) and the judge re-verifies resolution against evidence.

    `reuse_map` ({edge_hash: prior verdict bundle}) enables targeted re-judgment: an edge
    whose content is byte-identical to a prior round AND was not flagged last round is
    carried forward (no LLM call). Changed edges, new edges, and previously-flagged edges
    are always re-judged fresh (never trust that a fix landed)."""
    tools = tools if tools is not None else default_tools()
    reuse_map = reuse_map or {}
    out = []
    for inp in build_edge_inputs(doc, prior_flags):
        if not inp["evidence"]:
            out.append({
                "edge": inp["edge"],
                "verdict": {"edge_supported": None, "note": "no evidence attached (legacy edge)"},
                "skipped": True,
            })
            continue
        h = edge_content_hash(inp)
        prior = reuse_map.get(h)
        if prior is not None and not inp.get("prior_round_flags"):
            # Unchanged edge that was clean last round -> carry its verdict forward.
            reused = dict(prior)
            reused["edge"] = inp["edge"]
            reused["edge_hash"] = h
            reused["reused"] = True
            out.append(reused)
            continue
        bundle = run_judge(PROMPT, inp, tools, backend, max_iters=max_iters, use_cache=use_cache)
        bundle["edge"] = inp["edge"]
        bundle["edge_hash"] = h
        bundle["reused"] = False
        out.append(bundle)
    return out


def judge_path_file(path_file: str, backend: Backend, **kw) -> list[dict]:
    doc = yaml.safe_load(Path(path_file).read_text())
    return judge_edges(doc, backend, **kw)
