"""
Post-QC structural quality analysis (deterministic — NO LLM).

Reads a DrugMechDB path that already passed the Layer 1-4 QC gate and computes the
structural quality signals from docs/path_quality_framework.md §4 and the issue
taxonomy in docs/quality_system_design.md. It is a SCORER/REPORTER, not a gate.

Severity tiers:
  HARD  a logical error a correct mechanism cannot have (high precision, act on these)
  SOFT  a convention/prioritization signal (review, not necessarily wrong)
  INFO  a note (e.g. relied on a review-confidence predicate sign)

Checks:
  connectivity         HARD  no drug->disease path (disconnected / id mismatch)
  cycle                HARD  directed cycle (paths must be acyclic)
  duplicate_edge       HARD  identical (source,target,key) repeated
  type_violation       HARD  predicate domain/range violated (e.g. 'decreases activity of' a Disease)
  net_polarity         HARD  incoherent (all branches net +) or inconsistent (branches disagree)
                       SOFT  indeterminate (reverse/opaque predicate; cannot compose safely)
  short_circuit        HARD  a <=2-edge path bypasses the >=3-edge mechanism
  clinical_shortcut    HARD  clinical-outcome edge (treats/...) used as a bypass
  direct_drug_disease  HARD  drug's only target is the disease itself
  noncanonical_start   INFO  first target is not a Protein (allowed but non-canonical)
  length_out_of_range  SOFT  outside 3-7 links
  dangling_node        SOFT  node not on any drug->disease path
  unknown_predicate    SOFT  predicate missing from the polarity lexicon
  review_predicate     INFO  net polarity relied on a review-confidence sign

Usage:
    python scripts/quality/structural_quality.py kb/paths/<file>.yaml
    python scripts/quality/structural_quality.py                       # corpus summary
    python scripts/quality/structural_quality.py --json <file>
    python scripts/quality/structural_quality.py --severity HARD       # only HARD-flagged
"""

from __future__ import annotations

import argparse
import json
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Iterable

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent
PATHS_DIR = REPO / "kb" / "paths"
LEXICON_FILE = HERE / "predicate_polarity.yaml"

LENGTH_MIN, LENGTH_MAX = 3, 7
CANONICAL_FIRST_TARGET = {"Protein", "GeneFamily", "MacromolecularComplex"}
MAX_SIMPLE_PATHS = 512  # safety cap; DMDB paths are tiny so this is never approached


# ── lexicon ─────────────────────────────────────────────────────────────────

def load_lexicon() -> dict:
    doc = yaml.safe_load(LEXICON_FILE.read_text())
    preds = doc["predicates"]
    groups = doc.get("type_groups", {})

    def resolve(spec):
        if spec is None:
            return None
        return set(groups[spec]) if isinstance(spec, str) else set(spec)

    constraints = {}
    for pred, c in (doc.get("type_constraints") or {}).items():
        constraints[pred] = {"subj_in": resolve(c.get("subj_in")), "obj_in": resolve(c.get("obj_in"))}
    return {"predicates": preds, "constraints": constraints}


def orientation(entry: dict) -> str:
    """forward | reverse | neutral | opaque — derived from role + sign."""
    role, sign = entry.get("role"), entry.get("sign", 0)
    if role in ("contextual", "structural"):
        return "neutral"
    if role == "reverse":
        return "reverse"
    if sign == 0:
        return "opaque"          # directional role but unknown sign (regulates, correlated with, ...)
    return "forward"


# ── graph helpers ─────────────────────────────────────────────────────────────

def simple_paths(adj, src, dst):
    out = []

    def dfs(node, visited, trail):
        if len(out) >= MAX_SIMPLE_PATHS:
            return
        if node == dst and trail:
            out.append(list(trail)); return
        for (nbr, pred) in adj.get(node, []):
            if nbr in visited:
                continue
            visited.add(nbr); trail.append((node, nbr, pred))
            dfs(nbr, visited, trail)
            trail.pop(); visited.discard(nbr)

    if src and dst:
        dfs(src, {src}, [])
    return out


def has_cycle(nodes, adj) -> bool:
    WHITE, GRAY, BLACK = 0, 1, 2
    color = {n: WHITE for n in nodes}

    def visit(u) -> bool:
        color[u] = GRAY
        for (v, _k) in adj.get(u, []):
            if color.get(v) == GRAY:
                return True
            if color.get(v) == WHITE and visit(v):
                return True
        color[u] = BLACK
        return False

    return any(color[n] == WHITE and visit(n) for n in nodes)


# ── polarity over all drug->disease paths ─────────────────────────────────────

def path_polarity(path_edges, preds):
    """Return ('product', int) | ('indeterminate', reason) | ('all_neutral', None),
    plus the set of review-confidence predicates relied on and unknown predicates."""
    product, n_forward = 1, 0
    reviewed, unknown = [], []
    for (_s, _t, pred) in path_edges:
        e = preds.get(pred)
        if e is None:
            unknown.append(pred)
            return ("indeterminate", "unknown_predicate"), reviewed, unknown
        ori = orientation(e)
        if ori == "neutral":
            continue
        if ori in ("reverse", "opaque"):
            return ("indeterminate", ori), reviewed, unknown
        product *= e["sign"]; n_forward += 1
        if e.get("confidence") == "review":
            reviewed.append(pred)
    if n_forward == 0:
        return ("all_neutral", None), reviewed, unknown
    return ("product", product), reviewed, unknown


def analyze(path: Path, lex: dict) -> dict:
    preds, constraints = lex["predicates"], lex["constraints"]
    doc = yaml.safe_load(path.read_text())
    graph = doc.get("graph", {}) or {}
    nodes = doc.get("nodes", []) or []
    links = doc.get("links", []) or []

    label = {n.get("id"): n.get("label") for n in nodes if isinstance(n, dict)}
    adj = defaultdict(list)
    indeg, outdeg = Counter(), Counter()
    edge_counts = Counter()
    for e in links:
        s, t, k = e.get("source"), e.get("target"), e.get("key")
        adj[s].append((t, k)); outdeg[s] += 1; indeg[t] += 1
        edge_counts[(s, t, k)] += 1

    drug = graph.get("drug_mesh") if graph.get("drug_mesh") in label else None
    if drug is None:
        srcs = [n for n in label if indeg[n] == 0]
        drug = srcs[0] if srcs else None
    disease = graph.get("disease_mesh") if graph.get("disease_mesh") in label else None
    if disease is None:
        sinks = [n for n in label if outdeg[n] == 0]
        disease = sinks[0] if sinks else None

    flags = []
    def flag(sev, code, msg): flags.append({"severity": sev, "code": code, "msg": msg})

    # connectivity + paths
    paths = simple_paths(adj, drug, disease)
    if not paths:
        flag("HARD", "connectivity", "no drug->disease path (disconnected or node-id mismatch)")

    # cycle / duplicate
    if has_cycle(list(label), adj):
        flag("HARD", "cycle", "directed cycle present (path must be acyclic)")
    for (s, t, k), c in edge_counts.items():
        if c > 1:
            flag("HARD", "duplicate_edge", f"edge repeated {c}x: {s} --{k}--> {t}")

    # predicate domain/range
    for e in links:
        k = e.get("key"); c = constraints.get(k)
        if not c:
            continue
        ls, lo = label.get(e.get("source")), label.get(e.get("target"))
        if c["subj_in"] and ls and ls not in c["subj_in"]:
            flag("HARD", "type_violation", f"'{k}' subject is {ls} (expected {sorted(c['subj_in'])})")
        if c["obj_in"] and lo and lo not in c["obj_in"]:
            flag("HARD", "type_violation", f"'{k}' object is {lo} (expected {sorted(c['obj_in'])})")

    # net polarity over ALL paths
    pol_summary = None
    if paths:
        products, indet, allneutral, reviewed_all = [], 0, 0, set()
        for p in paths:
            kind, reviewed, _unk = path_polarity(p, preds)
            reviewed_all.update(reviewed)
            if kind[0] == "product":
                products.append(kind[1])
            elif kind[0] == "indeterminate":
                indet += 1
            else:
                allneutral += 1
        if products:
            if all(x < 0 for x in products):
                pol_summary = "coherent"
            elif all(x > 0 for x in products):
                pol_summary = "incoherent"
                flag("HARD", "net_polarity", "every determinable branch nets POSITIVE — drug appears to NOT suppress disease")
            else:
                pol_summary = "inconsistent"
                flag("HARD", "net_polarity", f"branches disagree in net sign ({sum(x<0 for x in products)} negative / {sum(x>0 for x in products)} positive) — over-modeling or a sign error")
        else:
            pol_summary = "indeterminate"
            flag("SOFT", "net_polarity", f"polarity indeterminate ({indet} reverse/opaque, {allneutral} all-neutral path(s))")
        if reviewed_all and pol_summary in ("coherent", "incoherent", "inconsistent"):
            flag("INFO", "review_predicate", f"polarity relied on review-confidence sign(s): {sorted(reviewed_all)}")

    # short-circuit / clinical shortcut
    if len(paths) > 1:
        lens = sorted(len(p) for p in paths)
        if lens[0] <= 2 and lens[-1] >= 3:
            short = min(paths, key=len)
            flag("HARD", "short_circuit", f"a {lens[0]}-edge path bypasses the {lens[-1]}-edge mechanism: "
                 + " -> ".join([short[0][0]] + [t for (_s, t, _k) in short]))
    for e in links:
        ent = preds.get(e.get("key"), {})
        if ent.get("role") == "clinical_outcome" and e.get("source") == drug and e.get("target") == disease and len(links) > 1:
            flag("HARD", "clinical_shortcut", f"clinical-outcome edge '{e.get('key')}' used directly drug->disease")

    # start convention
    first_targets = [label.get(t) for (t, _k) in adj.get(drug, [])]
    if first_targets and all(lt in ("Disease", "PhenotypicFeature") for lt in first_targets):
        flag("HARD", "direct_drug_disease", f"drug's only target(s) are {first_targets} (no molecular entry point)")
    elif first_targets and not any(lt in CANONICAL_FIRST_TARGET for lt in first_targets):
        flag("INFO", "noncanonical_start", f"first target(s) {first_targets} not a Protein (allowed, non-canonical)")

    # length
    n = len(links)
    if not (LENGTH_MIN <= n <= LENGTH_MAX):
        flag("SOFT", "length_out_of_range", f"{n} links (outside {LENGTH_MIN}-{LENGTH_MAX})")

    # dangling nodes
    if paths:
        on_path = {drug, disease}
        for p in paths:
            for (s, t, _k) in p:
                on_path.add(s); on_path.add(t)
        dangling = [nid for nid in label if nid not in on_path]
        if dangling:
            flag("SOFT", "dangling_node", f"{len(dangling)} node(s) not on any drug->disease path: {dangling}")

    # unknown predicate (record-level)
    unknown = sorted({e.get("key") for e in links if e.get("key") not in preds})
    if unknown:
        flag("SOFT", "unknown_predicate", f"predicate(s) not in lexicon: {unknown}")

    sev = {s: sum(1 for f in flags if f["severity"] == s) for s in ("HARD", "SOFT", "INFO")}
    try:
        rel = str(path.resolve().relative_to(REPO))
    except ValueError:
        rel = str(path)
    return {
        "file": rel, "id": graph.get("_id"),
        "n_nodes": len(nodes), "n_edges": len(links), "n_paths": len(paths),
        "polarity": pol_summary, "flags": flags, "severity_counts": sev,
        "clean_hard": sev["HARD"] == 0, "clean": len(flags) == 0,
    }


# ── CLI ───────────────────────────────────────────────────────────────────────

def iter_files(targets):
    targets = list(targets)
    if not targets:
        return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    files = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
        elif p.is_file():
            files.append(p)
    return files


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("targets", nargs="*")
    ap.add_argument("--json", action="store_true")
    ap.add_argument("--severity", choices=("HARD", "SOFT", "INFO"), help="Only show records with >=1 flag of this severity")
    args = ap.parse_args()

    lex = load_lexicon()
    results = [analyze(f, lex) for f in iter_files(args.targets)]
    if args.severity:
        shown = [r for r in results if r["severity_counts"][args.severity] > 0]
    else:
        shown = results

    if args.json:
        print(json.dumps(shown, indent=2)); return 0

    if len(shown) <= 25:
        for r in shown:
            tag = "OK  " if r["clean"] else ("HARD" if not r["clean_hard"] else "soft")
            print(f"[{tag}] {r['id']}  ({r['n_nodes']}n/{r['n_edges']}e, {r['n_paths']} path(s), polarity={r['polarity']})")
            for f in r["flags"]:
                print(f"        [{f['severity']}] {f['code']}: {f['msg']}")

    n = len(results)
    by_code = Counter(); by_sev = Counter()
    for r in results:
        for f in r["flags"]:
            by_code[(f["severity"], f["code"])] += 1
        for s in ("HARD", "SOFT", "INFO"):
            if r["severity_counts"][s] > 0:
                by_sev[s] += 1
    n_clean = sum(1 for r in results if r["clean"])
    n_hard = sum(1 for r in results if not r["clean_hard"])
    print(f"\n=== Structural quality summary ({n} records) ===")
    print(f"  Clean (no flags)         : {n_clean} ({n_clean/n:.1%})")
    print(f"  HARD-clean (no logical err): {n - n_hard} ({(n-n_hard)/n:.1%})")
    print(f"  >=1 HARD flag            : {n_hard} ({n_hard/n:.1%})")
    print(f"  >=1 SOFT flag            : {by_sev['SOFT']} ({by_sev['SOFT']/n:.1%})")
    print(f"  polarity: " + ", ".join(f"{k}={v}" for k, v in Counter(r['polarity'] for r in results).most_common()))
    print("  Flags by code:")
    for (sev, code), c in sorted(by_code.items(), key=lambda x: (-x[1])):
        print(f"    {c:>5}  [{sev}] {code}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
