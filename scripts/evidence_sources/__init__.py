"""
Source-agnostic evidence-fetch layer for DrugMechDB curation.

Sourcing is source-agnostic (AGENTS.md §4): an EvidenceItem may cite any
connected source that *asserts* the established mechanism, as long as the
snippet is a verbatim substring of the fetched-and-cached text. This package
is the one fetch-and-cache layer over every sanctioned source. Each source
writes the SAME cache shape `pubmed_fetch.py` established, under a
source-agnostic key (`<SOURCE>_<id>.md`) that QC Layer 4 resolves and
verbatim-verifies regardless of source, and honors the SAME ephemeral
full-text rule (non-abstract bodies are stripped once the record passes QC).

Sources:
  - PMID          — PubMed (delegates to scripts/pubmed_fetch.py)
  - ChEMBL        — curated mechanism-of-action assertions
  - clinicaltrials— ClinicalTrials.gov trial summaries
  - bioRxiv       — bioRxiv preprints (ephemeral OA full text)
  - medRxiv       — medRxiv preprints (ephemeral OA full text)

CLI: `python scripts/evidence_fetch.py …` (see cli.py).
"""

from __future__ import annotations

from pathlib import Path

from . import common
from .base import EvidenceSource, SourceRegistry
from .pubmed import PubMedSource
from .chembl import ChEMBLSource
from .clinicaltrials import ClinicalTrialsSource
from .biorxiv import BioRxivSource, MedRxivSource

REGISTRY = SourceRegistry()
for _src in (PubMedSource(), ChEMBLSource(), ClinicalTrialsSource(),
             BioRxivSource(), MedRxivSource()):
    REGISTRY.register(_src)


def get_source(reference_id: str) -> EvidenceSource | None:
    """Return the source that owns `reference_id`, or None."""
    return REGISTRY.get(reference_id)


def sources() -> list[EvidenceSource]:
    return REGISTRY.all()


def _pmid_refetch_abstract(reference_id: str) -> str | None:
    """Recover a PubMed abstract for a marker-less legacy full_text file."""
    rec = common.pubmed_fetch._fetch_pubmed_record(reference_id.split(":", 1)[-1])
    return (rec or {}).get("abstract")


def strip_all_fulltext(*, offline: bool = False, cache_dir: Path | None = None) -> list[dict]:
    """Revert EVERY source's full_text cache file to abstract-only (ephemeral rule).

    Source-agnostic: globs all `*.md` files (not just `PMID_*`), so a bioRxiv or
    other preprint full-text body is stripped too. Marker-less legacy PubMed files
    recover their abstract via PubMed; other sources always carry the marker."""
    directory = common._cache_dir(cache_dir)
    out: list[dict] = []
    for path in sorted(directory.glob("*.md")):
        if common.cache_content_type(path) != "full_text":
            continue
        refetch = _pmid_refetch_abstract if path.name.startswith("PMID_") else None
        out.append(common.strip_fulltext_file(path, offline=offline, refetch_abstract=refetch))
    return out


__all__ = [
    "EvidenceSource", "SourceRegistry", "REGISTRY",
    "PubMedSource", "ChEMBLSource", "ClinicalTrialsSource",
    "BioRxivSource", "MedRxivSource",
    "get_source", "sources", "strip_all_fulltext", "common",
]
