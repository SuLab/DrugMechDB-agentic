"""
Grounding tools for the LLM judge — independent, deterministic, NO LLM.

These are the *external referents* that make verification reliable (framework §6):
the judge must cite one of these, or abstain. Two tools are provided, covering the
two highest-value grounding tiers:

  - read_source        — fetch the cited PMID's text (abstract or full text) via the
                         pubmed_fetch wrapper and locate the snippet's surrounding
                         context. Tier 3 (entailment over the cited text); works for any
                         edge that has a snippet.
  - chembl_get_mechanism — ChEMBL REST drug->target->action records. Tier 1: an
                         independent, expert-curated oracle for the Drug->target edge
                         that begins almost every DrugMechDB path.

All network calls reuse pubmed_fetch's certifi-backed, throttled, retrying _http_get.
Results are cached on disk under quality_cache/grounding/. Tools NEVER raise — on any
failure they return an informative string so the model can drop a tier or abstain.
"""

from __future__ import annotations

import importlib.util
import json
import re
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
REPO = HERE.parent.parent.parent  # scripts/quality/judge -> repo root
CACHE_DIR = REPO / "quality_cache" / "grounding"

# Reuse the pubmed_fetch wrapper (certifi HTTP, throttle, cache) without making
# scripts/ a package.
_pf_spec = importlib.util.spec_from_file_location("pubmed_fetch", REPO / "scripts" / "pubmed_fetch.py")
pf = importlib.util.module_from_spec(_pf_spec)
_pf_spec.loader.exec_module(pf)

# The Layer-4 matcher's normalization — so "snippet present?" here means exactly
# what Layer 4 means by it.
try:
    from linkml_reference_validator.validation.supporting_text_validator import (
        SupportingTextValidator,
    )
    _normalize = SupportingTextValidator.normalize_text
except Exception:  # pragma: no cover - validator always present in this env
    def _normalize(t: str) -> str:
        return re.sub(r"\s+", " ", re.sub(r"[^\w\s]", " ", (t or "").lower())).strip()

CHEMBL_BASE = "https://www.ebi.ac.uk/chembl/api/data"
_SLUG_RE = re.compile(r"[^a-z0-9]+")


def _slug(text: str) -> str:
    return _SLUG_RE.sub("_", (text or "").lower()).strip("_") or "x"


def _cache_get(key: str) -> dict | None:
    p = CACHE_DIR / f"{key}.json"
    if p.exists():
        try:
            return json.loads(p.read_text())
        except Exception:
            return None
    return None


def _cache_put(key: str, value: dict) -> None:
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    (CACHE_DIR / f"{key}.json").write_text(json.dumps(value, indent=2))


# ── read_source ───────────────────────────────────────────────────────────────

def read_source(reference: str, snippet: str | None = None, window: int = 400,
                allow_network: bool = True) -> str:
    """Return the cited source's content + whether `snippet` is verbatim-present
    (under Layer-4 normalization) and its surrounding context.

    `allow_network=False` makes this a pure read of the committed references_cache/
    (no fetch_one fallback, which would WRITE the cache). The semantic critic uses
    this mode to verify the curator's own snippet without ever writing the curator's
    cache — its independent reading goes through the in-memory tools below instead."""
    try:
        bare = pf._normalize_pmid(reference)
    except Exception:
        return f"read_source: '{reference}' is not a PMID; cannot ground."

    cache_file = pf.cache_path(bare)
    if not cache_file.exists():
        if not allow_network:
            return (f"read_source: PMID:{bare} is not in the committed references_cache/. "
                    "The critic does not fetch into the curator's cache; use read_abstract / "
                    "read_fulltext for independent reading instead.")
        # Best-effort fetch (abstract tier). May fail offline / paywalled.
        res = pf.fetch_one(reference)
        if res.get("error") and not cache_file.exists():
            return (f"read_source: PMID:{bare} could not be retrieved ({res.get('error')}). "
                    "No source text available to ground this snippet.")

    text = cache_file.read_text(encoding="utf-8")
    parts = text.split("## Content", 1)
    frontmatter = parts[0]
    body = parts[1].strip() if len(parts) > 1 else text
    ctype = pf._cache_content_type(cache_file) or "unknown"
    title_m = re.search(r"^title:\s*(.+)$", frontmatter, re.M)
    title = title_m.group(1).strip().strip('"') if title_m else "(title unknown)"

    out = [f"SOURCE PMID:{bare}  (content_type={ctype})", f"Title: {title}"]
    if snippet:
        nbody, nsnip = _normalize(body), _normalize(snippet)
        present = nsnip in nbody
        out.append(f"Snippet verbatim-present (Layer-4 normalization): {present}")
        if present:
            # Locate an approximate raw context window around the match.
            idx = _approx_locate(body, snippet)
            if idx is not None:
                lo, hi = max(0, idx - window), min(len(body), idx + len(snippet) + window)
                out.append("Surrounding context (raw):")
                out.append(("..." if lo else "") + body[lo:hi].strip() + ("..." if hi < len(body) else ""))
        else:
            out.append("Surrounding context: snippet not located verbatim; first 600 chars of source body:")
            out.append(body[:600].strip())
    else:
        out.append("Source body (first 1200 chars):")
        out.append(body[:1200].strip())
    return "\n".join(out)


def _approx_locate(body: str, snippet: str) -> int | None:
    """Best-effort raw index of the snippet's start, tolerating whitespace/case."""
    # Try first 5 alnum tokens of the snippet as an anchor in a normalized view.
    toks = re.findall(r"\w+", snippet.lower())[:5]
    if not toks:
        return None
    anchor = toks[0]
    low = body.lower()
    start = 0
    while True:
        i = low.find(anchor, start)
        if i == -1:
            return None
        # accept first hit; good enough for a context window
        return i


# ── chembl_get_mechanism ────────────────────────────────────────────────────

def chembl_get_mechanism(drug: str) -> str:
    """ChEMBL drug->target->action records for `drug` (name or synonym).

    Tier-1 independent grounding for the Drug->target edge. Cached; never raises.
    """
    key = f"chembl_{_slug(drug)}"
    cached = _cache_get(key)
    if cached is not None:
        return cached["text"]

    text = _chembl_lookup(drug)
    _cache_put(key, {"drug": drug, "text": text})
    return text


def _chembl_get_json(url: str) -> dict | None:
    try:
        return json.loads(pf._http_get(url, accept="application/json"))
    except Exception:
        return None


def _mechanisms_for(chembl_id: str) -> list:
    mech = _chembl_get_json(f"{CHEMBL_BASE}/mechanism?molecule_chembl_id={chembl_id}&format=json")
    return (mech or {}).get("mechanisms") or []


def _chembl_lookup(drug: str) -> str:
    q = urllib.parse.quote(drug)
    search = _chembl_get_json(f"{CHEMBL_BASE}/molecule/search?q={q}&format=json&limit=6")
    molecules = (search or {}).get("molecules") or []
    if not molecules:
        return (f"ChEMBL: no molecule found for '{drug}'. This edge cannot be grounded via "
                "ChEMBL (tier 1) — fall back to reading the cited source, or abstain.")

    # ChEMBL often files the mechanism under a salt/active form rather than the
    # parent (e.g. tamoxifen's MoA lives on CHEMBL786 'tamoxifen citrate', not
    # CHEMBL83). Try the top search hits plus the parent/active forms of the best
    # hit, and use the first molecule that actually carries mechanism records.
    primary = molecules[0]
    pref = primary.get("pref_name") or drug
    candidates: list[str] = []
    for m in molecules:
        cid = m.get("molecule_chembl_id")
        if cid and cid not in candidates:
            candidates.append(cid)
    hier = primary.get("molecule_hierarchy") or {}
    for extra in (hier.get("parent_chembl_id"), hier.get("active_chembl_id")):
        if extra and extra not in candidates:
            candidates.append(extra)

    chembl_id, mechanisms = None, []
    for cid in candidates[:8]:
        mm = _mechanisms_for(cid)
        if mm:
            chembl_id, mechanisms = cid, mm
            break

    if not mechanisms:
        return (f"ChEMBL: '{drug}' resolves to {primary.get('molecule_chembl_id')} ({pref}) "
                f"but no curated mechanism record was found across {candidates[:8]}. "
                "Drop to tier 2/3 grounding or abstain.")

    via = f" via {chembl_id}" if chembl_id != primary.get("molecule_chembl_id") else ""
    lines = [f"ChEMBL mechanism records for '{drug}' = {primary.get('molecule_chembl_id')} ({pref}){via}:"]
    for m in mechanisms[:6]:
        target_id = m.get("target_chembl_id")
        target_name = _chembl_target_name(target_id) if target_id else None
        lines.append(
            f"  - action_type={m.get('action_type')!r}; "
            f"target={target_name or target_id or 'n/a'}; "
            f"direct_interaction={m.get('direct_interaction')}; "
            f"moa={m.get('mechanism_of_action')!r}"
        )
    lines.append("(ChEMBL is an independent, expert-curated oracle — cite it as grounding.)")
    return "\n".join(lines)


def _chembl_target_name(target_chembl_id: str) -> str | None:
    cached = _cache_get(f"target_{target_chembl_id}")
    if cached is not None:
        return cached.get("pref_name")
    data = _chembl_get_json(f"{CHEMBL_BASE}/target/{target_chembl_id}?format=json")
    pref = (data or {}).get("pref_name")
    _cache_put(f"target_{target_chembl_id}", {"pref_name": pref})
    return pref


# ── independent in-memory reading (for the semantic critic) ─────────────────────
#
# These let the critic widen its knowledge BEYOND the curator's cited papers, from
# real retrieved text (never its own training). Crucially they read IN MEMORY and
# NEVER write references_cache/ — so the critic can never bias or pollute the
# curator's committed evidence base. Nothing here is persisted to the repo.

def search_pubmed(query: str, max_results: int = 10) -> str:
    """PubMed search for papers the curator may not have cited. Returns PMIDs only;
    read the relevant ones with read_abstract / read_fulltext. Writes nothing."""
    try:
        ids = pf.search(query, retmax=max_results)
    except Exception as e:
        return f"search_pubmed: lookup failed ({e}); try a different query or abstain."
    if not ids:
        return f"search_pubmed: no results for {query!r}."
    return (f"PubMed results for {query!r} ({len(ids)}): "
            + ", ".join(f"PMID:{i}" for i in ids)
            + "\nRead the ones relevant to the edge under review with read_abstract / read_fulltext.")


def read_abstract(reference: str) -> str:
    """In-memory PubMed abstract for any PMID (independent of the curator's cache).
    Use to corroborate or challenge an edge with evidence the curator did not cite."""
    try:
        bare = pf._normalize_pmid(reference)
    except Exception:
        return f"read_abstract: '{reference}' is not a PMID."
    r = pf.fetch_abstract_text(bare)
    if r.get("error"):
        return f"read_abstract PMID:{bare}: {r['error']}"
    head = f"PMID:{bare}  {r.get('title')}  ({r.get('journal')}, {r.get('year')})"
    if r.get("retracted"):
        head += "  [RETRACTED — do not rely on this]"
    return head + "\n\n" + (r.get("abstract") or "(no abstract available)")


def read_fulltext(reference: str, max_chars: int = 6000) -> str:
    """In-memory open-access full text for any PMID (independent of the curator's
    cache). Use when an abstract is insufficient to judge the edge. Writes nothing."""
    try:
        bare = pf._normalize_pmid(reference)
    except Exception:
        return f"read_fulltext: '{reference}' is not a PMID."
    r = pf.fetch_fulltext_text(bare)
    if r.get("error"):
        return f"read_fulltext PMID:{bare}: {r['error']} (fall back to read_abstract or abstain)."
    body = r.get("body") or ""
    tail = "" if len(body) <= max_chars else f"\n[...truncated at {max_chars} chars...]"
    flag = "  [RETRACTED — do not rely on this]" if r.get("retracted") else ""
    return f"PMID:{bare}  {r.get('title')}  (full text via {r.get('source')}){flag}\n\n" + body[:max_chars] + tail


# ── tool registry helpers (consumed by runner.py) ──────────────────────────────

def default_tools() -> list:
    """Return the judge's grounding tools as backend-agnostic Tool specs."""
    from .backends import Tool
    return [
        Tool(
            name="read_source",
            description=(
                "Fetch the cited source (by PMID) and check whether a snippet appears "
                "verbatim in it (Layer-4 normalization), returning the surrounding context. "
                "Use this to confirm a snippet exists and to read the sentence around it for "
                "subject/object/polarity/scope checks."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "PMID curie, e.g. 'PMID:12345678'"},
                    "snippet": {"type": "string", "description": "the snippet text to locate (optional)"},
                },
                "required": ["reference"],
            },
            fn=lambda a: read_source(a.get("reference", ""), a.get("snippet")),
        ),
        Tool(
            name="chembl_get_mechanism",
            description=(
                "Look up ChEMBL's expert-curated drug->target->action mechanism records for a "
                "drug name. The strongest independent grounding for a Drug->protein-target edge. "
                "Returns action_type, target name, and mechanism-of-action text."
            ),
            input_schema={
                "type": "object",
                "properties": {"drug": {"type": "string", "description": "drug name or synonym"}},
                "required": ["drug"],
            },
            fn=lambda a: chembl_get_mechanism(a.get("drug", "")),
        ),
    ]


def critic_tools() -> list:
    """Tool set for the semantic critic (runs after deterministic QC passes).

    Differs from default_tools() in two firewall-critical ways:
      - read_source is READ-ONLY (allow_network=False): the critic verifies the
        curator's own snippet against the committed cache but never fetches into /
        writes that cache.
      - it adds search_pubmed / read_abstract / read_fulltext, which read IN MEMORY
        and persist nothing — the critic's independent reading can never land in the
        repo or bias the curator. cite-or-abstain still holds: a judgment must rest on
        ChEMBL or on a source the critic actually retrieved here, or it abstains.
    """
    from .backends import Tool
    return [
        Tool(
            name="read_source",
            description=(
                "Read the CURATOR'S cited source (by PMID) from the committed cache and check "
                "whether a snippet is verbatim-present (Layer-4 normalization), with surrounding "
                "context. Read-only: confirms the curator's evidence; does NOT fetch new papers."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "reference": {"type": "string", "description": "PMID curie, e.g. 'PMID:12345678'"},
                    "snippet": {"type": "string", "description": "the snippet text to locate (optional)"},
                },
                "required": ["reference"],
            },
            fn=lambda a: read_source(a.get("reference", ""), a.get("snippet"), allow_network=False),
        ),
        Tool(
            name="chembl_get_mechanism",
            description=(
                "ChEMBL's expert-curated drug->target->action mechanism records for a drug name. "
                "The strongest INDEPENDENT grounding for a Drug->protein-target edge."
            ),
            input_schema={
                "type": "object",
                "properties": {"drug": {"type": "string", "description": "drug name or synonym"}},
                "required": ["drug"],
            },
            fn=lambda a: chembl_get_mechanism(a.get("drug", "")),
        ),
        Tool(
            name="search_pubmed",
            description=(
                "Search PubMed for papers BEYOND the curator's cited set, to corroborate or "
                "challenge an edge or the overall mechanism. Returns PMIDs; read them with "
                "read_abstract / read_fulltext. Reads in memory; writes nothing."
            ),
            input_schema={
                "type": "object",
                "properties": {
                    "query": {"type": "string", "description": "PubMed query string"},
                    "max_results": {"type": "integer", "description": "cap on PMIDs (default 10)"},
                },
                "required": ["query"],
            },
            fn=lambda a: search_pubmed(a.get("query", ""), int(a.get("max_results", 10) or 10)),
        ),
        Tool(
            name="read_abstract",
            description=(
                "Read any PMID's abstract IN MEMORY (independent of the curator's cache). Use to "
                "ground a judgment in evidence the curator did not cite. Writes nothing."
            ),
            input_schema={
                "type": "object",
                "properties": {"reference": {"type": "string", "description": "PMID curie"}},
                "required": ["reference"],
            },
            fn=lambda a: read_abstract(a.get("reference", "")),
        ),
        Tool(
            name="read_fulltext",
            description=(
                "Read any PMID's open-access FULL TEXT in memory (independent of the curator's "
                "cache) when an abstract is insufficient. Writes nothing."
            ),
            input_schema={
                "type": "object",
                "properties": {"reference": {"type": "string", "description": "PMID curie"}},
                "required": ["reference"],
            },
            fn=lambda a: read_fulltext(a.get("reference", "")),
        ),
    ]
