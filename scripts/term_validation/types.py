"""Result types for term resolution.

The four-state `TermStatus` is the load-bearing design choice here: it keeps
"the ontology says this term does not exist" strictly separate from "we could
not ask the ontology". Collapsing those two into a boolean is how a flaky
network turns into fabricated evidence of bad data.
"""

from __future__ import annotations

import enum
from dataclasses import dataclass, asdict


class TermStatus(str, enum.Enum):
    """Outcome of resolving one CURIE against its source ontology."""

    EXISTS = "exists"
    """The ontology returned a record for this identifier."""

    ABSENT = "absent"
    """The ontology was reached and reported no such identifier. A real failure."""

    OBSOLETE = "obsolete"
    """The identifier resolves but is deprecated/deleted upstream — e.g. a
    UniProt accession with entryType "Inactive", or an OBO term flagged
    is_obsolete. Distinct from ABSENT: the record is not fabricated, it has
    aged out. Durable, so it is cached."""

    UNRESOLVED = "unresolved"
    """Could not ask: network error, timeout, the ontology itself unavailable,
    or no backend answered. NEVER counted as a failure — it is an absence of
    evidence, not evidence of absence."""

    SKIPPED = "skipped"
    """The prefix is deliberately not validated (see conf/oak_config.yaml)."""


@dataclass(frozen=True)
class TermResult:
    """One CURIE's resolution.

    `label` is the ontology's canonical label when known, and is what the
    name-match check compares a record's `name` against. It is None for every
    status except EXISTS (and may be None even then, if a backend resolves the
    identifier but exposes no label).
    """

    curie: str
    status: TermStatus
    label: str | None = None
    source: str | None = None
    """Which backend answered — e.g. "ols4", "oak:sqlite:obo:go", "uniprot"."""
    detail: str | None = None
    """Why, for UNRESOLVED / SKIPPED. Human-readable; never parsed."""
    synonyms: tuple[str, ...] = ()
    """Alternative labels the authority accepts, when it returns them in the
    same response (OLS4 and UniProt do; MeSH would need a second fetch per term,
    which is not worth 2,539 extra requests). Used only to suppress false name
    mismatches — a record is entitled to prefer a synonym."""

    @property
    def ok(self) -> bool:
        """True when this term is not a failure.

        UNRESOLVED and SKIPPED are never failures — we did not establish
        anything about them. ABSENT and OBSOLETE are."""
        return self.status not in (TermStatus.ABSENT, TermStatus.OBSOLETE)

    def to_dict(self) -> dict:
        d = asdict(self)
        d["status"] = self.status.value
        return d

    @classmethod
    def from_dict(cls, d: dict) -> "TermResult":
        return cls(
            curie=d["curie"],
            status=TermStatus(d["status"]),
            label=d.get("label"),
            source=d.get("source"),
            detail=d.get("detail"),
            synonyms=tuple(d.get("synonyms") or ()),
        )


class LookupError_(Exception):
    """A backend could not complete a lookup.

    Raised by resolvers instead of returning ABSENT, so the caller can record
    UNRESOLVED. Named with a trailing underscore to avoid shadowing the builtin.
    """
