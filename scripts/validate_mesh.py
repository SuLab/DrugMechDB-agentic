#!/usr/bin/env python3
"""
MeSH node validation — do MESH identifiers resolve at the NLM, and do node names match a MeSH entry term?

Named by conf/oak_config.yaml, which routes MESH to a custom validator because
it is not an OBO ontology and has no `sqlite:obo:` adapter. The config has
described this script since July; this is it.

Audit by default — it reports and exits 0. Pass --strict for gate behaviour.

Usage:
    python scripts/validate_mesh.py                  # whole corpus
    python scripts/validate_mesh.py kb/paths/X.yaml  # specific files
    python scripts/validate_mesh.py --offline        # committed cache only
    python scripts/validate_mesh.py --strict         # exit 1 on a bad identifier
"""

from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))  # scripts/ is not a package

from term_validation.cli import run  # noqa: E402

if __name__ == "__main__":
    sys.exit(run("MESH", {"MESH"}))
