"""
Semantic critic — the in-session gate that runs AFTER the deterministic QC gate
(scripts/qc.py Layers 1-4) passes, and BEFORE the path is sent for a PR.

Pipeline position (see .claude/commands/curate.md):

    curate -> deterministic QC (1-4, incl. verbatim) -> [THIS] semantic critic
           -> (loop back to curate on RE_CURATE, capped) -> delete full text -> PR

What it does that the deterministic layer cannot:
  - re-derives each edge's evidence support INDEPENDENTLY, grounding in ChEMBL and in
    sources it retrieves itself over the SAME trusted multi-source layer the curator uses
    (search_pubmed / read_abstract / read_fulltext, plus search_evidence / read_evidence
    over ChEMBL / ClinicalTrials / bioRxiv / medRxiv / DrugBank) — i.e. knowledge BEYOND
    the curator's cited snippets. cite-or-abstain; no web search.
  - judges the chain as a whole (accepted MoA, net direction, missing/wrong step).

Fix-tracking (flags are stateful; judgment is not): on round > 1 the critic loads the
PRIOR round's flags from the sidecar and hands them to the judges, which independently
RE-GROUND whether each is resolved / partially_resolved / unresolved (never trusting that
the fix landed), while still running the full independent review for NEW issues. The
sidecar ACCUMULATES a per-round history, so an ESCALATE preserves what was flagged and
tried each round for the human reviewer.

The criteria this scores against are the shared checklist in docs/path_quality_rubric.md
(§A per-edge ladder, §B path validity) — the same rubric the LLM judge prompts and human
review use; its design rationale is docs/path_quality_framework.md.

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
            if name in ("read_abstract", "read_fulltext", "read_evidence"):
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


# ── fix-tracking memory: flags are stateful, judgment stays stateless ──────────
#
# The maintainer's design: the critic re-grounds every judgment from scratch each
# round (it never trusts that a fix landed), but the FLAGS it raised carry over.
# When round_no > 1 the prior round's flags are loaded from the sidecar history and
# handed to the judges, which independently re-verify — against re-read evidence —
# whether each is now resolved / partially_resolved / unresolved.

def _load_prior_rounds(sidecar_path: Path) -> list[dict]:
    """The accumulated per-round history from a prior sidecar (empty if none)."""
    if not sidecar_path.exists():
        return []
    try:
        prev = yaml.safe_load(sidecar_path.read_text()) or {}
    except Exception:
        return []
    rounds = prev.get("rounds")
    return list(rounds) if isinstance(rounds, list) else []


def _prior_round_flags(prior_rounds: list[dict], round_no: int) -> tuple[list[dict], str | None]:
    """The previous round's agent-facing flags to re-verify this round.

    Returns (edge_flags, path_issue) from the entry for round_no-1, falling back to
    the latest recorded round. Empty/None when there is no prior round."""
    if not prior_rounds:
        return [], None
    target = next((r for r in prior_rounds if r.get("round") == round_no - 1), None)
    if target is None:
        target = prior_rounds[-1]
    return list(target.get("flags") or []), target.get("path_issue")


def _collect_prior_flag_status(edge_bundles: list[dict], path_bundle: dict) -> list[dict]:
    """Aggregate the judges' re-grounded resolution of each prior-round flag.

    The status is JUDGED this round (the judges re-read the evidence with the prior
    flags in their input), never inferred from memory. Each judge emits an optional
    `prior_flag_resolution` list; this rolls them up for the critic's report + audit."""
    _VALID = {"resolved", "partially_resolved", "unresolved"}
    out: list[dict] = []

    def _pull(v: dict, scope: str) -> None:
        for r in (v.get("prior_flag_resolution") or []):
            if not isinstance(r, dict):
                continue
            status = (r.get("status") or "").lower()
            out.append({
                "scope": scope,
                "flag": r.get("flag") or r.get("prior_flag") or r.get("issue"),
                "status": status if status in _VALID else "unresolved",
                "basis": r.get("basis") or r.get("note"),
            })

    for b in edge_bundles:
        if b.get("skipped"):
            continue
        _pull(b.get("verdict", {}) or {}, "edge")
    _pull(path_bundle.get("verdict", {}) or {}, "path")
    return out


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

    # The structural report is READ for context (passed to judge_path below), but its
    # flags do NOT force the critic's verdict — the critic reverts to its own edge/path
    # LLM judgment. The deterministic gate owns the (binary) structural disposition.
    struct = structural_quality.analyze(p, LEX)

    # Fix-tracking: on a later round, load the flags the critic raised previously so
    # the judges can independently re-verify (re-grounded) whether each was resolved.
    sidecar_path = PROVENANCE_DIR / f"{record_id}.semantic_review.yaml"
    prior_rounds = _load_prior_rounds(sidecar_path)
    prior_edge_flags: list[dict] = []
    prior_path_issue: str | None = None
    if round_no > 1:
        prior_edge_flags, prior_path_issue = _prior_round_flags(prior_rounds, round_no)
    path_prior = [{"issue": prior_path_issue}] if prior_path_issue else None

    tools = critic_tools()
    edge_bundles = judge_edges(doc, backend, tools=tools, prior_flags=prior_edge_flags or None,
                               max_iters=max_iters, use_cache=use_cache)
    path_bundle = judge_path(doc, struct, edge_bundles, backend, tools=tools,
                             prior_flags=path_prior, max_iters=max_iters, use_cache=use_cache)

    edge_reviews, flags, labels = _flag_edges(edge_bundles)
    prior_flag_status = _collect_prior_flag_status(edge_bundles, path_bundle)
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
    # The sidecar ACCUMULATES a per-round history rather than overwriting, so on
    # ESCALATE (max_rounds exhausted) a human sees what was flagged each round and
    # what the curator tried in response. Re-running the same round replaces only
    # that round's entry (idempotent).
    model = getattr(backend, "model", backend.name)
    now_iso = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")
    reported_path_issue = path_issue if (path_problem and verdict != "ACCEPT") else None
    round_entry = {
        "round": round_no,
        "reviewed_at": now_iso,
        "verdict": verdict,
        "summary": summary,
        "flags": flags,                        # agent-facing: WHAT, never the fix/source
        "path_issue": reported_path_issue,
        "prior_flag_status": prior_flag_status,   # re-grounded resolution vs the prior round
        "consulted_independent_sources": consulted,
        "edge_reviews": edge_reviews,
    }
    history = [r for r in prior_rounds if r.get("round") != round_no] + [round_entry]
    history.sort(key=lambda r: r.get("round", 0))

    sidecar = {
        "record_id": record_id,
        "critic_model": model,
        "critic_provider": backend.name,
        "first_reviewed_at": history[0].get("reviewed_at", now_iso),
        "last_reviewed_at": now_iso,
        "current_round": round_no,
        "max_rounds": max_rounds,
        "overall_verdict": verdict,            # latest round's verdict (pr_labels.py reads this)
        "overall_summary": summary,
        "rounds": history,
    }
    PROVENANCE_DIR.mkdir(parents=True, exist_ok=True)
    sidecar_path.write_text(yaml.safe_dump(sidecar, sort_keys=False, allow_unicode=True))
    try:
        sidecar_rel = str(sidecar_path.relative_to(REPO))
    except ValueError:                          # dir redirected outside the repo (tests)
        sidecar_rel = str(sidecar_path)

    return {
        "record_id": record_id,
        "verdict": verdict,
        "round": round_no,
        "max_rounds": max_rounds,
        "flags": flags,                        # agent-facing: WHAT, never the fix/source
        "path_issue": reported_path_issue,
        "prior_flag_status": prior_flag_status,   # fix-tracking vs the prior round
        "n_independent_sources": len(consulted),
        "sidecar": sidecar_rel,
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
    if res.get("prior_flag_status"):
        print("\nPrior-round flags, re-verified against evidence this round:")
        for r in res["prior_flag_status"]:
            print(f"  [{r.get('status')}] ({r.get('scope')}) {r.get('flag')}")
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
    ap.add_argument("--provider", choices=("anthropic",), default="anthropic",
                    help="critic provider (Anthropic-only)")
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
