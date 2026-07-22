#!/usr/bin/env python3
"""
Audit the PRECISION of the deterministic structural-quality checker's HARD flags.

The structural-quality scorer (scripts/quality/structural_quality.py) is slated to become a
GATE. Before that, its HARD flags must be trusted to be *real* logical errors, not artifacts of
the checker's own heuristics. This tool measures and assembles the evidence a human needs to
adjudicate that.

It is strictly READ-ONLY over the corpus. It:
  1. runs structural_quality.analyze() over every legacy record in kb/paths/*.yaml,
  2. tallies per-check HARD-flag COUNTS across the whole corpus,
  3. selects a ~20-record dossier of HARD-flagged records, deliberately BIASED toward
     SUSPECTED FALSE POSITIVES (records where a HARD flag may be firing on a legitimate path),
     with a few clear true positives for calibration/contrast, and
  4. writes docs/structural_precision_audit.md — a per-record worksheet a human can adjudicate.

Selection is DETERMINISTIC (bucket predicate + id sort + take-N), so the dossier is reproducible
and the script is re-runnable as the corpus evolves. The analyst's per-record rationale lives in
REVIEWED_NOTES (an overlay keyed by record id); any selected record lacking a note is emitted with
a placeholder so the gap is visible.

Usage:
    python scripts/audit_structural_precision.py            # write docs/structural_precision_audit.md
    python scripts/audit_structural_precision.py --print    # print to stdout, do not write
    python scripts/audit_structural_precision.py --out PATH  # write elsewhere
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path
from collections import Counter

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
QUALITY_DIR = REPO / "scripts" / "quality"
sys.path.insert(0, str(QUALITY_DIR))

# structural_quality.py is imported, NOT modified. It resolves its own paths from its location.
from structural_quality import load_lexicon, analyze, iter_files, orientation  # noqa: E402

DEFAULT_OUT = REPO / "docs" / "structural_precision_audit.md"

# The full set of HARD checks the scorer can emit (docs order); used so the counts table always
# lists every check, including ones with a zero count in the current corpus.
HARD_CHECKS = [
    "connectivity", "cycle", "duplicate_edge", "type_violation",
    "net_polarity", "short_circuit", "clinical_shortcut", "direct_drug_disease",
]


# ── analysis helpers ────────────────────────────────────────────────────────

def hard_codes(r: dict) -> set:
    return {f["code"] for f in r["flags"] if f["severity"] == "HARD"}


def flags_of(r: dict, code: str) -> list:
    return [f for f in r["flags"] if f["code"] == code]


def review_msg(r: dict) -> str:
    return " ".join(f["msg"] for f in r["flags"] if f["code"] == "review_predicate")


def n_review_preds(r: dict) -> int:
    m = review_msg(r)
    return len(re.findall(r"'[^']+'", m)) if m else 0


def sc_middle_label(r: dict, labels: dict):
    """Label of the middle node of the 2-edge 'bypass' path a short_circuit reported."""
    for f in flags_of(r, "short_circuit"):
        m = re.search(r": (\S+) -> (\S+) -> (\S+)", f["msg"])
        if m:
            return labels.get(m.group(2))
    return None


def ddd_msg(r: dict) -> str:
    return " ".join(f["msg"] for f in flags_of(r, "direct_drug_disease"))


def tv_msgs(r: dict) -> list:
    return [f["msg"] for f in flags_of(r, "type_violation")]


def load_doc(path: Path) -> dict:
    return yaml.safe_load(path.read_text())


def node_labels(doc: dict) -> dict:
    return {n.get("id"): n.get("label") for n in (doc.get("nodes") or []) if isinstance(n, dict)}


def node_names(doc: dict) -> dict:
    return {n.get("id"): n.get("name") for n in (doc.get("nodes") or []) if isinstance(n, dict)}


# ── analyst overlay: verified per-record rationales ─────────────────────────
# class: one of
#   FP   suspected false positive (HARD flag likely firing on a legitimate path)
#   TP   true positive kept for calibration/contrast (a real logical error)
#   MIX  record carries both a suspected-FP HARD flag and a genuine one
#   AMB  ambiguous — the flag surfaces a real tension; needs a human call

REVIEWED_NOTES = {
    "DB00152_MESH_D001361_1": ("FP",
        "Thiamine branches into four parallel metabolic processes (glucose metabolism, "
        "acetylcholine secretion, lactate biosynthesis, ATP synthesis) that each CONVERGE on "
        "avitaminosis. The flagged 2-edge branch (thiamine -> acetylcholine secretion -> disease) "
        "is a legitimate independent convergent route, not a bypass of the longer branch — exactly "
        "the 'branch only on convergence' pattern the convention permits. short_circuit appears to "
        "misread convergence as a shortcut."),
    "DB00152_MESH_D013832_1": ("FP",
        "Same convergent-branch structure as DB00152_MESH_D001361_1 (thiamine, different indication). "
        "Multiple metabolic branches of differing length all terminate at the disease; the short "
        "branch is a real parallel mechanism, so short_circuit is a probable false positive. Included "
        "to show the pattern is systematic, not a one-off."),
    "DB00258_MESH_D006996_1": ("FP",
        "Calcium acetate treats hypocalcemia via two convergent branches: directly raising calcium "
        "(2-edge: acetate -increases abundance of-> Calcium -neg corr-> hypocalcemia) and via the "
        "calcium-sensing receptor / homeostasis (3-edge). The flagged short branch is the PRIMARY, "
        "most direct mechanism (giving calcium raises calcium), not a spurious bypass. Strong "
        "suspected false positive."),
    "B02362_MESH_D003882_1": ("MIX",
        "Two HARD flags of opposite quality. duplicate_edge is a TRUE positive: the triple "
        "'GO:0006954 -positively correlated with-> MESH:D003882' is listed twice verbatim (a real "
        "redundant edge). short_circuit is a suspected false positive: the 2-edge branch "
        "(drug -neg reg-> inflammatory response -> disease) is a legitimate convergent branch. Good "
        "for calibrating that one record can carry both a real and a spurious HARD flag."),
    "DB02659_MESH_D019294_1": ("AMB",
        "short_circuit with a Protein-typed middle. Cholic acid replacement for CTX: the 2-edge "
        "branch collapses the mechanism into a direct 'enzyme -negatively correlated with-> disease' "
        "edge, while the 3-edge branch spells out the cholestanol route. Here the short branch IS a "
        "partial shortcut of the detailed mechanism, so the flag is not obviously wrong — a useful "
        "contrast to the clean convergent-branch false positives."),
    "DB00115_MESH_D018798_1": ("FP",
        "direct_drug_disease fires because the drug's first target is a Disease-TYPED node (Vitamin "
        "B12 Deficiency). But that node is a mechanistic INTERMEDIATE: the path continues 3 more "
        "edges (B12 deficiency -> malabsorption -> iron homeostasis -> iron-deficiency anemia). The "
        "drug does NOT go directly to the indication disease, so the 'direct drug->disease' framing "
        "is a false positive triggered purely by the intermediate's node type. (drug_mesh is also "
        "absent, forcing the checker's fallback drug-id heuristic.)"),
    "DB00395_MESH_D001416_1": ("FP",
        "direct_drug_disease fires because all three of carisoprodol's first targets are "
        "PhenotypicFeature-typed (muscle stiffness/myalgia/spasm). But the path continues "
        "(phenotype -located in-> trunk musculature -location of-> backache): a symptom->anatomy-> "
        "disease chain, not a direct drug->disease shortcut. The flag conflates 'non-molecular / "
        "non-canonical start' (which has its own INFO flag) with a true drug->disease bypass."),
    "DB00126_MESH_D001206_1": ("TP",
        "Single edge 'ascorbic acid -treats-> ascorbic acid deficiency' — a genuine 1-edge stub with "
        "no molecular mechanism (the record's own comment says the MoA is unknown). direct_drug_disease "
        "is a correct true positive. Adjudication nuance for the human: replacement-therapy 'treats "
        "deficiency' stubs may be an ACCEPTED minimal curation rather than an error — the flag is "
        "structurally right, but the keep/reject policy is a maintainer call."),
    "DB01527_MESH_D000856_1": ("TP",
        "Two direct drug->disease edges and nothing else: 'treats' AND 'contraindicated for' the same "
        "disease (a contradictory stub). The 'treats' clinical_shortcut is a clean true positive "
        "(clinical-outcome edge as a bypass, like P06 edge 4). Nuance: flagging 'contraindicated for' "
        "as a *clinical_shortcut* is a debatable label — it is a non-mechanistic clinical edge but not "
        "a therapeutic bypass; worth a human note on whether the code name fits."),
    "DB00993_MESH_D001172_1": ("TP",
        "The corpus's only cycle. Cause is a SELF-LOOP: 'GO:0006955 (immune response) -positively "
        "regulates-> GO:0006955' — a node pointing to itself. A correct acyclic mechanism cannot have "
        "this; clean true positive and a good calibration anchor for the cycle check."),
    "DB09105_MESH_D007014_1": ("FP",
        "net_polarity=incoherent, but the net-positive product depends entirely on TWO review-"
        "confidence signs ('has phenotype' +1, 'manifestation of' +1). Asfotase alfa genuinely treats "
        "hypophosphatasia (it degrades pyrophosphate, relieving inhibition of mineralization). The "
        "phenotype here is 'reduced bone mineral density', for which more crystal growth should be "
        "NEGATIVE, so 'has phenotype' = +1 is the wrong sign in context. The flag is an artifact of an "
        "unconfirmed lexicon sign, not a real incoherence."),
    "DB00905_MESH_D005902_2": ("FP",
        "net_polarity=incoherent driven by the review-confidence sign 'increases transport of' (+1). "
        "Bimatoprost lowers intraocular pressure by increasing aqueous-humor OUTFLOW/drainage — so "
        "'increases transport of aqueous humor' should DECREASE its level (-1 in context), not +1. The "
        "lexicon's blanket +1 flips the net sign. Bimatoprost demonstrably treats glaucoma, so this is "
        "a suspected false positive rooted in a context-dependent, unconfirmed sign."),
    "DB00008_MESH_D019698_1": ("TP",
        "net_polarity=incoherent on HIGH-confidence signs only (no review reliance). The path never "
        "encodes the drug's suppression of the virus: it runs peginterferon -pos reg-> receptor -> "
        "antiviral response, then '-in taxon-> Hepacivirus C -causes-> hepatitis C' (all +/neutral). "
        "The missing NEGATIVE step (antiviral response should DECREASE the virus) is a real modeling "
        "gap, so the incoherent flag looks like a true positive. Good contrast to the review-sign FPs."),
    "DB00201_MESH_D001416_1": ("AMB",
        "net_polarity=inconsistent (branches disagree). Caffeine's two branches to cAMP genuinely "
        "contradict: blocking adenosine receptors lowers cAMP while inhibiting phosphodiesterase raises "
        "it, so one branch nets to decreased pain and the other to increased pain. The disagreement is "
        "real in the modeled graph — a legitimate detection of internal inconsistency / over-modeling — "
        "though the human should decide whether it reflects a curation error or physiological complexity."),
    "DB00242_MESH_D020529_1": ("FP",
        "type_violation: terminal edge 'lymphocyte proliferation (BiologicalProcess) -occurs in-> "
        "relapsing-remitting MS (Disease)'. The mechanism (cladribine -> kills lymphocytes -> less "
        "proliferation -> treats MS) is sound; only the terminal predicate's object-type is off. This "
        "'occurs in -> Disease' pattern recurs 117x corpus-wide — a systematic terminal-connector "
        "convention, so flagging it HARD (a 'logical error a correct mechanism cannot have') is likely "
        "over-severe. Prime suspected-false-positive class."),
    "DB00188_MESH_D009101_1": ("FP",
        "type_violation: 'bortezomib -decreases activity of-> NF-kappaB complex' where the node is "
        "TYPED CellularComponent (not in the ACTIVITY_BEARING group, which does include "
        "MacromolecularComplex). NF-kappaB is a macromolecular complex mislabeled as a cellular "
        "component; decreasing its activity is biologically fine. The flag surfaces a NODE-TYPING "
        "inconsistency, not a broken mechanism — suspected false positive."),
    "DB00916_MESH_D001922_1": ("FP",
        "type_violation: 'metronidazole -decreases activity of-> DNA' where DNA is typed "
        "ChemicalSubstance (outside ACTIVITY_BEARING). Metronidazole damages microbial DNA — the "
        "biology is correct; the constraint fires only because DNA, a functional macromolecule, is "
        "typed as a chemical. A granularity/typing nuance, not a logical error — suspected false "
        "positive."),
    "DB00041_MESH_D015470_1": ("TP",
        "type_violation: two edges use 'treats' with a BiologicalProcess SUBJECT ('cytotoxic T cell "
        "differentiation -treats-> AML', 'NK cell activation -treats-> AML'). 'treats' is a clinical "
        "drug->disease predicate; a biological process cannot 'treat' a disease. This is a genuine "
        "predicate misuse mid-path — a real true positive, and a calibration contrast to the "
        "over-strict typing false positives above."),
    "DB00005_MESH_D015535_1": ("TP",
        "duplicate_edge with no other HARD flag: the triple 'GO:0006954 (inflammatory response) "
        "-causes-> MESH:D015535' is listed twice verbatim. An identical repeated edge is pure "
        "redundancy a correct multigraph should not carry — clean true positive, the calibration "
        "anchor for the duplicate_edge check."),
}

CLASS_LABEL = {
    "FP": "SUSPECTED FALSE POSITIVE",
    "TP": "true positive (calibration / contrast)",
    "MIX": "MIXED (one suspected-FP flag + one true-positive flag)",
    "AMB": "AMBIGUOUS — flag surfaces a real tension; human call",
}


# ── selection: deterministic buckets, biased toward suspected false positives ──

def build_index(results: list) -> dict:
    by_id = {}
    for r in results:
        r["_labels"] = node_labels(load_doc(REPO / r["file"]))
        by_id[r["id"]] = r
    return by_id


def select_dossier(results: list) -> list:
    """Return an ordered list of (bucket_label, record) pairs, deduped by id."""
    S = lambda pred: sorted((r for r in results if pred(r)), key=lambda x: x["id"])
    lab = lambda r: r["_labels"]

    buckets = [
        ("short_circuit: convergent branch (suspected FP)",
         S(lambda r: "short_circuit" in hard_codes(r) and "duplicate_edge" not in hard_codes(r)
           and r["polarity"] == "coherent"
           and sc_middle_label(r, lab(r)) in ("ChemicalSubstance", "BiologicalProcess", "Pathway"))[:3]),
        ("short_circuit + duplicate_edge (mixed)",
         S(lambda r: {"short_circuit", "duplicate_edge"} <= hard_codes(r))[:1]),
        ("short_circuit: Protein middle (contrast)",
         S(lambda r: "short_circuit" in hard_codes(r) and sc_middle_label(r, lab(r)) == "Protein")[:1]),
        ("direct_drug_disease: Disease-typed intermediate, multi-edge (suspected FP)",
         S(lambda r: "direct_drug_disease" in hard_codes(r) and r["n_edges"] >= 3 and "Disease" in ddd_msg(r))[:1]),
        ("direct_drug_disease: Phenotype-typed intermediate, multi-edge (suspected FP)",
         S(lambda r: "direct_drug_disease" in hard_codes(r) and r["n_edges"] >= 3
           and "Disease" not in ddd_msg(r) and "PhenotypicFeature" in ddd_msg(r))[:1]),
        ("direct_drug_disease: 1-edge stub (true positive)",
         S(lambda r: "direct_drug_disease" in hard_codes(r) and r["n_edges"] == 1)[:1]),
        ("clinical_shortcut (true positive)",
         S(lambda r: "clinical_shortcut" in hard_codes(r))[:1]),
        ("cycle (true positive)",
         S(lambda r: "cycle" in hard_codes(r))),
        ("net_polarity: incoherent via >=2 review-confidence signs (suspected FP)",
         S(lambda r: "net_polarity" in hard_codes(r) and n_review_preds(r) >= 2)[:1]),
        ("net_polarity: incoherent via 'increases transport of' review sign (suspected FP)",
         S(lambda r: "net_polarity" in hard_codes(r) and "increases transport of" in review_msg(r))[:1]),
        ("net_polarity: incoherent on high-confidence signs (true positive)",
         S(lambda r: "net_polarity" in hard_codes(r) and r["polarity"] == "incoherent" and n_review_preds(r) == 0)[:1]),
        ("net_polarity: inconsistent branches (ambiguous)",
         S(lambda r: "net_polarity" in hard_codes(r) and r["polarity"] == "inconsistent"
           and "short_circuit" not in hard_codes(r))[:1]),
        ("type_violation: 'occurs in' -> Disease (suspected FP)",
         S(lambda r: any("'occurs in' object is Disease" in m for m in tv_msgs(r)))[:1]),
        ("type_violation: 'decreases activity of' -> CellularComponent (suspected FP)",
         S(lambda r: any("'decreases activity of' object is CellularComponent" in m for m in tv_msgs(r)))[:1]),
        ("type_violation: 'decreases activity of' -> ChemicalSubstance (suspected FP)",
         S(lambda r: any("'decreases activity of' object is ChemicalSubstance" in m for m in tv_msgs(r)))[:1]),
        ("type_violation: 'treats' subject is a process (true positive)",
         S(lambda r: any("'treats' subject is BiologicalProcess" in m for m in tv_msgs(r)))[:1]),
        ("duplicate_edge: sole HARD flag (true positive)",
         S(lambda r: hard_codes(r) == {"duplicate_edge"})[:1]),
    ]

    seen, ordered = set(), []
    for label, recs in buckets:
        for r in recs:
            if r["id"] in seen:
                continue
            seen.add(r["id"])
            ordered.append((label, r))
    return ordered


# ── rendering ────────────────────────────────────────────────────────────────

def signed_edges_block(doc: dict, lex: dict) -> str:
    preds = lex["predicates"]
    labels = node_labels(doc)
    names = node_names(doc)
    lines = []
    for e in (doc.get("links") or []):
        s, t, k = e.get("source"), e.get("target"), e.get("key")
        ent = preds.get(k)
        if ent is None:
            tag = "sign=?, not-in-lexicon"
        else:
            tag = f"sign={ent.get('sign', 0):+d}, {orientation(ent)}, {ent.get('role')}"
        sn = f"{s} [{labels.get(s)}: {names.get(s)}]"
        tn = f"{t} [{labels.get(t)}: {names.get(t)}]"
        lines.append(f"  {sn}\n      --{k}  ({tag})-->\n  {tn}")
    return "\n".join(lines)


def render_record(idx: int, bucket_label: str, r: dict, lex: dict) -> str:
    doc = load_doc(REPO / r["file"])
    g = doc.get("graph", {}) or {}
    cls, note = REVIEWED_NOTES.get(r["id"], (None, None))
    verdict_hdr = CLASS_LABEL.get(cls, "(no analyst note yet — REVIEW)")

    hard = [f for f in r["flags"] if f["severity"] == "HARD"]
    hard_lines = "\n".join(f"  - `{f['code']}` — {f['msg']}" for f in hard)

    out = []
    out.append(f"### {idx}. `{r['id']}` — {verdict_hdr}\n")
    out.append(f"- **Selection bucket:** {bucket_label}")
    out.append(f"- **Indication:** {g.get('drug')} -> {g.get('disease')}  "
               f"({r['n_nodes']} nodes / {r['n_edges']} edges / {r['n_paths']} simple path(s); "
               f"polarity = {r['polarity']})")
    if g.get("drug_mesh") is None:
        out.append("- **Note:** `drug_mesh` absent from `graph` — the checker's fallback "
                   "(first in-degree-0 node) picks the drug, which can affect drug-anchored checks.")
    out.append(f"- **HARD flag(s) fired:**\n{hard_lines}")
    if doc.get("comment"):
        c = " ".join(str(doc["comment"]).split())
        out.append(f"- **Record comment:** {c}")
    out.append("- **Path (signed backbone; implicated fragment is called out in the flag message above):**")
    out.append("```")
    out.append(signed_edges_block(doc, lex))
    out.append("```")
    if note:
        out.append(f"- **Why selected (analyst):** {note}")
    else:
        out.append("- **Why selected (analyst):** _(pending — record surfaced by a bucket with no note)_")
    out.append("")
    out.append("- **Verdict (human):** ☐ true error   ☐ false positive   ☐ needs rule change")
    out.append("- **Reviewer notes:** ")
    out.append("\n---\n")
    return "\n".join(out)


def render_markdown(results: list, dossier: list, lex: dict) -> str:
    n = len(results)
    n_hard = sum(1 for r in results if any(f["severity"] == "HARD" for f in r["flags"]))

    # corpus-wide HARD counts: edge occurrences (total flags) AND records affected
    flag_occurrences = Counter()
    records_with = Counter()
    for r in results:
        codes_here = set()
        for f in r["flags"]:
            if f["severity"] == "HARD":
                flag_occurrences[f["code"]] += 1
                codes_here.add(f["code"])
        for c in codes_here:
            records_with[c] += 1

    # polarity breakdown for net_polarity context
    pol = Counter(r["polarity"] for r in results)

    out = []
    out.append("# Structural-quality HARD-flag precision audit\n")
    out.append("> Generated by `scripts/audit_structural_precision.py` (deterministic, read-only over "
               "`kb/paths/*.yaml`). Regenerate by re-running that script. **This is a review worksheet: "
               "the goal is for a human to confirm each HARD flag is a real error, not a false positive, "
               "before the structural scorer is used as a gate.**\n")

    out.append("## What was measured\n")
    out.append(f"- Records analyzed: **{n}** legacy path records.")
    out.append(f"- Records with >=1 HARD flag: **{n_hard}** ({n_hard/n:.1%}).")
    out.append("- The structural scorer was run unmodified via `structural_quality.analyze()`; only "
               "HARD-severity flags are audited here (SOFT/INFO are out of scope).\n")

    out.append("## Corpus-wide HARD-flag counts (per check)\n")
    out.append("`edge/flag occurrences` counts every firing of the check; `records affected` counts "
               "distinct records with >=1 such flag (a record can fire several checks).\n")
    out.append("| HARD check | edge/flag occurrences | records affected |")
    out.append("|---|---:|---:|")
    for code in HARD_CHECKS:
        out.append(f"| `{code}` | {flag_occurrences.get(code, 0)} | {records_with.get(code, 0)} |")
    out.append(f"| **any HARD** | {sum(flag_occurrences.values())} | {n_hard} |")
    out.append("")
    out.append("Polarity distribution (context for `net_polarity`): "
               + ", ".join(f"`{k}`={v}" for k, v in pol.most_common()) + ".")
    out.append("`net_polarity` HARD fires on `incoherent` (every branch nets positive) and "
               "`inconsistent` (branches disagree); `indeterminate` is SOFT, not audited here.\n")

    out.append("## How the dossier was selected\n")
    out.append("Selection is deterministic (a bucket predicate + record-id sort + fixed take-N per "
               "bucket) and deliberately **biased toward suspected false positives** — records where a "
               "HARD flag may be firing on a legitimate path — with a handful of clear true positives "
               "kept for calibration/contrast. The bias heuristics, one per failure family:\n")
    out.append("- **`short_circuit`** — bias toward records whose short ('bypass') path passes through "
               "a molecular/process intermediate and whose polarity is coherent: the signature of a "
               "legitimate *convergent* branch (which the path convention allows), which the check may "
               "misread as a shortcut. One Protein-middle case and one clean true positive are kept for "
               "contrast.")
    out.append("- **`direct_drug_disease`** — bias toward records where the flag fires but the path is "
               "multi-edge (the Disease/Phenotype-typed first target is a mechanistic *intermediate*, "
               "not the terminal disease). A genuine 1-edge stub is kept as the true positive.")
    out.append("- **`net_polarity`** — bias toward records whose net sign depends on a "
               "`review`-confidence (unconfirmed) sign in the polarity lexicon. A high-confidence "
               "`incoherent` case and an `inconsistent` case are kept for contrast.")
    out.append("- **`type_violation`** — bias toward the highest-volume, systematic domain/range "
               "patterns (e.g. `occurs in -> Disease`; `decreases activity of` a "
               "ChemicalSubstance/CellularComponent) that look like over-strict constraints or node "
               "mistyping. A `treats`-with-a-process-subject case is kept as a genuine predicate misuse.")
    out.append("- **`duplicate_edge` / `cycle` / `clinical_shortcut`** — expected to be high-precision; "
               "representative records are included primarily as true-positive calibration anchors.")
    out.append("- **`connectivity`** — 0 occurrences in the corpus; nothing to adjudicate.\n")
    out.append(f"Dossier size: **{len(dossier)}** records. Each is labeled with the analyst's suspected "
               "class, but the **Verdict** line is left blank for the human reviewer.\n")

    out.append("## Legend\n")
    out.append("- **SUSPECTED FALSE POSITIVE** — analyst believes the HARD flag is firing on a legitimate path.")
    out.append("- **true positive** — analyst believes the flag is a real logical error (kept for calibration).")
    out.append("- **MIXED** — the record carries both a suspected-FP and a genuine HARD flag.")
    out.append("- **AMBIGUOUS** — the flag surfaces a real tension; needs a human call.\n")
    out.append("---\n")

    out.append("## Dossier\n")
    for i, (bucket_label, r) in enumerate(dossier, 1):
        out.append(render_record(i, bucket_label, r, lex))

    # tally the analyst-suspected split for a quick orientation line
    split = Counter(REVIEWED_NOTES.get(r["id"], (None,))[0] for _, r in dossier)
    out.append("## Analyst-suspected split (pre-adjudication)\n")
    out.append(", ".join(f"{CLASS_LABEL.get(k, k)}: {v}" for k, v in split.items()
                         if k is not None) + ".")
    out.append("\n_These are the analyst's priors, not verdicts. The human review fills the Verdict "
               "lines above; disagreements are the signal that a rule needs tightening or relaxing._")
    return "\n".join(out)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", type=Path, default=DEFAULT_OUT, help="output markdown path")
    ap.add_argument("--print", dest="to_stdout", action="store_true", help="print to stdout, do not write a file")
    args = ap.parse_args()

    lex = load_lexicon()
    files = iter_files([])
    results = [analyze(f, lex) for f in files]
    build_index(results)
    dossier = select_dossier(results)

    md = render_markdown(results, dossier, lex)
    if args.to_stdout:
        print(md)
        return 0

    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(md)

    n_hard = sum(1 for r in results if any(f["severity"] == "HARD" for f in r["flags"]))
    print(f"Analyzed {len(results)} records; {n_hard} with >=1 HARD flag.")
    print(f"Selected {len(dossier)} records for the review dossier.")
    missing = [r["id"] for _, r in dossier if r["id"] not in REVIEWED_NOTES]
    if missing:
        print(f"WARNING: {len(missing)} selected record(s) lack an analyst note: {missing}")
    print(f"Wrote {args.out.relative_to(REPO)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
