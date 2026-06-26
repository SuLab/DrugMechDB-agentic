---
name: dmdb-references
description: Add, validate, and repair per-edge evidence on DrugMechDB paths so every snippet is a verbatim substring of its cited source. Use when adding evidence, when QC Layer 4 (reference verification) fails, or when backfilling PMIDs onto a path.
---

# dmdb-references — evidence & verbatim snippets

This skill backs **QC Layer 4** (`scripts/validate_references.py`, via
`linkml-reference-validator`). It enforces the one contract that makes the KB
machine-verifiable: **a snippet must appear verbatim in the source it cites.**

## The contract

Each `EvidenceItem` on an edge:

```yaml
links:
  - key: decreases activity of
    source: MESH:D000068818
    target: UniProt:P00533
    evidence:
      - reference: PMID:12345678        # the cited source
        snippet: "exact substring copied from that source's text"
        supports: SUPPORT               # SUPPORT | PARTIAL | REFUTE | NO_EVIDENCE | WRONG_STATEMENT
        evidence_source: HUMAN_CLINICAL  # HUMAN_CLINICAL | MODEL_ORGANISM | IN_VITRO | COMPUTATIONAL | OTHER
        explanation: "optional curator note"
```

- **Never fabricate a snippet.** It must be a literal substring of the referenced
  document. The validator does exact substring matching against the cached text.
- An edge with no supporting source uses `supports: NO_EVIDENCE` + an `explanation`,
  rather than a guessed citation.

## Workflow

1. **Fetch the source into the cache first** (the validator reads `references_cache/`):
   - `.venv-py310/bin/python scripts/pubmed_fetch.py search "<query>"`
   - `.venv-py310/bin/python scripts/pubmed_fetch.py fetch PMID:12345678`
   This writes `references_cache/PMID_12345678.md` (the abstract).
   **You may not hand-edit `references_cache/` — it is script-write-only (a pre-edit hook
   blocks Edit/Write there). That is what makes the verbatim check trustworthy: the agent
   cannot author the source text it later cites.**
2. **Escalate to full text only if the abstract is insufficient for an edge** (not by default):
   - `pubmed_fetch.py probe PMID:12345678 --json` — is open-access full text available? (no download)
   - `pubmed_fetch.py fetch PMID:12345678 --fulltext` — upgrade the cache to `content_type:
     full_text` (abstract prepended), then snippet from the body. See AGENTS.md §4.4.
3. **Copy the snippet verbatim** from that cached source (abstract or full text) into the edge.
4. **Validate offline** (deterministic, no network):
   `just qc-layer 4 kb/paths/<file>.yaml` or `just qc <file>` — Layer 4 runs `--offline`
   against the committed cache. The pre-edit hook does the same on every write.

## Matcher operators & full-text guards

The matcher normalizes whitespace, case, and punctuation, and supports two operators —
handy when snippeting messy full-text prose, but use them sparingly:

- `...` — order-independent multi-part match. Bridge an unavoidable inline-citation artifact:
  `snippet: "aspirin acetylates ... cyclooxygenase 1"`.
- `[...]` — drop an editorial insert from the query.

When snippeting **full text**, read the surrounding context before setting `supports`:
- A substring hit may sit in a **negated/refuted** sentence → `REFUTE` / `WRONG_STATEMENT` /
  `NO_EVIDENCE`, not `SUPPORT`.
- In a **multi-drug** paper, confirm the matched sentence's subject is *your* drug/entity.
- Bibliographies and raw table cells are excluded from the cached body, so a match won't
  come from a reference list.

## Source-policy note (read before scaling)

The *machinery* is source-agnostic — it verifies "snippet ⊂ cited source" regardless of
source. The **policy** is to cite the **secondary source that asserts the established
mechanism** (DrugBank MoA, GO, UniProt, Reactome, reviews) and to bar primary-literature
reconstruction. This policy is under review — confirm it with the maintainers before a
large backfill run. Until then, keep snippets verbatim and the `reference` honest about
its source.

Full-text escalation currently allows *any* open-access article (broader than
secondary-source-only) and commits the fetched body to the cache. Full text comes from the
redistribution-permissive PMC open-access subset, but some carry non-commercial (`cc by-nc`)
licenses — flagged for maintainer review. The fetcher records each source's `license` in
the cache frontmatter for audit.
