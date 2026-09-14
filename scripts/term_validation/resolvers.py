"""Prefix routing, config loading, and the cached resolution front door.

`conf/oak_config.yaml` is the single source of truth for which prefixes are
validated and how. It existed in the repo before this module did, but nothing
read it. Its own comments define the convention this file implements:

    "sqlite:obo:<name>"  -> an OBO ontology; OAK preferred, OLS4 as fallback
    ""                   -> not OAK's job. Either a non-OBO authority with its
                            own REST validator (MESH / UniProt / Reactome), or
                            a prefix we deliberately do not validate at all.

So an empty adapter string means "skip OAK", NOT "skip validation" — the
distinction the config's coverage notes spell out and that the missing
validate_mesh.py / validate_uniprot.py / validate_reactome.py were meant to
cover.
"""

from __future__ import annotations

from dataclasses import replace
from pathlib import Path

import yaml

from . import backends
from .cache import TermCache
from .types import TermResult, TermStatus, LookupError_

REPO = Path(__file__).resolve().parent.parent.parent
DEFAULT_CONFIG = REPO / "conf" / "oak_config.yaml"

# Non-OBO authorities that carry their own REST validator. Keyed by CURIE prefix
# exactly as it appears in the corpus.
CUSTOM_RESOLVERS = {
    "MESH": backends.resolve_mesh,
    "UniProt": backends.resolve_uniprot,
    "REACT": backends.resolve_reactome,
    "reactome": backends.resolve_reactome,
}

# Legacy prefixes present in the corpus that are not what the authority calls
# itself. The corpus keeps its own spelling (Hard Boundary #3 — no data
# migration); we translate only for the lookup.
#
# This is load-bearing: querying OLS4 with the corpus spelling `taxonomy:10298`
# returns nothing, which would be recorded as ABSENT and invent 166 failures
# out of thin air. Canonicalising first is what stops that.
PREFIX_ALIASES = {
    "taxonomy": "NCBITaxon",
    "reactome": "REACT",
}


def canonical_curie(curie: str) -> str:
    """The form the upstream authority expects, for lookup purposes only."""
    if ":" not in curie:
        return curie
    prefix, rest = curie.split(":", 1)
    return f"{PREFIX_ALIASES[prefix]}:{rest}" if prefix in PREFIX_ALIASES else curie


def load_config(path: Path | str | None = None) -> dict[str, str]:
    """Read conf/oak_config.yaml -> {prefix: adapter_string}."""
    cfg_path = Path(path) if path else DEFAULT_CONFIG
    if not cfg_path.exists():
        raise FileNotFoundError(f"OAK config not found: {cfg_path}")
    doc = yaml.safe_load(cfg_path.read_text()) or {}
    adapters = doc.get("ontology_adapters")
    if not isinstance(adapters, dict):
        raise ValueError(f"{cfg_path} must define a mapping under `ontology_adapters`")
    return {str(k): ("" if v is None else str(v)) for k, v in adapters.items()}


def ontology_name(adapter_string: str) -> str | None:
    """"sqlite:obo:go" -> "go". None when the adapter names no OBO ontology."""
    if adapter_string.startswith("sqlite:obo:"):
        name = adapter_string.split("sqlite:obo:", 1)[1].strip()
        return name or None
    return None


def normalize_label(value: str | None) -> str:
    """Casefold + collapse whitespace, for comparing a record name to a label.

    Deliberately conservative: it only absorbs case and spacing differences.
    Anything more aggressive (stripping punctuation, singularising) would start
    hiding genuine mismatches, which is the opposite of the point.
    """
    if not isinstance(value, str):
        return ""
    return " ".join(value.split()).casefold()


class Registry:
    """Routes a CURIE to a backend, with a write-through cache in front."""

    def __init__(self, config: dict[str, str] | None = None,
                 cache: TermCache | None = None,
                 *, prefer_oak: bool = True, use_cache: bool = True):
        self.config = config if config is not None else load_config()
        self.cache = cache if cache is not None else TermCache()
        self.prefer_oak = prefer_oak
        self.use_cache = use_cache
        self.stats = {"cache_hits": 0, "lookups": 0}

    def prefix_of(self, curie: str) -> str:
        return curie.split(":", 1)[0] if isinstance(curie, str) and ":" in curie else ""

    def policy_for(self, prefix: str) -> tuple[str, str | None]:
        """Return (kind, detail) where kind is "obo" | "custom" | "skip" | "unknown"."""
        if prefix in CUSTOM_RESOLVERS:
            return "custom", None
        if prefix not in self.config:
            return "unknown", f"prefix {prefix!r} is not listed in conf/oak_config.yaml"
        adapter = self.config[prefix]
        ont = ontology_name(adapter)
        if ont:
            return "obo", ont
        return "skip", f"prefix {prefix!r} is configured as not validated"

    def resolve(self, curie: str) -> TermResult:
        if not isinstance(curie, str) or ":" not in curie:
            return TermResult(str(curie), TermStatus.UNRESOLVED,
                              detail="not a CURIE (no prefix separator)")

        if self.use_cache:
            hit = self.cache.get(curie)
            if hit is not None:
                self.stats["cache_hits"] += 1
                return hit

        prefix = self.prefix_of(curie)
        kind, detail = self.policy_for(prefix)

        if kind in ("skip", "unknown"):
            return TermResult(curie, TermStatus.SKIPPED, detail=detail)

        self.stats["lookups"] += 1
        query = canonical_curie(curie)
        try:
            if kind == "custom":
                result = CUSTOM_RESOLVERS[prefix](query)
            else:
                result = self._resolve_obo(query, detail or "")
        except LookupError_ as exc:
            return TermResult(curie, TermStatus.UNRESOLVED, detail=str(exc))

        # Report against the corpus's own spelling, not the canonical one.
        if result.curie != curie:
            result = replace(result, curie=curie)

        if self.use_cache:
            self.cache.put(result)
        return result

    def _resolve_obo(self, curie: str, ontology: str) -> TermResult:
        """OAK first (the locked preference), OLS4 when OAK is unreachable.

        An OAK failure is not fatal and not evidence about the term — it just
        means we fall through. Only if OLS4 also fails does this raise, and the
        caller records UNRESOLVED.
        """
        if self.prefer_oak:
            try:
                return backends.resolve_oak(curie, f"sqlite:obo:{ontology}")
            except LookupError_:
                pass  # fall through to OLS4; reported by the caller if that fails too
        return backends.resolve_obo(curie, ontology)

    def flush(self) -> list[Path]:
        return self.cache.flush() if self.use_cache else []


def default_registry(**kwargs) -> Registry:
    return Registry(**kwargs)
