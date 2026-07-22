"""
PubMed evidence source — a thin adapter over `scripts/pubmed_fetch.py`.

PubMed keeps its full, unchanged implementation in `pubmed_fetch.py` (E-utilities,
Europe PMC / PubTator3 full text, retraction flags, the abstract/full-text tiers).
This adapter simply exposes that engine through the unified `EvidenceSource`
interface so the one CLI dispatches PMID references alongside the newer sources
without duplicating any PubMed logic. Every existing PubMed behavior — and the
tests that depend on it — is untouched.

Reference CURIE: `PMID:35569550`.
"""

from __future__ import annotations

from pathlib import Path

from . import common
from .base import EvidenceSource

pf = common.pubmed_fetch


class PubMedSource(EvidenceSource):
    PREFIX = "PMID"
    SUPPORTS_FULLTEXT = True
    DESCRIPTION = "PubMed abstracts (kept) + open-access full text (ephemeral)."

    @classmethod
    def can_handle(cls, reference_id: str) -> bool:
        return super().can_handle(reference_id) or reference_id.strip().isdigit()

    @staticmethod
    def _translate(res: dict) -> dict:
        """Normalize pubmed_fetch's `{"pmid": ...}` dict to `{"reference": PMID:...}`."""
        out = dict(res)
        pmid = out.pop("pmid", None)
        if pmid is not None:
            out["reference"] = f"PMID:{pmid}"
        return out

    def search(self, query: str, retmax: int = 20) -> list[str]:
        return [f"PMID:{p}" for p in pf.search(query, retmax=retmax)]

    def fetch(self, reference_id: str, *, force: bool = False,
              offline: bool = False, cache_dir: Path | None = None) -> dict:
        return self._translate(pf.fetch_one(reference_id, force=force, offline=offline))

    def probe(self, reference_id: str) -> dict:
        return self._translate(pf.probe(reference_id))

    def fetch_fulltext(self, reference_id: str, *, force: bool = False,
                       offline: bool = False, cache_dir: Path | None = None) -> dict:
        return self._translate(pf.fetch_fulltext_one(reference_id, force=force, offline=offline))
