"""Resolution backends — one per identifier authority.

Each backend answers exactly one question: does this CURIE resolve, and what is
its canonical label? Every backend obeys the same contract:

    * return EXISTS / ABSENT / OBSOLETE only when the authority actually
      answered and the answer is unambiguous;
    * raise `LookupError_` for anything else — network failure, timeout, an
      unexpected payload shape, or the ontology itself being unavailable.

The caller turns `LookupError_` into UNRESOLVED. Backends must never convert a
failure to reach the authority into ABSENT; that is the one bug this module
exists to prevent.

Empirically determined "not found" signals (probed 2026-09-13):

    MeSH       200 with an empty JSON object `{ }`
    UniProt    404; and 200 with entryType "Inactive" means deleted/obsolete
    Reactome   404 with a JSON body naming the id
    OLS4       200 with `_embedded.terms` absent or empty — but only
               trustworthy once the ontology itself is confirmed to exist
"""

from __future__ import annotations

import json
import ssl
import time
import urllib.error
import urllib.parse
import urllib.request

from .types import TermResult, TermStatus, LookupError_

USER_AGENT = "DrugMechDB-agentic term-validation (https://github.com/SuLab/DrugMechDB-agentic)"
TIMEOUT = 30

# Same rationale as scripts/pubmed_fetch.py: some environments (the managed venv
# among them) ship Python without a usable system CA bundle, so prefer certifi's.
try:
    import certifi
    _SSL_CONTEXT: ssl.SSLContext = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL_CONTEXT = ssl.create_default_context()

# Courtesy pacing — an audit walks thousands of terms against public APIs that
# are free and unauthenticated. Seconds between calls, per host.
_HOST_INTERVAL = {
    "www.ebi.ac.uk": 0.12,
    "id.nlm.nih.gov": 0.20,
    "rest.uniprot.org": 0.12,
    "reactome.org": 0.20,
}
_DEFAULT_INTERVAL = 0.20
_last_call_by_host: dict[str, float] = {}

_RETRY_STATUS = {429, 500, 502, 503, 504}
_MAX_ATTEMPTS = 3


def _throttle(host: str) -> None:
    interval = _HOST_INTERVAL.get(host, _DEFAULT_INTERVAL)
    last = _last_call_by_host.get(host)
    if last is not None:
        wait = interval - (time.monotonic() - last)
        if wait > 0:
            time.sleep(wait)
    _last_call_by_host[host] = time.monotonic()


def _get_json(url: str, *, timeout: int = TIMEOUT) -> tuple[int, dict | list | None]:
    """GET a URL and parse JSON. Returns (status_code, parsed_or_None).

    A 404 is returned as data (callers treat it as a meaningful "not found"),
    because for these APIs it *is* the answer. Every other transport problem
    raises LookupError_ so it can become UNRESOLVED — never ABSENT.
    """
    host = urllib.parse.urlparse(url).hostname or ""
    req = urllib.request.Request(
        url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})

    last_error: str = "unknown"
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        _throttle(host)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CONTEXT) as resp:
                body = resp.read().decode("utf-8", errors="replace")
                code = resp.getcode()
        except urllib.error.HTTPError as exc:
            if exc.code == 404:
                return 404, None
            last_error = f"HTTP {exc.code} from {url}"
            if exc.code not in _RETRY_STATUS or attempt == _MAX_ATTEMPTS:
                raise LookupError_(last_error) from exc
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_error = f"network error for {url}: {exc}"
            if attempt == _MAX_ATTEMPTS:
                raise LookupError_(last_error) from exc
        else:
            if not body.strip():
                raise LookupError_(f"empty body from {url}")
            try:
                return code, json.loads(body)
            except json.JSONDecodeError as exc:
                raise LookupError_(f"non-JSON body from {url}: {exc}") from exc
        time.sleep(0.5 * (2 ** (attempt - 1)))

    raise LookupError_(last_error)


def local_id(curie: str) -> str:
    return curie.split(":", 1)[1] if ":" in curie else curie


# ── MeSH ────────────────────────────────────────────────────────────────────
def _mesh_confirm(curie: str, ident: str) -> TermResult:
    """Second opinion from the record endpoint, for ids `lookup/details` cannot serve.

    `/mesh/<id>.json` covers Supplementary Concept Records as well as
    descriptors, and still returns a bare `{ }` for an id that does not exist —
    so it can settle absence where the lookup endpoint only reports silence.
    It carries no entry terms, hence the two-step: one call for the common
    descriptor case, a second only when the first comes back empty.
    """
    code, data = _get_json(f"https://id.nlm.nih.gov/mesh/{urllib.parse.quote(ident)}.json")
    if code == 404 or data is None:
        return TermResult(curie, TermStatus.ABSENT, source="mesh")
    if not isinstance(data, dict):
        raise LookupError_(f"unexpected MeSH record payload for {curie}")
    if not data:
        return TermResult(curie, TermStatus.ABSENT, source="mesh")

    label = data.get("label")
    if isinstance(label, dict):
        label = label.get("@value")
    elif isinstance(label, list) and label:
        first = label[0]
        label = first.get("@value") if isinstance(first, dict) else str(first)

    if data.get("http://id.nlm.nih.gov/mesh/vocab#active") is False:
        return TermResult(curie, TermStatus.OBSOLETE, label=label, source="mesh",
                          detail="MeSH record is not active")
    return TermResult(curie, TermStatus.EXISTS, label=label, source="mesh")


def resolve_mesh(curie: str) -> TermResult:
    """NLM MeSH, via the `lookup/details` endpoint.

    Chosen over `/mesh/<id>.json` because one call answers both questions the
    audit asks: an absent id returns `terms: []`, and a present one returns its
    full entry-term list — the preferred term plus every synonym.

    Those entry terms matter more here than anywhere else. MeSH inverts its
    headings ("Arthritis, Rheumatoid") and the descriptor endpoint exposes only
    that inverted form, so comparing record names against it alone flags a large
    fraction of the ~2,500 MeSH nodes for what is a formatting convention.
    "Morphea" is a real entry term for D012594; against the preferred label
    "Scleroderma, Localized" it looks like an error.

    Also handles C-number supplementary concept records (1,438 node occurrences
    in the corpus), which this endpoint serves the same way.

    Known limitation: this endpoint does not expose a deprecation flag, so MeSH
    identifiers are never reported OBSOLETE — only EXISTS or ABSENT.
    """
    ident = local_id(curie)
    code, data = _get_json(
        "https://id.nlm.nih.gov/mesh/lookup/details"
        f"?descriptor={urllib.parse.quote(ident)}")
    if code == 404 or data is None:
        return _mesh_confirm(curie, ident)
    if not isinstance(data, dict):
        raise LookupError_(f"unexpected MeSH payload type {type(data).__name__} for {curie}")

    terms = data.get("terms")
    if terms is None:
        raise LookupError_(f"MeSH response for {curie} has no `terms` key")
    if not terms:
        # `lookup/details` serves DESCRIPTORS. It returns an empty term list —
        # indistinguishable from "no such id" — for most Supplementary Concept
        # Records, and the corpus uses 1,438 of those. Eptifibatide (C086648) is
        # real and comes back empty here. Confirm against the record endpoint
        # before calling anything absent.
        return _mesh_confirm(curie, ident)

    label = None
    synonyms: list[str] = []
    for term in terms:
        if not isinstance(term, dict):
            continue
        text = term.get("label")
        if not isinstance(text, str):
            continue
        if term.get("preferred") and label is None:
            label = text
        else:
            synonyms.append(text)
    if label is None:  # no term flagged preferred; take the first and keep the rest
        label = synonyms.pop(0) if synonyms else None

    return TermResult(curie, TermStatus.EXISTS, label=label, source="mesh",
                      synonyms=tuple(dict.fromkeys(synonyms)))


# ── UniProt ─────────────────────────────────────────────────────────────────
def resolve_uniprot(curie: str) -> TermResult:
    """UniProtKB. 404 means absent; entryType "Inactive" means deleted/merged."""
    acc = local_id(curie)
    url = (f"https://rest.uniprot.org/uniprotkb/{urllib.parse.quote(acc)}.json"
           "?fields=protein_name,accession")
    code, data = _get_json(url)
    if code == 404 or data is None:
        return TermResult(curie, TermStatus.ABSENT, source="uniprot")
    if not isinstance(data, dict):
        raise LookupError_(f"unexpected UniProt payload type {type(data).__name__} for {curie}")

    entry_type = data.get("entryType") or ""
    if entry_type.strip().lower() == "inactive":
        reason = (data.get("inactiveReason") or {})
        why = reason.get("inactiveReasonType") or "inactive"
        return TermResult(curie, TermStatus.OBSOLETE, source="uniprot",
                          detail=f"UniProt entry is inactive ({why})")

    desc = data.get("proteinDescription") or {}
    rec = desc.get("recommendedName") or {}
    full = rec.get("fullName") or {}
    label = full.get("value")
    if label is None:
        submitted = desc.get("submissionNames") or []
        if submitted:
            label = ((submitted[0].get("fullName") or {}).get("value"))

    syns: list[str] = []
    for short in rec.get("shortNames") or []:
        if isinstance(short, dict) and short.get("value"):
            syns.append(short["value"])
    for alt in desc.get("alternativeNames") or []:
        alt_full = (alt or {}).get("fullName") or {}
        if alt_full.get("value"):
            syns.append(alt_full["value"])
        for short in alt.get("shortNames") or []:
            if isinstance(short, dict) and short.get("value"):
                syns.append(short["value"])
    return TermResult(curie, TermStatus.EXISTS, label=label, source="uniprot",
                      synonyms=tuple(dict.fromkeys(syns)))


# ── Reactome ────────────────────────────────────────────────────────────────
def resolve_reactome(curie: str) -> TermResult:
    """Reactome ContentService. Absent stable ids return a clean 404."""
    ident = local_id(curie)
    code, data = _get_json(
        f"https://reactome.org/ContentService/data/query/{urllib.parse.quote(ident)}")
    if code == 404 or data is None:
        return TermResult(curie, TermStatus.ABSENT, source="reactome")
    if not isinstance(data, dict):
        raise LookupError_(f"unexpected Reactome payload type {type(data).__name__} for {curie}")
    return TermResult(curie, TermStatus.EXISTS,
                      label=data.get("displayName"), source="reactome")


# ── OBO via EBI OLS4 ────────────────────────────────────────────────────────
_OLS_ROOT = "https://www.ebi.ac.uk/ols4/api"
_ontology_available: dict[str, bool] = {}


def _ols_ontology_exists(ontology: str) -> bool:
    """Is this ontology actually loaded in OLS4?

    Without this guard an unavailable ontology would make every one of its
    terms look ABSENT — manufacturing thousands of false failures. Cached per
    process; a failure to check raises rather than guessing.
    """
    if ontology in _ontology_available:
        return _ontology_available[ontology]
    code, data = _get_json(f"{_OLS_ROOT}/ontologies/{urllib.parse.quote(ontology)}")
    available = not (code == 404 or data is None)
    _ontology_available[ontology] = available
    return available


def resolve_obo(curie: str, ontology: str) -> TermResult:
    """Resolve an OBO CURIE through OLS4 against a named ontology."""
    if not _ols_ontology_exists(ontology):
        raise LookupError_(f"OLS4 has no ontology {ontology!r}; cannot judge {curie}")

    url = (f"{_OLS_ROOT}/ontologies/{urllib.parse.quote(ontology)}/terms"
           f"?obo_id={urllib.parse.quote(curie)}")
    code, data = _get_json(url)
    if code == 404 or data is None:
        return TermResult(curie, TermStatus.ABSENT, source=f"ols4:{ontology}")
    if not isinstance(data, dict):
        raise LookupError_(f"unexpected OLS4 payload type {type(data).__name__} for {curie}")

    terms = ((data.get("_embedded") or {}).get("terms")) or []
    if not terms:
        return TermResult(curie, TermStatus.ABSENT, source=f"ols4:{ontology}")

    term = terms[0]
    label = term.get("label")
    syns = tuple(s for s in (term.get("synonyms") or []) if isinstance(s, str))
    if term.get("is_obsolete"):
        return TermResult(curie, TermStatus.OBSOLETE, label=label,
                          source=f"ols4:{ontology}", detail="OLS4 reports is_obsolete")
    return TermResult(curie, TermStatus.EXISTS, label=label,
                      source=f"ols4:{ontology}", synonyms=syns)


# ── OAK (preferred when its sqlite adapters are reachable) ──────────────────
_oak_adapters: dict[str, object] = {}
_oak_unavailable: dict[str, str] = {}
"""Adapter strings whose construction already failed, with the reason.

Building an OAK adapter downloads a multi-hundred-MB sqlite database. Retrying
a build that has already failed once would repeat that attempt for every term
in the corpus, so the failure is remembered and short-circuited."""


def resolve_oak(curie: str, adapter_string: str) -> TermResult:
    """Resolve via an OAK adapter (e.g. "sqlite:obo:go").

    This is the project's locked preference — offline, deterministic and
    authoritative. It is attempted first for OBO prefixes and falls back to
    OLS4 when the adapter cannot be built, which is what happens in any
    environment that cannot reach the bbop-sqlite bucket.
    """
    if adapter_string in _oak_unavailable:
        raise LookupError_(
            f"OAK adapter {adapter_string!r} unavailable: {_oak_unavailable[adapter_string]}")

    adapter = _oak_adapters.get(adapter_string)
    if adapter is None:
        try:
            from oaklib import get_adapter
            adapter = get_adapter(adapter_string)
        except Exception as exc:  # adapter construction downloads; many failure modes
            _oak_unavailable[adapter_string] = str(exc)
            raise LookupError_(f"OAK adapter {adapter_string!r} unavailable: {exc}") from exc
        _oak_adapters[adapter_string] = adapter

    try:
        label = adapter.label(curie)
    except Exception as exc:
        raise LookupError_(f"OAK lookup failed for {curie} via {adapter_string}: {exc}") from exc

    if label is None:
        # OAK returns None both for "absent" and for "present but unlabelled".
        # Disambiguate via the entity listing before calling it absent.
        try:
            known = curie in set(adapter.entities())
        except Exception as exc:
            raise LookupError_(
                f"OAK could not confirm absence of {curie} via {adapter_string}: {exc}") from exc
        if not known:
            return TermResult(curie, TermStatus.ABSENT, source=f"oak:{adapter_string}")
    return TermResult(curie, TermStatus.EXISTS, label=label, source=f"oak:{adapter_string}")
