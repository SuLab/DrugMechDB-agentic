"""
The evidence-source interface + registry.

Every sanctioned source implements the same small contract so the unified CLI
can treat them interchangeably. The contract intentionally matches the verbs
`pubmed_fetch.py` already exposes (search / fetch / probe / info / strip), just
generalized off PubMed:

    prefix()              — the reference CURIE prefix this source owns (e.g. "ChEMBL")
    can_handle(ref)       — does this source own this reference id?
    canonical_reference(id) — bare id -> the CURIE a curator writes in `reference:`
    search(query, retmax) — free-text -> candidate reference CURIEs (optional)
    fetch(ref, ...)       — fetch abstract-tier text + metadata, write the cache
    probe(ref)            — is an ephemeral full-text body available? (optional)
    fetch_fulltext(ref, ...) — escalate to full text, write a full_text cache (optional)

`fetch`/`fetch_fulltext` return the same status-dict shape as pubmed_fetch
(`{"reference": ..., "cached": bool, "path": str, ...}` or `{"error": ...}`),
so the CLI reports every source uniformly.
"""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from pathlib import Path

from . import common


class EvidenceSource(ABC):
    """Base class for a sanctioned evidence source."""

    #: Reference CURIE prefix, in the exact casing a curator writes it.
    PREFIX: str = ""
    #: Whether this source can escalate to an ephemeral full-text body.
    SUPPORTS_FULLTEXT: bool = False
    #: One-line human description for the `sources` listing.
    DESCRIPTION: str = ""

    # -- identity ----------------------------------------------------------
    @classmethod
    def prefix(cls) -> str:
        return cls.PREFIX

    @classmethod
    def can_handle(cls, reference_id: str) -> bool:
        """True if this source owns `reference_id` (prefix match, case-insensitive)."""
        return bool(re.match(rf"^{re.escape(cls.PREFIX)}[:\s]", reference_id, re.IGNORECASE))

    @classmethod
    def identifier(cls, reference_id: str) -> str:
        """Strip a leading `<prefix>:` (any case) to the bare identifier."""
        s = reference_id.strip()
        m = re.match(rf"^{re.escape(cls.PREFIX)}[:\s]+(.+)$", s, re.IGNORECASE)
        return m.group(1).strip() if m else s

    @classmethod
    def canonical_reference(cls, identifier: str) -> str:
        """Bare id -> the CURIE that belongs in an EvidenceItem `reference:`."""
        return f"{cls.PREFIX}:{cls.identifier(identifier)}"

    # -- operations (override what the source supports) --------------------
    def search(self, query: str, retmax: int = 20) -> list[str]:  # pragma: no cover - optional
        raise NotImplementedError(f"{self.PREFIX} source does not support search")

    @abstractmethod
    def fetch(self, reference_id: str, *, force: bool = False,
              offline: bool = False, cache_dir: Path | None = None) -> dict:
        ...

    def probe(self, reference_id: str) -> dict:
        return {"reference": self.canonical_reference(reference_id),
                "fulltext_available": False,
                "note": f"{self.PREFIX} has no full-text tier"}

    def fetch_fulltext(self, reference_id: str, *, force: bool = False,
                       offline: bool = False, cache_dir: Path | None = None) -> dict:
        # Sources without a full-text tier fall back to the abstract tier so the
        # unified `fetch --fulltext` never errors on a mixed batch.
        if not self.SUPPORTS_FULLTEXT:
            res = self.fetch(reference_id, force=force, offline=offline, cache_dir=cache_dir)
            res.setdefault("note", f"{self.PREFIX} has no full-text tier; fetched abstract tier")
            return res
        raise NotImplementedError

    # -- shared helpers ----------------------------------------------------
    def _fresh_cache_hit(self, reference_id: str, force: bool, cache_dir: Path | None,
                         *, want_fulltext: bool = False) -> dict | None:
        """Return a cache-hit status dict if a fresh (and tier-adequate) cache exists."""
        path = common.cache_path(reference_id, cache_dir)
        if force or not common.cache_is_fresh(path):
            return None
        ctype = common.cache_content_type(path)
        if want_fulltext and ctype != "full_text":
            return None
        hit = {"reference": common.normalize_reference_id(reference_id),
               "cached": True, "path": str(path)}
        if ctype:
            hit["content_type"] = ctype
        return hit


class SourceRegistry:
    """Registry mapping reference prefixes to source instances."""

    def __init__(self) -> None:
        self._sources: list[EvidenceSource] = []

    def register(self, source: EvidenceSource) -> EvidenceSource:
        self._sources.append(source)
        return source

    def get(self, reference_id: str) -> EvidenceSource | None:
        for src in self._sources:
            if src.can_handle(reference_id):
                return src
        return None

    def by_prefix(self, prefix: str) -> EvidenceSource | None:
        for src in self._sources:
            if src.PREFIX.lower() == prefix.lower():
                return src
        return None

    def all(self) -> list[EvidenceSource]:
        return list(self._sources)
