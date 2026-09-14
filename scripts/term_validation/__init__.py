"""
Term validation — does a node's CURIE actually EXIST in its source ontology,
and does the record's `name` match the ontology's canonical label?

WHY THIS EXISTS
    Layer 2 (scripts/validate_node_ontology.py) checks that a CURIE's *prefix*
    matches the canonical ontology for its Biolink type — `Protein` -> `UniProt`.
    It never asks whether the identifier resolves. So every one of these passes
    the full QC gate today:

        UniProt:P99999   (well-formed, does not exist)
        GO:0000000       (well-formed, does not exist)
        MESH:D999999     (well-formed, does not exist)
        UniProt:P21397 named "Banana ripening factor 7"   (real ID, wrong name)

    Fabricated identifiers are the characteristic failure of LLM-assisted
    curation, so this is the gap that matters most for an agent-curated KB.

THE ONE INVARIANT
    A lookup that FAILS is not the same as a term that is ABSENT. A network
    timeout must never be recorded as "this term does not exist" — that would
    turn a flaky connection into false evidence of a bad record. Hence
    `TermStatus` has four states, not a boolean, and UNRESOLVED is never
    counted as a failure.

BACKENDS (see resolvers.py for the prefix -> backend routing)
    OBO ontologies (GO/HP/CL/UBERON/CHEBI/PR/NCBITaxon)
        OAK `sqlite:obo:` adapters when reachable (offline, deterministic,
        the locked project decision), else the EBI OLS4 REST API.
    Non-OBO (MESH/UniProt/Reactome)
        Their own REST APIs — these have no OBO adapter. The scripts named in
        conf/oak_config.yaml (validate_mesh.py / validate_uniprot.py /
        validate_reactome.py) are thin CLIs over these resolvers.

DETERMINISM
    Every resolution is cached on disk (cache.py) keyed by CURIE. The cache is
    committed so CI and a fresh clone reproduce an audit without network access.
"""

from .types import TermResult, TermStatus
from .cache import TermCache
from .resolvers import Registry, load_config, default_registry

__all__ = [
    "TermResult",
    "TermStatus",
    "TermCache",
    "Registry",
    "load_config",
    "default_registry",
]
