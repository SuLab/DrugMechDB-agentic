"""External research-agent providers for DrugMechDB curation.

Each provider implements the BaseProvider interface in base.py and returns a
ResearchDossier — a structured markdown report with proposed PMIDs and a
mechanism narrative. The curation agent treats the dossier as advisory only;
every PMID is re-fetched via scripts/pubmed_fetch.py and every snippet is
verified by Layer 4 before landing in a path YAML.

Add a new provider by:
  1. Creating scripts/research_providers/<name>.py with a class
     subclassing BaseProvider
  2. Registering it in PROVIDERS below
  3. Implementing `run()` to return a ResearchDossier
"""

from __future__ import annotations

from .base import BaseProvider, ResearchDossier  # re-export
from .claude import ClaudeProvider
from .openai import OpenAIProvider
from .perplexity import PerplexityProvider
from .asta import AstaProvider

PROVIDERS: dict[str, type[BaseProvider]] = {
    ClaudeProvider.name: ClaudeProvider,
    OpenAIProvider.name: OpenAIProvider,
    PerplexityProvider.name: PerplexityProvider,
    AstaProvider.name: AstaProvider,
}

__all__ = ["BaseProvider", "ResearchDossier", "PROVIDERS"]
