#!/usr/bin/env python3
"""
Analyse the prompt-caching validation run (experiments/caching_test/).

Caching changes what a request costs, not what the model sees, so each curation is
priced three ways from its own recorded per-turn usage — no control arm is needed:

  actual       what was billed, with the static prefix AND the conversation cached
  prefix_only  the previous setup: only tools + system cached, history at full price
  no_cache     every prompt token at the base input rate

`prefix_only` is the fair baseline, because the harness already cached the prefix
before this change. The prefix size P is measured, not estimated: on the first turn of
any curation after the first, the only thing that can match an earlier cache entry is
the shared tools + system prefix, so that turn's cache_read_input_tokens equals P.

The critic records totals rather than per-turn usage, so it is priced as actual and
no_cache only.

Usage: python experiments/caching_test/analyze.py
"""
from __future__ import annotations

import json
import statistics as st
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE.parent.parent / "scripts"))
from run_pilot import PRICING, billed_cost, uncached_cost  # noqa: E402


def load_results() -> list[dict]:
    rows = []
    for f in sorted(HERE.glob("run_summary_*.json")):
        s = json.loads(f.read_text())
        for r in s.get("results", []):
            if "skipped" not in r:
                rows.append({**r, "_model": s["model"]})
    return rows


def prefix_size(rows: list[dict]) -> int:
    """Tools + system tokens: turn-1 cache reads of every curation after the first."""
    reads = [r["turn_usage"][0]["cache_read_input_tokens"] for r in rows[1:]
             if r.get("turn_usage") and r["turn_usage"][0]["cache_read_input_tokens"] > 0]
    if not reads:
        raise SystemExit("no warm first turn to measure the prefix from")
    if max(reads) != min(reads):
        print(f"note: prefix reads vary {sorted(set(reads))}; using the most common")
    return st.mode(reads)


def prefix_only_cost(model: str, turns: list[dict], prefix: int, warm_start: bool) -> float:
    """Price a run as if only the static prefix were cached (the previous setup)."""
    pr = PRICING[model]
    total = 0.0
    for i, t in enumerate(turns):
        prompt = (t["input_tokens"] + t["cache_read_input_tokens"]
                  + t["cache_creation_input_tokens"])
        if i == 0 and not warm_start:
            total += prefix * pr["write"]            # first curation writes the prefix
        else:
            total += prefix * pr["read"]
        total += (prompt - prefix) * pr["in"]        # history and task at full price
        total += t["output_tokens"] * pr["out"]
    return round(total / 1_000_000, 4)


def main() -> int:
    rows = load_results()
    if not rows:
        print("no completed curations yet")
        return 1
    P = prefix_size(rows)
    print(f"static prefix (tools + system): {P:,} tokens, measured\n")
    hdr = (f"{'pair':<26}{'ok':>4}{'turns':>7}{'cache-read %':>14}"
           f"{'actual':>9}{'prefix-only':>13}{'no-cache':>10}{'critic':>9}")
    print(hdr)
    print("-" * len(hdr))
    tot = {"act": 0.0, "pre": 0.0, "none": 0.0, "crit": 0.0, "crit_none": 0.0}
    for i, r in enumerate(rows):
        m, u, turns = r["_model"], r["usage"], r["turn_usage"]
        prompt = u["input_tokens"] + u["cache_read_input_tokens"] + u["cache_creation_input_tokens"]
        read_pct = 100 * u["cache_read_input_tokens"] / prompt
        act = billed_cost(m, u)
        pre = prefix_only_cost(m, turns, P, warm_start=i > 0)
        none = uncached_cost(m, u)
        crit = r.get("critic_cost_usd") or 0.0
        crit_none = r.get("critic_uncached_cost_usd") or 0.0
        for k, v in (("act", act), ("pre", pre), ("none", none),
                     ("crit", crit), ("crit_none", crit_none)):
            tot[k] += v
        print(f"{r['pair_id']:<26}{'yes' if r.get('ok') else 'no':>4}{r['iters']:>7}"
              f"{read_pct:>13.0f}%{act:>9.2f}{pre:>13.2f}{none:>10.2f}{crit:>9.2f}")
    n = len(rows)
    print("-" * len(hdr))
    print(f"{'curator, mean':<37}{'':>13}{tot['act']/n:>9.2f}{tot['pre']/n:>13.2f}"
          f"{tot['none']/n:>10.2f}")
    saving_vs_prev = 1 - tot["act"] / tot["pre"]
    saving_vs_none = 1 - tot["act"] / tot["none"]
    print(f"\ncurator saving vs previous setup (prefix-only): {saving_vs_prev:.0%}")
    print(f"curator saving vs no caching at all:           {saving_vs_none:.0%}")
    print(f"critic mean ${tot['crit']/n:.2f} actual, ${tot['crit_none']/n:.2f} with no caching "
          f"({1 - tot['crit']/tot['crit_none']:.0%} saving)" if tot["crit_none"] else "")
    print(f"total per curation (curator + critic): ${(tot['act'] + tot['crit'])/n:.2f} mean")

    # Health check from the caching guide: on a warm loop, each turn should write about
    # one turn's worth of new content, not the whole conversation again.
    print("\nper-turn cache writes (should stay small, one turn's worth each):")
    for r in rows:
        w = [t["cache_creation_input_tokens"] for t in r["turn_usage"][1:]]
        print(f"  {r['pair_id']:<26} median {st.median(w):>6,.0f}  max {max(w):>7,}  turns {len(w)+1}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
