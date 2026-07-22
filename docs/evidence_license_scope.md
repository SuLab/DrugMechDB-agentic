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

## Open question flagged for the maintainer (CC-BY-NC committed snippets)

DrugBank Mechanism-of-Action text is **CC-BY-NC**. The default policy above allows committing a *short
attributed snippet* from it (as a quotation). If the lab prefers a stricter line — **committed snippets
only from OA / CC-BY sources**, with CC-BY-NC used purely to *locate* a claim which is then re-sourced
from an open-access source — that is a one-flag tightening.

- **Default (recommended): snippet-as-quotation is acceptable** for any source, because only a short
  attributed quote persists.
- **Stricter option (maintainer's call):** restrict committed snippets to OA / CC-BY.

This specific legal line is **left for the maintainer to confirm** (it ties to the DrugBank follow-up
in #67). Regardless of which is chosen, the enforcement below already prevents body redistribution.

## Enforcement

- **Ephemeral deletion:** `evidence_fetch.py strip-fulltext --all` (#67), run post-QC — removes every
  fetched body across all sources.
- **Committed shape:** the schema's `EvidenceItem` cannot hold a body; only snippet + citation.
- **Recommended (nice-to-have):** record each evidence item's **source license** in citation metadata,
  so a future tightening can filter committed snippets deterministically.

### See also
- `AGENTS.md` §4 (sourcing) and the CLAUDE.md "Ephemeral full text (anti-infringement)" note.
- Issue #67 (multi-source fetch + ephemeral full text) — the enforcement mechanism.
