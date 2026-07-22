"""
Source-agnostic backbone for the evidence-fetch layer.

`scripts/pubmed_fetch.py` established the contract every evidence source must
honor: fetch authoritative text from an API, write it into a markdown-with-YAML
cache file that `linkml-reference-validator` (QC Layer 4) reads, keep an optional
full-text body that is stripped before a PR, and never let the agent author the
source text it later cites. This module lifts that contract out of PubMed so the
*same* cache shape and ephemeral-full-text rules apply to any source.

The one invariant that makes Layer 4 source-agnostic:

    the cache file for a reference CURIE is looked up by
    `linkml-reference-validator` purely by transforming the CURIE string — it
    checks that file on disk BEFORE any network fetch. So if a fetcher writes a
    file whose name matches what the validator will compute, Layer 4
    verbatim-verifies the snippet from it regardless of which source produced it.

`cache_filename()` mirrors the validator's `normalize_reference_id()` +
`get_cache_path()` byte-for-byte (guarded by a parity test), so a curator may
write `ChEMBL:CHEMBL25`, `bioRxiv:10.1101/…`, `clinicaltrials:NCT…` etc. and the
snippet is checked against exactly the file the matching fetcher wrote.

PubMed keeps its own, unchanged implementation in `pubmed_fetch.py`; this layer
reuses that module's generic primitives (HTTP with per-host throttle + retry,
JATS normalization, frontmatter helpers) rather than duplicating them.
"""

from __future__ import annotations

import datetime as dt
import hashlib
import importlib.util
import os
import re
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent.parent.parent
SCRIPTS = REPO / "scripts"

# ---------------------------------------------------------------------------
# Reuse pubmed_fetch.py's generic primitives (scripts/ is not a package, so it
# is imported by file path — the same pattern tests and scripts/quality use).
# This keeps HTTP throttling/backoff, TLS setup, JATS normalization, and the
# cache-shape helpers single-sourced instead of re-implemented per source.
# ---------------------------------------------------------------------------
if "pubmed_fetch" in sys.modules:
    pubmed_fetch = sys.modules["pubmed_fetch"]
else:
    _pf_spec = importlib.util.spec_from_file_location("pubmed_fetch", SCRIPTS / "pubmed_fetch.py")
    pubmed_fetch = importlib.util.module_from_spec(_pf_spec)
    sys.modules["pubmed_fetch"] = pubmed_fetch
    _pf_spec.loader.exec_module(pubmed_fetch)

http_get = pubmed_fetch._http_get              # (url, *, accept=None, max_retries=3) -> bytes
yaml_quote = pubmed_fetch._yaml_quote          # per validator frontmatter convention
normalize_jats = pubmed_fetch.normalize_jats   # JATS full-text XML -> flattened prose
cache_is_fresh = pubmed_fetch.cache_is_fresh   # (path, ttl_days) -> bool
cache_content_type = pubmed_fetch._cache_content_type
parse_frontmatter = pubmed_fetch._parse_frontmatter

# The literal marker that separates the prepended abstract from an ephemeral
# full-text body inside a cache file. MUST equal pubmed_fetch's so a single
# `strip-fulltext` pass reverts every source's full_text caches identically.
FULLTEXT_MARKER = pubmed_fetch.FULLTEXT_MARKER

CACHE_TTL_DAYS = pubmed_fetch.CACHE_TTL_DAYS

# Same DMDB_CACHE_DIR contract as pubmed_fetch: default to the committed
# references_cache/, redirect for isolated runs. Unset == original behavior.
CACHE_DIR = (
    Path(os.environ["DMDB_CACHE_DIR"]).resolve()
    if os.environ.get("DMDB_CACHE_DIR")
    else REPO / "references_cache"
)


def _cache_dir(cache_dir: Path | None) -> Path:
    return Path(cache_dir).resolve() if cache_dir is not None else CACHE_DIR


# ---------------------------------------------------------------------------
# Reference-id normalization — a native mirror of linkml-reference-validator's
# ReferenceFetcher.normalize_reference_id + get_cache_path. Kept native (rather
# than importing the validator) so a fetch never depends on the validator being
# importable; a parity test asserts it stays byte-identical to the validator.
# ---------------------------------------------------------------------------
_PREFIX_ID_RE = re.compile(r"^([A-Za-z_]+)[:\s]+(.+)$")


def _parse_reference_id(reference_id: str) -> tuple[str, str]:
    stripped = reference_id.strip()
    if stripped.lower().startswith(("http://", "https://")):
        return "url", stripped
    m = _PREFIX_ID_RE.match(stripped)
    if m:
        prefix = m.group(1)
        # file/url keep lower case; every other prefix is upper-cased — exactly
        # like the validator, so e.g. `bioRxiv:` and `biorxiv:` collapse to one file.
        prefix = prefix.lower() if prefix.lower() in ("file", "url") else prefix.upper()
        return prefix, m.group(2).strip()
    if stripped.isdigit():
        return "PMID", stripped
    return "UNKNOWN", reference_id


def normalize_reference_id(reference_id: str) -> str:
    """Canonical reference id (upper-cased prefix), matching the QC validator."""
    prefix, identifier = _parse_reference_id(reference_id)
    if prefix == "UNKNOWN":
        return reference_id.strip()
    return f"{prefix}:{identifier}"


def cache_filename(reference_id: str) -> str:
    """The cache file name QC Layer 4 will look for, for this reference CURIE."""
    norm = normalize_reference_id(reference_id)
    safe = norm.replace(":", "_").replace("/", "_").replace("?", "_").replace("=", "_")
    return f"{safe}.md"


def cache_path(reference_id: str, cache_dir: Path | None = None) -> Path:
    return _cache_dir(cache_dir) / cache_filename(reference_id)


def iso_now() -> str:
    return dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")


def content_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]


# ---------------------------------------------------------------------------
# Cache writer — the ONE definition of the source-agnostic cache shape. Mirrors
# pubmed_fetch._write_cache's layout exactly (verified by a parity test) so the
# QC gate treats every source's file identically: YAML frontmatter, then a
# `## Content` body the validator extracts and substring-matches.
# ---------------------------------------------------------------------------
def write_cache(
    reference_id: str,
    record: dict,
    *,
    content_type: str = "abstract",
    body: str | None = None,
    cache_dir: Path | None = None,
) -> Path:
    """Write one reference cache file for `reference_id` (any source).

    `record` supplies optional metadata (title/authors/journal/year/doi/… and a
    default `abstract`). `body` overrides the cached content (used for full
    text, where it is `abstract + FULLTEXT_MARKER + fulltext`). The literal
    `## Content` heading is required — the validator keys body extraction off it.
    """
    directory = _cache_dir(cache_dir)
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / cache_filename(reference_id)

    lines = ["---"]
    lines.append(f"reference_id: {normalize_reference_id(reference_id)}")
    if record.get("source"):
        # Provenance only; the validator ignores unknown frontmatter keys.
        lines.append(f"source: {record['source']}")
    if record.get("title"):
        lines.append(f"title: {yaml_quote(record['title'])}")
    if record.get("authors"):
        lines.append("authors:")
        for a in record["authors"]:
            lines.append(f"- {yaml_quote(a)}")
    if record.get("journal"):
        lines.append(f"journal: {yaml_quote(record['journal'])}")
    if record.get("year"):
        lines.append(f"year: '{record['year']}'")
    if record.get("doi"):
        lines.append(f"doi: {record['doi']}")
    if record.get("url"):
        lines.append(f"url: {yaml_quote(record['url'])}")
    if record.get("retracted"):
        lines.append("retracted: true")
    if record.get("fulltext_source"):
        lines.append(f"fulltext_source: {record['fulltext_source']}")
    if record.get("license"):
        lines.append(f"license: {yaml_quote(record['license'])}")
    if record.get("content_hash"):
        lines.append(f"content_hash: {record['content_hash']}")
    lines.append(f"content_type: {content_type}")
    lines.append(f"fetched_at: '{iso_now()}'")
    lines.append("---")
    lines.append("")
    if record.get("title"):
        lines.append(f"# {record['title']}")
        if record.get("authors"):
            lines.append(f"**Authors:** {', '.join(record['authors'])}")
        if record.get("journal"):
            jr = record["journal"] + (f" ({record['year']})" if record.get("year") else "")
            lines.append(f"**Journal:** {jr}")
        if record.get("doi"):
            lines.append(f"**DOI:** [{record['doi']}](https://doi.org/{record['doi']})")
        lines.append("")
        lines.append("## Content")
        lines.append("")
    content = body if body is not None else record.get("abstract")
    if content:
        lines.append(content)
    elif record.get("title"):
        lines.append("(No abstract available — title only.)")
    path.write_text("\n".join(lines), encoding="utf-8")
    return path


def assemble_fulltext_body(abstract: str | None, fulltext: str) -> str:
    """Compose a full_text body: abstract, marker, then the ephemeral body.

    Mirrors pubmed_fetch so the file supersets the abstract tier (abstract-grounded
    snippets keep validating) and `strip-fulltext` can cleanly recover the abstract.
    """
    if abstract:
        return abstract + "\n\n" + FULLTEXT_MARKER + "\n\n" + fulltext
    return fulltext


# ---------------------------------------------------------------------------
# Ephemeral full text — strip a full_text cache back to abstract-only, keeping
# every scrap of metadata + the verified snippet. Source-agnostic: any
# `<SOURCE>_<id>.md` file works, because the marker convention is shared.
# ---------------------------------------------------------------------------
def strip_fulltext_file(path: Path, *, offline: bool = False, refetch_abstract=None) -> dict:
    """Revert one full_text cache FILE to abstract-only.

    Drops everything from FULLTEXT_MARKER onward plus the full-text-only metadata
    (fulltext_source / license / content_hash), preserving all citation metadata.
    No-op for abstract-only (or missing) files. For a marker-less legacy full_text
    file the abstract is recovered via the optional `refetch_abstract(reference_id)`
    callable (skipped when offline)."""
    if not path.exists():
        return {"file": str(path), "skipped": "not cached"}

    fm = parse_frontmatter(path)
    if fm.get("content_type") != "full_text":
        return {"file": str(path), "skipped": "not full_text"}

    reference_id = fm.get("reference_id") or path.stem
    text = path.read_text(encoding="utf-8")
    body = text.split("## Content", 1)[1].strip() if "## Content" in text else ""
    if FULLTEXT_MARKER in body:
        abstract = body.split(FULLTEXT_MARKER, 1)[0].strip()
    elif offline or refetch_abstract is None:
        return {"file": str(path), "reference_id": reference_id,
                "skipped": "legacy full_text, no marker, offline — left as-is"}
    else:
        abstract = (refetch_abstract(reference_id) or "").strip()

    record = {
        "source": fm.get("source"),
        "title": fm.get("title"), "authors": fm.get("authors"),
        "journal": fm.get("journal"), "year": fm.get("year"),
        "doi": fm.get("doi"), "url": fm.get("url"),
        "retracted": fm.get("retracted"),
        "abstract": abstract,
    }
    write_cache(reference_id, record, content_type="abstract",
                body=abstract or None, cache_dir=path.parent)
    return {"file": str(path), "reference_id": reference_id, "stripped": True,
            "had_abstract": bool(abstract)}
