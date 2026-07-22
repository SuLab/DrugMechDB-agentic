"""
bioRxiv / medRxiv evidence source — preprints.

Preprints are sanctioned under the source-agnostic policy when they *assert* an
established mechanism. The bioRxiv details API returns the preprint abstract
(cached as the `abstract` tier, kept) and a `jatsxml` URL for the open-access
full text. When an edge needs a sentence the abstract lacks, the fetcher
escalates to that JATS body — normalized with the SAME JATS flattener PubMed
full text uses — and caches it as `content_type: full_text`. That body is
**ephemeral**: `strip-fulltext` deletes it once the record passes QC, so the
repo keeps the verified snippet + citation but never the copyrighted body.

Reference CURIE: `bioRxiv:10.1101/2020.05.01.072066` / `medRxiv:10.1101/…`
(the preprint DOI). API: https://api.biorxiv.org  (free, no key).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import common
from .base import EvidenceSource

DETAILS = "https://api.biorxiv.org/details/{server}/{doi}"
# Redistribution-permissive licenses whose full-text body we are willing to
# fetch (it is stripped pre-PR regardless; this just gates the escalation).
_OA_LICENSES = {"cc_by", "cc_by_sa", "cc_by_nc", "cc_by_nc_sa", "cc0", "cc_by_nd"}


class _PreprintSource(EvidenceSource):
    SERVER = ""  # "biorxiv" | "medrxiv"
    SUPPORTS_FULLTEXT = True

    def _details(self, doi: str) -> dict | None:
        url = DETAILS.format(server=self.SERVER, doi=doi)
        data = json.loads(common.http_get(url, accept="application/json"))
        coll = data.get("collection") or []
        # Latest version is last in the collection.
        return coll[-1] if coll else None

    @staticmethod
    def _authors(raw: str | None) -> list[str]:
        if not raw:
            return []
        return [a.strip() for a in raw.split(";") if a.strip()]

    def _record(self, doi: str, det: dict) -> dict:
        date = det.get("date") or ""
        return {
            "source": self.SERVER,
            "title": det.get("title"),
            "authors": self._authors(det.get("authors")),
            "journal": f"{self.SERVER} (preprint)",
            "year": date[:4] if date[:4].isdigit() else None,
            "doi": doi,
            "license": det.get("license"),
            "abstract": (det.get("abstract") or "").strip(),
            "url": det.get("jatsxml"),
        }

    def fetch(self, reference_id: str, *, force: bool = False,
              offline: bool = False, cache_dir: Path | None = None) -> dict:
        doi = self.identifier(reference_id)
        ref = self.canonical_reference(doi)

        hit = self._fresh_cache_hit(ref, force, cache_dir)
        if hit:
            return hit
        if offline:
            path = common.cache_path(ref, cache_dir)
            if path.exists():
                return {"reference": ref, "cached": True, "stale": True, "path": str(path)}
            return {"reference": ref, "error": "offline and not cached"}

        try:
            det = self._details(doi)
        except Exception as e:
            return {"reference": ref, "error": f"{self.SERVER} fetch failed: {e}"}
        if not det:
            return {"reference": ref, "error": f"{self.SERVER} preprint not found: {doi}"}
        record = self._record(doi, det)
        if not record.get("abstract"):
            return {"reference": ref, "error": f"no abstract for {doi}"}
        written = common.write_cache(ref, record, content_type="abstract", cache_dir=cache_dir)
        return {"reference": ref, "cached": False, "path": str(written),
                "license": record.get("license")}

    def probe(self, reference_id: str) -> dict:
        doi = self.identifier(reference_id)
        ref = self.canonical_reference(doi)
        try:
            det = self._details(doi)
        except Exception as e:
            return {"reference": ref, "fulltext_available": False, "error": f"lookup failed: {e}"}
        if not det:
            return {"reference": ref, "fulltext_available": False, "note": "not found"}
        jats = det.get("jatsxml")
        lic = (det.get("license") or "").lower()
        available = bool(jats) and (lic in _OA_LICENSES or not lic)
        return {"reference": ref, "fulltext_available": available,
                "best_source": self.SERVER if available else None,
                "license": det.get("license"), "jatsxml": jats}

    def fetch_fulltext(self, reference_id: str, *, force: bool = False,
                       offline: bool = False, cache_dir: Path | None = None) -> dict:
        doi = self.identifier(reference_id)
        ref = self.canonical_reference(doi)

        hit = self._fresh_cache_hit(ref, force, cache_dir, want_fulltext=True)
        if hit:
            return hit
        if offline:
            path = common.cache_path(ref, cache_dir)
            if path.exists():
                return {"reference": ref, "cached": True, "stale": True, "path": str(path)}
            return {"reference": ref, "error": "offline and not cached"}

        try:
            det = self._details(doi)
        except Exception as e:
            return {"reference": ref, "error": f"{self.SERVER} fetch failed: {e}"}
        if not det:
            return {"reference": ref, "error": f"{self.SERVER} preprint not found: {doi}"}

        jats_url = det.get("jatsxml")
        lic = (det.get("license") or "").lower()
        if not jats_url:
            return {"reference": ref, "error": "no open-access JATS full text available"}
        if lic and lic not in _OA_LICENSES:
            return {"reference": ref, "error": f"license '{lic}' not redistribution-permissive"}
        try:
            fulltext = common.normalize_jats(common.http_get(jats_url, accept="application/xml"))
        except Exception as e:
            return {"reference": ref, "error": f"JATS fetch/normalize failed: {e}"}
        if not fulltext or len(fulltext) < 200:
            return {"reference": ref, "error": "full-text body too short / unusable"}

        record = self._record(doi, det)
        abstract = record.get("abstract")
        body = common.assemble_fulltext_body(abstract, fulltext)
        record["fulltext_source"] = self.SERVER
        record["content_hash"] = common.content_hash(body)
        written = common.write_cache(ref, record, content_type="full_text",
                                     body=body, cache_dir=cache_dir)
        return {"reference": ref, "cached": False, "path": str(written),
                "content_type": "full_text", "fulltext_source": self.SERVER,
                "license": record.get("license")}


class BioRxivSource(_PreprintSource):
    PREFIX = "bioRxiv"
    SERVER = "biorxiv"
    DESCRIPTION = "bioRxiv preprints (abstract kept; OA full text ephemeral)."


class MedRxivSource(_PreprintSource):
    PREFIX = "medRxiv"
    SERVER = "medrxiv"
    DESCRIPTION = "medRxiv preprints (abstract kept; OA full text ephemeral)."
