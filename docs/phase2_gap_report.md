# Phase 2 Gap Report — Validation Layers Against the Legacy Corpus

**PRD reference:** [PRD v3 §6 Phase 2](PRD_v3.md)
**Date:** May 2026
**Corpus:** 4,846 files in `kb/paths/`, profile `legacy` (Layers 1, 2, 3)

## Summary

| Layer | Status | Detail |
|---|---|---|
| **Layer 1** — schema | **PASS** | 4,846 / 4,846 files structurally valid against `MechanisticPath`. |
| **Layer 2** — node ontology | **FAIL** | 230 prefix violations across 190 files; 1,768 legacy-prefix warnings across 1,596 files. |
| **Layer 3** — predicate | **PASS** | 4,846 / 4,846 files; every edge `key` is a member of `BiolinkPredicate`. |
| **Layer 4** — reference | **NO-OP** | 0 files contain `evidence`; Layer 4 is skipped for the legacy profile by design. |

PRD Phase 2 exit criterion ("Layer 3 passes for 100% of legacy files") is **met**.

The Layer 2 failures and warnings are pre-existing data drift in the corpus and are documented below; Phase 2 surfaces them but does not fix them. Resolution work is sized for a follow-up (Phase 2.x or curator remediation sprint), not a Phase 2 exit blocker.

## Reproducibility

```
.venv-py310/bin/python scripts/qc.py                   # auto profile per file (defaults to legacy here)
.venv-py310/bin/python scripts/qc.py --profile legacy  # forced
.venv-py310/bin/python scripts/qc.py --json            # machine-readable
just qc                                                # if `just` is installed (brew install just)
```

Machine-readable Layer 2 output: [`phase2_layer2_failures.json`](phase2_layer2_failures.json).

## Layer 2 — Node ontology check

### Failures (230 total, 190 files)

These are nodes whose CURIE prefix does **not** match the canonical ontology for the declared Biolink `label` and is **not** a recognized legacy prefix. They almost certainly represent curation errors:

| # | Biolink label | Wrong prefix | Canonical | Likely fix |
|---:|---|---|---|---|
| 53 | `BiologicalProcess` | `MESH` | `GO` | Re-curate node ID against GO; many MESH disease IDs are mislabeled as processes |
| 34 | `GeneFamily` | `MESH` | `InterPro` | Map MESH "drug class" entries to InterPro families; some may be `ChemicalSubstance`, not `GeneFamily` |
| 34 | `PhenotypicFeature` | `MESH` | `HP` | Re-curate against HPO; MESH disease IDs are commonly miscast as phenotypes |
| 29 | `ChemicalSubstance` | `DB` | `MESH`, `CHEBI` | Re-label as `Drug` (DrugBank IDs are for `Drug` nodes), or rebind to MESH/CHEBI |
| 27 | `Protein` | `MESH` | `UniProt` | Re-map MESH protein records to UniProt accessions |
| 23 | `BiologicalProcess` | `reactome` | `GO` | Re-label as `Pathway` (Reactome is for pathways), or rebind to GO |
| 7 | `CellularComponent` | `MESH` | `GO` | Re-map MESH anatomy to GO cellular component |
| 6 | `BiologicalProcess` | `HP` | `GO` | Re-label as `PhenotypicFeature` (HPO IDs are phenotypes) |
| 6 | `GrossAnatomicalStructure` | `MESH` | `UBERON` | Re-map MESH anatomy to UBERON |
| 4 | `Cell` | `MESH` | `CL` | Re-map MESH cell records to Cell Ontology |
| 1 | `Disease` | `DB` | `MESH` | Almost certainly a `Drug`, not a `Disease` |
| 1 | `Disease` | `HP` | `MESH` | Re-label as `PhenotypicFeature` |
| 1 | `Drug` | `CHEBI` | `MESH`, `DB` | Rebind to MESH or add CHEBI to the canonical set if intentional |
| 1 | `Protein` | `InterPro` | `UniProt` | Re-label as `GeneFamily` (InterPro is families) |
| 1 | `GrossAnatomicalStructure` | `CL` | `UBERON` | Re-label as `Cell` |
| 1 | `GeneFamily` | `UniProt` | `InterPro` | Re-label as `Protein` |
| 1 | `ChemicalSubstance` | `GO` | `MESH`, `CHEBI` | Re-label as `BiologicalProcess` / `MolecularActivity` |

These are real curation errors with a clear remediation path: most can be fixed by either relabeling (cheap, no ID lookup) or rebinding (requires looking up the canonical ontology ID). They are out of scope for Phase 2's exit but should be addressed before Phase 4 launches the QC dashboard.

### Warnings (1,768 total, 1,596 files) — accepted legacy prefixes

The schema explicitly tolerates these legacy prefixes; they pass validation but are flagged for awareness.

| # | Biolink label | Legacy prefix | Canonical |
|---:|---|---|---|
| 1,347 | `OrganismTaxon` | `taxonomy` | `NCBITaxon` |
| 306 | `Pathway` | `reactome` | `REACT` |
| 112 | `GeneFamily` | `Pfam` | `InterPro` |
| 3 | `GeneFamily` | `TIGR` | `InterPro` |

Migrating these to canonical prefixes is a mechanical rewrite (similar shape to Phase 1 normalization) — recommend bundling into a Phase 2.x cleanup script. Not blocking.

### Deep-mode option (not run at this Phase 2 close)

`scripts/validate_node_ontology.py --deep` delegates to `linkml-term-validator validate-data` with the default `sqlite:obo:` adapter. This performs the **richer** checks the PRD describes:
- Whether each `id` actually resolves in its source ontology.
- Whether `name` matches the canonical ontology label (label drift detection).

Deep mode requires OAK to download SQLite copies of GO, HP, CL, UBERON, CHEBI, etc. (multi-hundred-MB first-run cost). It is supported by the tooling but not gated by the Phase 2 exit criterion; recommend wiring it into the GitHub Actions workflow with adapter caching during Phase 4.

## Layer 3 — Predicate validation

`Layer 3 PASS: 4846 files, every edge key is in BiolinkPredicate (67 canonical predicates).`

This was already the case at Phase 1.5 close. The Phase 2 standalone validator [`scripts/validate_predicates.py`](../scripts/validate_predicates.py) is a read-only check that complements the rewriting performed by [`scripts/canonicalize_predicates.py`](../scripts/canonicalize_predicates.py).

## Layer 4 — Reference verification

`Layer 4 NO-OP: 4846 files, none contain evidence to verify (legacy paths skip Layer 4 by design).`

End-to-end Layer 4 wiring is proven by the tests/ pytest suite, which exercises:

| Fixture | Expected | Actual |
|---|---|---|
| [`tests/fixtures/sample_ai_curated.yaml`](../tests/fixtures/sample_ai_curated.yaml) (verbatim snippet against cached PMID:99999999) | PASS | PASS |
| [`tests/fixtures/sample_ai_curated_bad_snippet.yaml`](../tests/fixtures/sample_ai_curated_bad_snippet.yaml) (snippet NOT in abstract) | FAIL | FAIL |

The synthetic PMID and abstract live at [`references_cache/PMID_99999999.md`](../references_cache/PMID_99999999.md). Real PubMed fetches use NCBI E-utilities (via `linkml-reference-validator`'s built-in fetcher); when a PMID is uncached, the validator hits NCBI, parses the abstract, and writes it to `references_cache/` for future runs. The cache file format is markdown with YAML frontmatter.

## Schema changes made during Phase 2

To unblock Layer 4 wiring, three small schema edits were applied to [`src/drugmechdb/schema/drugmechdb.yaml`](../src/drugmechdb/schema/drugmechdb.yaml):

1. **Added `oa:` and `dcterms:` to the `prefixes:` block** so the validator can resolve `oa:exact` and `dcterms:references`.
2. **Tagged `snippet` with `slot_uri: oa:exact`** — identifies the supporting-text slot to `linkml-reference-validator`.
3. **Tagged `reference` with `slot_uri: dcterms:references`** — identifies the citation slot.
4. **Renamed slot `path_id` (alias `_id`) → `_id`**. The `linkml-reference-validator`'s slot lookup did not honor LinkML aliases, so the slot name was changed to match the data. All 4,846 files already used `_id:`; no data migration required. Layer 1 still passes (verified).

## Recommendations / follow-up work

| Item | Owner | When |
|---|---|---|
| Resolve the 230 Layer-2 prefix failures (curation re-label / rebind) | Curators | Phase 2.x sprint, before dashboard launch |
| Mechanical rewrite of legacy prefixes (`taxonomy:` → `NCBITaxon:`, `reactome:` → `REACT:`, `Pfam:` / `TIGR:` → `InterPro:`) — bundle as a one-shot script analogous to `phase1_normalize_paths.py` | Phase 2.x | Bundle with Phase 4 dashboard work |
| Wire `--deep` Layer 2 into Phase 4 CI with adapter cache | Phase 4 | Phase 4 |
| Apply the `at least one of {drug_mesh, drugbank}` lint mentioned in [drugmechdb.yaml](../src/drugmechdb/schema/drugmechdb.yaml) Phase-1 comment | Phase 2.x | Before backfill campaign |
| Decide on tolerance for `linkml-reference-validator` whitespace normalization (currently exact substring) | Phase 3 agent design | Phase 3 |
