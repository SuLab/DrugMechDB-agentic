"""
scripts/eval_cli.py — one reusable CLI for the whole evaluation harness.

The eval logic used to be split across two entry points: scripts/run_phase3_eval.py
(the SCORING layer — runs the 4-layer QC gate over agent outputs and tabulates the
pass rate) and experiments/opus_vs_sonnet/run_arm.py (an older, self-contained
two-arm curation runner). This CLI unifies them behind three subcommands, each a
thin WRAPPER around the existing code — no scoring or curation logic is duplicated:

  score    Wrap scripts/run_phase3_eval.py's scoring over an outputs dir. Reuses that
           module's QC dispatch and reporting verbatim (globals are redirected, not
           reimplemented) so `score` with no overrides reproduces the Phase-3 behavior.

  curate   Curate a set of eval pairs into an ISOLATED output dir using the canonical
           engine scripts/curate_engine.py (curate_one) — NOT a reimplementation.
           BUILD-ONLY: the default is a dry-run plan that constructs no client and makes
           no API call. A real curation happens ONLY with the explicit --run flag, which
           is the sole path that builds a real Anthropic client (reusing the engine's
           client-injection pattern).

  compare  Compare two arms' outputs, opus-vs-sonnet style (per-arm summary +
           head-to-head), reading the committed run_summary.json / analysis.json shape.

── CANONICAL CURATION LOOP ──────────────────────────────────────────────────────
scripts/curate_engine.py (curate_one) is now the canonical, headless /curate loop —
new eval curation should go through the engine (directly, or via `eval_cli curate`).
experiments/opus_vs_sonnet/run_arm.py is retained ONLY as the historical two-arm eval
runner that produced the committed opus/ and sonnet/ artifacts; it is not the path for
new curation work.

── BUILD-ONLY ─────────────────────────────────────────────────────────────────────
Importing this module constructs nothing and calls nothing external. `score` and
`compare` are offline (QC subprocess / JSON reads). `curate` defaults to a dry run;
only `curate --run` constructs a real client and performs curation.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent              # scripts/
REPO = HERE.parent
sys.path.insert(0, str(HERE))                        # so run_phase3_eval / curate_engine / campaign_runner import

DEFAULT_PAIRS_FILE = REPO / "docs" / "phase3_eval_pairs.yaml"


# ════════════════════════════════════════════════════════════════════════════════
# score — wrap scripts/run_phase3_eval.py's scoring layer over an outputs dir
# ════════════════════════════════════════════════════════════════════════════════

def cmd_score(args) -> int:
    """Thin wrapper over run_phase3_eval.cmd_score / cmd_report.

    Reuses that module's QC dispatch and reporting unchanged. To let the same scoring
    run over an arbitrary outputs dir / pairs file, the module's path globals are
    redirected in-process before dispatch (the file is never modified). With no
    overrides this reproduces the canonical Phase-3 scoring exactly.
    """
    import run_phase3_eval as rpe

    if args.outputs_dir:
        rpe.OUTPUTS_DIR = Path(args.outputs_dir).resolve()
    if args.pairs_file:
        rpe.PAIRS_FILE = Path(args.pairs_file).resolve()
    if args.results_json:
        rpe.RESULTS_JSON = Path(args.results_json).resolve()
    elif args.outputs_dir:
        # Don't clobber docs/phase3_eval_results.json when scoring a custom dir.
        rpe.RESULTS_JSON = Path(args.outputs_dir).resolve().parent / "eval_results.json"
    if args.report_file:
        rpe.RESULTS_FILE = Path(args.report_file).resolve()
    elif args.outputs_dir:
        rpe.RESULTS_FILE = Path(args.outputs_dir).resolve().parent / "eval_results.md"

    print(f"[score] outputs_dir = {rpe.OUTPUTS_DIR}")
    print(f"[score] pairs_file  = {rpe.PAIRS_FILE}")
    print(f"[score] results     = {rpe.RESULTS_JSON}")
    print()

    rc = rpe.cmd_score(args.pair_ids)
    if args.report:
        rpe.cmd_report()
    return rc


# ════════════════════════════════════════════════════════════════════════════════
# curate — drive scripts/curate_engine.curate_one over a set of eval pairs
# ════════════════════════════════════════════════════════════════════════════════

def _load_work_items(pairs_file: Path, want: set[str] | None):
    """Read an eval pairs file (docs/phase3_eval_pairs.yaml shape) into WorkItems.

    Reuses campaign_runner.WorkItem — the same work-item type the production campaign
    dispatches — so an eval pair and a corpus record are curated through one code path.
    """
    import yaml
    from campaign_runner import WorkItem

    doc = yaml.safe_load(pairs_file.read_text(encoding="utf-8")) or {}
    pairs = doc.get("pairs", []) if isinstance(doc, dict) else doc
    items = []
    for p in pairs:
        pid = p.get("id")
        if want and pid not in want:
            continue
        items.append(WorkItem(
            id=pid, drug=p.get("drug"), disease=p.get("disease"),
            drug_mesh=p.get("drug_mesh"), drugbank=p.get("drugbank"),
            disease_mesh=p.get("disease_mesh"),
        ))
    return items


def cmd_curate(args, *, client=None) -> int:
    """Curate eval pairs into an isolated out dir via curate_engine.curate_one.

    BUILD-ONLY: no --run (and no injected client) => a dry-run plan that constructs no
    client and makes no API call. --run is the ONLY path that builds a real client
    (via the engine's client-injection pattern) and actually curates. `client` is an
    injection seam for offline tests (a mock), never used by the CLI itself.
    """
    import curate_engine

    pairs_file = Path(args.pairs_file).resolve() if args.pairs_file else DEFAULT_PAIRS_FILE
    want = set(args.pairs.split(",")) if args.pairs else None
    items = _load_work_items(pairs_file, want)
    if not items:
        print(f"[curate] no pairs selected from {pairs_file}"
              + (f" (filter: {sorted(want)})" if want else ""), file=sys.stderr)
        return 2

    out_dir = Path(args.out_dir).resolve()
    paths_dir = out_dir / "paths"
    cache_root = out_dir / "cache"
    model = args.model

    is_dry = not args.run and client is None
    if is_dry:
        print("── curate: DRY RUN (build-only) — constructs no client, makes no API call ──")
        print(f"  pairs_file : {pairs_file}")
        print(f"  pairs      : {len(items)} selected -> {', '.join(i.id for i in items)}")
        print(f"  model      : {model}")
        print(f"  out_dir    : {out_dir}")
        print(f"    outputs  : {paths_dir}/<pair_id>.yaml   (isolated; never kb/paths)")
        print(f"    cache    : {cache_root}/<pair_id>/       (per-pair DMDB_CACHE_DIR)")
        print(f"  offline    : {args.offline}")
        print()
        print("A real curation is deliberate. To actually curate (constructs a real")
        print("Anthropic client and calls the API), re-run with --run:")
        print(f"    {Path(sys.argv[0]).name} curate --out-dir {args.out_dir} "
              f"--pairs-file {pairs_file.name} --model {model} --run")
        return 0

    # ── real run (or an injected test client) ──────────────────────────────────
    if client is None:
        client = curate_engine._build_real_client()   # live run only; the sole client build

    results = []
    n_ok = 0
    for item in items:
        out_path = paths_dir / f"{item.id}.yaml"
        cache_dir = cache_root / item.id
        print(f"[curate] {item.id}: {item.drug} -> {item.disease} ...", flush=True)
        res = curate_engine.curate_one(
            item, model=model, cache_dir=cache_dir, out_path=out_path,
            client=client, offline=args.offline)
        n_ok += 1 if res.ok else 0
        results.append(res.to_dict())
        print(f"  ok={res.ok} gate={res.gate_verdict} wrote={res.wrote_yaml} "
              f"iters={res.iters} stopped={res.stopped}", flush=True)

    out_dir.mkdir(parents=True, exist_ok=True)
    summary = out_dir / "run_summary.json"
    summary.write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(f"\n[curate] {n_ok}/{len(items)} accepted · wrote {summary}")
    print(f"[curate] score them with:  {Path(sys.argv[0]).name} score "
          f"--outputs-dir {paths_dir} --pairs-file {pairs_file}")
    return 0 if n_ok == len(items) else 1


# ════════════════════════════════════════════════════════════════════════════════
# compare — two-arm head-to-head from committed run_summary/analysis JSON
# ════════════════════════════════════════════════════════════════════════════════

def _normalize_pair(rec: dict) -> dict:
    """Map any of the three committed per-pair shapes into one common record:
      - analysis.json arm entry : pair / full_pass / written / iters / wall / cost / l4
      - run_arm run_summary.json: pair_id / output_written / est_cost_usd / wall_seconds
      - curate_engine result    : item_id / gate_passed / wrote_yaml / iters
    `passed` is None when the source carries no pass/fail (run_summary has no QC verdict).
    """
    pid = rec.get("pair") or rec.get("pair_id") or rec.get("item_id")
    if "full_pass" in rec:
        passed = rec.get("full_pass")
    elif "gate_passed" in rec:
        passed = rec.get("gate_passed")
    else:
        passed = None
    written = rec.get("written")
    if written is None:
        written = rec.get("output_written")
    if written is None:
        written = rec.get("wrote_yaml")
    return {
        "id": pid,
        "passed": passed,
        "written": bool(written),
        "iters": rec.get("iters"),
        "wall": rec.get("wall", rec.get("wall_seconds")),
        "cost": rec.get("cost", rec.get("est_cost_usd")),
        "l4": rec.get("l4"),
        "l123_fail": rec.get("l123_fail"),
    }


def _is_analysis_shape(obj) -> bool:
    """analysis.json = dict of arm-name -> {model, pairs:[...]}"""
    return (isinstance(obj, dict)
            and bool(obj)
            and all(isinstance(v, dict) and "pairs" in v for v in obj.values()))


def _resolve_arm(path_str: str) -> tuple[str, str | None, list[dict]]:
    """Resolve one arm-spec into (label, model, normalized_pairs).

    Accepts a directory (looks for run_summary.json inside) or a JSON file that is a
    run_summary.json / curate_engine result LIST. An analysis.json (dict-of-arms) is
    rejected here — pass it alone as the single argument instead.
    """
    p = Path(path_str)
    if p.is_dir():
        label = p.name
        p = p / "run_summary.json"
    else:
        label = p.stem
    if not p.exists():
        raise FileNotFoundError(f"no run_summary.json at {p}")
    obj = json.loads(p.read_text(encoding="utf-8"))
    if _is_analysis_shape(obj):
        raise ValueError(f"{p} is an analysis.json (dict of arms) — pass it alone, "
                         f"not as one of two arms.")
    if not isinstance(obj, list):
        raise ValueError(f"{p} is not a run_summary list")
    model = next((r.get("model") for r in obj if r.get("model")), None)
    return label, model, [_normalize_pair(r) for r in obj]


def _summarize(pairs: list[dict]) -> dict:
    scored = [p for p in pairs if p["passed"] is not None]
    passed = [p for p in scored if p["passed"]]
    costed = [p["cost"] for p in pairs if isinstance(p.get("cost"), (int, float))]
    itered = [p["iters"] for p in pairs if isinstance(p.get("iters"), (int, float))]
    walled = [p["wall"] for p in pairs if isinstance(p.get("wall"), (int, float))]
    return {
        "n": len(pairs),
        "written": sum(1 for p in pairs if p["written"]),
        "scored": len(scored),
        "passed": len(passed),
        "pass_rate": (len(passed) / len(scored)) if scored else None,
        "total_cost": round(sum(costed), 4) if costed else None,
        "costed_n": len(costed),
        "mean_iters": round(sum(itered) / len(itered), 1) if itered else None,
        "mean_wall": round(sum(walled) / len(walled), 1) if walled else None,
    }


def _fmt_rate(r) -> str:
    return "—" if r is None else f"{r:.0%}"


def cmd_compare(args) -> int:
    inputs = args.inputs
    labels_override = args.labels.split(",") if args.labels else None

    arms: list[tuple[str, str | None, list[dict]]] = []
    if len(inputs) == 1:
        # A single combined analysis.json (dict of arms).
        obj = json.loads(Path(inputs[0]).read_text(encoding="utf-8"))
        if not _is_analysis_shape(obj):
            print("A single argument must be an analysis.json (dict of arms). For two "
                  "run_summary.json files or arm dirs, pass both.", file=sys.stderr)
            return 2
        for name, arm in obj.items():
            arms.append((name, arm.get("model"),
                         [_normalize_pair(r) for r in arm.get("pairs", [])]))
    elif len(inputs) == 2:
        for spec in inputs:
            arms.append(_resolve_arm(spec))
    else:
        print("compare takes 1 analysis.json OR 2 arm specs (dir/run_summary.json).",
              file=sys.stderr)
        return 2

    if labels_override and len(labels_override) == len(arms):
        arms = [(labels_override[i], m, p) for i, (_, m, p) in enumerate(arms)]

    # ── per-arm summary ─────────────────────────────────────────────────────────
    summaries = {label: _summarize(pairs) for (label, _m, pairs) in arms}
    print("── Per-arm summary ──────────────────────────────────────────────────")
    print(f"{'arm':10} {'model':22} {'n':>3} {'writ':>4} {'pass':>7} {'rate':>5} "
          f"{'$total':>8} {'it':>5} {'wall':>6}")
    for (label, model, pairs) in arms:
        s = summaries[label]
        print(f"{label[:10]:10} {str(model or '—')[:22]:22} {s['n']:>3} {s['written']:>4} "
              f"{s['passed']:>3}/{s['scored']:<3} {_fmt_rate(s['pass_rate']):>5} "
              f"{('$'+format(s['total_cost'],'.2f')) if s['total_cost'] is not None else '—':>8} "
              f"{str(s['mean_iters'] or '—'):>5} {str(s['mean_wall'] or '—'):>6}")

    result: dict = {"arms": summaries, "head_to_head": None, "winner": None}

    # ── head-to-head (needs exactly two arms) ────────────────────────────────────
    if len(arms) == 2:
        (la, ma, pa), (lb, mb, pb) = arms
        da = {p["id"]: p for p in pa}
        db = {p["id"]: p for p in pb}
        common = sorted(set(da) & set(db))
        both_pass = only_a = only_b = both_fail = comparable = 0
        cost_a = cost_b = 0.0
        cost_pairs = 0
        for pid in common:
            x, y = da[pid], db[pid]
            if x["passed"] is not None and y["passed"] is not None:
                comparable += 1
                if x["passed"] and y["passed"]:
                    both_pass += 1
                elif x["passed"]:
                    only_a += 1
                elif y["passed"]:
                    only_b += 1
                else:
                    both_fail += 1
            if isinstance(x.get("cost"), (int, float)) and isinstance(y.get("cost"), (int, float)):
                cost_a += x["cost"]; cost_b += y["cost"]; cost_pairs += 1

        h2h = {
            "common_pairs": len(common),
            "comparable_pairs": comparable,
            "both_pass": both_pass, f"{la}_only": only_a, f"{lb}_only": only_b,
            "both_fail": both_fail,
            "cost_common_pairs": cost_pairs,
            f"{la}_cost_common": round(cost_a, 4) if cost_pairs else None,
            f"{lb}_cost_common": round(cost_b, 4) if cost_pairs else None,
        }
        result["head_to_head"] = h2h

        print("\n── Head-to-head (shared pairs) ──────────────────────────────────────")
        print(f"  common pairs        : {len(common)}  (comparable on pass/fail: {comparable})")
        print(f"  both pass           : {both_pass}")
        print(f"  {la} passes, {lb} fails : {only_a}")
        print(f"  {lb} passes, {la} fails : {only_b}")
        print(f"  both fail           : {both_fail}")
        if cost_pairs:
            print(f"  cost on {cost_pairs} shared pairs : {la} ${cost_a:.2f}  vs  {lb} ${cost_b:.2f}")

        # Winner: higher pass rate first, then lower total cost. State the basis plainly.
        ra = summaries[la]["pass_rate"]
        rb = summaries[lb]["pass_rate"]
        winner = basis = None
        if ra is not None and rb is not None and ra != rb:
            winner = la if ra > rb else lb
            basis = f"higher pass rate ({_fmt_rate(max(ra, rb))} vs {_fmt_rate(min(ra, rb))})"
        elif cost_pairs and cost_a != cost_b:
            winner = la if cost_a < cost_b else lb
            basis = f"equal pass rate, lower cost on shared pairs (${min(cost_a, cost_b):.2f} vs ${max(cost_a, cost_b):.2f})"
        result["winner"] = {"arm": winner, "basis": basis}
        print(f"\n  WINNER: {winner or 'tie / indeterminate'}"
              + (f"  ({basis})" if basis else ""))

    if args.json:
        Path(args.json).write_text(json.dumps(result, indent=2), encoding="utf-8")
        print(f"\n[compare] wrote {args.json}")
    return 0


# ════════════════════════════════════════════════════════════════════════════════
# CLI
# ════════════════════════════════════════════════════════════════════════════════

def build_parser() -> argparse.ArgumentParser:
    ap = argparse.ArgumentParser(
        prog="eval_cli.py", description=__doc__,
        formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)

    ps = sub.add_parser("score", help="run the 4-layer QC scoring over an outputs dir "
                                       "(wraps run_phase3_eval.py)")
    ps.add_argument("pair_ids", nargs="*", help="restrict to these pair ids (default: all)")
    ps.add_argument("--outputs-dir", help="dir of <pair_id>.yaml agent outputs "
                                          "(default: tests/phase3_eval_outputs)")
    ps.add_argument("--pairs-file", help="eval pairs YAML (default: docs/phase3_eval_pairs.yaml)")
    ps.add_argument("--results-json", help="where to write the machine-readable results")
    ps.add_argument("--report-file", help="where --report writes the Markdown table")
    ps.add_argument("--report", action="store_true", help="also write the Markdown report")

    pc = sub.add_parser("curate", help="curate eval pairs into an isolated dir via "
                                       "curate_engine.curate_one (DRY RUN unless --run)")
    pc.add_argument("--out-dir", required=True, help="isolated output dir (paths/ + cache/)")
    pc.add_argument("--pairs-file", help="eval pairs YAML (default: docs/phase3_eval_pairs.yaml)")
    pc.add_argument("--pairs", help="comma-separated pair ids (default: all in the file)")
    pc.add_argument("--model", default=None, help="model id (default: engine DEFAULT_MODEL)")
    pc.add_argument("--offline", action="store_true", help="evidence fetch cache-only (--offline)")
    pc.add_argument("--run", action="store_true",
                    help="ACTUALLY curate: builds a real client and calls the API "
                         "(default is a no-API dry-run plan)")

    pk = sub.add_parser("compare", help="two-arm head-to-head from committed "
                                        "run_summary.json / analysis.json")
    pk.add_argument("inputs", nargs="+",
                    help="one analysis.json, OR two arm specs (dir or run_summary.json)")
    pk.add_argument("--labels", help="comma-separated labels to override arm names")
    pk.add_argument("--json", help="also write the computed comparison to this JSON path")
    return ap


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.cmd == "score":
        return cmd_score(args)
    if args.cmd == "curate":
        if args.model is None:
            import curate_engine
            args.model = curate_engine.DEFAULT_MODEL
        return cmd_curate(args)
    if args.cmd == "compare":
        return cmd_compare(args)
    return 1


if __name__ == "__main__":
    sys.exit(main())
