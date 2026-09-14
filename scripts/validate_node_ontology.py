"""
Layer 2 — Node ontology check.

For every PathNode in every path file, verify that the CURIE prefix of `id`
matches the canonical ontology for the declared Biolink `label`. Legacy
prefixes (taxonomy, reactome, Pfam, TIGR) are accepted but flagged as
warnings rather than failures.

WHAT THIS LAYER DOES NOT DO
    It checks the *shape* of an identifier, never its existence. GO:0000000,
    MESH:D999999 and a real UniProt accession carrying a completely wrong name
    all pass this layer and the whole QC gate. Use --existence (below) for that.

    --deep hands off to `linkml-term-validator`, but note that it currently
    passes everything: that tool validates dynamic enums and binding
    constraints, and the schema declares neither on node `id`/`name`
    (`range: uriorcurie` and `range: string`), so it walks the record, finds
    nothing to check and reports success. Wiring real bindings into the schema
    is the durable fix; --existence is the answer available today.

    --existence resolves every identifier against its source ontology via
    scripts/term_validation/ (OAK where reachable, else OLS4/REST, all cached).
    It is ADVISORY: findings are printed but never change the exit status,
    because gating on it is a separate decision.

Usage:
    python scripts/validate_node_ontology.py                 # all files, prefix check
    python scripts/validate_node_ontology.py kb/paths/X.yaml # specific file(s)
    python scripts/validate_node_ontology.py --deep          # hand off to linkml-term-validator
    python scripts/validate_node_ontology.py --existence     # also resolve every id (advisory)
    python scripts/validate_node_ontology.py --json          # machine-readable

Exit status: 0 if every node passes (prefix matches canonical), 1 otherwise.
Warnings (legacy prefixes) do not affect exit status.
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import unicodedata
from pathlib import Path
from typing import Iterable

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "drugmechdb.yaml"


# Canonical CURIE prefixes per Biolink node type, sourced from
# src/drugmechdb/schema/biolink_nodes.yaml (Canonical ID prefix in each
# permissible_value description). Multiple canonical prefixes are permitted.
CANONICAL_PREFIXES: dict[str, set[str]] = {
    "Drug": {"MESH", "DB"},
    "Protein": {"UniProt"},
    "BiologicalProcess": {"GO"},
    "MolecularActivity": {"GO"},
    "CellularComponent": {"GO"},
    "Cell": {"CL"},
    "Pathway": {"REACT", "Reactome"},
    "Disease": {"MESH"},
    "PhenotypicFeature": {"HP"},
    "GrossAnatomicalStructure": {"UBERON"},
    "ChemicalSubstance": {"MESH", "CHEBI"},
    "GeneFamily": {"InterPro"},
    "OrganismTaxon": {"NCBITaxon"},
    "MacromolecularComplex": {"PR"},
}

# Legacy prefixes that are tolerated (warning, not failure) — see schema's
# "Legacy / non-canonical prefixes present in existing data" block.
LEGACY_PREFIXES: dict[str, set[str]] = {
    "OrganismTaxon": {"taxonomy"},
    "Pathway": {"reactome"},
    "GeneFamily": {"Pfam", "TIGR"},
}


def parse_curie(curie: str) -> tuple[str | None, str | None]:
    if not isinstance(curie, str) or ":" not in curie:
        return None, None
    prefix, rest = curie.split(":", 1)
    return prefix, rest


# A CURIE identifier is `prefix:reference` and must contain no whitespace and no
# invisible characters. Control (Cc), format (Cf — e.g. U+FEFF zero-width no-break
# space, U+200B zero-width space), and space-separator (Zs/Zl/Zp) characters can hide
# inside an ID — often as a copy-paste artifact or a YAML `﻿` escape — leaving the
# ID looking correct while failing to resolve. Reject them so they can't reappear.
def invisible_chars(value) -> list[str]:
    if not isinstance(value, str):
        return []
    return [f"U+{ord(ch):04X}" for ch in value
            if unicodedata.category(ch) in ("Cc", "Cf", "Zs", "Zl", "Zp")]


# Node names are human-readable and may contain ordinary spaces (U+0020), but never
# invisible or non-standard-whitespace characters: a U+00A0 non-breaking space or a
# zero-width char is always a copy-paste artifact that corrupts the label and can
# defeat canonical-label matching. Ordinary spaces are allowed; everything else in
# the control / format / space-separator categories is rejected.
def invisible_name_chars(value) -> list[str]:
    if not isinstance(value, str):
        return []
    return [f"U+{ord(ch):04X}" for ch in value
            if ch != " " and unicodedata.category(ch) in ("Cc", "Cf", "Zs", "Zl", "Zp")]


def iter_files(targets: Iterable[str]) -> list[Path]:
    targets = list(targets)
    if not targets:
        return sorted(p for p in PATHS_DIR.glob("*.yaml") if p.name != "_index.yaml")
    files: list[Path] = []
    for t in targets:
        p = Path(t)
        if p.is_dir():
            files.extend(sorted(q for q in p.glob("*.yaml") if q.name != "_index.yaml"))
        elif p.is_file():
            files.append(p)
    return files


def validate_file(path: Path) -> tuple[list[dict], list[dict]]:
    """Return (failures, warnings)."""
    with path.open() as fh:
        doc = yaml.safe_load(fh)
    failures = []
    warnings = []
    if not isinstance(doc, dict):
        failures.append({"file": str(path), "node_index": None, "id": None, "label": None, "reason": "not a YAML mapping"})
        return failures, warnings

    for i, node in enumerate(doc.get("nodes") or []):
        if not isinstance(node, dict):
            failures.append({"file": str(path), "node_index": i, "id": None, "label": None, "reason": "node is not a mapping"})
            continue
        nid = node.get("id")
        label = node.get("label")

        bad = invisible_chars(nid)
        if bad:
            failures.append({
                "file": str(path), "node_index": i, "id": nid, "label": label,
                "reason": f"identifier contains invisible/whitespace character(s) {bad} — "
                          "strip them (a zero-width char makes the ID fail to resolve while looking correct)",
            })
            continue

        name_bad = invisible_name_chars(node.get("name"))
        if name_bad:
            failures.append({
                "file": str(path), "node_index": i, "id": nid, "label": label,
                "reason": f"name contains invisible/non-standard-whitespace character(s) {name_bad} "
                          "— normalize to ordinary spaces (ordinary spaces are fine)",
            })

        prefix, _ = parse_curie(nid)

        if label not in CANONICAL_PREFIXES:
            failures.append({
                "file": str(path), "node_index": i, "id": nid, "label": label,
                "reason": f"unknown Biolink node type {label!r}",
            })
            continue

        canonical = CANONICAL_PREFIXES[label]
        legacy = LEGACY_PREFIXES.get(label, set())

        if prefix in canonical:
            continue
        if prefix in legacy:
            warnings.append({
                "file": str(path), "node_index": i, "id": nid, "label": label,
                "reason": f"legacy prefix {prefix!r} (canonical: {sorted(canonical)})",
            })
            continue
        failures.append({
            "file": str(path), "node_index": i, "id": nid, "label": label,
            "reason": f"prefix {prefix!r} not canonical for label {label!r} (expected one of {sorted(canonical)})",
        })

    # Link endpoints are identifiers too — guard them so an invisible char can't
    # reappear on a source/target even if it doesn't match a (clean) node id.
    for j, edge in enumerate(doc.get("links") or []):
        if not isinstance(edge, dict):
            continue
        for field in ("source", "target"):
            bad = invisible_chars(edge.get(field))
            if bad:
                failures.append({
                    "file": str(path), "node_index": None, "id": edge.get(field), "label": None,
                    "reason": f"link[{j}] {field} identifier contains invisible/whitespace character(s) {bad}",
                })

    return failures, warnings


def run_deep_mode(files: list[Path]) -> int:
    """Hand off to linkml-term-validator. Returns its exit code."""
    if not files:
        return 0
    cli = REPO / ".venv-py310" / "bin" / "linkml-term-validator"
    if not cli.exists():
        cli_path = "linkml-term-validator"
    else:
        cli_path = str(cli)
    cmd = [cli_path, "validate-data", "--schema", str(SCHEMA), "-t", "MechanisticPath", "--lenient"]
    cmd.extend(str(p) for p in files)
    print(f"Running: {' '.join(cmd[:8])} … ({len(files)} files)")
    result = subprocess.run(cmd, capture_output=False)
    return result.returncode


def run_existence_check(files: list[Path], *, offline: bool = False,
                        quiet: bool = False) -> dict:
    """Resolve every identifier in `files`. ADVISORY — never affects exit status.

    Layer 2 gates on prefix shape only. Whether a non-resolving identifier
    should fail the build is an open decision, so this reports and returns.
    """
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    from term_validation.audit import audit
    from term_validation.resolvers import Registry

    registry = Registry(prefer_oak=False, offline=offline)
    report = audit(files, registry)
    registry.flush()
    data = report.to_dict()

    if not quiet:
        failures = report.existence_failures
        print(f"\nExistence check (advisory): {data['unique_curies']} unique identifiers, "
              f"{len(failures)} that do not resolve, "
              f"{len(report.name_mismatches)} name mismatches, "
              f"{data['status_counts'].get('unresolved', 0)} not reached.")
        for finding in failures[:20]:
            item = finding.to_dict()
            print(f"  [{item['status']}] {item['curie']}  name={item['record_name']!r}")
        if len(failures) > 20:
            print(f"  …and {len(failures) - 20} more — see scripts/audit_term_existence.py")
    return data


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="Files or directories. Default: kb/paths/")
    parser.add_argument("--deep", action="store_true", help="Hand off to linkml-term-validator")
    parser.add_argument("--existence", action="store_true",
                        help="Also resolve every identifier against its source ontology "
                             "(advisory: never changes the exit status).")
    parser.add_argument("--offline", action="store_true",
                        help="--existence only: use the committed term cache, no network.")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    files = iter_files(args.targets)

    if args.deep:
        return run_deep_mode(files)

    all_failures: list[dict] = []
    all_warnings: list[dict] = []
    for path in files:
        f, w = validate_file(path)
        all_failures.extend(f)
        all_warnings.extend(w)

    summary = {
        "files_checked": len(files),
        "failure_count": len(all_failures),
        "warning_count": len(all_warnings),
        "failures": all_failures,
        "warnings": all_warnings,
    }

    if args.existence:
        summary["existence"] = run_existence_check(files, offline=args.offline,
                                                   quiet=args.json)

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if all_failures:
            print(f"Layer 2 FAIL: {summary['failure_count']} prefix violations "
                  f"across {len({f['file'] for f in all_failures})} files "
                  f"(+ {summary['warning_count']} legacy-prefix warnings)")
            for f in all_failures[:30]:
                print(f"  {Path(f['file']).name}: node[{f['node_index']}] id={f['id']!r} label={f['label']!r} — {f['reason']}")
            if len(all_failures) > 30:
                print(f"  …and {len(all_failures) - 30} more (use --json for full list)")
        else:
            print(f"Layer 2 PASS: {len(files)} files, every node CURIE matches its canonical ontology "
                  f"({summary['warning_count']} legacy-prefix warnings).")
    return 0 if not all_failures else 1


if __name__ == "__main__":
    sys.exit(main())
