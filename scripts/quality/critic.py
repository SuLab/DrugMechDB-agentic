"""
Semantic critic — the in-session gate that runs AFTER the deterministic QC gate
(scripts/qc.py Layers 1-4) passes, and BEFORE the path is sent for a PR.

Pipeline position (see .claude/commands/curate.md):

    curate -> deterministic QC (1-4, incl. verbatim) -> [THIS] semantic critic
           -> (loop back to curate on RE_CURATE, capped) -> delete full text -> PR

What it does that the deterministic layer cannot:
  - re-derives each edge's evidence support INDEPENDENTLY, grounding in ChEMBL and in
    papers it retrieves itself (search_pubmed / read_abstract / read_fulltext) — i.e.
    knowledge BEYOND the curator's cited snippets. cite-or-abstain.
  - judges the chain as a whole (accepted MoA, net direction, missing/wrong step).

Two firewalls (judge/grounding.py critic_tools):
  - it reads the curator's cited cache READ-ONLY and never writes references_cache/;
  - its independent reading is IN MEMORY and is never committed — only the list of
    consulted source IDs is recorded, in the sidecar.

Two outputs:
  - the agent-facing FLAGS report (stdout / --json): per flagged edge, WHAT is wrong
    (never the fix, never which source to use) + the overall verdict. This is what the
    curation agent acts on.
  - the committed provenance SIDECAR provenance/<id>.semantic_review.yaml: the full
    audit (verdicts, grounding, every independent source consulted). The paper bodies
    are never committed — only their identifiers.

Verdict ∈ ACCEPT / RE_CURATE / ESCALATE / ABSTAIN. RE_CURATE means loop back to
/curate; after --max-rounds it becomes ESCALATE (hold for human). REFUTE /
WRONG_STATEMENT findings escalate immediately (curator territory).

Usage:
    python scripts/quality/critic.py kb/paths/<file>.yaml
    python scripts/quality/critic.py <file> --round 2 --max-rounds 3
    python scripts/quality/critic.py <file> --json
Exit: 0 = ACCEPT · 1 = RE_CURATE/ESCALATE · 2 = ABSTAIN or could-not-run.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent          # scripts/quality
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))                    # so `import quality_profile` / `judge.*` resolve

import quality_profile as qp                      # noqa: E402  (run_qc, make_backend)
import structural_quality                         # noqa: E402
from judge.edge_evidence_judge import judge_edges  # noqa: E402
from judge.path_coherence_judge import judge_path  # noqa: E402
from judge.grounding import critic_tools           # noqa: E402

PROVENANCE_DIR = REPO / "provenance"
LEX = structural_quality.load_lexicon()

# Re-derived support labels that mean "the curator's edge as written is wrong on the
# facts" — curator territory, escalate to a human rather than auto-loop.
_ESCALATE_SUPPORTS = {"REFUTE", "WRONG_STATEMENT"}
# Labels that mean "the evidence doesn't establish the edge" — re-source (loop).
_RECURATE_SUPPORTS = {"PARTIAL", "NO_EVIDENCE"}


def _curator_pmids(doc: dict) -> set[str]:
    """Every PMID the curator cited (so we can prove the critic grounded beyond them)."""
    out: set[str] = set()
    for link in doc.get("links") or []:
        for ev in (link.get("evidence") or []):
            ref = ev.get("reference")
            if ref:
                out.add(str(ref))
    return out


def _consulted_independent_sources(bundles: list[dict], path_bundle: dict, curator: set[str]) -> list[str]:
    """Collect the source IDs the critic actually retrieved, minus the curator's cited
    set — the audit trail that the critic grounded in evidence BEYOND the curator."""
    found: set[str] = set()
    for b in [*bundles, path_bundle]:
        for call in (b.get("tool_calls") or []):
            name, inp = call.get("name"), (call.get("input") or {})
            if name in ("read_abstract", "read_fulltext"):
                ref = inp.get("reference")
                if ref:
                    found.add(str(ref))
            elif name == "chembl_get_mechanism":
                drug = inp.get("drug")
                if drug:
                    found.add(f"ChEMBL:{drug}")
    return sorted(found - curator)


def _edge_str(edge: dict) -> str:
    s = (edge.get("subject") or {}).get("name") or (edge.get("subject") or {}).get("id")
    o = (edge.get("object") or {}).get("name") or (edge.get("object") or {}).get("id")
    return f"{s} --{edge.get('predicate')}--> {o}"


def _flag_edges(edge_bundles: list[dict]) -> tuple[list[dict], list[dict], set[str]]:
    """Return (edge_reviews_for_sidecar, flags_for_curator, rederived_support_labels)."""
    reviews: list[dict] = []
    flags: list[dict] = []
    labels: set[str] = set()
    for b in edge_bundles:
        if b.get("skipped"):
            continue
        edge = b.get("edge", {})
        es = _edge_str(edge)
        v = b.get("verdict", {}) or {}
        for verd in (v.get("verdicts") or []):
            red = (verd.get("rederived_supports") or "").upper()
            if red:
                labels.add(red)
            review = {
                "edge": es,
                "reference": verd.get("reference"),
                "rederived_supports": red or None,
                "agrees_with_curator": verd.get("agrees_with_curator"),
                "issue": verd.get("issue_for_curator"),
                "grounding": json.dumps(verd.get("independent_grounding"), default=str)
                             if verd.get("independent_grounding") else verd.get("note"),
                "confidence": verd.get("confidence"),
            }
            reviews.append({k: val for k, val in review.items() if val is not None})
            if red and red != "SUPPORT":
                flags.append({"edge": es,
                              "issue": verd.get("issue_for_curator")
                              or "the cited evidence does not establish this edge as written"})
    return reviews, flags, labels


def run_critic(path_file: str, backend, *, round_no: int = 1, max_rounds: int = 3,
               max_iters: int = 6, use_cache: bool = True, require_qc: bool = True) -> dict:
    p = Path(path_file)
    doc = yaml.safe_load(p.read_text())
    record_id = (doc.get("graph") or {}).get("_id") or p.stem

    # Precondition: deterministic QC must pass — don't spend judge tokens on a path
    # that hasn't cleared Layers 1-4 yet.
    if require_qc:
        qc = qp.run_qc(p)
        if not qc.get("overall_pass"):
            return {"record_id": record_id, "verdict": "QC_NOT_PASSED",
                    "note": "Run scripts/qc.py --profile ai_curated and fix Layers 1-4 first.",
                    "qc_layers": qc.get("layers")}

    struct = structural_quality.analyze(p, LEX)
    tools = critic_tools()
    edge_bundles = judge_edges(doc, backend, tools=tools, max_iters=max_iters, use_cache=use_cache)
    path_bundle = judge_path(doc, struct, edge_bundles, backend, tools=tools,
                             max_iters=max_iters, use_cache=use_cache)

    edge_reviews, flags, labels = _flag_edges(edge_bundles)
    pv = path_bundle.get("verdict", {}) or {}
    path_overall = ((pv.get("overall") or {}).get("verdict") or "").lower()
    path_issue = pv.get("issue_for_curator")
    path_summary = (pv.get("overall") or {}).get("summary") or ""

    # ── derive the disposition ──────────────────────────────────────────────
    escalate_now = bool(labels & _ESCALATE_SUPPORTS)               # factual contradiction
    edge_problem = bool(labels & _RECURATE_SUPPORTS) or bool(flags)
    path_problem = path_overall in ("revise", "reject")
    all_abstain = bool(edge_reviews) and all(
        (r.get("rederived_supports") is None) for r in edge_reviews)

    if escalate_now:
        verdict = "ESCALATE"
    elif edge_problem or path_problem:
        verdict = "RE_CURATE" if round_no < max_rounds else "ESCALATE"
    elif path_overall == "abstain" or all_abstain:
        verdict = "ABSTAIN"
    else:
        verdict = "ACCEPT"

    consulted = _consulted_independent_sources(edge_bundles, path_bundle, _curator_pmids(doc))

    summary_bits = []
    if path_summary:
        summary_bits.append(path_summary)
    if escalate_now:
        summary_bits.append("An edge's evidence contradicts the claim (curator territory).")
    summary = " ".join(summary_bits) or "No semantic problems found."

    # ── write the committed provenance sidecar (full audit, no paper bodies) ──
    model = getattr(backend, "model", backend.name)
    sidecar = {
        "record_id": record_id,
        "reviewed_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "critic_model": model,
        "critic_provider": backend.name,
        "rounds": round_no,
        "overall_verdict": verdict,
        "overall_summary": summary,
        "consulted_independent_sources": consulted,
        "edge_reviews": edge_reviews,
    }
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
    sidecar_path = PROVENANCE_DIR / f"{record_id}.semantic_review.yaml"
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True))

    return {
        "record_id": record_id,
        "verdict": verdict,
        "round": round_no,
        "max_rounds": max_rounds,
        "flags": flags,                        # agent-facing: WHAT, never the fix/source
        "path_issue": path_issue if (path_problem and verdict != "ACCEPT") else None,
        "n_independent_sources": len(consulted),
        "sidecar": str(sidecar_path.relative_to(REPO)),
        "summary": summary,
    }


# ── agent-facing report ─────────────────────────────────────────────────────

_NEXT_STEP = {
    "ACCEPT": "Path passes semantic review. Delete full text (pubmed_fetch.py strip-fulltext --all) and open the PR.",
    "RE_CURATE": "Re-run /curate addressing the flags above, then re-run the critic with --round {next}. "
                 "The critic will not tell you which source to use — re-source independently.",
    "ESCALATE": "Round cap reached or a factual contradiction was found. Mark the offending edge(s) "
                "supports: NO_EVIDENCE with an explanation and hand off to a human reviewer.",
    "ABSTAIN": "The critic could not independently ground a load-bearing judgment. Hand off to a human reviewer.",
    "QC_NOT_PASSED": "Deterministic QC has not passed yet; fix Layers 1-4 before the semantic critic runs.",
}


def _print_report(res: dict) -> None:
    v = res["verdict"]
    print(f"=== SEMANTIC CRITIC — {res['record_id']} ===")
    if v == "QC_NOT_PASSED":
        print(f"[{v}] {res.get('note')}")
        return
    print(f"Verdict: {v}   (round {res['round']}/{res['max_rounds']}, "
          f"{res['n_independent_sources']} independent source(s) consulted — see {res['sidecar']})")
    print(f"Summary: {res['summary']}")
    if res.get("flags"):
        print("\nFlagged edges (re-source these — the critic states the problem, NOT the fix or which paper to use):")
        for f in res["flags"]:
            print(f"  ⚑ {f['edge']}")
            print(f"      issue: {f['issue']}")
    if res.get("path_issue"):
        print(f"\nPath-level issue: {res['path_issue']}")
    nxt = _NEXT_STEP.get(v, "")
    if v == "RE_CURATE":
        nxt = nxt.replace("{next}", str(res["round"] + 1))
    print(f"\nNext step: {nxt}")


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path_file", help="kb/paths/<file>.yaml to review")
    ap.add_argument("--provider", choices=("anthropic", "openai"), help="force critic provider")
    ap.add_argument("--round", type=int, default=1, dest="round_no",
                    help="which curate↔critic round this is (1-based)")
    ap.add_argument("--max-rounds", type=int, default=3,
                    help="after this many rounds a still-flagged path ESCALATEs to human")
    ap.add_argument("--max-iters", type=int, default=6, help="tool-loop cap per judge call")
    ap.add_argument("--no-cache", action="store_true")
    ap.add_argument("--skip-qc-precheck", action="store_true",
                    help="don't re-run the QC gate first (assume the caller already did)")
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    backend, note = qp.make_backend(args.provider)
    if backend is None:
        print(f"semantic critic cannot run: {note}", file=sys.stderr)
        return 2

    res = run_critic(args.path_file, backend, round_no=args.round_no, max_rounds=args.max_rounds,
                     max_iters=args.max_iters, use_cache=not args.no_cache,
                     require_qc=not args.skip_qc_precheck)

    if args.json:
        print(json.dumps(res, indent=2, default=str))
    else:
        _print_report(res)

    return {"ACCEPT": 0, "RE_CURATE": 1, "ESCALATE": 1,
            "ABSTAIN": 2, "QC_NOT_PASSED": 2}.get(res["verdict"], 1)


if __name__ == "__main__":
    sys.exit(main())
