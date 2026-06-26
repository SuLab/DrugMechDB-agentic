"""Perplexity provider stub.

Implementation plan (when prioritized):

  - Use Perplexity API with the `sonar-pro` (or `sonar-reasoning`) model;
    these are web-grounded online models that return cited responses.
  - Endpoint: https://api.perplexity.ai/chat/completions (OpenAI-compatible).
  - Environment: PERPLEXITY_API_KEY.
  - Prompt: reuse SYSTEM_PROMPT + USER_PROMPT_TEMPLATE from claude.py with
    minor adjustments (Perplexity may prepend its own citation table).
  - Cost: ~$0.005 per query; significantly cheaper than Claude+web_search.
  - Citations are returned as a separate field — parse and dedup into
    candidate_pmids.

See docs/research_providers.md for the new-provider checklist.
"""

from __future__ import annotations

from .base import BaseProvider, ResearchDossier


class PerplexityProvider(BaseProvider):
    name = "perplexity"
    default_model = "sonar-pro"
    requires_env = ("PERPLEXITY_API_KEY",)

    def run(self, drug: str, disease: str) -> ResearchDossier:
        raise NotImplementedError(
            "PerplexityProvider is not yet implemented. See the docstring at "
            "scripts/research_providers/perplexity.py for the implementation "
            "plan. Track it under Phase 4b in PRD v3."
        )
