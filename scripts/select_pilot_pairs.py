"""
scripts/select_pilot_pairs.py — pick the ~20-pair stress set for the re-curation pilot.

READ-ONLY over kb/paths. This never writes a curation and never touches the corpus; it
only reads every record to categorize it, then emits the pilot manifest to
experiments/pilot/pilot_pairs.yaml.

Every pilot pair is an EXISTING record (it already has a legacy path), so the set doubles
as the agreement-vs-legacy set: each re-curation can be compared against the curator's
legacy path for the same (drug, disease).

── WHAT THE SET STRESS-TESTS (why each bucket exists) ────────────────────────────────
The gate (scripts/quality/structural_quality.py HARD_BLOCKING_CHECKS) HARD-bounces only
four high-precision invariants — connectivity, cycle, duplicate_edge, clinical_shortcut —
and demotes short_circuit / direct_drug_disease / net_polarity / type_violation to
advisory INFO (they over-fired on the gold-standard legacy corpus). The pilot is built to
probe exactly that boundary:

  hard_gate       (~4) legacy path fires a STILL-HARD check (clinical_shortcut / duplicate_edge
                       / cycle). Re-curation must catch/repair the known issue — proves the
                       gate still bites on real errors.
  convergent      (~4) multi-target / convergent-branch drug whose legacy path fires the
                       now-DEMOTED short_circuit. Proves these legitimate convergent paths
                       now PASS instead of being wrongly bounced.
  chembl_preprint (~4) small-molecule -> named-protein-target mechanism whose compound->target
                       bioactivity is ChEMBL's core coverage (and, for newer drugs, appears in
                       preprints). Exercises the source-agnostic multi-source evidence layer
                       beyond PubMed.
  ordinary        (~8) clean legacy records (no structural flags at all) — the baseline the
                       re-curation should reproduce, and the bulk agreement-vs-legacy anchors.

~5 pairs are marked `repeat: 3` (spread across buckets) for a cross-run-consistency check:
run the same pair three times and measure how stable the agent's output is.

Selection is fully deterministic (fixed bucket predicates, record-id sort, drugbank dedupe,
fixed take-N) so re-running reproduces the same manifest. Read-only: the ONLY file written
is the manifest under experiments/pilot/.
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent               # scripts/
REPO = HERE.parent
KB_PATHS = REPO / "kb" / "paths"
INDEX = KB_PATHS / "_index.yaml"
DEFAULT_OUT = REPO / "experiments" / "pilot" / "pilot_pairs.yaml"

sys.path.insert(0, str(HERE / "quality"))            # so `import structural_quality` resolves
import structural_quality as sq                       # noqa: E402

# The three structural checks that STILL HARD-bounce a curation (a re-curation must fix
# these). Kept in sync with structural_quality.HARD_BLOCKING_CHECKS minus `connectivity`
# (0 occurrences in the corpus — nothing to select).
STILL_HARD = frozenset({"clinical_shortcut", "duplicate_edge", "cycle"})

# Category 3 pool: canonical SMALL-MOLECULE -> single named protein-target mechanisms whose
# compound->target bioactivity is a ChEMBL staple. Ordered for drug-class diversity; the
# first four whose corpus record structurally verifies (small-molecule drug with a direct
# `(in|de)creases activity of` edge to a UniProt protein) are taken. Peptide/biologic
# hormones are deliberately excluded — ChEMBL bioactivity does NOT cover them well.
CHEMBL_POOL = [
    ("DB00619_MESH_D015464_1", "ChEMBL:CHEMBL941",
     "imatinib -> BCR-ABL1 tyrosine kinase (UniProt:P00519), chronic myeloid leukemia"),
    ("DB01076_MESH_D006937_1", "ChEMBL:CHEMBL1487",
     "atorvastatin -> HMG-CoA reductase (UniProt:P04035), hypercholesterolemia"),
    ("DB00843_MESH_D000544_1", "ChEMBL:CHEMBL502",
     "donepezil -> acetylcholinesterase (UniProt:P22303), Alzheimer disease"),
    ("DB09038_MESH_D003924_1", "ChEMBL:CHEMBL2107830",
     "empagliflozin -> SGLT2 / SLC5A2 (UniProt:P31639), type-2 diabetes (newer drug — "
     "mechanism also carried by preprints)"),
    ("DB00188_MESH_D009101_1", "ChEMBL:CHEMBL325041",
     "bortezomib -> 20S proteasome subunit beta-5 (UniProt:P28074), multiple myeloma"),
    ("DB00472_MESH_D003865_1", "ChEMBL:CHEMBL41",
     "fluoxetine -> serotonin transporter SLC6A4 (UniProt:P31645), major depressive disorder"),
]

ACTIVITY_PREDS = frozenset({"decreases activity of", "increases activity of"})

# Bucket sizes and the repeat marks.
N_HARD, N_CONVERGENT, N_CHEMBL, N_ORDINARY = 4, 4, 4, 8
REPEAT_COUNT = 3          # a marked pair is curated this many times
N_REPEAT_MARKS = 5        # how many pairs get the repeat mark (spread across buckets)


# ── corpus scan (deterministic, read-only) ────────────────────────────────────

def load_index() -> dict:
    doc = yaml.safe_load(INDEX.read_text(encoding="utf-8"))
    entries = doc.values() if isinstance(doc, dict) else doc
    out = {}
    for e in entries:
        if isinstance(e, dict) and e.get("id"):
            out[e["id"]] = e
    return out


def small_molecule_protein_target(path: Path) -> bool:
    """True iff the drug node has a direct `(in|de)creases activity of` edge to a UniProt
    protein — the structural signature of a ChEMBL-covered compound->target mechanism."""
    doc = yaml.safe_load(path.read_text(encoding="utf-8"))
    graph = doc.get("graph", {}) or {}
    nodes = {n.get("id"): n for n in doc.get("nodes", []) if isinstance(n, dict)}
    drug = graph.get("drug_mesh")
    for e in doc.get("links", []) or []:
        if e.get("source") != drug or e.get("key") not in ACTIVITY_PREDS:
            continue
        tgt = nodes.get(e.get("target"), {})
        if tgt.get("label") == "Protein" and str(e.get("target")).startswith("UniProt"):
            return True
    return False


def scan_corpus() -> dict:
    """id -> {codes:set, msgs:{code:msg}, polarity, n_edges}. One analyze() per record."""
    lex = sq.load_lexicon()
    files = sorted(p for p in KB_PATHS.glob("*.yaml") if p.name != "_index.yaml")
    info = {}
    for f in files:
        r = sq.analyze(f, lex)
        info[f.stem] = {
            "codes": {fl["code"] for fl in r["flags"]},
            "msgs": {fl["code"]: fl["msg"] for fl in r["flags"]},
            "polarity": r["polarity"],
            "n_edges": r["n_edges"],
        }
    return info


# ── bucket selection ───────────────────────────────────────────────────────────

def _take_distinct_drugbank(candidates, index, used_db, n):
    """From id-sorted `candidates`, take up to n whose drugbank is not yet used (one per drug)."""
    picked = []
    for rid in candidates:
        db = (index.get(rid, {}) or {}).get("drugbank")
        if db in used_db:
            continue
        picked.append(rid)
        used_db.add(db)
        if len(picked) >= n:
            break
    return picked


def select(info: dict, index: dict) -> dict:
    used_db: set = set()
    buckets: dict = {}

    # 1. hard_gate — guarantee coverage of all three still-HARD checks: the single cycle
    #    record + the single clinical_shortcut record, then fill with duplicate_edge
    #    (distinct drug). All id-sorted for determinism.
    def with_code(code):
        return sorted(rid for rid, d in info.items() if code in d["codes"])

    hard: list = []
    for code in ("cycle", "clinical_shortcut"):
        for rid in with_code(code):
            if (index.get(rid, {}) or {}).get("drugbank") not in used_db:
                hard.append(rid)
                used_db.add((index.get(rid, {}) or {}).get("drugbank"))
                break
    dup = [rid for rid in with_code("duplicate_edge") if rid not in hard]
    hard += _take_distinct_drugbank(dup, index, used_db, N_HARD - len(hard))
    buckets["hard_gate"] = sorted(hard)

    # 2. convergent — short_circuit (now advisory INFO) + coherent polarity + a molecular
    #    entry point (NOT direct_drug_disease) + no still-HARD flag: the legitimate
    #    convergent-branch shape the demoted check used to over-bounce.
    conv_cands = sorted(
        rid for rid, d in info.items()
        if "short_circuit" in d["codes"]
        and d["polarity"] == "coherent"
        and "direct_drug_disease" not in d["codes"]
        and not (d["codes"] & STILL_HARD))
    buckets["convergent"] = sorted(_take_distinct_drugbank(conv_cands, index, used_db, N_CONVERGENT))

    # 3. chembl_preprint — first N of the curated pool that exist and structurally verify.
    chembl: list = []
    for rid, chembl_id, note in CHEMBL_POOL:
        if len(chembl) >= N_CHEMBL:
            break
        f = KB_PATHS / f"{rid}.yaml"
        db = (index.get(rid, {}) or {}).get("drugbank")
        if rid not in index or not f.exists() or db in used_db:
            continue
        if not small_molecule_protein_target(f):
            continue
        chembl.append(rid)
        used_db.add(db)
        info[rid]["chembl_id"] = chembl_id
        info[rid]["chembl_note"] = note
    buckets["chembl_preprint"] = sorted(chembl)

    # 4. ordinary — perfectly clean records (no flag of any severity), distinct drug,
    #    excluding drugs already used above.
    clean = sorted(rid for rid, d in info.items() if not d["codes"])
    buckets["ordinary"] = sorted(_take_distinct_drugbank(clean, index, used_db, N_ORDINARY))
    return buckets


def build_why(rid: str, category: str, info: dict) -> str:
    d = info[rid]
    if category == "hard_gate":
        hits = sorted(d["codes"] & STILL_HARD)
        detail = "; ".join(d["msgs"][c] for c in hits)
        return (f"legacy path fires still-HARD gate check(s) {hits}: {detail}. "
                f"Re-curation must catch/repair this known error — proves the gate still bites.")
    if category == "convergent":
        return (f"multi-target/convergent-branch drug ({d['n_edges']}-edge, coherent): legacy path "
                f"fires the now-DEMOTED short_circuit ({d['msgs'].get('short_circuit', '')}). "
                f"With short_circuit advisory-only, re-curation should PASS.")
    if category == "chembl_preprint":
        return (f"{d.get('chembl_note', '')}. Compound->target bioactivity is ChEMBL's core "
                f"coverage ({d.get('chembl_id', '')}) — exercises the non-PubMed multi-source "
                f"evidence layer.")
    return (f"clean legacy record (no structural flags; {d['n_edges']}-edge {d['polarity']} path) — "
            f"ordinary baseline + agreement-vs-legacy anchor.")


def assemble(buckets: dict, info: dict, index: dict) -> list[dict]:
    # repeat marks: one per bucket for hard_gate/convergent/chembl_preprint + two ordinary,
    # so the consistency check spans easy and hard cases. Deterministic (first id-sorted).
    marks: set = set()
    for cat in ("hard_gate", "convergent", "chembl_preprint"):
        if buckets.get(cat):
            marks.add(buckets[cat][0])
    marks.update(buckets.get("ordinary", [])[:N_REPEAT_MARKS - len(marks)])

    rows: list[dict] = []
    for cat in ("hard_gate", "convergent", "chembl_preprint", "ordinary"):
        for rid in buckets.get(cat, []):
            e = index.get(rid, {}) or {}
            rows.append({
                "id": rid,
                "drug": e.get("drug"),
                "disease": e.get("disease"),
                "drug_mesh": e.get("drug_mesh"),
                "disease_mesh": e.get("disease_mesh"),
                "drugbank": e.get("drugbank"),
                "category": cat,
                "why": build_why(rid, cat, info),
                "repeat": REPEAT_COUNT if rid in marks else 1,
            })
    return rows


# ── CLI ─────────────────────────────────────────────────────────────────────────

def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT,
                    help=f"manifest output path (default {DEFAULT_OUT.relative_to(REPO)})")
    ap.add_argument("--print-only", action="store_true",
                    help="print the chosen set but do NOT write the manifest")
    args = ap.parse_args(argv)

    index = load_index()
    print(f"Scanning {sum(1 for _ in KB_PATHS.glob('*.yaml')) - 1} corpus records "
          f"(read-only) to categorize ...")
    info = scan_corpus()
    buckets = select(info, index)
    rows = assemble(buckets, info, index)

    n_repeat = sum(1 for r in rows if r["repeat"] > 1)
    n_curations = sum(r["repeat"] for r in rows)
    print(f"\n=== Pilot set: {len(rows)} pairs · {n_repeat} marked repeat={REPEAT_COUNT} "
          f"· {n_curations} total curations ===\n")
    for cat in ("hard_gate", "convergent", "chembl_preprint", "ordinary"):
        crows = [r for r in rows if r["category"] == cat]
        print(f"── {cat} ({len(crows)}) " + "─" * (60 - len(cat)))
        for r in crows:
            rep = f"  [repeat x{r['repeat']}]" if r["repeat"] > 1 else ""
            print(f"  {r['id']:26s} {r['drug']} -> {r['disease']}{rep}")
            print(f"      why: {r['why']}")
        print()

    if args.print_only:
        print("(--print-only: manifest NOT written)")
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    header = (
        "# Re-curation pilot stress set — generated by scripts/select_pilot_pairs.py.\n"
        "# READ-ONLY selection over kb/paths; every pair is an existing record (has a legacy\n"
        "# path), so this doubles as the agreement-vs-legacy set. Buckets: hard_gate (gate must\n"
        "# still bite), convergent (demoted short_circuit must now PASS), chembl_preprint\n"
        "# (multi-source evidence layer), ordinary (clean baseline). `repeat: 3` marks the\n"
        "# cross-run-consistency subset. Regenerate by re-running the selector.\n\n")
    args.out.write_text(header + yaml.safe_dump({"pairs": rows}, sort_keys=False,
                                                allow_unicode=True), encoding="utf-8")
    print(f"Wrote {args.out.relative_to(REPO)} ({len(rows)} pairs).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
