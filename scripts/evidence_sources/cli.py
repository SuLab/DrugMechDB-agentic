"""
Unified evidence-fetch CLI — one interface over every sanctioned source.

Mirrors `pubmed_fetch.py`'s verbs but dispatches by reference prefix, so a
curator uses ONE command whether the evidence is a PubMed abstract, a ChEMBL
mechanism, a ClinicalTrials.gov summary, a preprint, or DrugBank MoA text:

    python scripts/evidence_fetch.py sources
    python scripts/evidence_fetch.py search chembl "aspirin"
    python scripts/evidence_fetch.py fetch ChEMBL:CHEMBL25
    python scripts/evidence_fetch.py fetch clinicaltrials:NCT00000102
    python scripts/evidence_fetch.py fetch PMID:35569550 ChEMBL:CHEMBL25   # mixed batch
    python scripts/evidence_fetch.py probe bioRxiv:10.1101/2020.05.01.072066
    python scripts/evidence_fetch.py fetch bioRxiv:10.1101/2020.05.01.072066 --fulltext
    python scripts/evidence_fetch.py info ChEMBL:CHEMBL25
    python scripts/evidence_fetch.py strip-fulltext --all                  # ephemeral cleanup (all sources)

`PMID:` references route to the unchanged `pubmed_fetch.py` engine; every other
prefix routes to its source module. Cache files land in `references_cache/`
(or `$DMDB_CACHE_DIR`), named so QC Layer 4 verbatim-verifies them source-agnostically.
"""

from __future__ import annotations

import argparse
import json
import sys

from . import REGISTRY, get_source, sources, strip_all_fulltext, common
from . import _pmid_refetch_abstract


def _dispatch_fetch(ref: str, *, fulltext: bool, force: bool, offline: bool) -> dict:
    src = get_source(ref)
    if src is None:
        return {"reference": ref, "error": f"no source registered for reference: {ref}"}
    if fulltext:
        return src.fetch_fulltext(ref, force=force, offline=offline)
    return src.fetch(ref, force=force, offline=offline)


def _print_fetch(r: dict) -> None:
    ref = r.get("reference", "?")
    tag = "ERROR" if r.get("error") else ("CACHED" if r.get("cached") else "FETCHED")
    bits = [f"{tag} {ref}"]
    if r.get("error"):
        bits.append(r["error"])
    if r.get("content_type") == "full_text":
        bits.append(f"[full_text:{r.get('fulltext_source', '?')}]")
    if r.get("license_note"):
        bits.append(f"[{r['license_note']}]")
    if r.get("note"):
        bits.append(f"({r['note']})")
    if r.get("path"):
        bits.append(r["path"])
    print("  ".join(bits))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="evidence_fetch", description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_sources = sub.add_parser("sources", help="List registered evidence sources")
    p_sources.add_argument("--json", action="store_true")

    p_search = sub.add_parser("search", help="Search one source -> candidate reference CURIEs")
    p_search.add_argument("source", help="Source prefix, e.g. chembl / clinicaltrials / PMID")
    p_search.add_argument("query", help="Free-text query")
    p_search.add_argument("--max", type=int, default=20, dest="retmax")

    p_fetch = sub.add_parser("fetch", help="Fetch + cache reference(s) from any source")
    p_fetch.add_argument("refs", nargs="+", help="Reference CURIEs (PMID:.. ChEMBL:.. etc.)")
    p_fetch.add_argument("--fulltext", action="store_true",
                         help="Escalate to ephemeral full text where the source supports it")
    p_fetch.add_argument("--max-fulltext", type=int, default=5, dest="max_fulltext",
                         help="Cap full-text escalations this run (rest fetch abstract tier)")
    p_fetch.add_argument("--force", action="store_true", help="Bypass cache freshness")
    p_fetch.add_argument("--offline", action="store_true", help="Cache-only; never hit the network")
    p_fetch.add_argument("--json", action="store_true")

    p_probe = sub.add_parser("probe", help="Is ephemeral full text available? (no body download)")
    p_probe.add_argument("ref")
    p_probe.add_argument("--json", action="store_true")

    p_info = sub.add_parser("info", help="Show cache state for a reference (no network)")
    p_info.add_argument("ref")
    p_info.add_argument("--json", action="store_true")

    p_strip = sub.add_parser("strip-fulltext",
                             help="Revert full_text cache(s) to abstract-only (all sources)")
    p_strip.add_argument("refs", nargs="*", help="References to strip; or pass --all")
    p_strip.add_argument("--all", action="store_true", dest="all_ft")
    p_strip.add_argument("--offline", action="store_true",
                         help="Don't re-fetch to recover marker-less legacy abstracts")
    p_strip.add_argument("--json", action="store_true")

    args = parser.parse_args(argv)

    if args.cmd == "sources":
        rows = [{"prefix": s.PREFIX, "fulltext": s.SUPPORTS_FULLTEXT,
                 "description": s.DESCRIPTION} for s in sources()]
        if args.json:
            print(json.dumps(rows, indent=2))
        else:
            for r in rows:
                ft = "full-text" if r["fulltext"] else "abstract-only"
                print(f"  {r['prefix']:<15} [{ft:<13}] {r['description']}")
        return 0

    if args.cmd == "search":
        src = REGISTRY.by_prefix(args.source)
        if src is None:
            print(f"unknown source: {args.source}", file=sys.stderr)
            return 2
        try:
            refs = src.search(args.query, retmax=args.retmax)
        except NotImplementedError as e:
            print(str(e), file=sys.stderr)
            return 2
        for r in refs:
            print(r)
        return 0 if refs else 1

    if args.cmd == "fetch":
        results = []
        ft_used = 0
        for ref in args.refs:
            use_ft = args.fulltext and ft_used < args.max_fulltext
            results.append(_dispatch_fetch(ref, fulltext=use_ft, force=args.force,
                                           offline=args.offline))
            if use_ft:
                ft_used += 1
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                _print_fetch(r)
        return 0 if all(not r.get("error") for r in results) else 1

    if args.cmd == "probe":
        src = get_source(args.ref)
        out = ({"reference": args.ref, "error": "no source registered"}
               if src is None else src.probe(args.ref))
        print(json.dumps(out, indent=2) if args.json else out)
        return 0 if out.get("fulltext_available") else 1

    if args.cmd == "info":
        path = common.cache_path(args.ref)
        if not path.exists():
            out = {"reference": common.normalize_reference_id(args.ref), "cached": False}
        else:
            out = {"reference": common.normalize_reference_id(args.ref), "cached": True,
                   "path": str(path), "fresh": common.cache_is_fresh(path),
                   "content_type": common.cache_content_type(path),
                   "size_bytes": path.stat().st_size}
        print(json.dumps(out, indent=2) if args.json else out)
        return 0

    if args.cmd == "strip-fulltext":
        if args.all_ft:
            results = strip_all_fulltext(offline=args.offline)
        elif args.refs:
            results = []
            for r in args.refs:
                path = common.cache_path(r)
                refetch = _pmid_refetch_abstract if path.name.startswith("PMID_") else None
                results.append(common.strip_fulltext_file(path, offline=args.offline,
                                                          refetch_abstract=refetch))
        else:
            parser.error("strip-fulltext needs references or --all")
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                if r.get("stripped"):
                    print(f"STRIPPED {r.get('reference_id', r.get('file'))}  "
                          f"(abstract kept: {r['had_abstract']})")
                else:
                    print(f"SKIPPED  {r.get('reference_id', r.get('file'))}  ({r.get('skipped')})")
        return 0

    parser.error("unknown cmd")
    return 2
