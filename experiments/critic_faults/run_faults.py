#!/usr/bin/env python3
"""
Semantic-critic fault-injection experiment.

QUESTION
    Does the semantic critic detect mechanistic faults that every deterministic
    layer accepts?

DESIGN — matched pairs
    For each pilot-curated record named in mutations.yaml we build two variants:
      MUTANT  — one injected fault (near-miss target substitution, or polarity
                inversion). The mechanism is now false.
      CONTROL — the unmutated record.
    Both are run through the critic under identical conditions. The pair differs
    in exactly one edit, so the mutation is the only variable.

    CONTROLS ARE NOT OPTIONAL. A detection rate without a false-positive rate is
    meaningless: a critic that rejects everything would score 100% detection. We
    report the full 2x2 and derive sensitivity AND specificity.

PRECONDITION (verified, not assumed)
    Every variant must PASS the deterministic gate (qc.py Layers 1-4 offline +
    the HARD structural checks). A mutant the gate catches is a test of the gate,
    not of the critic, and is EXCLUDED and reported as such.

CONFOUND CONTROLS
    state      every run gets a fresh DMDB_CRITIC_STATE_DIR and a redirected
               provenance dir, so no run can read another run's sidecar history.
    round      every run pinned to round 1, so none reaches the second-round
               "affirmed-weak / escalate-last" logic that changes the verdict rule.
    blinding   the critic sees path content only; variant ids are neutral and
               contain no arm marker.
    order      mutant/control runs are interleaved, so API drift hits both arms
               equally.
    model      judge model pinned explicitly and recorded.
    cache      Layer 4 verifies against the ORIGINAL per-record pilot cache, so
               snippet verifiability is identical across arms.

OUTPUT
    results.jsonl   one line per run, written incrementally (crash-safe, resumable)
    summary.json    the 2x2, per-fault-class breakdown, exclusions

USAGE
    python experiments/critic_faults/run_faults.py --run        # live (spends API)
    python experiments/critic_faults/run_faults.py              # dry plan, no API
    python experiments/critic_faults/run_faults.py --run --only DB00002_MESH_D003110_1
Exit: 0 ok · 2 setup error.
"""
from __future__ import annotations

import argparse
import copy
import json
import os
import random
import sys
import traceback
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PILOT_OUT = REPO / "experiments" / "pilot" / "outputs"
PILOT_CACHE = REPO / "experiments" / "pilot" / "cache"
SPEC = HERE / "mutations.yaml"
WORK = HERE / "work"
RESULTS = HERE / "results.jsonl"
SUMMARY = HERE / "summary.json"

sys.path.insert(0, str(REPO / "scripts" / "quality"))
sys.path.insert(0, str(REPO / "scripts"))

import structural_quality  # noqa: E402
import gate as gate_mod  # noqa: E402
import quality_profile as qp  # noqa: E402
import critic as critic_mod  # noqa: E402

SEED = 20260824


# ── variant construction ──────────────────────────────────────────────────────

def apply_fault(doc: dict, spec: dict) -> dict:
    """Return a mutated copy of `doc`. Raises if the spec does not match the doc,
    so a silently-unapplied mutation can never enter the experiment."""
    d = copy.deepcopy(doc)
    kind = spec["fault"]

    if kind == "target_substitution":
        src, dst = spec["from_id"], spec["to_id"]
        hit = False
        for n in d.get("nodes") or []:
            if n.get("id") == src:
                n["id"] = dst
                n["name"] = spec["to_name"]
                hit = True
        if not hit:
            raise ValueError(f"node {src} not found")
        for l in d.get("links") or []:
            if l.get("source") == src:
                l["source"] = dst
            if l.get("target") == src:
                l["target"] = dst

    elif kind == "polarity_inversion":
        i = spec["edge_index"]
        links = d.get("links") or []
        if i >= len(links):
            raise ValueError(f"edge_index {i} out of range")
        if links[i].get("key") != spec["from_key"]:
            raise ValueError(
                f"edge {i} key is {links[i].get('key')!r}, spec expects {spec['from_key']!r}")
        links[i]["key"] = spec["to_key"]

    else:
        raise ValueError(f"unknown fault {kind!r}")

    return d


def write_variant(doc: dict, record: str, arm: str, out_dir: Path) -> tuple[Path, str]:
    """Write a variant with a NEUTRAL record id. The id encodes an opaque index,
    never the arm, so nothing the critic reads can reveal which arm it is."""
    vid = f"{record}_v{'1' if arm == 'control' else '2'}"
    d = copy.deepcopy(doc)
    d.setdefault("graph", {})["_id"] = vid
    out_dir.mkdir(parents=True, exist_ok=True)
    p = out_dir / f"{vid}.yaml"
    p.write_text(yaml.safe_dump(d, sort_keys=False, allow_unicode=True))
    return p, vid


# ── deterministic precondition ────────────────────────────────────────────────

def gate_passes(path: Path, cache_dir: Path) -> tuple[bool, dict]:
    """Run the deterministic gate only (no critic) with Layer 4 pinned to the
    record's own pilot cache."""
    os.environ["DMDB_CACHE_DIR"] = str(cache_dir.resolve())
    passed, fb = gate_mod.run_gate(str(path), backend=None, run_critic=False, offline=True)
    d = fb.to_dict()
    return passed, {
        "verdict": d["verdict"],
        "qc_failures": [f.get("name") for f in d.get("qc_failures") or []],
        "hard_structural": [f.get("code") for f in d.get("hard_structural") or []],
    }


# ── one critic run, fully isolated ────────────────────────────────────────────

def run_one(path: Path, vid: str, backend, state_root: Path) -> dict:
    state = state_root / vid
    state.mkdir(parents=True, exist_ok=True)
    os.environ["DMDB_CRITIC_STATE_DIR"] = str(state)
    prov = state / "provenance"
    prov.mkdir(parents=True, exist_ok=True)
    saved = critic_mod.PROVENANCE_DIR
    critic_mod.PROVENANCE_DIR = prov          # never touch the repo's provenance/
    try:
        res = critic_mod.run_critic(
            str(path), backend,
            round_no=1, max_rounds=4,          # pinned: no second-round verdict logic
            use_cache=True, require_qc=False,  # gate verified separately, with the right cache
        )
        return {
            "verdict": res.get("verdict"),
            "escalation_reason": res.get("escalation_reason"),
            "n_flags": len(res.get("flags") or []),
            "flags": res.get("flags"),
            "path_issue": res.get("path_issue"),
            "n_independent_sources": res.get("n_independent_sources"),
            "summary": res.get("summary"),
        }
    finally:
        critic_mod.PROVENANCE_DIR = saved


REJECT = {"RE_CURATE", "ESCALATE"}


def classify(verdict: str | None) -> str:
    if verdict in REJECT:
        return "rejected"
    if verdict == "ACCEPT":
        return "accepted"
    return "indeterminate"          # ABSTAIN / QC_NOT_PASSED / error


# ── main ──────────────────────────────────────────────────────────────────────

def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--run", action="store_true", help="actually call the API (spends money)")
    ap.add_argument("--only", help="restrict to one record id")
    ap.add_argument("--model", default=os.environ.get("DMDB_JUDGE_MODEL", "claude-opus-4-8"))
    args = ap.parse_args()

    spec = yaml.safe_load(SPEC.read_text())["faults"]
    if args.only:
        spec = [s for s in spec if s["record"] == args.only]
    if not spec:
        print("no faults selected", file=sys.stderr)
        return 2

    # ── build + verify every variant BEFORE spending anything ─────────────────
    units, excluded = [], []
    for s in spec:
        rec = s["record"]
        src = PILOT_OUT / f"{rec}.yaml"
        cache = PILOT_CACHE / rec
        if not src.exists():
            excluded.append({"record": rec, "why": "missing pilot output"}); continue
        doc = yaml.safe_load(src.read_text())
        try:
            mut = apply_fault(doc, s)
        except Exception as e:
            excluded.append({"record": rec, "why": f"mutation did not apply: {e}"}); continue

        wd = WORK / rec
        cp, cid = write_variant(doc, rec, "control", wd)
        mp, mid = write_variant(mut, rec, "mutant", wd)

        c_ok, c_det = gate_passes(cp, cache)
        m_ok, m_det = gate_passes(mp, cache)
        if not (c_ok and m_ok):
            excluded.append({"record": rec, "why": "variant failed the deterministic gate",
                             "control": c_det, "mutant": m_det})
            continue

        units.append({"record": rec, "fault": s["fault"], "rationale": s.get("rationale", "").strip(),
                      "control": {"id": cid, "path": str(cp)},
                      "mutant": {"id": mid, "path": str(mp)},
                      "cache": str(cache)})

    print(f"pairs ready: {len(units)}   excluded: {len(excluded)}")
    for e in excluded:
        print(f"  EXCLUDED {e['record']}: {e['why']}")
    print(f"runs to perform: {len(units) * 2}   judge model: {args.model}")

    if not args.run:
        print("\nDRY PLAN — no API call made. Re-run with --run to execute.")
        for u in units:
            print(f"  {u['record']:<28} {u['fault']}")
        return 0

    backend, note = qp.make_backend("anthropic")
    if backend is None:
        print(f"cannot run: {note}", file=sys.stderr)
        return 2
    print(f"backend: {note}")

    # interleave arms so API drift hits both equally
    queue = []
    for u in units:
        queue.append((u, "control"))
        queue.append((u, "mutant"))
    random.Random(SEED).shuffle(queue)

    done = set()
    if RESULTS.exists():                      # resumable
        for line in RESULTS.read_text().splitlines():
            try:
                done.add(json.loads(line)["variant_id"])
            except Exception:
                pass
        print(f"resuming — {len(done)} runs already recorded")

    state_root = WORK / "_state"
    with RESULTS.open("a") as fh:
        for i, (u, arm) in enumerate(queue, 1):
            v = u[arm]
            if v["id"] in done:
                continue
            os.environ["DMDB_CACHE_DIR"] = u["cache"]
            print(f"[{i}/{len(queue)}] {u['record']} {arm} …", flush=True)
            rec = {"record": u["record"], "arm": arm, "fault": u["fault"],
                   "variant_id": v["id"], "model": args.model}
            try:
                rec.update(run_one(Path(v["path"]), v["id"], backend, state_root))
                rec["error"] = None
            except Exception as e:
                rec.update({"verdict": None, "error": f"{type(e).__name__}: {e}"})
                traceback.print_exc()
            rec["outcome"] = classify(rec.get("verdict"))
            fh.write(json.dumps(rec, default=str) + "\n")
            fh.flush()
            print(f"      -> {rec.get('verdict')} ({rec['outcome']})", flush=True)

    summarize(units, excluded, args.model)
    return 0


def summarize(units, excluded, model) -> None:
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]
    by = {(r["record"], r["arm"]): r for r in rows}

    cells = {"mutant_rejected": 0, "mutant_accepted": 0, "mutant_indeterminate": 0,
             "control_rejected": 0, "control_accepted": 0, "control_indeterminate": 0}
    per_class: dict = {}
    paired = []
    for u in units:
        m, c = by.get((u["record"], "mutant")), by.get((u["record"], "control"))
        if not m or not c:
            continue
        cells[f"mutant_{m['outcome']}"] += 1
        cells[f"control_{c['outcome']}"] += 1
        k = u["fault"]
        pc = per_class.setdefault(k, {"n": 0, "detected": 0, "control_false_positive": 0})
        pc["n"] += 1
        pc["detected"] += int(m["outcome"] == "rejected")
        pc["control_false_positive"] += int(c["outcome"] == "rejected")
        paired.append({"record": u["record"], "fault": k,
                       "mutant_verdict": m.get("verdict"), "control_verdict": c.get("verdict"),
                       "detected": m["outcome"] == "rejected",
                       "control_clean": c["outcome"] == "accepted"})

    n = len(paired)
    det = sum(p["detected"] for p in paired)
    fp = sum(1 for p in paired if not p["control_clean"])
    out = {
        "n_pairs_completed": n,
        "judge_model": model,
        "detection_rate": round(det / n, 3) if n else None,
        "control_false_positive_rate": round(fp / n, 3) if n else None,
        "cells": cells,
        "per_fault_class": per_class,
        "excluded": excluded,
        "pairs": paired,
    }
    SUMMARY.write_text(json.dumps(out, indent=2))
    print("\n=== SUMMARY ===")
    print(f"pairs completed        : {n}")
    print(f"faults detected        : {det}/{n}" + (f"  ({det/n:.0%})" if n else ""))
    print(f"controls false-flagged : {fp}/{n}" + (f"  ({fp/n:.0%})" if n else ""))
    for k, v in per_class.items():
        print(f"  {k:<22} detected {v['detected']}/{v['n']}   control FP {v['control_false_positive']}/{v['n']}")
    print(f"\nwrote {SUMMARY}")


if __name__ == "__main__":
    sys.exit(main())
