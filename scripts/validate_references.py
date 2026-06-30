"""
Layer 4 — Reference verification.

For each input file that contains `evidence` items, verify that every
EvidenceItem's `snippet` is a verbatim substring of the abstract of the
cited PMID. Abstracts are fetched from PubMed E-utilities and cached in
references_cache/ (90-day TTL by default in the linkml-reference-validator
config).

This layer is a no-op for files without any `evidence` field. Legacy
profile paths skip Layer 4 entirely; ai_curated paths require it.

Delegates the actual fetch + substring check to the upstream tool:
    linkml-reference-validator validate data <file> --schema <schema>

The schema's `snippet` slot is tagged `slot_uri: oa:exact` and `reference`
is tagged `slot_uri: dcterms:references` so the validator can auto-detect
which slots to check.

Usage:
    python scripts/validate_references.py                   # all files (legacy = no-op)
    python scripts/validate_references.py kb/paths/X.yaml   # specific file(s)
    python scripts/validate_references.py --offline         # do not hit PubMed; use cache only
    python scripts/validate_references.py --json            # machine-readable output

Exit status: 0 if all files pass (or have no evidence to check), 1 otherwise.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from pathlib import Path
from typing import Iterable

import yaml

REPO = Path(__file__).resolve().parent.parent
PATHS_DIR = REPO / "kb" / "paths"
SCHEMA = REPO / "src" / "drugmechdb" / "schema" / "drugmechdb.yaml"
CACHE_DIR = Path(os.environ["DMDB_CACHE_DIR"]).resolve() if os.environ.get("DMDB_CACHE_DIR") else REPO / "references_cache"
VALIDATOR_BIN = REPO / ".venv-py310" / "bin" / "linkml-reference-validator"


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


def has_evidence(path: Path) -> bool:
    """Cheap pre-check: does this file contain any `evidence:` block on an edge?"""
    with path.open() as fh:
        doc = yaml.safe_load(fh)
    if not isinstance(doc, dict):
        return False
    for link in doc.get("links") or []:
        if isinstance(link, dict) and link.get("evidence"):
            return True
    return False


def _validator_cli() -> str:
    return str(VALIDATOR_BIN) if VALIDATOR_BIN.exists() else "linkml-reference-validator"


def run_validator(path: Path, offline: bool) -> tuple[int, str]:
    """Return (exit_code, combined_stdout_stderr)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cmd = [
        _validator_cli(),
        "validate", "data", str(path),
        "--schema", str(SCHEMA),
        "--target-class", "MechanisticPath",
        "--cache-dir", str(CACHE_DIR),
    ]
    env = os.environ.copy()
    if offline:
        env["LINKML_REFERENCE_VALIDATOR_OFFLINE"] = "1"
    proc = subprocess.run(cmd, capture_output=True, text=True, env=env)
    return proc.returncode, proc.stdout + proc.stderr


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("targets", nargs="*", help="Files or directories. Default: kb/paths/")
    parser.add_argument("--offline", action="store_true", help="Cache-only (do not fetch from PubMed)")
    parser.add_argument("--json", action="store_true", help="Machine-readable output")
    args = parser.parse_args()

    files = iter_files(args.targets)
    with_evidence = [p for p in files if has_evidence(p)]

    per_file: list[dict] = []
    fails = 0
    for path in with_evidence:
        code, log = run_validator(path, offline=args.offline)
        per_file.append({"file": str(path), "exit_code": code, "log": log})
        if code != 0:
            fails += 1

    summary = {
        "files_checked": len(files),
        "files_with_evidence": len(with_evidence),
        "files_failing": fails,
        "results": per_file,
    }

    if args.json:
        print(json.dumps(summary, indent=2))
    else:
        if not with_evidence:
            print(f"Layer 4 NO-OP: {len(files)} files, none contain evidence to verify "
                  "(legacy paths skip Layer 4 by design).")
        elif fails == 0:
            print(f"Layer 4 PASS: {len(with_evidence)} files with evidence, "
                  f"every snippet verified as verbatim substring of its PMID abstract.")
        else:
            print(f"Layer 4 FAIL: {fails} / {len(with_evidence)} files have at least one snippet "
                  "that is not a verbatim substring of its PMID abstract.")
            for r in per_file[:5]:
                if r["exit_code"] != 0:
                    print(f"\n  {Path(r['file']).name}:")
                    for line in r["log"].splitlines()[:8]:
                        print(f"    {line}")
    return 0 if fails == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
