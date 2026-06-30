"""
Thin wrapper around NCBI E-utilities + open-access full-text sources for the
AI curation agent.

The agent never authors source text: its only input here is a PMID. This wrapper
fetches from authoritative APIs and writes the result into
references_cache/PMID_xxxxxxxx.md *itself*, in the markdown-with-YAML-frontmatter
format that linkml-reference-validator reads — so a successful fetch primes Layer 4
caching too, against text the agent could not have fabricated.

Tiers:
  - `fetch`            — PubMed abstract (NCBI efetch, db=pubmed).
  - `probe`            — is open-access full text legally available? (Europe PMC
                         search; one metadata call, no body download.)
  - `fetch --fulltext` — open-access full text, normalized into the cache body
                         (Europe PMC fullTextXML -> PubTator3 -> efetch db=pmc),
                         with the PubMed abstract prepended so the file supersets
                         the abstract tier and prior abstract-grounded snippets
                         still validate.

Caching:
  - 90-day TTL (PRD §5.1.2). --force re-fetches; --offline skips the network.
  - A full_text cache is never silently downgraded back to an abstract.
  - Surfaces NCBI-flagged retractions in the cached metadata.

Rate limits are enforced *per host*: NCBI E-utilities 3 req/s (10 with
NCBI_API_KEY), PubTator3 3 req/s, Europe PMC ~10 req/s, plus exponential backoff
on 429/5xx. All sources are free and require no key (Europe PMC / PubTator3) or an
optional key (NCBI).

Usage:
    python scripts/pubmed_fetch.py search "aspirin platelet aggregation"   # PMIDs only
    python scripts/pubmed_fetch.py fetch  PMID:35569550                    # one abstract
    python scripts/pubmed_fetch.py fetch  PMID:35569550 PMID:36129273      # batch
    python scripts/pubmed_fetch.py fetch  PMID:35569550 --force            # bypass cache
    python scripts/pubmed_fetch.py fetch  PMID:35569550 --offline          # cache-only
    python scripts/pubmed_fetch.py probe  PMID:35569550                    # full-text availability
    python scripts/pubmed_fetch.py fetch  PMID:35569550 --fulltext         # escalate to full text
    python scripts/pubmed_fetch.py info   PMID:35569550                    # show cached state
    python scripts/pubmed_fetch.py strip-fulltext --all                    # revert full_text -> abstract (pre-PR)
"""

from __future__ import annotations

import argparse
import datetime as dt
import hashlib
import json
import os
import re
import ssl
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from xml.etree import ElementTree as ET

import yaml

REPO = Path(__file__).resolve().parent.parent
# CACHE_DIR defaults to the committed references_cache/, but can be redirected
# via DMDB_CACHE_DIR for isolated runs (e.g. per-arm experiment caches). The
# override is backward-compatible: unset = original behavior.
CACHE_DIR = Path(os.environ["DMDB_CACHE_DIR"]).resolve() if os.environ.get("DMDB_CACHE_DIR") else REPO / "references_cache"

# Separates the prepended PubMed abstract from the open-access full-text body
# inside a full_text cache file. It lives in the `## Content` body (so the
# verbatim matcher still sees one searchable blob) and lets `strip-fulltext`
# cleanly revert a file to abstract-only, keeping all metadata, before a PR.
FULLTEXT_MARKER = "## Full Text"

EUTILS_BASE = "https://eutils.ncbi.nlm.nih.gov/entrez/eutils"
EUROPEPMC_BASE = "https://www.ebi.ac.uk/europepmc/webservices/rest"
PUBTATOR_BASE = "https://www.ncbi.nlm.nih.gov/research/pubtator3-api"
CACHE_TTL_DAYS = 90

API_KEY = os.environ.get("NCBI_API_KEY", "").strip()
TOOL = "drugmechdb-ai-curation"
EMAIL = os.environ.get("NCBI_CONTACT_EMAIL", "drugmechdb-curation@example.org")

# Per-host throttle. NCBI E-utilities (incl. efetch db=pmc) live on
# eutils.ncbi.nlm.nih.gov: 10 req/s with key, 3 req/s without. PubTator3 lives on
# www.ncbi.nlm.nih.gov: 3 req/s. Europe PMC lives on www.ebi.ac.uk: ~10 req/s.
NCBI_EUTILS_HOST = "eutils.ncbi.nlm.nih.gov"
PUBTATOR_HOST = "www.ncbi.nlm.nih.gov"
EUROPEPMC_HOST = "www.ebi.ac.uk"

_HOST_INTERVALS = {
    NCBI_EUTILS_HOST: 0.11 if API_KEY else 0.34,
    PUBTATOR_HOST: 0.34,
    EUROPEPMC_HOST: 0.10,
}
_DEFAULT_INTERVAL = 0.34
_last_call_by_host: dict[str, float] = {}

# Some environments ship Python without a usable system CA bundle (the managed
# venv is one of them). Prefer certifi's bundle when available so HTTPS
# verification works out of the box; fall back to the system default otherwise.
try:
    import certifi
    _SSL_CONTEXT: ssl.SSLContext = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()

# Statuses worth retrying with exponential backoff (rate-limit + transient server).
_RETRY_STATUS = {429, 500, 502, 503, 504}

PMID_RE = re.compile(r"^PMID:(\d+)$")
PLAIN_PMID_RE = re.compile(r"^\d+$")


def _host_of(url: str) -> str:
    return urllib.parse.urlparse(url).netloc.lower()


def _throttle(host: str) -> None:
    interval = _HOST_INTERVALS.get(host, _DEFAULT_INTERVAL)
    last = _last_call_by_host.get(host, 0.0)
    delta = time.monotonic() - last
    if delta < interval:
        time.sleep(interval - delta)
    _last_call_by_host[host] = time.monotonic()


def _http_get(url: str, *, accept: str | None = None, max_retries: int = 3) -> bytes:
    host = _host_of(url)
    headers = {"User-Agent": f"{TOOL} ({EMAIL})"}
    if accept:
        headers["Accept"] = accept
    attempt = 0
    while True:
        _throttle(host)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=60, context=_SSL_CONTEXT) as resp:
                return resp.read()
        except urllib.error.HTTPError as e:
            if e.code in _RETRY_STATUS and attempt < max_retries:
                ra = e.headers.get("Retry-After") if e.headers else None
                wait = float(ra) if (ra and ra.isdigit()) else 2.0 ** attempt
                time.sleep(wait)
                attempt += 1
                continue
            raise
        except urllib.error.URLError:
            if attempt < max_retries:
                time.sleep(2.0 ** attempt)
                attempt += 1
                continue
            raise


def _eutils_url(endpoint: str, params: dict) -> str:
    p = dict(params)
    p["tool"] = TOOL
    p["email"] = EMAIL
    if API_KEY:
        p["api_key"] = API_KEY
    return f"{EUTILS_BASE}/{endpoint}?{urllib.parse.urlencode(p)}"


def _normalize_pmid(s: str) -> str:
    """Return the bare numeric PMID for either 'PMID:1234' or '1234'."""
    s = s.strip()
    m = PMID_RE.match(s)
    if m:
        return m.group(1)
    if PLAIN_PMID_RE.match(s):
        return s
    raise ValueError(f"not a PMID: {s!r}")


def _curie(pmid_bare: str) -> str:
    return f"PMID:{pmid_bare}"


def cache_path(pmid_bare: str) -> Path:
    return CACHE_DIR / f"PMID_{pmid_bare}.md"


def cache_is_fresh(path: Path, ttl_days: int = CACHE_TTL_DAYS) -> bool:
    if not path.exists():
        return False
    # Parse fetched_at from frontmatter if present; fall back to mtime.
    try:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            head = text.split("---", 2)[1]
            for line in head.splitlines():
                if line.startswith("fetched_at:"):
                    ts = line.split(":", 1)[1].strip().strip("'\"")
                    parsed = dt.datetime.fromisoformat(ts.rstrip("Z"))
                    age = dt.datetime.now(dt.timezone.utc) - parsed.replace(
                        tzinfo=dt.timezone.utc
                    )
                    return age.days < ttl_days
    except Exception:
        pass
    age = dt.datetime.now() - dt.datetime.fromtimestamp(path.stat().st_mtime)
    return age.days < ttl_days


def _cache_content_type(path: Path) -> str | None:
    """Read `content_type` from a cached reference's frontmatter, or None."""
    if not path.exists():
        return None
    try:
        text = path.read_text(encoding="utf-8")
        if text.startswith("---"):
            head = text.split("---", 2)[1]
            for line in head.splitlines():
                if line.startswith("content_type:"):
                    return line.split(":", 1)[1].strip()
    except Exception:
        pass
    return None


def _yaml_quote(value: str) -> str:
    """Quote per linkml-reference-validator's frontmatter convention."""
    if any(ch in value for ch in "[]{}:,#&*?|<>=!%@`\"'\\") or value != value.strip():
        escaped = value.replace("\\", "\\\\").replace('"', '\\"')
        return f'"{escaped}"'
    if value.lower() in ("true", "false", "yes", "no", "on", "off", "null", "~"):
        return f'"{value}"'
    return value


def _write_cache(
    pmid_bare: str,
    record: dict,
    *,
    content_type: str = "abstract",
    body: str | None = None,
) -> Path:
    """Write a reference cache file.

    `content_type` is recorded in the frontmatter (the validator ignores it, but
    it documents the tier). `body`, if given, overrides record['abstract'] as the
    cached content (used for full text). The literal `## Content` heading MUST be
    preserved — linkml-reference-validator keys body extraction off it.
    """
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    path = cache_path(pmid_bare)
    fetched_at = dt.datetime.now(dt.timezone.utc).isoformat(timespec="seconds")

    lines = ["---"]
    lines.append(f"reference_id: PMID:{pmid_bare}")
    if record.get("title"):
        lines.append(f"title: {_yaml_quote(record['title'])}")
    if record.get("authors"):
        lines.append("authors:")
        for a in record["authors"]:
            lines.append(f"- {_yaml_quote(a)}")
    if record.get("journal"):
        lines.append(f"journal: {_yaml_quote(record['journal'])}")
    if record.get("year"):
        lines.append(f"year: '{record['year']}'")
    if record.get("doi"):
        lines.append(f"doi: {record['doi']}")
    if record.get("pmcid"):
        lines.append(f"pmcid: {record['pmcid']}")
    if record.get("retracted"):
        lines.append("retracted: true")
    if record.get("corrections_in"):
        lines.append("corrections_in:")
        for c in record["corrections_in"]:
            lines.append(f"- {_yaml_quote(c)}")
    if record.get("fulltext_source"):
        lines.append(f"fulltext_source: {record['fulltext_source']}")
    if record.get("license"):
        lines.append(f"license: {_yaml_quote(record['license'])}")
    if record.get("content_hash"):
        lines.append(f"content_hash: {record['content_hash']}")
    lines.append(f"content_type: {content_type}")
    lines.append(f"fetched_at: '{fetched_at}'")
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


def _parse_pubmed_xml(xml_bytes: bytes) -> list[dict]:
    """Parse an esummary/efetch response into per-article records."""
    out: list[dict] = []
    root = ET.fromstring(xml_bytes)
    # efetch with rettype=xml returns PubmedArticleSet/PubmedArticle.
    for article in root.findall(".//PubmedArticle"):
        med = article.find(".//MedlineCitation")
        pmid = (med.findtext("PMID") or "").strip() if med is not None else ""
        rec: dict = {"pmid": pmid}

        # Title
        title_el = article.find(".//Article/ArticleTitle")
        rec["title"] = "".join(title_el.itertext()).strip() if title_el is not None else None

        # Abstract — may be split across multiple AbstractText elements with Label attrs
        abs_parts = []
        for at in article.findall(".//Article/Abstract/AbstractText"):
            label = at.get("Label")
            text = "".join(at.itertext()).strip()
            if label:
                abs_parts.append(f"**{label}:** {text}")
            else:
                abs_parts.append(text)
        rec["abstract"] = "\n\n".join(abs_parts) if abs_parts else None

        # Authors
        authors = []
        for au in article.findall(".//Article/AuthorList/Author"):
            ln = au.findtext("LastName") or ""
            init = au.findtext("Initials") or ""
            coll = au.findtext("CollectiveName")
            if coll:
                authors.append(coll.strip())
            elif ln:
                authors.append((ln + " " + init).strip())
        rec["authors"] = authors

        # Journal + Year
        rec["journal"] = article.findtext(".//Article/Journal/Title")
        rec["year"] = article.findtext(".//Article/Journal/JournalIssue/PubDate/Year") or \
                      article.findtext(".//Article/Journal/JournalIssue/PubDate/MedlineDate")
        if rec["year"]:
            # MedlineDate may be like "2019 Jun-Jul" — keep first 4 digits.
            m = re.match(r"(\d{4})", rec["year"])
            if m:
                rec["year"] = m.group(1)

        # DOI
        for aid in article.findall(".//Article/ELocationID"):
            if aid.get("EIdType") == "doi":
                rec["doi"] = aid.text.strip() if aid.text else None
                break

        # Retraction / errata signal
        history = article.findall(".//CommentsCorrectionsList/CommentsCorrections")
        rec["retracted"] = any(c.get("RefType") == "RetractionIn" for c in history)
        rec["corrections_in"] = [
            (c.findtext("PMID") or c.findtext("RefSource") or "").strip()
            for c in history
            if c.get("RefType") in ("RetractionIn", "CorrectedAndRepublishedIn", "ErratumIn")
        ]
        rec["corrections_in"] = [c for c in rec["corrections_in"] if c]
        out.append(rec)
    return out


def _fetch_pubmed_record(pmid_bare: str) -> dict | None:
    """efetch one PMID from db=pubmed and parse it (no caching)."""
    url = _eutils_url("efetch.fcgi", {
        "db": "pubmed", "id": pmid_bare, "rettype": "xml", "retmode": "xml",
    })
    try:
        xml = _http_get(url)
    except Exception:
        return None
    records = _parse_pubmed_xml(xml)
    return records[0] if records else None


def fetch_one(pmid: str, force: bool = False, offline: bool = False) -> dict:
    """Fetch one PMID abstract. Returns a record dict; writes cache on success."""
    bare = _normalize_pmid(pmid)
    cache_file = cache_path(bare)

    if not force and cache_is_fresh(cache_file):
        return {"pmid": bare, "cached": True, "path": str(cache_file)}

    # Monotonic: an abstract fetch must never downgrade a fresh full_text cache
    # (another edge may depend on a full-text snippet).
    if cache_is_fresh(cache_file) and _cache_content_type(cache_file) == "full_text":
        return {"pmid": bare, "cached": True, "path": str(cache_file),
                "content_type": "full_text", "note": "kept full_text (no downgrade)"}

    if offline:
        if cache_file.exists():
            return {"pmid": bare, "cached": True, "stale": True, "path": str(cache_file)}
        return {"pmid": bare, "error": "offline and not cached"}

    record = _fetch_pubmed_record(bare)
    if record is None:
        return {"pmid": bare, "error": "fetch failed or no record returned by PubMed"}
    if not record.get("abstract"):
        # PRD §5.1.2: paywalled / no-abstract — surface but don't write cache
        # (so future runs retry; downstream agent records evidence_source OTHER).
        return {"pmid": bare, "error": "no abstract available", "title": record.get("title")}
    written = _write_cache(bare, record)
    return {"pmid": bare, "cached": False, "path": str(written), "retracted": record.get("retracted", False)}


# ---------------------------------------------------------------------------
# Full-text tier: probe availability, fetch open-access full text, normalize.
# ---------------------------------------------------------------------------

def _europepmc_lookup(pmid_bare: str) -> dict | None:
    """Europe PMC core search by PMID — returns the result dict (pmcid, OA flags)."""
    q = urllib.parse.quote(f"EXT_ID:{pmid_bare} AND SRC:MED")
    url = f"{EUROPEPMC_BASE}/search?query={q}&resultType=core&format=json"
    # Let network errors propagate so callers can distinguish them from a genuine
    # "no result" (None) — an SSL/timeout must not be read as "not open-access".
    data = json.loads(_http_get(url, accept="application/json"))
    results = (data.get("resultList") or {}).get("result") or []
    return results[0] if results else None


def probe(pmid: str) -> dict:
    """Is open-access full text legally available? One metadata call, no body."""
    bare = _normalize_pmid(pmid)
    try:
        rec = _europepmc_lookup(bare)
    except Exception as e:
        # Network/SSL error — unknown, NOT a negative. Caller should retry rather
        # than conclude "no full text".
        return {"pmid": bare, "fulltext_available": False, "best_source": None,
                "pmcid": None, "is_open_access": False, "license": None,
                "error": f"lookup failed: {e}"}
    if not rec:
        return {"pmid": bare, "fulltext_available": False, "best_source": None,
                "pmcid": None, "is_open_access": False, "license": None,
                "note": "not found in Europe PMC"}
    pmcid = rec.get("pmcid")
    is_oa = rec.get("isOpenAccess") == "Y"
    in_epmc = rec.get("inEPMC") == "Y"
    # We COMMIT the fetched body, so require the redistribution-permissive
    # PMC open-access subset (isOpenAccess=Y) — not merely free-to-read.
    available = bool(pmcid) and is_oa
    return {
        "pmid": bare,
        "fulltext_available": available,
        "best_source": "europepmc" if available else None,
        "pmcid": pmcid,
        "is_open_access": is_oa,
        "in_epmc": in_epmc,
        "license": rec.get("license"),
        "doi": rec.get("doi"),
    }


def _sanitize_xml(xml_bytes: bytes) -> bytes:
    """Make JATS/BioC XML safe for ElementTree: drop DOCTYPE + neutralize any
    non-standard named entity (&alpha; &mdash; ...) to a space. Internal
    consistency is preserved because the agent snippets from the SAME cached body.
    """
    text = xml_bytes.decode("utf-8", errors="replace")
    text = re.sub(r"<!DOCTYPE[^>\[]*(\[[^\]]*\])?\s*>", "", text, flags=re.DOTALL)
    text = re.sub(
        r"&(?!amp;|lt;|gt;|quot;|apos;|#\d+;|#x[0-9A-Fa-f]+;)[A-Za-z][A-Za-z0-9]*;",
        " ",
        text,
    )
    return text.encode("utf-8")


def _localname(tag: str) -> str:
    return tag.rsplit("}", 1)[-1] if "}" in tag else tag


# JATS subtrees that are not prose (citations, metadata, raw table grids).
_JATS_DROP_TAGS = {
    "ref-list", "back", "front", "table", "fn-group", "fn",
    "floats-group", "table-wrap-foot", "object-id", "ack",
}
# Inline elements whose text content is a marker, not prose.
_JATS_DROP_INLINE = {"xref", "label"}
# Block-level elements we capture as separate prose blocks.
_JATS_BLOCK_TAGS = {"p", "title", "caption", "list-item", "disp-quote"}


def _jats_inline_text(el) -> str:
    """Flatten an element to inline prose: drop citation/footnote markers, keep
    sub/sup inline with no separator (H<sub>2</sub>O -> H2O)."""
    parts: list[str] = []
    if el.text:
        parts.append(el.text)
    for child in el:
        cname = _localname(child.tag)
        if cname not in _JATS_DROP_INLINE and cname not in _JATS_DROP_TAGS:
            parts.append(_jats_inline_text(child))
        if child.tail:
            parts.append(child.tail)
    return "".join(parts)


def _jats_collect_blocks(el, out: list[str]) -> None:
    name = _localname(el.tag)
    if name in _JATS_DROP_TAGS:
        return
    if name in _JATS_BLOCK_TAGS:
        text = _jats_inline_text(el).strip()
        if text:
            out.append(text)
        return
    for child in el:
        _jats_collect_blocks(child, out)


def _post_normalize(text: str) -> str:
    # De-hyphenate soft line-wrap hyphens: "cyclo-\noxygenase" -> "cyclooxygenase".
    text = re.sub(r"(\w)-\s*\n\s*([a-z])", r"\1\2", text)
    text = text.replace("\xa0", " ")
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    text = "\n".join(line.strip() for line in text.split("\n"))
    return text.strip()


def normalize_jats(xml_bytes: bytes) -> str:
    """JATS full-text XML -> flattened prose body (abstract excluded; it is
    prepended separately from the canonical PubMed record)."""
    root = ET.fromstring(_sanitize_xml(xml_bytes))
    blocks: list[str] = []
    _jats_collect_blocks(root, blocks)
    return _post_normalize("\n\n".join(blocks))


def normalize_bioc(xml_bytes: bytes) -> str:
    """PubTator3 BioC XML -> flattened prose body. Each <passage>/<text> is
    already plain prose; drop reference and raw-table passages."""
    root = ET.fromstring(_sanitize_xml(xml_bytes))
    blocks: list[str] = []
    for passage in root.iter("passage"):
        sectype = ""
        for infon in passage.findall("infon"):
            if infon.get("key") in ("section_type", "type"):
                sectype = (infon.text or "").upper()
        if sectype in ("REF", "REFERENCE", "TABLE"):
            continue
        txt = passage.findtext("text")
        if txt and txt.strip():
            blocks.append(txt.strip())
    return _post_normalize("\n\n".join(blocks))


def _fetch_jats_europepmc(pmcid: str) -> str | None:
    # Endpoint is /{PMCID}/fullTextXML — the PMCID already carries its "PMC" prefix,
    # so there is no separate /PMC/ source segment (that form 404s).
    url = f"{EUROPEPMC_BASE}/{pmcid}/fullTextXML"
    try:
        return normalize_jats(_http_get(url, accept="application/xml"))
    except Exception:
        return None


def _fetch_pubtator3(pmid_bare: str) -> str | None:
    url = f"{PUBTATOR_BASE}/publications/export/biocxml?pmids={pmid_bare}&full=true"
    try:
        return normalize_bioc(_http_get(url, accept="application/xml"))
    except Exception:
        return None


def _fetch_efetch_pmc(pmcid: str) -> str | None:
    numeric = pmcid.replace("PMC", "")
    url = _eutils_url("efetch.fcgi", {
        "db": "pmc", "id": numeric, "rettype": "xml", "retmode": "xml",
    })
    try:
        return normalize_jats(_http_get(url))
    except Exception:
        return None


def _assemble_fulltext(pmid_bare: str) -> dict:
    """Probe + fetch + normalize open-access full text for one PMID, IN MEMORY.

    Does NOT touch the cache — both the cache-writing path (`fetch_fulltext_one`)
    and the no-write critic path (`fetch_fulltext_text`) build on this. The PubMed
    abstract is prepended, separated from the body by FULLTEXT_MARKER, so the cache
    file supersets the abstract tier (prior abstract-grounded snippets keep
    validating) and the abstract can be cleanly recovered on strip.
    Precedence: Europe PMC -> PubTator3 -> efetch-pmc. Returns a dict with
    `body`/`source`/`license`/`pmcid`/`meta`/`content_hash`, or `{'error': ...}`.
    """
    pr = probe(pmid_bare)
    if pr.get("error"):
        return {"error": f"probe failed: {pr['error']}"}
    if not pr.get("fulltext_available"):
        return {"error": "no open-access full text available",
                "pmcid": pr.get("pmcid"), "is_open_access": pr.get("is_open_access")}

    pmcid = pr.get("pmcid")
    body = None
    source = None
    if pmcid:
        body = _fetch_jats_europepmc(pmcid)
        source = "europepmc" if body else None
    if not body:
        body = _fetch_pubtator3(pmid_bare)
        source = "pubtator3" if body else None
    if not body and pmcid:
        body = _fetch_efetch_pmc(pmcid)
        source = "efetch_pmc" if body else None

    if not body or len(body) < 200:
        return {"error": "full-text fetch returned no usable body", "pmcid": pmcid}

    meta = _fetch_pubmed_record(pmid_bare) or {"pmid": pmid_bare}
    abstract = meta.get("abstract")
    full_body = (abstract + "\n\n" + FULLTEXT_MARKER + "\n\n" + body) if abstract else body
    return {
        "body": full_body,
        "fulltext_only": body,
        "abstract": abstract,
        "source": source,
        "license": pr.get("license"),
        "pmcid": pmcid,
        "meta": meta,
        "content_hash": hashlib.sha256(full_body.encode("utf-8")).hexdigest()[:16],
    }


def fetch_fulltext_one(pmid: str, force: bool = False, offline: bool = False) -> dict:
    """Escalate to open-access full text. Writes an in-place full_text cache with
    the PubMed abstract prepended. Precedence: Europe PMC -> PubTator3 -> efetch-pmc."""
    bare = _normalize_pmid(pmid)
    cache_file = cache_path(bare)

    if not force and cache_is_fresh(cache_file) and _cache_content_type(cache_file) == "full_text":
        return {"pmid": bare, "cached": True, "path": str(cache_file), "content_type": "full_text"}

    if offline:
        if cache_file.exists():
            return {"pmid": bare, "cached": True, "stale": True, "path": str(cache_file)}
        return {"pmid": bare, "error": "offline and not cached"}

    asm = _assemble_fulltext(bare)
    if asm.get("error"):
        return {"pmid": bare, **{k: asm[k] for k in ("error", "pmcid", "is_open_access") if k in asm}}

    meta = asm["meta"]
    meta["fulltext_source"] = asm["source"]
    meta["license"] = asm["license"]
    meta["content_hash"] = asm["content_hash"]
    if asm.get("pmcid"):
        meta["pmcid"] = asm["pmcid"]

    written = _write_cache(bare, meta, content_type="full_text", body=asm["body"])
    return {"pmid": bare, "cached": False, "path": str(written),
            "content_type": "full_text", "fulltext_source": asm["source"],
            "license": asm["license"], "retracted": meta.get("retracted", False)}


# ---------------------------------------------------------------------------
# In-memory readers (NO cache write) — for the semantic critic, whose independent
# reading must never land in the committed references_cache/ (it would bias the
# curator and bloat the repo). These return text to the caller and persist nothing.
# ---------------------------------------------------------------------------

def fetch_abstract_text(pmid: str) -> dict:
    """In-memory PubMed abstract for one PMID. NEVER writes the cache."""
    bare = _normalize_pmid(pmid)
    rec = _fetch_pubmed_record(bare)
    if rec is None:
        return {"pmid": bare, "error": "fetch failed or no record returned by PubMed"}
    return {"pmid": bare, "title": rec.get("title"), "abstract": rec.get("abstract"),
            "journal": rec.get("journal"), "year": rec.get("year"),
            "authors": rec.get("authors"), "doi": rec.get("doi"),
            "retracted": rec.get("retracted", False)}


def fetch_fulltext_text(pmid: str) -> dict:
    """In-memory open-access full text for one PMID. NEVER writes the cache."""
    bare = _normalize_pmid(pmid)
    asm = _assemble_fulltext(bare)
    if asm.get("error"):
        return {"pmid": bare, "error": asm["error"], "pmcid": asm.get("pmcid")}
    meta = asm.get("meta") or {}
    return {"pmid": bare, "title": meta.get("title"), "body": asm["body"],
            "source": asm["source"], "license": asm["license"],
            "retracted": meta.get("retracted", False)}


# ---------------------------------------------------------------------------
# strip-fulltext: revert a full_text cache to abstract-only, KEEPING metadata.
# Run before opening a PR so the committed corpus never carries full-text bodies
# (verbatim is enforced once at curation; CI re-checks the source-free layers).
# ---------------------------------------------------------------------------

def _parse_frontmatter(path: Path) -> dict:
    """Parse the YAML frontmatter block of a cache file into a dict."""
    try:
        text = path.read_text(encoding="utf-8")
    except Exception:
        return {}
    if not text.startswith("---"):
        return {}
    try:
        return yaml.safe_load(text.split("---", 2)[1]) or {}
    except Exception:
        return {}


def strip_fulltext_one(pmid: str, *, offline: bool = False) -> dict:
    """Revert one full_text cache file to abstract-only.

    Drops everything from FULLTEXT_MARKER onward plus the full-text-only metadata
    (fulltext_source, license, content_hash) while preserving title/authors/journal/
    year/doi/pmcid/retraction. No-op for abstract-only (or missing) files. For legacy
    full_text files written before the marker existed, the abstract is recovered by
    re-fetching the PubMed record (skipped offline)."""
    bare = _normalize_pmid(pmid)
    path = cache_path(bare)
    if not path.exists():
        return {"pmid": bare, "skipped": "not cached"}

    fm = _parse_frontmatter(path)
    if fm.get("content_type") != "full_text":
        return {"pmid": bare, "skipped": "not full_text"}

    text = path.read_text(encoding="utf-8")
    body = text.split("## Content", 1)[1].strip() if "## Content" in text else ""
    if FULLTEXT_MARKER in body:
        abstract = body.split(FULLTEXT_MARKER, 1)[0].strip()
    else:
        # Legacy full_text with no marker: recover the abstract from PubMed.
        if offline:
            return {"pmid": bare, "skipped": "legacy full_text, no marker, offline — left as-is"}
        rec = _fetch_pubmed_record(bare)
        abstract = (rec or {}).get("abstract") or ""

    record = {
        "title": fm.get("title"), "authors": fm.get("authors"),
        "journal": fm.get("journal"), "year": fm.get("year"),
        "doi": fm.get("doi"), "pmcid": fm.get("pmcid"),
        "retracted": fm.get("retracted"), "corrections_in": fm.get("corrections_in"),
        "abstract": abstract,
    }
    _write_cache(bare, record, content_type="abstract", body=abstract or None)
    return {"pmid": bare, "stripped": True, "path": str(path),
            "had_abstract": bool(abstract)}


def strip_all_fulltext(*, offline: bool = False) -> list[dict]:
    """Strip every full_text cache file in references_cache/ to abstract-only."""
    out = []
    for f in sorted(CACHE_DIR.glob("PMID_*.md")):
        if _cache_content_type(f) == "full_text":
            bare = f.stem.replace("PMID_", "")
            out.append(strip_fulltext_one(bare, offline=offline))
    return out


def search(query: str, retmax: int = 20) -> list[str]:
    """Return a list of bare PMIDs matching the query, max retmax."""
    url = _eutils_url("esearch.fcgi", {
        "db": "pubmed", "term": query, "retmax": retmax, "retmode": "json",
    })
    try:
        data = json.loads(_http_get(url))
    except Exception as e:
        print(f"search failed: {e}", file=sys.stderr)
        return []
    return data.get("esearchresult", {}).get("idlist", [])


def info(pmid: str) -> dict:
    bare = _normalize_pmid(pmid)
    cache_file = cache_path(bare)
    if not cache_file.exists():
        return {"pmid": bare, "cached": False}
    return {
        "pmid": bare, "cached": True,
        "path": str(cache_file),
        "fresh": cache_is_fresh(cache_file),
        "content_type": _cache_content_type(cache_file),
        "size_bytes": cache_file.stat().st_size,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="cmd", required=True)

    p_search = sub.add_parser("search", help="esearch — return PMIDs matching a query")
    p_search.add_argument("query", help="PubMed search expression")
    p_search.add_argument("--max", type=int, default=20, dest="retmax")

    p_fetch = sub.add_parser("fetch", help="efetch — pull abstract(s) and cache")
    p_fetch.add_argument("pmids", nargs="+", help="One or more PMIDs (PMID:nnn or nnn)")
    p_fetch.add_argument("--force", action="store_true", help="Bypass cache freshness check")
    p_fetch.add_argument("--offline", action="store_true", help="Use cache only; never hit the network")
    p_fetch.add_argument("--fulltext", action="store_true",
                         help="Escalate to open-access full text (probe first; abstract fallback)")
    p_fetch.add_argument("--max-fulltext", type=int, default=5, dest="max_fulltext",
                         help="Cap full-text escalations this invocation (rest fetch abstract)")
    p_fetch.add_argument("--json", action="store_true", help="Emit machine-readable JSON")

    p_probe = sub.add_parser("probe", help="Is open-access full text available? (no body download)")
    p_probe.add_argument("pmid")
    p_probe.add_argument("--json", action="store_true")

    p_info = sub.add_parser("info", help="Show cache state for a PMID (no network)")
    p_info.add_argument("pmid")
    p_info.add_argument("--json", action="store_true")

    p_strip = sub.add_parser(
        "strip-fulltext",
        help="Revert full_text cache(s) to abstract-only, keeping metadata (run pre-PR)")
    p_strip.add_argument("pmids", nargs="*", help="PMIDs to strip; omit and pass --all for every full_text file")
    p_strip.add_argument("--all", action="store_true", dest="all_ft",
                         help="Strip every full_text file in references_cache/")
    p_strip.add_argument("--offline", action="store_true",
                         help="Don't re-fetch to recover abstracts for marker-less legacy files")
    p_strip.add_argument("--json", action="store_true")

    args = parser.parse_args()

    if args.cmd == "search":
        ids = search(args.query, retmax=args.retmax)
        for pid in ids:
            print(_curie(pid))
        return 0 if ids else 1

    if args.cmd == "fetch":
        results = []
        ft_used = 0
        for p in args.pmids:
            if args.fulltext and ft_used < args.max_fulltext:
                r = fetch_fulltext_one(p, force=args.force, offline=args.offline)
                ft_used += 1
            else:
                r = fetch_one(p, force=args.force, offline=args.offline)
            results.append(r)
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                tag = "ERROR" if r.get("error") else ("CACHED" if r.get("cached") else "FETCHED")
                bits = [f"{tag} PMID:{r['pmid']}"]
                if r.get("error"):
                    bits.append(r["error"])
                if r.get("content_type") == "full_text":
                    bits.append(f"[full_text:{r.get('fulltext_source', '?')}]")
                if r.get("retracted"):
                    bits.append("[RETRACTED]")
                if r.get("path"):
                    bits.append(r["path"])
                print("  ".join(bits))
        return 0 if all(not r.get("error") for r in results) else 1

    if args.cmd == "probe":
        out = probe(args.pmid)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(out)
        return 0 if out.get("fulltext_available") else 1

    if args.cmd == "info":
        out = info(args.pmid)
        if args.json:
            print(json.dumps(out, indent=2))
        else:
            print(out)
        return 0

    if args.cmd == "strip-fulltext":
        if args.all_ft:
            results = strip_all_fulltext(offline=args.offline)
        elif args.pmids:
            results = [strip_fulltext_one(p, offline=args.offline) for p in args.pmids]
        else:
            parser.error("strip-fulltext needs PMIDs or --all")
        if args.json:
            print(json.dumps(results, indent=2))
        else:
            for r in results:
                if r.get("stripped"):
                    print(f"STRIPPED PMID:{r['pmid']}  (abstract kept: {r['had_abstract']})")
                else:
                    print(f"SKIPPED  PMID:{r['pmid']}  ({r.get('skipped')})")
        return 0

    parser.error("unknown cmd")


if __name__ == "__main__":
    sys.exit(main())
