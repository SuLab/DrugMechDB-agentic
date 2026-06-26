"""OpenAI provider — uses the OpenAI Responses API with the web_search tool.

A second external research agent, parallel to the claude provider. Like claude,
it runs in a separate API call from the curation agent and has access to live
web search, which the curation agent does NOT (PRD §5.1.1 restricts the
curation agent to PubMed E-utilities only).

The provider's job: propose PMIDs and a mechanism narrative. The curation
agent treats both as advisory and re-verifies every PMID via the PubMed
wrapper. This split is intentional — it lets the research agent be loose
(broad recall, web grounding) while the curation agent stays strict
(verbatim snippet contract).

Environment:
    OPENAI_API_KEY        required
    DMDB_OPENAI_MODEL     optional override (default: see DEFAULT_MODEL)
"""

from __future__ import annotations

import datetime as dt
import os
import re

from .base import BaseProvider, ResearchDossier

DEFAULT_MODEL = "gpt-5"
DEFAULT_MAX_OUTPUT_TOKENS = 16000

PMID_RE = re.compile(r"PMID:(\d{4,10})")


SYSTEM_PROMPT = """\
You are a biomedical literature research agent for DrugMechDB. Your role is to
research the mechanistic basis by which a drug treats or affects a disease,
proposing candidate PubMed citations that a downstream curation agent will
verify and use to build a Biolink-compliant mechanistic path.

Hard rules:
- Only cite PMIDs you have verified by web search (pubmed.ncbi.nlm.nih.gov or
  scholar.google.com). Do not fabricate PMIDs.
- Prefer primary research papers over reviews when both exist.
- Do not cite preprints (bioRxiv, medRxiv).
- Snippets you include are advisory only — they will be re-verified by the
  curation agent against the official cached PubMed abstract. The curation
  agent is bound by a verbatim-substring contract.
- Focus on the most well-established mechanism, not speculative pathways.
"""


USER_PROMPT_TEMPLATE = """\
Research the mechanism by which {drug} affects {disease}.

Produce a markdown response with EXACTLY this structure:

## Proposed mechanism summary
2–3 paragraphs describing the mechanistic pathway from {drug} to its effect
on {disease}, with inline (PMID:XXXX) citations.

## Candidate PMIDs
Bulleted list, 5–15 PMIDs ordered by relevance:
- PMID:XXXXXXXX — One-sentence relevance note.
- ...

Only include PMIDs you verified exist via web search.

## Mechanism graph proposal (advisory)
Drug → intermediate1 → intermediate2 → ... → Disease

Each arrow labeled with a Biolink-style predicate (e.g., "decreases activity
of", "positively regulates", "contributes to"). This topology is advisory —
the curation agent will validate it.

Output ONLY the markdown body. No preamble or closing remarks.
"""


class OpenAIProvider(BaseProvider):
    name = "openai"
    default_model = DEFAULT_MODEL
    requires_env = ("OPENAI_API_KEY",)

    def __init__(self, model: str | None = None):
        super().__init__(model=model or os.environ.get("DMDB_OPENAI_MODEL", DEFAULT_MODEL))

    def run(self, drug: str, disease: str) -> ResearchDossier:
        for var in self.requires_env:
            if not os.environ.get(var):
                raise RuntimeError(
                    f"{self.name} provider requires environment variable {var}. "
                    "Get an API key at https://platform.openai.com/api-keys and "
                    "`export OPENAI_API_KEY=...`."
                )

        # Import inside run() so unrelated subcommands don't pay the import cost.
        try:
            from openai import OpenAI  # type: ignore
        except ImportError as e:
            raise RuntimeError(
                "openai package not installed. Run "
                "`.venv-py310/bin/pip install openai`."
            ) from e

        client = OpenAI()
        query = USER_PROMPT_TEMPLATE.format(drug=drug, disease=disease)

        # Responses API is OpenAI's agentic primitive — analogous to Anthropic
        # messages.create with tools. `web_search` is the built-in tool;
        # older SDK versions called it `web_search_preview` — swap if your
        # SDK errors with "unknown tool type".
        response = client.responses.create(
            model=self.model,
            instructions=SYSTEM_PROMPT,
            input=query,
            tools=[{"type": "web_search"}],
            max_output_tokens=DEFAULT_MAX_OUTPUT_TOKENS,
        )

        # `output_text` concatenates the assistant's text output, skipping
        # tool-call records — analogous to walking content blocks of type "text"
        # in the Anthropic SDK.
        markdown_body = (getattr(response, "output_text", "") or "").strip()

        if not markdown_body:
            status = getattr(response, "status", None)
            incomplete = getattr(response, "incomplete_details", None)
            reason = getattr(incomplete, "reason", None) if incomplete else None
            raise RuntimeError(
                f"{self.name} provider returned no text content; "
                f"status={status!r}, incomplete_reason={reason!r}. "
                f"If reason='max_output_tokens', raise DEFAULT_MAX_OUTPUT_TOKENS."
            )

        pmids = self._extract_pmids(markdown_body)

        usage = getattr(response, "usage", None)
        notes = ""
        if usage is not None:
            notes = (
                f"input_tokens={getattr(usage, 'input_tokens', '?')}, "
                f"output_tokens={getattr(usage, 'output_tokens', '?')}"
            )

        return ResearchDossier(
            provider=self.name,
            model=self.model,
            drug=drug,
            disease=disease,
            query=query,
            generated_at=dt.datetime.now(dt.timezone.utc),
            markdown_body=markdown_body,
            candidate_pmids=pmids,
            raw_response=markdown_body,
            notes=notes,
        )

    @staticmethod
    def _extract_pmids(text: str) -> list[str]:
        """Dedup PMID curies in order of first appearance."""
        seen: dict[str, None] = {}
        for match in PMID_RE.finditer(text):
            curie = f"PMID:{match.group(1)}"
            seen.setdefault(curie, None)
        return list(seen.keys())
