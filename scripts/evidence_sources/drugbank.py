"""
DrugBank evidence source — mechanism-of-action prose.

DrugBank's Mechanism-of-Action text is a primary sanctioned source that
*asserts* the established mechanism (AGENTS.md §4). Two access caveats,
BOTH deliberately surfaced rather than hidden:

  1. Access is gated. DrugBank's own pages require a login/license (go.drugbank.com
     returns 403 unauthenticated), and the free BioThings aggregator (MyChem.info)
     carries only DrugBank's openly-redistributable fields — NOT `mechanism_of_action`.
     So a *live* MoA fetch generally fails in an unauthenticated environment; this
     fetcher is built end-to-end and verified against a recorded fixture, and live
     verification is PENDING a licensed access path.
  2. Licensing. DrugBank's academic data is CC-BY-NC. Whether a MoA sentence may be
     committed to this repo (as an abstract-tier snippet) or must be treated as an
     ephemeral body is an open policy question flagged for the maintainers.

Fetch order: MyChem.info `drugbank.mechanism_of_action` (if a licensed instance
exposes it) → the `DMDB_DRUGBANK_FIXTURE` recorded-response file (for offline
tests / a maintainer-provided export). Reference CURIE: `DrugBank:DB00945`.
"""

from __future__ import annotations

import json
import os
from pathlib import Path

from . import common
from .base import EvidenceSource

MYCHEM = "https://mychem.info/v1/chem/{db_id}?fields=drugbank.mechanism_of_action,drugbank.name"


class DrugBankSource(EvidenceSource):
    PREFIX = "DrugBank"
    SUPPORTS_FULLTEXT = False
    DESCRIPTION = ("DrugBank mechanism-of-action prose (license-gated; live fetch "
                   "pending, fixture-backed).")

    @classmethod
    def identifier(cls, reference_id: str) -> str:
        return super().identifier(reference_id).upper()

    def _from_mychem(self, db_id: str) -> tuple[str | None, str | None]:
        """Return (mechanism_of_action, drug_name) from MyChem, or (None, None)."""
        try:
            data = json.loads(common.http_get(MYCHEM.format(db_id=db_id),
                                              accept="application/json"))
        except Exception:
            return None, None
        db = data.get("drugbank") or {}
        if isinstance(db, list):  # MyChem may return a list for merged records
            db = db[0] if db else {}
        return db.get("mechanism_of_action"), db.get("name")

    def _from_fixture(self, db_id: str) -> tuple[str | None, str | None]:
        """Read a recorded MoA response from DMDB_DRUGBANK_FIXTURE (JSON).

        Format: {"DB00945": {"mechanism_of_action": "...", "name": "..."}} or a
        single {"mechanism_of_action": "...", "name": "..."} object.
        """
        fixture = os.environ.get("DMDB_DRUGBANK_FIXTURE")
        if not fixture or not Path(fixture).exists():
            return None, None
        try:
            data = json.loads(Path(fixture).read_text(encoding="utf-8"))
        except Exception:
            return None, None
        rec = data.get(db_id, data) if isinstance(data, dict) else {}
        return rec.get("mechanism_of_action"), rec.get("name")

    def fetch(self, reference_id: str, *, force: bool = False,
              offline: bool = False, cache_dir: Path | None = None) -> dict:
        db_id = self.identifier(reference_id)
        ref = self.canonical_reference(db_id)

        hit = self._fresh_cache_hit(ref, force, cache_dir)
        if hit:
            return hit

        moa = name = None
        if not offline:
            moa, name = self._from_mychem(db_id)
        if not moa:
            moa, name = self._from_fixture(db_id)

        if not moa:
            if offline:
                path = common.cache_path(ref, cache_dir)
                if path.exists():
                    return {"reference": ref, "cached": True, "stale": True, "path": str(path)}
            return {"reference": ref,
                    "error": ("no open DrugBank mechanism_of_action available "
                              "(license-gated; set DMDB_DRUGBANK_FIXTURE or use a "
                              "licensed MyChem instance)")}

        record = {
            "source": "drugbank",
            "title": f"DrugBank mechanism of action: {name or db_id}",
            "abstract": moa.strip(),
            "license": "CC-BY-NC (DrugBank academic)",
            "url": f"https://go.drugbank.com/drugs/{db_id}",
        }
        written = common.write_cache(ref, record, content_type="abstract", cache_dir=cache_dir)
        return {"reference": ref, "cached": False, "path": str(written),
                "license_note": "CC-BY-NC — commit-vs-ephemeral policy open (see maintainers)"}
