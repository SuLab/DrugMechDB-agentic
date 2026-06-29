"""Provider abstraction for external research agents."""

from __future__ import annotations

import datetime as dt
from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class ResearchDossier:
    """The structured artifact a research provider returns.

    The `markdown_body` is the human-readable section that gets written to
    research/<slug>-<provider>.md. The other fields are the parsed/structured
    metadata that lands in the file's YAML frontmatter and is consumed by
    the curation agent.
    """

    provider: str                                # e.g. "claude"
    model: str                                   # e.g. "claude-opus-4-8"
    drug: str
    disease: str
    query: str                                   # the actual query string passed to the provider
    generated_at: dt.datetime                    # UTC
    markdown_body: str                           # the dossier body (no frontmatter)
    candidate_pmids: list[str] = field(default_factory=list)  # ["PMID:23422285", …]
    raw_response: str = ""                        # full provider response for archival; may equal markdown_body
    cost_usd: float | None = None                 # optional, if the provider reports it
    notes: str = ""                               # provider-specific notes (rate-limit warnings, etc.)


class BaseProvider(ABC):
    """Abstract base for research providers.

    Subclasses MUST set the `name` class attribute (used for CLI dispatch and
    cache filenames) and implement `run`. Subclasses SHOULD also set a
    `default_model` if they invoke an underlying LLM.
    """

    name: str = ""
    default_model: str = ""
    requires_env: tuple[str, ...] = ()  # env vars that must be set before run()

    def __init__(self, model: str | None = None):
        self.model = model or self.default_model

    @abstractmethod
    def run(self, drug: str, disease: str) -> ResearchDossier:
        """Execute the research query. Returns a ResearchDossier or raises."""
