#!/usr/bin/env python3
"""
Reactome node validation — do Reactome stable identifiers resolve?

Named by conf/oak_config.yaml, which routes Reactome to a custom validator because
it is not an OBO ontology and has no `sqlite:obo:` adapter. The config has
described this script since July; this is it.

Audit by default — it reports and exits 0. Pass --strict for gate behaviour.

Usage:
    python scripts/validate_reactome.py                  # whole corpus
    python scripts/validate_reactome.py kb/paths/X.yaml  # specific files
    python scripts/validate_reactome.py --offline        # committed cache only
    python scripts/validate_reactome.py --strict         # exit 1 on a bad identifier
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ is not a package

from term_validation.cli import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run("Reactome", {"REACT", "reactome"}))
