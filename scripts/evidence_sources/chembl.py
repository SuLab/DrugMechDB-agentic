"""
ChEMBL evidence source — drug mechanism-of-action assertions.

ChEMBL curates a `mechanism_of_action` string per drug (molecule)–target pair
(e.g. CHEMBL25 "Cyclooxygenase inhibitor"). That string is an established,
already-asserted mechanism — exactly the kind of secondary assertion the
source-agnostic policy accepts (AGENTS.md §4). It is short and citation-grade,
so it is cached as the `abstract` tier (kept, re-verifiable); ChEMBL has no
full-text tier.

Reference CURIE: `ChEMBL:CHEMBL25` (the molecule ChEMBL id).
API: https://www.ebi.ac.uk/chembl/api/data  (free, no key).
"""

from __future__ import annotations

import json
from pathlib import Path

from . import common
from .base import EvidenceSource

API = "https://www.ebi.ac.uk/chembl/api/data"


class ChEMBLSource(EvidenceSource):
    PREFIX = "ChEMBL"
    SUPPORTS_FULLTEXT = False
    DESCRIPTION = "ChEMBL curated mechanism-of-action assertions (drug -> target)."

    def _fetch_mechanisms(self, chembl_id: str) -> list[dict]:
        url = f"{API}/mechanism?molecule_chembl_id={chembl_id}&format=json"
        data = json.loads(common.http_get(url, accept="application/json"))
        return data.get("mechanisms") or []

    def _molecule_name(self, chembl_id: str) -> str | None:
        try:
            url = f"{API}/molecule/{chembl_id}?format=json"
            data = json.loads(common.http_get(url, accept="application/json"))
            return data.get("pref_name")
        except Exception:
            return None

    def search(self, query: str, retmax: int = 20) -> list[str]:
        """Free-text drug-name search -> candidate `ChEMBL:` reference CURIEs."""
        import urllib.parse
        url = f"{API}/molecule/search?q={urllib.parse.quote(query)}&format=json&limit={retmax}"
        try:
            data = json.loads(common.http_get(url, accept="application/json"))
        except Exception:
            return []
        out = []
        for m in data.get("molecules") or []:
            cid = m.get("molecule_chembl_id")
            if cid:
                out.append(self.canonical_reference(cid))
        return out[:retmax]

    def fetch(self, reference_id: str, *, force: bool = False,
              offline: bool = False, cache_dir: Path | None = None) -> dict:
        ref = self.canonical_reference(reference_id)
        chembl_id = self.identifier(reference_id)

        hit = self._fresh_cache_hit(ref, force, cache_dir)
        if hit:
            return hit
        if offline:
            path = common.cache_path(ref, cache_dir)
            if path.exists():
                return {"reference": ref, "cached": True, "stale": True, "path": str(path)}
            return {"reference": ref, "error": "offline and not cached"}

        try:
            mechanisms = self._fetch_mechanisms(chembl_id)
        except Exception as e:
            return {"reference": ref, "error": f"ChEMBL fetch failed: {e}"}
        if not mechanisms:
            return {"reference": ref, "error": f"no ChEMBL mechanism_of_action for {chembl_id}"}

        # Body = ChEMBL's own assertion strings only (no fetcher-authored prose),
        # one per line, so any snippet a curator copies is verbatim ChEMBL text.
        seen: set[str] = set()
        body_lines: list[str] = []
        targets: list[str] = []
        for m in mechanisms:
            moa = (m.get("mechanism_of_action") or "").strip()
            if moa and moa not in seen:
                seen.add(moa)
                body_lines.append(moa)
            comment = (m.get("mechanism_comment") or "").strip()
            if comment and comment not in seen:
                seen.add(comment)
                body_lines.append(comment)
            if m.get("target_chembl_id"):
                targets.append(m["target_chembl_id"])

        name = self._molecule_name(chembl_id)
        record = {
            "source": "chembl",
            "title": f"ChEMBL mechanism of action: {name or chembl_id}",
            "abstract": "\n".join(body_lines),
            "url": f"https://www.ebi.ac.uk/chembl/web_components/explore/compound/{chembl_id}",
        }
        written = common.write_cache(ref, record, content_type="abstract", cache_dir=cache_dir)
        return {"reference": ref, "cached": False, "path": str(written),
                "targets": sorted(set(targets))}
