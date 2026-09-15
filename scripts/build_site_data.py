"""
Build the static-site JSON (index + per-record) that web-revamp-mockup/ consumes
in "live" mode, from the **agentically curated** path records.

WHY THIS EXISTS
The site's data layer (web-revamp-mockup/dmdb-data.js) has one documented swap
point: flip SOURCE to "live" and the pages fetch the JSON files named in its
ENDPOINTS map. This script emits exactly those shapes.

WHAT IT READS
Not kb/paths/ — those 4,846 records are the legacy corpus and carry no per-edge
evidence. The AI-curated records produced by the harness live in the run output
directories listed in RUNS below. The same (drug, disease) pair is often curated
by several runs (model comparison, pilot repeats), so a record's site id is
namespaced by run: "<run>__<file stem>". graph._id is kept as `record_id`.

WHAT IT ADDS (join, not invention)
  * `paper`       — title/authors/journal/year/doi for each cited PMID, read from
                    reference's PMID_*.md frontmatter in any references_cache/.
  * `source_type` — derived from the reference CURIE prefix (PMID -> pubmed, ...).
  * `source_tier` — from the cache entry's content_type (abstract vs full text).
  * `graph.summary` — the node chain along the record's longest path, joined with
                    arrows. Generated for display; flagged as such in `site`.
  * `area`        — a COARSE display-only bucket keyword-matched from the disease
                    name. Not an ontology assertion; it exists to drive the
                    browse facet and nothing else.

Usage:
    python scripts/build_site_data.py                # write web-revamp-mockup/data/
    python scripts/build_site_data.py --out DIR      # write elsewhere
"""

from __future__ import annotations

import argparse
import json
import re
from pathlib import Path

import yaml

HERE = Path(__file__).resolve().parent
REPO = HERE.parent
# Every reference cache in the repo: the shared one plus the per-run caches the
# model-eval runs wrote alongside their outputs.
CACHE_DIRS = [
    REPO / "references_cache",
    REPO / "experiments" / "opus_vs_sonnet" / "opus" / "references_cache",
    REPO / "experiments" / "opus_vs_sonnet" / "sonnet" / "references_cache",
]
DEFAULT_OUT = REPO / "web-revamp-mockup" / "data"

# The agentic curation runs, in display order: (run key, label, glob).
RUNS = [
    ("pilot", "Pilot run", "experiments/pilot/outputs/*.yaml"),
    ("opus", "Opus (model eval)", "experiments/opus_vs_sonnet/opus/outputs/*.yaml"),
    ("sonnet", "Sonnet (model eval)", "experiments/opus_vs_sonnet/sonnet/outputs/*.yaml"),
    ("phase3", "Phase-3 eval", "tests/phase3_eval_outputs/*.yaml"),
]

# Coarse display buckets for the browse facet. First match wins, so the more
# specific patterns are listed first.
AREA_RULES = [
    ("Neoplasms", r"leukemia|leukaemia|lymphoma|neoplasm|carcinoma|tumor|tumour|myeloma|myelogenous|cancer"),
    ("Immune", r"psoriasis|arthritis|arthropath|lupus|crohn|sclerosis|dermatomyositis|asthma|cryopyrin|periodic syndrome|colitis"),
    ("Infectious disease", r"tuberculosis|influenza|herpes|hepatitis|conjunctivitis|staphylococc|infection|malaria|hiv"),
    ("Cardiovascular", r"heart failure|hypertension|myocardial|stroke|thromb|embolism|angina|arrhythmia"),
    ("Blood", r"hemophilia|haemophilia|factor viii|thrombocytopen|anemia|anaemia"),
    ("Metabolic", r"cholesterol|diabetes|gout|avitaminosis|deficiency|hypocalcemia|obesity|anorexia|lipid"),
    ("Endocrine", r"thyroid|dwarfism|acromegal|adrenal"),
    ("Nervous system", r"alzheimer|parkinson|epilep|migraine|neuropath|pain"),
    ("Mental health", r"depress|anxiety|bipolar|schizophren|psychos"),
    ("Respiratory", r"pulmonary fibrosis|copd|bronch"),
    ("Musculoskeletal", r"osteoarthritis|osteoporosis|myopath"),
    ("Kidney", r"nephritis|nephropath|renal"),
]

TIER = {"abstract": "ABSTRACT", "full_text": "FULL_TEXT", "fulltext": "FULL_TEXT"}


def area_for(disease: str) -> str:
    d = (disease or "").lower()
    for area, pattern in AREA_RULES:
        if re.search(pattern, d):
            return area
    return "Other"


def source_type_for(reference: str) -> str:
    ref = (reference or "").upper()
    if ref.startswith("PMID"):
        return "pubmed"
    if ref.startswith("PMC"):
        return "pmc"
    if ref.startswith("DB") or ref.startswith("DRUGBANK"):
        return "drugbank"
    if ref.startswith("DOI") or ref.startswith("10."):
        return "doi"
    return "other"


def load_cache() -> dict[str, dict]:
    """Map reference id -> paper credential block, from references_cache frontmatter."""
    papers: dict[str, dict] = {}
    for md in sorted(m for d in CACHE_DIRS if d.is_dir() for m in d.glob("*.md")):
        text = md.read_text(encoding="utf-8", errors="replace")
        if not text.startswith("---"):
            continue
        end = text.find("\n---", 3)
        if end == -1:
            continue
        try:
            fm = yaml.safe_load(text[3:end]) or {}
        except yaml.YAMLError:
            continue
        ref = fm.get("reference_id")
        if not ref:
            continue
        papers[str(ref)] = {
            "title": fm.get("title"),
            "authors": fm.get("authors") or [],
            "journal": fm.get("journal"),
            "year": str(fm.get("year")) if fm.get("year") is not None else None,
            "doi": fm.get("doi"),
            "pmcid": fm.get("pmcid"),
            "license": fm.get("license"),
            "_tier": TIER.get(str(fm.get("content_type") or "").lower()),
        }
    return papers


def longest_chain(nodes: list[dict], links: list[dict]) -> list[str]:
    """Node ids along a longest source->target chain (the record's 'spine')."""
    incoming: dict[str, list[str]] = {n["id"]: [] for n in nodes}
    for l in links:
        if l.get("target") in incoming:
            incoming[l["target"]].append(l.get("source"))

    best: dict[str, list[str]] = {}
    visiting: set[str] = set()

    def chain(nid: str) -> list[str]:
        if nid in best:
            return best[nid]
        if nid in visiting:                     # cycle guard
            return [nid]
        visiting.add(nid)
        parents = [p for p in incoming.get(nid, []) if p in incoming]
        longest: list[str] = []
        for p in parents:
            c = chain(p)
            if len(c) > len(longest):
                longest = c
        visiting.discard(nid)
        best[nid] = longest + [nid]
        return best[nid]

    return max((chain(n["id"]) for n in nodes), key=len, default=[])


def build_record(path: Path, run: str, run_label: str, papers: dict[str, dict]) -> dict:
    raw = yaml.safe_load(path.read_text(encoding="utf-8")) or {}
    graph = dict(raw.get("graph") or {})
    nodes = raw.get("nodes") or []
    links = [dict(l) for l in (raw.get("links") or [])]
    by_id = {n["id"]: n for n in nodes}

    # enrich each EvidenceItem with its joined paper credential + derived fields
    for link in links:
        items = link.get("evidence")
        if not isinstance(items, list):
            continue
        enriched = []
        for item in items:
            it = dict(item)
            ref = it.get("reference")
            it["source_type"] = source_type_for(ref)
            paper = papers.get(str(ref))
            if paper:
                p = {k: v for k, v in paper.items() if k != "_tier"}
                it["paper"] = p
                it.setdefault("source_tier", paper.get("_tier") or "ABSTRACT")
            else:
                it["paper"] = None
            enriched.append(it)
        link["evidence"] = enriched

    chain = longest_chain(nodes, links)
    graph["summary"] = " → ".join(by_id[n]["name"] for n in chain if n in by_id)

    # references ship as bare URL strings in the record files; the site wants
    # {url, type, label} rows.
    refs = []
    for r in raw.get("references") or []:
        if isinstance(r, dict):
            refs.append(r)
            continue
        url = str(r)
        host = re.sub(r"^https?://(www\.)?", "", url).split("/")[0]
        kind = "drugbank" if "drugbank" in host else "wiki" if "wikipedia" in host else "other"
        refs.append({"url": url, "type": kind, "label": f"{host} — record source"})

    site_id = f"{run}__{path.stem}"
    return {
        "directed": raw.get("directed", True),
        "multigraph": raw.get("multigraph", True),
        "graph": graph,
        "nodes": nodes,
        "links": links,
        "references": refs,
        "site": {
            "id": site_id,
            "record_id": graph.get("_id"),
            "run": run,
            "run_label": run_label,
            "source_file": str(path.relative_to(REPO)),
            "summary_generated": True,
        },
    }


def index_row(rec: dict) -> dict:
    nodes, links = rec["nodes"], rec["links"]
    types, seen = [], set()
    for nid in longest_chain(nodes, links):
        label = next((n["label"] for n in nodes if n["id"] == nid), None)
        if label and label not in seen:
            seen.add(label)
            types.append(label)
    for n in nodes:                             # types off the spine still matter to the facet
        if n.get("label") and n["label"] not in seen:
            seen.add(n["label"])
            types.append(n["label"])

    target = next((n["name"] for n in nodes if n.get("label") == "Protein"), None)
    if not target:
        target = next((n["name"] for n in nodes[1:]), "")

    sourced = sum(1 for l in links if l.get("evidence"))
    flagged = sum(
        1 for l in links
        if any((it.get("supports") or "SUPPORT") != "SUPPORT" for it in (l.get("evidence") or []))
    )
    return {
        "id": rec["site"]["id"],
        "record_id": rec["site"]["record_id"],
        "run": rec["site"]["run_label"],
        "drug": rec["graph"].get("drug") or "",
        "disease": rec["graph"].get("disease") or "",
        "area": area_for(rec["graph"].get("disease")),
        "target": target or "",
        "types": types,
        "steps": max(len(longest_chain(nodes, links)) - 1, 0),
        "edges": len(links),
        "sourced": sourced,
        "flagged": flagged,
    }


def main() -> int:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--out", default=str(DEFAULT_OUT), help="output data directory")
    args = ap.parse_args()

    out = Path(args.out)
    records_dir = out / "records"
    records_dir.mkdir(parents=True, exist_ok=True)

    papers = load_cache()
    rows, written = [], 0
    for run, run_label, pattern in RUNS:
        for path in sorted(REPO.glob(pattern)):
            rec = build_record(path, run, run_label, papers)
            (records_dir / f"{rec['site']['id']}.json").write_text(
                json.dumps(rec, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
            rows.append(index_row(rec))
            written += 1

    rows.sort(key=lambda r: (r["drug"].lower(), r["disease"].lower(), r["id"]))
    (out / "index.json").write_text(
        json.dumps(rows, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    runs = {r["run"] for r in rows}
    print(f"Wrote {written} records + index.json to {out} "
          f"({len(runs)} runs, {len({r['record_id'] for r in rows})} distinct path ids).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
