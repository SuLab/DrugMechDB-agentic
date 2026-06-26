"""Cache layer for research dossiers.

Layout:
  research/<drug_slug>_<disease_slug>-<provider>.md

Each file is markdown with YAML frontmatter that captures provider, model,
query, generation timestamp, and TTL. Fresh entries within TTL are returned
unchanged; stale entries are silently overwritten on the next run.

The TTL default is 30 days (mechanism understanding evolves faster than the
underlying PubMed abstracts, which use the PRD's 90-day cap).
"""

from __future__ import annotations

import datetime as dt
import re
from pathlib import Path

import yaml

from .base import ResearchDossier

REPO = Path(__file__).resolve().parent.parent.parent
CACHE_DIR = REPO / "research"
DEFAULT_TTL_DAYS = 30


_SLUG_RE = re.compile(r"[^a-z0-9]+")


def slugify(text: str) -> str:
    """Filesystem-safe slug. Lowercase, non-alphanumerics → underscore."""
    return _SLUG_RE.sub("_", text.lower()).strip("_")


def cache_path(drug: str, disease: str, provider: str) -> Path:
    fname = f"{slugify(drug)}_{slugify(disease)}-{provider}.md"
    return CACHE_DIR / fname


# ─── Read ─────────────────────────────────────────────────────────────────


def load(path: Path) -> tuple[dict, str] | None:
    """Return (frontmatter, body) if the cache file exists, else None."""
    if not path.exists():
        return None
    text = path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return None
    parts = text.split("---", 2)
    if len(parts) < 3:
        return None
    try:
        fm = yaml.safe_load(parts[1]) or {}
    except yaml.YAMLError:
        return None
    return fm, parts[2].lstrip("\n")


def is_fresh(frontmatter: dict, ttl_days: int = DEFAULT_TTL_DAYS) -> bool:
    """Check whether a cache entry is within its TTL.

    `ttl_days` is the active policy at read time; it overrides whatever
    `ttl_days` was stored in the entry's frontmatter at write time. The stored
    value is kept for human reference only — it documents what TTL was active
    when the entry was produced.
    """
    ts = frontmatter.get("generated_at")
    if not ts:
        return False
    if isinstance(ts, str):
        try:
            ts = dt.datetime.fromisoformat(ts.rstrip("Z"))
        except ValueError:
            return False
    if ts.tzinfo is None:
        ts = ts.replace(tzinfo=dt.timezone.utc)
    age = dt.datetime.now(dt.timezone.utc) - ts
    return age.days < ttl_days


# ─── Write ────────────────────────────────────────────────────────────────


def write(dossier: ResearchDossier, ttl_days: int = DEFAULT_TTL_DAYS) -> Path:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(dossier.drug, dossier.disease, dossier.provider)
    fm = {
        "provider": dossier.provider,
        "model": dossier.model,
        "drug": dossier.drug,
        "disease": dossier.disease,
        "query": dossier.query,
        "generated_at": dossier.generated_at.isoformat(timespec="seconds"),
        "ttl_days": ttl_days,
        "candidate_pmids": dossier.candidate_pmids,
    }
    if dossier.cost_usd is not None:
        fm["cost_usd"] = dossier.cost_usd
    if dossier.notes:
        fm["notes"] = dossier.notes

    fm_yaml = yaml.dump(fm, sort_keys=False, allow_unicode=True).rstrip()
    body = dossier.markdown_body.lstrip("\n").rstrip() + "\n"
    path.write_text(f"---\n{fm_yaml}\n---\n\n{body}", encoding="utf-8")
    return path


# ─── Combined: try-cache-then-call ────────────────────────────────────────


def load_if_fresh(
    drug: str,
    disease: str,
    provider: str,
    ttl_days: int = DEFAULT_TTL_DAYS,
) -> Path | None:
    """Return the cache path if a fresh entry exists; else None."""
    path = cache_path(drug, disease, provider)
    loaded = load(path)
    if not loaded:
        return None
    fm, _ = loaded
    return path if is_fresh(fm, ttl_days) else None
