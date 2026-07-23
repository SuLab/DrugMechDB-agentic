"""
scripts/run_pilot.py — drive the curation engine over the pilot stress set (BUILD-ONLY).

Reads experiments/pilot/pilot_pairs.yaml (from scripts/select_pilot_pairs.py) and runs
scripts/curate_engine.curate_one once per curation, into ISOLATED per-curation output +
cache under experiments/pilot/ — NEVER kb/paths (curate_engine asserts this). It captures
cost, wall-clock, and iteration count per curation into experiments/pilot/run_summary.json
(this is what closes the "measure iters/cost/wall per pilot pair" gap).

── SAFETY: DRY-RUN BY DEFAULT — NO API CALL, NO CLIENT (constraint of this module) ─────
Running this module with no flag prints the PLAN (which pairs, repeat counts, estimated
cost) and constructs NO Anthropic client and makes NO API call. A real run happens ONLY
with the explicit `--run` flag, which is the sole path that lets a live client be built.

Testing: the core `run_pilot(...)` accepts a `client_factory` injection point, so the
whole orchestration (expand repeats, isolate paths, invoke the real gate, capture metrics,
resume) is exercised OFFLINE with a mock client — exactly like tests/test_curate_engine.py
— with zero real API. `--run` without an injected factory passes client=None to the engine,
which then (and only then) builds the real anthropic.Anthropic().

── REPEATS (cross-run consistency) ───────────────────────────────────────────────────
A pair with `repeat: N` is curated N times into distinct outputs: <id>.yaml for run 1 and
<id>__rK.yaml for runs 2..N (each with its own isolated cache dir). Comparing the N outputs
measures how stable the agent is on the same input.

── RESUMABLE ───────────────────────────────────────────────────────────────────────
A curation whose output file already exists is skipped, so an interrupted --run resumes
without redoing finished curations (`--force` overrides).

Cost: the DRY-RUN plan estimates from the eval baseline (Opus, prompt-cached: ~$2-4/pair;
see experiments/opus_vs_sonnet). A real --run additionally computes the billed cost per
curation from token usage via the same per-MTok pricing model used by the eval harness.
"""

from __future__ import annotations

import argparse
import datetime as dt
import json
import sys
import time
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent               # scripts/
REPO = HERE.parent
PILOT_DIR = REPO / "experiments" / "pilot"
DEFAULT_PAIRS = PILOT_DIR / "pilot_pairs.yaml"
DEFAULT_OUT_ROOT = PILOT_DIR
SUMMARY_NAME = "run_summary.json"

sys.path.insert(0, str(HERE))                        # so `import curate_engine` / `campaign_runner` resolve

DEFAULT_MODEL = "claude-opus-4-8"

# Per-MTok pricing (mirrors experiments/opus_vs_sonnet/run_arm.py, claude-api skill 2026-06):
#   opus-4-8 $5 in / $25 out; sonnet-4-6 $3 in / $15 out. cache reads ~0.1x, writes ~1.25x.
PRICING = {
    "claude-opus-4-8":   {"in": 5.0,  "out": 25.0},
    "claude-opus-4-7":   {"in": 5.0,  "out": 25.0},
    "claude-sonnet-4-6": {"in": 3.0,  "out": 15.0},
    "claude-sonnet-5":   {"in": 3.0,  "out": 15.0},
}
# Dry-run per-pair estimate band (Opus, prompt-cached) from the 40-pair eval baseline.
EST_PER_PAIR_LOW, EST_PER_PAIR_HIGH = 2.0, 4.0


def billed_cost(model: str, usage: dict) -> float:
    """Billed USD for one curation from token usage (same model as the eval harness)."""
    pr = PRICING.get(model, {"in": 0.0, "out": 0.0})
    in_eff = (usage.get("input_tokens", 0)
              + usage.get("cache_creation_input_tokens", 0) * 1.25
              + usage.get("cache_read_input_tokens", 0) * 0.1)
    return round((in_eff * pr["in"] + usage.get("output_tokens", 0) * pr["out"]) / 1_000_000, 4)


# ── plan: expand repeats into concrete (out_path, cache_dir) curation tasks ─────

def load_pairs(pairs_file: Path) -> list[dict]:
    doc = yaml.safe_load(pairs_file.read_text(encoding="utf-8")) or {}
    return doc.get("pairs", []) if isinstance(doc, dict) else list(doc)


def build_plan(pairs: list[dict], out_root: Path, only: set[str] | None = None) -> list[dict]:
    """One task per curation. Repeat run 1 -> <id>.yaml; runs 2..N -> <id>__rK.yaml.
    Each task carries its own isolated out_path + cache_dir (never kb/paths)."""
    paths_dir = out_root / "outputs"
    cache_root = out_root / "cache"
    tasks: list[dict] = []
    for p in pairs:
        pid = p["id"]
        if only and pid not in only:
            continue
        reps = max(1, int(p.get("repeat", 1)))
        for k in range(1, reps + 1):
            tag = pid if k == 1 else f"{pid}__r{k}"
            tasks.append({
                "pair_id": pid,
                "repeat_index": k,
                "repeat_total": reps,
                "category": p.get("category"),
                "drug": p.get("drug"),
                "disease": p.get("disease"),
                "out_path": paths_dir / f"{tag}.yaml",
                "cache_dir": cache_root / tag,
            })
    return tasks


# ── the runner core (client-injectable for offline tests) ───────────────────────

def run_pilot(pairs: list[dict], *, out_root: Path = DEFAULT_OUT_ROOT,
              model: str = DEFAULT_MODEL, do_run: bool = False, critic: bool = False,
              offline: bool = False, force: bool = False, max_iters: int = 40,
              only: set[str] | None = None, client_factory=None) -> dict:
    """Plan (and, iff do_run, execute) the pilot.

    do_run=False  -> pure PLAN: builds no client, calls curate_one on nothing, hits no API.
    do_run=True   -> curates each task via curate_engine.curate_one. `client_factory`, if
                     given, supplies a client per curation (tests pass a MOCK); otherwise
                     client=None is passed to the engine, which builds the real client.
    """
    tasks = build_plan(pairs, out_root, only=only)
    n_pairs = len({t["pair_id"] for t in tasks})
    summary = {
        "generated_at": dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds"),
        "model": model, "mode": "run" if do_run else "dry-run",
        "critic": critic, "offline": offline,
        "plan": {
            "pairs": n_pairs, "curations": len(tasks),
            "est_cost_usd_low": round(len(tasks) * EST_PER_PAIR_LOW, 2),
            "est_cost_usd_high": round(len(tasks) * EST_PER_PAIR_HIGH, 2),
        },
        "results": [],
    }

    if not do_run:
        # PLAN ONLY. No client is constructed and curate_one is never called.
        return summary

    # ── live execution path (the only place a client is used) ──
    import curate_engine  # imported lazily; importing does not build a client

    run_id = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    for t in tasks:
        out_path: Path = t["out_path"]
        if out_path.exists() and not force:
            summary["results"].append({**_task_ident(t), "skipped": "output exists"})
            continue

        item = _item(t)
        client = client_factory() if client_factory is not None else None  # None => engine builds real
        t0 = time.time()
        res = curate_engine.curate_one(
            item, model=model, cache_dir=t["cache_dir"], out_path=out_path,
            client=client, max_iters=max_iters, run_id=run_id,
            offline=offline, gate_critic=critic)
        wall = round(time.time() - t0, 1)

        summary["results"].append({
            **_task_ident(t),
            "ok": res.ok,
            "gate_verdict": res.gate_verdict,
            "gate_passed": res.gate_passed,
            "stopped": res.stopped,
            "iters": res.iters,
            "wall_seconds": wall,
            "est_cost_usd": billed_cost(model, res.usage),
            "usage": res.usage,
            "tool_call_counts": res.tool_call_counts,
            "output_written": res.output_written,
            "error": res.error,
        })

    done = [r for r in summary["results"] if "skipped" not in r]
    summary["totals"] = {
        "curations": len(summary["results"]),
        "executed": len(done),
        "skipped": len(summary["results"]) - len(done),
        "ok": sum(1 for r in done if r.get("ok")),
        "total_cost_usd": round(sum(r.get("est_cost_usd", 0) or 0 for r in done), 4),
        "total_wall_seconds": round(sum(r.get("wall_seconds", 0) or 0 for r in done), 1),
    }
    return summary


def _task_ident(t: dict) -> dict:
    try:
        rel = str(t["out_path"].resolve().relative_to(REPO))
    except ValueError:
        rel = str(t["out_path"])
    return {"pair_id": t["pair_id"], "repeat_index": t["repeat_index"],
            "category": t["category"], "out_path": rel}


def _item(t: dict):
    """A curate_engine work item for one task, reusing campaign_runner.WorkItem."""
    from campaign_runner import WorkItem
    p = _PAIR_BY_ID.get(t["pair_id"], {})
    return WorkItem(id=t["pair_id"], drug=p.get("drug"), disease=p.get("disease"),
                    drug_mesh=p.get("drug_mesh"), disease_mesh=p.get("disease_mesh"),
                    drugbank=p.get("drugbank"))


_PAIR_BY_ID: dict = {}   # populated by main()/callers so _item() can resolve identifiers


# ── printing ─────────────────────────────────────────────────────────────────────

def print_plan(summary: dict, tasks: list[dict]) -> None:
    pl = summary["plan"]
    print(f"PILOT PLAN ({summary['mode'].upper()}) — model={summary['model']} "
          f"critic={summary['critic']} offline={summary['offline']}")
    print(f"  {pl['pairs']} pairs -> {pl['curations']} curations "
          f"(repeats expanded)")
    print(f"  est cost (Opus, prompt-cached, ${EST_PER_PAIR_LOW:.0f}-${EST_PER_PAIR_HIGH:.0f}/curation): "
          f"${pl['est_cost_usd_low']:.0f} - ${pl['est_cost_usd_high']:.0f}")
    print("  curations:")
    for t in tasks:
        rep = f"  (repeat {t['repeat_index']}/{t['repeat_total']})" if t["repeat_total"] > 1 else ""
        print(f"    [{t['category']:15s}] {t['out_path'].name:30s} "
              f"{t['drug']} -> {t['disease']}{rep}")
    print("\n  DRY RUN: no Anthropic client was constructed and no API call was made.")
    print("  To execute the real pilot, re-run with --run (this bills the API).")


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--pairs", type=Path, default=DEFAULT_PAIRS,
                    help=f"pilot manifest (default {DEFAULT_PAIRS.relative_to(REPO)})")
    ap.add_argument("--out-root", type=Path, default=DEFAULT_OUT_ROOT,
                    help="root for outputs/ + cache/ + run_summary.json (never kb/paths)")
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--run", action="store_true",
                    help="ACTUALLY curate (bills the API). Without this, prints the plan only.")
    ap.add_argument("--critic", action="store_true",
                    help="let the in-loop gate run the semantic critic (an LLM call). "
                         "Default off: deterministic gate, no critic call.")
    ap.add_argument("--offline", action="store_true",
                    help="evidence fetch is cache-only (reproducible; no live sources).")
    ap.add_argument("--force", action="store_true", help="re-curate even if the output exists.")
    ap.add_argument("--max-iters", type=int, default=40)
    ap.add_argument("--only", default="", help="comma-separated pair ids to include (default all).")
    args = ap.parse_args(argv)

    if not args.pairs.exists():
        print(f"ERROR: {args.pairs} not found — run scripts/select_pilot_pairs.py first.",
              file=sys.stderr)
        return 2

    pairs = load_pairs(args.pairs)
    _PAIR_BY_ID.clear()
    _PAIR_BY_ID.update({p["id"]: p for p in pairs})
    only = {s.strip() for s in args.only.split(",") if s.strip()} or None

    summary = run_pilot(
        pairs, out_root=args.out_root, model=args.model, do_run=args.run,
        critic=args.critic, offline=args.offline, force=args.force,
        max_iters=args.max_iters, only=only)

    if not args.run:
        print_plan(summary, build_plan(pairs, args.out_root, only=only))
        return 0

    # live run: persist the metrics summary next to the outputs
    out_summary = args.out_root / SUMMARY_NAME
    out_summary.parent.mkdir(parents=True, exist_ok=True)
    out_summary.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    tt = summary.get("totals", {})
    print(f"PILOT RUN complete — {tt.get('executed')} curated "
          f"({tt.get('ok')} ok), {tt.get('skipped')} skipped.")
    print(f"  total cost ${tt.get('total_cost_usd')} · wall {tt.get('total_wall_seconds')}s")
    print(f"  metrics -> {out_summary.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
