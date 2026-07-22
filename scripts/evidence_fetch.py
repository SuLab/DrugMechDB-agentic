#!/usr/bin/env python3
"""
Launcher for the unified, source-agnostic evidence-fetch CLI.

This is the one entry point for fetching + caching evidence from ANY sanctioned
source (PubMed, ChEMBL, ClinicalTrials.gov, bioRxiv/medRxiv, DrugBank). It is the
multi-source companion to `scripts/pubmed_fetch.py` (which remains the PubMed
engine): every source writes the same cache shape and honors the same ephemeral
full-text rule, so QC Layer 4 verbatim-verifies snippets source-agnostically.

    python scripts/evidence_fetch.py sources
    python scripts/evidence_fetch.py fetch ChEMBL:CHEMBL25
    python scripts/evidence_fetch.py fetch bioRxiv:10.1101/2020.05.01.072066 --fulltext
    python scripts/evidence_fetch.py strip-fulltext --all

Implementation lives in scripts/evidence_sources/ (one module per source).
"""

from __future__ import annotations

import sys
from pathlib import Path

# scripts/ is not a package; put it on sys.path so `evidence_sources` imports
# (the same convention scripts/quality/critic.py uses for its siblings).
sys.path.insert(0, str(Path(__file__).resolve().parent))

from evidence_sources.cli import main  # noqa: E402

if __name__ == "__main__":
    sys.exit(main())
