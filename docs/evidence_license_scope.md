# Evidence full-text / open-access license scope

> **Decision:** the **committed** artifact is always only a **short verbatim snippet + citation
> metadata** — never a full-text body. Full-text bodies are fetched **ephemerally** (to locate and
> verify the snippet) and **deleted after QC**. This keeps the project in attributed-quotation
> territory, not redistribution, regardless of the source body's license.

## Tiers

| Source license | Full text may be fetched? | What is committed |
|---|---|---|
| Abstract / open-access (CC0, CC-BY, public domain, government works) | yes | verbatim snippet + citation |
| Non-open (CC-BY-**NC**, publisher copyright, closed) | **ephemerally only** — fetch to locate + verify the snippet, then delete post-QC | verbatim snippet + citation only |
| — | full-text **body** of any non-open source | **never committed** |

## Why this is safe

- The **ephemeral model** (built in #67) guarantees no full-text body is ever committed — the body is
  fetched, the snippet is extracted + verbatim-verified (QC Layer 4), and the body is stripped by
  `evidence_fetch.py strip-fulltext` after the record passes QC.
- A **short verbatim snippet with attribution is a quotation/citation**, not redistribution — standard
  scholarly practice. The committed `EvidenceItem` has no body field: only `reference` (CURIE),
  `snippet` (verbatim), `supports`, `evidence_source`.

## DrugBank dropped as a source (2026-07)

DrugBank has been removed as an evidence source. Its Terms of Use bar creating "derivative databases"
from its content, which is incompatible with redistributing snippets in this CC0 knowledge base. The
agentic workflow no longer fetches DrugBank content or stores DrugBank IDs for new records. (Legacy
records keep their DrugBank IDs as identifiers — those are accession numbers, not DrugBank content.)

The general **non-open tier** above still governs any *other* CC-BY-NC / copyrighted source: a short
attributed snippet persists as a quotation; the full-text body is fetched only ephemerally and deleted
post-QC. If the lab prefers a stricter line — committed snippets only from OA / CC-BY sources — that
remains a one-flag tightening left for the maintainer to confirm.

## Enforcement

- **Ephemeral deletion:** `evidence_fetch.py strip-fulltext --all` (#67), run post-QC — removes every
  fetched body across all sources.
- **Committed shape:** the schema's `EvidenceItem` cannot hold a body; only snippet + citation.
- **Recommended (nice-to-have):** record each evidence item's **source license** in citation metadata,
  so a future tightening can filter committed snippets deterministically.

### See also
- `AGENTS.md` §4 (sourcing) and the CLAUDE.md "Ephemeral full text (anti-infringement)" note.
- Issue #67 (multi-source fetch + ephemeral full text) — the enforcement mechanism.
