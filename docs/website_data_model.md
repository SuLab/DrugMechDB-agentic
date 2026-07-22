# What the website surfaces (data-model design)

> **Decision:** the next-generation DrugMechDB site surfaces the corpus through the pages already in
> `web-revamp-mockup/`, each backed by the data adapter `web-revamp-mockup/dmdb-data.js`
> (`getIndex` / `getRecord` / `getDashboard`). The design goal, taken from Dismech, is to move
> beyond the old graph-only site to **evidence-, provenance-, and quality-transparent** browsing —
> while staying static and zero-dependency so it hosts as plain files.

## Views and their data contracts

| View (page) | Surfaces | Adapter method | Backing data |
|---|---|---|---|
| **Browse / search** (`browse.html`) | field-boosted search + facets (disease area, node type present, path length) over every path | `getIndex()` | a lightweight per-record index (drug, disease, target, area, node types, step count, id) |
| **Record** (`record.html`) | the pathograph (drug→…→disease), concepts (nodes + CURIEs), relationships (edges + predicates), **per-edge evidence** (verbatim snippet + citation), **provenance**, semantic-validation status, and View-source / Download / Cite | `getRecord(id)` | one record's full graph + its `evidence` + provenance sidecar |
| **Embeddings** (`embeddings.html`) | similarity/neighborhood scatter over the corpus | (future) | node/path embeddings (not yet computed) |
| **Dashboard** (`dashboard.html`) | corpus health: QC-by-layer, structural-quality, coverage, provenance, records-needing-attention | `getDashboard()` | `data/dashboard.json` computed by `scripts/compute_dashboard_metrics.py` (#68) |
| **Docs** (`docs.html`) | schema, conventions, how to read a path, API/export pointers | static | — |

## What is new vs. the legacy DrugMechDB site (Dismech-parity)

The old site was essentially a **graph viewer**. The revamp adds the machinery Dismech demonstrates for
a living, self-validating KB:

1. **Per-edge evidence, in the open** — each edge shows its verbatim snippet + citation (source-agnostic,
   #59/#67), not just a record-level URL list.
2. **Provenance** — each AI-curated record shows how it was produced (model, prompt version, run) from
   the provenance sidecar the engine stamps (#55).
3. **Quality transparency** — the dashboard exposes QC-by-layer + structural-quality + records-needing-
   attention (#68), so the corpus's health is visible, not implicit.
4. **Machine-readable exports** — KGX (#18) and Cytoscape CX2 (#36) are linkable from the site, closing
   the ecosystem loop.

## Constraints this honors

- **Static + zero-dependency.** No build step; the site is plain HTML/CSS/JS served as files (deploy
  workflow is dormant, #39). This is what makes hosting cheap and the download small.
- **Data via one swap-point.** Every page reads through `dmdb-data.js`; "sample" mode uses bundled
  fixtures, "live" mode fetches `data/*.json`. Wiring the real corpus post-forwardfill is a one-flag
  change, no page edits.
- **Minimal visual design** — one flat accent + white + plain bordered containers; no decorative
  gradients/ramps. (See the a11y pass, #43.)

## Not yet backed by data (tracked)

- **Embeddings** view — needs computed node/path embeddings.
- **Coverage / treatment-target / priority-to-curate** dashboard panels — need an external
  approved-indication list + curated evidence (flagged `measured:false` in #68).
- The **real corpus** lands in "live" mode after forwardfill; today the pages render sample data.
