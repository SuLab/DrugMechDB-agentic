"""
scripts/quality/gate.py — the ENFORCED curation gate (issue #7).

The deterministic structural checks used to be report-only. This module turns them
into a GATE a curation must pass, and returns ONE actionable, curator-facing feedback
report combining every check:

  * the QC gate            — scripts/qc.py Layers 1-4 (schema / ontology / predicate / verbatim)
  * the structural checks  — scripts/quality/structural_quality.py (topology / polarity / ...)

Unlike quality_profile.py (which SCORES a path into a profile) this module GATES it: a
curation that fails is bounced back to the curator. Two design rules the maintainer set:

  1. BOTH checkers always run, and the structural checks run EVEN IF QC fails (no
     short-circuit). The curator sees EVERY problem at once instead of fixing them one
     bounce at a time.
  2. The UNION of all problems is returned as a single report. WHAT is wrong is stated
     in terms of the path's own entities/edges, obeying the flags-not-fixes firewall
     (evidence/coverage issues never name the fix/PMID/source; a structural
     shortcut/redundancy edge MAY be named for removal — see path_coherence_judge.md).

Disposition (severity is owned by structural_quality.HARD_BLOCKING_CHECKS — the single
point to adjust; see issue #28):

  * a QC layer failure OR a HARD structural flag        -> RE_CURATE  (deterministic bounce)
  * only SOFT structural flags (net_polarity / type_violation) -> handed to the semantic
    critic (scripts/quality/critic.py), which decides whether the flag is a real problem
    and, if so, routes it back to the curator with context
  * nothing flagged                                     -> PASS

The curate<->critic loop is capped by the critic's own --round / --max-rounds mechanism.

Clean callable for the (headless) curation engine:
    passed, feedback = run_gate("kb/paths/X.yaml")     # passed: bool
    print(feedback.render())                           # curator-facing text
    feedback.to_dict()                                 # machine-readable

Usage:
    python scripts/quality/gate.py kb/paths/<file>.yaml
    python scripts/quality/gate.py <file> --json
    python scripts/quality/gate.py <file> --no-critic          # deterministic layers only
    python scripts/quality/gate.py <file> --round 2 --max-rounds 3
    python scripts/quality/gate.py <file> --online             # let Layer 4 fetch PubMed
Exit: 0 = PASS · 1 = RE_CURATE / ESCALATE (bounce) · 2 = could not run.
"""

from __future__ import annotations

import argparse
import dataclasses
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent          # scripts/quality
REPO = HERE.parent.parent
sys.path.insert(0, str(HERE))                    # so `import structural_quality` / `critic` resolve

import structural_quality                          # noqa: E402
import quality_profile as qp                        # noqa: E402  (reuse make_backend)

QC = REPO / "scripts" / "qc.py"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"
LEX = structural_quality.load_lexicon()

_LAYER_NAMES = {1: "schema", 2: "node ontology", 3: "predicate enum",
                4: "reference (verbatim snippet)"}
# HARD structural codes may name the offending edge / topology fix — a structural
# defect, not a scientific spoiler (firewall exception, per path_coherence_judge.md /
# rubric §B). Codes without a hint (connectivity, cycle) are self-explanatory.
_STRUCTURAL_HINT = {
    "clinical_shortcut": "remove this redundant clinical-outcome bypass edge; keep only the mechanism chain.",
    "short_circuit": "remove the short bypass edge / sub-path; keep only the full mechanism chain.",
    "duplicate_edge": "remove the duplicate edge (keep a single copy).",
    "direct_drug_disease": "the drug connects straight to the disease with no molecular entry point; "
                           "a mechanism path must begin drug -> (a molecular target).",
}


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ── the two deterministic checkers (invoked, never duplicated) ─────────────────

def _summarize_qc_detail(raw: str) -> list[str]:
    """Compact one-line-per-failure summary from a layer's --json `failures` list.

    All four layer scripts emit `{"failures": [{...}]}` where each failure carries a
    `reason`/`message` plus locators (id / key / node_index / edge_index / location).
    Falls back to the raw text lines when the shape is unexpected."""
    raw = (raw or "").strip()
    if not raw:
        return []
    try:
        data = json.loads(raw)
    except Exception:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    fails = data.get("failures") if isinstance(data, dict) else None
    if not isinstance(fails, list) or not fails:
        return [ln.strip() for ln in raw.splitlines() if ln.strip()]
    lines: list[str] = []
    for f in fails:
        if not isinstance(f, dict):
            lines.append(str(f)); continue
        reason = f.get("reason") or f.get("message") or ""
        loc = [f"{k}={f[k]}" for k in ("id", "key", "node_index", "edge_index", "location")
               if f.get(k) is not None]
        prefix = " ".join(loc)
        lines.append((f"{prefix}: {reason}" if prefix else reason).strip())
    return lines


def _run_qc(path_file: Path, *, offline: bool = True) -> dict:
    """Run scripts/qc.py Layers 1-4 and capture per-layer pass/fail + failure detail."""
    cmd = [_py(), str(QC), "--json", str(path_file)]
    if offline:
        cmd.append("--offline")
    proc = subprocess.run(cmd, capture_output=True, text=True)
    layers: dict[int, bool] = {}
    failures: list[dict] = []
    try:
        data = json.loads(proc.stdout)
        for r in data.get("results", []):
            ln, ok = r["layer"], (r["exit_code"] == 0)
            layers[ln] = ok
            if not ok:
                raw = (r.get("output") or "").strip()
                failures.append({"layer": ln, "name": _LAYER_NAMES.get(ln, f"layer {ln}"),
                                 "detail": raw, "detail_lines": _summarize_qc_detail(raw)})
        overall = data.get("overall_pass", proc.returncode == 0)
    except Exception:
        overall = (proc.returncode == 0)
        if not overall:
            raw = (proc.stdout + proc.stderr).strip()
            failures.append({"layer": None, "name": "qc", "detail": raw,
                             "detail_lines": _summarize_qc_detail(raw)})
    return {"layers": layers, "overall_pass": overall, "failures": failures}


def _partition_structural(struct: dict) -> tuple[list[dict], list[dict], list[dict]]:
    """Split structural flags into (hard-bounce, soft->critic, advisory), by CODE.

    Classification is driven by structural_quality.HARD_BLOCKING_CHECKS /
    SOFT_CRITIC_CHECKS — the single point to adjust (issue #28)."""
    hard, soft, advisory = [], [], []
    for f in struct.get("flags", []):
        code = f.get("code")
        if code in structural_quality.HARD_BLOCKING_CHECKS:
            hard.append(f)
        elif code in structural_quality.SOFT_CRITIC_CHECKS:
            soft.append(f)
        else:
            advisory.append(f)
    return hard, soft, advisory


# ── the union feedback report ─────────────────────────────────────────────────

@dataclasses.dataclass
class GateFeedback:
    """The single curator-facing report combining QC + structural (+ critic)."""
    record_id: str
    verdict: str                 # PASS | RE_CURATE | ESCALATE | ABSTAIN | PASS_SOFT_UNADJUDICATED
    passed: bool
    qc_failures: list = dataclasses.field(default_factory=list)
    hard_structural: list = dataclasses.field(default_factory=list)
    soft_structural: list = dataclasses.field(default_factory=list)
    advisory: list = dataclasses.field(default_factory=list)
    critic: dict | None = None

    def to_dict(self) -> dict:
        return {
            "record_id": self.record_id,
            "verdict": self.verdict,
            "passed": self.passed,
            "qc_failures": self.qc_failures,
            "hard_structural": self.hard_structural,
            "soft_structural": self.soft_structural,
            "advisory": self.advisory,
            "critic": self.critic,
        }

    def render(self) -> str:
        out: list[str] = []
        out.append(f"=== CURATION GATE — {self.record_id} ===")
        out.append(f"Verdict: {self.verdict}   ({'PASS' if self.passed else 'BOUNCE — return to curator'})")
        n_problems = len(self.qc_failures) + len(self.hard_structural) + len(self.soft_structural)
        if n_problems == 0 and not self.advisory:
            out.append("No blocking problems found across the QC gate and the structural checks.")
            return "\n".join(out)

        out.append("")
        out.append("All problems found (fix every item before re-submitting — the gate runs")
        out.append("QC and the structural checks together so you see them at once):")

        if self.qc_failures:
            out.append("\n-- QC gate failures (must fix; deterministic bounce) --")
            for f in self.qc_failures:
                tag = f"Layer {f['layer']} ({f['name']})" if f.get("layer") else f["name"]
                out.append(f"  [{tag}]")
                for line in (f.get("detail_lines") or [f.get("detail", "")]):
                    if line and line.strip():
                        out.append(f"      {line.strip()}")

        if self.hard_structural:
            out.append("\n-- HARD structural failures (must fix; deterministic bounce) --")
            for f in self.hard_structural:
                out.append(f"  [{f['code']}] {f['msg']}")
                hint = _STRUCTURAL_HINT.get(f["code"])
                if hint:
                    out.append(f"      -> {hint}")

        if self.soft_structural:
            if self.critic is not None:
                out.append("\n-- SOFT structural flags (adjudicated by the semantic critic) --")
            else:
                out.append("\n-- SOFT structural flags (need semantic review; not auto-bounced) --")
            for f in self.soft_structural:
                out.append(f"  [{f['code']}] {f['msg']}")

        if self.critic is not None:
            out.append("\n-- Semantic critic --")
            out.append(f"  verdict: {self.critic.get('verdict')}   {self.critic.get('summary', '')}".rstrip())
            for f in (self.critic.get("flags") or []):
                out.append(f"  ⚑ {f.get('edge')}")
                out.append(f"      issue: {f.get('issue')}")
            if self.critic.get("path_issue"):
                out.append(f"  path-level issue: {self.critic['path_issue']}")

        if self.advisory:
            out.append("\n-- Advisory (convention/prioritization notes; not blocking) --")
            for f in self.advisory:
                out.append(f"  [{f['code']}] {f['msg']}")

        return "\n".join(out)


# ── the gate ──────────────────────────────────────────────────────────────────

def run_gate(
    path_file: str,
    *,
    backend=None,
    run_critic: bool = True,
    offline: bool = True,
    round_no: int = 1,
    max_rounds: int = 3,
    use_cache: bool = True,
) -> tuple[bool, GateFeedback]:
    """Run the enforced gate on one path file.

    Returns (passed, GateFeedback). QC (Layers 1-4) and the structural checks BOTH run
    and BOTH are always reported (structural runs even when QC fails). A QC failure or a
    HARD structural flag is a deterministic bounce; only-SOFT structural flags are handed
    to the semantic critic (when a judge backend is available) which decides.

    `backend` — a judge backend (from quality_profile.make_backend); pass None (or
    run_critic=False) for a purely deterministic gate with no LLM/network dependency."""
    p = Path(path_file)
    doc = yaml.safe_load(p.read_text())
    record_id = (doc.get("graph") or {}).get("_id") or p.stem

    qc = _run_qc(p, offline=offline)
    struct = structural_quality.analyze(p, LEX)                  # runs regardless of QC
    hard, soft, advisory = _partition_structural(struct)

    hard_bounce = bool(qc["failures"]) or bool(hard)
    critic_res = None

    if hard_bounce:
        # Deterministic reject. Do NOT spend judge tokens — but still surface the SOFT
        # and advisory flags so the curator fixes everything in one pass.
        verdict, passed = "RE_CURATE", False
    elif soft and run_critic and backend is not None:
        # Only SOFT structural flags (and QC clean): hand to the semantic critic.
        import critic as critic_mod
        critic_res = critic_mod.run_critic(
            str(p), backend, round_no=round_no, max_rounds=max_rounds,
            use_cache=use_cache, require_qc=False,   # QC already passed above
        )
        verdict = critic_res.get("verdict", "RE_CURATE")
        passed = (verdict == "ACCEPT")
    elif soft:
        # SOFT flags but no judge available: per the maintainer's rule SOFT never
        # hard-bounces, so the deterministic gate PASSES but the flags are surfaced as
        # needing semantic adjudication (a critic/human must look before merge).
        verdict, passed = "PASS_SOFT_UNADJUDICATED", True
    else:
        verdict, passed = "PASS", True

    critic_view = None
    if critic_res is not None:
        critic_view = {
            "verdict": critic_res.get("verdict"),
            "summary": critic_res.get("summary"),
            "flags": critic_res.get("flags"),
            "structural_flags": critic_res.get("structural_flags"),
            "path_issue": critic_res.get("path_issue"),
            "sidecar": critic_res.get("sidecar"),
        }

    fb = GateFeedback(
        record_id=record_id, verdict=verdict, passed=passed,
        qc_failures=qc["failures"], hard_structural=hard,
        soft_structural=soft, advisory=advisory, critic=critic_view,
    )
    return passed, fb


# ── CLI ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path_file", help="kb/paths/<file>.yaml to gate")
    ap.add_argument("--json", action="store_true", help="machine-readable feedback")
    ap.add_argument("--no-critic", action="store_true",
                    help="deterministic layers only (no LLM critic on SOFT flags)")
    ap.add_argument("--provider", choices=("anthropic", "openai"), help="force critic provider")
    ap.add_argument("--round", type=int, default=1, dest="round_no",
                    help="which curate<->critic round this is (1-based)")
    ap.add_argument("--max-rounds", type=int, default=3,
                    help="after this many rounds a still-flagged path ESCALATEs to human")
    ap.add_argument("--online", action="store_true",
                    help="let Layer 4 fetch PubMed (default: offline against references_cache)")
    ap.add_argument("--no-cache", action="store_true")
    args = ap.parse_args()

    if not Path(args.path_file).is_file():
        print(f"gate: not a file: {args.path_file}", file=sys.stderr)
        return 2

    backend = None
    if not args.no_critic:
        backend, note = qp.make_backend(args.provider)
        if backend is None and not args.json:
            print(f"(note: {note}; SOFT flags will not be critic-adjudicated)\n", file=sys.stderr)

    passed, fb = run_gate(
        args.path_file, backend=backend, run_critic=not args.no_critic,
        offline=not args.online, round_no=args.round_no, max_rounds=args.max_rounds,
        use_cache=not args.no_cache,
    )

    if args.json:
        print(json.dumps(fb.to_dict(), indent=2, default=str))
    else:
        print(fb.render())
    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
