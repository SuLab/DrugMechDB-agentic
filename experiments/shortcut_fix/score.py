"""
Score the shortcut-fix re-curation (Issue #2).

Runs the DETERMINISTIC structural-quality analyzer (scripts/quality/structural_quality.py)
on every pair in eval_pairs.yaml, for BOTH:
  * BEFORE  = experiments/opus_vs_sonnet/opus/outputs/<pair>.yaml  (pre-fix AGENTS.md)
  * AFTER   = experiments/shortcut_fix/opus/outputs/<pair>.yaml     (post-fix AGENTS.md)

and reports the per-pair shortcut-flag status and the combined shortcut-flag RATE
(fraction of scored records carrying `clinical_shortcut` and/or `short_circuit`),
which is the Issue #2 "done when" metric (target: AFTER <= 10%).

Deterministic and LLM-free — this is the objective judge of the experiment.

Usage:
    .venv-py310/bin/python experiments/shortcut_fix/score.py
    .venv-py310/bin/python experiments/shortcut_fix/score.py --json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

import yaml

EXP_DIR = Path(__file__).resolve().parent
REPO = EXP_DIR.parent.parent
sys.path.insert(0, str(REPO / "scripts" / "quality"))

import structural_quality as sq  # noqa: E402

BEFORE_DIR = REPO / "experiments" / "opus_vs_sonnet" / "opus" / "outputs"
AFTER_DIR = EXP_DIR / "opus" / "outputs"
SHORTCUT_CODES = {"clinical_shortcut", "short_circuit"}   # Issue #2 metric
RELATED_CODES = {"direct_drug_disease"}                    # reported, not in the headline rate

LEX = sq.load_lexicon()


def score_one(path: Path) -> dict | None:
    if not path.exists() or path.stat().st_size == 0:
        return None
    r = sq.analyze(path, LEX)
    codes = [f["code"] for f in r["flags"]]
    return {
        "n_edges": r["n_edges"],
        "n_paths": r["n_paths"],
        "shortcut_flags": sorted(c for c in codes if c in SHORTCUT_CODES),
        "related_flags": sorted(c for c in codes if c in RELATED_CODES),
        "hard_flags": sorted(f["code"] for f in r["flags"] if f["severity"] == "HARD"),
        "clean_hard": r["clean_hard"],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--json", action="store_true")
    args = ap.parse_args()

    pairs = yaml.safe_load((EXP_DIR / "eval_pairs.yaml").read_text())["pairs"]

    rows, before_hits, after_hits, before_n, after_n = [], 0, 0, 0, 0
    for p in pairs:
        pid = p["id"]
        b = score_one(BEFORE_DIR / f"{pid}.yaml")
        a = score_one(AFTER_DIR / f"{pid}.yaml")
        if b:
            before_n += 1
            if b["shortcut_flags"]:
                before_hits += 1
        if a:
            after_n += 1
            if a["shortcut_flags"]:
                after_hits += 1
        rows.append({"pair": pid, "disease_area": p.get("disease_area"),
                     "before": b, "after": a})

    before_rate = before_hits / before_n if before_n else None
    after_rate = after_hits / after_n if after_n else None
    result = {
        "metric": "records with clinical_shortcut and/or short_circuit",
        "before": {"scored": before_n, "shortcut": before_hits,
                   "rate": before_rate},
        "after": {"scored": after_n, "shortcut": after_hits,
                  "rate": after_rate},
        "target_after_rate": 0.10,
        "pass": (after_rate is not None and after_rate <= 0.10),
        "pairs": rows,
    }

    if args.json:
        print(json.dumps(result, indent=2))
        return 0

    print("=== Shortcut-fix re-curation — before vs after ===\n")
    print(f"{'pair':<6}{'area':<16}{'before (edges/paths → shortcut)':<42}{'after (edges/paths → shortcut)'}")
    for r in rows:
        def fmt(x):
            if not x:
                return "— not run —"
            sc = ",".join(x["shortcut_flags"]) or "clean"
            return f"{x['n_edges']}e/{x['n_paths']}p → {sc}"
        print(f"{r['pair']:<6}{str(r['disease_area']):<16}{fmt(r['before']):<42}{fmt(r['after'])}")

    print(f"\nBEFORE: {before_hits}/{before_n} shortcutted"
          + (f" ({before_rate:.0%})" if before_rate is not None else ""))
    print(f"AFTER : {after_hits}/{after_n} shortcutted"
          + (f" ({after_rate:.0%})" if after_rate is not None else ""))
    print(f"Target: AFTER <= 10%  →  {'PASS ✅' if result['pass'] else 'not yet'}")

    (EXP_DIR / "analysis.json").write_text(json.dumps(result, indent=2))
    print(f"\nWrote {(EXP_DIR / 'analysis.json').relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
