#!/usr/bin/env python3
"""
UniProt node validation — do UniProt accessions resolve, and are any of them deleted?

Named by conf/oak_config.yaml, which routes UniProt to a custom validator because
it is not an OBO ontology and has no `sqlite:obo:` adapter. The config has
described this script since July; this is it.

Audit by default — it reports and exits 0. Pass --strict for gate behaviour.

Usage:
    python scripts/validate_uniprot.py                  # whole corpus
    python scripts/validate_uniprot.py kb/paths/X.yaml  # specific files
    python scripts/validate_uniprot.py --offline        # committed cache only
    python scripts/validate_uniprot.py --strict         # exit 1 on a bad identifier
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ is not a package

from term_validation.cli import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run("UniProt", {"UniProt"}))
