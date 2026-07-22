"""
ClinicalTrials.gov evidence source — registered-trial summaries.

A trial record's brief/detailed summary asserts the intended mechanism and
therapeutic rationale (e.g. "nifedipine … to permit a decrease in the dose of
glucocorticoid …"). ClinicalTrials.gov content is US-government public domain,
so the summary is cached as the `abstract` tier (kept, re-verifiable); there is
no separate ephemeral full-text body.

Reference CURIE: `clinicaltrials:NCT00000102` (bioregistry standard prefix).
API: https://clinicaltrials.gov/api/v2  (free, no key).
"""

from __future__ import annotations

import json
import re
import urllib.parse
from pathlib import Path

from . import common
from .base import EvidenceSource

API = "https://clinicaltrials.gov/api/v2"
_NCT_RE = re.compile(r"^NCT\d{8}$", re.IGNORECASE)


class ClinicalTrialsSource(EvidenceSource):
    PREFIX = "clinicaltrials"
    SUPPORTS_FULLTEXT = False
    DESCRIPTION = "ClinicalTrials.gov registered-trial summaries (public domain)."

    @classmethod
    def can_handle(cls, reference_id: str) -> bool:
        # Own the prefixed form and a bare NCT id.
        return super().can_handle(reference_id) or bool(_NCT_RE.match(reference_id.strip()))

    @classmethod
    def identifier(cls, reference_id: str) -> str:
        ident = super().identifier(reference_id)
        return ident.upper()

    def search(self, query: str, retmax: int = 20) -> list[str]:
        url = (f"{API}/studies?query.term={urllib.parse.quote(query)}"
               f"&fields=protocolSection.identificationModule.nctId&pageSize={retmax}")
        try:
            data = json.loads(common.http_get(url, accept="application/json"))
        except Exception:
            return []
        out = []
        for study in data.get("studies") or []:
            nct = (study.get("protocolSection", {})
                   .get("identificationModule", {}).get("nctId"))
            if nct:
                out.append(self.canonical_reference(nct))
        return out[:retmax]

    def fetch(self, reference_id: str, *, force: bool = False,
              offline: bool = False, cache_dir: Path | None = None) -> dict:
        nct = self.identifier(reference_id)
        ref = self.canonical_reference(nct)

        hit = self._fresh_cache_hit(ref, force, cache_dir)
        if hit:
            return hit
        if offline:
            path = common.cache_path(ref, cache_dir)
            if path.exists():
                return {"reference": ref, "cached": True, "stale": True, "path": str(path)}
            return {"reference": ref, "error": "offline and not cached"}

        url = f"{API}/studies/{nct}"
        try:
            data = json.loads(common.http_get(url, accept="application/json"))
        except Exception as e:
            return {"reference": ref, "error": f"ClinicalTrials.gov fetch failed: {e}"}

        record = self._parse(nct, data)
        if not record.get("abstract"):
            return {"reference": ref, "error": f"no summary text for {nct}"}
        written = common.write_cache(ref, record, content_type="abstract", cache_dir=cache_dir)
        return {"reference": ref, "cached": False, "path": str(written),
                "status": record.get("_status")}

    def _parse(self, nct: str, data: dict) -> dict:
        proto = data.get("protocolSection", {})
        ident = proto.get("identificationModule", {})
        desc = proto.get("descriptionModule", {})
        status = proto.get("statusModule", {})

        title = ident.get("officialTitle") or ident.get("briefTitle")
        parts = [t for t in (desc.get("briefSummary"), desc.get("detailedDescription")) if t]
        year = None
        sd = status.get("startDateStruct", {}).get("date") or status.get("statusVerifiedDate")
        if sd:
            m = re.match(r"(\d{4})", sd)
            if m:
                year = m.group(1)
        return {
            "source": "clinicaltrials",
            "title": title,
            "year": year,
            "abstract": "\n\n".join(parts).strip(),
            "url": f"https://clinicaltrials.gov/study/{nct}",
            "_status": status.get("overallStatus"),
        }
