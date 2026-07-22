"""
scripts/compliance_score.py — deterministic compliance score + keep/reject decision.

Answers one question about a single curated path: *is it good enough to keep?* — and does
so with **zero non-determinism**: no LLM, no network, no semantic critic. It reuses only
the deterministic machinery already in the repo:

  * the 4-layer QC gate      — scripts/qc.py Layers 1-4 (schema / ontology / predicate /
                               verbatim), invoked as a subprocess with `--offline` so
                               Layer 4 is pinned to the committed references_cache/ and
                               never touches the network.
  * the structural checks    — scripts/quality/structural_quality.analyze() (a pure
                               function: topology / polarity / redundancy), imported and
                               called directly.

It deliberately does NOT call the semantic critic (scripts/quality/critic.py) or any judge
backend — those are LLM-driven and non-deterministic, so they can never appear in a
reproducible keep/reject decision. (This module also avoids importing scripts/quality/gate.py
for the same reason: gate.py pulls in quality_profile -> judge.backends, i.e. LLM SDKs.)

────────────────────────────────────────────────────────────────────────────────────────
THE BAR (the maintainer's design; see docs/path_quality_framework.md §2 "quality is a
vector, not a scalar"). Quality is scored as HARD gates + graded SOFT signals; the
keep-line is a maintainer value-judgment, made explicit here:

HARD gates — must ALL pass, else the path is rejected outright:
  * QC Layer 1  (schema)
  * QC Layer 2  (node ontology)
  * QC Layer 3  (predicate enum)
  * QC Layer 4  (verbatim snippet)  — ai_curated profile only; skipped (== not-applicable,
                                      NOT a failure) for legacy paths with no per-edge evidence
  * NO HARD structural flag         — structural_quality.HARD_BLOCKING_CHECKS =
                                      {clinical_shortcut, short_circuit, direct_drug_disease,
                                       connectivity, cycle, duplicate_edge}
  If ANY hard gate fails  ->  tier=REJECT, score=0.0, keep=False.

SOFT signals — graded, they DO NOT auto-reject:
  * SOFT structural flags           — structural_quality.SOFT_CRITIC_CHECKS =
                                      {net_polarity, type_violation}
  Rationale (deliberate): a SOFT flag *may or may not* be a real defect — net polarity can
  be indeterminate from lexicon gaps, and a predicate type violation reads very differently
  with semantic context. The critic / a human adjudicates that downstream. Because this
  module is purely deterministic it CANNOT make that call, so a SOFT flag is never allowed
  to reject on its own; it only lowers the tier to "needs review" and shaves the score.

  (Structural flags that are neither HARD nor SOFT-critic — e.g. length_out_of_range,
  dangling_node, unknown_predicate, noncanonical_start, review_predicate — are convention /
  prioritization *advisories*. They are surfaced in the breakdown for transparency but,
  matching gate.py's partition, do NOT affect tier / score / keep.)

Tiers:
  REJECT            any hard gate fails
  KEEP_WITH_REVIEW  all hard gates pass, >=1 SOFT flag (keepable, but flag for review)
  COMPLIANT         all hard gates pass, 0 SOFT flags

Scalar score in [0, 1]:
  0.0                             if any hard gate fails
  1.0 - min(0.5, 0.1 * n_soft)   otherwise   (each SOFT flag costs 0.1; floor 0.5 so a
                                              keepable path never scores below half)

Keep decision — the "good-enough-to-keep" threshold:
  keep = hard_gates_pass
  i.e. the deterministic keep-line IS EXACTLY the HARD-gate line. Both COMPLIANT and
  KEEP_WITH_REVIEW are keepable; only REJECT is not. SOFT flags flag-for-review but never
  block keeping — they are adjudicated downstream by the critic / a human.

────────────────────────────────────────────────────────────────────────────────────────
Callable:
    from compliance_score import compliance_score
    result = compliance_score("kb/paths/X.yaml")            # profile auto-detected
    result = compliance_score("tests/.../P06.yaml", profile="ai_curated")
    # -> {tier, score, keep, hard_gates:{layer1..4, structural_hard:[...]},
    #     soft_flags:[...], breakdown:{...}}   (deterministic, reproducible)

CLI:
    python scripts/compliance_score.py kb/paths/<file>.yaml
    python scripts/compliance_score.py <file> [<file> ...] --json
    python scripts/compliance_score.py <file> --profile ai_curated
Exit: 0 = all keepable · 1 = >=1 REJECT · 2 = a file could not be processed.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent            # scripts/
REPO = HERE.parent
QUALITY_DIR = HERE / "quality"
sys.path.insert(0, str(QUALITY_DIR))              # so `import structural_quality` resolves

import structural_quality                          # noqa: E402  (pure, deterministic, no LLM)

QC = HERE / "qc.py"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"

# The two structural severity sets are OWNED by structural_quality (issue #28's single point
# to adjust). We import them rather than re-listing, so this scorer can never drift from the
# gate's classification.
HARD_STRUCTURAL = structural_quality.HARD_BLOCKING_CHECKS
SOFT_STRUCTURAL = structural_quality.SOFT_CRITIC_CHECKS

_LAYER_NAMES = {1: "schema", 2: "node ontology", 3: "predicate enum",
                4: "reference (verbatim snippet)"}

# scoring constants (the maintainer's formula — see module docstring)
_SOFT_PENALTY = 0.1
_SCORE_FLOOR = 0.5


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ── QC (Layers 1-4), reused via subprocess — offline, so no network ────────────

def _summarize_qc_detail(raw: str) -> list[str]:
    """Compact one-line-per-failure summary from a layer's --json `failures` list.

    Each layer script emits `{"failures": [{...}]}` with a reason/message plus locators.
    Falls back to raw text lines when the shape is unexpected. (Same shape gate.py reads.)"""
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


def _run_qc(path_file: Path, *, profile: str) -> dict:
    """Run scripts/qc.py Layers 1-4 (`--offline`, no network) and capture per-layer results.

    Returns {"layers": {n: bool}, "profile_used": str|None, "failures": [...], "ran_ok": bool}.
    A layer that did not run for this profile is simply absent from `layers` (== not
    applicable, NOT a failure) — Layer 4 is skipped for legacy (no per-edge evidence)."""
    cmd = [_py(), str(QC), "--json", "--offline", "--profile", profile, str(path_file)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    layers: dict[int, bool] = {}
    failures: list[dict] = []
    profile_used: str | None = None
    ran_ok = True
    try:
        data = json.loads(proc.stdout)
        counts = data.get("profile_counts") or {}
        # the bucket with a file in it is the profile qc actually applied
        profile_used = next((p for p, c in counts.items() if c), None) or profile
        for r in data.get("results", []):
            ln, ok = r["layer"], (r["exit_code"] == 0)
            layers[ln] = ok
            if not ok:
                raw = (r.get("output") or "").strip()
                failures.append({"layer": ln, "name": _LAYER_NAMES.get(ln, f"layer {ln}"),
                                 "detail_lines": _summarize_qc_detail(raw)})
    except Exception:
        # qc.py could not be parsed (crash / non-JSON). Treat as a non-passing run: we cannot
        # confirm compliance, so it must not be silently kept.
        ran_ok = False
        raw = (proc.stdout + proc.stderr).strip()
        failures.append({"layer": None, "name": "qc (could not run)",
                         "detail_lines": _summarize_qc_detail(raw) or [raw[:400]]})
    return {"layers": layers, "profile_used": profile_used, "failures": failures, "ran_ok": ran_ok}


# ── the compliance score ───────────────────────────────────────────────────────

def _flag_view(f: dict) -> dict:
    """Compact, stable view of a structural flag for output."""
    return {"code": f.get("code"), "severity": f.get("severity"), "msg": f.get("msg")}


def compliance_score(path_file, *, profile: str = "auto") -> dict:
    """Deterministic compliance score + keep/reject decision for one curated path.

    `profile` is passed straight to qc.py: 'auto' (default) detects legacy vs ai_curated
    per-file (ai_curated iff any edge carries evidence); 'legacy' / 'ai_curated' force it.

    Returns the result dict documented in the module header. Fully deterministic: no LLM,
    no network (QC runs `--offline`), same input -> identical output."""
    p = Path(path_file)

    doc = yaml.safe_load(p.read_text())
    record_id = ((doc or {}).get("graph") or {}).get("_id") or p.stem

    # (1) QC Layers 1-4 — reused, offline
    qc = _run_qc(p, profile=profile)

    # (2) structural checks — reused pure function
    lex = structural_quality.load_lexicon()
    struct = structural_quality.analyze(p, lex)
    struct_flags = struct.get("flags", [])
    structural_hard = [_flag_view(f) for f in struct_flags if f.get("code") in HARD_STRUCTURAL]
    soft_flags      = [_flag_view(f) for f in struct_flags if f.get("code") in SOFT_STRUCTURAL]
    advisory        = [_flag_view(f) for f in struct_flags
                       if f.get("code") not in HARD_STRUCTURAL and f.get("code") not in SOFT_STRUCTURAL]

    # (3) HARD gates: every QC layer that RAN must pass, QC must have run, and there must be
    #     no HARD structural flag. A skipped layer (Layer 4 for legacy) is absent from
    #     qc["layers"] and therefore does not count against the gate.
    qc_layers_pass = qc["ran_ok"] and all(qc["layers"].values())
    hard_gates_pass = qc_layers_pass and not structural_hard

    # per-layer view for output: True / False if it ran, None if not applicable for this profile
    layer_view = {f"layer{n}": qc["layers"].get(n, None) for n in (1, 2, 3, 4)}

    # (4) tier / score / keep
    n_soft = len(soft_flags)
    if not hard_gates_pass:
        tier = "REJECT"
        score = 0.0
    elif n_soft == 0:
        tier = "COMPLIANT"
        score = 1.0
    else:
        tier = "KEEP_WITH_REVIEW"
        score = round(1.0 - min(_SCORE_FLOOR, _SOFT_PENALTY * n_soft), 4)
    keep = hard_gates_pass   # the deterministic keep-line IS the HARD-gate line

    score_formula = (
        "0.0 (a hard gate failed)" if not hard_gates_pass
        else f"1.0 - min({_SCORE_FLOOR}, {_SOFT_PENALTY} * {n_soft} soft) = {score}"
    )

    return {
        "file": str(p),
        "record_id": record_id,
        "profile": qc["profile_used"] or profile,
        "tier": tier,
        "score": score,
        "keep": keep,
        "hard_gates": {
            **layer_view,
            "structural_hard": structural_hard,
        },
        "soft_flags": soft_flags,
        "breakdown": {
            "hard_gates_pass": hard_gates_pass,
            "qc_ran": qc["ran_ok"],
            "qc_layers_pass": qc_layers_pass,
            "qc_failures": qc["failures"],
            "soft_flag_count": n_soft,
            "score_formula": score_formula,
            "keep_rule": "keep == hard_gates_pass (COMPLIANT & KEEP_WITH_REVIEW keep; REJECT does not)",
            "advisory_flags": advisory,   # convention/prioritization notes — NOT scored
            "polarity": struct.get("polarity"),
            "n_nodes": struct.get("n_nodes"),
            "n_edges": struct.get("n_edges"),
            "n_paths": struct.get("n_paths"),
        },
    }


# ── rendering ───────────────────────────────────────────────────────────────────

def render(result: dict) -> str:
    out: list[str] = []
    keep = "KEEP" if result["keep"] else "DO NOT KEEP"
    out.append(f"=== COMPLIANCE — {result['record_id']} ({result['profile']}) ===")
    out.append(f"Tier: {result['tier']}   Score: {result['score']:.2f}   Decision: {keep}")

    hg = result["hard_gates"]
    out.append("")
    out.append("HARD gates (must all pass to keep):")
    for n in (1, 2, 3, 4):
        v = hg.get(f"layer{n}")
        mark = "PASS" if v is True else ("FAIL" if v is False else "n/a ")
        out.append(f"  [{mark}] QC Layer {n} ({_LAYER_NAMES[n]})")
    sh = hg["structural_hard"]
    out.append(f"  [{'FAIL' if sh else 'PASS'}] no HARD structural flag"
               + (f"  ({len(sh)} present)" if sh else ""))
    for f in sh:
        out.append(f"        [{f['code']}] {f['msg']}")

    qc_fail = result["breakdown"]["qc_failures"]
    if qc_fail:
        out.append("")
        out.append("QC failure detail:")
        for f in qc_fail:
            tag = f"Layer {f['layer']} ({f['name']})" if f.get("layer") else f["name"]
            out.append(f"  [{tag}]")
            for line in (f.get("detail_lines") or []):
                if line.strip():
                    out.append(f"        {line.strip()}")

    sf = result["soft_flags"]
    out.append("")
    if sf:
        out.append(f"SOFT flags (graded; flag-for-review, do NOT block keeping) — {len(sf)}:")
        for f in sf:
            out.append(f"  [{f['code']}] {f['msg']}")
    else:
        out.append("SOFT flags: none")

    adv = result["breakdown"]["advisory_flags"]
    if adv:
        out.append("")
        out.append("Advisory (convention/prioritization notes; NOT scored):")
        for f in adv:
            out.append(f"  [{f['code']}] {f['msg']}")

    out.append("")
    out.append(f"Score = {result['breakdown']['score_formula']}")
    return "\n".join(out)


# ── CLI ───────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("path_files", nargs="+", help="path YAML file(s) to score")
    ap.add_argument("--profile", choices=("auto", "legacy", "ai_curated"), default="auto",
                    help="QC profile (default: auto — legacy vs ai_curated per file)")
    ap.add_argument("--json", action="store_true", help="machine-readable output")
    args = ap.parse_args()

    results = []
    could_not_process = False
    for pf in args.path_files:
        if not Path(pf).is_file():
            print(f"compliance_score: not a file: {pf}", file=sys.stderr)
            could_not_process = True
            continue
        results.append(compliance_score(pf, profile=args.profile))

    if args.json:
        print(json.dumps(results if len(results) != 1 else results[0], indent=2, default=str))
    else:
        for r in results:
            print(render(r))
            print()

    if could_not_process:
        return 2
    if any(r["tier"] == "REJECT" for r in results):
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
