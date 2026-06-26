"""
Phase 3 evaluation orchestrator.

Bookkeeping for the 30-pair eval (PRD v3 §6 Phase 3). Reads the pair list at
docs/phase3_eval_pairs.yaml, expects agent outputs at
tests/phase3_eval_outputs/<pair_id>.yaml, and scores each output via the
Layer-1-4 QC pipeline.

This script does not invoke the agent itself — it is the scoring and
reporting layer. Spawn `/curate` interactively (or via the Agent tool from
the running Claude session) for each pair. The agent is responsible for
writing its draft to the eval output directory using the `pair_id` as the
filename stem (e.g. `tests/phase3_eval_outputs/P01.yaml`).

Subcommands:
  prompt <pair_id>      Emit the /curate prompt for one pair (copy/paste-ready)
  list                  Show all 30 pairs with their stratification + current status
  score [pair_id...]    Run QC against agent outputs and tabulate first-pass rate
  report                Write docs/phase3_eval_results.md with the final scoring
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from collections import Counter
from pathlib import Path

import yaml

REPO = Path(__file__).resolve().parent.parent
PAIRS_FILE = REPO / "docs" / "phase3_eval_pairs.yaml"
OUTPUTS_DIR = REPO / "tests" / "phase3_eval_outputs"
RESULTS_FILE = REPO / "docs" / "phase3_eval_results.md"
RESULTS_JSON = REPO / "docs" / "phase3_eval_results.json"
VENV_PY = REPO / ".venv-py310" / "bin" / "python"


def load_pairs() -> list[dict]:
    with PAIRS_FILE.open() as fh:
        doc = yaml.safe_load(fh)
    return doc.get("pairs", [])


def output_path(pair_id: str) -> Path:
    return OUTPUTS_DIR / f"{pair_id}.yaml"


def _py() -> str:
    return str(VENV_PY) if VENV_PY.exists() else sys.executable


# ────────────────────────────────────────────────────────────────────────────
# Subcommand: prompt
# ────────────────────────────────────────────────────────────────────────────

PROMPT_TEMPLATE = """\
Curate a new DrugMechDB mechanistic path for **{drug}** for **{disease}**.

Pair-specific metadata (from docs/phase3_eval_pairs.yaml):
  pair_id      : {pair_id}
  drug_mesh    : {drug_mesh}
  drugbank     : {drugbank}
  disease_mesh : {disease_mesh}
  drug_class   : {drug_class}
  disease_area : {disease_area}
  existing_in_corpus : {existing_in_corpus}

**Eval-mode override:** write your final YAML to
    tests/phase3_eval_outputs/{pair_id}.yaml
NOT to kb/paths/. Set the graph `_id` to the eval pair id (e.g. {pair_id}_{drugbank_short}_{disease_short}) so it remains a valid identifier under the schema, but do NOT touch kb/paths/_index.yaml.

Follow AGENTS.md exactly. Use scripts/pubmed_fetch.py for all evidence
lookups. After drafting, run:
    .venv-py310/bin/python scripts/canonicalize_predicates.py --write tests/phase3_eval_outputs/{pair_id}.yaml
    .venv-py310/bin/python scripts/qc.py --profile ai_curated tests/phase3_eval_outputs/{pair_id}.yaml
Iterate up to 3 retries per AGENTS.md §5.

In your final message, report:
  - retry_count (0 = first-pass success)
  - PMIDs cited
  - per-layer pass/fail on the final QC run
  - any unresolved validation failures
"""


def cmd_prompt(pair_id: str) -> int:
    pairs = {p["id"]: p for p in load_pairs()}
    if pair_id not in pairs:
        print(f"unknown pair id: {pair_id}", file=sys.stderr)
        return 2
    p = pairs[pair_id]
    drugbank_short = (p.get("drugbank") or "DB:UNK").split(":")[-1]
    disease_short = (p.get("disease_mesh") or "MESH:UNK").replace(":", "_")
    print(PROMPT_TEMPLATE.format(
        drug=p["drug"], disease=p["disease"],
        pair_id=p["id"], drug_mesh=p.get("drug_mesh", "—"),
        drugbank=p.get("drugbank", "—"), disease_mesh=p["disease_mesh"],
        drug_class=p["drug_class"], disease_area=p["disease_area"],
        existing_in_corpus=p["existing_in_corpus"],
        drugbank_short=drugbank_short, disease_short=disease_short,
    ))
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Subcommand: list
# ────────────────────────────────────────────────────────────────────────────

def cmd_list() -> int:
    pairs = load_pairs()
    drug_classes = Counter(p["drug_class"] for p in pairs)
    disease_areas = Counter(p["disease_area"] for p in pairs)
    print(f"Total pairs: {len(pairs)}")
    print(f"Drug classes ({len(drug_classes)}): " +
          ", ".join(f"{k}({v})" for k, v in drug_classes.most_common()))
    print(f"Disease areas ({len(disease_areas)}): " +
          ", ".join(f"{k}({v})" for k, v in disease_areas.most_common()))
    print(f"In-corpus: {sum(1 for p in pairs if p['existing_in_corpus'])} / Net-new: "
          f"{sum(1 for p in pairs if not p['existing_in_corpus'])}")
    print()
    print(f"{'id':6} {'drug':25} {'disease':35} {'class':16} {'output'}")
    for p in pairs:
        out = output_path(p["id"])
        status = "✓" if out.exists() else "—"
        print(f"{p['id']:6} {p['drug'][:24]:25} {p['disease'][:34]:35} {p['drug_class']:16} {status}")
    return 0


# ────────────────────────────────────────────────────────────────────────────
# Subcommand: score
# ────────────────────────────────────────────────────────────────────────────

def _run_qc(path: Path) -> dict:
    cmd = [_py(), str(REPO / "scripts" / "qc.py"), "--json", "--profile", "ai_curated", str(path)]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError:
        return {"_raw_stdout": proc.stdout, "_raw_stderr": proc.stderr, "overall_pass": False}


def cmd_score(targets: list[str]) -> int:
    pairs = {p["id"]: p for p in load_pairs()}
    selected = pairs.keys() if not targets else targets

    results = []
    for pair_id in selected:
        if pair_id not in pairs:
            results.append({"pair_id": pair_id, "status": "unknown_pair"})
            continue
        out = output_path(pair_id)
        if not out.exists():
            results.append({"pair_id": pair_id, "status": "no_output"})
            continue
        qc = _run_qc(out)
        per_layer = {r["layer"]: (r["exit_code"] == 0) for r in qc.get("results", [])}
        results.append({
            "pair_id": pair_id,
            "drug": pairs[pair_id]["drug"],
            "disease": pairs[pair_id]["disease"],
            "drug_class": pairs[pair_id]["drug_class"],
            "disease_area": pairs[pair_id]["disease_area"],
            "existing_in_corpus": pairs[pair_id]["existing_in_corpus"],
            "status": "scored",
            "overall_pass": qc.get("overall_pass", False),
            "per_layer": per_layer,
            "output_path": str(out.relative_to(REPO)),
        })

    n_attempted = sum(1 for r in results if r["status"] == "scored")
    n_passed = sum(1 for r in results if r.get("overall_pass"))
    print(f"Pairs attempted   : {n_attempted}")
    print(f"Pairs no_output   : {sum(1 for r in results if r['status']=='no_output')}")
    print(f"Pairs passed (all 4 layers): {n_passed} / {n_attempted}"
          + (f" ({n_passed/n_attempted:.0%})" if n_attempted else ""))

    by_class = Counter()
    pass_by_class = Counter()
    for r in results:
        if r["status"] != "scored":
            continue
        by_class[r["drug_class"]] += 1
        if r.get("overall_pass"):
            pass_by_class[r["drug_class"]] += 1
    if by_class:
        print("\nPer drug class:")
        for cls, total in by_class.most_common():
            print(f"  {cls:18} {pass_by_class[cls]:>3}/{total:<3} pass")

    RESULTS_JSON.parent.mkdir(parents=True, exist_ok=True)
    RESULTS_JSON.write_text(json.dumps(results, indent=2))
    print(f"\nDetails: {RESULTS_JSON}")
    return 0 if n_passed == n_attempted and n_attempted > 0 else 1


# ────────────────────────────────────────────────────────────────────────────
# Subcommand: report
# ────────────────────────────────────────────────────────────────────────────

def cmd_report() -> int:
    if not RESULTS_JSON.exists():
        print("No results yet — run `score` first.", file=sys.stderr)
        return 1
    results = json.loads(RESULTS_JSON.read_text())
    pairs = load_pairs()
    scored = [r for r in results if r["status"] == "scored"]
    no_output = [r for r in results if r["status"] == "no_output"]

    if scored:
        first_pass = sum(1 for r in scored if r.get("overall_pass"))
        rate = first_pass / len(scored)
    else:
        first_pass = 0; rate = 0.0

    lines = []
    lines.append("# Phase 3 Evaluation Results\n")
    lines.append(f"**Pairs attempted:** {len(scored)} / {len(pairs)}")
    lines.append(f"**Pass rate (first-pass, all 4 layers):** {first_pass} / {len(scored)} "
                 f"({rate:.0%})" if scored else "")
    lines.append(f"**Exit threshold (PRD §6 Phase 3):** ≥80% — "
                 f"{'MET' if rate >= 0.8 else 'NOT MET' if scored else 'n/a (no scored pairs)'}\n")
    if no_output:
        lines.append(f"**Pairs not yet attempted:** {', '.join(r['pair_id'] for r in no_output)}\n")
    lines.append("\n## Per-pair detail\n")
    lines.append("| ID | Drug | Disease | Class | L1 | L2 | L3 | L4 | Overall |")
    lines.append("|---|---|---|---|---|---|---|---|---|")
    for r in results:
        if r["status"] != "scored":
            lines.append(f"| {r['pair_id']} | — | — | — | — | — | — | — | NOT_ATTEMPTED |")
            continue
        pl = r.get("per_layer", {})
        cell = lambda b: "✓" if b is True else ("✗" if b is False else "—")
        lines.append(f"| {r['pair_id']} | {r['drug']} | {r['disease']} | {r['drug_class']} | "
                     f"{cell(pl.get(1))} | {cell(pl.get(2))} | {cell(pl.get(3))} | {cell(pl.get(4))} | "
                     f"{'PASS' if r.get('overall_pass') else 'FAIL'} |")
    RESULTS_FILE.write_text("\n".join(lines))
    print(f"Wrote {RESULTS_FILE}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)
    sub.add_parser("list")
    p_prompt = sub.add_parser("prompt"); p_prompt.add_argument("pair_id")
    p_score = sub.add_parser("score"); p_score.add_argument("pair_ids", nargs="*")
    sub.add_parser("report")
    args = parser.parse_args()
    if args.cmd == "list": return cmd_list()
    if args.cmd == "prompt": return cmd_prompt(args.pair_id)
    if args.cmd == "score": return cmd_score(args.pair_ids)
    if args.cmd == "report": return cmd_report()
    return 1


if __name__ == "__main__":
    sys.exit(main())
