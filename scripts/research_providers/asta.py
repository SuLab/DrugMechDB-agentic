"""Asta provider stub.

Implementation plan (when prioritized):

  - Asta is Allen AI's Scholar QA / literature search agent. It returns
    a different shape than narrative-style providers: a ranked list of
    papers with summaries, evidence snippets, and relevance scores.
  - Endpoint: documented at https://asta.allen.ai/ (requires Semantic
    Scholar / Asta API access).
  - Environment: ASTA_API_KEY.
  - Asta's output is closer to the "candidate PMIDs" half of our dossier
    format than to the "mechanism summary" half — so the adapter should
    map Asta's per-paper output into the bulleted PMID list and synthesize
    a brief summary section from the top results.
  - DisMech defaults to Asta because its literature-search style aligns
    well with their evidence-snippet workflow; the same case applies here
    once we have multiple providers and want to use them in parallel.

See docs/research_providers.md for the new-provider checklist.
"""

from __future__ import annotations

from .base import BaseProvider, ResearchDossier


class AstaProvider(BaseProvider):
    name = "asta"
    default_model = "asta-default"
    requires_env = ("ASTA_API_KEY",)

    def run(self, drug: str, disease: str) -> ResearchDossier:
        raise NotImplementedError(
            "AstaProvider is not yet implemented. See the docstring at "
            "scripts/research_providers/asta.py for the implementation plan. "
            "Track it under Phase 4b in PRD v3."
        )
